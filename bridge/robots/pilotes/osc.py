"""Pilote OSC (Open Sound Control) : pour les robots et dispositifs pilotés depuis des outils de scène
(Max, Pure Data, TouchDesigner, Isadora, QLab) ou des microcontrôleurs OSC.

Adresses envoyées : /robot/servos <ms> <deg…> ; /robot/drive <l> <r> ; /robot/estop ; /robot/reset ;
/robot/hb ; /robot/geste <nom> ; /robot/dire <texte>.
Adresses écoutées (port local) : /robot/tel <estop 0|1> <vbat> <dist> <deg…> ; /robot/info <nom> <fw> <n>.
"""
from __future__ import annotations

import asyncio
from typing import Any

from .base import Pilote


class PiloteOSC(Pilote):
    type = "osc"

    def __init__(self, desc):
        super().__init__(desc)
        c = desc.connexion
        self.hote, self.port = c.get("hote", "127.0.0.1"), int(c.get("port", 9100))
        self.port_local = int(c.get("port_local", 9101))
        self._client = None
        self._serveur = None

    async def ouvrir(self) -> None:
        from pythonosc.dispatcher import Dispatcher
        from pythonosc.osc_server import AsyncIOOSCUDPServer
        from pythonosc.udp_client import SimpleUDPClient
        self._client = SimpleUDPClient(self.hote, self.port)
        d = Dispatcher()

        def tel(_adr, *args):
            if len(args) < 3:
                return
            # OSC transporte des flottants simple précision : valeurs arrondies (convention : −1 = absent)
            self.pousser({"t": "tel", "ms": self.ms(), "estop": bool(args[0]),
                          "vbat": round(float(args[1]), 2) if float(args[1]) >= 0 else None,
                          "dist": round(float(args[2]), 1) if float(args[2]) >= 0 else None,
                          "deg": [round(float(x), 2) for x in args[3:]], "drive": [0, 0]})

        def info(_adr, *args):
            self.pousser(self.info(nom_robot=args[0] if args else self.desc.nom))

        d.map("/robot/tel", tel)
        d.map("/robot/info", info)
        self._serveur = AsyncIOOSCUDPServer(("0.0.0.0", self.port_local), d, asyncio.get_running_loop())
        self._transport, _ = await self._serveur.create_serve_endpoint()
        self._client.send_message("/robot/hello", [])
        self.pousser(self.info(osc=f"{self.hote}:{self.port}"))

    async def envoyer(self, msg: dict[str, Any]) -> None:
        t = msg.get("t")
        if t == "servos":
            self._client.send_message("/robot/servos", [int(msg.get("ms", 0)), *[float(x) for x in msg["deg"]]])
        elif t == "drive":
            self._client.send_message("/robot/drive", [float(msg.get("l", 0)), float(msg.get("r", 0))])
        elif t in ("estop", "reset", "hb", "hello"):
            self._client.send_message(f"/robot/{t}", [])
        elif t == "geste":
            self._client.send_message("/robot/geste", [str(msg.get("nom", ""))])
        elif t == "dire":
            self._client.send_message("/robot/dire", [str(msg.get("texte", ""))])

    async def fermer(self) -> None:
        if self._serveur is not None:
            self._transport.close()
