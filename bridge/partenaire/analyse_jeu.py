"""Analyse du jeu : précision textuelle, mesures vocales, descripteurs de mouvement, trajectoires.

Toutes les mesures sont des INDICES observables. Elles ne disent ni la
qualité artistique d'une interprétation ni l'intériorité de l'acteur ;
le programme ROBO-SCÈNE exige de ne pas confondre l'estimation d'une
intention à partir de signaux avec l'accès à l'intériorité de l'artiste.
"""
from __future__ import annotations

import math
import statistics as st
from difflib import SequenceMatcher
from typing import Any

from .texte_outils import mots, syllabes


# ─────────────────────────────────────────────────────────────
#  Fidélité au texte
# ─────────────────────────────────────────────────────────────
def precision_texte(reference: str, dit: str) -> dict[str, Any]:
    ref, hyp = mots(reference), mots(dit)
    if not ref:
        return {"precision": None, "omissions": [], "ajouts": [], "substitutions": []}
    sm = SequenceMatcher(a=ref, b=hyp, autojunk=False)
    om, aj, sub, justes = [], [], [], 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            justes += i2 - i1
        elif op == "delete":
            om.append(" ".join(ref[i1:i2]))
        elif op == "insert":
            aj.append(" ".join(hyp[j1:j2]))
        else:
            sub.append({"attendu": " ".join(ref[i1:i2]), "dit": " ".join(hyp[j1:j2])})
    return {"precision": round(justes / len(ref), 3), "mots_attendus": len(ref), "mots_justes": justes,
            "omissions": om, "ajouts": aj, "substitutions": sub}


# ─────────────────────────────────────────────────────────────
#  Mesures vocales (détection d'activité vocale locale, dans le navigateur)
# ─────────────────────────────────────────────────────────────
def mesure_replique(texte: str, m: dict[str, Any]) -> dict[str, Any]:
    """`m` : latence_ms, duree_ms, pauses_ms[], rms_db, rms_db_max, souffles, transcription?"""
    pauses = [p for p in (m.get("pauses_ms") or []) if p >= 250]
    duree = float(m.get("duree_ms") or 0)
    phonation = max(1.0, duree - sum(pauses))
    debit = round(syllabes(texte) / (phonation / 1000), 2) if duree > 300 else None
    if debit is not None and not 1.0 <= debit <= 12.0:
        debit = None  # hors des débits articulatoires plausibles : détection douteuse (bruit, coupure)
    out = {
        "latence_ms": m.get("latence_ms"),
        "chevauchement": (m.get("latence_ms") or 0) < 0,
        "duree_ms": int(duree) if duree else None,
        "pauses": len(pauses), "pause_totale_ms": int(sum(pauses)),
        "debit_syl_s": debit,
        "intensite_db": m.get("rms_db"), "dynamique_db": (round(m["rms_db_max"] - m["rms_db"], 1)
                                                          if m.get("rms_db_max") is not None and m.get("rms_db") is not None else None),
        "souffles": int(m.get("souffles") or 0),
        "mode_fin": m.get("mode_fin", "detection"),
    }
    if m.get("transcription"):
        out["texte"] = precision_texte(texte, m["transcription"])
    return out


def _med(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(st.median(xs), 1) if xs else None


def synthese_passage(mesures: list[dict[str, Any]]) -> dict[str, Any]:
    lat = [m["latence_ms"] for m in mesures if m.get("latence_ms") is not None]
    prec = [m["texte"]["precision"] for m in mesures if m.get("texte") and m["texte"]["precision"] is not None]
    return {
        "repliques": len(mesures),
        "latence_mediane_ms": _med(lat),
        "latence_dispersion_ms": round(st.pstdev(lat), 1) if len(lat) > 1 else None,
        "chevauchements": sum(1 for m in mesures if m.get("chevauchement")),
        "souffles": sum(m.get("souffles", 0) for m in mesures),
        "precision_moyenne": round(sum(prec) / len(prec), 3) if prec else None,
        "debit_median": _med([m.get("debit_syl_s") for m in mesures]),
        "pauses": sum(m.get("pauses", 0) for m in mesures),
    }


def tendance(valeurs: list[float | None]) -> dict[str, Any]:
    """Pente (moindres carrés) d'une série de passages ; None si moins de trois points."""
    pts = [(i, v) for i, v in enumerate(valeurs) if v is not None]
    if len(pts) < 3:
        return {"pente": None, "n": len(pts)}
    xs, ys = zip(*pts)
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    pente = sum((x - mx) * (y - my) for x, y in pts) / den if den else 0.0
    return {"pente": round(pente, 3), "n": len(pts)}


def trajectoire(passages: list[dict[str, Any]]) -> dict[str, Any]:
    """Évolution longitudinale des indices de coordination sur les passages successifs.

    Indices liés aux mécanismes du cadre relationnel ROBO-SCÈNE : la baisse de la
    dispersion des latences documente une STABILISATION de la coordination (HE1) ;
    une hausse ponctuelle suivie d'un retour documente une RÉORGANISATION. Ce ne
    sont pas des mesures de la relation elle-même, qui reste à interpréter."""
    s = [p["synthese"] for p in passages]
    lat = [x.get("latence_mediane_ms") for x in s]
    disp = [x.get("latence_dispersion_ms") for x in s]
    souf = [float(x.get("souffles", 0)) for x in s]
    prec = [x.get("precision_moyenne") for x in s]
    lecture = []
    td = tendance(disp)
    if td["pente"] is not None:
        lecture.append("Dispersion des latences en baisse : indice de stabilisation de la coordination."
                       if td["pente"] < 0 else
                       "Dispersion des latences stable ou en hausse : pas d'indice de stabilisation à ce stade.")
    ts = tendance(souf)
    if ts["pente"] is not None and ts["pente"] < 0:
        lecture.append("Recours au souffleur en baisse : la mémorisation progresse.")
    perturbes = [i for i, p in enumerate(passages) if p.get("perturbation")]
    for i in perturbes:
        if 0 < i < len(passages) - 1 and lat[i] and lat[i - 1] and lat[i + 1]:
            if lat[i] > lat[i - 1] and lat[i + 1] <= lat[i]:
                lecture.append(f"Passage {i + 1} (perturbation {passages[i]['perturbation']}) : hausse de latence "
                               f"puis retour — indice de réorganisation.")
    return {"passages": len(passages), "latence_mediane": lat, "dispersion": disp, "souffles": souf,
            "precision": prec, "tendances": {"latence": tendance(lat), "dispersion": td, "souffles": ts,
                                             "precision": tendance(prec)},
            "lecture": lecture,
            "avertissement": "Indices observables, à trianguler avec l'observation de plateau et les entretiens "
                             "d'explicitation ; ils ne mesurent ni la présence ni la relation directement."}


# ─────────────────────────────────────────────────────────────
#  Descripteurs de mouvement (points clés d'une captation sans marqueurs)
# ─────────────────────────────────────────────────────────────
ARTICULATIONS_SUIVIES = ("nez", "poignet_g", "poignet_d", "hanche_g", "hanche_d")


def descripteurs_mouvement(images: list[dict[str, Any]]) -> dict[str, Any]:
    """`images` : [{t: secondes, points: {nom: [x, y(, z)]}}], coordonnées normalisées.

    Grandeurs cinématiques classiquement associées aux facteurs d'effort de Laban
    (cf. Larboulette et Gibet, 2015) : énergie cinétique → poids ; accélération →
    temps ; rectitude du trajet → espace ; secousse (jerk) → flux. Valeurs
    relatives, à comparer d'une prise à l'autre pour un même acteur et un même cadrage."""
    if len(images) < 4:
        return {"images": len(images), "erreur": "au moins quatre images sont nécessaires"}
    noms = [n for n in ARTICULATIONS_SUIVIES if all(n in im["points"] for im in images)]
    if not noms:
        noms = sorted(set.intersection(*(set(im["points"]) for im in images)))[:6]
    t = [float(im["t"]) for im in images]

    def derivee(series: list[list[float]], ts: list[float]) -> tuple[list[list[float]], list[float]]:
        out, tt = [], []
        for i in range(1, len(series)):
            dt = max(1e-3, ts[i] - ts[i - 1])
            out.append([(b - a) / dt for a, b in zip(series[i - 1], series[i])])
            tt.append((ts[i] + ts[i - 1]) / 2)
        return out, tt

    norme = lambda v: math.sqrt(sum(c * c for c in v))  # noqa: E731
    energie, acc, secousse, rectitude = [], [], [], []
    for n in noms:
        pos = [list(map(float, im["points"][n])) for im in images]
        v, tv = derivee(pos, t)
        a, ta = derivee(v, tv)
        j, _ = derivee(a, ta)
        energie.append([norme(x) ** 2 for x in v])
        acc.append(sum(norme(x) for x in a) / len(a))
        secousse.append(sum(norme(x) for x in j) / len(j) if j else 0.0)
        chemin = sum(norme([q - p for p, q in zip(pos[i - 1], pos[i])]) for i in range(1, len(pos)))
        droite = norme([q - p for p, q in zip(pos[0], pos[-1])])
        if chemin > 1e-6:  # une articulation immobile ne renseigne pas l'espace
            rectitude.append(droite / chemin)
    e_tot = [sum(col) for col in zip(*energie)]
    return {
        "images": len(images), "duree_s": round(t[-1] - t[0], 2), "articulations": noms,
        "poids_energie_max": round(max(e_tot), 4), "poids_energie_moy": round(sum(e_tot) / len(e_tot), 4),
        "temps_acceleration": round(sum(acc) / len(acc), 4),
        "espace_rectitude": round(sum(rectitude) / len(rectitude), 3) if rectitude else None,
        "flux_secousse": round(sum(secousse) / len(secousse), 4),
        "lecture": "Valeurs relatives : comparer d'une prise à l'autre, à cadrage constant.",
    }
