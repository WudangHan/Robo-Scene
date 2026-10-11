"""Moteur de conduite : GO, retour, ARRÊT, actions différées."""
from __future__ import annotations

import threading
from datetime import datetime

from .conduite import Conduite, Repere


class Moteur:
    def __init__(self, conduite: Conduite, *, qlab=None, dmx=None, osc_p3=None, osc_libre=None, gestes=None,
                 journal=print):
        self.c = conduite
        self.qlab, self.dmx, self.osc_p3, self.osc_libre, self.gestes = qlab, dmx, osc_p3, osc_libre, gestes
        self.journal = journal
        self.index = -1               # dernier repère joué
        self._minuteries: list[threading.Timer] = []
        self._verrou = threading.Lock()
        self.historique: list[tuple[str, str, str]] = []  # (heure, repère, type d'action)

    @property
    def prochain(self) -> Repere | None:
        return self.c.reperes[self.index + 1] if self.index + 1 < len(self.c.reperes) else None

    def go(self) -> Repere | None:
        r = self.prochain
        if r is None:
            self.journal("Fin de conduite.")
            return None
        self.index += 1
        self.journal(f"GO — repère {r.numero} : {r.nom}")
        for a in r.actions:
            if a.delai > 0:
                t = threading.Timer(a.delai, self._executer, args=(r, a))
                t.daemon = True
                with self._verrou:
                    self._minuteries.append(t)
                t.start()
            else:
                self._executer(r, a)
        return r

    def retour(self):
        """Recule le pointeur d'un repère sans rien rejouer (comme « back » en régie)."""
        self.index = max(-1, self.index - 1)
        self.journal(f"Pointeur reculé ; prochain repère : {self.prochain.numero if self.prochain else '—'}")

    def arret(self):
        """ARRÊT logiciel : annule les actions différées, panique du son, fige la lumière, suspend les gestes.

        Ne remplace PAS l'arrêt d'urgence matériel du robot (plan P2.1, §6.2)."""
        with self._verrou:
            for t in self._minuteries:
                t.cancel()
            self._minuteries.clear()
        if self.qlab:
            self.qlab.panique()
        if self.dmx:
            self.dmx.figer()
        if self.gestes:
            self.gestes.suspendu = True
        self.journal("ARRÊT logiciel : actions différées annulées, son en panique, lumière figée, gestes suspendus.")

    def reprendre_gestes(self):
        if self.gestes:
            self.gestes.suspendu = False
            self.journal("Gestes réautorisés par la régie.")

    def _executer(self, r: Repere, a):
        self.historique.append((datetime.now().strftime("%H:%M:%S.%f")[:-3], r.numero, a.type))
        try:
            if a.type == "lumiere" and self.dmx:
                self.dmx.transferer({self.c.projecteurs[p]: int(v) for p, v in a.valeur.items()}, a.transfert)
            elif a.type == "son" and self.qlab:
                self.qlab.demarrer_cue(str(a.valeur))
            elif a.type == "provenance" and self.osc_p3:
                self.osc_p3.envoyer("/p3/provenance", a.valeur, r.numero)
            elif a.type == "osc" and self.osc_libre:
                self.osc_libre.envoyer(a.valeur["adresse"], *a.valeur.get("arguments", []))
            elif a.type == "geste" and self.gestes:
                # le geste s'exécute dans un fil séparé pour ne pas bloquer la régie
                threading.Thread(target=self.gestes.jouer, args=(a.valeur, r.numero), daemon=True).start()
        except Exception as e:  # une sortie défaillante ne doit pas bloquer les autres
            self.journal(f"⚠ Repère {r.numero}, action {a.type} : {e}")
