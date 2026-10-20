"""Pilote « ligne JSON » : le protocole unifié tel quel, un objet JSON par ligne.

Modes : sim (robot simulé), serie (USB), tcp (Wi-Fi, ESP32 en point d'accès), udp, websocket (robot serveur
WebSocket, par exemple un Raspberry Pi ou un ESP32 avec bibliothèque WebSocket). C'est le pilote du robot
maison ESP32 et de tout microcontrôleur programmé avec le SDK Arduino ou C++ (sdk/).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from ... import transports
from .base import Pilote


def _images_importees(desc, nom: str) -> list | None:
    """Images d'un geste natif importé dans la bibliothèque (sequences/<robot>/hw_<nom>.json), pour la simulation."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[3] / "sequences" / (desc.sequences or desc.id) / f"hw_{nom}.json"
    try:
        images = json.loads(p.read_text(encoding="utf-8"))["images"]
    except (OSError, ValueError, KeyError):
        return None
    return images if all(len(i.get("deg", [])) == len(desc.articulations) for i in images) else None


class PiloteLigneJSON(Pilote):
    type = "ligne_json"

    def __init__(self, desc):
        super().__init__(desc)
        c = desc.connexion
        mode = c.get("mode", "sim")
        if desc.simulation:
            mode = "sim"
        self.mode = mode
        if mode == "serie":
            self.t = transports.TransportSerie(c.get("port_serie") or c.get("port"), int(c.get("debit", 115200)))
        elif mode == "tcp":
            self.t = transports.TransportTCP(c.get("hote", "192.168.4.1"), int(c.get("port", 3333)))
        elif mode == "udp":
            self.t = TransportUDP(c.get("hote", "127.0.0.1"), int(c.get("port", 3334)), int(c.get("port_local", 0)))
        elif mode == "websocket":
            self.t = TransportWebSocket(c["url"])
        else:
            self.t = transports.TransportSimule(len(desc.articulations), desc.repos, desc.propulsion,
                                                desc.chien_de_garde_ms, gestes_natifs=desc.gestes_natifs,
                                                images_geste=lambda nom: _images_importees(desc, nom),
                                                vbat=12.6 if (desc.batterie_min_v or 0) > 8.2 else 8.2)   # LiPo 3S (AiNex, TonyPi) ou 2S
        self.nom = mode

    async def ouvrir(self) -> None:
        await self.t.ouvrir()

    async def envoyer(self, msg: dict[str, Any]) -> None:
        await self.t.envoyer(msg)

    async def recevoir(self) -> dict[str, Any]:
        return await self.t.recevoir()

    async def fermer(self) -> None:
        await self.t.fermer()


class TransportUDP(transports.Transport):
    nom = "udp"

    class _Protocole(asyncio.DatagramProtocol):
        def __init__(self, file):
            self.file = file

        def datagram_received(self, data, addr):
            for ligne in data.splitlines():
                m = transports._decoder(ligne)
                if m is not None:
                    self.file.put_nowait(m)

    def __init__(self, hote: str, port: int, port_local: int = 0):
        self.hote, self.port, self.port_local = hote, port, port_local
        self._file: asyncio.Queue = asyncio.Queue()
        self._tr = None

    async def ouvrir(self) -> None:
        loop = asyncio.get_running_loop()
        self._tr, _ = await loop.create_datagram_endpoint(
            lambda: self._Protocole(self._file), local_addr=("0.0.0.0", self.port_local),
            remote_addr=(self.hote, self.port))

    async def envoyer(self, msg: dict[str, Any]) -> None:
        self._tr.sendto((json.dumps(msg, separators=(",", ":")) + "\n").encode())

    async def recevoir(self) -> dict[str, Any]:
        return await self._file.get()

    async def fermer(self) -> None:
        if self._tr:
            self._tr.close()


class TransportWebSocket(transports.Transport):
    nom = "websocket"

    def __init__(self, url: str):
        self.url = url
        self._session = None
        self._ws = None

    async def ouvrir(self) -> None:
        import aiohttp
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(self.url, heartbeat=5, timeout=5)

    async def envoyer(self, msg: dict[str, Any]) -> None:
        await self._ws.send_str(json.dumps(msg, separators=(",", ":")))

    async def recevoir(self) -> dict[str, Any]:
        import aiohttp
        while True:
            m = await self._ws.receive()
            if m.type == aiohttp.WSMsgType.TEXT:
                for ligne in m.data.splitlines():
                    d = transports._decoder(ligne)
                    if d is not None:
                        return d
            elif m.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                return {"t": "lien", "etat": "perdu", "msg": "WebSocket fermé"}

    async def fermer(self) -> None:
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
