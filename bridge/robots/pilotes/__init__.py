"""Registre des pilotes : un type par famille de protocole ; ajouter un pilote = ajouter une classe ici."""
from __future__ import annotations

from .base import Pilote
from .externe import PiloteExterne
from .hiwonder_bus import PiloteHiwonderBus
from .http_rest import PiloteHTTP
from .ligne_json import PiloteLigneJSON
from .mqtt import PiloteMQTT
from .osc import PiloteOSC
from .reachy_mini import PiloteReachyMini
from .rosbridge import PiloteRosbridge
from .tonypi_rpc import PiloteTonyPiRPC

TYPES: dict[str, type[Pilote]] = {c.type: c for c in (
    PiloteLigneJSON, PiloteHiwonderBus, PiloteRosbridge, PiloteMQTT, PiloteOSC, PiloteHTTP, PiloteReachyMini,
    PiloteExterne, PiloteTonyPiRPC)}

DESCRIPTIONS = {
    "ligne_json": "JSON par ligne — série USB, TCP, UDP, WebSocket ou simulation (ESP32, Arduino, Pico, Teensy…)",
    "hiwonder_bus": "Bus de servomoteurs Hiwonder / LewanSoul (AiNex, bras xArm…)",
    "rosbridge": "ROS 1 ou ROS 2 par rosbridge (JointTrajectory, Twist, JointState)",
    "mqtt": "Courtier MQTT (microcontrôleurs Wi-Fi, installations scénographiques)",
    "osc": "Open Sound Control (Max, Pure Data, TouchDesigner, Isadora, QLab)",
    "http": "Interface REST d'un robot (gabarits de requêtes et pointeurs JSON)",
    "reachy_mini": "Reachy Mini par sa trousse Python (pose de tête, corps, antennes)",
    "tonypi_rpc": "Hiwonder TonyPi par son serveur JSON-RPC (port 9030) : rien à installer sur le robot",
    "externe": "Programme pilote dans n'importe quel langage (Python, JavaScript, C++, Rust…), par stdin/stdout",
}


def creer(desc, **kw) -> Pilote:
    try:
        cls = TYPES[desc.pilote]
    except KeyError:
        raise ValueError(f"Pilote inconnu « {desc.pilote} » ; disponibles : {', '.join(TYPES)}") from None
    return cls(desc, **kw)
