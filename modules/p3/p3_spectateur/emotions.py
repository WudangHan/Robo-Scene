"""Les huit émotions de la grille, disposées selon le cercle de Russell (1980).

Coordonnées (agrément v, intensité a) reprises de la spécification P3.1, section 3.
Les libellés sont des adaptations au contexte théâtral, à valider (rétrotraduction T.1, tests P3.3).
"""
from __future__ import annotations

EMOTIONS: list[dict] = [
    {"k": "ravi", "fr": "Ravi·e", "en": "Delighted", "v": 1.0, "a": 0.0},
    {"k": "enth", "fr": "Enthousiaste", "en": "Excited", "v": 0.7, "a": 0.7},
    {"k": "saisi", "fr": "Saisi·e", "en": "Struck", "v": 0.0, "a": 1.0},
    {"k": "inq", "fr": "Inquiet·ète", "en": "Uneasy", "v": -0.7, "a": 0.7},
    {"k": "contr", "fr": "Contrarié·e", "en": "Displeased", "v": -1.0, "a": 0.0},
    {"k": "abat", "fr": "Abattu·e", "en": "Downcast", "v": -0.7, "a": -0.7},
    {"k": "engo", "fr": "Engourdi·e", "en": "Drowsy", "v": 0.0, "a": -1.0},
    {"k": "apai", "fr": "Apaisé·e", "en": "Calm", "v": 0.7, "a": -0.7},
]
CLES = tuple(e["k"] for e in EMOTIONS)


def plus_proche(v: float, a: float) -> str:
    """Clé de l'émotion la plus proche (distance euclidienne) d'un point (v, a) de [-1, 1]²."""
    return min(EMOTIONS, key=lambda e: (e["v"] - v) ** 2 + (e["a"] - a) ** 2)["k"]


def curseur_vers_unite(x: int) -> float:
    """Échelle de neuf points (1–9, inspirée du SAM) → [-1, 1]."""
    return (x - 5) / 4
