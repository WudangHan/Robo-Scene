"""Aucune décision exclusivement automatisée concernant une personne (G-05).

Fondement : article 12.1 de la Loi sur la protection des renseignements personnels dans le secteur privé
(Québec) — une personne visée par une décision fondée exclusivement sur un traitement automatisé doit en être
informée, peut demander des explications et une révision ; une intervention humaine déterminante écarte ces
obligations particulières (Caron, Raymond Chabot Grant Thornton, 2024).

La plateforme ne prend donc aucune décision sur une personne : tout ce qu'un système produit à son sujet
(classement, retour de jeu, sélection de candidatures, attribution de rôle) n'est qu'une PROPOSITION, sans effet
tant qu'une personne nommée ne l'a pas validée ou modifiée, avec motif. Le journal conserve les deux.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class DecisionNonValidee(PermissionError):
    pass


class Decisions:
    def __init__(self, fichier: Path):
        self.fichier = Path(fichier)
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        self._verrou = threading.Lock()

    def _lire(self) -> list[dict[str, Any]]:
        if not self.fichier.exists():
            return []
        return [json.loads(l) for l in self.fichier.read_text(encoding="utf-8").splitlines() if l.strip()]

    def _ajouter(self, d: dict[str, Any]) -> None:
        with self._verrou, self.fichier.open("a", encoding="utf-8") as f:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    def proposer(self, *, objet: str, personne: str, recommandation: str, source: str,
                 explication: str = "") -> dict[str, Any]:
        d = {"type": "proposition", "id": f"DP-{len(self._lire()) + 1:05d}",
             "date": datetime.now().astimezone().isoformat(timespec="seconds"), "objet": objet,
             "personne": personne, "recommandation": recommandation, "source": source,
             "explication": explication}
        self._ajouter(d)
        return d

    def valider(self, pid: str, *, validateur: str, decision: str, motif: str) -> dict[str, Any]:
        if not (validateur.strip() and motif.strip()):
            raise ValueError("La validation exige la personne qui décide et un motif")
        if not any(x["id"] == pid and x["type"] == "proposition" for x in self._lire()):
            raise KeyError(pid)
        d = {"type": "validation", "id": pid, "date": datetime.now().astimezone().isoformat(timespec="seconds"),
             "validateur": validateur, "decision": decision, "motif": motif}
        self._ajouter(d)
        return d

    def decision_effective(self, pid: str) -> dict[str, Any]:
        """Renvoie la décision humaine ; refuse si la proposition n'a pas été validée."""
        vals = [x for x in self._lire() if x["id"] == pid and x["type"] == "validation"]
        if not vals:
            raise DecisionNonValidee(f"{pid} : aucune validation humaine — la proposition reste sans effet (G-05)")
        return vals[-1]

    def en_attente(self) -> list[dict[str, Any]]:
        lignes = self._lire()
        valides = {x["id"] for x in lignes if x["type"] == "validation"}
        return [x for x in lignes if x["type"] == "proposition" and x["id"] not in valides]
