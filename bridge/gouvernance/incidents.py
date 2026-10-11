"""Fiches d'incident (R-08 ; politique G.5 : traitement sous 48 heures ; registre G6 des incidents).

Tout arrêt d'urgence — bouton de l'interface, bouton physique signalé par le robot, perte de lien pendant un
mouvement — ouvre une fiche. La qualification (gravité, cause, mesures) relève d'une personne ; la fiche reste
« ouverte » tant qu'elle n'est pas close avec ces informations.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

GRAVITES = ("mineur", "modere", "grave")


class Incidents:
    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)
        self.dossier.mkdir(parents=True, exist_ok=True)

    def _chemin(self, iid: str) -> Path:
        return self.dossier / f"{iid}.json"

    def creer(self, *, motif: str, robot: str | None, seance: str | None, origine: str,
              contexte: dict[str, Any] | None = None) -> dict[str, Any]:
        now = datetime.now().astimezone()
        n = 1 + len(list(self.dossier.glob(f"INC-{now:%Y%m%d}-*.json")))
        iid = f"INC-{now:%Y%m%d}-{n:03d}"
        fiche = {"id": iid, "ouverture": now.isoformat(timespec="seconds"),
                 "echeance_traitement": (now + timedelta(hours=48)).isoformat(timespec="seconds"),
                 "motif": motif, "origine": origine, "robot": robot, "seance": seance,
                 "contexte": contexte or {}, "statut": "ouvert", "gravite": None, "cause": None,
                 "mesures": None, "personnes_blessees": None, "cloture": None, "cloture_par": None}
        self._chemin(iid).write_text(json.dumps(fiche, ensure_ascii=False, indent=2), encoding="utf-8")
        return fiche

    def lister(self) -> list[dict[str, Any]]:
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(self.dossier.glob("INC-*.json"))]

    def ouverts(self) -> list[dict[str, Any]]:
        return [f for f in self.lister() if f["statut"] == "ouvert"]

    def clore(self, iid: str, *, gravite: str, cause: str, mesures: str, par: str,
              personnes_blessees: bool = False) -> dict[str, Any]:
        if gravite not in GRAVITES:
            raise ValueError(f"Gravité : {', '.join(GRAVITES)}")
        if not (cause.strip() and mesures.strip() and par.strip()):
            raise ValueError("Cause, mesures et personne qui clôt sont requises")
        p = self._chemin(iid)
        f = json.loads(p.read_text(encoding="utf-8"))
        f.update({"statut": "clos", "gravite": gravite, "cause": cause[:1000], "mesures": mesures[:1000],
                  "personnes_blessees": bool(personnes_blessees), "cloture_par": par[:60],
                  "cloture": datetime.now().astimezone().isoformat(timespec="seconds")})
        p.write_text(json.dumps(f, ensure_ascii=False, indent=2), encoding="utf-8")
        return f
