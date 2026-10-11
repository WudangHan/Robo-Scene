"""Exécuteur à bibliothèque fermée, avec confirmation humaine obligatoire.

Règle (plan de prévention P2.1, §6.4) : un module d'IA peut seulement PROPOSER le nom
d'un geste de la bibliothèque ; l'exécution exige la confirmation de l'opérateur humain,
et le statut du geste doit autoriser la cible et la vitesse demandées (§6.5).
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from .bibliotheque import Geste, charger, valider

# Statut minimal exigé selon la cible et la vitesse
EXIGENCES = {
    ("sim", "lente"): "brouillon",
    ("sim", "pleine"): "brouillon",
    ("robot", "lente"): "valide_sim",
    ("robot", "pleine"): "valide",
}
ORDRE = ["brouillon", "valide_sim", "valide_robot_lent", "valide"]
FACTEUR_LENT = 0.5  # vitesse réduite des répétitions (P2.1, §6.5, étape 2)


@dataclass
class Proposition:
    """Ce qu'un module d'IA ou un humain peut produire : un nom, jamais une commande."""
    geste: str
    source: str           # ex. « P1/SI-01 », « operateur »
    motif: str = ""
    horodatage: str = ""


class RefusExecution(Exception):
    pass


class ExecuteurFerme:
    def __init__(self, chemin_bibliotheque=None, journal="journal_gestes.jsonl", chemin_sequences=None):
        self.gestes: dict[str, Geste] = charger(chemin_bibliotheque)
        # Séquences (P2.4) : enchaînements de gestes de la bibliothèque, traités comme des gestes
        # composites ; leur statut effectif est le plus bas de ceux de leurs gestes.
        from .sequenceur import charger_sequences
        self.sequences = charger_sequences(chemin_sequences, self.gestes)
        self.gestes.update(self.sequences)
        self.journal = Path(journal)
        # Toute la bibliothèque doit être conforme avant toute exécution.
        erreurs = {n: valider(g) for n, g in self.gestes.items()}
        self.non_conformes = {n: e for n, e in erreurs.items() if e}

    # ------------------------------------------------------------------ journal
    def _journaliser(self, evenement: str, **donnees):
        ligne = {"horodatage": datetime.now(timezone.utc).isoformat(), "evenement": evenement, **donnees}
        with open(self.journal, "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")

    # --------------------------------------------------------------- proposer
    def proposer(self, nom: str, source: str, motif: str = "") -> Proposition:
        """Accepte une proposition SEULEMENT si le nom appartient à la bibliothèque."""
        if nom not in self.gestes:
            self._journaliser("proposition_refusee", geste=nom, source=source, raison="hors bibliothèque")
            raise RefusExecution(f"« {nom} » n'appartient pas à la bibliothèque fermée")
        p = Proposition(nom, source, motif, datetime.now(timezone.utc).isoformat())
        self._journaliser("proposition", **asdict(p))
        return p

    # --------------------------------------------------------------- executer
    def autoriser(self, p: Proposition, cible: str, vitesse: str) -> Geste:
        g = self.gestes[p.geste]
        if p.geste in self.non_conformes:
            raise RefusExecution(f"{p.geste} : non conforme aux limites ({self.non_conformes[p.geste][0]})")
        requis = EXIGENCES[(cible, vitesse)]
        if ORDRE.index(g.statut) < ORDRE.index(requis):
            raise RefusExecution(f"{p.geste} : statut « {g.statut} » insuffisant pour {cible}/{vitesse} "
                                 f"(requis : « {requis} »)")
        return g

    def executer(self, p: Proposition, *, confirmation_operateur: bool, cible: str = "sim",
                 vitesse: str = "lente", mini=None):
        """Joue le geste sur le robot (ou la simulation du daemon) via le SDK Reachy Mini.

        `mini` : instance `reachy_mini.ReachyMini` déjà connectée (réelle ou daemon --sim).
        """
        if not confirmation_operateur:
            self._journaliser("execution_refusee", geste=p.geste, raison="pas de confirmation humaine")
            raise RefusExecution("Confirmation de l'opérateur requise")
        g = self.autoriser(p, cible, vitesse)
        if mini is None:
            raise RefusExecution("Aucune connexion au robot ou au simulateur")
        from reachy_mini.utils import create_head_pose  # import tardif : SDK facultatif pour les tests

        facteur = FACTEUR_LENT if vitesse == "lente" else 1.0
        self._journaliser("execution_debut", geste=g.nom, statut=g.statut, cible=cible, vitesse=vitesse,
                          source=p.source)
        try:
            for k in g.images_cles:
                t = k.tete
                mini.goto_target(
                    head=create_head_pose(x=t["x"], y=t["y"], z=t["z"], roll=t["roll"], pitch=t["pitch"],
                                          yaw=t["yaw"], mm=True, degrees=True),
                    antennas=[math.radians(k.antennes[0]), math.radians(k.antennes[1])],
                    body_yaw=math.radians(k.body_yaw),
                    duration=k.duree / facteur,
                )
        except Exception as e:  # tout incident est consigné (G.5 : 48 h)
            self._journaliser("execution_interrompue", geste=g.nom, erreur=str(e))
            raise
        self._journaliser("execution_fin", geste=g.nom)
        time.sleep(0.05)
