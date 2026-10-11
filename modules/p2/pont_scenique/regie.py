"""Poste de régie en ligne de commande.

  python -m pont_scenique.regie pont_scenique/conduite_exemple.yaml --a-blanc
  python -m pont_scenique.regie ma_conduite.yaml --qlab 192.168.1.10 --sacn-univers 1 --cible sim

Touches : Entrée = GO ; b = retour ; a = ARRÊT ; r = réautoriser les gestes ; q = quitter.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .conduite import charger, valider
from .moteur import Moteur
from .sorties import SortieDMX, SortieGestes, SortieOSC, SortieQLab, PORT_QLAB


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pont_scenique.regie")
    ap.add_argument("conduite")
    ap.add_argument("--a-blanc", action="store_true", help="aucun envoi réseau ni mouvement")
    ap.add_argument("--qlab", default="127.0.0.1")
    ap.add_argument("--qlab-port", type=int, default=PORT_QLAB)
    ap.add_argument("--sacn-univers", type=int, default=1)
    ap.add_argument("--sacn-unicast", default=None, help="IP du nœud DMX (sinon multidiffusion)")
    ap.add_argument("--p3", default="127.0.0.1:9000", help="hôte:port de l'interface spectateur")
    ap.add_argument("--osc", default="127.0.0.1:8000", help="hôte:port pour les messages OSC libres")
    ap.add_argument("--cible", choices=["sim", "robot"], default="sim")
    ap.add_argument("--vitesse", choices=["lente", "pleine"], default="lente")
    ap.add_argument("--journal", default="journal_regie.jsonl")
    a = ap.parse_args(argv)

    jf = Path(a.journal)

    def journal(msg: str):
        print(msg)
        with open(jf, "a", encoding="utf-8") as f:
            f.write(json.dumps({"horodatage": datetime.now(timezone.utc).isoformat(), "message": msg},
                               ensure_ascii=False) + "\n")

    from gestes_scene import ExecuteurFerme
    ex = ExecuteurFerme(journal="journal_gestes.jsonl")
    c = charger(a.conduite)
    erreurs = valider(c, set(ex.gestes))
    if erreurs:
        for e in erreurs:
            print("✗", e)
        return 1

    h3, p3 = a.p3.split(":")
    ho, po = a.osc.split(":")
    mini = None
    if not a.a_blanc:
        from reachy_mini import ReachyMini
        mini = ReachyMini(media_backend="no_media")
    m = Moteur(c,
               qlab=SortieQLab(a.qlab, a.qlab_port, a.a_blanc, journal),
               dmx=SortieDMX(a.sacn_univers, ip_unicast=a.sacn_unicast, a_blanc=a.a_blanc, journal=journal),
               osc_p3=SortieOSC(h3, int(p3), a.a_blanc, journal),
               osc_libre=SortieOSC(ho, int(po), a.a_blanc, journal),
               gestes=SortieGestes(ex, a.cible, a.vitesse, mini, a.a_blanc, journal),
               journal=journal)
    journal(f"Conduite « {c.titre} » chargée : {len(c.reperes)} repères. Cible gestes : {a.cible}/{a.vitesse}.")
    try:
        while True:
            nxt = m.prochain
            invite = f"[prochain : {nxt.numero} — {nxt.nom}]" if nxt else "[fin]"
            cmd = input(f"{invite} Entrée=GO  b=retour  a=ARRÊT  r=gestes  q=quitter > ").strip().lower()
            if cmd == "":
                m.go()
            elif cmd == "b":
                m.retour()
            elif cmd == "a":
                m.arret()
            elif cmd == "r":
                m.reprendre_gestes()
            elif cmd == "q":
                break
    finally:
        m.dmx.fermer()
        if mini is not None:
            mini.__exit__(None, None, None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
