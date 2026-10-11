"""Mesures de l'opération 4 (N-04) : écart de transformation et taux de conservation.

* L'écart reprend exactement la définition du journal I-5 (prototype P1, atelier_p1.ecart) : distance de
  Levenshtein normalisée par la longueur de la plus longue chaîne, de 0 (inchangée) à 1 (entièrement réécrite).
* (Inférence) Le taux de conservation complète l'écart par une mesure orientée : la part des mots de la
  proposition qui subsistent, dans le même ordre, dans la version transformée (plus longue sous-suite commune
  de mots). Deux versions très différentes en longueur peuvent avoir un écart élevé et une conservation
  élevée (une proposition gardée intacte puis prolongée) : c'est précisément l'ambiguïté que l'écart seul
  ne permet pas de lever.
"""
from __future__ import annotations

import re

from .. import _modules  # noqa: F401  (rend atelier_p1 importable)
from atelier_p1.ecart import ecart_transformation  # source unique de la définition I-5

__all__ = ["ecart_transformation", "taux_conservation", "mesurer"]


def _mots(s: str) -> list[str]:
    return re.findall(r"[\wÀ-ÿœæ'’-]+", (s or "").casefold())


def _plsc(a: list[str], b: list[str]) -> int:
    """Longueur de la plus longue sous-suite commune (programmation dynamique, mémoire linéaire)."""
    if not a or not b:
        return 0
    prec = [0] * (len(b) + 1)
    for x in a:
        cour = [0]
        for j, y in enumerate(b, 1):
            cour.append(prec[j - 1] + 1 if x == y else max(prec[j], cour[j - 1]))
        prec = cour
    return prec[-1]


def taux_conservation(proposition: str, version: str) -> float:
    a, b = _mots(proposition), _mots(version)
    if not a:
        return 1.0 if not b else 0.0
    return round(_plsc(a, b) / len(a), 4)


def mesurer(proposition: str, version: str) -> dict[str, float]:
    return {"ecart": ecart_transformation(proposition, version),
            "conservation": taux_conservation(proposition, version)}
