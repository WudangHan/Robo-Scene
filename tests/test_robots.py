"""Couche robots universelle : profils, pilotes (bus Hiwonder, rosbridge, MQTT, OSC, HTTP, Reachy Mini,
programmes externes en Python, JavaScript et C++), bibliothèque fermée à statuts, flotte et arrêt global."""
import asyncio
import json
import shutil
import socket
import struct
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestClient, TestServer

from bridge.robots import pilotes
from bridge.robots.bibliotheque import BibliothequeJSON, BibliothequeP2, RefusBibliotheque, exigence
from bridge.robots.description import charger, charger_profils
from bridge.robots.pilotes import hiwonder_bus as hw
from bridge.robots.pilotes.http_rest import pointeur, remplir
from bridge.robots.pilotes.rosbridge import duree_ros, type_ros
from bridge.serveur import CTL, RACINE, charger_config, creer_app

PROFILS = RACINE / "robots"


def run(c):
    return asyncio.run(c)


def port_libre(udp=False):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM if udp else socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def recevoir_jusqua(p, pred, delai=3.0):
    async def boucle():
        while True:
            m = await p.recevoir()
            if pred(m):
                return m
    return await asyncio.wait_for(boucle(), delai)


# ── Profils ────────────────────────────────────────────────
def test_profils_valides():
    ds = {d.id: d for d in charger_profils(PROFILS)}
    assert {"ainex-01", "reachy-mini", "ros2-exemple", "mqtt-exemple", "osc-exemple", "http-exemple",
            "externe-python", "externe-javascript", "externe-cpp"} <= set(ds)
    assert len(ds["ainex-01"].articulations) == 24 and ds["ainex-01"].rayon_exclusion_m == 1.2
    assert ds["ainex-01"].simulation and ds["reachy-mini"].bibliotheque == "p2"
    assert all(d.pilote in pilotes.TYPES for d in ds.values())


# ── Bus Hiwonder (protocole LewanSoul / LX) ────────────────
def test_trame_hiwonder_et_conversion():
    # Servo 1 → position 500 en 1000 ms : 55 55 01 07 01 F4 01 E8 03 + somme
    t = hw.trame_mouvement(1, 500, 1000)
    assert t.hex(" ") == "55 55 01 07 01 f4 01 e8 03 16"
    assert hw.lire_trame(b"\x00\x13" + t + b"\x55") == (1, 1, b"\xf4\x01\xe8\x03", b"\x55")
    assert hw.lire_trame(t[:-1] + b"\x00") is None                     # somme fausse : rejetée
    assert hw.deg_vers_pas(0) == 500 and hw.deg_vers_pas(120) == 1000 and hw.deg_vers_pas(-200) == 0
    assert hw.pas_vers_deg(hw.deg_vers_pas(24)) == 24.0
    assert hw.trame(254, hw.MOVE_STOP).hex(" ") == "55 55 fe 03 0c f2"


class FausseSerie:
    """Bus simulé : répond aux lectures de position et de tension ; enregistre les écritures."""

    def __init__(self):
        self.ecrit, self.reponse = [], b""

    def write(self, b):
        self.ecrit.append(bytes(b))
        r = hw.lire_trame(bytes(b))
        if r and r[1] == hw.POS_READ:
            self.reponse += hw.trame(r[0], hw.POS_READ, struct.pack("<h", 500 + 25 * r[0]))
        elif r and r[1] == hw.VIN_READ:
            self.reponse += hw.trame(r[0], hw.VIN_READ, struct.pack("<H", 11800))

    def read(self, n):
        out, self.reponse = self.reponse[:n], self.reponse[n:]
        return out

    def reset_input_buffer(self):
        self.reponse = b""

    def close(self):
        pass


def test_pilote_hiwonder():
    d = charger(PROFILS / "ainex.toml")
    d = replace(d, simulation=False, articulations=d.articulations[:3], connexion={**d.connexion, "periode_lecture_s": 0.02})
    serie = FausseSerie()

    async def scenario():
        p = pilotes.creer(d, serie=serie)
        await p.ouvrir()
        tel = await recevoir_jusqua(p, lambda m: m["t"] == "tel")
        assert tel["deg"] == [hw.pas_vers_deg(525), hw.pas_vers_deg(550), hw.pas_vers_deg(575)] and tel["vbat"] == 11.8
        await p.envoyer({"t": "servos", "deg": [10, -10, 0], "ms": 800})
        mouv = [hw.lire_trame(b) for b in serie.ecrit if hw.lire_trame(b) and hw.lire_trame(b)[1] == hw.MOVE_TIME_WRITE]
        assert mouv, "aucune trame de mouvement"
        await p.envoyer({"t": "estop"})
        assert serie.ecrit[-1] == hw.trame(254, hw.MOVE_STOP)
        await p.envoyer({"t": "servos", "deg": [0, 0, 0], "ms": 100})
        assert (await recevoir_jusqua(p, lambda m: m["t"] == "err"))["msg"] == "estop"
        await p.fermer()
    run(scenario())


# ── ROS 1 et ROS 2 par rosbridge ───────────────────────────
def test_types_et_durees_ros():
    assert type_ros("trajectory_msgs", "JointTrajectory", 2) == "trajectory_msgs/msg/JointTrajectory"
    assert type_ros("trajectory_msgs", "JointTrajectory", 1) == "trajectory_msgs/JointTrajectory"
    assert duree_ros(1250, 2) == {"sec": 1, "nanosec": 250_000_000}
    assert duree_ros(1250, 1) == {"secs": 1, "nsecs": 250_000_000}


def test_pilote_rosbridge():
    recu = []

    async def ws(request):
        w = web.WebSocketResponse()
        await w.prepare(request)
        async for m in w:
            d = json.loads(m.data)
            recu.append(d)
            if d.get("op") == "subscribe":
                await w.send_str(json.dumps({"op": "publish", "topic": "/joint_states",
                                             "msg": {"name": ["elbow_joint", "shoulder_joint"], "position": [-0.5, 0.25]}}))
        return w

    async def scenario():
        app = web.Application()
        app.router.add_get("/", ws)
        async with TestServer(app) as srv:
            d = charger(PROFILS / "exemple_ros2.toml")
            d = replace(d, connexion={**d.connexion, "url": str(srv.make_url("/")).replace("http", "ws")})
            p = pilotes.creer(d)
            await p.ouvrir()
            tel = await recevoir_jusqua(p, lambda m: m["t"] == "tel")
            assert tel["deg"] == [pytest.approx(14.32, abs=0.01), pytest.approx(-28.65, abs=0.01)]
            await p.envoyer({"t": "servos", "deg": [30, -45], "ms": 1500})
            await p.envoyer({"t": "estop"})
            await asyncio.sleep(0.2)
            await p.fermer()
        ops = [(x["op"], x.get("topic")) for x in recu]
        assert ("advertise", "/arm_controller/joint_trajectory") in ops
        traj = next(x for x in recu if x["op"] == "publish" and x["topic"] == "/arm_controller/joint_trajectory")["msg"]
        assert traj["joint_names"] == ["shoulder_joint", "elbow_joint"]
        assert traj["points"][0]["positions"] == [pytest.approx(0.5236, abs=1e-4), pytest.approx(-0.7854, abs=1e-4)]
        assert traj["points"][0]["time_from_start"] == {"sec": 1, "nanosec": 500_000_000}
        arret = [x for x in recu if x.get("topic") == "/robo_scene/arret_urgence" and x["op"] == "publish"]
        assert arret and arret[0]["msg"] == {"data": True}
    run(scenario())


# ── MQTT (courtier réel en mémoire) ────────────────────────
def test_pilote_mqtt():
    amqtt = pytest.importorskip("amqtt.broker")
    port = port_libre()

    async def scenario():
        broker = amqtt.Broker({"listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{port}"}}})
        await broker.start()
        try:
            import paho.mqtt.client as mqtt
            robot = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="robot-test")
            cmds = []
            robot.on_message = lambda c, u, m: cmds.append(json.loads(m.payload))
            robot.connect("127.0.0.1", port)
            robot.subscribe("robo-scene/mqtt-exemple/cmd")
            robot.loop_start()
            d = charger(PROFILS / "exemple_mqtt.toml")
            p = pilotes.creer(replace(d, connexion={**d.connexion, "port": port}))
            await p.ouvrir()
            await asyncio.sleep(0.3)
            await p.envoyer({"t": "servos", "deg": [100], "ms": 500})
            await p.envoyer({"t": "estop"})
            robot.publish("robo-scene/mqtt-exemple/tel", json.dumps({"t": "tel", "deg": [100], "estop": True}))
            tel = await recevoir_jusqua(p, lambda m: m["t"] == "tel")
            for _ in range(30):
                if len(cmds) >= 2:
                    break
                await asyncio.sleep(0.1)
            assert [c["t"] for c in cmds[:2]] == ["servos", "estop"] and tel["estop"] is True
            robot.loop_stop()
            await p.fermer()
        finally:
            await broker.shutdown()
    run(scenario())


# ── OSC ────────────────────────────────────────────────────
def test_pilote_osc():
    from pythonosc.dispatcher import Dispatcher
    from pythonosc.osc_server import AsyncIOOSCUDPServer
    from pythonosc.udp_client import SimpleUDPClient
    p_robot, p_pont = port_libre(True), port_libre(True)
    recu = []

    async def scenario():
        disp = Dispatcher()
        disp.set_default_handler(lambda adr, *a: recu.append((adr, list(a))))
        srv = AsyncIOOSCUDPServer(("127.0.0.1", p_robot), disp, asyncio.get_running_loop())
        tr, _ = await srv.create_serve_endpoint()
        d = charger(PROFILS / "exemple_osc.toml")
        p = pilotes.creer(replace(d, connexion={"hote": "127.0.0.1", "port": p_robot, "port_local": p_pont}))
        await p.ouvrir()
        await p.envoyer({"t": "servos", "deg": [120.0], "ms": 700})
        await p.envoyer({"t": "estop"})
        SimpleUDPClient("127.0.0.1", p_pont).send_message("/robot/tel", [1, 7.4, 55.0, 120.0])
        tel = await recevoir_jusqua(p, lambda m: m["t"] == "tel")
        await asyncio.sleep(0.2)
        tr.close()
        await p.fermer()
        assert ("/robot/servos", [700, 120.0]) in recu and ("/robot/estop", []) in recu
        assert tel == {**tel, "estop": True, "vbat": 7.4, "dist": 55.0, "deg": [120.0]}
    run(scenario())


# ── HTTP ───────────────────────────────────────────────────
def test_gabarits_http():
    assert remplir('{"p": {deg}, "t": {ms}}', {"deg": [1.5, 2], "ms": 300}) == {"p": [1.5, 2], "t": 300}
    assert pointeur({"a": {"b": [3, 4]}}, "/a/b/1") == 4


def test_pilote_http():
    recu = []

    async def joints(r):
        recu.append(await r.json())
        return web.json_response({"ok": True})

    async def etat(_):
        return web.json_response({"joints": [10.0, -5.0], "battery": 12.1})

    async def scenario():
        app = web.Application()
        app.router.add_post("/api/joints", joints)
        app.router.add_post("/api/stop", joints)
        app.router.add_get("/api/state", etat)
        async with TestServer(app) as srv:
            d = charger(PROFILS / "exemple_http.toml")
            p = pilotes.creer(replace(d, connexion={**d.connexion, "url": str(srv.make_url("")).rstrip("/")}))
            await p.ouvrir()
            tel = await recevoir_jusqua(p, lambda m: m["t"] == "tel")
            await p.envoyer({"t": "servos", "deg": [20, 30], "ms": 400})
            await p.fermer()
        assert tel["deg"] == [10.0, -5.0] and tel["vbat"] == 12.1
        assert recu == [{"positions": [20.0, 30.0], "duration_ms": 400}]
    run(scenario())


# ── Reachy Mini (trousse simulée) ──────────────────────────
def test_pilote_reachy_mini(monkeypatch):
    import sys
    import types
    poses = []
    utils = types.ModuleType("reachy_mini.utils")
    utils.create_head_pose = lambda **kw: kw
    monkeypatch.setitem(sys.modules, "reachy_mini", types.ModuleType("reachy_mini"))
    monkeypatch.setitem(sys.modules, "reachy_mini.utils", utils)

    class Mini:
        def goto_target(self, **kw):
            poses.append(kw)

    async def scenario():
        d = replace(charger(PROFILS / "reachy_mini.toml"), simulation=False)
        p = pilotes.creer(d, mini=Mini())
        await p.ouvrir()
        await p.envoyer({"t": "servos", "deg": [0, 0, -8, 0, 26, 0, 0, 30, 30], "ms": 1500})
        tel = await recevoir_jusqua(p, lambda m: m["t"] == "tel")
        await p.envoyer({"t": "estop"})
        await p.envoyer({"t": "servos", "deg": [0] * 9, "ms": 500})
        err = await recevoir_jusqua(p, lambda m: m["t"] == "err")
        await p.fermer()
        return tel, err
    tel, err = run(scenario())
    assert len(poses) == 1 and poses[0]["head"]["pitch"] == 26 and poses[0]["duration"] == 1.5
    assert poses[0]["antennas"] == [pytest.approx(0.5236, abs=1e-4)] * 2 and tel["estimee"] and err["msg"] == "estop"


def test_bibliotheque_p2_reachy():
    b = BibliothequeP2()
    assert {"salut", "acquiescer", "eveil"} <= set(b.lister())
    s = b.lire("salut")
    assert len(s["images"][0]["deg"]) == 9 and s["images"][0]["ms"] == 1500 and s["statut"] == "brouillon"
    with pytest.raises(RefusBibliotheque):
        b.promouvoir("salut", "valide_sim", "SG")


# ── Programmes externes : Python, JavaScript, C++ ──────────
def _cpp():
    exe = RACINE / "sdk" / "cpp" / "build" / "exemple_simule"
    if not exe.exists():
        if not shutil.which("g++"):
            pytest.skip("g++ absent")
        exe.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["g++", "-std=c++17", "-O2", "-pthread", str(RACINE / "sdk/cpp/exemple_simule.cpp"),
                        "-o", str(exe)], check=True)
    return exe


@pytest.mark.parametrize("langage", ["python", "javascript", "cpp"])
def test_pilotes_externes_multilangages(langage):
    if langage == "javascript" and not shutil.which("node"):
        pytest.skip("node absent")
    if langage == "cpp":
        _cpp()
    d = charger(PROFILS / f"exemple_externe_{langage}.toml")

    async def scenario():
        p = pilotes.creer(d, racine=RACINE)
        p.dossier = RACINE
        await p.ouvrir()
        info = await recevoir_jusqua(p, lambda m: m["t"] == "info")
        await p.envoyer({"t": "servos", "deg": [200, 40], "ms": 300})       # 200 : borné localement à 170
        tel = await recevoir_jusqua(p, lambda m: m["t"] == "tel" and m["deg"][0] == 170)
        await p.envoyer({"t": "estop"})
        await recevoir_jusqua(p, lambda m: m["t"] == "tel" and m["estop"])
        await p.envoyer({"t": "drive", "l": 0.5, "r": 0.5})
        err = await recevoir_jusqua(p, lambda m: m["t"] == "err")
        await p.envoyer({"t": "reset"})
        await p.envoyer({"t": "drive", "l": 0.5, "r": 0.5})
        roule = await recevoir_jusqua(p, lambda m: m["t"] == "tel" and m["drive"][0] == 0.5)
        arret = await recevoir_jusqua(p, lambda m: m["t"] == "tel" and m["drive"][0] == 0, 2.0)  # chien de garde
        await p.fermer()
        return info, tel, err, roule, arret
    info, tel, err, roule, arret = run(scenario())
    assert info["servos"] == 2 and tel["deg"] == [170, 40] and err["msg"] == "estop"


# ── Bibliothèque fermée à statuts ──────────────────────────
def test_statuts_et_exigences(tmp_path):
    assert exigence("brouillon", False)[0] and not exigence("brouillon", True)[0]
    assert exigence("valide_sim", True)[:2] == (True, 0.5) and exigence("valide", True)[:2] == (True, 1.0)
    b = BibliothequeJSON(tmp_path / "seq", 2, tmp_path / "essais.jsonl")
    b.enregistrer({"nom": "vague", "images": [{"deg": [90, 90], "ms": 500}]})
    assert b.lire("vague")["statut"] == "brouillon"
    with pytest.raises(RefusBibliotheque):        # aucun essai consigné
        b.promouvoir("vague", "valide_sim", "SG")
    b.consigner_essai("vague", "sim", "pleine", True)
    with pytest.raises(RefusBibliotheque):        # un cran à la fois
        b.promouvoir("vague", "valide", "SG")
    with pytest.raises(RefusBibliotheque):        # auteur requis
        b.promouvoir("vague", "valide_sim", "  ")
    assert b.promouvoir("vague", "valide_sim", "SG", "rapport du jumeau lu")["statut"] == "valide_sim"
    b.consigner_essai("vague", "robot", "lente", True)
    assert b.promouvoir("vague", "valide_robot_lent", "SG")["statut"] == "valide_robot_lent"
    # Modifier le contenu ramène au brouillon et invalide les essais antérieurs
    b.enregistrer({"nom": "vague", "images": [{"deg": [80, 90], "ms": 500}]})
    assert b.lire("vague")["statut"] == "brouillon"
    b.consigner_essai("vague", "sim", "pleine", True)
    b.promouvoir("vague", "valide_sim", "SG")
    with pytest.raises(RefusBibliotheque):        # l'essai robot lent portait sur l'ancien contenu
        b.promouvoir("vague", "valide_robot_lent", "SG")


# ── Flotte par le pont : activation, choix, observateur, arrêt global ──
@pytest.fixture
def cfg(tmp_path):
    c = charger_config(RACINE / "config.toml")
    c["robot"]["transport"] = "sim"
    c["protocole"]["dossier_corpus"] = str(tmp_path / "corpus")
    c["donnees"] = {"dossier": str(tmp_path / "donnees")}
    import shutil
    shutil.copytree(RACINE / "sequences", tmp_path / "sequences", ignore=shutil.ignore_patterns("externe-*", "_essais.jsonl"))
    c["flotte"] = {"dossier_profils": "robots", "dossier_sequences": str(tmp_path / "sequences")}
    return c


async def attendre(ws, pred, delai=5.0):
    async def boucle():
        while True:
            m = json.loads((await ws.receive()).data)
            if pred(m):
                return m
    return await asyncio.wait_for(boucle(), delai)


def test_flotte_par_le_pont(cfg, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    async def scenario():
        app = creer_app(cfg)
        async with TestClient(TestServer(app)) as cl:
            ctl = app[CTL]
            ws = await cl.ws_connect("/ws")
            conf = await attendre(ws, lambda m: m["type"] == "config")
            ids = {r["id"] for r in conf["flotte"]}
            assert {"robo-scene-01", "ainex-01", "reachy-mini"} <= ids
            # Un robot « réel » (pilote Python externe) doté d'une zone d'exclusion exige l'observateur
            d = next(x for x in ctl.profils_disponibles if x.id == "externe-python")
            d.rayon_exclusion_m = 1.0
            await ws.send_json({"op": "robot_activer", "robot": "externe-python", "simulation": False})
            await attendre(ws, lambda m: m.get("flotte") and any(r["id"] == "externe-python" and r["lien"] == "connecte"
                                                                  for r in m["flotte"]), 8)
            await ws.send_json({"op": "robot_choisir", "robot": "externe-python"})
            c2 = await attendre(ws, lambda m: m["type"] == "config" and m["robot_id"] == "externe-python")
            assert c2["noms"] == ["base", "tete"] and not c2["simulation"]
            await ws.send_json({"op": "articulations", "deg": [100, 100], "ms": 200})
            refus = await attendre(ws, lambda m: m["type"] == "journal" and m["niveau"] == "refus")
            assert "Observateur" in refus["msg"]
            await ws.send_json({"op": "observateur", "present": True, "initiales": "OBS"})
            await attendre(ws, lambda m: m["type"] == "config" and m["observateur"])
            await ws.send_json({"op": "articulations", "deg": [100, 100], "ms": 200})
            await attendre(ws, lambda m: m["type"] == "etat" and m["robot_id"] == "externe-python" and m["deg"] == [100, 100])
            # Une séquence « brouillon » est refusée sur un robot réel
            ctl.robots["externe-python"].biblio.enregistrer({"nom": "test", "images": [{"deg": [90, 90], "ms": 100}]})
            await ws.send_json({"op": "seq_jouer", "nom": "test"})
            r2 = await attendre(ws, lambda m: m["type"] == "journal" and m["niveau"] == "refus")
            assert "brouillon" in r2["msg"]
            # Arrêt global : tous les robots, une fiche d'incident
            await ws.send_json({"op": "estop"})
            await attendre(ws, lambda m: m["type"] == "etat" and m["arret"])
            assert all(r.securite.arret_urgence for r in ctl.robots.values())
            assert len(ctl.gouv.incidents.ouverts()) == 1
            await ws.send_json({"op": "rearmer"})
            await attendre(ws, lambda m: m["type"] == "etat" and not m["arret"])
            assert not any(r.securite.arret_urgence for r in ctl.robots.values())
            await ws.close()
    run(scenario())
