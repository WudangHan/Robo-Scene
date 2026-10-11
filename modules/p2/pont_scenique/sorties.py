"""Sorties du pont scénique : son (QLab par OSC), lumière (sACN / E1.31), OSC libre, gestes.

Chaque sortie peut fonctionner « à blanc » : elle consigne ce qu'elle aurait envoyé, sans réseau.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

PORT_QLAB = 53000  # port OSC d'écoute de QLab (dictionnaire OSC de QLab 5)


class SortieOSC:
    """Envoi de messages OSC (python-osc). `envoyer` peut être remplacé pour les essais."""

    def __init__(self, hote: str = "127.0.0.1", port: int = PORT_QLAB, a_blanc: bool = False, journal=print):
        self.a_blanc, self.journal = a_blanc, journal
        self.client = None
        if not a_blanc:
            from pythonosc.udp_client import SimpleUDPClient
            self.client = SimpleUDPClient(hote, port)
        self.cible = f"{hote}:{port}"

    def envoyer(self, adresse: str, *arguments):
        self.journal(f"OSC → {self.cible} {adresse} {list(arguments)}" + (" (à blanc)" if self.a_blanc else ""))
        if self.client is not None:
            self.client.send_message(adresse, list(arguments) if arguments else [])


class SortieQLab(SortieOSC):
    def demarrer_cue(self, numero: str):
        self.envoyer(f"/cue/{numero}/start")

    def panique(self):
        self.envoyer("/panic")  # fondu bref puis arrêt (dictionnaire OSC de QLab 5)


class SortieDMX:
    """Lumière par sACN (E1.31), avec transferts calculés ici à 30 Hz.

    `emettre(niveaux)` reçoit les 512 niveaux de l'univers ; par défaut, la bibliothèque `sacn`.
    """

    FREQ = 30.0

    def __init__(self, univers: int = 1, multicast: bool = True, ip_unicast: str | None = None,
                 a_blanc: bool = False, journal=print, emettre: Callable[[tuple], None] | None = None,
                 port_local: int = 5568):
        self.univers, self.a_blanc, self.journal = univers, a_blanc, journal
        self.niveaux = [0] * 512
        self._verrou = threading.Lock()
        self._fondus: dict[int, tuple[float, float, float, float]] = {}  # canal -> (départ, arrivée, t0, durée)
        self._arret = threading.Event()
        self._emetteur = None
        if emettre is not None:
            self._emettre = emettre
        elif a_blanc:
            self._emettre = lambda niv: None
        else:
            import sacn
            self._emetteur = sacn.sACNsender(bind_port=port_local)
            self._emetteur.start()
            self._emetteur.activate_output(univers)
            self._emetteur[univers].multicast = multicast
            if ip_unicast:
                self._emetteur[univers].multicast = False
                self._emetteur[univers].destination = ip_unicast
            self._emettre = lambda niv: setattr(self._emetteur[univers], "dmx_data", niv)
        self._fil = threading.Thread(target=self._boucle, daemon=True)
        self._fil.start()

    def transferer(self, cibles: dict[int, int], duree: float):
        """Fait passer chaque canal de son niveau actuel au niveau cible en `duree` secondes (linéaire)."""
        self.journal(f"DMX univers {self.univers} : {cibles} en {duree} s" + (" (à blanc)" if self.a_blanc else ""))
        t0 = time.monotonic()
        with self._verrou:
            for canal, cible in cibles.items():
                self._fondus[canal] = (float(self.niveaux[canal - 1]), float(cible), t0, max(duree, 0.0))

    def niveau(self, canal: int) -> int:
        with self._verrou:
            return self.niveaux[canal - 1]

    def figer(self):
        """Arrête les transferts en cours en conservant les niveaux atteints (aucun noir brutal)."""
        with self._verrou:
            self._fondus.clear()
        self.journal("DMX : transferts figés, niveaux conservés")

    def _boucle(self):
        while not self._arret.is_set():
            maintenant = time.monotonic()
            with self._verrou:
                for canal, (a, b, t0, d) in list(self._fondus.items()):
                    s = 1.0 if d == 0 else min(1.0, (maintenant - t0) / d)
                    self.niveaux[canal - 1] = int(round(a + s * (b - a)))
                    if s >= 1.0:
                        del self._fondus[canal]
                donnees = tuple(self.niveaux)
            self._emettre(donnees)
            time.sleep(1.0 / self.FREQ)

    def fermer(self):
        self._arret.set()
        self._fil.join(timeout=1)
        if self._emetteur is not None:
            self._emetteur.stop()


class SortieGestes:
    """Gestes du robot, exclusivement par l'exécuteur à bibliothèque fermée (gestes_scene)."""

    def __init__(self, executeur, cible: str = "sim", vitesse: str = "lente", mini=None,
                 a_blanc: bool = False, journal=print):
        self.ex, self.cible, self.vitesse, self.mini = executeur, cible, vitesse, mini
        self.a_blanc, self.journal = a_blanc, journal
        self.suspendu = False
        self._verrou = threading.Lock()  # un seul geste à la fois

    def jouer(self, nom: str, repere: str):
        from gestes_scene import RefusExecution
        if self.suspendu:
            self.journal(f"Geste « {nom} » ignoré : gestes suspendus après ARRÊT")
            return
        try:
            p = self.ex.proposer(nom, source=f"conduite, repère {repere}")
            self.ex.autoriser(p, self.cible, self.vitesse)
        except RefusExecution as e:
            self.journal(f"⚠ Geste refusé au repère {repere} : {e}")
            return
        if self.a_blanc or self.mini is None:
            self.journal(f"Geste « {nom} » ({self.cible}, {self.vitesse}) — à blanc")
            return
        with self._verrou:
            # Le GO de la régie vaut confirmation de l'opérateur pour ce geste autorisé.
            self.ex.executer(p, confirmation_operateur=True, cible=self.cible, vitesse=self.vitesse, mini=self.mini)
