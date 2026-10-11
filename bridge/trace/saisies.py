"""Saisies de régie : transformation « de tête » (N-07) et catégorie ouverte « autre » (N-08).

Limites du cadre R.4 (§9) que ces deux fonctions visent à réduire :
1. le modèle des cinq opérations peut ne pas épuiser les gestes de cocréation : une catégorie « autre »
   reste ouverte et elle est revue après chaque atelier, avec la révision des hypothèses (P1.4) ;
2. une transformation opérée de tête, pendant une répétition, échappe au journal : la régie la saisit après
   coup, en moins de trente secondes, et la trace est marquée « reconstituée ».
"""
from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .journal import JournalCocreation, horodatage


def transformation_de_tete(j: JournalCocreation, *, pseudonyme: str, description: str,
                           cycle: str | None = None, generation: int | None = None, proposition: int | None = None,
                           version: str | None = None, module: str = "SCENE",
                           debut_saisie: float | None = None) -> dict[str, Any]:
    description = (description or "").strip()
    if not description:
        raise ValueError("Décrire la transformation en quelques mots.")
    d: dict[str, Any] = {"description": description[:500], "version": version,
                         "generation": generation, "proposition": proposition}
    if debut_saisie is not None:
        d["delai_saisie_s"] = round(max(0.0, time.time() - debut_saisie), 1)
    return j.emettre(module, "transformation", ("personne", pseudonyme), d, cycle=cycle, reconstitue=True)


def autre(j: JournalCocreation, *, pseudonyme: str, categorie: str, description: str, module: str = "SCENE",
          cycle: str | None = None) -> dict[str, Any]:
    return j.emettre(module, "autre", ("personne", pseudonyme), {"description": (description or "")[:1000]},
                     cycle=cycle, categorie_autre=categorie.strip()[:60])


def revue_autres(evenements: list[dict[str, Any]]) -> dict[str, Any]:
    """Synthèse des événements « autre » à revoir après l'atelier (N-08)."""
    autres = [e for e in evenements if e["operation"] == "autre"]
    return {"total": len(autres), "par_categorie": dict(Counter(e["categorie_autre"] for e in autres)),
            "evenements": [{"id": e["id"], "categorie": e["categorie_autre"],
                            "description": e["donnees"].get("description", "")} for e in autres],
            "reconstituees": sum(1 for e in evenements if e.get("reconstitue"))}


def consigner_revue(dossier: str | Path, seance: str, decisions: list[dict[str, str]], auteur: str) -> Path:
    """Enregistre les décisions de revue (fusion dans une opération existante, nouvelle catégorie, rejet).

    Chaque décision : {"categorie": ..., "decision": "fusion:selection" | "nouvelle_categorie" | "ecartee",
    "justification": ...}. Le fichier daté rejoint la révision des hypothèses (repère P1.4)."""
    for d in decisions:
        if not d.get("justification"):
            raise ValueError("Chaque décision de revue doit être justifiée.")
    p = Path(dossier) / "revues"
    p.mkdir(parents=True, exist_ok=True)
    f = p / f"{datetime.now():%Y-%m-%d}_revue_categories_{seance}.json"
    f.write_text(json.dumps({"seance": seance, "date": horodatage(), "auteur": auteur, "decisions": decisions},
                            ensure_ascii=False, indent=2), encoding="utf-8")
    return f
