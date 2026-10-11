"""Profils d'acteurs, consentements révocables, passages de répétition et suivi de formation.

Données rangées dans partenaire/donnees/, sur la machine de l'équipe uniquement.
Par défaut l'acteur est désigné par un pseudonyme. Sans consentement explicite,
aucune mesure n'est conservée ; le retrait efface l'ensemble de ses données.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .connaissances import RACINE
from .texte_outils import sans_accents

DOSSIER = RACINE / "partenaire" / "donnees"

CONSENTEMENTS = {
    "mesures_vocales": "Conserver les mesures vocales calculées localement (latences, durées, pauses, intensité).",
    "transcription": "Utiliser la reconnaissance vocale du navigateur pour comparer le texte dit au texte écrit "
                     "(selon le navigateur, l'audio peut être traité par un service distant).",
    "camera": "Utiliser la caméra pour une estimation de pose locale et conserver les descripteurs de mouvement "
              "(aucune image n'est enregistrée).",
    "recherche": "Verser ces traces, pseudonymisées, au corpus de recherche ROBO-SCÈNE.",
    # Consentements généralisés à toute la plateforme (cahier des fonctions, G-01)
    "atelier_p1": "Participer aux ateliers d'écriture (P1) : consignes, choix et réécritures consignés sous pseudonyme "
                  "dans le journal des cinq opérations (I-5).",
    "entretien": "Entretien enregistré (I-1), transcrit sur cette machine (SI-03) puis pseudonymisé ; l'audio est "
                 "détruit après vérification de la transcription.",
    "captation_video": "Captation vidéo des ateliers ou présentations (DO-07), conservée dans le volume chiffré.",
}


def _horodatage() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _id(s: str) -> str:
    v = re.sub(r"[^a-z0-9\-]", "", sans_accents(s.lower()).replace(" ", "-"))[:40]
    if not v:
        raise ValueError("Identifiant invalide")
    return v


class Stockage:
    def __init__(self, dossier: Path | None = None):
        self.dossier = dossier = dossier or DOSSIER
        (dossier / "acteurs").mkdir(parents=True, exist_ok=True)

    def _chemin(self, aid: str) -> Path:
        return self.dossier / "acteurs" / _id(aid)

    # ── Profils ─────────────────────────────────────────────
    def lister(self) -> list[dict[str, Any]]:
        out = []
        for d in sorted((self.dossier / "acteurs").iterdir()):
            f = d / "profil.json"
            if f.exists():
                p = json.loads(f.read_text(encoding="utf-8"))
                out.append({k: p[k] for k in ("id", "pseudonyme", "annee_formation", "consentements")})
        return out

    def profil(self, aid: str) -> dict[str, Any]:
        f = self._chemin(aid) / "profil.json"
        if not f.exists():
            raise KeyError(f"Acteur inconnu : {aid}")
        return json.loads(f.read_text(encoding="utf-8"))

    def creer(self, pseudonyme: str, annee_formation: int = 1) -> dict[str, Any]:
        aid = _id(pseudonyme)
        d = self._chemin(aid)
        if (d / "profil.json").exists():
            return self.profil(aid)
        d.mkdir(parents=True, exist_ok=True)
        p = {"id": aid, "pseudonyme": pseudonyme.strip()[:40], "annee_formation": int(annee_formation),
             "cree": _horodatage(), "consentements": {k: None for k in CONSENTEMENTS},
             "historique_consentements": [], "exercices": [], "auto_evaluations": []}
        self._ecrire(p)
        return p

    def _ecrire(self, p: dict[str, Any]) -> None:
        f = self._chemin(p["id"]) / "profil.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(f)

    def consentir(self, aid: str, cle: str, accorde: bool) -> dict[str, Any]:
        if cle not in CONSENTEMENTS:
            raise ValueError(f"Consentement inconnu : {cle}")
        p = self.profil(aid)
        p["consentements"][cle] = _horodatage() if accorde else None
        p["historique_consentements"].append({"ts": _horodatage(), "cle": cle, "accorde": bool(accorde)})
        self._ecrire(p)
        return p

    def a_consenti(self, aid: str | None, cle: str) -> bool:
        if not aid:
            return False
        try:
            return bool(self.profil(aid)["consentements"].get(cle))
        except KeyError:
            return False

    def retirer(self, aid: str) -> None:
        """Droit de retrait : efface le profil et toutes les traces de l'acteur."""
        shutil.rmtree(self._chemin(aid), ignore_errors=True)

    # ── Formation ───────────────────────────────────────────
    def noter_exercice(self, aid: str, exercice: str, note: str = "") -> dict[str, Any]:
        p = self.profil(aid)
        p["exercices"].append({"ts": _horodatage(), "exercice": exercice, "note": note[:1000]})
        self._ecrire(p)
        return p

    def auto_evaluer(self, aid: str, notes: dict[str, int], commentaire: str = "") -> dict[str, Any]:
        p = self.profil(aid)
        p["auto_evaluations"].append({"ts": _horodatage(),
                                      "notes": {k: max(1, min(5, int(v))) for k, v in notes.items()},
                                      "commentaire": commentaire[:1000]})
        self._ecrire(p)
        return p

    # ── Passages de répétition ──────────────────────────────
    def _fichier_passages(self, aid: str, piece: str, role: str) -> Path:
        return self._chemin(aid) / "passages" / f"{_id(piece)}__{_id(role)}.json"

    def ajouter_passage(self, aid: str, piece: str, role: str, passage: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.a_consenti(aid, "mesures_vocales"):
            raise PermissionError("Consentement « mesures vocales » absent : passage non conservé")
        f = self._fichier_passages(aid, piece, role)
        f.parent.mkdir(parents=True, exist_ok=True)
        passages = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
        passage = {**passage, "numero": len(passages) + 1, "ts": _horodatage()}
        passages.append(passage)
        f.write_text(json.dumps(passages, ensure_ascii=False, indent=1), encoding="utf-8")
        return passages

    def passages(self, aid: str, piece: str, role: str) -> list[dict[str, Any]]:
        f = self._fichier_passages(aid, piece, role)
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
