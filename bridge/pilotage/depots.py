"""Tableau de l'emplacement exact de chaque fichier déposé (P-03 : règle de pilotage du chercheur).

Chaque fois que la plateforme écrit un livrable (export, rapport, analyse), elle ajoute au tableau du jour
une ligne : fichier, emplacement exact, taille, empreinte, objet. Le tableau Markdown se lit tel quel et se
recopie dans les comptes rendus.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path


def _empreinte(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:12]


def consigner(dossier_donnees: str | Path, fichiers: list[str | Path], objet: str) -> Path:
    d = Path(dossier_donnees) / "depots"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{datetime.now():%Y-%m-%d}_tableau_depots.md"
    neuf = not f.exists()
    with f.open("a", encoding="utf-8") as o:
        if neuf:
            o.write(f"# Fichiers déposés le {datetime.now():%Y-%m-%d}\n\n"
                    "| Heure | Fichier | Emplacement exact | Taille | Empreinte (SHA-256, 12) | Objet |\n"
                    "|---|---|---|---|---|---|\n")
        for p in map(Path, fichiers):
            if p.exists():
                o.write(f"| {datetime.now():%H:%M} | `{p.name}` | `{p.resolve().parent}` | {p.stat().st_size} o "
                        f"| {_empreinte(p)} | {objet} |\n")
    return f


def lister(dossier_donnees: str | Path) -> list[dict[str, str]]:
    d = Path(dossier_donnees) / "depots"
    return [{"date": p.name[:10], "chemin": str(p), "contenu": p.read_text(encoding="utf-8")}
            for p in sorted(d.glob("*_tableau_depots.md"), reverse=True)[:10]] if d.exists() else []
