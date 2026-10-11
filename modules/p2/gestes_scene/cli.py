"""Ligne de commande de l'opérateur.

  python -m gestes_scene.cli lister
  python -m gestes_scene.cli valider
  python -m gestes_scene.cli jouer acquiescer --cible sim --vitesse lente
  python -m gestes_scene.cli sequences              # plan minuté des séquences (P2.4)
  python -m gestes_scene.cli jouer fin_de_scene --cible sim

« jouer » demande à l'opérateur de retaper le nom du geste avant tout mouvement.
Pour la cible « sim », lancer d'abord le simulateur du SDK :  reachy-mini-daemon --sim
(sur macOS : mjpython -m reachy_mini.daemon.app.main --sim).
"""
from __future__ import annotations

import argparse
import sys

from .bibliotheque import charger, valider
from .executeur import ExecuteurFerme, RefusExecution


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="gestes_scene")
    sous = ap.add_subparsers(dest="cmd", required=True)
    sous.add_parser("lister")
    sous.add_parser("valider")
    sous.add_parser("sequences")
    j = sous.add_parser("jouer")
    j.add_argument("geste")
    j.add_argument("--cible", choices=["sim", "robot"], default="sim")
    j.add_argument("--vitesse", choices=["lente", "pleine"], default="lente")
    a = ap.parse_args(argv)

    if a.cmd == "lister":
        for n, g in charger().items():
            print(f"{n:16} {g.statut:18} {g.duree_totale:4.1f} s  {g.description.get('fr', '')}")
        return 0
    if a.cmd == "sequences":
        from .sequenceur import charger_sequences, decrire
        for seq in charger_sequences().values():
            print(decrire(seq))
        return 0
    if a.cmd == "valider":
        total = 0
        for n, g in charger().items():
            for e in valider(g):
                print("✗", e)
                total += 1
        print("Bibliothèque conforme." if total == 0 else f"{total} violation(s).")
        return 1 if total else 0

    ex = ExecuteurFerme()
    try:
        p = ex.proposer(a.geste, source="operateur")
        ex.autoriser(p, a.cible, a.vitesse)
    except RefusExecution as e:
        print("Refus :", e)
        return 2
    print(f"Geste « {a.geste} » — cible {a.cible}, vitesse {a.vitesse}.")
    print("Zone d'exclusion dégagée et arrêt d'urgence à portée ? Retapez le nom du geste pour confirmer :")
    ok = input("> ").strip() == a.geste
    from reachy_mini import ReachyMini
    with ReachyMini(media_backend="no_media") as mini:
        try:
            ex.executer(p, confirmation_operateur=ok, cible=a.cible, vitesse=a.vitesse, mini=mini)
        except RefusExecution as e:
            print("Refus :", e)
            return 2
    print("Terminé ; consigné dans", ex.journal)
    return 0


if __name__ == "__main__":
    sys.exit(main())
