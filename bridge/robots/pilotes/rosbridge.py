"""Pilote ROS 1 et ROS 2 par rosbridge (protocole JSON sur WebSocket ; aucun ROS requis sur cet ordinateur).

Le robot (ou son ordinateur embarqué) exécute rosbridge_server ; le pont s'y connecte (ws://hôte:9090) et :
* publie les articulations comme trajectory_msgs/JointTrajectory (un point, durée = ms), en radians ;
* publie la propulsion comme geometry_msgs/Twist (vitesse linéaire et angulaire bornées) ;
* publie l'arrêt d'urgence comme std_msgs/Bool (true) sur un sujet dédié, puis une vitesse nulle ;
* s'abonne à sensor_msgs/JointState pour la télémétrie (radians → degrés, appariés par nom de joint).

Noms des types : ROS 1 « paquet/Type », ROS 2 « paquet/msg/Type » ; durées : ROS 1 {secs, nsecs},
ROS 2 {sec, nanosec}. Les sujets sont réglables dans le profil du robot ([connexion]).
"""
from __future__ import annotations

import json
import math
from typing import Any

from .base import Pilote


def type_ros(paquet: str, nom: str, version: int) -> str:
    return f"{paquet}/msg/{nom}" if version == 2 else f"{paquet}/{nom}"


def duree_ros(ms: float, version: int) -> dict[str, int]:
    s, ns = int(ms // 1000), int((ms % 1000) * 1_000_000)
    return {"sec": s, "nanosec": ns} if version == 2 else {"secs": s, "nsecs": ns}


class PiloteRosbridge(Pilote):
    type = "rosbridge"

    def __init__(self, desc, ws_factory=None):
        super().__init__(desc)
        c = desc.connexion
        self.url = c.get("url", "ws://127.0.0.1:9090")
        self.version = int(c.get("ros", 2))
        self.s_traj = c.get("sujet_trajectoire", "/robo_scene/joint_trajectory")
        self.s_etat = c.get("sujet_etat", "/joint_states")
        self.s_vit = c.get("sujet_vitesse", "/cmd_vel")
        self.s_arret = c.get("sujet_arret", "/robo_scene/arret_urgence")
        self.v_lin, self.v_ang = float(c.get("vitesse_lineaire_max", 0.2)), float(c.get("vitesse_angulaire_max", 0.8))
        self.joints = [str(a.id or a.nom) for a in desc.articulations]
        self.radians = [a.unite == "deg" for a in desc.articulations]
        self._ws_factory = ws_factory
        self._ws = self._session = None
        self._estop = False
        self._deg = list(desc.repos)

    async def _envoyer_json(self, d: dict[str, Any]) -> None:
        await self._ws.send_str(json.dumps(d))

    async def ouvrir(self) -> None:
        if self._ws_factory:
            self._ws = await self._ws_factory(self.url)
        else:
            import aiohttp
            self._session = aiohttp.ClientSession()
            self._ws = await self._session.ws_connect(self.url, heartbeat=5, timeout=5)
        v = self.version
        for sujet, t in ((self.s_traj, type_ros("trajectory_msgs", "JointTrajectory", v)),
                         (self.s_vit, type_ros("geometry_msgs", "Twist", v)),
                         (self.s_arret, type_ros("std_msgs", "Bool", v))):
            await self._envoyer_json({"op": "advertise", "topic": sujet, "type": t})
        await self._envoyer_json({"op": "subscribe", "topic": self.s_etat,
                                  "type": type_ros("sensor_msgs", "JointState", v), "throttle_rate": 50})
        self.pousser(self.info(ros=v, url=self.url))

    def _publier(self, sujet: str, msg: dict) -> dict:
        return {"op": "publish", "topic": sujet, "msg": msg}

    async def envoyer(self, msg: dict[str, Any]) -> None:
        t = msg.get("t")
        if t == "hello":
            self.pousser(self.info(ros=self.version, url=self.url))
        elif t == "servos":
            if self._estop:
                self.pousser({"t": "err", "msg": "estop"})
                return
            pos = [math.radians(float(d)) if r else float(d) / 1000 for d, r in zip(msg["deg"], self.radians)]
            point = {"positions": pos, "time_from_start": duree_ros(float(msg.get("ms", 0)), self.version)}
            await self._envoyer_json(self._publier(self.s_traj, {"joint_names": self.joints, "points": [point]}))
        elif t == "drive":
            if self._estop:
                return
            g, d = float(msg.get("l", 0)), float(msg.get("r", 0))
            await self._envoyer_json(self._publier(self.s_vit, {
                "linear": {"x": round((g + d) / 2 * self.v_lin, 4), "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": round((d - g) / 2 * self.v_ang, 4)}}))
        elif t == "estop":
            self._estop = True
            await self._envoyer_json(self._publier(self.s_arret, {"data": True}))
            await self._envoyer_json(self._publier(self.s_vit, {"linear": {"x": 0.0, "y": 0.0, "z": 0.0},
                                                                "angular": {"x": 0.0, "y": 0.0, "z": 0.0}}))
        elif t == "reset":
            self._estop = False
            await self._envoyer_json(self._publier(self.s_arret, {"data": False}))
        elif t != "hb":
            self.refuser(str(t))

    async def recevoir(self) -> dict[str, Any]:
        if not self._file.empty():
            return self._file.get_nowait()
        while True:
            m = await self._ws.receive()
            data = getattr(m, "data", m)
            if not isinstance(data, str):
                if data is None or getattr(m, "type", None) in (8, 256, 257, 258):
                    return {"t": "lien", "etat": "perdu", "msg": "rosbridge fermé"}
                continue
            try:
                d = json.loads(data)
            except json.JSONDecodeError:
                continue
            if d.get("op") == "publish" and d.get("topic") == self.s_etat:
                js = d.get("msg", {})
                par_nom = dict(zip(js.get("name", []), js.get("position", [])))
                for i, (j, r) in enumerate(zip(self.joints, self.radians)):
                    if j in par_nom:
                        self._deg[i] = round(math.degrees(par_nom[j]) if r else par_nom[j] * 1000, 2)
                return {"t": "tel", "ms": self.ms(), "deg": list(self._deg), "drive": [0, 0], "estop": self._estop}
            if d.get("op") == "status" and d.get("level") == "error":
                return {"t": "err", "msg": d.get("msg", "rosbridge")}

    async def fermer(self) -> None:
        if self._ws is not None:
            await self._ws.close()
        if self._session is not None:
            await self._session.close()
