"""Journalisation de séance selon la nomenclature ROBO-SCÈNE.

Identifiant : [DATE]_[SYSTÈME]_[TYPE]_[NUMÉRO]
Arborescence : corpus/[Système]/[Type]/[Date]/
Pour chaque séance : un .jsonl (événements horodatés, télémétrie décimée)
et un .json (métadonnées de la séance, mis à jour à la clôture).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def _horodatage() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


class Seance:
    def __init__(self, racine: Path, systeme: str, type_: str, operatrice: str,
                 config: dict[str, Any], transport: str):
        self.date = datetime.now().strftime("%Y%m%d")
        sys_ = re.sub(r"[^A-Za-z0-9.-]", "", systeme) or "ROBOT"
        typ = re.sub(r"[^A-Za-z0-9.-]", "", type_) or "X"
        self.dossier = Path(racine) / sys_ / typ / self.date
        self.dossier.mkdir(parents=True, exist_ok=True)
        numero = 1 + max(
            (int(m.group(1)) for p in self.dossier.glob("*.json")
             if (m := re.search(r"_(\d{3})\.json$", p.name))),
            default=0,
        )
        self.id = f"{self.date}_{sys_}_{typ}_{numero:03d}"
        self.chemin_evt = self.dossier / f"{self.id}.jsonl"
        self.chemin_meta = self.dossier / f"{self.id}.json"
        self._f = open(self.chemin_evt, "a", encoding="utf-8")
        self.meta: dict[str, Any] = {
            "identifiant": self.id,
            "systeme": sys_,
            "type": typ,
            "transport": transport,
            "operatrice": operatrice,
            "debut": _horodatage(),
            "fin": None,
            "parametres": config,
            "compteurs": {
                "commandes": 0, "commandes_refusees": 0, "arrets_urgence": 0,
                "propositions_ia": 0, "ia_validees": 0, "ia_rejetees": 0,
                "ia_bloquees_seuil": 0, "sequences_jouees": 0,
            },
            "notes_observationnelles": [],
        }
        self._ecrire_meta()
        self.evenement("seance", action="ouverture", identifiant=self.id)

    def evenement(self, categorie: str, **donnees: Any) -> None:
        ligne = {"ts": _horodatage(), "cat": categorie, **donnees}
        self._f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        self._f.flush()

    def compter(self, cle: str, n: int = 1) -> None:
        self.meta["compteurs"][cle] = self.meta["compteurs"].get(cle, 0) + n

    def note(self, texte: str) -> None:
        self.meta["notes_observationnelles"].append({"ts": _horodatage(), "texte": texte})
        self.evenement("note", texte=texte)
        self._ecrire_meta()

    def _ecrire_meta(self) -> None:
        tmp = self.chemin_meta.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.chemin_meta)

    def sauvegarder(self) -> None:
        self._ecrire_meta()

    def cloturer(self) -> None:
        if self.meta["fin"] is None:
            self.meta["fin"] = _horodatage()
            self.evenement("seance", action="cloture")
            self._ecrire_meta()
            self._f.close()
