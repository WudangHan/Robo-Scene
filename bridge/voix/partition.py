"""Partition prosodique d'une réplique : ce qu'une voix humaine fait du texte, phrase par phrase.

La voix du navigateur hachait les répliques parce que chaque virgule ouvrait un nouvel énoncé, et parce que
l'émotion se réduisait à trois valeurs (débit, hauteur, volume) fixées pour toute la réplique. La partition
remplace ces trois valeurs par une description du JEU, indépendante de tout moteur :

* l'unité de diction est la PHRASE (groupe de souffle), jamais la virgule : la mélodie de la phrase n'est
  plus brisée ; les groupes internes (virgules, points-virgules) restent dans le même énoncé ;
* chaque phrase reçoit son type intonatif (assertion, question, exclamation, suspension), sa place dans
  l'arc de la réplique (montée vers le sommet, ou extinction pour la tristesse et la lassitude), un débit,
  une hauteur et une intensité propres, une qualité de voix (pleine, soufflée, chuchotée, brisée, éclatante),
  une respiration avant les phrases longues ou chargées, et au plus un mot d'insistance ;
* de faibles variations déterministes (graine tirée du texte) empêchent deux phrases d'être dites au même
  tempo : un même texte, dans une même variation, donne toujours le même rendu (séances comparables).

La partition est ensuite TRADUITE pour chaque moteur : balises de jeu d'Eleven v3, consigne de jeu en
langage naturel pour gpt-4o-mini-tts, SSML pour les voix neuronales d'Azure (dont les voix fr-CA),
paramètres de Piper, et segments phrase par phrase pour la voix du navigateur (repli).

(Inférence) Les correspondances émotion → jeu vocal sont des heuristiques de conception inspirées des
descriptions de la prosodie émotionnelle ; elles ne prétendent ni à l'universalité ni à une validation
expérimentale et se modifient dans ce fichier.
"""
from __future__ import annotations

import hashlib
import random
import re
from typing import Any
from xml.sax.saxutils import escape

VERSION = 1

# ── Jeu vocal par émotion ────────────────────────────────────────────────────────────────────────────
# arc : « monte » (l'intensité croît vers la fin), « retombe » (elle s'éteint), « vague » (monte puis cède)
# qualite : qualité de voix dominante à forte intensité ; souffle : propension à respirer entre les phrases
# tags_el : balises Eleven v3 (anglais, conformément au guide de l'éditeur) ; nonverbal_el : son de jeu
# consigne : direction de jeu pour une consigne en langage naturel
JEU: dict[str, dict[str, Any]] = {
    "neutre": {"arc": "plat", "qualite": "pleine", "souffle": 0.3, "tags_el": [], "nonverbal_el": None,
               "consigne": "ton naturel de conversation, sans emphase, comme on parle à quelqu'un en face"},
    "colère": {"arc": "monte", "qualite": "éclatante", "souffle": 0.5, "tags_el": ["angry"], "fort_el": ["shouting"],
               "nonverbal_el": None,
               "consigne": "colère d'abord contenue puis qui monte ; attaques nettes des consonnes, voix qui se durcit, "
                           "mots qui claquent sur les insistances"},
    "joie": {"arc": "vague", "qualite": "pleine", "souffle": 0.3, "tags_el": ["happy"], "fort_el": ["excited"],
             "nonverbal_el": "laughs softly",
             "consigne": "joie lumineuse, sourire audible dans la voix, mélodie vive et ouverte"},
    "tristesse": {"arc": "retombe", "qualite": "brisée", "souffle": 0.8, "tags_el": ["sad"], "fort_el": ["crying"],
                  "nonverbal_el": "sighs",
                  "consigne": "tristesse retenue ; voix basse et lente, fins de phrases qui s'éteignent, "
                              "gorge serrée qui menace de se briser sur les mots chargés"},
    "peur": {"arc": "monte", "qualite": "soufflée", "souffle": 0.9, "tags_el": ["nervous"], "fort_el": ["panicked"],
             "nonverbal_el": "gasps",
             "consigne": "peur ; souffle court, débit irrégulier qui s'accélère, voix serrée et un peu haute"},
    "tendresse": {"arc": "plat", "qualite": "soufflée", "souffle": 0.6, "tags_el": ["softly", "warmly"],
                  "fort_el": ["softly", "warmly"], "nonverbal_el": None,
                  "consigne": "tendresse ; voix douce et proche, presque à l'oreille, legato, sans aucune dureté"},
    "mépris": {"arc": "plat", "qualite": "pleine", "souffle": 0.2, "tags_el": ["dismissive"], "fort_el": ["contemptuous"],
               "nonverbal_el": "scoffs",
               "consigne": "mépris froid ; débit lent et contrôlé, fins de phrases tombantes, distance hautaine"},
    "surprise": {"arc": "vague", "qualite": "pleine", "souffle": 0.4, "tags_el": ["surprised"], "fort_el": ["astonished"],
                 "nonverbal_el": "gasps",
                 "consigne": "surprise ; attaque haute et soudaine, puis la voix se reprend"},
    "ironie": {"arc": "plat", "qualite": "pleine", "souffle": 0.2, "tags_el": ["sarcastic"], "fort_el": ["sarcastic"],
               "nonverbal_el": None,
               "consigne": "ironie ; ton faussement aimable, mélodie appuyée sur les mots qu'on retourne, "
                           "petit sourire en coin dans la voix"},
    "lassitude": {"arc": "retombe", "qualite": "soufflée", "souffle": 0.8, "tags_el": ["tired"], "fort_el": ["exhausted"],
                  "nonverbal_el": "exhales",
                  "consigne": "lassitude ; voix lourde et lente, énergie qui baisse au fil de la réplique, soupirs"},
    "assurance": {"arc": "plat", "qualite": "pleine", "souffle": 0.2, "tags_el": ["confident"], "fort_el": ["confident"],
                  "nonverbal_el": None,
                  "consigne": "assurance ; voix posée et timbrée, débit égal, fins de phrases nettes et descendantes"},
}

STYLE_CONSIGNE = {
    "réalisme psychologique": "jeu réaliste, intime, comme au cinéma ; rien de déclamé",
    "farce populaire": "jeu de farce : énergie franche, rythme vif, contrastes appuyés, adresse au public",
    "tragédie grecque": "jeu tragique : ampleur, lenteur, voix projetée et grave, silences pleins",
    "documentaire": "jeu sobre et neutre, presque sans couleur, au service du sens",
    "film muet": "",
}

QUALITES_FR = {"pleine": "voix pleine et timbrée", "soufflée": "voix soufflée, beaucoup d'air",
               "chuchotée": "chuchotement", "brisée": "voix qui se brise", "éclatante": "voix éclatante, projetée"}

# Mots outils : jamais porteurs de l'insistance
OUTILS = set("""le la les un une des du de d l au aux et ou mais donc or ni car que qu qui quoi dont où ce cet cette ces
mon ma mes ton ta tes son sa ses notre nos votre vos leur leurs je j tu il elle on nous vous ils elles me m te t se s
lui y en ne n pas plus ai as a avons avez ont suis es est sommes êtes sont été être avoir fait faire dans sur sous avec
pour par sans chez vers entre comme si oui non bien très tout tous toute toutes cela ça ceci voici voilà alors aussi""".split())
NEGATIONS_FORTES = {"jamais", "rien", "personne", "plus", "aucun", "aucune", "nul", "nulle"}
INTERJECTIONS = re.compile(r"^(ah|oh|hélas|helas|eh|hé|ô|o|ha|holà|hola|las|ouf|bah|hein|tiens|dieu|ciel)\b", re.I)


def _graine(*parts: Any) -> random.Random:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return random.Random(int(h[:12], 16))


def _born(x: float, a: float, b: float) -> float:
    return min(b, max(a, x))


def nettoyer(texte: str) -> str:
    t = str(texte or "").replace("\n", " ").replace("...", "…")
    t = re.sub(r"\s+([,;:!?…»])", lambda m: (" " + m.group(1)) if m.group(1) in "!?:;»" else m.group(1), t)
    return re.sub(r"\s+", " ", t).strip()


def phrases(texte: str) -> list[str]:
    """Phrases (groupes de souffle). Une phrase de plus de 220 caractères est coupée à « ; » ou « : »."""
    out: list[str] = []
    for p in re.split(r"(?<=[.!?…])\s+(?=\S)", nettoyer(texte)):
        p = p.strip()
        if not p:
            continue
        if len(p) <= 220:
            out.append(p)
        else:
            out.extend(x.strip() for x in re.split(r"(?<=[;:])\s+", p) if x.strip())
    return out


def type_phrase(p: str) -> str:
    fin = p.rstrip(" »\"')")[-1:] if p.strip() else "."
    return {"?": "question", "!": "exclamation", "…": "suspension"}.get(fin, "assertion")


def _mots(p: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿœŒæÆ]+(?:['’-][A-Za-zÀ-ÖØ-öø-ÿœŒæÆ]+)*", p)


def insistance(p: str, deja: set[str]) -> str | None:
    """Le mot qu'une personne appuierait : capitales, négation forte, mot répété, sinon le mot plein le plus long
    du dernier groupe (le français place l'accent de groupe en fin de groupe)."""
    ms = _mots(p)
    if not ms:
        return None
    for m in ms:
        if len(m) > 2 and m.isupper():
            return m
    for m in ms:
        if m.lower() in NEGATIONS_FORTES and re.search(r"\bn(?:e\b|['’])(?:\s*[^\s,;:.!?]+){0,3}?\s+" + re.escape(m) + r"\b", p, re.I):
            return m
    pleins = [m for m in ms if m.lower().strip("'’") not in OUTILS and len(m) >= 4]
    vus: dict[str, int] = {}
    for m in pleins:
        vus[m.lower()] = vus.get(m.lower(), 0) + 1
    for m in pleins:
        if vus[m.lower()] > 1 and m.lower() not in deja:
            return m
    groupes = [g for g in re.split(r"[,;:]", p) if _mots(g)]
    dernier = [m for m in _mots(groupes[-1] if groupes else p) if m in pleins]
    cand = dernier or pleins
    cand = [m for m in cand if m.lower() not in deja] or cand
    return max(cand, key=len) if cand else None


def construire(texte: str, variation: dict[str, Any] | None = None, *, regime: str = "humain",
               marques: dict[str, Any] | None = None, personnage: str = "", langue: str = "fr-CA",
               base: dict[str, float] | None = None) -> dict[str, Any]:
    """Partition prosodique d'une réplique.

    variation : variation du partenaire (emotion, intensite, melange, style…) ; base : débit, hauteur et volume
    déjà calculés par variations.rendu_voix (échelle de la voix du navigateur), dont la partition part."""
    v = variation or {}
    emo = v.get("emotion", "neutre") if v.get("emotion") in JEU else "neutre"
    inten = int(v.get("intensite", 5) or 0)
    k = _born(inten / 10, 0, 1)
    jeu = JEU[emo]
    marques = marques or {}
    style = v.get("style", "réalisme psychologique")
    base = base or {"debit": 1.0, "hauteur": 1.0, "volume": 0.85}
    rnd = _graine(texte, emo, inten, v.get("melange"), style, personnage)
    ph = phrases(texte)
    n = len(ph)
    chuchote = bool(marques.get("chuchote"))
    aparte = bool(marques.get("aparte"))
    deja: set[str] = set()
    sortie = []
    for i, p in enumerate(ph):
        pos = i / (n - 1) if n > 1 else 1.0
        # Arc : intensité locale de la phrase (0–1)
        if jeu["arc"] == "monte":
            loc = k * (0.65 + 0.35 * pos)
        elif jeu["arc"] == "retombe":
            loc = k * (1.0 - 0.35 * pos)
        elif jeu["arc"] == "vague":
            loc = k * (0.75 + 0.25 * (1 - abs(2 * pos - 1)))
        else:
            loc = k * (0.9 + 0.1 * rnd.random())
        t = type_phrase(p)
        if t == "exclamation":
            loc = min(1.0, loc + 0.12)
        # Débit relatif à la base : jitter humain ±4 %, phrase brève plus détachée, fin de tirade ralentie
        debit = base["debit"] * (1 + (rnd.random() - 0.5) * 0.08)
        if len(p) < 25:
            debit *= 0.96
        if i == n - 1 and n > 2:
            debit *= 0.95
        if jeu["arc"] == "monte":
            debit *= 1 + 0.08 * loc * pos
        if jeu["arc"] == "retombe":
            debit *= 1 - 0.07 * k * pos
        # Hauteur : déclinaison d'ensemble, question montante, exclamation haute, suspension tenue
        hauteur = base["hauteur"] * (1 + (rnd.random() - 0.5) * 0.04)
        hauteur *= {"question": 1.04, "exclamation": 1.05 + 0.05 * loc, "suspension": 0.99}.get(t, 1.0)
        if jeu["arc"] == "retombe":
            hauteur *= 1 - 0.04 * pos * k
        volume = base["volume"] * (1 + {"exclamation": 0.12, "suspension": -0.08}.get(t, 0) * (0.5 + loc))
        qualite = "pleine"
        if chuchote or aparte:
            qualite = "chuchotée"
            volume = min(volume, 0.45)
        elif loc >= 0.6 and jeu["qualite"] != "pleine":
            qualite = jeu["qualite"]
        # Respiration : avant une phrase longue, ou souvent dans les émotions « soufflées »
        souffle = i > 0 and (len(p) > 90 or rnd.random() < jeu["souffle"] * k)
        pause = {"question": 520, "exclamation": 420, "suspension": 780}.get(t, 460)
        pause = pause * (1 + v.get("_pause", 0)) * (0.85 + 0.3 * rnd.random())
        if jeu["arc"] == "retombe":
            pause *= 1 + 0.4 * k
        if i == n - 1:
            pause = 0
        mot = insistance(p, deja) if inten >= 4 else None
        if mot:
            deja.add(mot.lower())
        sortie.append({"texte": p, "type": t, "intensite_locale": round(loc * 10, 1),
                       "debit": round(_born(debit, 0.6, 1.6), 3), "hauteur": round(_born(hauteur, 0.4, 1.6), 3),
                       "volume": round(_born(volume, 0.15, 1.0), 3), "qualite": qualite, "souffle_avant": souffle,
                       "insistance": mot, "pause_apres_ms": int(pause)})
    duree = sum(len(_mots(s["texte"])) * 300 / s["debit"] + s["pause_apres_ms"] for s in sortie)
    return {"version": VERSION, "langue": langue, "regime": regime, "personnage": personnage, "emotion": emo,
            "intensite": inten, "melange": v.get("melange"), "style": style, "aparte": aparte, "chuchote": chuchote,
            "arc": jeu["arc"], "phrases": sortie, "duree_estimee_ms": int(duree)}


# ═══════════════════════════════ Traductions par moteur ═══════════════════════════════

def vers_navigateur(part: dict[str, Any]) -> list[dict[str, Any]]:
    """Repli : UN énoncé par phrase (les virgules restent dans l'énoncé), prosodie propre à chaque phrase."""
    return [{"texte": s["texte"], "debit": s["debit"], "hauteur": s["hauteur"], "volume": s["volume"],
             "pause_apres_ms": s["pause_apres_ms"] + (180 if i + 1 < len(part["phrases"])
                                                        and part["phrases"][i + 1]["souffle_avant"] else 0)}
            for i, s in enumerate(part["phrases"])]


def consigne_jeu(part: dict[str, Any], accent: str = "québécois") -> str:
    """Direction de jeu en langage naturel (gpt-4o-mini-tts ; aussi affichée à l'opératrice)."""
    jeu = JEU.get(part["emotion"], JEU["neutre"])
    inten = part["intensite"]
    degre = "à peine perceptible" if inten <= 2 else "légère" if inten <= 4 else "nette" if inten <= 7 else "très forte"
    lignes = [
        f"Langue : français {accent}, accent naturel du Québec (pas d'accent de France), prononciation de théâtre "
        "mais vivante." if accent == "québécois" else f"Langue : français {accent}.",
        "Tu es un acteur ou une actrice qui donne la réplique en répétition : tu JOUES, tu ne lis pas.",
    ]
    if part.get("personnage"):
        lignes.append(f"Personnage : {part['personnage']}.")
    etat = f"État : {jeu['consigne']} ; intensité {degre} ({inten}/10)"
    if part.get("melange"):
        etat += f", teintée de {part['melange']}"
    lignes.append(etat + ".")
    if STYLE_CONSIGNE.get(part.get("style")):
        lignes.append(f"Registre : {STYLE_CONSIGNE[part['style']]}.")
    arc = {"monte": "l'intensité monte d'une phrase à l'autre jusqu'à la fin",
           "retombe": "l'énergie s'éteint peu à peu jusqu'à la dernière phrase",
           "vague": "l'élan culmine au milieu puis se relâche"}.get(part["arc"])
    if arc and len(part["phrases"]) > 1:
        lignes.append(f"Arc : {arc}.")
    mots = [s["insistance"] for s in part["phrases"] if s.get("insistance")]
    if mots:
        lignes.append("Insistances : " + ", ".join(f"« {m} »" for m in mots[:6]) + ".")
    if part.get("chuchote") or part.get("aparte"):
        lignes.append("Dit à mi-voix, en aparté, comme pour soi ou pour le public seulement.")
    lignes.append("Rythme humain : respirations audibles entre les phrases, vrais silences aux points de suspension, "
                  "tempo qui varie d'une phrase à l'autre ; jamais de débit mécanique ni de mélodie répétitive.")
    return "\n".join(lignes)


def vers_openai(part: dict[str, Any], accent: str = "québécois") -> dict[str, Any]:
    texte = " ".join(s["texte"] for s in part["phrases"])
    debit = sum(s["debit"] for s in part["phrases"]) / max(1, len(part["phrases"]))
    return {"input": texte, "instructions": consigne_jeu(part, accent)[:1800], "speed": round(_born(debit, 0.8, 1.25), 2)}


def vers_elevenlabs(part: dict[str, Any]) -> dict[str, Any]:
    """Texte balisé pour Eleven v3 : balise d'état à chaque changement, sons de jeu (soupir, souffle), ellipses
    pour les silences ; la vitesse et la stabilité vont dans voice_settings. Les balises SSML <break> ne sont pas
    prises en charge par v3 (guide de l'éditeur) : les silences passent par la ponctuation."""
    jeu = JEU.get(part["emotion"], JEU["neutre"])
    morceaux: list[str] = []
    precedent: tuple[str, ...] = ()
    for i, s in enumerate(part["phrases"]):
        tags: list[str] = []
        if s["qualite"] == "chuchotée":
            tags.append("whispers")
        elif part["emotion"] != "neutre" and s["intensite_locale"] >= 2:
            tags.extend(jeu.get("fort_el", jeu["tags_el"]) if s["intensite_locale"] >= 7.5 else jeu["tags_el"])
        if s["souffle_avant"] and jeu.get("nonverbal_el") and s["intensite_locale"] >= 5:
            tags.insert(0, jeu["nonverbal_el"])
        elif s["souffle_avant"]:
            tags.insert(0, "inhales")
        texte = s["texte"]
        if s.get("insistance") and s["intensite_locale"] >= 7 and len(s["insistance"]) >= 4:
            texte = re.sub(r"\b" + re.escape(s["insistance"]) + r"\b", s["insistance"].upper(), texte, count=1)
        if s["type"] == "suspension" and not texte.endswith("…"):
            texte = texte.rstrip(".") + "…"
        cle = tuple(t for t in tags if t not in ("inhales", jeu.get("nonverbal_el")))
        bal = [t for t in tags if t in ("inhales", jeu.get("nonverbal_el")) or cle != precedent]
        precedent = cle or precedent
        morceaux.append("".join(f"[{t}] " for t in dict.fromkeys(bal)) + texte)
        if s["pause_apres_ms"] >= 700 and i + 1 < len(part["phrases"]) and not texte.endswith("…"):
            morceaux.append("…")
    debit = sum(s["debit"] for s in part["phrases"]) / max(1, len(part["phrases"]))
    k = part["intensite"] / 10
    # Stabilité v3 : 0 = créative (plus expressive), 0,5 = naturelle, 1 = robuste (guide de l'éditeur)
    stabilite = 0.0 if k >= 0.7 and part["emotion"] != "neutre" else 0.5
    return {"text": " ".join(morceaux), "voice_settings": {"stability": stabilite, "similarity_boost": 0.8,
                                                           "speed": round(_born(debit, 0.7, 1.2), 2)}}


def _pc(x: float) -> str:
    v = round((x - 1) * 100)
    return f"{'+' if v >= 0 else ''}{v}%"


def vers_ssml(part: dict[str, Any], voix: str, langue: str = "fr-CA", style: str | None = None) -> str:
    """SSML pour Azure : prosodie par phrase (débit, hauteur, volume), mot d'insistance appuyé, silences et
    respirations figurés par des pauses ; style mstts:express-as seulement si la voix en déclare un."""
    corps = []
    for i, s in enumerate(part["phrases"]):
        t = escape(s["texte"])
        dernier = (_mots(s["texte"]) or [""])[-1]
        if s["type"] == "question" and dernier and dernier != s.get("insistance"):
            t = re.sub(r"([\wÀ-ÿœæ'’-]+)(\s*\?)$", r'<prosody pitch="+3st">\1</prosody>\2', t)
        if s.get("insistance") and s["intensite_locale"] >= 4:
            m = escape(s["insistance"])
            monte = 2 if s["type"] == "question" and s["insistance"] == dernier else 0
            t = re.sub(r"(?<![\w<\"=-])" + re.escape(m) + r"(?![\w\"])",
                       f'<prosody pitch="+{1 + monte + round(s["intensite_locale"] / 4)}st" volume="+12%" rate="-8%">{m}</prosody>',
                       t, count=1)
        # Une voix neuronale porte déjà sa mélodie : les écarts sont atténués (un fort décalage de hauteur la dégrade)
        vol = "x-soft" if s["qualite"] == "chuchotée" else _pc(1 + 0.6 * (s["volume"] / 0.85 - 1))
        bloc = (f'<prosody rate="{_pc(1 + 0.8 * (s["debit"] - 1))}" pitch="{_pc(1 + 0.5 * (s["hauteur"] - 1))}" '
                f'volume="{vol}">{t}</prosody>')
        if s["souffle_avant"] and i:
            bloc = '<break time="250ms"/>' + bloc
        if s["pause_apres_ms"]:
            bloc += f'<break time="{min(5000, s["pause_apres_ms"])}ms"/>'
        corps.append(bloc)
    contenu = "".join(corps)
    if style:
        deg = round(_born(part["intensite"] / 5, 0.3, 2.0), 2)
        contenu = f'<mstts:express-as style="{escape(style)}" styledegree="{deg}">{contenu}</mstts:express-as>'
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{langue}">'
            f'<voice name="{escape(voix)}">{contenu}</voice></speak>')


def vers_piper(part: dict[str, Any]) -> list[dict[str, Any]]:
    """Piper (local) : une synthèse par phrase ; length_scale = inverse du débit, variabilité (noise) accrue avec
    l'intensité ; la hauteur n'est pas réglable avec ce moteur."""
    return [{"texte": s["texte"], "length_scale": round(1 / s["debit"], 3),
             "noise_scale": round(0.55 + 0.25 * s["intensite_locale"] / 10, 3), "noise_w": 0.8,
             "silence_ms": s["pause_apres_ms"] + (200 if s["souffle_avant"] else 0)} for s in part["phrases"]]


def texte_brut(part: dict[str, Any]) -> str:
    return " ".join(s["texte"] for s in part["phrases"])
