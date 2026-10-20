"""Agent d'interaction en langage naturel, toujours supervisé.

L'agent ne commande jamais le robot directement : il formule une PROPOSITION (action + paramètres +
confiance + justification) que le contrôleur soumet ensuite à la règle de séance, à la couche de sécurité,
puis à l'opératrice.

Règle de séance (décision du 11 octobre 2026, conforme à la politique d'IA G.5 et au plan P2.1, §6.4) :
* « bibliotheque_fermee » (par défaut) : l'agent ne peut proposer que le NOM d'une séquence ou d'un geste
  validé, le retour au repos, ou rien ; il ne voit ni angle ni vitesse ;
* « angles_s04 » : l'agent peut aussi proposer des angles et des déplacements, validés par l'opératrice —
  mode réservé aux séances incarnées S04 déclarées dans [protocole] type.

Moteurs : le service unique des modèles (Claude Sonnet ou GPT Luna, version la plus récente fixée au début
de la séance) ou, sans clé API, un analyseur de règles déterministe.

La confiance retenue reste min(confiance déclarée, confiance de vérification) : une auto-évaluation d'un
modèle de langage n'est pas une probabilité calibrée.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

SYSTEME_FERME = """Tu es l'agent de mouvement d'un robot de scène (projet ROBO-SCÈNE).
Règle de la bibliothèque fermée : tu ne peux proposer que le NOM d'une séquence ou d'un geste de la liste
fournie, le retour au repos, ou rien. Tu ne donnes jamais d'angle, de vitesse ni de durée.
Réponds UNIQUEMENT par un objet JSON :
{"action": "sequence" | "repos" | "aucune", "parametres": {"nom": "nom exact"} ou {},
 "confiance": nombre entre 0 et 1, "justification": "une phrase en français"}
Si la consigne est ambiguë, dangereuse ou ne correspond à aucun nom de la liste : "aucune"."""

SYSTEME_ANGLES = """Tu es l'agent de mouvement d'un robot de scène (projet ROBO-SCÈNE, séance incarnée S04).
Tu reçois une consigne en français de l'opératrice et l'état du robot.
Tu réponds UNIQUEMENT par un objet JSON, sans texte autour :
{"action": "articulations" | "propulsion" | "sequence" | "repos" | "aucune",
 "parametres": {...},
 "confiance": nombre entre 0 et 1,
 "justification": "une phrase en français"}
- "articulations" : parametres = {"deg": [un angle par articulation, ou null pour ne pas bouger], "ms": durée}
- "propulsion" : parametres = {"g": -1..1, "d": -1..1, "ms": durée avant arrêt (max 3000)}
- "sequence" : parametres = {"nom": nom exact d'une séquence disponible}
- "repos" : parametres = {}
- "aucune" : si la consigne est ambiguë, dangereuse ou hors capacités.
Respecte les limites articulaires fournies. En cas de doute, baisse la confiance.
Une personne peut se trouver près du robot : privilégie des mouvements lents."""

ACTIONS_FERMEES = {"sequence", "repos", "aucune"}


def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def _extraire_json(texte: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", texte, re.S)
    if not m:
        raise ValueError("Aucun objet JSON dans la réponse")
    return json.loads(m.group(0))


class Agent:
    def __init__(self, cfg: dict[str, Any], noms: list[str], service=None):
        self.cfg = cfg
        self.noms = noms
        self.service = service if cfg.get("active", True) else None

    @property
    def moteur(self) -> str:
        if self.service is not None and self.service.disponible("commande", domaine="robot"):
            return self.service.moteur("commande", domaine="robot")
        return "regles"

    async def proposer(self, consigne: str, etat: dict[str, Any], limites: dict[str, Any],
                       sequences: list[str], regle: str = "bibliotheque_fermee") -> dict[str, Any]:
        ferme = regle != "angles_s04"
        if ferme:
            contexte: dict[str, Any] = {"sequences_et_gestes_disponibles": sequences}
        else:
            contexte = {
                "articulations": [
                    {"nom": n, "angle_actuel": (etat.get("deg") or [None] * len(self.noms))[i],
                     "min": limites["min_deg"][i], "max": limites["max_deg"][i], "repos": limites["repos"][i]}
                    for i, n in enumerate(self.noms)],
                "propulsion_disponible": limites["propulsion_active"],
                "distance_obstacle_cm": etat.get("dist"),
                "sequences_disponibles": sequences,
            }
        prompt = f"Consigne : {consigne}\n\nContexte :\n{json.dumps(contexte, ensure_ascii=False)}"
        trace = None
        if self.moteur != "regles":
            try:
                r = await self.service.generer("commande", SYSTEME_FERME if ferme else SYSTEME_ANGLES, prompt,
                                               temperature=float(self.cfg.get("temperature", 0.2)),
                                               max_tokens=int(self.cfg.get("max_tokens", 600)), domaine="robot")
                prop = _extraire_json(r.texte)
                prop["moteur"] = f"{r.fournisseur}:{r.modele_exact}"
                prop["brut"] = r.texte
                trace = r.trace()
            except Exception as exc:  # réseau, quota, refus de sensibilité, JSON invalide…
                prop = self._regles(consigne, limites, sequences, ferme)
                prop["moteur"] = "regles (repli)"
                prop["justification"] += f" [Repli : {type(exc).__name__}]"
        else:
            prop = self._regles(consigne, limites, sequences, ferme)
            prop["moteur"] = "regles"
        prop["prompt"] = prompt
        prop["regle"] = regle
        prop["trace_modele"] = trace or {"systeme": "REGLES", "version_modele": "regles-1.0", "fournisseur": "local",
                                         "parametres_demandes": {}, "parametres_appliques": {},
                                         "ecarts_parametres": [], "jetons_entree": 0, "jetons_sortie": 0}
        prop.setdefault("parametres", {})
        try:
            prop["confiance"] = max(0.0, min(1.0, float(prop.get("confiance", 0))))
        except (TypeError, ValueError):
            prop["confiance"] = 0.0
        return prop

    # ── Analyseur de secours : consignes simples, confiance prudente ──
    def _regles(self, consigne: str, limites: dict, sequences: list[str], ferme: bool = True) -> dict[str, Any]:
        c = _sans_accents(consigne)
        n = len(self.noms)
        for s in sequences:
            if _sans_accents(s) in c:
                return {"action": "sequence", "parametres": {"nom": s}, "confiance": 0.9,
                        "justification": f"La consigne nomme la séquence « {s} »."}
        if re.search(r"\b(repos|neutre|initial)\b", c):
            return {"action": "repos", "parametres": {}, "confiance": 0.9,
                    "justification": "Retour à la position de repos."}
        if re.search(r"\b(stop|arrete|arret|immobile)\b", c):
            return {"action": "propulsion", "parametres": {"g": 0, "d": 0, "ms": 0},
                    "confiance": 0.95, "justification": "Consigne d'arrêt."}
        if limites.get("propulsion_active"):
            if re.search(r"\b(avance|en avant)\b", c):
                return {"action": "propulsion", "parametres": {"g": 0.3, "d": 0.3, "ms": 1500},
                        "confiance": 0.8, "justification": "Avance lente, 1,5 s."}
            if re.search(r"\b(recule|en arriere)\b", c):
                return {"action": "propulsion", "parametres": {"g": -0.3, "d": -0.3, "ms": 1500},
                        "confiance": 0.75, "justification": "Recul lent, 1,5 s (vision arrière absente)."}
            if "gauche" in c and "tourne" in c:
                return {"action": "propulsion", "parametres": {"g": -0.3, "d": 0.3, "ms": 800},
                        "confiance": 0.8, "justification": "Rotation sur place vers la gauche."}
            if "droite" in c and "tourne" in c:
                return {"action": "propulsion", "parametres": {"g": 0.3, "d": -0.3, "ms": 800},
                        "confiance": 0.8, "justification": "Rotation sur place vers la droite."}
        for i, nom in enumerate(self.noms):
            if _sans_accents(nom) in c:
                deg = [None] * n
                if re.search(r"\b(leve|monte|haut)\b", c):
                    deg[i] = limites["max_deg"][i] - 10
                elif re.search(r"\b(baisse|descend|bas)\b", c):
                    deg[i] = limites["min_deg"][i] + 10
                else:
                    continue
                return {"action": "articulations", "parametres": {"deg": deg, "ms": 1200},
                        "confiance": 0.8, "justification": f"Mouvement de l'articulation « {nom} »."}
        return {"action": "aucune", "parametres": {}, "confiance": 0.0,
                "justification": "Consigne non reconnue par l'analyseur de règles."}
