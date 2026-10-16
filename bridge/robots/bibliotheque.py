"""Bibliothèque fermée de gestes et de séquences, par robot (P2.2, P2.4 ; plan de prévention P2.1, §6.4–6.5).

Règles communes à tous les robots :
* un module d'IA ne peut proposer que le NOM d'une entrée de la bibliothèque ;
* chaque entrée porte un statut, qui ne progresse que d'un cran à la fois, par décision humaine signée et
  appuyée sur un essai consigné : brouillon → valide_sim (essai complet en simulation) → valide_robot_lent
  (essai complet sur le robot, vitesse réduite) → valide ;
* sur un robot réel : « brouillon » est refusé ; « valide_sim » et « valide_robot_lent » sont joués à vitesse
  réduite (durées doublées) ; seule une entrée « valide » est jouée à pleine vitesse. En simulation, tout
  statut est jouable.

Deux sources :
* BibliothequeJSON — séquences d'images clés articulaires (sequences/*.json) : ESP32, AiNex, ROS, etc. ;
* BibliothequeP2 — gestes et séquences du Reachy Mini (modules/p2/gestes_scene, YAML), en lecture seule :
  leur statut se modifie dans le fichier YAML après lecture du rapport du jumeau numérique MuJoCo.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

STATUTS = ("brouillon", "valide_sim", "valide_robot_lent", "valide")
FACTEUR_LENT = 0.5


class RefusBibliotheque(Exception):
    pass


def exigence(statut: str, cible_reelle: bool) -> tuple[bool, float, str]:
    """(autorisé, facteur de vitesse, motif) selon le statut et la cible (P2.1, §6.5)."""
    if statut not in STATUTS:
        return False, 0.0, f"statut inconnu « {statut} »"
    if not cible_reelle:
        return True, 1.0, "simulation : tout statut est jouable"
    if statut == "brouillon":
        return False, 0.0, "statut « brouillon » : valider d'abord en simulation (P2.1, §6.5)"
    if statut in ("valide_sim", "valide_robot_lent"):
        return True, FACTEUR_LENT, f"statut « {statut} » : vitesse réduite de moitié sur le robot réel"
    return True, 1.0, "statut « valide » : pleine vitesse"


def ralentir(images: list[dict[str, Any]], facteur: float) -> list[dict[str, Any]]:
    if facteur >= 1:
        return images
    return [{**im, "ms": float(im.get("ms", 800)) / facteur, "pause_ms": float(im.get("pause_ms", 0)) / facteur}
            for im in images]


def _nom_sur(nom: str) -> str:
    # Forme NFC d'abord : en NFD (fréquent sous macOS), les accents combinants ne sont pas des \w et étaient
    # retirés, si bien que « révérence » devenait « reverence » (refus « Séquence inconnue » de S04_001).
    nom = unicodedata.normalize("NFC", nom or "")
    sur = re.sub(r"[^\w\- ]", "", nom, flags=re.UNICODE).strip()
    if not sur:
        raise RefusBibliotheque("Nom de séquence invalide")
    return sur


class BibliothequeJSON:
    lecture_seule = False

    def __init__(self, dossier: Path, n_articulations: int, fichier_essais: Path | None = None):
        self.dossier = Path(dossier)
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.n = n_articulations
        # Les essais sont consignés hors du fichier de la séquence (le contenu et le statut n'en sont pas modifiés)
        self.fichier_essais = Path(fichier_essais) if fichier_essais else self.dossier / "_essais.jsonl"

    def _chemin(self, nom: str) -> Path:
        return self.dossier / f"{_nom_sur(nom)}.json"

    def lister(self) -> list[str]:
        return sorted(unicodedata.normalize("NFC", p.stem) for p in self.dossier.glob("*.json")
                      if not p.stem.startswith("_"))

    def lire(self, nom: str) -> dict[str, Any]:
        p = self._chemin(nom)
        if not p.exists():                     # fichier enregistré en NFD sur un système qui ne normalise pas
            cible = p.name
            p = next((q for q in self.dossier.glob("*.json") if unicodedata.normalize("NFC", q.name) == cible), p)
        if not p.exists():
            raise RefusBibliotheque(f"Séquence inconnue : {nom}")
        d = json.loads(p.read_text(encoding="utf-8"))
        d.setdefault("statut", "brouillon")
        d.setdefault("validations", [])
        d["essais"] = self._essais(p.stem)
        return d

    def _essais(self, nom: str) -> list[dict[str, Any]]:
        if not self.fichier_essais.exists():
            return []
        out = []
        for l in self.fichier_essais.read_text(encoding="utf-8").splitlines():
            if l.strip():
                e = json.loads(l)
                if e.get("nom") == nom:
                    out.append(e)
        return out

    def statuts(self) -> dict[str, str]:
        return {n: self.lire(n)["statut"] for n in self.lister()}

    def enregistrer(self, seq: dict[str, Any]) -> str:
        images = seq.get("images") or []
        if not images:
            raise RefusBibliotheque("Séquence vide")
        for im in images:
            if len(im.get("deg", [])) != self.n:
                raise RefusBibliotheque("Chaque image doit fixer tous les angles")
        p = self._chemin(seq.get("nom", ""))
        # Toute modification du contenu ramène la séquence au statut « brouillon » (nouvelle validation exigée)
        ancien = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        statut = ancien.get("statut", "brouillon") if ancien.get("images") == images else "brouillon"
        d = {"nom": p.stem, "images": images, "statut": statut,
             "validations": ancien.get("validations", []) if statut != "brouillon" else []}
        if statut == "brouillon" and ancien:
            d["version_anterieure_invalidee"] = datetime.now().astimezone().isoformat(timespec="seconds")
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        return p.stem

    def consigner_essai(self, nom: str, cible: str, vitesse: str, complet: bool) -> None:
        empreinte = json.dumps(self.lire(nom)["images"], sort_keys=True)
        import hashlib
        self.fichier_essais.parent.mkdir(parents=True, exist_ok=True)
        with self.fichier_essais.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"nom": _nom_sur(nom), "date": datetime.now().astimezone().isoformat(timespec="seconds"),
                                "cible": cible, "vitesse": vitesse, "complet": bool(complet),
                                "contenu": hashlib.sha256(empreinte.encode()).hexdigest()[:16]},
                               ensure_ascii=False) + "\n")

    def promouvoir(self, nom: str, statut: str, auteur: str, note: str = "") -> dict[str, Any]:
        d = self.lire(nom)
        if statut not in STATUTS:
            raise RefusBibliotheque(f"Statut inconnu : {statut}")
        i, j = STATUTS.index(d["statut"]), STATUTS.index(statut)
        if not auteur.strip():
            raise RefusBibliotheque("La promotion exige le nom ou les initiales de la personne qui valide")
        if j != i + 1:
            raise RefusBibliotheque(f"Un cran à la fois : « {d['statut']} » → « {STATUTS[i + 1] if i + 1 < len(STATUTS) else '—'} »")
        preuve = {"valide_sim": ("sim", None), "valide_robot_lent": ("robot", "lente"), "valide": ("robot", "lente")}[statut]
        import hashlib
        contenu = hashlib.sha256(json.dumps(d["images"], sort_keys=True).encode()).hexdigest()[:16]
        ok = any(e["complet"] and e["cible"] == preuve[0] and (preuve[1] is None or e["vitesse"] == preuve[1])
                 and e.get("contenu") == contenu for e in d["essais"])
        if not ok:
            raise RefusBibliotheque(f"Aucun essai complet consigné ({preuve[0]}"
                                    f"{', vitesse ' + preuve[1] if preuve[1] else ''}) pour justifier « {statut} »")
        d["statut"] = statut
        d["validations"].append({"date": datetime.now().astimezone().isoformat(timespec="seconds"),
                                 "statut": statut, "auteur": auteur.strip()[:60], "note": note[:300]})
        brut = {k: v for k, v in d.items() if k != "essais"}
        self._chemin(nom).write_text(json.dumps(brut, ensure_ascii=False, indent=2), encoding="utf-8")
        return d


class BibliothequeP2:
    """Gestes et séquences du Reachy Mini (YAML du prototype P2), convertis en images clés unifiées."""
    lecture_seule = True

    def __init__(self, chemin_gestes: str | Path | None = None, chemin_sequences: str | Path | None = None):
        from .. import _modules  # noqa: F401
        from gestes_scene import charger, charger_sequences, valider
        self.gestes = charger(chemin_gestes)
        self.gestes.update(charger_sequences(chemin_sequences, dict(self.gestes)))
        self.non_conformes = {n: e for n, g in self.gestes.items() if (e := valider(g))}

    def lister(self) -> list[str]:
        return sorted(self.gestes)

    def statuts(self) -> dict[str, str]:
        return {n: g.statut for n, g in self.gestes.items()}

    def lire(self, nom: str) -> dict[str, Any]:
        g = self.gestes.get(nom)
        if g is None:
            raise RefusBibliotheque(f"Geste inconnu : {nom}")
        if nom in self.non_conformes:
            raise RefusBibliotheque(f"{nom} : non conforme aux limites ({self.non_conformes[nom][0]})")
        images = [{"deg": [k.tete["x"], k.tete["y"], k.tete["z"], k.tete["roll"], k.tete["pitch"], k.tete["yaw"],
                           k.body_yaw, k.antennes[0], k.antennes[1]], "ms": k.duree * 1000} for k in g.images_cles]
        return {"nom": nom, "images": images, "statut": g.statut, "description": g.description,
                "intention": g.intention, "laban": g.laban, "essais": [], "validations": []}

    def enregistrer(self, seq):
        raise RefusBibliotheque("Bibliothèque P2 en lecture seule : modifier bibliotheque_gestes.yaml")

    def consigner_essai(self, *a, **k) -> None:
        pass

    def promouvoir(self, *a, **k):
        raise RefusBibliotheque("Statut P2 : à modifier dans le fichier YAML après lecture du rapport du jumeau MuJoCo")
