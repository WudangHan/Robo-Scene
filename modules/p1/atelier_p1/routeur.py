"""Routeur de sensibilité (décision D03 ; fiche d'impact P1.1, ENF-01 et EF-07).

Chaque consigne est acheminée vers le modèle distant (SI-01) seulement si AUCUN motif de sensibilité n'est
relevé ; au moindre doute, elle va au modèle local (SI-02). Si le modèle local est indisponible, la génération
est refusée : le routeur ne se rabat jamais sur le modèle distant.

La liste de blocage (noms de personnes participantes) est un fichier tenu HORS du dossier du projet, dans le
volume chiffré prévu par le plan de gestion des données (G.6) ; elle n'est jamais journalisée.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

RE_COURRIEL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
RE_TELEPHONE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")


def _plier(s: str) -> str:
    """Minuscules, sans accents ni ponctuation : « Éloïse » et « eloise » se confondent."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").casefold()
    return re.sub(r"[^\w]+", " ", s).strip()


def charger_liste_blocage(chemin: str | Path | None) -> list[str]:
    if not chemin:
        return []
    lignes = Path(chemin).read_text(encoding="utf-8").splitlines()
    return [_plier(l) for l in lignes if l.strip() and not l.lstrip().startswith("#")]


@dataclass
class Decision:
    cible: str                      # "distant" ou "local"
    motifs: list[str] = field(default_factory=list)

    @property
    def sensible(self) -> bool:
        return self.cible == "local"


class Routeur:
    def __init__(self, liste_blocage: list[str] | None = None, hors_ligne: bool = False):
        self.noms = [n for n in (liste_blocage or []) if n]
        self.hors_ligne = hors_ligne

    def decider(self, texte: str, extraits=(), confidentielle: bool = False) -> Decision:
        motifs = []
        if self.hors_ligne:
            motifs.append("mode hors ligne actif (EF-07)")
        if confidentielle:
            motifs.append("consigne marquée confidentielle par l'artiste")
        plie = f" {_plier(texte)} "
        if any(f" {n} " in plie for n in self.noms):
            motifs.append("nom figurant sur la liste de blocage locale (ENF-01)")  # le nom n'est pas répété
        if RE_COURRIEL.search(texte or ""):
            motifs.append("adresse de courriel détectée")
        if RE_TELEPHONE.search(texte or ""):
            motifs.append("numéro de téléphone détecté")
        for e in extraits:
            if e.local_seulement:
                motifs.append(f"extrait {e.code} réservé au modèle local (catégorie {e.categorie})")
        return Decision("local" if motifs else "distant", motifs)
