"""Moteur de variations émotionnelles du partenaire.

Deux régimes de rendu, au choix de l'équipe artistique :

* « émulation humaine » : la variation est rendue par une prosodie (débit,
  hauteur, volume, pauses) et des postures inspirées du jeu humain ;
* « voie machinique » : la variation est rendue par des qualités de
  mouvement issues des facteurs d'effort de Laban — poids (léger ↔ fort),
  temps (soutenu ↔ soudain), espace (indirect ↔ direct), flux (libre ↔
  contenu) — et par une voix délibérément non humaine. Aucune émotion n'y
  est attribuée à la machine : seule une qualité expressive est produite.

Les correspondances émotion → prosodie → effort sont des HEURISTIQUES de
départ, modifiables dans ce fichier ; elles ne prétendent ni à
l'universalité des émotions ni à une validation expérimentale.
"""
from __future__ import annotations

import hashlib
import math
import random
import re
from typing import Any

from .texte_outils import normaliser, raciner, syllabes

AXES = ("poids", "temps", "espace", "flux")

# prosodie : écarts à intensité 10 (débit, hauteur relatifs ; volume absolu ; pause = facteur)
# effort : coordonnées Laban entre -1 et 1 (poids léger -1 / fort +1 ; temps soutenu -1 / soudain +1 ;
#          espace indirect -1 / direct +1 ; flux libre -1 / contenu +1)
# posture : décalages articulaires (degrés) à intensité 10, par nom d'articulation canonique
EMOTIONS: dict[str, dict[str, Any]] = {
    "neutre": {"prosodie": (0, 0, 0, 0), "effort": (0, 0, 0, 0), "posture": {}},
    "colère": {"prosodie": (0.18, 0.12, 0.30, -0.35), "effort": (0.9, 0.7, 0.8, 0.7),
               "posture": {"epaule": 25, "coude": -20, "tete": 8}},
    "joie": {"prosodie": (0.15, 0.18, 0.15, -0.2), "effort": (-0.5, 0.6, -0.4, -0.7),
             "posture": {"epaule": 20, "tete": 15}},
    "tristesse": {"prosodie": (-0.28, -0.15, -0.30, 0.7), "effort": (-0.2, -0.8, -0.4, 0.2),
                  "posture": {"tete": -25, "epaule": -20, "coude": 15}},
    "peur": {"prosodie": (0.12, 0.20, -0.15, 0.3), "effort": (-0.6, 0.8, -0.6, 0.9),
             "posture": {"epaule": 15, "coude": 30, "tete": -12}},
    "tendresse": {"prosodie": (-0.15, 0.05, -0.25, 0.3), "effort": (-0.8, -0.7, -0.5, -0.6),
                  "posture": {"base": 10, "tete": -8, "epaule": 8}},
    "mépris": {"prosodie": (-0.10, -0.08, 0.05, 0.2), "effort": (0.5, -0.4, 0.8, 0.6),
               "posture": {"tete": 20, "base": -20}},
    "surprise": {"prosodie": (0.10, 0.25, 0.15, 0.1), "effort": (-0.3, 0.9, 0.7, -0.2),
                 "posture": {"tete": 20, "epaule": 30}},
    "ironie": {"prosodie": (0.05, 0.10, 0.0, 0.25), "effort": (-0.6, 0.3, -0.7, -0.4),
               "posture": {"tete": 10, "base": 15}},
    "lassitude": {"prosodie": (-0.25, -0.12, -0.20, 0.5), "effort": (-0.1, -0.9, -0.6, -0.5),
                  "posture": {"tete": -18, "epaule": -12}},
    "assurance": {"prosodie": (-0.05, -0.05, 0.20, 0.15), "effort": (0.7, -0.5, 0.9, -0.2),
                  "posture": {"tete": 10, "epaule": 10}},
}

CONTRAIRES = {"colère": "tendresse", "tendresse": "colère", "joie": "tristesse", "tristesse": "joie",
              "peur": "assurance", "assurance": "peur", "mépris": "tendresse", "surprise": "lassitude",
              "lassitude": "surprise", "ironie": "assurance", "neutre": "surprise"}

# Livret, 1re année, exercice 6.3 « Variation sur un thème » : cinq registres stylistiques
STYLES: dict[str, dict[str, float]] = {
    "réalisme psychologique": {"debit": 0, "hauteur": 0, "volume": 0, "pause": 0, "ampleur": 1.0, "voix": 1},
    "farce populaire": {"debit": 0.15, "hauteur": 0.15, "volume": 0.1, "pause": -0.2, "ampleur": 1.4, "voix": 1},
    "tragédie grecque": {"debit": -0.2, "hauteur": -0.1, "volume": 0.15, "pause": 0.5, "ampleur": 1.2, "voix": 1},
    "film muet": {"debit": 0, "hauteur": 0, "volume": 0, "pause": 0, "ampleur": 1.6, "voix": 0},
    "documentaire": {"debit": 0, "hauteur": 0, "volume": 0, "pause": 0, "ampleur": 0.3, "voix": 1,
                     "aplatir": 0.3},
}

LEXIQUE: dict[str, tuple[str, ...]] = {
    "colère": ("colere", "furieux", "rage", "traitre", "insolent", "fache", "maudit", "assez", "indigne",
               "perfide", "fureur", "courroux", "infame"),
    "joie": ("joie", "bonheur", "heureux", "ravi", "plaisir", "rire", "charmant", "merveille", "enchante"),
    "tristesse": ("helas", "pleur", "larme", "malheur", "douleur", "triste", "perdu", "seul", "mourir",
                  "chagrin", "fatigue"),
    "peur": ("peur", "crainte", "trembl", "effroi", "terreur", "danger", "craindre", "affreux"),
    "tendresse": ("aimer", "aime", "coeur", "tendre", "doux", "cher", "amour", "pardon", "douceur"),
    "mépris": ("mepris", "vil", "lache", "sot", "ridicule", "pitoyable", "miserable"),
    "surprise": ("quoi", "comment", "vraiment", "ciel", "dieu", "incroyable", "etrange"),
    "ironie": ("bravo", "admirable", "parfait", "bien sur", "evidemment"),
    "lassitude": ("las", "lasse", "fatigue", "ennui", "toujours", "encore", "assez"),
    "assurance": ("veux", "dois", "jamais", "certain", "sais", "declare", "net"),
}

DIDASCALIES: list[tuple[str, str]] = [
    (r"col[eè]re|furi|emport|rage|violemment|criant|hurl", "colère"),
    (r"riant|gaiement|joyeu|souriant|ravi", "joie"),
    (r"pleur|larme|sanglot|tristement|accabl", "tristesse"),
    (r"trembl|effray|peur|inquiet|angoiss", "peur"),
    (r"doucement|tendrement|avec douceur|caress", "tendresse"),
    (r"froidement|s[eè]chement|ironi|raill|moqu", "ironie"),
    (r"surpris|stup[eé]f|[eé]tonn", "surprise"),
    (r"las|fatigu|dans un souffle|abattu", "lassitude"),
    (r"fermement|avec force|r[eé]solu", "assurance"),
]

# Mots fréquents à valeur faible : ils comptent pour moitié
FAIBLES = {"veux", "dois", "sais", "toujours", "encore", "comment", "quoi", "seul", "cher", "net", "assez"}
_RAC_LEX = {e: tuple(raciner(m) if " " not in m else m for m in ms) for e, ms in LEXIQUE.items()}
SEUIL_INDICE = 1.0


def indices(texte: str, didascalies: list[str] | None = None,
            types_tei: list[str] | None = None) -> dict[str, Any]:
    """Indices textuels explicites ; chaque score est justifié par les preuves relevées."""
    scores: dict[str, float] = {e: 0.0 for e in LEXIQUE}
    preuves: dict[str, list[str]] = {e: [] for e in LEXIQUE}
    marques = {"aparte": False, "chuchote": False, "adresse": None}
    for d in didascalies or []:
        dn = normaliser(d)
        if "a part" in dn:
            marques["aparte"] = True
        if re.search(r"\bbas\b|souffle|murmur|chuchot", dn):
            marques["chuchote"] = True
        for motif, emo in DIDASCALIES:
            if re.search(motif, dn):
                scores[emo] += 3
                preuves[emo].append(f"didascalie « {d} »")
    for t in types_tei or []:
        if t in ("toward", "away"):
            marques["adresse"] = t
    norm = normaliser(texte)
    toks = re.findall(r"[a-z]+", norm)
    racs = [raciner(t) for t in toks]
    for emo, lex in _RAC_LEX.items():
        for m in lex:
            n = norm.count(m) if " " in m else sum(1 for r in racs if r == m or (len(m) > 4 and r.startswith(m)))
            if n:
                poids = 0.5 if m in {raciner(f) for f in FAIBLES} | FAIBLES else 1.0
                scores[emo] += n * poids
                preuves[emo].append(f"lexique « {m} » ×{n}")
    excl, quest = texte.count("!"), texte.count("?")
    susp = texte.count("…") + texte.count("...")
    if excl:
        for emo in ("colère", "joie", "surprise"):
            scores[emo] += 0.5 * excl
        preuves["colère"].append(f"{excl} point(s) d'exclamation")
    if quest:
        scores["surprise"] += 0.4 * quest
        preuves["surprise"].append(f"{quest} point(s) d'interrogation")
    if susp:
        scores["tristesse"] += 0.4 * susp
        scores["peur"] += 0.3 * susp
        preuves["tristesse"].append(f"{susp} point(s) de suspension")
    classes = sorted(((s, e) for e, s in scores.items() if s > 0), reverse=True)
    return {"candidats": [{"emotion": e, "score": round(s, 2), "preuves": preuves[e]} for s, e in classes[:4]],
            "marques": marques, "ponctuation": {"exclamations": excl, "questions": quest, "suspensions": susp}}


def variation(emotion: str = "neutre", intensite: int = 5, melange: str | None = None, part_melange: float = 0.5,
              style: str = "réalisme psychologique", etiquette: str = "", justification: str = "",
              source: str = "règles", effort: dict[str, float] | None = None) -> dict[str, Any]:
    """Une variation. `effort` (poids, temps, espace, flux entre -1 et 1) permet de composer
    une qualité expressive directement, sans passer par une étiquette émotionnelle."""
    if emotion not in EMOTIONS:
        raise ValueError(f"Émotion inconnue : {emotion}")
    if melange and melange not in EMOTIONS:
        raise ValueError(f"Émotion inconnue : {melange}")
    if style not in STYLES:
        raise ValueError(f"Style inconnu : {style}")
    return {"emotion": emotion, "intensite": max(1, min(10, int(intensite))), "melange": melange,
            "part_melange": max(0.0, min(1.0, float(part_melange))), "style": style,
            "etiquette": etiquette or (f"{emotion} et {melange}" if melange else emotion),
            "justification": justification, "source": source,
            "effort": {a: max(-1.0, min(1.0, float((effort or {}).get(a, 0)))) for a in AXES} if effort else None}


def propositions(texte: str, didascalies: list[str] | None = None, types_tei: list[str] | None = None) -> dict[str, Any]:
    """Trois variations : lecture des indices du texte, contre-emploi, mélange (exercice 5.3 du livret)."""
    ind = indices(texte, didascalies, types_tei)
    cands = [c for c in ind["candidats"] if c["score"] >= SEUIL_INDICE]
    if cands:
        e1 = cands[0]["emotion"]
        explicite = any(p.startswith("didascalie") for p in cands[0]["preuves"])
        lecture = variation(e1, 7 if explicite else 5, etiquette=f"lecture du texte : {e1}",
                            justification="Indices : " + " ; ".join(cands[0]["preuves"]))
        e2 = cands[1]["emotion"] if len(cands) > 1 else CONTRAIRES[e1]
    else:
        e1, e2 = "neutre", "surprise"
        lecture = variation("neutre", 3, etiquette="lecture du texte : sans indice marqué",
                            justification="Aucun indice explicite (didascalie, lexique, ponctuation) : "
                                          "jeu retenu, laissé ouvert à la proposition de l'acteur.")
    contre = CONTRAIRES[e1]
    return {
        "indices": ind,
        "propositions": [
            lecture,
            variation(contre, 4, etiquette=f"contre-emploi : {contre}",
                      justification=f"Jouer contre l'indice dominant ({e1}) pour éprouver le sous-texte."),
            variation(e1 if e1 != "neutre" else e2, 5, melange=e2 if e2 != e1 else contre, part_melange=0.4,
                      etiquette=f"mélange : {e1} et {e2 if e2 != e1 else contre}",
                      justification="Deux affects simultanés, au sens de l'exercice 5.3 « Mix d'émotions » du livret."),
        ],
    }


# ─────────────────────────────────────────────────────────────
#  Rendu : voix et geste
# ─────────────────────────────────────────────────────────────
def _vecteurs(v: dict[str, Any]) -> tuple[list[float], list[float], dict[str, float]]:
    k = v["intensite"] / 10
    a = EMOTIONS[v["emotion"]]
    pros = [x * k for x in a["prosodie"]]
    eff = [x * k for x in a["effort"]]
    post = {j: d * k for j, d in a["posture"].items()}
    if v.get("effort"):
        eff = [v["effort"][a] for a in AXES]
    if v.get("melange"):
        b, w = EMOTIONS[v["melange"]], v["part_melange"]
        pros = [(1 - w) * x + w * y * k for x, y in zip(pros, b["prosodie"])]
        if not v.get("effort"):
            eff = [(1 - w) * x + w * y * k for x, y in zip(eff, b["effort"])]
        for j, d in b["posture"].items():
            post[j] = (1 - w) * post.get(j, 0) + w * d * k
    return pros, eff, post


def _segments(texte: str, facteur_pause: float) -> list[dict[str, Any]]:
    morceaux = re.split(r"(?<=[,;:.!?…])\s+", texte.replace("\n", " "))
    segs = []
    for m in morceaux:
        if not m.strip():
            continue
        fin = m.rstrip()[-1]
        base = 650 if fin == "…" or m.rstrip().endswith("...") else 420 if fin in ".!?" else 230 if fin in ",;:" else 0
        segs.append({"texte": m.strip(), "pause_apres_ms": int(max(0, base * (1 + facteur_pause)))})
    return segs


def rendu_voix(texte: str, v: dict[str, Any], regime: str = "humain",
               marques: dict[str, Any] | None = None) -> dict[str, Any]:
    pros, eff, _ = _vecteurs(v)
    st = STYLES[v["style"]]
    marques = marques or {}
    if regime == "machinique":
        # Voix non humaine : hauteur fixe, débit et pauses commandés par l'effort de temps et le flux
        debit = 1.0 + 0.35 * eff[1]
        hauteur = 0.6
        volume = 0.75 + 0.2 * eff[0]
        pause = 0.6 * eff[3] - 0.3 * eff[1]
    else:
        aplat = st.get("aplatir", 1.0)
        debit = 1.0 + aplat * pros[0] + st["debit"]
        hauteur = 1.0 + aplat * pros[1] + st["hauteur"]
        volume = 0.8 + aplat * pros[2] + st["volume"]
        pause = aplat * pros[3] + st["pause"]
    if marques.get("aparte") or marques.get("chuchote"):
        volume -= 0.3
    debit = round(min(1.6, max(0.6, debit)), 2)
    segs = _segments(texte, pause)
    duree = sum(syllabes(s["texte"]) for s in segs) / (5.2 * debit) * 1000 + sum(s["pause_apres_ms"] for s in segs)
    return {"parler": bool(st["voix"]), "debit": debit, "hauteur": round(min(1.6, max(0.4, hauteur)), 2),
            "volume": round(min(1.0, max(0.15, volume)), 2), "type_voix": regime,
            "segments": segs, "duree_estimee_ms": int(duree)}


CANON = {"base": ("base", "socle", "rotation", "taille"), "epaule": ("epaule", "bras", "shoulder"),
         "coude": ("coude", "avant", "elbow"), "tete": ("tete", "cou", "head", "regard", "nuque")}


def _indices_articulations(noms: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, n in enumerate(noms):
        mots_nom = set(re.findall(r"[a-z]+", normaliser(n)))
        for c, alias in CANON.items():
            if c not in out and mots_nom & set(alias):
                out[c] = i
                break
    return out


def rendu_geste(v: dict[str, Any], duree_ms: int, noms: list[str], repos: list[float],
                min_deg: list[float], max_deg: list[float], regime: str = "humain",
                graine: str = "") -> list[dict[str, Any]]:
    """Images clés [{deg, ms}] couvrant `duree_ms`, bornées aux limites articulaires.

    La couche de sécurité du pont borne et ralentit de nouveau chaque image."""
    _, eff, post = _vecteurs(v)
    ampleur = STYLES[v["style"]]["ampleur"]
    idx = _indices_articulations(noms)
    rnd = random.Random(int(hashlib.sha256(f"{graine}|{v['etiquette']}|{regime}".encode()).hexdigest()[:12], 16))
    n = len(noms)

    def borner(deg: list[float]) -> list[float]:
        return [round(max(min_deg[i], min(max_deg[i], d)), 1) for i, d in enumerate(deg)]

    images: list[dict[str, Any]] = []
    duree_ms = max(600, int(duree_ms))
    if regime == "machinique":
        poids, temps, espace, flux = eff
        amp = (8 + 22 * (poids + 1) / 2) * ampleur
        pas = int(900 - 600 * (temps + 1) / 2)              # soudain : pas courts
        tenue = int(max(0, 350 * (flux + 1) / 2 - 60))      # contenu : arrêts marqués
        principal = idx.get("epaule", 0)
        t, signe = 0, 1
        while t < duree_ms - pas:
            deg = list(repos)
            if espace >= 0:   # direct : un seul axe, aller-retour franc
                deg[principal] = repos[principal] + signe * amp
            else:             # indirect : plusieurs articulations déphasées, cibles variées
                for j in range(n):
                    deg[j] = repos[j] + amp * (0.4 + 0.6 * rnd.random()) * math.sin(t / 300 + j * 1.7) \
                        * (1 if j == principal else 0.6)
            images.append({"deg": borner(deg), "ms": pas})
            if tenue:
                images.append({"deg": borner(deg), "ms": tenue})
            t += pas + tenue
            signe = -signe
    else:
        cible = list(repos)
        for c, d in post.items():
            if c in idx:
                cible[idx[c]] = repos[idx[c]] + d * ampleur
        entree = min(1200, max(300, int(duree_ms * 0.25)))
        images.append({"deg": borner(cible), "ms": entree})
        # Battements : petits mouvements de tête accordés aux attaques de phrase
        reste = duree_ms - entree
        k = idx.get("tete", n - 1)
        nb = max(1, min(6, reste // 900))
        amp = 3 + 6 * v["intensite"] / 10 * ampleur
        for b in range(nb):
            hoche = list(cible)
            hoche[k] = cible[k] - amp
            images.append({"deg": borner(hoche), "ms": 220})
            images.append({"deg": borner(cible), "ms": max(250, reste // nb - 220)})
    images.append({"deg": borner(list(repos)), "ms": 900})
    return images


def decrire(v: dict[str, Any]) -> dict[str, Any]:
    """Vue lisible : coordonnées d'effort et prosodie résultantes (pour l'interface et le journal)."""
    pros, eff, _ = _vecteurs(v)
    return {"effort": dict(zip(AXES, [round(x, 2) for x in eff])),
            "prosodie": dict(zip(("debit", "hauteur", "volume", "pause"), [round(x, 2) for x in pros]))}
