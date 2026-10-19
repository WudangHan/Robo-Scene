"""Drone de scène : zones de vol (parité navigateur ↔ pont), modèle de vol, conduite, contrôleur du drone réel,
adaptateurs (simulation, JSON par ligne, Tello, MAVLink) et garde-fous (observateur, liste de contrôle, ARRÊT, G-06).

python -m pytest -q tests/test_drone.py — les essais JavaScript exigent Node.js ; l'essai MAVLink exige pymavlink."""
import asyncio
import json
import math
import random
import shutil
import socket
import subprocess
import time

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bridge.drone import zones
from bridge.drone.adaptateurs import (FORCER, MASQUE_POSITION, AdaptateurLigneJSON, AdaptateurMavlink,
                                      AdaptateurTello, Repere)
from bridge.drone.controleur import DroneControleur, duree_min
from bridge.gouvernance.biometrie import ViolationBiometrique
from bridge.serveur import CTL, RACINE, charger_config, creer_app

NODE = shutil.which("node")
SALLE = zones.charger_salle()


def node(script: str):
    r = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=120, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def port_libre(udp=True):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM if udp else socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ── Zones (pont) ────────────────────────────────────────────
def test_reperes_selon_le_mode():
    sur_plateau = [k for k, p in SALLE["reperes"].items() if p[2] <= SALLE["volumes"]["plateau"]["z"][1]]
    en_salle = [k for k in SALLE["reperes"] if k not in sur_plateau]
    for k in sur_plateau:
        for m in SALLE["modes"]:
            assert zones.verifier(SALLE, SALLE["reperes"][k], m)["ok"], (k, m)
    for k in en_salle:
        assert not zones.verifier(SALLE, SALLE["reperes"][k], "plateau")["ok"], k
        assert zones.verifier(SALLE, SALLE["reperes"][k], "salle_vide")["ok"], k
    # en représentation, aucun point au-dessus d'un bloc de sièges, à quelque hauteur que ce soit
    for b in SALLE["public"]:
        c = [(b["x"][0] + b["x"][1]) / 2, 6.0, (b["z"][0] + b["z"][1]) / 2]
        v = zones.verifier(SALLE, c, "representation")
        assert not v["ok"] and "public" in v["motif"].lower()


def test_obstacles_marges_et_interpretes():
    assert not zones.verifier(SALLE, [0, 6.4, 0.0], "salle_vide")["ok"]          # manteau (marge 0,5 m)
    assert not zones.verifier(SALLE, [5.2, 3, 0.0], "salle_vide")["ok"]          # cadre côté cour
    assert not zones.verifier(SALLE, [0, 7.0, -1.4], "plateau")["ok"]            # porteuse n° 1
    assert not zones.verifier(SALLE, [2, 0.3, -3], "plateau")["ok"]              # trop bas hors de l'aire
    assert zones.verifier(SALLE, SALLE["aire"]["centre"], "plateau")["ok"]       # posé sur l'aire
    assert not zones.verifier(SALLE, [1, 2.0, -3], "plateau", [[0, -3]])["ok"]   # cylindre d'un interprète
    assert zones.verifier(SALLE, [1, 3.0, -3], "plateau", [[0, -3]])["ok"]       # au-dessus du cylindre
    assert not zones.verifier(SALLE, [float("nan"), 1, 1])["ok"]
    seg = zones.verifier_segment(SALLE, [0, 2, -3], [0, 7.5, 0], "salle_vide")
    assert not seg["ok"] and 0 < seg["fraction"] < 1


def test_duree_min_ralentit_au_lieu_de_refuser():
    R = SALLE["regles"]
    a, b = [0, 2, -3], [4.5, 2, -3]
    assert duree_min(R, a, b, 1.0) == pytest.approx(1.875 * 4.5 / R["vitesse_max_h_m_s"])
    assert duree_min(R, a, b, 20.0) == 20.0


def test_repere_ned_aller_retour():
    for cap in (0, 37, 90, -120):
        r = Repere([0.3, 0.0, -6.5], cap)
        for _ in range(50):
            p = [random.uniform(-6, 6), random.uniform(0, 7), random.uniform(-9, 12)]
            assert r.depuis_ned(*r.vers_ned(p)) == pytest.approx(p, abs=1e-9)
            lacet = random.uniform(-180, 180)
            assert (r.lacet_depuis_ned(r.lacet_vers_ned(lacet)) - lacet + 180) % 360 - 180 == pytest.approx(0, abs=1e-9)
    r = Repere([0, 0, -6.5], 0)
    assert r.vers_ned([0, 1, -7.5]) == pytest.approx((1, 0, -1))      # 1 m vers le lointain = 1 m au nord ; 1 m de haut
    assert r.vers_ned([1, 0, -6.5]) == pytest.approx((0, 1, 0))       # cour = est


def test_g06_aucune_conservation_video():
    class Ctl:
        observateur = None
    with pytest.raises(ViolationBiometrique):
        DroneControleur(Ctl(), {"conserver_video": True})


# ── JavaScript : parité, vol, conduite ──────────────────────
@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_parite_zones_navigateur_et_pont():
    rnd = random.Random(42)
    pts = [[round(rnd.uniform(-10, 10), 3), round(rnd.uniform(-1.5, 9), 3), round(rnd.uniform(-9.5, 20.5), 3)] for _ in range(3000)]
    inter = [[0.5, -3.0], [-3.2, -5.0]]
    script = f"""
      import fs from "fs";
      import {{ verifier }} from "./web/drone/geofence.js";
      const S = JSON.parse(fs.readFileSync("./web/drone/salle.json", "utf8"));
      const pts = {json.dumps(pts)}, inter = {json.dumps(inter)};
      const out = {{}};
      for (const m of Object.keys(S.modes)) out[m] = pts.map((p) => verifier(S, p, {{ mode: m, interpretes: inter }}).ok);
      console.log(JSON.stringify(out));"""
    js = node(script)
    for m in SALLE["modes"]:
        py = [zones.verifier(SALLE, p, m, inter)["ok"] for p in pts]
        assert py == js[m], m
        assert 0 < sum(py) < len(py)


@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_conduite_exemple_et_vol_simule():
    script = """
      import fs from "fs";
      import { compiler, CONDUITE_EXEMPLE } from "./web/drone/conduite.js";
      import { DroneVirtuel, dureeMin } from "./web/drone/vol.js";
      import { verifier } from "./web/drone/geofence.js";
      const S = JSON.parse(fs.readFileSync("./web/drone/salle.json", "utf8"));
      const res = {};
      for (const m of Object.keys(S.modes)) { const c = compiler(S, CONDUITE_EXEMPLE, null, { mode: m }); res[m] = { ok: c.ok, erreurs: c.erreurs.length }; }
      // vol complet de la conduite en salle vide, pas de 20 ms
      const c = compiler(S, CONDUITE_EXEMPLE, null, { mode: "salle_vide" });
      const d = new DroneVirtuel(S, { mode: "salle_vide", turbulence: 0 });
      const ecarts = [], violations = [];
      for (const s of c.segments) {
        let r;
        if (s.action === "decoller") r = d.decoller(s.p1[1] - s.p0[1]);
        else if (s.action === "atterrir") r = d.atterrir();
        else if (s.action === "stationnaire") r = d.stationnaire();
        else r = d.allerA(s.p1, { duree: s.T });
        if (!r.ok) { violations.push(`refus ${s.id} ${r.motif}`); break; }
        for (let t = 0; t < s.T + 6; t += 0.02) {
          d.pas(0.02);
          if (d.enVol && !["atterrissage", "decollage"].includes(d.etat) && !verifier(S, d.p, d.ctx).ok) violations.push(`${s.id} ${d.p.map(x=>x.toFixed(2))}`);
          if (s.action === "aller" && d.consigne.type !== "trajectoire" && t > s.T) break;
          if (s.action === "decoller" && d.etat === "vol") break;
          if (s.action === "atterrir" && d.etat === "au_sol") break;
        }
        for (let k = 0; k < 50; k++) d.pas(0.02);                // 1 s de stabilisation au repère
        ecarts.push(Math.hypot(...d.p.map((x, i) => x - s.p1[i])));
      }
      res.vol = { ecart_max: Math.max(...ecarts), violations: violations.slice(0, 5), etat: d.etat, batterie: d.batterie };
      // mur virtuel : poussée continue vers la salle en mode « plateau seul »
      const m = new DroneVirtuel(S, { mode: "plateau", turbulence: 0 });
      m.decoller(2); for (let i = 0; i < 400; i++) m.pas(0.02);
      m.lacet = 0; let pire = -1e9;
      for (let i = 0; i < 1500; i++) { m.manuel([0.3, 1, 0.2], 0); m.pas(0.02); pire = Math.max(pire, m.p[2]); if (!verifier(S, m.p, m.ctx).ok) { res.mur_viole = m.p; break; } }
      res.mur = pire;
      // ARRÊT : descente contrôlée, verrou jusqu'au réarmement ; coupure : chute
      m.arretUrgence("essai"); for (let i = 0; i < 1500 && m.enVol; i++) m.pas(0.02);
      res.arret = { etat: m.etat, decollage_refuse: !m.decoller().ok, rearme: m.rearmer().ok, redecolle: m.decoller().ok };
      for (let i = 0; i < 300; i++) m.pas(0.02);
      res.coupure_sans_mot = m.couperMoteurs("oui").ok;
      m.couperMoteurs("COUPER"); const etat1 = m.etat; for (let i = 0; i < 300; i++) m.pas(0.02);
      res.coupure = [etat1, m.etat];
      // batterie : retour puis atterrissage automatiques
      const b = new DroneVirtuel(S, { turbulence: 0 }); b.decoller(1.5); for (let i = 0; i < 300; i++) b.pas(0.02);
      b.allerA([4.5, 2, -3], {}); for (let i = 0; i < 400; i++) b.pas(0.02);
      b.batterie = S.regles.batterie_retour_pct - 0.5; for (let i = 0; i < 3000 && b.enVol; i++) b.pas(0.02);
      res.batterie = { etat: b.etat, distance_aire: Math.hypot(b.p[0] - S.aire.centre[0], b.p[2] - S.aire.centre[2]) };
      // perte de liaison : stationnaire puis atterrissage
      const l = new DroneVirtuel(S, { turbulence: 0 }); l.decoller(1.5); for (let i = 0; i < 300; i++) l.pas(0.02);
      l.liaison.exigee = true; l.signalLiaison(l.t); const etats = new Set();
      for (let i = 0; i < 800; i++) { l.pas(0.02); etats.add(l.consigne.type); }
      res.liaison = { etat: l.etat, consignes: [...etats] };
      res.duree = dureeMin(S.regles, [0, 2, -3], [4.5, 2, -3], 1.0).T;
      console.log(JSON.stringify(res));"""
    r = node(script)
    assert r["salle_vide"]["ok"] and not r["plateau"]["ok"] and not r["representation"]["ok"]
    assert r["vol"]["violations"] == [], r["vol"]
    assert r["vol"]["ecart_max"] < 0.05 and r["vol"]["etat"] == "au_sol"
    lim = SALLE["volumes"]["plateau"]["z"][1] - SALLE["regles"]["marge_m"]
    assert "mur_viole" not in r and r["mur"] <= lim + 1e-6
    assert r["arret"] == {"etat": "au_sol", "decollage_refuse": True, "rearme": True, "redecolle": True}
    assert r["coupure_sans_mot"] is False and r["coupure"] == ["chute", "coupe"]
    assert r["batterie"]["etat"] == "au_sol" and r["batterie"]["distance_aire"] < SALLE["aire"]["rayon"]
    assert r["liaison"]["etat"] == "au_sol" and "stationnaire" in r["liaison"]["consignes"]
    assert r["duree"] == pytest.approx(duree_min(SALLE["regles"], [0, 2, -3], [4.5, 2, -3], 1.0))


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


async def test_page_et_drone_simule_par_le_pont(cfg):
    app = creer_app(cfg)
    async with TestClient(TestServer(app)) as cl:
        r = await cl.get("/drone")
        html = await r.text()
        assert r.status == 200 and "/static/drone/app.js" in html and "importmap" in html
        for f in ("geofence.js", "vol.js", "conduite.js", "theatre3d.js", "camera4k.js", "app.js", "drone.css", "salle.json"):
            assert (await cl.get(f"/static/drone/{f}")).status == 200, f
        ws = await cl.ws_connect("/ws")
        await ws.send_json({"op": "drone_connecter", "adaptateur": "mavlink"})
        m = await _attendre(ws, lambda m: m["type"] == "drone_refus")
        assert "reel_autorise" in m["msg"]
        await ws.send_json({"op": "drone_connecter", "adaptateur": "simulation"})
        e = await _attendre(ws, lambda m: m["type"] == "drone_etat" and m["adaptateur"] == "simulation")
        assert e["reel"] is False and e["mode"] == "plateau"
        hb = asyncio.create_task(_battre(ws))
        await ws.send_json({"op": "drone_decoller", "hauteur": 1.5})
        await _attendre(ws, lambda m: m["type"] == "drone_tel" and m["etat"] == "vol")
        await ws.send_json({"op": "drone_aller", "p": "salle_centre"})          # salle fermée en mode plateau
        m = await _attendre(ws, lambda m: m["type"] == "drone_refus")
        assert "Destination refusée" in m["msg"]
        await ws.send_json({"op": "drone_aller", "p": "centre", "duree": 3})
        a = await _attendre(ws, lambda m: m["type"] == "drone_aller")
        assert a["duree"] >= 3
        t = await _attendre(ws, lambda m: m["type"] == "drone_tel" and math.dist(m["p"], [0, 2, -3]) < 0.1, 12)
        assert t["etat"] == "vol"
        # ARRÊT global (n'importe quelle page) : le drone se pose et reste verrouillé
        await ws.send_json({"op": "estop", "motif": "essai"})
        await _attendre(ws, lambda m: m["type"] == "drone_tel" and m["etat"] == "au_sol" and m["urgence"], 12)
        await ws.send_json({"op": "drone_decoller"})
        m = await _attendre(ws, lambda m: m["type"] == "drone_refus")
        assert "Arrêt d'urgence" in m["msg"]
        await ws.send_json({"op": "rearmer"})
        await asyncio.sleep(0.2)
        assert app[CTL].drone.urgence is False
        hb.cancel()
        journal = app[CTL].seance.chemin_evt.read_text(encoding="utf-8")
        actions = [json.loads(x).get("action") for x in journal.splitlines() if '"drone"' in x]
        assert {"connexion", "decoller", "aller", "arret_urgence"} <= set(actions)
        await ws.close()


async def _battre(ws):
    while True:
        await ws.send_json({"op": "drone_hb"})
        await asyncio.sleep(0.2)


async def test_chien_de_garde_page_muette(cfg):
    app = creer_app(cfg)
    async with TestClient(TestServer(app)) as cl:
        d = app[CTL].drone
        d.R = {**d.R, "perte_liaison_stationnaire_s": 0.3, "perte_liaison_atterrir_s": 0.8}
        ws = await cl.ws_connect("/ws")
        await ws.send_json({"op": "drone_connecter", "adaptateur": "simulation"})
        await _attendre(ws, lambda m: m["type"] == "drone_etat" and m["adaptateur"])
        await ws.send_json({"op": "drone_decoller", "hauteur": 1.0})
        await _attendre(ws, lambda m: m["type"] == "drone_tel" and m["etat"] == "vol", 10)
        # plus aucun battement : stationnaire, puis atterrissage
        await _attendre(ws, lambda m: m["type"] == "drone_tel" and m["etat"] in ("atterrissage", "au_sol"), 10)
        journal = app[CTL].seance.chemin_evt.read_text(encoding="utf-8")
        assert "page de pilotage muette" in journal
        await ws.close()


class Compagnon(asyncio.DatagramProtocol):
    """Ordinateur compagnon factice : consigne les commandes et renvoie la télémétrie de la dernière position."""
    def __init__(self):
        self.recus, self.p, self.etat, self.adr = [], [0, 0, -6.5], "au_sol", None

    def connection_made(self, tr):
        self.tr = tr

    def datagram_received(self, data, addr):
        self.adr = addr
        m = json.loads(data.decode())
        self.recus.append(m)
        if m["cmd"] == "decoller":
            self.p = [self.p[0], m["hauteur"], self.p[2]]
            self.etat = "vol"
        elif m["cmd"] == "position":
            self.p = m["p"]
        elif m["cmd"] in ("atterrir", "urgence"):
            self.p = [self.p[0], 0, self.p[2]]
            self.etat = "au_sol"
        self.tr.sendto((json.dumps({"t": "tel", "p": self.p, "etat": self.etat, "arme": self.etat == "vol",
                                    "batterie": 88, "lacet": 180}) + "\n").encode(), addr)


async def test_conditions_du_vol_reel_ligne_json(cfg):
    port = port_libre()
    loop = asyncio.get_running_loop()
    tr, comp = await loop.create_datagram_endpoint(Compagnon, local_addr=("127.0.0.1", port))
    cfg["drone"] = {**cfg["drone"], "reel_autorise": True, "ligne_json": {"hote": "127.0.0.1", "port": port}}
    app = creer_app(cfg)
    try:
        async with TestClient(TestServer(app)) as cl:
            ws = await cl.ws_connect("/ws")
            hb = asyncio.create_task(_battre(ws))
            await ws.send_json({"op": "drone_connecter", "adaptateur": "ligne_json"})
            e = await _attendre(ws, lambda m: m["type"] == "drone_etat" and m["adaptateur"] == "ligne_json")
            assert e["reel"] is True and not e["liste_complete"]
            await ws.send_json({"op": "drone_decoller"})
            m = await _attendre(ws, lambda m: m["type"] == "drone_refus")
            assert "Observateur" in m["msg"]
            await ws.send_json({"op": "observateur", "present": True, "initiales": "OB"})
            await ws.send_json({"op": "drone_decoller"})
            m = await _attendre(ws, lambda m: m["type"] == "drone_refus")
            assert "Liste de contrôle" in m["msg"]
            ids = [c["id"] for c in SALLE["liste_controle"]]
            await ws.send_json({"op": "drone_liste", "coches": ids, "par": ""})
            m = await _attendre(ws, lambda m: m["type"] == "drone_refus")
            assert "initiales" in m["msg"]
            await ws.send_json({"op": "drone_liste", "coches": ids, "par": "SG"})
            await _attendre(ws, lambda m: m["type"] == "drone_etat" and m["liste_complete"])
            await ws.send_json({"op": "drone_mode", "mode": "representation"})
            m = await _attendre(ws, lambda m: m["type"] == "drone_refus")
            assert "représentation" in m["msg"]
            await ws.send_json({"op": "drone_decoller", "hauteur": 1.5})
            await _attendre(ws, lambda m: m["type"] == "drone_tel" and m["etat"] == "vol")
            await ws.send_json({"op": "drone_aller", "p": [0, 2, -3], "duree": 2})
            await _attendre(ws, lambda m: m["type"] == "drone_tel" and m["p"] and math.dist(m["p"], [0, 2, -3]) < 0.02, 8)
            positions = [m["p"] for m in comp.recus if m["cmd"] == "position"]
            assert len(positions) >= 10                                   # trajet découpé (10 Hz)
            assert all(zones.verifier(SALLE, p, "plateau")["ok"] for p in positions)
            # vitesse vers la salle en mode plateau : la composante qui franchirait le cadre est retirée
            await asyncio.sleep(0.5)                                      # fin du trajet découpé
            comp.p = [0, 2, 0.6]
            app[CTL].drone.tel["p"], app[CTL].drone.tel["v"] = [0, 2, 0.6], [0, 0, 0]
            await ws.send_json({"op": "drone_vitesse", "v": [0.5, 0, 1.0], "lacet_vitesse": 0})
            await asyncio.sleep(0.3)
            v = [m for m in comp.recus if m["cmd"] == "vitesse"][-1]["v"]
            assert v[2] == 0 and v[0] == 0.5
            await ws.send_json({"op": "drone_coupure", "confirmation": "non"})
            m = await _attendre(ws, lambda m: m["type"] == "drone_refus")
            assert "COUPER" in m["msg"]
            await ws.send_json({"op": "drone_coupure", "confirmation": "COUPER"})
            await asyncio.sleep(0.3)
            assert comp.recus[-1]["cmd"] in ("couper", "urgence") and app[CTL].drone.urgence
            hb.cancel()
            await ws.close()
    finally:
        tr.close()


# ── Adaptateurs Tello et MAVLink contre des appareils factices ──
class TelloFactice(asyncio.DatagramProtocol):
    def __init__(self):
        self.recus = []

    def connection_made(self, tr):
        self.tr = tr

    def datagram_received(self, data, addr):
        t = data.decode()
        self.recus.append(t)
        self.tr.sendto(b"100" if t == "battery?" else b"ok", addr)


async def test_tello_decomposition_des_deplacements():
    port = port_libre()
    loop = asyncio.get_running_loop()
    tr, tello = await loop.create_datagram_endpoint(TelloFactice, local_addr=("127.0.0.1", port))
    a = AdaptateurTello({"hote": "127.0.0.1", "port": port, "port_etat": port_libre()}, Repere([0, 0, -6.5], 0))
    tel = []
    await a.ouvrir(tel.append)
    try:
        await a.decoller(1.5)
        # nez vers le lointain (lacet 180) : aller vers la salle = reculer ; cour est alors à droite du drone
        await a.aller([1.0, 1.5, -3.0], 0.0, 0.5)
        cmds = tello.recus
        assert cmds[0] == "command" and "takeoff" in cmds and "up 70" in cmds
        assert "back 350" in cmds and "right 100" in cmds and ("cw 180" in cmds or "ccw 180" in cmds)
        await a.aller([1.0, 1.5, -3.0], 90.0, 0.5)          # 0 → 90 : vers cour, sens antihoraire vu de dessus
        assert tello.recus[-1] == "ccw 90"
        assert tel[-1]["p"] == pytest.approx([1.0, 1.5, -3.0]) and tel[-1]["position"] == "estimée"
        await a.vitesse([0, 0, 0.5], 0)
        await asyncio.sleep(0.05)
        assert tello.recus[-1].startswith("rc ")
        await a.couper()
        await asyncio.sleep(0.05)
        assert "emergency" in tello.recus
    finally:
        await a.fermer()
        tr.close()


def test_mavlink_consignes_ardupilot():
    mavutil = pytest.importorskip("pymavlink.mavutil")
    import threading

    async def scenario():
        port = port_libre()
        vehicule = mavutil.mavlink_connection(f"udpout:127.0.0.1:{port}", source_system=1, source_component=1)
        arret = threading.Event()

        def battre():
            while not arret.is_set():
                vehicule.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_QUADROTOR, mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
                                            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 4, 0)
                vehicule.mav.local_position_ned_send(0, 1.0, 2.0, -1.5, 0, 0, 0)
                arret.wait(0.1)
        fil = threading.Thread(target=battre, daemon=True)
        fil.start()
        a = AdaptateurMavlink({"connexion": f"udpin:127.0.0.1:{port}", "delai_s": 5}, Repere([0, 0, -6.5], 0))
        tel = []
        try:
            await a.ouvrir(tel.append)
            await asyncio.sleep(0.5)
            # télémétrie NED → théâtre : nord 1 m = 1 m vers le lointain ; est 2 m = cour ; bas −1,5 = 1,5 m de haut
            assert tel and tel[-1]["p"] == pytest.approx([2.0, 1.5, -7.5])
            await a.position([0, 2, -3], None)
            await a.couper()
            vus = {}
            t0 = time.monotonic()
            while time.monotonic() - t0 < 4 and len(vus) < 2:
                m = await asyncio.to_thread(vehicule.recv_match, type=["SET_POSITION_TARGET_LOCAL_NED", "COMMAND_LONG"],
                                            blocking=True, timeout=1)
                if m:
                    vus[m.get_type()] = m
            sp, cl = vus["SET_POSITION_TARGET_LOCAL_NED"], vus["COMMAND_LONG"]
            assert sp.type_mask == MASQUE_POSITION and sp.coordinate_frame == mavutil.mavlink.MAV_FRAME_LOCAL_NED
            assert (sp.x, sp.y, sp.z) == pytest.approx((-3.5, 0.0, -2.0))     # 3,5 m vers la salle = 3,5 m au sud
            assert cl.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM and cl.param1 == 0 and cl.param2 == FORCER
        finally:
            arret.set()
            await a.fermer()
            vehicule.close()
    asyncio.run(scenario())
