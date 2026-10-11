"""Pilote Reachy Mini (Pollen Robotics / Hugging Face) par sa trousse de développement Python.

Le Reachy Mini ne s'exprime pas en angles de servos mais en POSE de tête (x, y, z en mm ; roulis, tangage,
lacet en degrés), en rotation du corps et en angles d'antennes. La description unifiée l'expose donc comme
neuf « articulations » virtuelles, dans cet ordre : x, y, z, roll, pitch, yaw, body_yaw, antenne_droite,
antenne_gauche — exactement les composantes des images clés de la bibliothèque fermée P2.2.

Appel employé (documentation du SDK, consultée le 11 octobre 2026) :
    mini.goto_target(head=create_head_pose(x, y, z, roll, pitch, yaw, mm=True, degrees=True),
                     antennas=[rad, rad], body_yaw=rad, duration=s, method="minjerk")
et ReachyMini(connection_mode=…, media_backend="no_media").

Limites connues :
* la documentation consultée ne décrit aucune méthode de lecture de la pose courante : la télémétrie publiée
  est la dernière cible commandée, marquée « estimee » ;
* aucune méthode d'arrêt n'y est décrite : l'arrêt logiciel bloque toute nouvelle commande, mais il
  n'interrompt pas un mouvement interpolé déjà lancé. Les gestes de la bibliothèque sont courts et lents,
  et l'arrêt matériel reste la mesure de sécurité de référence (P2.1).
"""
from __future__ import annotations

import asyncio
import math
from typing import Any

from .base import Pilote

AXES = ["x", "y", "z", "roll", "pitch", "yaw", "body_yaw", "antenne_droite", "antenne_gauche"]


class PiloteReachyMini(Pilote):
    type = "reachy_mini"

    def __init__(self, desc, mini=None):
        super().__init__(desc)
        if [a.nom for a in desc.articulations] != AXES:
            raise ValueError("Profil Reachy Mini : les articulations doivent être " + ", ".join(AXES))
        self.mode = desc.connexion.get("mode_connexion")       # None : détection automatique du SDK
        self._mini = mini
        self._cible = list(desc.repos)
        self._estop = False
        self._veille: asyncio.Task | None = None

    async def ouvrir(self) -> None:
        if self._mini is None:
            def connecter():
                from reachy_mini import ReachyMini
                kw = {"media_backend": "no_media"}
                if self.mode:
                    kw["connection_mode"] = self.mode
                return ReachyMini(**kw)
            try:
                self._mini = await asyncio.to_thread(connecter)
            except ImportError as exc:
                raise ConnectionError("Trousse reachy-mini absente : pip install reachy-mini "
                                      "(simulation : reachy-mini-daemon --sim)") from exc
        self.pousser(self.info(sdk="reachy_mini", axes=AXES))
        self._veille = asyncio.create_task(self._telemetrie())

    async def _telemetrie(self) -> None:
        while True:
            await asyncio.sleep(0.1)
            self.pousser({"t": "tel", "ms": self.ms(), "deg": list(self._cible), "drive": [0, 0],
                          "estop": self._estop, "estimee": True})

    def _goto(self, v: list[float], ms: float) -> None:
        from reachy_mini.utils import create_head_pose
        x, y, z, roll, pitch, yaw, by, ad, ag = v
        self._mini.goto_target(head=create_head_pose(x=x, y=y, z=z, roll=roll, pitch=pitch, yaw=yaw,
                                                     mm=True, degrees=True),
                               antennas=[math.radians(ad), math.radians(ag)], body_yaw=math.radians(by),
                               duration=max(0.25, ms / 1000), method="minjerk")

    async def envoyer(self, msg: dict[str, Any]) -> None:
        t = msg.get("t")
        if t == "servos":
            if self._estop:
                self.pousser({"t": "err", "msg": "estop"})
                return
            v = [float(x) for x in msg["deg"]]
            self._cible = v
            await asyncio.to_thread(self._goto, v, float(msg.get("ms", 1000)))
        elif t == "estop":
            self._estop = True
        elif t == "reset":
            self._estop = False
        elif t == "hello":
            self.pousser(self.info(sdk="reachy_mini", axes=AXES))
        elif t == "drive" and (msg.get("l") or msg.get("r")):
            self.refuser("propulsion")

    async def fermer(self) -> None:
        if self._veille:
            self._veille.cancel()
        close = getattr(self._mini, "__exit__", None)
        if close:
            try:
                close(None, None, None)
            except Exception:
                pass
