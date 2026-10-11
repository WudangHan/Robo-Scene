"""Pilote HTTP générique : pour un robot qui expose une interface REST.

Le profil décrit, pour chaque commande unifiée, une requête : méthode, chemin et gabarit de corps JSON dans
lequel {deg}, {deg0}…{degN}, {ms}, {l}, {r}, {nom} sont remplacés. La télémétrie est lue par sondage d'un
chemin GET et extraite par des pointeurs JSON (RFC 6901).

Exemple ([connexion] d'un profil) :
    url = "http://robot.local:8000"
    servos = {methode = "POST", chemin = "/api/joints", corps = '{"positions": {deg}, "duration_ms": {ms}}'}
    estop  = {methode = "POST", chemin = "/api/stop", corps = '{}'}
    telemetrie = {chemin = "/api/state", deg = "/joints/positions", vbat = "/battery/voltage", periode_s = 0.2}
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from .base import Pilote


def pointeur(doc: Any, p: str) -> Any:
    if not p:
        return doc
    for morceau in p.lstrip("/").split("/"):
        morceau = morceau.replace("~1", "/").replace("~0", "~")
        doc = doc[int(morceau)] if isinstance(doc, list) else doc[morceau]
    return doc


def remplir(gabarit: str, valeurs: dict[str, Any]) -> Any:
    texte = gabarit
    for k, v in valeurs.items():
        texte = texte.replace("{" + k + "}", json.dumps(v))
    return json.loads(texte)


class PiloteHTTP(Pilote):
    type = "http"

    def __init__(self, desc, session=None):
        super().__init__(desc)
        self.c = desc.connexion
        self.url = self.c["url"].rstrip("/")
        self._session = session
        self._sondage: asyncio.Task | None = None
        self._estop = False

    async def ouvrir(self) -> None:
        if self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3))
        self.pousser(self.info(url=self.url))
        if self.c.get("telemetrie"):
            self._sondage = asyncio.create_task(self._sonder())

    async def _requete(self, spec: dict[str, Any], valeurs: dict[str, Any]) -> None:
        corps = remplir(spec.get("corps", "{}"), valeurs) if spec.get("corps") else None
        async with self._session.request(spec.get("methode", "POST"), self.url + spec["chemin"], json=corps) as r:
            if r.status >= 400:
                self.pousser({"t": "err", "msg": f"HTTP {r.status} sur {spec['chemin']}"})

    async def _sonder(self) -> None:
        t = self.c["telemetrie"]
        while True:
            try:
                async with self._session.get(self.url + t["chemin"]) as r:
                    d = await r.json(content_type=None)
                tel = {"t": "tel", "ms": self.ms(), "drive": [0, 0], "estop": self._estop}
                for champ in ("deg", "vbat", "dist"):
                    if t.get(champ):
                        try:
                            tel[champ] = pointeur(d, t[champ])
                        except (KeyError, IndexError, ValueError, TypeError):
                            pass
                self.pousser(tel)
            except Exception as exc:
                self.pousser({"t": "lien", "etat": "perdu", "msg": f"HTTP : {exc}"})
                return
            await asyncio.sleep(float(t.get("periode_s", 0.2)))

    async def envoyer(self, msg: dict[str, Any]) -> None:
        t = msg.get("t")
        if t == "estop":
            self._estop = True
        elif t == "reset":
            self._estop = False
        elif t in ("servos", "drive") and self._estop:
            self.pousser({"t": "err", "msg": "estop"})
            return
        spec = self.c.get({"servos": "servos", "drive": "propulsion"}.get(t, t))
        if not isinstance(spec, dict):
            if t not in ("hb", "hello", "reset", "estop"):
                self.refuser(str(t))
            if t == "hello":
                self.pousser(self.info(url=self.url))
            return
        deg = [float(x) for x in msg.get("deg", [])]
        valeurs = {"deg": deg, "ms": int(msg.get("ms", 0)), "l": msg.get("l", 0), "r": msg.get("r", 0),
                   "nom": msg.get("nom", ""), **{f"deg{i}": v for i, v in enumerate(deg)}}
        await self._requete(spec, valeurs)

    async def fermer(self) -> None:
        if self._sondage:
            self._sondage.cancel()
        if self._session is not None:
            await self._session.close()
