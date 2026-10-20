"""Flotte de robots connectés : un état, une couche de sécurité et une bibliothèque par robot.

L'arrêt d'urgence est GLOBAL : il fige tous les robots à la fois (une seule scène, un seul geste d'arrêt) ;
le réarmement, action volontaire et distincte (ISO 13850), vaut lui aussi pour toute la flotte.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from ..securite import Limites, Securite
from . import pilotes
from .bibliotheque import BibliothequeJSON, BibliothequeP2
from .description import DescriptionRobot


class RobotConnecte:
    def __init__(self, desc: DescriptionRobot, dossier_sequences: Path, dossier_donnees: Path | None = None):
        self.desc = desc
        self.limites = Limites(min_deg=desc.min_deg, max_deg=desc.max_deg, repos=desc.repos,
                               vitesse_max_deg_s=desc.vitesse_max_deg_s, propulsion_max=desc.propulsion_max,
                               propulsion_active=desc.propulsion)
        self.securite = Securite(self.limites)
        self.etat: dict[str, Any] = {"deg": list(desc.repos), "drive": [0, 0]}
        self.lien = "deconnecte"
        self.derniere_tel = 0.0
        self.info: dict[str, Any] = {}
        self.pilote = None
        self.propulsion_jusqua = 0.0
        self.seq_tache: asyncio.Task | None = None
        self.seq_nom: str | None = None
        self.geste_natif: str | None = None     # geste natif en cours (événements du robot)
        self.alerte_batt = False
        self.tache: asyncio.Task | None = None
        self.biblio = (BibliothequeP2() if desc.bibliotheque == "p2"
                       else BibliothequeJSON(dossier_sequences, len(desc.articulations),
                                             (Path(dossier_donnees) / "essais_sequences" / f"{desc.id}.jsonl")
                                             if dossier_donnees else None))

    @property
    def id(self) -> str:
        return self.desc.id

    @property
    def reel(self) -> bool:
        """Vrai si le robot est matériel (exigences de statut de P2.1, §6.5)."""
        return not self.desc.simulation

    def creer_pilote(self):
        if self.desc.simulation:
            from dataclasses import replace
            return pilotes.creer(replace(self.desc, pilote="ligne_json", connexion={"mode": "sim"}))
        return pilotes.creer(self.desc)

    def resume(self) -> dict[str, Any]:
        return {**self.desc.resume(), "lien": self.lien, "arret": self.securite.arret_urgence,
                "sequence": self.seq_nom, "geste_natif": self.geste_natif, "vbat": self.etat.get("vbat"),
                "pilote_effectif": "simulation" if self.desc.simulation else self.desc.pilote}

    async def boucle(self, sur_message: Callable[["RobotConnecte", dict], Awaitable[None]],
                     log: Callable[..., Awaitable[None]]) -> None:
        """Connexion, réception, reconnexion après 3 s ; aucune commande ne passe si le lien est rompu."""
        while True:
            self.pilote = None
            try:
                self.pilote = self.creer_pilote()
                await self.pilote.ouvrir()
                self.lien = "connecte"
                await log(f"[{self.id}] Lien établi ({'simulation' if self.desc.simulation else self.desc.pilote})")
                await self.pilote.envoyer({"t": "hello"})
                while True:
                    msg = await self.pilote.recevoir()
                    if msg.get("t") == "lien" and msg.get("etat") == "perdu":
                        raise ConnectionError(msg.get("msg", "lien perdu"))
                    await sur_message(self, msg)
            except asyncio.CancelledError:
                if self.pilote:
                    try:
                        await self.pilote.fermer()
                    except Exception:
                        pass
                raise
            except Exception as exc:
                self.lien = "deconnecte"
                await log(f"[{self.id}] Lien indisponible : {exc} — nouvel essai dans 3 s", "alerte")
                try:
                    if self.pilote:
                        await self.pilote.fermer()
                except Exception:
                    pass
                await asyncio.sleep(3)

    def demarrer(self, sur_message, log) -> None:
        self.tache = asyncio.create_task(self.boucle(sur_message, log))

    async def arreter(self) -> None:
        if self.tache:
            self.tache.cancel()
            try:
                await self.tache
            except (asyncio.CancelledError, Exception):
                pass
            self.tache = None
        self.lien = "deconnecte"

    async def envoyer(self, msg: dict[str, Any]) -> None:
        if self.lien != "connecte" or self.pilote is None:
            from ..securite import CommandeRefusee
            raise CommandeRefusee(f"Robot {self.id} non connecté")
        await self.pilote.envoyer(msg)

    def muet(self, maintenant: float) -> bool:
        return self.lien == "connecte" and self.derniere_tel and maintenant - self.derniere_tel > 1.0


def maintenant() -> float:
    return time.monotonic()
