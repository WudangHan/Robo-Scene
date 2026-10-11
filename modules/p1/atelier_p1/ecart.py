"""Écart de transformation (journal I-5, opération 4).

Distance d'édition de Levenshtein (insertions, suppressions, substitutions de caractères), normalisée par la
longueur de la plus longue des deux chaînes : 0 = proposition conservée telle quelle, 1 = entièrement réécrite.
Les espaces multiples sont réduits et la casse est conservée (une majuscule changée est une transformation).
"""
from __future__ import annotations

import re

LIMITE = 20_000  # caractères ; au-delà, calcul sur les mots pour borner le temps de calcul


def _normaliser(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def levenshtein(a, b) -> int:
    """Distance de Levenshtein entre deux séquences (chaînes ou listes), en O(len(a)·len(b)) et mémoire linéaire."""
    if len(a) < len(b):
        a, b = b, a
    precedente = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        courante = [i]
        for j, cb in enumerate(b, 1):
            courante.append(min(precedente[j] + 1, courante[j - 1] + 1, precedente[j - 1] + (ca != cb)))
        precedente = courante
    return precedente[-1]


def ecart_transformation(proposition: str, version: str) -> float:
    a, b = _normaliser(proposition), _normaliser(version)
    if not a and not b:
        return 0.0
    if max(len(a), len(b)) > LIMITE:
        a, b = a.split(" "), b.split(" ")
    return round(levenshtein(a, b) / max(len(a), len(b)), 4)


def etiquette_suggeree(ecart: float | None, seuil_mixte: float = 0.0) -> str:
    """Suggestion d'étiquette, toujours soumise à la confirmation de l'artiste (EF-05).

    Sans proposition : « humaine » ; proposition inchangée : « systeme » ; sinon « mixte ».
    (Inférence) Le passage de « mixte » à « humaine » pour une réécriture quasi complète relève du jugement
    de l'artiste et de l'entente de création, non d'un seuil calculé.
    """
    if ecart is None:
        return "humaine"
    return "systeme" if ecart <= seuil_mixte else "mixte"
