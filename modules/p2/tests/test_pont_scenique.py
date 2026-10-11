"""Tests du pont scénique, sans matériel : python -m pytest code/tests"""
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gestes_scene import ExecuteurFerme  # noqa: E402
from pont_scenique import charger, valider, Moteur  # noqa: E402
from pont_scenique.sorties import SortieDMX, SortieGestes, SortieOSC, SortieQLab  # noqa: E402

EXEMPLE = Path(__file__).resolve().parents[1] / "pont_scenique" / "conduite_exemple.yaml"


class Collecte:
    def __init__(self):
        self.lignes = []

    def __call__(self, m):
        self.lignes.append(m)


@pytest.fixture
def ex(tmp_path):
    return ExecuteurFerme(journal=tmp_path / "j.jsonl")


def test_conduite_exemple_valide(ex):
    c = charger(EXEMPLE)
    assert valider(c, set(ex.gestes)) == []
    assert [r.numero for r in c.reperes] == ["0", "1", "2", "3", "4", "5", "6"]


def test_geste_inconnu_detecte(ex, tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("reperes:\n  - {numero: '1', actions: [{geste: pirouette}]}\n", encoding="utf-8")
    assert any("pirouette" in e for e in valider(charger(f), set(ex.gestes)))


def test_transfert_dmx_lineaire():
    trames = []
    d = SortieDMX(a_blanc=True, journal=lambda m: None, emettre=trames.append)
    d.transferer({4: 200}, 0.3)
    time.sleep(0.15)
    milieu = d.niveau(4)
    time.sleep(0.3)
    assert 40 < milieu < 160 and d.niveau(4) == 200
    d.figer()
    d.fermer()
    assert trames and len(trames[-1]) == 512


def test_osc_reellement_emis_vers_qlab():
    from pythonosc.dispatcher import Dispatcher
    from pythonosc.osc_server import ThreadingOSCUDPServer
    recus = []
    disp = Dispatcher()
    disp.set_default_handler(lambda adr, *args: recus.append(adr))
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    serveur = ThreadingOSCUDPServer(("127.0.0.1", port), disp)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    q = SortieQLab("127.0.0.1", port, journal=lambda m: None)
    q.demarrer_cue("4")
    q.panique()
    time.sleep(0.3)
    serveur.shutdown()
    assert recus == ["/cue/4/start", "/panic"]


def test_go_sequence_et_arret_annule_les_differes(ex):
    log = Collecte()
    c = charger(EXEMPLE)
    dmx = SortieDMX(a_blanc=True, journal=log)
    m = Moteur(c, qlab=SortieQLab(a_blanc=True, journal=log), dmx=dmx,
               osc_p3=SortieOSC(a_blanc=True, journal=log), osc_libre=SortieOSC(a_blanc=True, journal=log),
               gestes=SortieGestes(ex, "sim", "lente", a_blanc=True, journal=log), journal=log)
    m.go(); m.go(); m.go()          # repères 0, 1, 2 — le geste du repère 2 est différé de 3 s
    m.arret()
    time.sleep(0.2)
    assert not any("ecouter" in l for l in log.lignes), "le geste différé aurait dû être annulé"
    assert any("/panic" in l for l in log.lignes)
    m.reprendre_gestes()
    m.go()                          # repère 3 : provenance + lumière immédiates, geste différé
    time.sleep(1.8)
    dmx.fermer()
    assert any("/p3/provenance" in l and "mixte" in l for l in log.lignes)
    assert any("acquiescer" in l for l in log.lignes)


def test_brouillon_refuse_sur_robot(ex):
    log = Collecte()
    g = SortieGestes(ex, "robot", "lente", a_blanc=True, journal=log)
    g.jouer("salut", "5")
    assert any("refusé" in l for l in log.lignes)


def test_paquet_sacn_reel_en_boucle_locale():
    """Envoie un vrai paquet E1.31 en unicast vers 127.0.0.1:5568 et le décode."""
    r = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        r.bind(("127.0.0.1", 5568))
    except OSError:
        pytest.skip("port 5568 occupé (console ou logiciel d'éclairage ouvert)")
    r.settimeout(3)
    d = SortieDMX(univers=1, ip_unicast="127.0.0.1", journal=lambda m: None, port_local=0)
    d.transferer({1: 77, 4: 200}, 0)
    ok = False
    for _ in range(40):
        data, _ = r.recvfrom(1024)
        if len(data) == 638 and data[126] == 77 and data[129] == 200:
            ok = True
            break
    d.fermer()
    r.close()
    assert ok and data[125] == 0 and int.from_bytes(data[113:115], "big") == 1
