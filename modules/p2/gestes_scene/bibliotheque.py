"""Bibliothèque fermée de gestes : chargement, interpolation et validation.

Repère P2.2 du projet « L'IA au service de la création théâtrale » (S. Gagné, Ph. D.).
Ce module ne dépend PAS du SDK Reachy Mini : il peut être testé sans robot.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

STATUTS = ("brouillon", "valide_sim", "valide_robot_lent", "valide")

# Limites du SDK (documentation « Core Concepts » de Reachy Mini, consultée le 5 oct. 2026)
LIMITES_SDK = {
    "pitch": 40.0,      # degrés, |tangage| maximal de la tête
    "roll": 40.0,       # degrés, |roulis| maximal de la tête
    "yaw": 180.0,       # degrés, |lacet| maximal de la tête
    "body_yaw": 160.0,  # degrés, |rotation| maximale du corps
    "ecart_yaw": 65.0,  # degrés, écart maximal entre lacet de la tête et du corps
}

# Limites PROPRES AU PROJET (inférence prudente, à recalibrer après essais — P2.1, §6.5)
LIMITES_PROJET = {
    "translation_mm": 20.0,          # |x|, |y| maximal de la tête
    "z_min_mm": -20.0, "z_max_mm": 25.0,
    "antenne_deg": 90.0,             # |angle| maximal d'une antenne
    "vitesse_angulaire_deg_s": 120.0,  # tête et corps, à pleine vitesse
    "vitesse_antenne_deg_s": 360.0,
    "vitesse_lineaire_mm_s": 80.0,
    "duree_min_s": 0.25,             # durée minimale d'un segment
}

COMPOSANTES_TETE = ("x", "y", "z", "roll", "pitch", "yaw")


@dataclass
class ImageCle:
    """Une image clé : pose complète à atteindre en `duree` secondes."""
    duree: float
    tete: dict[str, float]
    antennes: tuple[float, float]
    body_yaw: float


@dataclass
class Geste:
    nom: str
    description: dict[str, str]
    intention: str
    laban: dict[str, str]
    statut: str
    images_cles: list[ImageCle] = field(default_factory=list)

    @property
    def duree_totale(self) -> float:
        return sum(k.duree for k in self.images_cles)


def _normaliser(nom: str, brut: dict[str, Any]) -> Geste:
    """Résout l'héritage des champs : `tete` absente = tête précédente conservée ;
    `tete: {}` = pose neutre ; composantes non précisées d'une tête donnée = 0 ;
    `antennes` ou `body_yaw` absents = valeur précédente conservée."""
    tete = {c: 0.0 for c in COMPOSANTES_TETE}
    antennes = (0.0, 0.0)
    body_yaw = 0.0
    images: list[ImageCle] = []
    for i, k in enumerate(brut.get("images_cles", [])):
        if "duree" not in k:
            raise ValueError(f"{nom} : image clé {i + 1} sans durée")
        if "tete" in k:
            inconnues = set(k["tete"]) - set(COMPOSANTES_TETE)
            if inconnues:
                raise ValueError(f"{nom} : composantes inconnues {sorted(inconnues)}")
            tete = {c: float(k["tete"].get(c, 0.0)) for c in COMPOSANTES_TETE}
        if "antennes" in k:
            a = k["antennes"]
            if len(a) != 2:
                raise ValueError(f"{nom} : il faut deux angles d'antennes [droite, gauche]")
            antennes = (float(a[0]), float(a[1]))
        if "body_yaw" in k:
            body_yaw = float(k["body_yaw"])
        images.append(ImageCle(float(k["duree"]), dict(tete), antennes, body_yaw))
    statut = brut.get("statut", "brouillon")
    if statut not in STATUTS:
        raise ValueError(f"{nom} : statut inconnu « {statut} »")
    return Geste(nom, brut.get("description", {}), brut.get("intention", ""),
                 brut.get("laban", {}), statut, images)


def charger(chemin: str | Path | None = None) -> dict[str, Geste]:
    """Charge la bibliothèque YAML ; par défaut, celle qui accompagne ce module."""
    chemin = Path(chemin) if chemin else Path(__file__).with_name("bibliotheque_gestes.yaml")
    with open(chemin, encoding="utf-8") as f:
        donnees = yaml.safe_load(f)
    return {nom: _normaliser(nom, brut) for nom, brut in donnees["gestes"].items()}


POSE_NEUTRE = ImageCle(0.0, {c: 0.0 for c in COMPOSANTES_TETE}, (0.0, 0.0), 0.0)


def valider(geste: Geste, depart: ImageCle = POSE_NEUTRE) -> list[str]:
    """Retourne la liste des violations (vide si le geste respecte toutes les limites).

    Les vitesses sont des vitesses moyennes par segment ; l'interpolation à jerk minimal
    du SDK atteint un pic d'environ 1,875 fois la moyenne, d'où le facteur appliqué."""
    pb: list[str] = []
    if not geste.images_cles:
        return [f"{geste.nom} : aucune image clé"]
    pic = 1.875  # rapport pic/moyenne d'un profil à jerk minimal
    prec = depart
    for i, k in enumerate(geste.images_cles, start=1):
        t = k.tete
        lieu = f"{geste.nom}, image {i}"
        for axe in ("pitch", "roll", "yaw"):
            if abs(t[axe]) > LIMITES_SDK[axe]:
                pb.append(f"{lieu} : {axe} {t[axe]}° hors limite SDK ±{LIMITES_SDK[axe]}°")
        if abs(k.body_yaw) > LIMITES_SDK["body_yaw"]:
            pb.append(f"{lieu} : body_yaw {k.body_yaw}° hors limite SDK")
        if abs(t["yaw"] - k.body_yaw) > LIMITES_SDK["ecart_yaw"]:
            pb.append(f"{lieu} : écart tête/corps {abs(t['yaw'] - k.body_yaw)}° > {LIMITES_SDK['ecart_yaw']}°")
        for axe in ("x", "y"):
            if abs(t[axe]) > LIMITES_PROJET["translation_mm"]:
                pb.append(f"{lieu} : {axe} {t[axe]} mm hors limite projet")
        if not LIMITES_PROJET["z_min_mm"] <= t["z"] <= LIMITES_PROJET["z_max_mm"]:
            pb.append(f"{lieu} : z {t['z']} mm hors limite projet")
        for j, a in enumerate(k.antennes):
            if abs(a) > LIMITES_PROJET["antenne_deg"]:
                pb.append(f"{lieu} : antenne {('droite', 'gauche')[j]} {a}° hors limite projet")
        if k.duree < LIMITES_PROJET["duree_min_s"]:
            pb.append(f"{lieu} : durée {k.duree} s < {LIMITES_PROJET['duree_min_s']} s")
            prec = k
            continue
        # vitesses de pointe estimées sur le segment
        dang = max(abs(t[a] - prec.tete[a]) for a in ("roll", "pitch", "yaw"))
        dang = max(dang, abs(k.body_yaw - prec.body_yaw))
        dlin = math.dist([t["x"], t["y"], t["z"]], [prec.tete["x"], prec.tete["y"], prec.tete["z"]])
        dant = max(abs(k.antennes[j] - prec.antennes[j]) for j in (0, 1))
        if pic * dang / k.duree > LIMITES_PROJET["vitesse_angulaire_deg_s"]:
            pb.append(f"{lieu} : vitesse angulaire de pointe ≈ {pic * dang / k.duree:.0f}°/s > "
                      f"{LIMITES_PROJET['vitesse_angulaire_deg_s']}°/s")
        if pic * dlin / k.duree > LIMITES_PROJET["vitesse_lineaire_mm_s"]:
            pb.append(f"{lieu} : vitesse linéaire de pointe ≈ {pic * dlin / k.duree:.0f} mm/s trop élevée")
        if pic * dant / k.duree > LIMITES_PROJET["vitesse_antenne_deg_s"]:
            pb.append(f"{lieu} : vitesse d'antenne de pointe ≈ {pic * dant / k.duree:.0f}°/s trop élevée")
        prec = k
    return pb


def min_jerk(s: float) -> float:
    """Profil à jerk minimal normalisé, s ∈ [0, 1]."""
    s = min(max(s, 0.0), 1.0)
    return 10 * s ** 3 - 15 * s ** 4 + 6 * s ** 5


def echantillonner(geste: Geste, frequence: float = 50.0, facteur_vitesse: float = 1.0,
                   depart: ImageCle = POSE_NEUTRE):
    """Génère (t, tete, antennes, body_yaw) à `frequence` Hz, durées divisées par le facteur."""
    t0, prec = 0.0, depart
    dt = 1.0 / frequence
    for k in geste.images_cles:
        d = k.duree / facteur_vitesse
        n = max(1, int(round(d * frequence)))
        for i in range(1, n + 1):
            s = min_jerk(i / n)
            tete = {c: prec.tete[c] + s * (k.tete[c] - prec.tete[c]) for c in COMPOSANTES_TETE}
            ant = tuple(prec.antennes[j] + s * (k.antennes[j] - prec.antennes[j]) for j in (0, 1))
            by = prec.body_yaw + s * (k.body_yaw - prec.body_yaw)
            yield t0 + i * dt, tete, ant, by
        t0 += n * dt
        prec = k
