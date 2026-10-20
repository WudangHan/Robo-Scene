"""Transports vers le robot : simulé, série (USB) ou TCP (Wi-Fi).

Tous parlent le même protocole : un objet JSON par ligne (voir PROTOCOLE.md).
"""
from __future__ import annotations

import asyncio
import json
import math
import random
import threading
import time
from typing import Any


class Transport:
    nom = "abstrait"

    async def ouvrir(self) -> None: ...
    async def envoyer(self, msg: dict[str, Any]) -> None: ...
    async def recevoir(self) -> dict[str, Any]: ...
    async def fermer(self) -> None: ...


def _decoder(ligne: bytes | str) -> dict[str, Any] | None:
    if isinstance(ligne, bytes):
        ligne = ligne.decode("utf-8", errors="replace")
    ligne = ligne.strip()
    if not ligne or not ligne.startswith("{"):
        return None  # bruit de démarrage de l'ESP32, messages de débogage
    try:
        return json.loads(ligne)
    except json.JSONDecodeError:
        return None


# ─────────────────────────────────────────────────────────────
#  Robot simulé : même protocole que le micrologiciel ESP32
# ─────────────────────────────────────────────────────────────
class TransportSimule(Transport):
    nom = "sim"

    def __init__(self, n_articulations: int, repos: list[float], propulsion: bool,
                 chien_de_garde_ms: int = 500, periode_ms: int = 50, gestes_natifs: list[str] | None = None,
                 images_geste=None, vbat: float = 8.2):
        self.n = n_articulations
        self.deg = list(map(float, repos))
        self.depart = list(self.deg)
        self.cible = list(self.deg)
        self.t0 = 0.0
        self.duree = 0.0
        self.roues = [0.0, 0.0]
        self.propulsion = propulsion
        self.pose = [0.0, 0.0, 0.0]  # x (m), y (m), cap (rad) sur un plateau de 4 × 3 m
        self.vbat = self.vbat0 = vbat           # tension pleine charge simulée (8,2 V : robot ESP32 ; 12,6 V : TonyPi)
        self.estop = False
        self.dernier_msg = time.monotonic()
        self.cdg = chien_de_garde_ms / 1000
        self.periode = periode_ms / 1000
        self._file: asyncio.Queue[dict] = asyncio.Queue()
        self._tache: asyncio.Task | None = None
        self.t_debut = time.monotonic()
        # Gestes natifs simulés (v2) : images converties des groupes d'actions du robot, si l'installation les a
        # importées (outils/hiwonder_tonypi.py) ; sinon, une pause de 1,5 s tient lieu de geste.
        self.gestes_natifs = list(gestes_natifs or [])
        self.images_geste = images_geste
        self._geste: asyncio.Task | None = None
        self.yeux: list[int] | None = None

    async def _jouer_geste(self, nom: str) -> None:
        images = (self.images_geste(nom) if self.images_geste else None) or []
        await self._file.put({"t": "evt", "type": "geste", "nom": nom, "etat": "debut", "simule": True})
        try:
            if not images:
                await asyncio.sleep(1.5)
            for im in images:
                self.depart, self.cible = list(self.deg), [float(x) for x in im["deg"]]
                self.duree, self.t0 = max(0.02, float(im.get("ms", 500)) / 1000), time.monotonic()
                await asyncio.sleep(self.duree)
            await self._file.put({"t": "evt", "type": "geste", "nom": nom, "etat": "fin", "simule": True})
        except asyncio.CancelledError:
            await self._file.put({"t": "evt", "type": "geste", "nom": nom, "etat": "interrompu", "simule": True})
            raise

    async def ouvrir(self) -> None:
        self._tache = asyncio.create_task(self._boucle())
        await self._file.put(self._info())

    def _info(self) -> dict:
        return {"t": "info", "nom": "SIM", "fw": "sim-1.0", "servos": self.n,
                "propulsion": self.propulsion}

    async def envoyer(self, msg: dict[str, Any]) -> None:
        self.dernier_msg = time.monotonic()
        t = msg.get("t")
        if t == "hello":
            await self._file.put(self._info())
        elif t == "estop":
            if self._geste and not self._geste.done():
                self._geste.cancel()
            self.estop = True
            self.roues = [0.0, 0.0]
            self.depart = list(self.deg)
            self.cible = list(self.deg)
            self.duree = 0.0
        elif t == "reset":
            self.estop = False
        elif self.estop and t in ("servos", "drive", "geste"):
            await self._file.put({"t": "err", "msg": "estop"})
        elif t == "geste":
            nom = str(msg.get("nom", ""))
            if nom not in self.gestes_natifs:
                await self._file.put({"t": "err", "msg": f"geste natif inconnu : {nom}"})
                return
            if self._geste and not self._geste.done():
                self._geste.cancel()
            self._geste = asyncio.create_task(self._jouer_geste(nom))
        elif t == "geste_arret":
            if self._geste and not self._geste.done():
                self._geste.cancel()
        elif t == "lumiere":
            self.yeux = [int(x) for x in (msg.get("rgb") or [0, 0, 0])[:3]]
        elif t in ("dire", "afficher"):
            pass                                   # simulation : la page affiche et dit elle-même
        elif t == "servos":
            if self._geste and not self._geste.done():
                self._geste.cancel()
            self.depart = list(self.deg)
            self.cible = [float(x) for x in msg["deg"]]
            self.duree = max(0.0, float(msg.get("ms", 0))) / 1000
            self.t0 = time.monotonic()
        elif t == "drive" and self.propulsion:
            self.roues = [float(msg.get("l", 0)), float(msg.get("r", 0))]

    async def recevoir(self) -> dict[str, Any]:
        return await self._file.get()

    async def _boucle(self) -> None:
        dernier = time.monotonic()
        while True:
            await asyncio.sleep(self.periode)
            now = time.monotonic()
            dt = now - dernier
            dernier = now
            # Chien de garde embarqué : silence du pont → arrêt des roues
            if now - self.dernier_msg > self.cdg:
                self.roues = [0.0, 0.0]
            # Interpolation linéaire des servos (comme le micrologiciel)
            if self.duree <= 0:
                a = 1.0
            else:
                a = min(1.0, (now - self.t0) / self.duree)
            if not self.estop:
                self.deg = [d + (c - d) * a for d, c in zip(self.depart, self.cible)]
            # Cinématique différentielle simple
            v_max, voie = 0.5, 0.18
            vl, vr = self.roues[0] * v_max, self.roues[1] * v_max
            v, w = (vl + vr) / 2, (vr - vl) / voie
            x, y, th = self.pose
            th += w * dt
            x = max(-2.0, min(2.0, x + v * math.cos(th) * dt))
            y = max(-1.5, min(1.5, y + v * math.sin(th) * dt))
            self.pose = [x, y, th]
            # Batterie : décharge lente, plus rapide en mouvement
            charge = 0.00002 + 0.0004 * (abs(vl) + abs(vr))
            self.vbat = max(self.vbat0 * 0.73, self.vbat - charge * dt * 20)
            dist = self._distance_mur(x, y, th)
            await self._file.put({
                "t": "tel",
                "ms": int((now - self.t_debut) * 1000),
                "deg": [round(d, 1) for d in self.deg],
                "drive": [round(r, 2) for r in self.roues],
                "vbat": round(self.vbat + random.uniform(-0.01, 0.01), 2),
                "dist": round(dist * 100 + random.uniform(-1, 1), 1),
                "pose": [round(x, 3), round(y, 3), round(th, 3)],
                "estop": self.estop,
            })

    @staticmethod
    def _distance_mur(x: float, y: float, th: float) -> float:
        """Distance (m) au bord du plateau dans la direction du cap, plafonnée à 4 m."""
        c, s = math.cos(th), math.sin(th)
        ds = []
        if c > 1e-6:
            ds.append((2.0 - x) / c)
        if c < -1e-6:
            ds.append((-2.0 - x) / c)
        if s > 1e-6:
            ds.append((1.5 - y) / s)
        if s < -1e-6:
            ds.append((-1.5 - y) / s)
        return min(min(ds, default=4.0), 4.0)

    async def fermer(self) -> None:
        if self._tache:
            self._tache.cancel()


# ─────────────────────────────────────────────────────────────
#  Série (USB) : pyserial dans un fil d'exécution dédié
# ─────────────────────────────────────────────────────────────
class TransportSerie(Transport):
    nom = "serie"

    def __init__(self, port: str, debit: int = 115200):
        self.port, self.debit = port, debit
        self._ser = None
        self._file: asyncio.Queue[dict] = asyncio.Queue()
        self._actif = False

    async def ouvrir(self) -> None:
        import serial  # pyserial, importé seulement si nécessaire

        loop = asyncio.get_running_loop()
        self._ser = serial.Serial(self.port, self.debit, timeout=0.1)
        self._actif = True

        def lire() -> None:
            while self._actif:
                try:
                    ligne = self._ser.readline()
                except Exception as exc:  # câble débranché
                    loop.call_soon_threadsafe(
                        self._file.put_nowait, {"t": "lien", "etat": "perdu", "msg": str(exc)})
                    return
                msg = _decoder(ligne)
                if msg is not None:
                    loop.call_soon_threadsafe(self._file.put_nowait, msg)

        threading.Thread(target=lire, daemon=True).start()
        await asyncio.sleep(2.0)  # beaucoup de cartes redémarrent à l'ouverture du port

    async def envoyer(self, msg: dict[str, Any]) -> None:
        data = (json.dumps(msg, separators=(",", ":")) + "\n").encode()
        await asyncio.get_running_loop().run_in_executor(None, self._ser.write, data)

    async def recevoir(self) -> dict[str, Any]:
        return await self._file.get()

    async def fermer(self) -> None:
        self._actif = False
        if self._ser:
            self._ser.close()


# ─────────────────────────────────────────────────────────────
#  TCP (Wi-Fi) : l'ESP32 écoute sur un port, une ligne JSON par message
# ─────────────────────────────────────────────────────────────
class TransportTCP(Transport):
    nom = "tcp"

    def __init__(self, hote: str, port: int):
        self.hote, self.port = hote, port
        self._r: asyncio.StreamReader | None = None
        self._w: asyncio.StreamWriter | None = None

    async def ouvrir(self) -> None:
        self._r, self._w = await asyncio.wait_for(
            asyncio.open_connection(self.hote, self.port), timeout=5)

    async def envoyer(self, msg: dict[str, Any]) -> None:
        self._w.write((json.dumps(msg, separators=(",", ":")) + "\n").encode())
        await self._w.drain()

    async def recevoir(self) -> dict[str, Any]:
        while True:
            ligne = await self._r.readline()
            if not ligne:
                return {"t": "lien", "etat": "perdu", "msg": "connexion TCP fermée"}
            msg = _decoder(ligne)
            if msg is not None:
                return msg

    async def fermer(self) -> None:
        if self._w:
            self._w.close()
