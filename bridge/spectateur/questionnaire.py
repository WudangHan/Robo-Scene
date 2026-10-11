"""Moteur de questionnaires (S-05) : instruments I-7 (après la présentation) et I-6 (après l'atelier).

Les instruments sont décrits en YAML (dossier « questionnaires/ ») à partir de T.1 et du dictionnaire A.2.
Un énoncé dont le texte n'a pas encore été saisi (« fr: null ») bloque le mode public : la plateforme ne
présente jamais à une personne participante un énoncé incomplet ou une traduction non validée.

Règles appliquées à la réception d'une réponse (plan d'analyse A.2, § 3 et § 5) :
* admissibilité « 18 ans ou plus » non cochée → rien n'est enregistré (exclusion avant collecte) ;
* « présence complète » enregistrée telle quelle : l'exclusion des présences partielles se fait à l'analyse ;
* identifiant de réponse aléatoire, date au jour près seulement, aucune adresse IP, aucun témoin ;
* valeurs hors échelle refusées ; énoncés facultatifs laissés vides permis (valeur manquante « NA »).
"""
from __future__ import annotations

import csv
import secrets
import threading
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

TEXTE_MAX = 1000


class ReponseInvalide(ValueError):
    pass


@dataclass
class Enonce:
    id: str
    partie: str
    type: str                      # echelle | differentiel | curseur | choix | texte
    fr: str | None
    en: str | None
    min: int | None = None
    max: int | None = None
    valeurs: list[str] | None = None
    libelles: dict[str, list[str]] | None = None
    ancres: dict[str, list[str]] | None = None
    facultatif: bool = False
    inverse: bool | None = None
    condition: dict[str, str] | None = None
    note: str | None = None

    def complet(self, langue: str = "fr") -> bool:
        if not (self.en if langue == "en" else self.fr):
            return False
        return not (self.type == "choix" and not self.valeurs)

    def public(self, langue: str, essai: bool) -> dict[str, Any]:
        texte = self.en if langue == "en" else self.fr
        if not texte and essai:
            texte = f"[{self.id} — texte à saisir]"
        d = {"id": self.id, "type": self.type, "texte": texte, "facultatif": self.facultatif}
        if self.type in ("echelle", "differentiel", "curseur"):
            d.update(min=self.min, max=self.max)
            if self.ancres:
                d["ancres"] = self.ancres.get(langue) or self.ancres.get("fr")
        if self.type == "choix":
            d["valeurs"] = self.valeurs or []
            lib = (self.libelles or {}).get(langue) or (self.libelles or {}).get("fr") or self.valeurs or []
            d["libelles"] = lib
        return d


@dataclass
class Instrument:
    id: str
    titre: dict[str, str]
    anonyme: bool
    jeu: str
    feuillet: dict[str, str | None]
    admissibilite: list[dict[str, Any]]
    presence: dict[str, Any] | None
    parties: list[dict[str, Any]]
    enonces: list[Enonce] = field(default_factory=list)
    chemin: Path | None = None

    # ── Chargement ──────────────────────────────────────────
    @classmethod
    def charger(cls, chemin: str | Path) -> "Instrument":
        d = yaml.safe_load(Path(chemin).read_text(encoding="utf-8"))
        ins = cls(id=d["instrument"], titre=d.get("titre", {}), anonyme=bool(d.get("anonyme", True)),
                  jeu=str(d.get("jeu_de_donnees", "")), feuillet=d.get("feuillet_information") or {},
                  admissibilite=d.get("admissibilite") or [], presence=d.get("presence"), parties=[],
                  chemin=Path(chemin))
        for p in d.get("parties") or []:
            ech = p.get("echelle") or {}
            type_partie = "differentiel" if ech.get("type") == "differentiel" else "echelle"
            ids = []
            for e in p.get("enonces") or []:
                t = e.get("type") or type_partie
                en = Enonce(id=e["id"], partie=p["id"], type=t, fr=e.get("fr"), en=e.get("en"),
                            min=e.get("min", ech.get("min")), max=e.get("max", ech.get("max")),
                            valeurs=[str(v) for v in e["valeurs"]] if e.get("valeurs") else None,
                            libelles=e.get("libelles"),
                            ancres={k: ech[k] for k in ("fr", "en") if ech.get(k)} or None,
                            facultatif=bool(e.get("facultatif") or p.get("facultatif")),
                            inverse=e.get("inverse"), condition=p.get("condition"), note=e.get("note"))
                ins.enonces.append(en)
                ids.append(en.id)
            ins.parties.append({"id": p["id"], "titre": p.get("titre", {}), "condition": p.get("condition"),
                                "facultatif": bool(p.get("facultatif")), "enonces": ids, "note": p.get("note")})
        return ins

    @property
    def colonnes(self) -> list[str]:
        cols = ["id_reponse", "instrument", "id_representation", "cond_support", "cond_provenance", "date",
                "langue", "mode"]
        if not self.anonyme:
            cols.append("pseudonyme")
        cols += [e.id for e in self.enonces]
        if self.presence:
            cols.append(self.presence["id"])
        return cols

    # ── Préparation ─────────────────────────────────────────
    def manques(self, langue: str = "fr") -> list[str]:
        """Ce qui empêche la passation publique dans cette langue."""
        m = []
        if not (self.feuillet or {}).get(langue):
            m.append(f"feuillet d'information ({langue})")
        for e in self.enonces:
            if not e.complet(langue):
                m.append(e.id)
        for a in self.admissibilite:
            if not a.get(langue):
                m.append(f"admissibilité {a.get('id')} ({langue})")
        return m

    def visibles(self, condition: dict[str, str] | None) -> list[Enonce]:
        cond = condition or {}
        return [e for e in self.enonces
                if not e.condition or all(cond.get(k) == v for k, v in e.condition.items())]

    def formulaire(self, langue: str, condition: dict[str, str] | None, essai: bool) -> dict[str, Any]:
        """Description publique : jamais de note interne, jamais de condition expérimentale."""
        vis = {e.id for e in self.visibles(condition)}
        par_id = {e.id: e for e in self.enonces}
        parties = []
        for p in self.parties:
            ids = [i for i in p["enonces"] if i in vis]
            if not ids:
                continue
            parties.append({"id": p["id"], "titre": p["titre"].get(langue) or p["titre"].get("fr"),
                            "facultatif": p["facultatif"],
                            "enonces": [par_id[i].public(langue, essai) for i in ids]})
        feuillet = (self.feuillet or {}).get(langue) or (
            "[Feuillet d'information à insérer avant toute passation publique]" if essai else None)
        return {"instrument": self.id, "titre": self.titre.get(langue) or self.titre.get("fr"), "langue": langue,
                "feuillet": feuillet, "essai": essai,
                "admissibilite": [{"id": a["id"], "texte": a.get(langue) or a.get("fr"),
                                   "obligatoire": bool(a.get("obligatoire"))} for a in self.admissibilite],
                "presence": ({"id": self.presence["id"], "texte": self.presence.get(langue) or self.presence.get("fr")}
                             if self.presence else None),
                "parties": parties}

    # ── Validation ──────────────────────────────────────────
    def valider(self, reponses: dict[str, Any], condition: dict[str, str] | None) -> dict[str, Any]:
        """Renvoie les valeurs normalisées (énoncés visibles seulement) ou lève ReponseInvalide."""
        if not isinstance(reponses, dict):
            raise ReponseInvalide("Réponses attendues sous forme d'objet")
        connus = {e.id for e in self.enonces}
        inconnus = [k for k in reponses if k not in connus]
        if inconnus:
            raise ReponseInvalide(f"Énoncés inconnus : {', '.join(inconnus[:5])}")
        sortie: dict[str, Any] = {}
        for e in self.visibles(condition):
            v = reponses.get(e.id)
            if v in (None, ""):
                sortie[e.id] = None
                continue
            if e.type in ("echelle", "differentiel", "curseur"):
                if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v:
                    raise ReponseInvalide(f"{e.id} : entier attendu")
                if not (e.min <= int(v) <= e.max):
                    raise ReponseInvalide(f"{e.id} : valeur hors de l'échelle {e.min}–{e.max}")
                sortie[e.id] = int(v)
            elif e.type == "choix":
                if str(v) not in (e.valeurs or []):
                    raise ReponseInvalide(f"{e.id} : modalité inconnue")
                sortie[e.id] = str(v)
            else:
                t = " ".join(str(v).split())
                if len(t) > TEXTE_MAX:
                    raise ReponseInvalide(f"{e.id} : {TEXTE_MAX} caractères au plus")
                if t[:1] in ("=", "+", "-", "@"):      # pas de formule exécutée à l'ouverture dans un tableur
                    t = "'" + t
                sortie[e.id] = t
        return sortie


class Stockage:
    """Fichiers CSV par instrument et par représentation (jeu DO-03) ; essais rangés à part."""

    def __init__(self, dossier: str | Path):
        self.dossier = Path(dossier)
        self._verrou = threading.Lock()

    def fichier(self, ins: Instrument, id_representation: str, essai: bool) -> Path:
        d = self.dossier / ("essais" if essai else "")
        d.mkdir(parents=True, exist_ok=True)
        sur = "".join(c for c in id_representation if c.isalnum() or c in "-_") or "sans_id"
        return d / f"{ins.id}_{sur}.csv"

    def enregistrer(self, ins: Instrument, *, id_representation: str, condition: dict[str, str] | None,
                    langue: str, essai: bool, admissibilite: dict[str, bool], presence: bool | None,
                    reponses: dict[str, Any], pseudonyme: str | None = None) -> dict[str, Any]:
        for a in ins.admissibilite:
            if a.get("obligatoire") and not admissibilite.get(a["id"]):
                # Exclusion avant collecte : aucune donnée n'est conservée (A.2, critère « moins de 18 ans »).
                return {"enregistre": False, "motif": "admissibilite"}
        if not ins.anonyme and not (pseudonyme and pseudonyme.strip()):
            raise ReponseInvalide("Pseudonyme requis pour cet instrument")
        valeurs = ins.valider(reponses, condition)
        ligne = {"id_reponse": "R" + secrets.token_hex(5), "instrument": ins.id,
                 "id_representation": id_representation, "cond_support": (condition or {}).get("cond_support", ""),
                 "cond_provenance": (condition or {}).get("cond_provenance", ""), "date": date.today().isoformat(),
                 "langue": langue, "mode": "essai" if essai else "public"}
        if not ins.anonyme:
            ligne["pseudonyme"] = pseudonyme.strip()
        for c in ins.colonnes[len(ligne):]:
            if ins.presence and c == ins.presence["id"]:
                ligne[c] = "" if presence is None else int(bool(presence))
            else:
                v = valeurs.get(c)
                ligne[c] = "NA" if v is None else v
        f = self.fichier(ins, id_representation, essai)
        with self._verrou:
            neuf = not f.exists()
            with f.open("a", newline="", encoding="utf-8") as o:
                w = csv.DictWriter(o, fieldnames=ins.colonnes, delimiter=";")
                if neuf:
                    w.writeheader()
                w.writerow(ligne)
        return {"enregistre": True, "id_reponse": ligne["id_reponse"]}

    def compter(self, ins: Instrument, id_representation: str, essai: bool = False) -> int:
        f = self.fichier(ins, id_representation, essai)
        if not f.exists():
            return 0
        with f.open(encoding="utf-8") as o:
            return max(0, sum(1 for _ in o) - 1)
