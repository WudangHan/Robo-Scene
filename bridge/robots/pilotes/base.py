"""Interface commune de tous les pilotes : le langage de commande unifié (PROTOCOLE.md, v2).

Du pont vers le robot : {"t": "hello" | "hb" | "servos" (deg, ms) | "drive" (l, r) | "estop" | "reset"
                         | "geste" (nom) | "dire" (texte)}
Du robot vers le pont : {"t": "info" | "tel" | "err" | "lien"}

Un pilote traduit ces messages dans le protocole natif du robot ; le contrôleur et la couche de sécurité,
eux, ne voient jamais que le langage unifié : toute commande, quel que soit le robot, a déjà été bornée et
ralentie par la couche de sécurité avant d'atteindre un pilote.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from ..description import DescriptionRobot


class Pilote:
    type = "abstrait"

    def __init__(self, desc: DescriptionRobot):
        self.desc = desc
        self.nom = self.type
        self._file: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.t0 = time.monotonic()

    async def ouvrir(self) -> None: ...
    async def envoyer(self, msg: dict[str, Any]) -> None: ...
    async def fermer(self) -> None: ...

    async def recevoir(self) -> dict[str, Any]:
        return await self._file.get()

    def pousser(self, msg: dict[str, Any]) -> None:
        self._file.put_nowait(msg)

    def pousser_depuis_fil(self, loop: asyncio.AbstractEventLoop, msg: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(self._file.put_nowait, msg)

    def info(self, **extra: Any) -> dict[str, Any]:
        return {"t": "info", "nom": self.desc.nom, "fw": f"pilote-{self.type}", "servos": len(self.desc.articulations),
                "propulsion": self.desc.propulsion, "articulations": self.desc.noms, **extra}

    def ms(self) -> int:
        return int((time.monotonic() - self.t0) * 1000)

    def refuser(self, quoi: str) -> None:
        self.pousser({"t": "err", "msg": f"{quoi} : non pris en charge par le pilote {self.type}"})
