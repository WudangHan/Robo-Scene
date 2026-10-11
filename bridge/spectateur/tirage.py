"""Tirage au sort scellé des conditions X.2 (plan d'analyse A.2, § 2.2 ; outil modules/x2/tirage_conditions.py).

Le tirage est fait une seule fois : le CSV, la graine et l'empreinte SHA-256 sont écrits dans
donnees/tirage/ ; un second tirage est refusé tant que le premier existe (le préenregistrement publie
l'empreinte AVANT la première représentation). La vérification rejoue la commande et compare l'empreinte.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import _modules  # noqa: F401
from tirage_conditions import en_csv, tirer


class TirageExistant(RuntimeError):
    pass


class Tirage:
    def __init__(self, dossier_donnees: str | Path):
        self.dossier = Path(dossier_donnees) / "tirage"

    @property
    def csv(self) -> Path:
        return self.dossier / "tirage_X2.csv"

    @property
    def meta(self) -> Path:
        return self.dossier / "tirage_X2.json"

    def existe(self) -> bool:
        return self.csv.exists() and self.meta.exists()

    def effectuer(self, representations: int, graine: int, sans_support: bool = False, par: str = "") -> dict[str, Any]:
        if self.existe():
            raise TirageExistant("Un tirage scellé existe déjà : le vérifier plutôt que le refaire")
        if not par.strip():
            raise ValueError("Indiquer qui effectue le tirage (initiales)")
        texte = en_csv(tirer(int(representations), int(graine), bool(sans_support)))
        empreinte = hashlib.sha256(texte.encode("utf-8")).hexdigest()
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.csv.write_text(texte, encoding="utf-8")
        m = {"representations": int(representations), "graine": int(graine), "sans_support": bool(sans_support),
             "sha256": empreinte, "date": datetime.now().astimezone().isoformat(timespec="seconds"), "par": par,
             "commande": (f"python modules/x2/tirage_conditions.py --representations {representations} "
                          f"--graine {graine}{' --sans-support' if sans_support else ''} --sortie tirage_X2.csv")}
        self.meta.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        return {**m, "lignes": self.lignes()}

    def lignes(self) -> list[dict[str, str]]:
        if not self.csv.exists():
            return []
        return list(csv.DictReader(io.StringIO(self.csv.read_text(encoding="utf-8")), delimiter=";"))

    def verifier(self) -> dict[str, Any]:
        if not self.existe():
            return {"existe": False}
        m = json.loads(self.meta.read_text(encoding="utf-8"))
        texte = self.csv.read_text(encoding="utf-8")
        rejoue = en_csv(tirer(m["representations"], m["graine"], m["sans_support"]))
        e_fichier = hashlib.sha256(texte.encode("utf-8")).hexdigest()
        return {"existe": True, **m, "empreinte_fichier": e_fichier,
                "fichier_intact": e_fichier == m["sha256"], "rejouable": rejoue == texte}

    def condition(self, id_representation: str) -> dict[str, str] | None:
        for l in self.lignes():
            if l["id_representation"] == id_representation:
                return {"cond_support": l["cond_support"], "cond_provenance": l["cond_provenance"]}
        return None
