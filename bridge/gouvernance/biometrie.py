"""Garde-fou biométrique (G-06).

Fondement : articles 44 et 45 de la Loi concernant le cadre juridique des technologies de l'information
(Québec) et guide de la Commission d'accès à l'information « Biométrie : principes à respecter et obligations
légales des organisations » (version 2.0, 21 septembre 2022) — un procédé qui vérifie ou confirme une identité par
des caractéristiques biométriques doit être déclaré à la Commission et exige le consentement exprès ; la création
d'une banque de telles caractéristiques doit lui être déclarée au moins 60 jours avant sa mise en service.

La plateforme s'interdit donc toute identification : l'estimation de pose ne produit que des grandeurs
cinématiques agrégées (vitesses, amplitudes, symétries), calculées dans le navigateur ; aucune image, aucune
suite de points du squelette, aucun gabarit n'est conservé.
"""
from __future__ import annotations

from typing import Any

CLES_INTERDITES = {"image", "images", "frame", "frames", "video", "landmarks", "points", "squelette",
                   "keypoints", "visage", "face", "embedding", "gabarit", "template"}
CONFIG_INTERDITE = ("conserver_video", "conserver_images", "conserver_points", "reconnaissance_faciale")


class ViolationBiometrique(ValueError):
    pass


def verifier_config(cfg: dict[str, Any]) -> None:
    for k in CONFIG_INTERDITE:
        if cfg.get(k):
            raise ViolationBiometrique(f"Option « {k} » interdite (G-06 : aucune donnée biométrique conservée)")


def nettoyer(descripteurs: dict[str, Any]) -> dict[str, Any]:
    """Refuse toute structure qui ressemblerait à des données brutes ou identifiantes ; ne garde que des scalaires."""
    propre = {}
    for k, v in descripteurs.items():
        if k.lower() in CLES_INTERDITES and not (isinstance(v, int) and not isinstance(v, bool)):
            # Un simple compte (ex. nombre d'images analysées) est permis ; un contenu ne l'est pas
            raise ViolationBiometrique(f"Champ « {k} » refusé : données brutes de pose ou d'image (G-06)")
        if isinstance(v, (int, float, str, bool)) or v is None:
            propre[k] = v
        elif isinstance(v, dict):
            propre[k] = nettoyer(v)
        elif isinstance(v, list) and len(v) <= 12 and all(isinstance(x, (int, float, str)) for x in v):
            propre[k] = v          # petits vecteurs agrégés ou noms d'articulations suivies
        else:
            raise ViolationBiometrique(f"Champ « {k} » refusé : séquence brute (G-06)")
    return propre
