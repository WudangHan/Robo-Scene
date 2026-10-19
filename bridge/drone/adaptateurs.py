"""Adaptateurs du drone réel : un par famille de protocole ; le contrôleur ne voit que l'interface commune.

Repère commun : le repère du théâtre (x vers cour, y vers le haut, z vers la salle, mètres ; lacet en degrés,
0 = nez vers la salle, 90 = nez vers cour, croissant dans le sens antihoraire vu de dessus ; vitesse de lacet dans le
même sens). Chaque adaptateur convertit vers le repère natif de l'appareil (cap NED et « cw » : sens horaire).

- simulation : drone cinématique dans le pont (répétition de toute la chaîne sans appareil) ;
- mavlink    : ArduPilot Copter en mode GUIDED (pymavlink) — drones à autopilote ouvert, dont ceux qui portent une
               caméra 4K (flux vidéo séparé : RTSP/SRT → MediaMTX → WHEP, ou sortie HDMI → carte de capture) ;
- tello      : Ryze/DJI Tello (SDK texte en UDP) — petit drone de répétition (caméra 720p, pas 4K) ;
- ligne_json : JSON par ligne en UDP vers un ordinateur compagnon (Crazyflie, drone maison, système de capture
               de mouvement…), qui reçoit directement les coordonnées du théâtre.

Références vérifiées (octobre 2026) : ArduPilot, « Copter Commands in Guided Mode » (masques 3576 et 3527 ; arrêt
après 3 s sans consigne de vitesse) et « Arming and Disarming » (paramètre 21196 : désarmement forcé, même en vol) ;
Ryze, « Tello SDK 2.0 User Guide » (ports 8889/8890, commandes, atterrissage automatique après 15 s sans commande).
"""
from __future__ import annotations

import asyncio
import json
import math
import socket
import threading
import time
from typing import Any, Callable

Rappel = Callable[[dict[str, Any]], None]


class Repere:
    """Passage du repère du théâtre au repère local NED de l'autopilote (nord, est, bas).

    origine : point du théâtre où l'autopilote fixe son origine locale (en général l'aire de décollage) ;
    cap_deg : angle, vu de dessus et compté vers cour, entre la direction du lointain et le nord local.
    Avec cap_deg = 0 : nord = lointain (−z), est = cour (+x), bas = −y.
    """

    def __init__(self, origine=(0.0, 0.0, 0.0), cap_deg: float = 0.0):
        self.o = [float(v) for v in origine]
        t = math.radians(cap_deg)
        self.nord = (math.sin(t), 0.0, -math.cos(t))
        self.est = (math.cos(t), 0.0, math.sin(t))

    def vers_ned(self, p) -> tuple[float, float, float]:
        d = [p[i] - self.o[i] for i in range(3)]
        return (d[0] * self.nord[0] + d[2] * self.nord[2], d[0] * self.est[0] + d[2] * self.est[2], -d[1])

    def depuis_ned(self, n: float, e: float, b: float) -> list[float]:
        return [self.o[0] + n * self.nord[0] + e * self.est[0], self.o[1] - b, self.o[2] + n * self.nord[2] + e * self.est[2]]

    def vitesse_vers_ned(self, v) -> tuple[float, float, float]:
        return (v[0] * self.nord[0] + v[2] * self.nord[2], v[0] * self.est[0] + v[2] * self.est[2], -v[1])

    def lacet_vers_ned(self, lacet_deg: float) -> float:
        """Lacet du théâtre → cap NED (radians, compté du nord vers l'est)."""
        f = (math.sin(math.radians(lacet_deg)), math.cos(math.radians(lacet_deg)))       # (x, z) de l'avant
        return math.atan2(f[0] * self.est[0] + f[1] * self.est[2], f[0] * self.nord[0] + f[1] * self.nord[2])

    def lacet_depuis_ned(self, cap_rad: float) -> float:
        x = math.cos(cap_rad) * self.nord[0] + math.sin(cap_rad) * self.est[0]
        z = math.cos(cap_rad) * self.nord[2] + math.sin(cap_rad) * self.est[2]
        return math.degrees(math.atan2(x, z))


class Adaptateur:
    nom = "abstrait"
    reel = True
    flux_position = True          # vrai : le contrôleur envoie des consignes de position à 10 Hz le long du trajet
    position_mesuree = True       # faux : position estimée à l'estime (pas de localisation absolue)

    def __init__(self, cfg: dict[str, Any], repere: Repere):
        self.cfg = cfg
        self.repere = repere
        self.rappel: Rappel = lambda _m: None
        self.tel: dict[str, Any] = {"p": list(repere.o), "v": [0.0, 0.0, 0.0], "lacet": 180.0, "batterie": None,
                                    "arme": False, "etat": "au_sol", "mode_autopilote": "", "position":
                                    "mesurée" if self.position_mesuree else "estimée"}

    async def ouvrir(self, rappel: Rappel) -> None:
        self.rappel = rappel

    async def fermer(self) -> None: ...
    async def armer(self) -> None: ...
    async def decoller(self, hauteur: float) -> None: ...
    async def atterrir(self) -> None: ...
    async def stationnaire(self) -> None: ...
    async def position(self, p, lacet: float | None) -> None: ...
    async def aller(self, p, lacet: float | None, vitesse: float) -> None:   # adaptateurs sans flux de position
        await self.position(p, lacet)
    async def vitesse(self, v, lacet_vitesse: float) -> None: ...
    async def urgence(self) -> None:
        await self.atterrir()
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
        self.cible: list[float] | None = None
        self.v_cmd: list[float] | None = None
        self.v_jusqua = 0.0
        self.tache: asyncio.Task | None = None
        self.batt = 100.0

    async def ouvrir(self, rappel):
        await super().ouvrir(rappel)
        self.tache = asyncio.create_task(self._boucle())
        self.publier(batterie=100.0, mode_autopilote="SIM")

    async def fermer(self):
        if self.tache:
            self.tache.cancel()

    async def _boucle(self):
        dt = 0.05
        while True:
            await asyncio.sleep(dt)
            t, p = self.tel, self.tel["p"]
            if t["etat"] in ("au_sol", "coupe"):
                continue
            if t["etat"] == "chute":
                p[1] = max(self.repere.o[1], p[1] - 3.0 * dt)
                if p[1] <= self.repere.o[1] + 1e-6:
                    self.publier(etat="coupe", arme=False, v=[0, 0, 0])
                continue
            if self.v_cmd is not None and time.monotonic() < self.v_jusqua:
                v = self.v_cmd
            elif self.cible is not None:
                e = [self.cible[i] - p[i] for i in range(3)]
                d = math.dist(self.cible, p)
                s = min(1.5, 2.5 * d)
                v = [x / d * s for x in e] if d > 1e-4 else [0.0, 0.0, 0.0]
            else:
                v = [0.0, 0.0, 0.0]
            for i in range(3):
                p[i] += v[i] * dt
            self.batt = max(0.0, self.batt - 100 / (12 * 60) * dt)
            etat = t["etat"]
            if etat in ("atterrissage",) and p[1] <= self.repere.o[1] + 0.02:
                etat, v = "au_sol", [0, 0, 0]
                t["arme"] = False
                self.cible = None
            elif etat == "decollage" and self.cible and abs(p[1] - self.cible[1]) < 0.05:
                etat = "vol"
            self.publier(p=p, v=v, etat=etat, batterie=round(self.batt, 1))

    async def armer(self):
        self.publier(arme=True)

    async def decoller(self, hauteur):
        p = self.tel["p"]
        self.cible = [p[0], self.repere.o[1] + hauteur, p[2]]
        self.publier(etat="decollage", arme=True)

    async def atterrir(self):
        p = self.tel["p"]
        self.cible = [p[0], self.repere.o[1], p[2]]
        self.v_cmd = None
        self.publier(etat="atterrissage")

    async def stationnaire(self):
        self.cible = list(self.tel["p"])
        self.v_cmd = None

    async def position(self, p, lacet):
        self.cible = list(p)
        self.v_cmd = None
        if lacet is not None:
            self.tel["lacet"] = float(lacet)

    async def vitesse(self, v, lacet_vitesse):
        self.v_cmd = list(v)
        self.v_jusqua = time.monotonic() + 0.5
        self.cible = list(self.tel["p"])
        self.tel["lacet"] = (self.tel["lacet"] + lacet_vitesse * 0.1) % 360

    async def couper(self):
        self.cible, self.v_cmd = None, None
        self.publier(etat="chute", arme=False)


# ── ArduPilot Copter par MAVLink (pymavlink) ───────────────────
MASQUE_POSITION = 3576            # 0b110111111000 : position seule (ArduPilot, Guided Mode)
MASQUE_POSITION_LACET = 2552      # (Inférence) 3576 sans le bit 10 « ignorer le lacet »
MASQUE_VITESSE = 3527             # 0b110111000111 : vitesse seule
MASQUE_VITESSE_LACET = 1479       # (Inférence) 3527 sans le bit 11 « ignorer la vitesse de lacet »
FORCER = 21196                    # MAV_CMD_COMPONENT_ARM_DISARM, param2 : forcer (désarmement même en vol)


class AdaptateurMavlink(Adaptateur):
    nom = "mavlink"

    def __init__(self, cfg, repere):
        super().__init__(cfg, repere)
        self.url = cfg.get("connexion", "udpin:0.0.0.0:14550")
        self.m = None
        self.fil: threading.Thread | None = None
        self.actif = False
        self.t0 = time.monotonic()

    async def ouvrir(self, rappel):
        await super().ouvrir(rappel)
        try:
            from pymavlink import mavutil
        except ImportError as exc:
            raise ConnectionError("pymavlink requis pour l'adaptateur MAVLink : pip install pymavlink") from exc
        self.mavutil = mavutil
        self.m = await asyncio.to_thread(mavutil.mavlink_connection, self.url, source_system=255, source_component=190)
        hb = await asyncio.to_thread(self.m.wait_heartbeat, timeout=float(self.cfg.get("delai_s", 5)))
        if hb is None:
            raise ConnectionError(f"Aucun battement de cœur MAVLink sur {self.url}")
        loop = asyncio.get_running_loop()
        self.actif = True
        self.fil = threading.Thread(target=self._lire, args=(loop,), daemon=True)
        self.fil.start()

    def _lire(self, loop):
        mav = self.mavutil.mavlink
        while self.actif:
            try:
                msg = self.m.recv_match(blocking=True, timeout=0.5)
            except (OSError, ValueError):
                break
            if msg is None:
                continue
            t, maj = msg.get_type(), {}
            if t == "HEARTBEAT" and msg.get_srcSystem() == self.m.target_system:
                maj["arme"] = bool(msg.base_mode & mav.MAV_MODE_FLAG_SAFETY_ARMED)
                try:
                    maj["mode_autopilote"] = self.mavutil.mode_string_v10(msg)
                except Exception:
                    pass
                if not maj["arme"]:
                    maj["etat"] = "au_sol"
                elif self.tel.get("etat") == "au_sol":
                    maj["etat"] = "vol"
            elif t == "LOCAL_POSITION_NED":
                maj["p"] = self.repere.depuis_ned(msg.x, msg.y, msg.z)
                o = self.repere
                maj["v"] = [msg.vx * o.nord[0] + msg.vy * o.est[0], -msg.vz, msg.vx * o.nord[2] + msg.vy * o.est[2]]
            elif t == "ATTITUDE":
                maj["lacet"] = round(self.repere.lacet_depuis_ned(msg.yaw), 1)
            elif t == "SYS_STATUS" and msg.battery_remaining >= 0:
                maj["batterie"] = float(msg.battery_remaining)
            elif t == "STATUSTEXT":
                maj["texte"] = msg.text
            if maj:
                loop.call_soon_threadsafe(lambda m=maj: self.publier(**m))

    def _ms(self) -> int:
        return int((time.monotonic() - self.t0) * 1000)

    def _commande(self, cmd: int, *params: float) -> None:
        p = list(params) + [0.0] * (7 - len(params))
        self.m.mav.command_long_send(self.m.target_system, self.m.target_component, cmd, 0, *p)

    def _mode(self, nom: str) -> None:
        self.m.set_mode(self.m.mode_mapping()[nom])

    async def fermer(self):
        self.actif = False
        if self.m:
            try:
                self.m.close()
            except Exception:
                pass

    async def armer(self):
        self._mode("GUIDED")
        self._commande(self.mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)

    async def decoller(self, hauteur):
        self._commande(self.mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, float(hauteur))
        self.publier(etat="decollage")

    async def atterrir(self):
        self._mode("LAND")
        self.publier(etat="atterrissage")

    async def stationnaire(self):
        await self.position(self.tel["p"], None)

    async def position(self, p, lacet):
        n, e, b = self.repere.vers_ned(p)
        masque, cap = (MASQUE_POSITION, 0.0) if lacet is None else (MASQUE_POSITION_LACET, self.repere.lacet_vers_ned(lacet))
        self.m.mav.set_position_target_local_ned_send(self._ms(), self.m.target_system, self.m.target_component,
                                                       self.mavutil.mavlink.MAV_FRAME_LOCAL_NED, masque,
                                                       n, e, b, 0, 0, 0, 0, 0, 0, cap, 0)

    async def vitesse(self, v, lacet_vitesse):
        vn, ve, vb = self.repere.vitesse_vers_ned(v)
        masque = MASQUE_VITESSE_LACET if lacet_vitesse else MASQUE_VITESSE
        self.m.mav.set_position_target_local_ned_send(self._ms(), self.m.target_system, self.m.target_component,
                                                       self.mavutil.mavlink.MAV_FRAME_LOCAL_NED, masque,
                                                       0, 0, 0, vn, ve, vb, 0, 0, 0, 0, -math.radians(lacet_vitesse))

    async def couper(self):
        self._commande(self.mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, FORCER)
        self.publier(etat="chute", arme=False)


# ── Tello (SDK texte, UDP) ─────────────────────────────────────
class AdaptateurTello(Adaptateur):
    """Commandes relatives au repère du drone ; position estimée à l'estime (le Tello ne se localise pas
    dans la salle) : à réserver aux répétitions de trajectoire, avec un observateur, à vitesse réduite."""
    nom = "tello"
    flux_position = False
    position_mesuree = False

    def __init__(self, cfg, repere):
        super().__init__(cfg, repere)
        self.hote = cfg.get("hote", "192.168.10.1")
        self.port = int(cfg.get("port", 8889))
        self.port_etat = int(cfg.get("port_etat", 8890))
        self.echelle = float(cfg.get("rc_echelle_m_s", 1.0))     # (Inférence) vitesse correspondant à rc 100
        self.signe_lateral = -1 if cfg.get("inverser_rc_lateral") else 1
        self.file: asyncio.Queue[str] = asyncio.Queue()
        self.reponses: asyncio.Queue[str] = asyncio.Queue()
        self.taches: list[asyncio.Task] = []
        self.dernier_envoi = 0.0

    async def ouvrir(self, rappel):
        await super().ouvrir(rappel)
        loop = asyncio.get_running_loop()
        adapt = self

        class Cmd(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):
                adapt.reponses.put_nowait(data.decode("utf-8", "replace").strip())

        class Etat(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):
                adapt._etat(data.decode("utf-8", "replace"))

        self.tr, _ = await loop.create_datagram_endpoint(Cmd, local_addr=("0.0.0.0", int(self.cfg.get("port_local", 0))))
        try:
            self.tr_etat, _ = await loop.create_datagram_endpoint(Etat, local_addr=("0.0.0.0", self.port_etat))
        except OSError:
            self.tr_etat = None
        if await self._envoyer("command") != "ok":
            raise ConnectionError(f"Le Tello ({self.hote}:{self.port}) ne répond pas « ok » à « command »")
        self.taches = [asyncio.create_task(self._garder_en_vie())]
        self.publier(mode_autopilote="SDK")

    def _etat(self, s: str) -> None:
        champs = dict(x.split(":", 1) for x in s.strip().strip(";").split(";") if ":" in x)
        maj: dict[str, Any] = {}
        try:
            if "bat" in champs:
                maj["batterie"] = float(champs["bat"])
            if "h" in champs:
                p = list(self.tel["p"])
                p[1] = self.repere.o[1] + float(champs["h"]) / 100
                maj["p"] = p
        except ValueError:
            return
        if maj:
            self.publier(**maj)

    async def _envoyer(self, texte: str, attendre: float = 7.0) -> str | None:
        while not self.reponses.empty():
            self.reponses.get_nowait()
        self.tr.sendto(texte.encode(), (self.hote, self.port))
        self.dernier_envoi = time.monotonic()
        if attendre <= 0:
            return None
        try:
            return await asyncio.wait_for(self.reponses.get(), attendre)
        except asyncio.TimeoutError:
            return None

    async def _garder_en_vie(self):
        # Le Tello atterrit seul après 15 s sans commande ; une question anodine le maintient tant que le pont vit.
        while True:
            await asyncio.sleep(1.0)
            if time.monotonic() - self.dernier_envoi > 5:
                await self._envoyer("battery?", attendre=2)

    async def fermer(self):
        for t in self.taches:
            t.cancel()
        self.tr.close()
        if self.tr_etat:
            self.tr_etat.close()

    async def armer(self):
        self.publier(arme=True)

    async def decoller(self, hauteur):
        r = await self._envoyer("takeoff", 20)
        if r != "ok":
            raise ConnectionError(f"Tello : décollage refusé ({r})")
        p = list(self.tel["p"])
        p[1] = self.repere.o[1] + 0.8          # le décollage automatique du Tello monte à environ 0,8 m (estimé)
        self.publier(etat="vol", p=p, arme=True)
        if hauteur > 1.0:
            await self.aller([p[0], self.repere.o[1] + hauteur, p[2]], None, 0.5)

    async def atterrir(self):
        self.publier(etat="atterrissage")
        await self._envoyer("land", 20)
        p = list(self.tel["p"])
        p[1] = self.repere.o[1]
        self.publier(etat="au_sol", arme=False, p=p)

    async def stationnaire(self):
        await self._envoyer("stop", 3)

    async def aller(self, p, lacet, vitesse):
        """Déplacement relatif décomposé en avant/arrière, droite/gauche, haut/bas (≥ 20 cm chacun), dans le repère
        du drone ; position estimée mise à jour par les déplacements effectivement acceptés."""
        q = list(self.tel["p"])
        d = [p[i] - q[i] for i in range(3)]
        psi = math.radians(self.tel["lacet"])
        avant = d[0] * math.sin(psi) + d[2] * math.cos(psi)
        droite = d[0] * -math.cos(psi) + d[2] * math.sin(psi)
        for cmd_pos, cmd_neg, val, axe in (("forward", "back", avant, "av"), ("right", "left", droite, "dr"),
                                            ("up", "down", d[1], "h")):
            cm = int(round(abs(val) * 100))
            if cm < 20:
                continue
            cm = min(cm, 500)
            r = await self._envoyer(f"{cmd_pos if val > 0 else cmd_neg} {cm}", 15)
            if r != "ok":
                raise ConnectionError(f"Tello : « {cmd_pos if val > 0 else cmd_neg} {cm} » refusé ({r})")
            s = math.copysign(cm / 100, val)
            if axe == "av":
                q[0] += s * math.sin(psi); q[2] += s * math.cos(psi)
            elif axe == "dr":
                q[0] += s * -math.cos(psi); q[2] += s * math.sin(psi)
            else:
                q[1] += s
            self.publier(p=list(q))
        if lacet is not None:
            ecart = (float(lacet) - self.tel["lacet"] + 180) % 360 - 180
            if abs(ecart) >= 1:
                # lacet du théâtre croissant = sens antihoraire vu de dessus ; « cw » = sens horaire
                await self._envoyer(f"{'ccw' if ecart > 0 else 'cw'} {int(round(abs(ecart)))}", 10)
                self.publier(lacet=float(lacet) % 360)

    async def vitesse(self, v, lacet_vitesse):
        psi = math.radians(self.tel["lacet"])
        avant = v[0] * math.sin(psi) + v[2] * math.cos(psi)
        droite = v[0] * -math.cos(psi) + v[2] * math.sin(psi)
        pc = lambda x: max(-100, min(100, int(round(x / self.echelle * 100))))
        await self._envoyer(f"rc {self.signe_lateral * pc(droite)} {pc(avant)} {pc(v[1])} "
                            f"{max(-100, min(100, int(round(-lacet_vitesse / 90 * 100))))}", attendre=0)

    async def urgence(self):
        await self.atterrir()

    async def couper(self):
        await self._envoyer("emergency", 2)
        self.publier(etat="coupe", arme=False)


# ── JSON par ligne vers un ordinateur compagnon ────────────────
class AdaptateurLigneJSON(Adaptateur):
    """Messages {"t": "drone", "cmd": …} en UDP ; le compagnon répond par {"t": "tel", "p": [x, y, z], …} dans le
    repère du théâtre (PROTOCOLE.md, section Drone)."""
    nom = "ligne_json"

    def __init__(self, cfg, repere):
        super().__init__(cfg, repere)
        self.hote = cfg.get("hote", "127.0.0.1")
        self.port = int(cfg.get("port", 9750))

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
                        adapt.publier(**{k: m[k] for k in ("p", "v", "lacet", "batterie", "arme", "etat") if k in m})

        self.tr, _ = await loop.create_datagram_endpoint(P, local_addr=("0.0.0.0", int(self.cfg.get("port_local", 0))))
        self._envoyer({"cmd": "hello"})

    def _envoyer(self, m: dict) -> None:
        self.tr.sendto((json.dumps({"t": "drone", **m}, ensure_ascii=False) + "\n").encode(), (self.hote, self.port))

    async def fermer(self):
        self.tr.close()

    async def armer(self):
        self._envoyer({"cmd": "armer"})

    async def decoller(self, hauteur):
        self._envoyer({"cmd": "decoller", "hauteur": hauteur})

    async def atterrir(self):
        self._envoyer({"cmd": "atterrir"})

    async def stationnaire(self):
        self._envoyer({"cmd": "stationnaire"})

    async def position(self, p, lacet):
        self._envoyer({"cmd": "position", "p": [round(x, 3) for x in p], "lacet": lacet})

    async def vitesse(self, v, lacet_vitesse):
        self._envoyer({"cmd": "vitesse", "v": [round(x, 3) for x in v], "lacet_vitesse": lacet_vitesse})

    async def urgence(self):
        self._envoyer({"cmd": "urgence"})

    async def couper(self):
        self._envoyer({"cmd": "couper"})


ADAPTATEURS: dict[str, type[Adaptateur]] = {c.nom: c for c in (AdaptateurSimulation, AdaptateurMavlink, AdaptateurTello,
                                                              AdaptateurLigneJSON)}
DESCRIPTIONS = {
    "simulation": "Drone simulé dans le pont (toute la chaîne, sans appareil)",
    "mavlink": "ArduPilot Copter par MAVLink (GUIDED) — drones à autopilote ouvert, caméra 4K par flux séparé",
    "tello": "Tello (SDK texte en UDP) — drone de répétition, caméra 720p, position estimée",
    "ligne_json": "JSON par ligne en UDP vers un ordinateur compagnon (drone maison, Crazyflie, capture de mouvement)",
}
