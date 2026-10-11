"""Pilote MQTT : le langage unifié transporté sur un courtier MQTT (Mosquitto, etc.).

Sujets : {prefixe}/{id}/cmd (pont → robot, JSON unifié) et {prefixe}/{id}/tel (robot → pont : info, tel, err).
Convient aux microcontrôleurs Wi-Fi (ESP32 avec PubSubClient) et aux installations domotiques ou
scénographiques déjà organisées autour d'un courtier. L'arrêt d'urgence est publié avec la qualité de service 1.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from .base import Pilote


class PiloteMQTT(Pilote):
    type = "mqtt"

    def __init__(self, desc, client_factory=None):
        super().__init__(desc)
        c = desc.connexion
        self.hote, self.port = c.get("hote", "127.0.0.1"), int(c.get("port", 1883))
        prefixe = c.get("prefixe", "robo-scene").rstrip("/")
        self.s_cmd, self.s_tel = f"{prefixe}/{desc.id}/cmd", f"{prefixe}/{desc.id}/tel"
        self.utilisateur, self.mot_de_passe = c.get("utilisateur"), c.get("mot_de_passe")
        self._factory = client_factory
        self._client = None

    async def ouvrir(self) -> None:
        loop = asyncio.get_running_loop()
        if self._factory:
            self._client = self._factory()
        else:
            import paho.mqtt.client as mqtt
            self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"robo-scene-pont-{self.desc.id}")
            if self.utilisateur:
                self._client.username_pw_set(self.utilisateur, self.mot_de_passe)
        connecte = asyncio.Event()

        def sur_connexion(client, userdata, flags, code, props=None):
            client.subscribe(self.s_tel, qos=1)
            loop.call_soon_threadsafe(connecte.set)

        def sur_message(client, userdata, message):
            try:
                d = json.loads(message.payload.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return
            if isinstance(d, dict) and "t" in d:
                self.pousser_depuis_fil(loop, d)

        def sur_deconnexion(client, userdata, *a):
            self.pousser_depuis_fil(loop, {"t": "lien", "etat": "perdu", "msg": "courtier MQTT déconnecté"})

        self._client.on_connect, self._client.on_message = sur_connexion, sur_message
        self._client.on_disconnect = sur_deconnexion
        self._client.connect(self.hote, self.port, keepalive=10)
        self._client.loop_start()
        await asyncio.wait_for(connecte.wait(), 5)

    async def envoyer(self, msg: dict[str, Any]) -> None:
        qos = 1 if msg.get("t") in ("estop", "reset") else 0
        self._client.publish(self.s_cmd, json.dumps(msg, separators=(",", ":")), qos=qos)

    async def fermer(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
