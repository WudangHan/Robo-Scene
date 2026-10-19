"""Chien de scène : sol praticable (parité navigateur ↔ pont), cinématique et locomotion, conduite, contrôleur du
chien réel, adaptateurs (simulation, rosbridge/ROS 2, Petoi, JSON par ligne) et garde-fous.

python -m pytest -q tests/test_chien.py — les essais JavaScript exigent Node.js."""
import asyncio
import json
import math
import random
import shutil
import socket
import subprocess

import pytest
from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestClient, TestServer

from bridge.chien import sol
from bridge.chien.adaptateurs import AdaptateurPetoi, AdaptateurRosbridge, RepereSol, lacet_quaternion
from bridge.chien.controleur import ChienControleur, duree_marche
from bridge.drone.zones import charger_salle
from bridge.gouvernance.biometrie import ViolationBiometrique
from bridge.serveur import CTL, RACINE, charger_config, creer_app

NODE = shutil.which("node")
SALLE = charger_salle()


def node(script: str):
    r = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=120, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def port_libre():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ── Sol praticable (pont) ───────────────────────────────────
def test_sol_selon_le_mode():
    R = SALLE["sol"]["reperes"]
    sur_plateau = [k for k, p in R.items() if p[1] <= SALLE["volumes"]["plateau"]["z"][1]]
    for k in sur_plateau:
        for m in SALLE["sol"]["modes"]:
            assert sol.verifier(SALLE, R[k], m)["ok"], (k, m)
    for k in ("bas_escalier_cour", "avant_salle_centre", "allee_milieu"):
        assert not sol.verifier(SALLE, R[k], "plateau")["ok"]
        assert sol.verifier(SALLE, R[k], "salle_vide")["ok"]
    # en représentation : l'allée centrale (1,8 m entre les rangées) se ferme ; l'avant-salle reste, à 1 m des rangées
    assert not sol.verifier(SALLE, R["allee_milieu"], "representation")["ok"]
    assert sol.verifier(SALLE, R["avant_salle_centre"], "representation")["ok"]
    assert not sol.verifier(SALLE, [2.0, 3.9], "representation")["ok"]           # moins de 1 m du parterre cour


def test_bords_obstacles_interpretes_et_hauteurs():
    assert not sol.verifier(SALLE, [0, 1.3], "salle_vide")["ok"]               # nez de scène (pas d'escalier ici)
    assert sol.verifier(SALLE, [5.8, 1.3], "salle_vide")["ok"]                 # haut de l'escalier cour
    assert not sol.verifier(SALLE, [4.8, 0.0], "plateau")["ok"]                # cadre de scène
    assert not sol.verifier(SALLE, [0, -3], "plateau", [[0.5, -3]])["ok"]      # cercle d'un interprète
    assert sol.hauteur_sol(SALLE, 5.8, 2.1) == pytest.approx(-0.6)             # mi-escalier
    assert sol.hauteur_sol(SALLE, 0, 9.0) == pytest.approx(-0.6)               # allée en pente
    assert sol.vitesse_max(SALLE, 5.8, 2.1, "salle_vide") == 0.3
    assert sol.vitesse_max(SALLE, 0, 3.3, "representation") == SALLE["sol"]["regles"]["vitesse_max_representation_m_s"]
    t = sol.verifier_trajet(SALLE, [0, 0.9], [0, 3.3], "salle_vide")             # sauter dans la fosse : refusé
    assert not t["ok"]
    assert duree_marche(SALLE, [5.8, 1.0], [5.8, 3.3], "salle_vide", 1.0) >= 1.875 * 2.3 / 0.6


def test_repere_odometrie_et_quaternion():
    r = RepereSol([-3.0, -6.5], 0.0)
    assert r.vers_theatre(1.0, 0.0) == pytest.approx([-3.0, -5.5])     # 1 m devant (vers la salle)
    assert r.vers_theatre(0.0, 1.0) == pytest.approx([-2.0, -6.5])     # 1 m à gauche = vers cour quand on regarde la salle
    for cap in (0, 45, 180, -120):
        r = RepereSol([1.0, 2.0], cap)
        for _ in range(30):
            X, Y = random.uniform(-5, 5), random.uniform(-5, 5)
            assert r.depuis_theatre(*r.vers_theatre(X, Y)) == pytest.approx([X, Y])
    th = 0.7
    assert lacet_quaternion({"x": 0, "y": 0, "z": math.sin(th / 2), "w": math.cos(th / 2)}) == pytest.approx(th)


def test_g06_aucune_conservation_video():
    class Ctl:
        observateur = None
    with pytest.raises(ViolationBiometrique):
        ChienControleur(Ctl(), {"conserver_images": True})


# ── JavaScript : parité, cinématique, marche, conduite ──────
@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_parite_sol_navigateur_et_pont():
    rnd = random.Random(7)
    pts = [[round(rnd.uniform(-9, 9), 3), round(rnd.uniform(-9.5, 15), 3)] for _ in range(4000)]
    inter = [[0.5, -3.0], [-3.2, -5.0]]
    js = node(f"""
      import fs from "fs";
      import {{ verifierSol }} from "./web/chien/sol.js";
      const S = JSON.parse(fs.readFileSync("./web/drone/salle.json", "utf8"));
      const pts = {json.dumps(pts)}, inter = {json.dumps(inter)}, out = {{}};
      for (const m of Object.keys(S.sol.modes)) out[m] = pts.map((p) => verifierSol(S, p, {{ mode: m, interpretes: inter }}).ok);
      console.log(JSON.stringify(out));""")
    for m in SALLE["sol"]["modes"]:
        py = [sol.verifier(SALLE, p, m, inter)["ok"] for p in pts]
        assert py == js[m], m
        assert 0 < sum(py) < len(py)


@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_chien_virtuel_marche_postures_et_securites():
    r = node("""
      import fs from "fs";
      import { ChienVirtuel, ik, fk, POSTURES, PATTES, dureeMarche } from "./web/chien/chien.js";
      import { compiler, CONDUITE_EXEMPLE } from "./web/chien/conduite.js";
      import { verifierSol, pointSol } from "./web/chien/sol.js";
      const S = JSON.parse(fs.readFileSync("./web/drone/salle.json", "utf8"));
      const res = {};
      // cinématique inverse ↔ directe
      let err = 0, hors = 0;
      for (let i = 0; i < 2000; i++) { const p = [Math.random() * 0.3 - 0.15, Math.random() * 0.1 - 0.05, -0.12 - Math.random() * 0.25];
        const a = ik(p); if (!a.atteint) { hors++; continue; } const q = fk(a); err = Math.max(err, Math.hypot(...q.map((x, j) => x - p[j]))); }
      res.ik = err;
      res.postures = Object.entries(POSTURES).every(([k, P]) => Object.values(P.pieds(0.3, 0)).every((pp) => ik([pp[0], 0, pp[1]]).atteint));
      // conduite d'exemple selon le mode
      for (const m of Object.keys(S.sol.modes)) res[m] = compiler(S, CONDUITE_EXEMPLE, null, { mode: m }).ok;
      // parcours complet en salle vide : plateau → escalier cour → avant-salle → allée, sans sortie du sol praticable
      const c = new ChienVirtuel(S, { mode: "salle_vide" }); c.lever(); for (let i = 0; i < 60; i++) c.pas(0.02);
      const viol = [], ecarts = [], appuis = [];
      for (const k of ["centre", "avant_scene", "haut_escalier_cour", "bas_escalier_cour", "avant_salle_centre", "allee_milieu"]) {
        const cible = pointSol(S, k), r = c.allerA(cible, {}); if (!r.ok) { viol.push(`refus ${k}`); break; }
        for (let t = 0; t < r.duree + 3; t += 0.02) { c.pas(0.02); if (!verifierSol(S, c.p, c.ctx).ok) viol.push(k);
          // pendant la marche, le corps reste à la hauteur de l'allure au-dessus du sol local
          if (c.consigne.type === "trajectoire") appuis.push(Math.abs(c.y - (c.y - 0))); }
        ecarts.push(Math.hypot(c.p[0] - cible[0], c.p[1] - cible[1]));
      }
      res.parcours = { violations: viol.slice(0, 3), ecart: Math.max(...ecarts), y: c.y };
      // poussée contre le nez de scène en mode plateau : le robot s'arrête au bord
      const b = new ChienVirtuel(S, { mode: "plateau" }); b.p = [0, -1]; b.lever(); for (let i = 0; i < 60; i++) b.pas(0.02);
      b.lacet = 0; b.lacetCible = 0; let zmax = -9;
      for (let i = 0; i < 800; i++) { b.marcher([0, 1], 0); b.pas(0.02); zmax = Math.max(zmax, b.p[1]); if (!verifierSol(S, b.p, b.ctx).ok) { res.bord_viole = b.p; break; } }
      res.zmax = zmax;
      // ARRÊT : freinage puis couché, verrou ; coupure : affaissé
      b.marcher([0, 0], 0); b.lacet = Math.PI; b.lacetCible = Math.PI; for (let i = 0; i < 100; i++) { b.marcher([0, 1], 0); b.pas(0.02); }
      b.arretUrgence("essai"); for (let i = 0; i < 200; i++) b.pas(0.02);
      res.arret = { etat: b.etat, posture: b.posture, vitesse: Math.hypot(...b.v), lever: b.lever().ok, rearme: b.rearmer().ok, relever: b.lever().ok };
      res.coupure = [b.couperMoteurs("non").ok, b.couperMoteurs("COUPER").ok, b.etat];
      // batterie : retour à la marque puis couché ; perte de liaison : arrêt puis couché
      const d = new ChienVirtuel(S, { mode: "plateau" }); d.lever(); for (let i = 0; i < 60; i++) d.pas(0.02);
      d.allerA([3, -2], {}); for (let i = 0; i < 600; i++) d.pas(0.02);
      d.batterie = S.sol.regles.batterie_retour_pct - 0.5; for (let i = 0; i < 2500 && d.etat === "debout"; i++) d.pas(0.02);
      res.batterie = { etat: d.etat, distance: Math.hypot(d.p[0] - S.sol.aire.centre[0], d.p[1] - S.sol.aire.centre[1]) };
      const l = new ChienVirtuel(S, {}); l.lever(); for (let i = 0; i < 60; i++) l.pas(0.02);
      l.liaison.exigee = true; l.signalLiaison(l.t); for (let i = 0; i < 300; i++) { if (i < 20) l.marcher([0, 1], 0); l.pas(0.02); }
      res.liaison = l.etat;
      res.duree = dureeMarche(S, [5.8, 1.0], [5.8, 3.3], "salle_vide", 1.0).T;
      console.log(JSON.stringify(res));""")
    assert r["ik"] < 1e-9 and r["postures"]
    assert r["salle_vide"] and r["representation"] and not r["plateau"]
    assert r["parcours"]["violations"] == [] and r["parcours"]["ecart"] < 0.05
    assert r["parcours"]["y"] == pytest.approx(sol.hauteur_sol(SALLE, 0, 9.0) + 0.30, abs=0.03)
    lim = SALLE["volumes"]["plateau"]["z"][1] - SALLE["sol"]["regles"]["rayon_m"]
    assert "bord_viole" not in r and r["zmax"] <= lim + 1e-6
    assert r["arret"] == {"etat": "urgence", "posture": "couche", "vitesse": 0, "lever": False, "rearme": True, "relever": True}
    assert r["coupure"] == [False, True, "affaisse"]
    assert r["batterie"]["etat"] == "couche" and r["batterie"]["distance"] < 0.1
    assert r["liaison"] == "couche"
    assert r["duree"] == pytest.approx(duree_marche(SALLE, [5.8, 1.0], [5.8, 3.3], "salle_vide", 1.0))


# ── Contrôleur et page, par le pont ─────────────────────────
@pytest.fixture
def cfg(tmp_path):
    c = charger_config(RACINE / "config.toml")
    c["robot"]["transport"] = "sim"
    c["protocole"]["dossier_corpus"] = str(tmp_path / "corpus")
    c["donnees"] = {"dossier": str(tmp_path / "donnees")}
    c["flotte"] = {"dossier_profils": "robots_absent"}
    return c


async def _attendre(ws, pred, delai=6.0):
    async def boucle():
        while True:
            m = json.loads((await ws.receive()).data)
            if pred(m):
                return m
    return await asyncio.wait_for(boucle(), delai)


async def _battre(ws):
    while True:
        await ws.send_json({"op": "chien_hb"})
        await asyncio.sleep(0.2)


async def test_page_et_chien_simule_par_le_pont(cfg):
    app = creer_app(cfg)
    async with TestClient(TestServer(app)) as cl:
        r = await cl.get("/chien")
        assert r.status == 200 and "/static/chien/app.js" in await r.text()
        for f in ("sol.js", "chien.js", "conduite.js", "theatre3d.js", "app.js", "chien.css"):
            assert (await cl.get(f"/static/chien/{f}")).status == 200, f
        ws = await cl.ws_connect("/ws")
        await ws.send_json({"op": "chien_connecter", "adaptateur": "rosbridge"})
        m = await _attendre(ws, lambda m: m["type"] == "chien_refus")
        assert "reel_autorise" in m["msg"]
        await ws.send_json({"op": "chien_connecter", "adaptateur": "simulation"})
        await _attendre(ws, lambda m: m["type"] == "chien_etat" and m["adaptateur"] == "simulation")
        hb = asyncio.create_task(_battre(ws))
        await ws.send_json({"op": "chien_aller", "p": "centre"})
        m = await _attendre(ws, lambda m: m["type"] == "chien_refus")
        assert "debout" in m["msg"]
        await ws.send_json({"op": "chien_posture", "posture": "debout"})
        await _attendre(ws, lambda m: m["type"] == "chien_tel" and m["etat"] == "debout")
        await ws.send_json({"op": "chien_aller", "p": "bas_escalier_cour"})        # salle fermée en mode plateau
        m = await _attendre(ws, lambda m: m["type"] == "chien_refus")
        assert "Destination refusée" in m["msg"]
        await ws.send_json({"op": "chien_aller", "p": [-1.5, -5.0], "duree": 3})
        a = await _attendre(ws, lambda m: m["type"] == "chien_aller")
        assert a["duree"] >= 3
        t = await _attendre(ws, lambda m: m["type"] == "chien_tel" and math.dist([m["p"][0], m["p"][2]], [-1.5, -5.0]) < 0.12, 14)
        assert t["etat"] == "debout"
        await ws.send_json({"op": "estop", "motif": "essai"})
        await _attendre(ws, lambda m: m["type"] == "chien_tel" and m["etat"] == "couche" and m["urgence"], 6)
        await ws.send_json({"op": "chien_posture", "posture": "debout"})
        m = await _attendre(ws, lambda m: m["type"] == "chien_refus")
        assert "Arrêt d'urgence" in m["msg"]
        await ws.send_json({"op": "rearmer"})
        await asyncio.sleep(0.2)
        assert app[CTL].chien.urgence is False
        hb.cancel()
        journal = app[CTL].seance.chemin_evt.read_text(encoding="utf-8")
        actions = [json.loads(x).get("action") for x in journal.splitlines() if '"chien"' in x]
        assert {"connexion", "posture", "aller", "arret_urgence"} <= set(actions)
        await ws.close()


async def test_chien_de_garde_page_muette(cfg):
    app = creer_app(cfg)
    async with TestClient(TestServer(app)) as cl:
        c = app[CTL].chien
        c.R = {**c.R, "perte_liaison_arret_s": 0.3, "perte_liaison_coucher_s": 0.8}
        ws = await cl.ws_connect("/ws")
        await ws.send_json({"op": "chien_connecter", "adaptateur": "simulation"})
        await _attendre(ws, lambda m: m["type"] == "chien_etat" and m["adaptateur"])
        await ws.send_json({"op": "chien_posture", "posture": "debout"})
        await _attendre(ws, lambda m: m["type"] == "chien_tel" and m["etat"] == "debout")
        await _attendre(ws, lambda m: m["type"] == "chien_tel" and m["etat"] == "couche", 6)
        assert "page de pilotage muette" in app[CTL].seance.chemin_evt.read_text(encoding="utf-8")
        await ws.close()


async def test_conditions_du_chien_reel_par_rosbridge(cfg):
    """Serveur rosbridge factice : consigne les publications et renvoie l'odométrie intégrée des /cmd_vel."""
    recus, etat = [], {"x": 0.0, "y": 0.0, "th": 0.0}
    ws_robot: list = []

    async def rosbridge(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        ws_robot.append(ws)

        async def odometrie():
            while not ws.closed:
                th = etat["th"]
                await ws.send_str(json.dumps({"op": "publish", "topic": "/odom", "msg": {
                    "pose": {"pose": {"position": {"x": etat["x"], "y": etat["y"], "z": 0},
                                      "orientation": {"x": 0, "y": 0, "z": math.sin(th / 2), "w": math.cos(th / 2)}}},
                    "twist": {"twist": {"linear": {"x": 0, "y": 0, "z": 0}}}}}))
                await asyncio.sleep(0.05)
        tache = asyncio.create_task(odometrie())
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                d = json.loads(msg.data)
                recus.append(d)
                if d.get("op") == "publish" and d["topic"] == "/cmd_vel":
                    lin, ang = d["msg"]["linear"], d["msg"]["angular"]
                    th = etat["th"]
                    etat["x"] += (lin["x"] * math.cos(th) - lin["y"] * math.sin(th)) * 0.1
                    etat["y"] += (lin["x"] * math.sin(th) + lin["y"] * math.cos(th)) * 0.1
                    etat["th"] += ang["z"] * 0.1
        tache.cancel()
        return ws

    robot = web.Application()
    robot.router.add_get("/", rosbridge)
    serveur = TestServer(robot)
    await serveur.start_server()
    cfg["chien"] = {**cfg["chien"], "reel_autorise": True,
                    "rosbridge": {"url": f"ws://127.0.0.1:{serveur.port}/", "ros": 2}}
    app = creer_app(cfg)
    try:
        async with TestClient(TestServer(app)) as cl:
            ws = await cl.ws_connect("/ws")
            hb = asyncio.create_task(_battre(ws))
            await ws.send_json({"op": "chien_connecter", "adaptateur": "rosbridge"})
            e = await _attendre(ws, lambda m: m["type"] == "chien_etat" and m["adaptateur"] == "rosbridge")
            assert e["reel"] is True
            ops = {(d["op"], d["topic"]) for d in recus}
            assert ("advertise", "/cmd_vel") in ops and ("subscribe", "/odom") in ops
            await ws.send_json({"op": "chien_posture", "posture": "debout"})
            m = await _attendre(ws, lambda m: m["type"] == "chien_refus")
            assert "Observateur" in m["msg"]
            await ws.send_json({"op": "observateur", "present": True, "initiales": "OB"})
            await ws.send_json({"op": "chien_posture", "posture": "debout"})
            m = await _attendre(ws, lambda m: m["type"] == "chien_refus")
            assert "Liste de contrôle" in m["msg"]
            await ws.send_json({"op": "chien_liste", "coches": [c["id"] for c in SALLE["sol"]["liste_controle"]], "par": "SG"})
            await _attendre(ws, lambda m: m["type"] == "chien_etat" and m["liste_complete"])
            await ws.send_json({"op": "chien_posture", "posture": "debout"})
            await _attendre(ws, lambda m: m["type"] == "chien_tel" and m["etat"] == "debout")
            assert {"op": "publish", "topic": "/robo_scene/posture", "msg": {"data": "debout"}} in recus
            # marche vers un point : poursuite par /cmd_vel jusqu'à l'arrivée mesurée par /odom
            await ws.send_json({"op": "chien_aller", "p": [-3.0, -5.0], "duree": 2})
            await _attendre(ws, lambda m: m["type"] == "chien_tel" and math.dist([m["p"][0], m["p"][2]], [-3.0, -5.0]) < 0.1, 12)
            twists = [d["msg"] for d in recus if d.get("op") == "publish" and d["topic"] == "/cmd_vel"]
            assert len(twists) >= 10 and max(t["linear"]["x"] for t in twists) <= 1.0 + 1e-6
            # vitesse vers le nez de scène en mode plateau : la composante fautive est retirée
            app[CTL].chien.tel.update(p=[0.0, 0.0, 0.9], lacet=0.0, v=[0.0, 0.0])
            etat.update(x=7.4, y=-3.0, th=0.0)            # odométrie cohérente avec [0, 0.9] (cap 0, origine [-3, -6.5])
            await asyncio.sleep(0.15)
            n0 = len(recus)
            await ws.send_json({"op": "chien_vitesse", "v": [1.0, 0.0], "lacet_vitesse": 0})
            await asyncio.sleep(0.2)
            dern = [d["msg"] for d in recus[n0:] if d.get("op") == "publish" and d["topic"] == "/cmd_vel"]
            assert dern and dern[-1]["linear"]["x"] == 0
            await ws.send_json({"op": "chien_coupure", "confirmation": "COUPER"})
            await asyncio.sleep(0.3)
            assert {"op": "publish", "topic": "/robo_scene/arret_urgence", "msg": {"data": True}} in recus
            assert app[CTL].chien.urgence
            hb.cancel()
            await ws.close()
    finally:
        await serveur.close()


class SerieFactice:
    def __init__(self):
        self.ecrits = []

    def write(self, b):
        self.ecrits.append(b.decode().strip())

    def close(self):
        pass


async def test_petoi_jetons():
    s = SerieFactice()
    a = AdaptateurPetoi({}, RepereSol([-3, -6.5], 0), serie_factory=lambda: s)
    tel = []
    await a.ouvrir(tel.append)
    try:
        await a.posture("debout")
        await a.vitesse(0.3, 0, 0)
        await a.vitesse(0.3, 0, 0)          # pas de répétition du même jeton
        await a.vitesse(0, 0, 30)
        await a.posture("assis")
        await a.couper()
        assert s.ecrits == ["kbalance", "kwkF", "kwkL", "ksit", "d"]
        assert tel[-1]["position"] == "estimée"
    finally:
        await a.fermer()
