"""Dialogue parlé entre une personne et le robot humanoïde, le chien ou le drone (demande du 20 octobre 2026).

La page écoute (reconnaissance vocale du navigateur, sur l'appareil par défaut), envoie la phrase au pont, puis dit
la réponse d'une voix humaine (synthèse du navigateur ; pour le TonyPi Pro, aussi par son haut-parleur s'il est relié).
Le pont confie la réponse au moteur que l'opératrice a choisi pour cette machine (Claude, GPT, Grok, Gemini ou un
modèle de LM Studio, voir bridge/modeles) ; le routeur de sensibilité D03 s'applique toujours avant ce choix.

Principes :
- Une réponse courte, orale, en français, dans le personnage de la machine, sans prétendre percevoir ce qu'elle ne
  perçoit pas.
- Le modèle peut PROPOSER des actions, seulement dans le vocabulaire fermé de la machine ; le pont les revalide
  (types, bornes, repères existants) et la page les présente à une personne, qui les valide ou les rejette. Ni la
  coupure des moteurs ni l'ARRÊT ne passent par le modèle : « stop » et « arrêt d'urgence » sont traités par la page
  avant tout appel.
- La mémoire d'échange est courte (six tours par machine), gardée en mémoire vive seulement et effaçable ; le
  journal de séance consigne le moteur, la version et les longueurs, jamais le texte des échanges (minimisation).
- Sans moteur disponible, une voie déterministe répond aux formules usuelles et dit qu'elle ne peut converser.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import deque
from typing import Any

from .partenaire import avatar as avatar_mod

DOMAINES = ("robot", "chien", "drone")
NOMS = {"robot": "le robot humanoïde", "chien": "le chien robot", "drone": "le drone"}
TOURS_MEMOIRE = 6

PERSONAS = {
    "robot": ("Tu es le robot humanoïde de scène de la plateforme ROBO-SCÈNE, un partenaire de jeu pour des "
              "comédiennes et des comédiens. Tu as un corps, un visage expressif, une voix ; tu peux faire des gestes, "
              "prendre des poses, te déplacer sur le plateau et montrer des émotions."),
    "chien": ("Tu es le chien robot de scène de la plateforme ROBO-SCÈNE : un quadrupède qui marche, s'assoit, se "
              "couche, donne la patte, salue et prend des allures expressives. Dans ce dialogue, tu parles comme un "
              "personnage de théâtre : chaleureux, curieux, joueur, avec de brèves touches canines."),
    "drone": ("Tu es le drone de scène de la plateforme ROBO-SCÈNE : un petit quadricoptère qui décolle, se pose, se "
              "déplace dans des zones permises au-dessus du plateau et filme avec sa caméra. Dans ce dialogue, tu parles "
              "comme un personnage de théâtre : précis, calme, un peu aérien."),
}

REGLES = """Règles de la conversation :
- Réponds en français, à l'oral : une à trois phrases courtes, sans liste, sans titre, sans émoticône ni balisage.
- Reste dans ton personnage, avec bienveillance ; si on te demande ce que tu es, dis que tu es une machine pilotée
  par un modèle d'IA, sous la responsabilité de l'équipe.
- N'affirme jamais voir, entendre ou sentir ce que le message ne t'apprend pas ; n'invente ni nom ni fait sur la personne.
- Tu ne peux rien faire de toi-même : si la personne te demande un mouvement, PROPOSE-le dans « actions », avec
  seulement les types et valeurs du vocabulaire fourni ; une personne validera ou non. Dis-le simplement
  (« Je peux le faire si on me le permet. »). Si rien n'est demandé, laisse « actions » vide.
- Jamais d'arrêt d'urgence ni de coupure des moteurs dans « actions » : l'arrêt passe par la page.
- Si la demande sort de ton rôle (avis médical, juridique, contenu blessant), décline poliment en une phrase.
Réponds uniquement par un objet JSON : {"reponse": "…", "actions": [ … ]}"""


# ── Vocabulaire fermé du chien et du drone (mêmes types que web/drone/commande.js) ──
POSTURES_CHIEN = ("assis", "patte", "salut", "etirement")
ALLURES_CHIEN = ("joyeux", "craintif", "menacant", "fatigue", "curieux", "neutre")
TYPES_MOBILES = {
    "chien": ("lever", "coucher", "posture", "allure", "aller", "deplacer", "tourner", "regarder", "retour", "arreter"),
    "drone": ("decoller", "atterrir", "aller", "deplacer", "tourner", "regarder", "retour", "arreter"),
}
INTERDITS = ("urgence", "coupure", "couper", "go")


def vocabulaire_mobile(domaine: str, reperes: list[str]) -> dict[str, Any]:
    v: dict[str, Any] = {
        "aller": {"repere": reperes},
        "deplacer": {"avant": "mètres, -3 à 3 (négatif : reculer)", "droite": "mètres, -3 à 3 (négatif : gauche)"},
        "tourner": {"angle": "degrés, -360 à 360 (positif : vers la gauche)"},
        "regarder": {"cible": ["salle", *reperes, None]},
        "retour": {}, "arreter": {},
    }
    if domaine == "chien":
        v |= {"lever": {}, "coucher": {}, "posture": {"nom": list(POSTURES_CHIEN)}, "allure": {"nom": list(ALLURES_CHIEN)}}
    else:
        v["deplacer"]["haut"] = "mètres, -2 à 2"
        v |= {"decoller": {"hauteur": "mètres, 0,6 à 3 (facultatif)"}, "atterrir": {}}
    return v


def _borne(v: Any, a: float, b: float) -> float:
    x = float(v)
    if x != x:  # NaN
        raise ValueError("valeur non numérique")
    return max(a, min(b, x))


def valider_mobile(domaine: str, actions: Any, reperes: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Actions proposées pour le chien ou le drone : types du vocabulaire, bornes, repères existants."""
    ok: list[dict[str, Any]] = []
    rejets: list[dict[str, Any]] = []
    permis = TYPES_MOBILES[domaine]
    for a in actions if isinstance(actions, list) else []:
        if not isinstance(a, dict) or a.get("type") not in permis:
            motif = "interdit au modèle (l'arrêt passe par la page)" if isinstance(a, dict) and a.get("type") in INTERDITS \
                else "type d'action inconnu"
            rejets.append({"action": a, "motif": motif})
            continue
        t = a["type"]
        try:
            if t == "aller":
                if a.get("repere") not in reperes:
                    raise ValueError("repère inexistant")
                x = {"type": t, "repere": a["repere"]}
            elif t == "deplacer":
                x = {"type": t, "avant": round(_borne(a.get("avant", 0) or 0, -3, 3), 2),
                     "droite": round(_borne(a.get("droite", 0) or 0, -3, 3), 2)}
                if domaine == "drone":
                    x["haut"] = round(_borne(a.get("haut", 0) or 0, -2, 2), 2)
                if not any(x[k] for k in ("avant", "droite", "haut") if k in x):
                    raise ValueError("déplacement nul")
            elif t == "tourner":
                x = {"type": t, "angle": round(_borne(a.get("angle"), -360, 360), 1)}
            elif t == "regarder":
                c = a.get("cible")
                if c not in ("salle", None, *reperes):
                    raise ValueError("cible de regard inconnue")
                x = {"type": t, "cible": c}
            elif t == "posture":
                if a.get("nom") not in POSTURES_CHIEN:
                    raise ValueError("posture inconnue")
                x = {"type": t, "nom": a["nom"]}
            elif t == "allure":
                if a.get("nom") not in ALLURES_CHIEN:
                    raise ValueError("allure inconnue")
                x = {"type": t, "nom": a["nom"]}
            elif t == "decoller":
                x = {"type": t, "hauteur": round(_borne(a["hauteur"], 0.6, 3), 2) if a.get("hauteur") is not None else None}
            else:
                x = {"type": t}
        except (ValueError, TypeError, KeyError) as exc:
            rejets.append({"action": a, "motif": str(exc) or "valeur invalide"})
            continue
        ok.append(x)
    return ok[:8], rejets


def vocabulaire_robot() -> dict[str, Any]:
    S = avatar_mod.schema()
    return {"emotion": {"nom": S["emotions"], "intensite": "0 à 10"}, "geste": {"nom": S["gestes"]},
            "pose": {"nom": S["poses"]}, "regard": {"cible": S["regards"]},
            "deplacer": {"avant": "mètres, -3 à 3", "lateral": "mètres, -3 à 3"},
            "orienter": {"angle": "degrés, + vers la gauche", "relatif": True}}


TYPES_ROBOT = ("emotion", "geste", "pose", "regard", "deplacer", "orienter")


def valider_robot(actions: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    choisies, hors = [], []
    for a in actions if isinstance(actions, list) else []:
        (choisies if isinstance(a, dict) and a.get("type") in TYPES_ROBOT else hors).append(a)
    ok, rejets = avatar_mod.valider(choisies)
    return ok[:8], rejets + [{"action": a, "motif": "type non permis en dialogue"} for a in hors]


# ── Voie déterministe (aucun moteur disponible) ──
def _sans_accents(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def reponse_deterministe(domaine: str, texte: str) -> str:
    t = _sans_accents(texte)
    nom = NOMS[domaine]
    if re.search(r"\b(bonjour|salut|allo|bonsoir|coucou)\b", t):
        return f"Bonjour ! Je suis {nom} de Robo-Scène. Je vous écoute."
    if re.search(r"\b(qui es[- ]tu|tu es qui|comment t'appelles|ton nom)\b", t):
        return f"Je suis {nom} de Robo-Scène, une machine de théâtre pilotée par l'équipe."
    if re.search(r"\b(comment (ca|tu) va|ca va)\b", t):
        return "Tout va bien de mon côté, merci. Et vous ?"
    if re.search(r"\b(merci)\b", t):
        return "Avec plaisir."
    if re.search(r"\b(au revoir|bonne nuit|a bientot|a plus tard)\b", t):
        return "Au revoir, à bientôt sur le plateau."
    return ("Je n'ai pas de modèle de langage disponible pour converser en ce moment. "
            "Choisissez un moteur dans le panneau Dialogue, ou donnez-moi une commande.")


def _extraire(texte: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", texte or "", re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            if isinstance(d, dict):
                return d
        except json.JSONDecodeError:
            pass
    return {"reponse": re.sub(r"\s+", " ", texte or "").strip(), "actions": []}


def nettoyer_oral(t: str) -> str:
    """Texte prêt à dire : sans balisage ni émoticônes, au plus 600 caractères, coupé à une fin de phrase."""
    t = re.sub(r"[*_#`>]+", "", str(t or ""))
    t = re.sub(r"[\U0001F000-\U0001FAFF☀-➿]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > 600:
        coupe = max(t.rfind(c, 0, 600) for c in ".!?")
        t = t[: coupe + 1] if coupe > 200 else t[:600].rstrip() + "…"
    return t


class Dialogue:
    """Une conversation par machine, partagée par les pages qui l'affichent."""

    def __init__(self, service: Any):
        self.service = service
        self.memoire: dict[str, deque] = {d: deque(maxlen=TOURS_MEMOIRE) for d in DOMAINES}

    def oublier(self, domaine: str | None = None) -> None:
        for d in ([domaine] if domaine in DOMAINES else DOMAINES):
            self.memoire[d].clear()

    def consigne(self, domaine: str, reperes: list[str], contexte: str) -> str:
        voc = vocabulaire_robot() if domaine == "robot" else vocabulaire_mobile(domaine, reperes)
        return (PERSONAS[domaine] + "\n\n" + REGLES + "\n\nVocabulaire des actions (types et valeurs permis) : "
                + json.dumps(voc, ensure_ascii=False) + (f"\n\nSituation actuelle : {contexte}" if contexte else ""))

    async def repondre(self, domaine: str, texte: str, *, reperes: Any = None, contexte: Any = None) -> dict[str, Any]:
        if domaine not in DOMAINES:
            raise ValueError(f"machine inconnue : {domaine}")
        texte = re.sub(r"\s+", " ", str(texte or "")).strip()[:800]
        if not texte:
            raise ValueError("phrase vide")
        reperes = [str(r)[:60] for r in (reperes or []) if isinstance(r, str)][:60]
        contexte = str(contexte or "")[:600]
        mem = self.memoire[domaine]
        base = {"domaine": domaine, "texte": texte}
        if not self.service.disponible("rapide", domaine=domaine):
            rep = reponse_deterministe(domaine, texte)
            mem.append((texte, rep))
            return {**base, "reponse": rep, "actions": [], "rejets": [], "moteur": "déterministe", "trace": None,
                    "ecarts": []}
        historique = "\n".join(f"Personne : {q}\nToi : {r}" for q, r in mem)
        contenu = (f"Échanges précédents :\n{historique}\n\n" if historique else "") + f"Personne : {texte}"
        try:
            # température seule (jamais avec top_p) ; D03 appliqué par le service avant le choix du moteur
            r = await self.service.generer("rapide", self.consigne(domaine, reperes, contexte), contenu,
                                           temperature=0.7, max_tokens=500, json_attendu=True, domaine=domaine)
        except Exception as exc:  # refus de sensibilité, réseau, quota
            return {**base, "reponse": "Je ne peux pas répondre à cela pour le moment.", "actions": [], "rejets": [],
                    "moteur": "aucun", "trace": None, "ecarts": [], "erreur": f"{type(exc).__name__} : {str(exc)[:200]}"}
        d = _extraire(r.texte)
        rep = nettoyer_oral(d.get("reponse") or d.get("texte") or "")
        if not rep:
            rep = "Pardon, je n'ai pas de réponse claire."
        if domaine == "robot":
            ok, rejets = valider_robot(d.get("actions"))
        else:
            ok, rejets = valider_mobile(domaine, d.get("actions"), reperes)
        mem.append((texte, rep))
        return {**base, "reponse": rep, "actions": ok, "rejets": rejets,
                "moteur": r.modele_exact or r.modele_demande, "fournisseur": r.fournisseur, "si": r.systeme,
                "famille": r.famille, "ecarts": list(r.ecarts), "trace": {**r.trace(), "famille": r.famille}}
