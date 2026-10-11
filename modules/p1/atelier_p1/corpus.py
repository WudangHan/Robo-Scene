"""Corpus sous licence (P1.2) : chargement et contrôle d'admission.

Le fichier `corpus.yaml` reprend les colonnes de l'onglet « Corpus » du registre P1-2 ; chaque extrait admis
est un fichier texte du même dossier. Les règles d'admission sont celles de la politique P1.2, section 3 :
catégories A, B, C admises ; E admise sur consentement, toujours « local seulement » ; D et F refusées.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ADMISES = {"A", "B", "C", "E"}


class ErreurCorpus(Exception):
    pass


@dataclass(frozen=True)
class Extrait:
    code: str
    titre: str
    auteur: str
    categorie: str
    licence: str
    source: str
    local_seulement: bool
    texte: str
    passage: str = ""

    def mention(self) -> str:
        return f"{self.auteur}, {self.titre}" + (f" ({self.passage})" if self.passage else "") + f" — {self.licence}"

    def public(self) -> dict:
        return {"code": self.code, "titre": self.titre, "auteur": self.auteur, "categorie": self.categorie,
                "licence": self.licence, "local_seulement": self.local_seulement, "passage": self.passage,
                "longueur": len(self.texte)}


def charger_corpus(dossier: str | Path) -> dict[str, Extrait]:
    dossier = Path(dossier)
    index = dossier / "corpus.yaml"
    if not index.exists():
        return {}
    donnees = yaml.safe_load(index.read_text(encoding="utf-8")) or {}
    corpus: dict[str, Extrait] = {}
    for e in donnees.get("extraits", []):
        code, cat = str(e["code"]), str(e["categorie"]).upper()
        if not e.get("admis", False):
            continue  # ligne consignée au registre mais refusée : jamais chargée
        if cat not in ADMISES:
            raise ErreurCorpus(f"{code} : catégorie {cat} non admissible (politique P1.2, section 3)")
        local = bool(e.get("local_seulement", False)) or cat == "E"   # E toujours local (D03, ENF-01)
        fichier = dossier / e["fichier"]
        if not fichier.exists():
            raise ErreurCorpus(f"{code} : fichier d'extrait introuvable ({fichier.name})")
        corpus[code] = Extrait(code=code, titre=e["titre"], auteur=e["auteur"], categorie=cat,
                               licence=e.get("licence", ""), source=e.get("source", ""), local_seulement=local,
                               texte=fichier.read_text(encoding="utf-8").strip(), passage=e.get("passage", ""))
    return corpus
