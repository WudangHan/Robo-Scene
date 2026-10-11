"""Pilote embarqué pour l'AiNex (à exécuter sur le Raspberry Pi du robot) : langage unifié en TCP, bus de
servomoteurs Hiwonder en série (protocole LewanSoul/LX).

    python3 ainex_embarque.py --port-serie /dev/ttyAMA0 --tcp 3333

Profil côté pont : pilote = "ligne_json", [connexion] mode = "tcp", hote = "<adresse du Pi>", port = 3333.

⚠ À vérifier à réception (fiche F-07) : le port série qui atteint le bus, le protocole de la carte
contrôleur (LX direct ou protocole propre de la carte), les numéros de servos et leurs bornes. Tant que ces
vérifications ne sont pas faites, lancer avec --a-blanc : les trames sont affichées, rien n'est envoyé.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from robo_scene_sdk import PiloteRobot  # noqa: E402

DIFFUSION, MOVE_TIME_WRITE, MOVE_STOP = 254, 1, 12


def trame(ident: int, commande: int, params: bytes = b"") -> bytes:
    n = 3 + len(params)
    return b"\x55\x55" + bytes([ident, n, commande]) + params + bytes([(~(ident + n + commande + sum(params))) & 0xFF])


class AiNex(PiloteRobot):
    nom = "AiNex"
    # Bornes provisoires et prudentes (±20° autour du centre) — à remplacer après relevé, servo par servo
    articulations = [(f"servo_{i:02d}", -20.0, 20.0, 0.0) for i in range(1, 25)]
    propulsion = False

    def __init__(self, port_serie: str, a_blanc: bool):
        super().__init__()
        self.a_blanc = a_blanc
        self.serie = None
        if not a_blanc:
            import serial
            self.serie = serial.Serial(port_serie, 115200, timeout=0.05)

    def _ecrire_bus(self, octets: bytes) -> None:
        if self.a_blanc:
            print("[à blanc]", octets.hex(" "), file=sys.stderr)
        else:
            self.serie.write(octets)

    def appliquer_servos(self, deg, ms):
        octets = b"".join(trame(i + 1, MOVE_TIME_WRITE, struct.pack("<HH", max(0, min(1000, round(500 + d * 1000 / 240))),
                                                                    max(0, min(30000, ms))))
                          for i, d in enumerate(deg))
        self._ecrire_bus(octets)

    def figer(self):
        self._ecrire_bus(trame(DIFFUSION, MOVE_STOP))   # fige à la position courante ; jamais de coupure du couple


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port-serie", default="/dev/ttyAMA0")
    ap.add_argument("--tcp", type=int, default=3333)
    ap.add_argument("--a-blanc", action="store_true")
    a = ap.parse_args()
    AiNex(a.port_serie, a.a_blanc).servir_tcp(a.tcp)
