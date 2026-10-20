"""Hiwonder TonyPi Pro : profil, conversions, groupes d'actions .d6a, pilote embarqué (à blanc), pilote JSON-RPC,
gestes natifs, chute et conduite de scène par le pont.   python -m pytest -q tests/test_tonypi.py"""
import asyncio
import importlib.util
import io
import json
import sqlite3
import sys
from contextlib import redirect_stderr

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bridge.robots import pilotes
from bridge.robots import tonypi as T
from bridge.robots.description import charger
from bridge.robots.pilotes.tonypi_rpc import PiloteTonyPiRPC, mode_marche
from bridge.serveur import CTL, RACINE, charger_config, creer_app

PROFIL = RACINE / "robots" / "tonypi_pro.toml"
DEBOUT = (500, 390, 500, 600, 500, 575, 800, 725, 500, 610, 500, 400, 500, 425, 200, 275, 500, 500)


def run(c):
    return asyncio.run(c)


def embarque():
    spec = importlib.util.spec_from_file_location("tonypi_embarque", RACINE / "sdk" / "python" / "tonypi_embarque.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["tonypi_embarque"] = m
    spec.loader.exec_module(m)
    return m


def profil_dict():
    import tomllib
    return tomllib.loads(PROFIL.read_text(encoding="utf-8"))


# ── Profil ─────────────────────────────────────────────────
def test_profil_complet_et_coherent():
    d = charger(PROFIL)
    assert len(d.articulations) == 20 and d.pilote == "ligne_json" and d.simulation and d.propulsion
    bus = [a for a in d.articulations if T.genre(a) == "bus"]
    assert sorted(T.numero(a) for a in bus) == list(range(1, 19))
    assert [a.id for a in d.articulations if T.genre(a) == "pwm"] == ["pwm:1", "pwm:2"]
    # zéro = position debout officielle ; debout (0) toujours dans les bornes
    assert all(a.zero == DEBOUT[T.numero(a) - 1] for a in bus)
    assert all(a.min <= 0 <= a.max for a in d.articulations)
    # gauche et droite sont symétriques pour les bras (sens déduits des groupes officiels, cohérents)
    for g, dr in (("epaule_g.flexion", "epaule_d.flexion"), ("epaule_g.abduction", "epaule_d.abduction")):
        ag, ad = (next(a for a in d.articulations if a.nom == n) for n in (g, dr))
        assert abs(ag.min - ad.min) < 1 and abs(ag.max - ad.max) < 1
    assert set(d.gestes_dynamiques) <= set(d.gestes_natifs) and "go_forward" in d.gestes_dynamiques
    assert all(g in d.libelles_gestes for g in d.gestes_natifs)
    assert set(d.jumeau["piloter"]) <= set(d.noms) and not any("genou" in n or "cheville" in n for n in d.jumeau["piloter"])
    rpc = charger(RACINE / "robots" / "tonypi_pro_rpc.toml")
    assert rpc.pilote == "tonypi_rpc" and not rpc.actif and rpc.sequences == d.sequences and rpc.noms == d.noms


def test_noms_du_profil_sont_des_axes_du_robot_virtuel():
    schema = json.loads((RACINE / "web" / "avatar" / "schema.json").read_text(encoding="utf-8"))
    assert set(charger(PROFIL).noms) <= set(schema["dofs"])            # reflet complet, jambes comprises


def test_conversions_pont_et_embarque_identiques():
    E = embarque()
    d, brut = charger(PROFIL), profil_dict()["articulations"]
    for a, ad in zip(d.articulations, brut):
        for v in (a.min, a.max, 0, (a.min + a.max) / 2, 13.7):
            assert T.vers_natif(a, v) == E.vers_natif(ad, v)
            assert abs(T.depuis_natif(a, T.vers_natif(a, v)) - E.depuis_natif(ad, E.vers_natif(ad, v))) < 0.11
    bras = next(a for a in d.articulations if a.nom == "epaule_d.flexion")
    assert T.vers_natif(bras, 0) == 275 and T.vers_natif(bras, 90) == 650 and T.vers_natif(bras, 999) == 1000
    tete = next(a for a in d.articulations if a.nom == "tete.flexion")
    assert T.vers_natif(tete, 0) == 1500 and T.vers_natif(tete, 27) == 1200          # + = regarder vers le bas


# ── Groupes d'actions .d6a ─────────────────────────────────
def test_d6a_aller_retour_et_import(tmp_path):
    d = charger(PROFIL)
    images = [{"ms": 500, "pas": dict(enumerate(DEBOUT, start=1))},
              {"ms": 300, "pas": {**dict(enumerate(DEBOUT, start=1)), 16: 787, 14: 177}}]
    T.ecrire_d6a(tmp_path / "salut.d6a", images)
    cols = [r[1] for r in sqlite3.connect(tmp_path / "salut.d6a").execute("pragma table_info(ActionGroup)")]
    assert cols[:2] == ["Index", "Time"] and cols[-1] == "Servo18" and len(cols) == 20
    lu = T.lire_d6a(tmp_path / "salut.d6a")
    assert lu == images
    seq = T.d6a_vers_sequence(lu, d.articulations, "hw_salut")
    assert seq["statut"] == "brouillon" and seq["images"][0]["deg"] == [0.0] * 20
    i = d.noms.index("epaule_d.flexion")
    assert seq["images"][1]["deg"][i] == pytest.approx(122.88)
    assert T.sequence_vers_d6a(seq, d.articulations) == images
    assert T.enveloppe(tmp_path)[16] == (275, 787)
    # outil d'import : séquences « hw_* » au statut brouillon, exclues du dépôt public
    sys.path.insert(0, str(RACINE / "outils"))
    import hiwonder_tonypi as outil
    faits = outil.importer(tmp_path, ["salut"], False, dest=tmp_path / "seq")
    assert faits == ["hw_salut"] and json.loads((tmp_path / "seq" / "hw_salut.json").read_text())["statut"] == "brouillon"
    assert "sequences/tonypi-pro/hw_*.json" in (RACINE / ".gitignore").read_text(encoding="utf-8")


# ── Pilote embarqué (à blanc) ──────────────────────────────
def test_pilote_embarque_a_blanc():
    E = embarque()
    sortie, err = [], io.StringIO()
    with redirect_stderr(err):
        r = E.TonyPi(profil_dict(), a_blanc=True)
        r._ecrire = sortie.append
        r.traiter('{"t":"hello"}')
        info = json.loads(sortie[-1])
        assert info["servos"] == 20 and "wave" in info["gestes"] and info["a_blanc"]
        deg = [0.0] * 20
        deg[charger(PROFIL).noms.index("epaule_d.flexion")] = 90
        deg[charger(PROFIL).noms.index("tete.flexion")] = 27
        r.traiter(json.dumps({"t": "servos", "deg": deg, "ms": 400}))
        r.traiter('{"t":"geste","nom":"rm -rf"}')
        assert "inconnu" in json.loads(sortie[-1])["msg"]
        r.traiter('{"t":"geste","nom":"wave"}')
        r._fil_geste.join(3)
        r.traiter('{"t":"estop"}')
        r.traiter(json.dumps({"t": "servos", "deg": deg, "ms": 400}))
        assert json.loads(sortie[-1])["msg"] == "estop"
        r._actif = False
    trace = err.getvalue()
    assert "[16, 650]" in trace and "pwm 0.4 [[1, 1200], [2, 1435]]" in trace and "groupe d'actions wave 1" in trace
    assert "arrêt du bus" in trace
    evts = [json.loads(x) for x in sortie if '"evt"' in x]
    assert [e["etat"] for e in evts if e["type"] == "geste"][:2] == ["debut", "fin"]


def test_marche_et_chute():
    E = embarque()
    assert E.mode_marche(0.6, 0.6) == mode_marche(0.6, 0.6) == "go_forward"
    assert E.mode_marche(-0.5, -0.5) == "back" and E.mode_marche(0.6, -0.6) == "turn_right"
    assert E.mode_marche(-0.6, 0.6) == "turn_left" and E.mode_marche(0.05, 0.0) is None
    assert E.chute_selon_imu(9.8, 0.0) is None                 # debout : ±90°
    assert E.chute_selon_imu(0.1, 9.8) == "avant" and E.chute_selon_imu(0.1, -9.8) == "arriere"


# ── Pilote JSON-RPC (serveur de Hiwonder) ──────────────────
def test_pilote_rpc():
    appels = []

    async def appeler(methode, params):
        appels.append((methode, params))
        if methode == "GetBusServosPulse":
            return [True, list(DEBOUT[:15]), methode]
        return [True, [], methode]

    async def scenario():
        d = charger(RACINE / "robots" / "tonypi_pro_rpc.toml")
        p = PiloteTonyPiRPC(d, appeler=appeler)
        await p.ouvrir()
        deg = [0.0] * 20
        deg[d.noms.index("epaule_d.flexion")] = 90
        deg[d.noms.index("main_d.fermeture")] = 50
        await p.envoyer({"t": "servos", "deg": deg, "ms": 300})
        bus = next(a for m, a in appels if m == "SetBusServoPulse")
        assert bus[:2] == [300, 16] and bus[2 + 2 * 15:2 + 2 * 16] == [16, 650] and 17 not in bus[2::2]
        assert next(a for m, a in appels if m == "set_pwm_servo") == [300, 2, 1, 1500, 2, 1435]
        await p.envoyer({"t": "geste", "nom": "bow"})
        await p.envoyer({"t": "geste", "nom": "inconnu"})
        await p.envoyer({"t": "drive", "l": 0.6, "r": 0.6})
        await p.envoyer({"t": "estop"})
        await p.envoyer({"t": "geste", "nom": "bow"})
        msgs = []
        while not p._file.empty():
            msgs.append(p._file.get_nowait())
        await p.fermer()
        return msgs

    msgs = run(scenario())
    noms = [m for m, _ in appels]
    assert ("RunAction", ["bow", 1]) in appels and ("RunAction", ["go_forward", 0]) in appels
    assert noms.count("StopActionGroup") >= 2 and "StopBusServo" in noms
    assert any(m.get("t") == "err" and "mains" in m["msg"] for m in msgs)
    assert any(m.get("t") == "err" and "hors de la liste" in m["msg"] for m in msgs)
    assert msgs[-1] == {"t": "err", "msg": "estop"}
    assert "tonypi_rpc" in pilotes.TYPES


# ── Par le pont : gestes natifs, chute, conduite ───────────
@pytest.fixture
def cfg(tmp_path):
    import shutil
    c = charger_config(RACINE / "config.toml")
    c["robot"]["transport"] = "sim"
    c["protocole"]["dossier_corpus"] = str(tmp_path / "corpus")
    c["donnees"] = {"dossier": str(tmp_path / "donnees")}
    shutil.copytree(RACINE / "sequences", tmp_path / "sequences", ignore=shutil.ignore_patterns("externe-*", "_essais.jsonl"))
    c["flotte"] = {"dossier_profils": "robots", "dossier_sequences": str(tmp_path / "sequences")}
    return c


async def attendre(ws, pred, delai=6.0):
    async def boucle():
        while True:
            m = await ws.receive_json()
            if pred(m):
                return m
    return await asyncio.wait_for(boucle(), delai)


def test_gestes_natifs_chute_et_conduite_par_le_pont(cfg, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    async def scenario():
        app = creer_app(cfg)
        async with TestClient(TestServer(app)) as cl:
            ctl = app[CTL]
            ws = await cl.ws_connect("/ws")
            await attendre(ws, lambda m: m.get("flotte") and any(r["id"] == "tonypi-pro" and r["lien"] == "connecte"
                                                                  for r in m["flotte"]), 8)
            await ws.send_json({"op": "robot_choisir", "robot": "tonypi-pro"})
            c = await attendre(ws, lambda m: m["type"] == "config" and m["robot_id"] == "tonypi-pro")
            assert len(c["noms"]) == 20 and any(g["nom"] == "bow" and g["libelle"] == "Révérence" for g in c["gestes_natifs"])
            assert c["jumeau"]["piloter"] and c["camera"]["mjpeg"].endswith("action=stream") and c["a_verifier"]
            await ws.send_json({"op": "geste_natif", "nom": "bow"})
            ev = await attendre(ws, lambda m: m["type"] == "robot_evenement" and m["evenement"] == "geste")
            assert ev["nom"] == "bow" and ev["etat"] == "debut"
            await ws.send_json({"op": "geste_natif", "nom": "danse_interdite"})
            refus = await attendre(ws, lambda m: m["type"] == "journal" and m["niveau"] == "refus")
            assert "liste fermée" in refus["msg"]
            await ws.send_json({"op": "robot_lumiere", "rgb": [255, 0, 0]})
            # chute signalée par le robot : arrêt de toute la flotte ; seul le relevé est permis après réarmement
            r = ctl.robots["tonypi-pro"]
            await ctl._sur_message_robot(r, {"t": "evt", "type": "chute", "sens": "avant", "releve": "stand_up_front"})
            assert all(x.securite.arret_urgence for x in ctl.robots.values())
            await ws.send_json({"op": "rearmer"})
            await attendre(ws, lambda m: m["type"] == "etat" and not m["arret"])
            await ws.send_json({"op": "geste_natif", "nom": "wave"})
            refus = await attendre(ws, lambda m: m["type"] == "journal" and m["niveau"] == "refus")
            assert "seul le relevé" in refus["msg"]
            await ws.send_json({"op": "geste_natif", "nom": "stand_up_front"})
            await attendre(ws, lambda m: m["type"] == "robot_evenement" and m.get("nom") == "stand_up_front")
            assert r.etat.get("chute") is None
            # conduite : « natif:<nom> » est un geste connu de la scène
            assert "natif:bow" in ctl.scene.gestes_connus()
            await ws.close()
    run(scenario())
