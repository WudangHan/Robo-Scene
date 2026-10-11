"""Pilote « bus de servomoteurs Hiwonder » (protocole LewanSoul / LX), pour l'AiNex et tout robot à servos
de bus Hiwonder raccordé par une carte USB-bus (BusLinker) ou par le port série d'un ordinateur embarqué.

Trame (protocole LewanSoul, repris par la bibliothèque libre HiWonder-BusLinker-servo-bus, licence MIT) :
    0x55 0x55 | ID | LONGUEUR | COMMANDE | PARAMÈTRES… | SOMME
    LONGUEUR = 3 + nombre de paramètres ; SOMME = octet de poids faible de ~(ID + LONGUEUR + COMMANDE + Σ paramètres)
Commandes employées : 1 SERVO_MOVE_TIME_WRITE (position 0–1000 pour 0–240°, durée en ms, petit-boutiste),
12 SERVO_MOVE_STOP, 27 SERVO_VIN_READ (mV), 28 SERVO_POS_READ (position signée). Identifiant de diffusion : 254.

Points à vérifier sur le robot réel (fiche fournisseur F-07 : spécifications du fabricant non vérifiées) :
* l'AiNex relie ses 24 servos à une carte contrôleur ; selon la carte, le Raspberry Pi parle au bus par le
  protocole LX ou par le protocole propre de la carte. Ce pilote vise le protocole LX ; pour l'autre cas,
  exécuter le pilote embarqué (sdk/python, exemple ainex_embarque.py) sur le Raspberry Pi et relier le pont
  en « ligne JSON » TCP ;
* l'ordre des octets des réponses varie selon la carte (la bibliothèque citée signale des réponses
  différentes de la documentation avec la BusLinker v2.5) : paramètre `ordre_octets_lecture`.

Sécurité : l'arrêt d'urgence envoie SERVO_MOVE_STOP en diffusion, ce qui fige les servos À LEUR POSITION.
Couper le couple (LOAD_OR_UNLOAD) ferait tomber un robot bipède : ce pilote ne le fait jamais ; l'arrêt
matériel (coupure de l'alimentation) reste exigé par le plan de prévention P2.1, robot sur support ou au sol.
"""
from __future__ import annotations

import asyncio
import struct
import threading
import time
from typing import Any

from .base import Pilote

ENTETE = b"\x55\x55"
DIFFUSION = 254
MOVE_TIME_WRITE, MOVE_STOP, VIN_READ, POS_READ = 1, 12, 27, 28
PAS_MAX, ANGLE_MAX = 1000, 240.0


def somme_controle(ident: int, longueur: int, commande: int, params: bytes) -> int:
    return (~(ident + longueur + commande + sum(params))) & 0xFF


def trame(ident: int, commande: int, params: bytes = b"") -> bytes:
    if not 0 <= ident <= DIFFUSION:
        raise ValueError(f"identifiant de servo hors de 0–254 : {ident}")
    longueur = 3 + len(params)
    return ENTETE + bytes([ident, longueur, commande]) + params + bytes([somme_controle(ident, longueur, commande, params)])


def lire_trame(flux: bytes) -> tuple[int, int, bytes, bytes] | None:
    """Extrait la première trame valide de `flux` ; renvoie (id, commande, paramètres, reste) ou None."""
    i = flux.find(ENTETE)
    while i >= 0:
        if len(flux) - i < 6:
            return None
        ident, longueur, commande = flux[i + 2], flux[i + 3], flux[i + 4]
        n = longueur - 3
        fin = i + 5 + n                      # position de l'octet de somme
        if n >= 0:
            if len(flux) <= fin:
                return None
            params = flux[i + 5:fin]
            if flux[fin] == somme_controle(ident, longueur, commande, params):
                return ident, commande, params, flux[fin + 1:]
        i = flux.find(ENTETE, i + 1)
    return None


def deg_vers_pas(deg: float, zero: float = 500.0, sens: int = 1) -> int:
    return max(0, min(PAS_MAX, int(round(zero + sens * deg * PAS_MAX / ANGLE_MAX))))


def pas_vers_deg(pas: float, zero: float = 500.0, sens: int = 1) -> float:
    return round(sens * (pas - zero) * ANGLE_MAX / PAS_MAX, 2)


def trame_mouvement(ident: int, pas: int, ms: int) -> bytes:
    return trame(ident, MOVE_TIME_WRITE, struct.pack("<HH", pas, max(0, min(30000, int(ms)))))


class PiloteHiwonderBus(Pilote):
    type = "hiwonder_bus"

    def __init__(self, desc, serie=None):
        super().__init__(desc)
        c = desc.connexion
        self.port, self.debit = c.get("port_serie", "/dev/ttyUSB0"), int(c.get("debit", 115200))
        self.ordre = "<" if c.get("ordre_octets_lecture", "petit") == "petit" else ">"
        self.periode = float(c.get("periode_lecture_s", 0.15))
        self._serie = serie                      # injectable pour les essais
        self._verrou = threading.Lock()
        self._actif = False
        self._estop = False
        self._cibles = list(desc.repos)
        self.ids = [a.id for a in desc.articulations]
        if any(i is None for i in self.ids):
            raise ValueError("Chaque articulation d'un robot Hiwonder doit porter le numéro de son servo (id)")

    async def ouvrir(self) -> None:
        if self._serie is None:
            import serial
            self._serie = serial.Serial(self.port, self.debit, timeout=0.05)
        self._actif = True
        loop = asyncio.get_running_loop()
        threading.Thread(target=self._lecture, args=(loop,), daemon=True).start()
        self.pousser(self.info(bus="LewanSoul/LX", ids=self.ids))

    def _ecrire(self, octets: bytes) -> None:
        with self._verrou:
            self._serie.write(octets)

    def _demander(self, ident: int, commande: int) -> bytes | None:
        with self._verrou:
            try:
                self._serie.reset_input_buffer()
            except AttributeError:
                pass
            self._serie.write(trame(ident, commande))
            tampon, t0 = b"", time.monotonic()
            while time.monotonic() - t0 < 0.03:
                tampon += self._serie.read(16) or b""
                r = lire_trame(tampon)
                if r and r[0] == ident and r[1] == commande:
                    return r[2]
        return None

    def _lecture(self, loop) -> None:
        """Lit cycliquement la position de chaque servo et la tension ; publie une télémétrie unifiée."""
        while self._actif:
            deg = []
            for a in self.desc.articulations:
                p = self._demander(a.id, POS_READ)
                if p and len(p) >= 2:
                    pas = struct.unpack(self.ordre + "h", p[:2])[0]
                    deg.append(pas_vers_deg(pas, a.zero if a.zero is not None else 500.0, a.sens))
                else:
                    deg.append(None)
            v = self._demander(self.ids[0], VIN_READ)
            vbat = round(struct.unpack(self.ordre + "H", v[:2])[0] / 1000, 2) if v and len(v) >= 2 else None
            self.pousser_depuis_fil(loop, {"t": "tel", "ms": self.ms(), "deg": deg, "drive": [0, 0],
                                           "vbat": vbat, "estop": self._estop, "estimee": any(d is None for d in deg)})
            time.sleep(self.periode)

    async def envoyer(self, msg: dict[str, Any]) -> None:
        t = msg.get("t")
        if t == "hello":
            self.pousser(self.info(bus="LewanSoul/LX", ids=self.ids))
        elif t == "estop":
            self._estop = True
            await asyncio.to_thread(self._ecrire, trame(DIFFUSION, MOVE_STOP))
        elif t == "reset":
            self._estop = False
        elif t == "servos":
            if self._estop:
                self.pousser({"t": "err", "msg": "estop"})
                return
            ms = int(msg.get("ms", 0))
            octets = b"".join(trame_mouvement(a.id, deg_vers_pas(float(d), a.zero if a.zero is not None else 500.0,
                                                                  a.sens), ms)
                              for a, d in zip(self.desc.articulations, msg["deg"]))
            self._cibles = list(msg["deg"])
            await asyncio.to_thread(self._ecrire, octets)
        elif t == "drive":
            if msg.get("l") or msg.get("r"):
                self.refuser("propulsion (la marche d'un bipède relève de son générateur de démarche)")
        elif t == "hb":
            pass
        else:
            self.refuser(str(t))

    async def fermer(self) -> None:
        self._actif = False
        if self._serie is not None and hasattr(self._serie, "close"):
            self._serie.close()
