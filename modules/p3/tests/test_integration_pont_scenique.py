"""Intégration P2.3 → P3.2 : la conduite d'exemple du pont scénique étiquette les réponses du public.

Le test est ignoré si le paquet `pont_scenique` (05_Prototypes/P2_Scenographie_robotique/code) est absent.
"""
import socket
import sys
import time
from pathlib import Path

import pytest

CODE_P2 = Path(__file__).resolve().parents[3] / "P2_Scenographie_robotique" / "code"
if not CODE_P2.exists():  # disposition intégrée Robo-Scène : modules/p2
    CODE_P2 = Path(__file__).resolve().parents[2] / "p2"
if CODE_P2.exists():
    sys.path.insert(0, str(CODE_P2))
pont = pytest.importorskip("pont_scenique.conduite")

from p3_spectateur import Seance  # noqa: E402
from p3_spectateur.serveur import demarrer_osc  # noqa: E402


def port_libre():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


def attendre(cond, delai=2.0):
    t = time.time()
    while time.time() - t < delai:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_conduite_exemple_vers_interface_spectateur(tmp_path):
    from pont_scenique.conduite import charger
    from pont_scenique.moteur import Moteur
    from pont_scenique.sorties import SortieOSC

    s = Seance(code="2026", delai_min_s=0, seuil_diffusion=1, afficher_provenance=True)
    p_prov, p_libre = port_libre(), port_libre()
    oscs = [demarrer_osc(s, p, tmp_path, journal=lambda *_: None, hote="127.0.0.1") for p in (p_prov, p_libre)]
    try:
        conduite = charger(CODE_P2 / "pont_scenique" / "conduite_exemple.yaml")
        m = Moteur(conduite, osc_p3=SortieOSC("127.0.0.1", p_prov, journal=lambda *_: None),
                   osc_libre=SortieOSC("127.0.0.1", p_libre, journal=lambda *_: None), journal=lambda *_: None)
        jetons = [s.rejoindre("2026") for _ in range(3)]
        for _ in range(4):                     # repères 0 à 3 : le repère 3 envoie « mixte »
            m.go()
        assert attendre(lambda: s.provenance == "mixte")
        for j in jetons:
            s.repondre(j, emotion="saisi")
        m.go()                                 # repère 4
        m.go()                                 # repère 5 : « humaine »
        assert attendre(lambda: s.provenance == "humaine" and s.repere == "5")
        s.repondre(jetons[0], emotion="ravi")
        m.go()                                 # repère 6 : /p3/fin par la sortie OSC libre
        assert attendre(lambda: s.close)
        export = sorted(tmp_path.glob("*.json"))[-1].read_text(encoding="utf-8")
        assert '"mixte"' in export and '"humaine"' in export
    finally:
        for o in oscs:
            o.shutdown()
