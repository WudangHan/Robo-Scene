"""Pilote « TonyPi par JSON-RPC » : relie le pont au serveur JSON-RPC que Hiwonder lance au démarrage du TonyPi
(RPCServer.py, port 9030, service tonypi.service ; c'est le canal de l'application mobile et du logiciel PC).
Rien à installer sur le robot.

Méthodes de Hiwonder employées (github.com/Hiwonder/TonyPi, RPCServer.py, consulté le 20 octobre 2026) :
    SetBusServoPulse(durée_ms, n, id1, pos1, …)   servos de bus 1 à 16 (le serveur refuse 17 et 18 : les mains)
    set_pwm_servo(durée_ms, n, id1, µs1, …)        servos PWM 1 et 2 (tête), impulsion brute 500–2500
    RunAction(nom, fois)                           groupe d'actions (0 = en boucle) ; ignoré si un geste tourne déjà
    StopBusServo("stopAction"), StopActionGroup("stopActionGroup")   arrêt du geste en cours
    GetBusServosPulse("angularReadback")           positions des servos 1 à 15 (le serveur s'arrête à 15)

Limites de ce mode (celles du serveur de Hiwonder) : ni mains, ni batterie, ni centrale inertielle, ni capteurs, ni
voix. Pour tout le robot : pilote embarqué sdk/python/tonypi_embarque.py (profil robots/tonypi_pro.toml).
L'arrêt d'urgence interrompt le geste et la marche ; les servos gardent la dernière position commandée (le couple
n'est jamais coupé).
"""
from __future__ import annotations

import asyncio
import itertools
from typing import Any

from .. import tonypi as T
from .base import Pilote

MARCHE = {"avant": "go_forward", "arriere": "back", "gauche": "turn_left", "droite": "turn_right"}


def mode_marche(g: float, d: float, seuil: float = 0.15) -> str | None:
    if abs(g) < seuil and abs(d) < seuil:
        return None
    if g > seuil and d > seuil and abs(g - d) < 0.35:
        return MARCHE["avant"]
    if g < -seuil and d < -seuil and abs(g - d) < 0.35:
        return MARCHE["arriere"]
    return MARCHE["droite"] if g > d else MARCHE["gauche"]


class PiloteTonyPiRPC(Pilote):
    type = "tonypi_rpc"

    def __init__(self, desc, appeler=None):
        super().__init__(desc)
        self.url = desc.connexion.get("url", "http://192.168.149.1:9030")
        self.periode = float(desc.connexion.get("periode_lecture_s", 1.0))
        self._appeler_injecte = appeler                 # injectable pour les essais
        self._session = None
        self._ids = itertools.count(1)
        self._tache: asyncio.Task | None = None
        self.cibles = list(desc.repos)
        self.estop = False
        self.marche: str | None = None
        self.geste_en_cours: str | None = None
        self._fin_geste: asyncio.Task | None = None
        self._mains_signalees = False

    async def appeler(self, methode: str, *params: Any) -> Any:
        if self._appeler_injecte:
            return await self._appeler_injecte(methode, list(params))
        import aiohttp
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3))
        corps = {"jsonrpc": "2.0", "method": methode, "params": list(params), "id": next(self._ids)}
        async with self._session.post(self.url, json=corps) as r:
            rep = await r.json(content_type=None)
        if "error" in rep:
            raise RuntimeError(f"{methode} : {rep['error'].get('message', rep['error'])}")
        res = rep.get("result")
        if isinstance(res, list) and res and res[0] is False:
            raise RuntimeError(f"{methode} : {res[1] if len(res) > 1 else 'refus'}")
        return res

    async def ouvrir(self) -> None:
        self._tache = asyncio.create_task(self._boucle())
        self.pousser(self.info(bus="TonyPi JSON-RPC (Hiwonder)", url=self.url, gestes=self.desc.gestes_natifs))

    async def _boucle(self) -> None:
        n = 0
        while True:
            await asyncio.sleep(0.2)
            n += 1
            deg, estimee = list(self.cibles), True
            if n % max(1, int(self.periode / 0.2)) == 0 and not self.geste_en_cours:
                try:
                    res = await self.appeler("GetBusServosPulse", "angularReadback")
                    pas = res[1] if isinstance(res, list) and len(res) > 1 else []
                    for k, a in enumerate(self.desc.articulations):
                        if T.genre(a) == "bus" and 1 <= T.numero(a) <= len(pas):
                            deg[k] = T.depuis_natif(a, pas[T.numero(a) - 1])
                    self.cibles, estimee = deg, False
                    if self._lien_perdu:
                        self._lien_perdu = False
                        self.pousser({"t": "lien", "etat": "retabli"})
                except Exception as exc:                  # robot injoignable : le pont signalera une télémétrie muette
                    if not self._lien_perdu:
                        self._lien_perdu = True
                        self.pousser({"t": "lien", "etat": "perdu", "msg": str(exc)})
                    continue
            if not self._lien_perdu:
                self.pousser({"t": "tel", "ms": self.ms(), "deg": deg, "drive": [0, 0], "estop": self.estop,
                              "estimee": estimee})

    _lien_perdu = False

    async def _arreter_geste(self) -> None:
        await self.appeler("StopBusServo", "stopAction")
        await self.appeler("StopActionGroup", "stopActionGroup")
        if self.geste_en_cours:
            self.pousser({"t": "evt", "type": "geste", "nom": self.geste_en_cours, "etat": "interrompu"})
        self.geste_en_cours = self.marche = None
        if self._fin_geste:
            self._fin_geste.cancel()
        await asyncio.sleep(0.15)                          # laisse le fil du serveur se terminer avant un nouveau RunAction

    async def envoyer(self, msg: dict[str, Any]) -> None:
        t = msg.get("t")
        try:
            if t == "hello":
                self.pousser(self.info(bus="TonyPi JSON-RPC (Hiwonder)", url=self.url, gestes=self.desc.gestes_natifs))
            elif t == "estop":
                self.estop = True
                await self._arreter_geste()
            elif t == "reset":
                self.estop = False
            elif t in ("servos", "geste", "drive") and self.estop:
                self.pousser({"t": "err", "msg": "estop"})
            elif t == "servos":
                await self._servos(msg)
            elif t == "geste":
                nom = str(msg.get("nom", ""))
                if nom not in self.desc.gestes_natifs:
                    return self.pousser({"t": "err", "msg": f"geste natif hors de la liste du profil : {nom}"})
                if self.geste_en_cours:
                    await self._arreter_geste()
                await self.appeler("RunAction", nom, 1)
                self.geste_en_cours = nom
                self.pousser({"t": "evt", "type": "geste", "nom": nom, "etat": "debut"})
                self._fin_geste = asyncio.create_task(self._attendre_fin(nom))
            elif t == "drive":
                mode = mode_marche(float(msg.get("l", 0)), float(msg.get("r", 0)))
                if mode != self.marche:
                    if self.marche or self.geste_en_cours:
                        await self._arreter_geste()
                    if mode:
                        await self.appeler("RunAction", mode, 0)
                        self.marche = self.geste_en_cours = mode
                        self.pousser({"t": "evt", "type": "marche", "mode": mode})
            elif t == "geste_arret":
                await self._arreter_geste()
            elif t == "hb":
                pass
            elif t in ("dire", "lumiere", "afficher"):
                self.pousser({"t": "err", "msg": f"{t} : indisponible par le serveur JSON-RPC de Hiwonder "
                                                 "(employer le pilote embarqué)", "niveau": "info"})
            else:
                self.refuser(str(t))
        except Exception as exc:
            self.pousser({"t": "err", "msg": f"TonyPi JSON-RPC : {exc}"})

    async def _servos(self, msg: dict[str, Any]) -> None:
        if self.geste_en_cours:
            await self._arreter_geste()
        ms = max(20, int(msg.get("ms", 0)))
        bus, pwm, mains = [], [], False
        for a, v in zip(self.desc.articulations, msg["deg"]):
            if v is None:
                continue
            if T.genre(a) == "pwm":
                pwm += [T.numero(a), T.vers_natif(a, v)]
            elif T.numero(a) <= 16:
                bus += [T.numero(a), T.vers_natif(a, v)]
            else:
                mains = mains or abs(float(v) - float(a.repos)) > 0.5
        if bus:
            await self.appeler("SetBusServoPulse", ms, len(bus) // 2, *bus)
        if pwm:
            await self.appeler("set_pwm_servo", ms, len(pwm) // 2, *pwm)
        self.cibles = [float(v) if v is not None else c for v, c in zip(msg["deg"], self.cibles)]
        if mains and not self._mains_signalees:
            self._mains_signalees = True
            self.pousser({"t": "err", "msg": "mains (servos 17 et 18) : refusées par le serveur JSON-RPC de Hiwonder ; "
                                             "employer le pilote embarqué", "niveau": "info"})

    async def _attendre_fin(self, nom: str) -> None:
        """Le serveur de Hiwonder ne signale pas la fin d'un geste : durée estimée d'après le geste importé dans la
        bibliothèque (outils/hiwonder_tonypi.py), sinon 8 s."""
        from .ligne_json import _images_importees
        images = _images_importees(self.desc, nom) or []
        duree = sum(float(i.get("ms", 0)) for i in images) / 1000 or 8.0
        try:
            await asyncio.sleep(duree + 0.3)
            if self.geste_en_cours == nom:
                self.geste_en_cours = None
                self.pousser({"t": "evt", "type": "geste", "nom": nom, "etat": "fin", "duree_estimee": True})
        except asyncio.CancelledError:
            pass

    async def fermer(self) -> None:
        if self._tache:
            self._tache.cancel()
        if self._session is not None:
            await self._session.close()
