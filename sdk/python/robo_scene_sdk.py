"""Trousse Python pour écrire le pilote d'un robot ROBO-SCÈNE (langage unifié, PROTOCOLE.md v2).

Sans dépendance. Un pilote hérite de `PiloteRobot`, déclare ses articulations et redéfinit les méthodes
`appliquer_servos`, `appliquer_propulsion`, `figer` et, au besoin, `lire_etat`. La trousse se charge du
reste : lecture des commandes, bornage local, chien de garde (500 ms sans message → propulsion coupée),
verrou d'arrêt jusqu'à « reset », télémétrie à 20 Hz.

Deux façons de le relier au pont :
* programme externe (profil : pilote = "externe") : `PiloteRobot.executer()` lit stdin et écrit stdout ;
* serveur TCP embarqué (profil : pilote = "ligne_json", mode = "tcp") : `PiloteRobot.servir_tcp(3333)`,
  par exemple sur le Raspberry Pi d'un AiNex.
"""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
from typing import Any, Callable


class PiloteRobot:
    nom = "ROBOT"
    version = "1.0.0"
    articulations: list[tuple[str, float, float, float]] = []   # (nom, min, max, repos)
    propulsion = False
    chien_de_garde_s = 0.5
    periode_tel_s = 0.05

    def __init__(self):
        self.deg = [a[3] for a in self.articulations]
        self.roues = [0.0, 0.0]
        self.estop = False
        self._dernier = time.monotonic()
        self._t0 = time.monotonic()
        self._ecrire: Callable[[str], None] = lambda s: None
        self._verrou = threading.Lock()

    # ── À redéfinir pour le matériel ────────────────────────
    def appliquer_servos(self, deg: list[float], ms: int) -> None:
        """Ordonner aux servos d'atteindre `deg` en `ms` millisecondes."""

    def appliquer_propulsion(self, gauche: float, droite: float) -> None:
        """Commande des roues, de −1 à 1."""

    def figer(self) -> None:
        """Arrêt immédiat : roues à zéro, servos figés à leur position (ne pas couper le couple d'un bipède)."""

    def geste(self, nom: str) -> bool:
        """Geste natif du robot ; renvoyer False s'il n'existe pas."""
        return False

    def arreter_geste(self) -> None:
        """Interrompre le geste natif en cours (v2.1), sans verrou d'arrêt."""

    def dire(self, texte: str) -> bool:
        """Synthèse vocale embarquée (v2) ; renvoyer False si le robot n'en dispose pas."""
        return False

    def lumiere(self, m: dict[str, Any]) -> bool:
        """Lumières du robot (v2.1) : m["rgb"] = [r, g, b] (0–255), m.get("ou") ; False si non pris en charge."""
        return False

    def afficher(self, m: dict[str, Any]) -> bool:
        """Afficheur du robot (v2.1) : m["texte"] ou m["motif"] ; False si non pris en charge."""
        return False

    def info_extra(self) -> dict[str, Any]:
        """Champs ajoutés au message « info » (gestes natifs, capacités…)."""
        return {}

    def lire_etat(self) -> dict[str, Any]:
        """Télémétrie supplémentaire (vbat, dist, pose…) ; par défaut, rien."""
        return {}

    def evenement(self, type_: str, **donnees: Any) -> None:
        """Événement ponctuel vers le pont (v2.1) : chute, toucher, bouton, manette, geste_fin…"""
        self._envoyer({"t": "evt", "type": type_, "ms": int((time.monotonic() - self._t0) * 1000), **donnees})

    # ── Mécanique commune ───────────────────────────────────
    def _envoyer(self, d: dict[str, Any]) -> None:
        with self._verrou:
            self._ecrire(json.dumps(d, separators=(",", ":"), ensure_ascii=False) + "\n")

    def info(self) -> dict[str, Any]:
        return {"t": "info", "nom": self.nom, "fw": f"sdk-python-{self.version}", "servos": len(self.articulations),
                "propulsion": self.propulsion, "articulations": [a[0] for a in self.articulations], **self.info_extra()}

    def traiter(self, ligne: str) -> None:
        ligne = ligne.strip()
        if not ligne.startswith("{"):
            return
        try:
            m = json.loads(ligne)
        except json.JSONDecodeError:
            return                           # ligne illisible : ignorée, jamais interprétée partiellement
        self._dernier = time.monotonic()
        t = m.get("t")
        if t == "hello":
            self._envoyer(self.info())
        elif t == "estop":
            self.estop = True
            self.roues = [0.0, 0.0]
            self.figer()
        elif t == "reset":
            self.estop = False
        elif t in ("servos", "drive", "geste", "dire") and self.estop:
            self._envoyer({"t": "err", "msg": "estop"})
        elif t == "servos":
            deg = m.get("deg", [])
            if len(deg) != len(self.articulations):
                self._envoyer({"t": "err", "msg": "nombre d'angles incorrect"})
                return
            # Bornage local, indépendant du pont (défense en profondeur)
            self.deg = [max(a[1], min(a[2], float(d))) for a, d in zip(self.articulations, deg)]
            self.appliquer_servos(self.deg, int(m.get("ms", 0)))
        elif t == "drive" and self.propulsion:
            self.roues = [max(-1.0, min(1.0, float(m.get("l", 0)))), max(-1.0, min(1.0, float(m.get("r", 0))))]
            self.appliquer_propulsion(*self.roues)
        elif t == "geste":
            if not self.geste(str(m.get("nom", ""))):
                self._envoyer({"t": "err", "msg": f"geste natif inconnu : {m.get('nom')}"})
        elif t == "geste_arret":
            self.arreter_geste()
        elif t == "dire":
            if not self.dire(str(m.get("texte", ""))[:500]):
                self._envoyer({"t": "err", "msg": "synthèse vocale embarquée indisponible", "niveau": "info"})
        elif t == "lumiere":
            if not self.lumiere(m):
                self._envoyer({"t": "err", "msg": "lumières non prises en charge", "niveau": "info"})
        elif t == "afficher":
            if not self.afficher(m):
                self._envoyer({"t": "err", "msg": "afficheur non pris en charge", "niveau": "info"})

    def _boucle_tel(self, actif: Callable[[], bool]) -> None:
        while actif():
            if time.monotonic() - self._dernier > self.chien_de_garde_s and any(self.roues):
                self.roues = [0.0, 0.0]
                self.appliquer_propulsion(0.0, 0.0)
            self._envoyer({"t": "tel", "ms": int((time.monotonic() - self._t0) * 1000),
                           "deg": [round(d, 1) for d in self.deg], "drive": self.roues, "estop": self.estop,
                           **self.lire_etat()})
            time.sleep(self.periode_tel_s)

    def executer(self, entree=None, sortie=None) -> None:
        """Mode « programme externe » : langage unifié sur stdin / stdout."""
        entree, sortie = entree or sys.stdin, sortie or sys.stdout

        def ecrire(s: str) -> None:
            sortie.write(s)
            sortie.flush()

        self._ecrire = ecrire
        fini = threading.Event()
        threading.Thread(target=self._boucle_tel, args=(lambda: not fini.is_set(),), daemon=True).start()
        self._envoyer(self.info())
        for ligne in entree:
            self.traiter(ligne)
        fini.set()
        self.figer()

    def servir_tcp(self, port: int = 3333, hote: str = "0.0.0.0") -> None:
        """Mode embarqué : un client (le pont) à la fois, une ligne JSON par message."""
        with socket.create_server((hote, port)) as srv:
            while True:
                conn, _ = srv.accept()
                with conn, conn.makefile("r", encoding="utf-8") as f:
                    self._ecrire = lambda s: conn.sendall(s.encode())
                    actif = threading.Event()
                    actif.set()
                    threading.Thread(target=self._boucle_tel, args=(actif.is_set,), daemon=True).start()
                    try:
                        for ligne in f:
                            self.traiter(ligne)
                    except OSError:
                        pass
                    finally:
                        actif.clear()
                        self.roues = [0.0, 0.0]
                        self.figer()
