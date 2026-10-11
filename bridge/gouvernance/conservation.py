"""Conservation et destruction des données (G-07 ; plan de gestion des données G.6, § 8).

Le plan G.6 v1.0 ne fixe pas de durées chiffrées : la plateforme ne détruit que ce dont l'échéance a été
arrêtée par le chercheur (gouvernance/conservation.yaml), signale les échéances « à fixer », et consigne toute
destruction (date, jeu de données, fichiers, méthode) dans donnees/gouvernance/destructions.jsonl.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


def _ecraser_et_supprimer(p: Path) -> None:
    """Écrasement simple puis suppression. (Inférence) Sur un disque SSD, l'écrasement ne garantit pas
    l'effacement physique : la protection effective repose sur le chiffrement du volume (G.6, § 4)."""
    try:
        n = p.stat().st_size
        with open(p, "r+b") as f:
            f.write(os.urandom(min(n, 1 << 20)))
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass
    p.unlink(missing_ok=True)


def etat(racine: str | Path, regles: str | Path, aujourd_hui: date | None = None) -> list[dict[str, Any]]:
    racine, aujourd_hui = Path(racine), aujourd_hui or date.today()
    jeux = (yaml.safe_load(Path(regles).read_text(encoding="utf-8")) or {}).get("jeux", {})
    out = []
    for code, j in jeux.items():
        ech = str(j.get("echeance") or "")
        fichiers = [p for motif in j.get("chemins", []) for p in racine.glob(motif) if p.is_file()]
        if not ech:
            statut = "à fixer"
        elif ech.startswith("après:"):
            statut = f"sur événement ({ech[6:]})"
        else:
            statut = "échue" if date.fromisoformat(ech) <= aujourd_hui else "en cours"
        out.append({"code": code, "libelle": j.get("libelle"), "sensibilite": j.get("sensibilite"),
                    "echeance": ech or None, "statut": statut, "fichiers": len(fichiers)})
    return out


def purger(racine: str | Path, regles: str | Path, journal: str | Path, *, executer: bool = False,
           aujourd_hui: date | None = None, par: str = "plateforme") -> list[dict[str, Any]]:
    """Détruit les fichiers des jeux dont l'échéance datée est passée. Sans `executer`, simple inventaire."""
    racine, aujourd_hui = Path(racine), aujourd_hui or date.today()
    jeux = (yaml.safe_load(Path(regles).read_text(encoding="utf-8")) or {}).get("jeux", {})
    rapport = []
    for code, j in jeux.items():
        ech = str(j.get("echeance") or "")
        if not ech or ech.startswith("après:") or date.fromisoformat(ech) > aujourd_hui:
            continue
        fichiers = sorted({p for motif in j.get("chemins", []) for p in racine.glob(motif) if p.is_file()})
        if executer:
            for p in fichiers:
                _ecraser_et_supprimer(p)
            if fichiers:
                Path(journal).parent.mkdir(parents=True, exist_ok=True)
                with open(journal, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"date": datetime.now().astimezone().isoformat(timespec="seconds"),
                                        "jeu": code, "echeance": ech, "fichiers": [str(p.relative_to(racine)) for p in fichiers],
                                        "methode": "écrasement aléatoire puis suppression", "par": par},
                                       ensure_ascii=False) + "\n")
        rapport.append({"jeu": code, "echeance": ech, "fichiers": len(fichiers), "detruits": executer})
    return rapport
