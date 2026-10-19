"""Adaptateurs du chien réel : un par famille de protocole ; le contrôleur ne voit que l'interface commune.

Interface commune : consignes de vitesse dans le repère du corps du robot (avant, gauche, en m/s ; vitesse de lacet
en °/s, positive dans le sens antihoraire vu de dessus, comme le lacet du théâtre et comme l'axe z de ROS), postures
nommées (debout, couche, assis, patte, salut, etirement), arrêt (vitesse nulle), coupure (le robot s'affaisse).
La télémétrie est rendue dans le repère du théâtre : p = [x, y, z], lacet en degrés.

- simulation : quadrupède cinématique dans le pont (répétition de toute la chaîne sans robot) ;
- rosbridge  : ROS 2 (ou ROS 1) par rosbridge — geometry_msgs/Twist sur /cmd_vel, nav_msgs/Odometry sur /odom,
               posture par std_msgs/String sur un sujet de la plateforme (un petit nœud, côté robot, la traduit en
               commandes du fabricant), arrêt d'urgence par std_msgs/Bool ; voie commune à de nombreux quadrupèdes
               (pilotes ROS 2 communautaires ou du fabricant) ;
- petoi      : Petoi Bittle / Nybble (OpenCat), protocole série par jetons (« kwkF », « ksit »…) ; boucle ouverte ;
- ligne_json : JSON par ligne en UDP vers un ordinateur compagnon, dans le repère du théâtre.
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from typing import Any, Callable

Rappel = Callable[[dict[str, Any]], None]
POSTURES = ("debout", "couche", "assis", "patte", "salut", "etirement")


class RepereSol:
    """Passage du repère d'odométrie du robot (X devant au départ, Y à gauche, lacet θ antihoraire) au repère du
    théâtre. origine : [x, z] de la marque de départ ; cap_deg : lacet du théâtre du robot à son départ."""

    def __init__(self, origine=(0.0, 0.0), cap_deg: float = 0.0, y0: float = 0.0):
        self.o = [float(origine[0]), float(origine[1])]
        self.cap = math.radians(cap_deg)
        self.y0 = float(y0)

    def vers_theatre(self, X: float, Y: float) -> list[float]:
        c = self.cap
        return [self.o[0] + X * math.sin(c) + Y * math.cos(c), self.o[1] + X * math.cos(c) - Y * math.sin(c)]

    def depuis_theatre(self, x: float, z: float) -> list[float]:
        c, dx, dz = self.cap, x - self.o[0], z - self.o[1]
        return [dx * math.sin(c) + dz * math.cos(c), dx * math.cos(c) - dz * math.sin(c)]

    def lacet_theatre(self, theta: float) -> float:
        return math.degrees(self.cap + theta)


def lacet_quaternion(q: dict) -> float:
    x, y, z, w = (float(q.get(k, 0)) for k in ("x", "y", "z", "w"))
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


class Adaptateur:
    nom = "abstrait"
    reel = True
    position_mesuree = True

    def __init__(self, cfg: dict[str, Any], repere: RepereSol):
        self.cfg = cfg
        self.repere = repere
        self.rappel: Rappel = lambda _m: None
        self.tel: dict[str, Any] = {"p": [repere.o[0], repere.y0, repere.o[1]], "v": [0.0, 0.0],
                                    "lacet": math.degrees(repere.cap), "batterie": None, "etat": "couche",
                                    "posture": "couche", "position": "mesurée" if self.position_mesuree else "estimée"}

    async def ouvrir(self, rappel: Rappel) -> None:
        self.rappel = rappel

    async def fermer(self) -> None: ...
    async def vitesse(self, avant: float, gauche: float, lacet_vitesse: float) -> None: ...
    async def posture(self, nom: str) -> None: ...
    async def arreter(self) -> None:
        await self.vitesse(0.0, 0.0, 0.0)
    async def urgence(self) -> None:
        await self.arreter()
        await self.posture("couche")
    async def couper(self) -> None: ...

    def publier(self, **maj: Any) -> None:
        self.tel.update(maj)
        self.tel["recu"] = time.monotonic()
        self.rappel(dict(self.tel))


# ── Simulation dans le pont ────────────────────────────────────
class AdaptateurSimulation(Adaptateur):
    nom = "simulation"
    reel = False

    def __init__(self, cfg, repere):
        super().__init__(cfg, repere)
        self.cmd = (0.0, 0.0, 0.0)
        self.cmd_jusqua = 0.0
        self.tache: asyncio.Task | None = None
        self.batt = 100.0

    async def ouvrir(self, rappel):
        await super().ouvrir(rappel)
        self.tache = asyncio.create_task(self._boucle())
        self.publier(batterie=100.0)

    async def fermer(self):
        if self.tache:
            self.tache.cancel()

    async def _boucle(self):
        dt = 0.05
        while True:
            await asyncio.sleep(dt)
            t = self.tel
            av, ga, wz = self.cmd if time.monotonic() < self.cmd_jusqua and t["etat"] == "debout" else (0.0, 0.0, 0.0)
            psi = math.radians(t["lacet"])
            vx = av * math.sin(psi) + ga * math.cos(psi)
            vz = av * math.cos(psi) - ga * math.sin(psi)
            p = t["p"]
            p[0] += vx * dt
            p[2] += vz * dt
            self.batt = max(0.0, self.batt - 100 / (60 * 60) * dt)
            self.publier(p=p, v=[vx, vz], lacet=(t["lacet"] + wz * dt), batterie=round(self.batt, 1))

    async def vitesse(self, avant, gauche, lacet_vitesse):
        self.cmd = (avant, gauche, lacet_vitesse)
        self.cmd_jusqua = time.monotonic() + 0.5

    async def posture(self, nom):
        etat = "couche" if nom == "couche" else "debout"
        self.publier(posture=nom, etat=etat)

    async def couper(self):
        self.cmd = (0.0, 0.0, 0.0)
        self.publier(etat="affaisse", posture="couche")


# ── ROS 2 / ROS 1 par rosbridge ────────────────────────────────
class AdaptateurRosbridge(Adaptateur):
    nom = "rosbridge"

    def __init__(self, cfg, repere, ws_factory=None):
        super().__init__(cfg, repere)
        self.url = cfg.get("url", "ws://127.0.0.1:9090")
        self.version = int(cfg.get("ros", 2))
        self.s_vit = cfg.get("sujet_vitesse", "/cmd_vel")
        self.s_odom = cfg.get("sujet_odometrie", "/odom")
        self.s_posture = cfg.get("sujet_posture", "/robo_scene/posture")
        self.s_arret = cfg.get("sujet_arret", "/robo_scene/arret_urgence")
        self.s_batt = cfg.get("sujet_batterie", "")
        self._ws_factory = ws_factory
        self._ws = self._session = None
        self.lecture: asyncio.Task | None = None

    def _type(self, paquet: str, nom: str) -> str:
        return f"{paquet}/msg/{nom}" if self.version == 2 else f"{paquet}/{nom}"

    async def _json(self, d: dict) -> None:
        await self._ws.send_str(json.dumps(d))

    async def ouvrir(self, rappel):
        await super().ouvrir(rappel)
        if self._ws_factory:
            self._ws = await self._ws_factory(self.url)
        else:
            import aiohttp
            self._session = aiohttp.ClientSession()
            self._ws = await self._session.ws_connect(self.url, heartbeat=5, timeout=5)
        for sujet, t in ((self.s_vit, self._type("geometry_msgs", "Twist")), (self.s_posture, self._type("std_msgs", "String")),
                         (self.s_arret, self._type("std_msgs", "Bool"))):
            await self._json({"op": "advertise", "topic": sujet, "type": t})
        await self._json({"op": "subscribe", "topic": self.s_odom, "type": self._type("nav_msgs", "Odometry"), "throttle_rate": 50})
        if self.s_batt:
            await self._json({"op": "subscribe", "topic": self.s_batt, "type": self._type("sensor_msgs", "BatteryState"), "throttle_rate": 1000})
        self.lecture = asyncio.create_task(self._lire())

    async def _lire(self):
        import aiohttp
        async for msg in self._ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            try:
                d = json.loads(msg.data)
            except json.JSONDecodeError:
                continue
            if d.get("op") != "publish":
                continue
            m = d.get("msg") or {}
            if d.get("topic") == self.s_odom:
                pose = (m.get("pose") or {}).get("pose") or {}
                pos, ori = pose.get("position") or {}, pose.get("orientation") or {}
                xz = self.repere.vers_theatre(float(pos.get("x", 0)), float(pos.get("y", 0)))
                tw = ((m.get("twist") or {}).get("twist") or {}).get("linear") or {}
                c = self.repere.cap + lacet_quaternion(ori)
                vx, vy = float(tw.get("x", 0)), float(tw.get("y", 0))
                self.publier(p=[xz[0], self.repere.y0 + float(pos.get("z", 0)), xz[1]],
                             v=[vx * math.sin(c) + vy * math.cos(c), vx * math.cos(c) - vy * math.sin(c)],
                             lacet=round(self.repere.lacet_theatre(lacet_quaternion(ori)), 1))
            elif self.s_batt and d.get("topic") == self.s_batt and m.get("percentage") is not None:
                pct = float(m["percentage"])
                self.publier(batterie=round(pct * 100 if pct <= 1 else pct, 1))

    async def fermer(self):
        if self.lecture:
            self.lecture.cancel()
        if self._ws is not None:
            await self._ws.close()
        if self._session is not None:
            await self._session.close()

    async def vitesse(self, avant, gauche, lacet_vitesse):
        await self._json({"op": "publish", "topic": self.s_vit, "msg": {
            "linear": {"x": round(avant, 4), "y": round(gauche, 4), "z": 0.0},
            "angular": {"x": 0.0, "y": 0.0, "z": round(math.radians(lacet_vitesse), 4)}}})

    async def posture(self, nom):
        await self._json({"op": "publish", "topic": self.s_posture, "msg": {"data": nom}})
        self.publier(posture=nom, etat="couche" if nom == "couche" else "debout")

    async def couper(self):
        await self.vitesse(0.0, 0.0, 0.0)
        await self._json({"op": "publish", "topic": self.s_arret, "msg": {"data": True}})
        self.publier(etat="affaisse")


# ── Petoi (OpenCat), série ─────────────────────────────────────
JETONS_POSTURE = {"debout": "kbalance", "couche": "krest", "assis": "ksit", "patte": "khi", "salut": "khi", "etirement": "kstr"}


class AdaptateurPetoi(Adaptateur):
    """Jetons série OpenCat (documentation Petoi) : marche « kwkF », « kwkL », « kwkR », recul « kbk », postures.
    Pas d'odométrie : position estimée à l'estime à partir d'une vitesse nominale (à étalonner)."""
    nom = "petoi"
    position_mesuree = False

    def __init__(self, cfg, repere, serie_factory=None):
        super().__init__(cfg, repere)
        self.port = cfg.get("port", "/dev/tty.usbmodem0001")
        self.debit = int(cfg.get("debit", 115200))          # (à vérifier selon la carte)
        self.v_nominale = float(cfg.get("vitesse_nominale_m_s", 0.1))
        self._factory = serie_factory
        self.s = None
        self.dernier = ""
        self.cmd = (0.0, 0.0, 0.0)
        self.cmd_jusqua = 0.0
        self.tache: asyncio.Task | None = None

    async def ouvrir(self, rappel):
        await super().ouvrir(rappel)
        if self._factory:
            self.s = self._factory()
        else:
            import serial  # pyserial
            self.s = await asyncio.to_thread(serial.Serial, self.port, self.debit, timeout=0.1)
        self.tache = asyncio.create_task(self._estime())

    def _jeton(self, j: str) -> None:
        if j != self.dernier:
            self.s.write((j + "\n").encode())
            self.dernier = j

    async def _estime(self):
        dt = 0.1
        while True:
            await asyncio.sleep(dt)
            av, _ga, wz = self.cmd if time.monotonic() < self.cmd_jusqua else (0.0, 0.0, 0.0)
            if not (av or wz) and self.dernier.startswith(("kwk", "kbk")):
                self._jeton("kbalance")
            t = self.tel
            psi = math.radians(t["lacet"])
            p = t["p"]
            v = self.v_nominale if av > 0.02 else (-self.v_nominale if av < -0.02 else 0.0)
            p[0] += v * math.sin(psi) * dt
            p[2] += v * math.cos(psi) * dt
            self.publier(p=p, lacet=t["lacet"] + (30.0 if wz > 5 else -30.0 if wz < -5 else 0.0) * dt)

    async def fermer(self):
        if self.tache:
            self.tache.cancel()
        if self.s:
            self.s.close()

    async def vitesse(self, avant, gauche, lacet_vitesse):
        self.cmd = (avant, gauche, lacet_vitesse)
        self.cmd_jusqua = time.monotonic() + 0.5
        if lacet_vitesse > 5:
            self._jeton("kwkL")
        elif lacet_vitesse < -5:
            self._jeton("kwkR")
        elif avant > 0.02:
            self._jeton("kwkF")
        elif avant < -0.02:
            self._jeton("kbk")
        else:
            self._jeton("kbalance")

    async def posture(self, nom):
        self._jeton(JETONS_POSTURE.get(nom, "kbalance"))
        self.publier(posture=nom, etat="couche" if nom == "couche" else "debout")

    async def couper(self):
        self._jeton("d")
        self.publier(etat="affaisse")


# ── JSON par ligne vers un ordinateur compagnon ────────────────
class AdaptateurLigneJSON(Adaptateur):
    nom = "ligne_json"

    def __init__(self, cfg, repere):
        super().__init__(cfg, repere)
        self.hote = cfg.get("hote", "127.0.0.1")
        self.port = int(cfg.get("port", 9751))

    async def ouvrir(self, rappel):
        await super().ouvrir(rappel)
        loop = asyncio.get_running_loop()
        adapt = self

        class P(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):
                for ligne in data.decode("utf-8", "replace").splitlines():
                    try:
                        m = json.loads(ligne)
                    except json.JSONDecodeError:
                        continue
                    if m.get("t") == "tel":
                        adapt.publier(**{k: m[k] for k in ("p", "v", "lacet", "batterie", "etat", "posture") if k in m})

        self.tr, _ = await loop.create_datagram_endpoint(P, local_addr=("0.0.0.0", int(self.cfg.get("port_local", 0))))
        self._envoyer({"cmd": "hello"})

    def _envoyer(self, m: dict) -> None:
        self.tr.sendto((json.dumps({"t": "chien", **m}, ensure_ascii=False) + "\n").encode(), (self.hote, self.port))

    async def fermer(self):
        self.tr.close()

    async def vitesse(self, avant, gauche, lacet_vitesse):
        self._envoyer({"cmd": "vitesse", "avant": round(avant, 3), "gauche": round(gauche, 3), "lacet_vitesse": round(lacet_vitesse, 2)})

    async def posture(self, nom):
        self._envoyer({"cmd": "posture", "nom": nom})

    async def couper(self):
        self._envoyer({"cmd": "couper"})


ADAPTATEURS: dict[str, type[Adaptateur]] = {c.nom: c for c in (AdaptateurSimulation, AdaptateurRosbridge, AdaptateurPetoi,
                                                              AdaptateurLigneJSON)}
DESCRIPTIONS = {
    "simulation": "Quadrupède simulé dans le pont (toute la chaîne, sans robot)",
    "rosbridge": "ROS 2 ou ROS 1 par rosbridge : /cmd_vel, /odom, posture et arrêt (quadrupèdes à pilote ROS)",
    "petoi": "Petoi Bittle / Nybble (OpenCat) par port série : marche et postures par jetons, position estimée",
    "ligne_json": "JSON par ligne en UDP vers un ordinateur compagnon (repère du théâtre)",
}
