"""Agent d'interaction en langage naturel, toujours supervisé.

L'agent ne commande jamais le robot directement : il formule une
PROPOSITION (action + paramètres + confiance + justification) que le
contrôleur soumet ensuite à la couche de sécurité, puis à l'opératrice.

Deux moteurs :
  * « claude » : API Anthropic (variable d'environnement ANTHROPIC_API_KEY) ;
  * « regles » : analyseur déterministe de secours, sans réseau.

La confiance retenue est min(confiance déclarée, confiance de vérification) :
une auto-évaluation d'un modèle de langage n'est pas une probabilité calibrée,
elle ne doit donc jamais suffire seule à autoriser un mouvement.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any

SYSTEME = """Tu es l'agent de mouvement d'un robot de scène (projet ROBO-SCÈNE).
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


def _sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower())
                   if unicodedata.category(c) != "Mn")


def _extraire_json(texte: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", texte, re.S)
    if not m:
        raise ValueError("Aucun objet JSON dans la réponse")
    return json.loads(m.group(0))


class Agent:
    def __init__(self, cfg: dict[str, Any], noms: list[str]):
        self.cfg = cfg
        self.noms = noms
        self.client = None
        self.moteur = "regles"
        if cfg.get("active", True) and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                from anthropic import AsyncAnthropic
                self.client = AsyncAnthropic()
                self.moteur = "claude"
            except ImportError:
                pass

    async def proposer(self, consigne: str, etat: dict[str, Any],
                       limites: dict[str, Any], sequences: list[str]) -> dict[str, Any]:
        contexte = {
            "articulations": [
                {"nom": n, "angle_actuel": etat.get("deg", [None] * len(self.noms))[i],
                 "min": limites["min_deg"][i], "max": limites["max_deg"][i],
                 "repos": limites["repos"][i]}
                for i, n in enumerate(self.noms)
            ],
            "propulsion_disponible": limites["propulsion_active"],
            "distance_obstacle_cm": etat.get("dist"),
            "sequences_disponibles": sequences,
        }
        prompt = f"Consigne : {consigne}\n\nÉtat du robot :\n{json.dumps(contexte, ensure_ascii=False)}"
        if self.moteur == "claude":
            try:
                rep = await self.client.messages.create(
                    model=self.cfg.get("modele", "claude-sonnet-5-5"),
                    max_tokens=int(self.cfg.get("max_tokens", 600)),
                    temperature=float(self.cfg.get("temperature", 0.2)),
                    system=SYSTEME,
                    messages=[{"role": "user", "content": prompt}],
                )
                texte = "".join(b.text for b in rep.content if getattr(b, "type", "") == "text")
                prop = _extraire_json(texte)
                prop["moteur"] = f"claude:{self.cfg.get('modele')}"
                prop["brut"] = texte
            except Exception as exc:  # réseau, quota, JSON invalide…
                prop = self._regles(consigne, limites, sequences)
                prop["moteur"] = "regles (repli)"
                prop["justification"] += f" [Repli : {type(exc).__name__}]"
        else:
            prop = self._regles(consigne, limites, sequences)
            prop["moteur"] = "regles"
        prop["prompt"] = prompt
        prop.setdefault("parametres", {})
        try:
            prop["confiance"] = max(0.0, min(1.0, float(prop.get("confiance", 0))))
        except (TypeError, ValueError):
            prop["confiance"] = 0.0
        return prop

    # ── Analyseur de secours : consignes simples, confiance prudente ──
    def _regles(self, consigne: str, limites: dict, sequences: list[str]) -> dict[str, Any]:
        c = _sans_accents(consigne)
        n = len(self.noms)
        for s in sequences:
            if _sans_accents(s) in c:
                return {"action": "sequence", "parametres": {"nom": s}, "confiance": 0.9,
                        "justification": f"La consigne nomme la séquence « {s} »."}
        if re.search(r"\b(stop|arrete|arret|immobile)\b", c):
            return {"action": "propulsion", "parametres": {"g": 0, "d": 0, "ms": 0},
                    "confiance": 0.95, "justification": "Consigne d'arrêt."}
        if re.search(r"\b(repos|neutre|initial)\b", c):
            return {"action": "repos", "parametres": {}, "confiance": 0.9,
                    "justification": "Retour à la position de repos."}
        if limites["propulsion_active"]:
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
        # « lève / baisse <articulation> »
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
                        "confiance": 0.8,
                        "justification": f"Mouvement de l'articulation « {nom} »."}
        return {"action": "aucune", "parametres": {}, "confiance": 0.0,
                "justification": "Consigne non reconnue par l'analyseur de règles."}
