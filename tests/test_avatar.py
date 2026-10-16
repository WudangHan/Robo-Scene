"""Tests du robot virtuel : python -m pytest -q tests/test_avatar.py
Les tests JavaScript (interprète de directives, cohérence des émotions) s'exécutent avec Node.js
s'il est installé ; sinon ils sont ignorés."""
import asyncio
import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bridge.partenaire import avatar, variations
from bridge.serveur import CTL, RACINE, charger_config, creer_app

WEB = RACINE / "web"
NODE = shutil.which("node")


def run(c):
    return asyncio.run(c)


def node(script: str):
    r = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# ── Schéma et validation (pont) ─────────────────────────────
def test_schema_coherent():
    S = avatar.schema()
    assert len(S["dofs"]) >= 30
    assert all(d["min"] < d["max"] and d["groupe"] in S["groupes"] for d in S["dofs"].values())
    # le répertoire émotionnel du robot virtuel prolonge celui du partenaire
    assert set(variations.EMOTIONS) <= set(S["emotions"])
    assert all(S["plateau"]["x"][0] <= x <= S["plateau"]["x"][1] for x, _ in S["lieux"].values())


def test_validation_bornes_et_rejets():
    ok, rejets = avatar.valider([
        {"type": "articulation", "dof": "coude_d.flexion", "valeur": 400},
        {"type": "articulation", "dof": "nez.rotation", "valeur": 10},
        {"type": "emotion", "nom": "joie", "intensite": 42},
        {"type": "emotion", "nom": "extase"},
        {"type": "visage", "au": {"au12": 3, "script": 1, "au46_g": 0.5}},
        {"type": "deplacer", "x": 99, "z": -99},
        {"type": "apparence", "cle": "haut", "valeur": "rouge"},
        {"type": "apparence", "cle": "haut", "valeur": "javascript:alert(1)"},
        {"type": "apparence", "cle": "taille", "valeur": 400},
        {"type": "executer_code", "code": "rm -rf"},
        "pas un objet",
    ])
    assert len(ok) == 6 and len(rejets) == 5
    assert ok[0]["valeur"] == 150 and ok[1]["intensite"] == 10
    assert ok[2]["au"] == {"au12": 1.0, "au46_g": 0.5}
    assert ok[3]["x"] == 2.0 and ok[3]["z"] == -1.5 and ok[5]["valeur"] == 205


def test_interpreter_sans_cle():
    r = run(avatar.interpreter(None, "fais la roue", {}))
    assert r["actions"] == [] and r["moteur"] == "aucun"


class _FauxService:
    """Imite ServiceModeles.generer : renvoie une proposition dont une action est hors vocabulaire."""
    def __init__(self, texte):
        self.texte = texte
        self.appels = []

    async def generer(self, role, systeme, contenu, **kw):
        self.appels.append({"role": role, "systeme": systeme, **kw})
        return SimpleNamespace(texte=self.texte, modele_exact="claude-sonnet-5-5", modele_demande="claude-sonnet-5-5",
                               famille="claude-sonnet", trace=lambda: {"version_modele": "claude-sonnet-5-5"})


def test_interpreter_modele_revalide():
    rep = json.dumps({"actions": [{"type": "geste", "nom": "reverence"}, {"type": "geste", "nom": "salto"},
                                  {"type": "articulation", "dof": "tronc.flexion", "valeur": 300}],
                      "confiance": 0.95, "justification": "Saluer la salle profondément."})
    s = _FauxService(rep)
    r = run(avatar.interpreter(s, "incline-toi très bas devant la salle", {"pose": {}}))
    assert [a["type"] for a in r["actions"]] == ["geste", "articulation"]
    assert r["actions"][1]["valeur"] == 80
    assert r["confiance"] == 0.5                       # plafonnée : une action a été écartée
    assert r["trace"]["version_modele"] == "claude-sonnet-5-5"
    kw = s.appels[0]
    assert kw["role"] == "commande" and "temperature" in kw and "top_p" not in kw   # jamais les deux ensemble


# ── Pont : page, fichiers, opérations ───────────────────────
@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    c = charger_config(RACINE / "config.toml")
    c["robot"]["transport"] = "sim"
    c["protocole"]["dossier_corpus"] = str(tmp_path / "corpus")
    return c


def test_page_et_operations_du_pont(cfg):
    async def scenario():
        app = creer_app(cfg)
        async with TestClient(TestServer(app)) as cl:
            r = await cl.get("/avatar")
            html = await r.text()
            assert r.status == 200 and "importmap" in html and "/static/avatar/app.js" in html
            for f in ("/static/vendor/three.module.min.js", "/static/vendor/OrbitControls.js", "/static/avatar/schema.json",
                      "/static/avatar/directives.js", "/static/avatar/humanoide.js"):
                assert (await cl.get(f)).status == 200, f
            ws = await cl.ws_connect("/ws")

            async def op(o, **d):
                await ws.send_json({"op": o, **d})
                while True:
                    m = json.loads((await asyncio.wait_for(ws.receive(), 6)).data)
                    if m["type"] in (o, "p_erreur"):
                        return m

            e = await op("p_avatar_etat")
            assert e["type"] == "p_avatar_etat" and e["moteur"] == "déterministe"
            i = await op("p_avatar_interpreter", texte="fais la roue", etat={})
            assert i["actions"] == [] and i["moteur"] == "aucun"
            await ws.send_json({"op": "p_avatar_journal", "evenement": {
                "texte": "lève le bras droit", "origine": "vocal", "source": "règles",
                "actions": [{"type": "articulation", "dof": "epaule_d.flexion", "valeur": 999}, {"type": "inconnu"}],
                "ignores": ["fais la roue"]}})
            # le pilotage par le robot virtuel passe par la couche de sécurité, avec une origine distincte
            await ws.send_json({"op": "articulations", "deg": [90, 300, 90, 90], "ms": 0, "origine": "avatar"})
            await asyncio.sleep(0.4)
            journal = app[CTL].seance.chemin_evt.read_text(encoding="utf-8")
            lignes = [json.loads(x) for x in journal.splitlines() if x.strip()]
            d = next(x for x in lignes if x.get("action") == "avatar_directive")
            assert d["actions"] == [{"type": "articulation", "dof": "epaule_d.flexion", "valeur": 180.0}]
            c = next(x for x in lignes if x.get("type") == "articulations" and x.get("origine") == "avatar")
            assert c["envoye"][1] <= 160                  # bornée par config.toml
            await ws.close()
    run(scenario())


# ── JavaScript (Node.js) ────────────────────────────────────
@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_interprete_de_directives_js():
    cas = {
        "lève le bras droit": [("articulation", "epaule_d.flexion", 160)],
        "lève les deux bras lentement": [("articulation", "epaule_g.flexion", 160)],
        "tourne la tête à gauche": [("articulation", "tete.rotation", 55)],
        "tourne la tête vers ma gauche": [("articulation", "tete.rotation", -55)],
        "va côté cour": [("deplacer", "x", 1.5)],
        "va côté jardin": [("deplacer", "x", -1.5)],
        "sois très en colère": [("emotion", "colère", 9.5)],
        "fais un clin d'oeil": [("geste", "clin_oeil", None)],
        "assieds-toi": [("pose", "assis", None)],
        "mets une chemise rouge et un pantalon noir": [("apparence", "haut", "rouge"), ("apparence", "bas", "noir")],
        "deviens triste, puis dis « Je ne reviendrai pas. »": [("emotion", "tristesse", 7), ("dire", "Je ne reviendrai pas.", None)],
        "lève le bras gauche à 45 degrés": [("articulation", "epaule_g.flexion", 45)],
        "avance de trois pas": [("deplacer", "avant", 1.8)],
    }
    script = f"""
      import {{ interpreter }} from "./web/avatar/directives.js";
      import fs from "node:fs";
      const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
      const cas = {json.dumps(list(cas))};
      console.log(JSON.stringify(Object.fromEntries(cas.map((c) => [c, interpreter(c, S)]))));
    """
    out = node(script)
    for phrase, attendus in cas.items():
        acts = out[phrase]["actions"]
        assert not out[phrase]["ignores"], phrase
        for typ, cle, val in attendus:
            trouve = [a for a in acts if a["type"] == typ]
            assert trouve, (phrase, typ)
            if typ == "articulation":
                assert any(a["dof"] == cle and a["valeur"] == val for a in trouve), (phrase, trouve)
            elif typ == "deplacer":
                assert any(a.get(cle) == val for a in trouve), (phrase, trouve)
            elif typ == "emotion":
                assert any(a["nom"] == cle and a["intensite"] == val for a in trouve), (phrase, trouve)
            elif typ in ("geste", "pose"):
                assert any(a["nom"] == cle for a in trouve), (phrase, trouve)
            elif typ == "apparence":
                assert any(a["cle"] == cle and a["valeur"] == val for a in trouve), (phrase, trouve)
            elif typ == "dire":
                assert any(a["texte"] == cle for a in trouve), (phrase, trouve)
    inc = node("""
      import { interpreter } from "./web/avatar/directives.js";
      import fs from "node:fs";
      const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
      console.log(JSON.stringify(interpreter("fais quelque chose d'étrange", S)));
    """)
    assert inc["actions"] == [] and inc["ignores"]


@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_validation_js_et_python_concordent():
    actions = [{"type": "articulation", "dof": "coude_d.flexion", "valeur": 400}, {"type": "emotion", "nom": "extase"},
               {"type": "visage", "au": {"au12": 3, "x": 1}}, {"type": "deplacer", "x": 99}, {"type": "inconnu"},
               {"type": "apparence", "cle": "haut", "valeur": "#12ab34"}, {"type": "apparence", "cle": "peau", "valeur": "verte"}]
    js = node(f"""
      import {{ valider }} from "./web/avatar/directives.js";
      import fs from "node:fs";
      const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
      const r = valider({json.dumps(actions)}, S);
      console.log(JSON.stringify({{ok: r.actions, n: r.rejets.length}}));
    """)
    ok, rejets = avatar.valider(actions)
    assert js["n"] == len(rejets)
    assert [a["type"] for a in js["ok"]] == [a["type"] for a in ok]
    assert js["ok"][0]["valeur"] == ok[0]["valeur"] == 150


@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_emotions_js_alignees_sur_le_partenaire():
    js = node("""
      import { EMOTIONS, GESTES, POSES } from "./web/avatar/emotions.js";
      import fs from "node:fs";
      const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
      const gestes = Object.fromEntries(Object.entries(GESTES).map(([n, f]) => [n, f(1, "devant")]));
      console.log(JSON.stringify({ E: EMOTIONS, gestes, poses: POSES, dofs: Object.keys(S.dofs), schemaGestes: S.gestes, schemaPoses: S.poses }));
    """)
    for nom, e in variations.EMOTIONS.items():
        assert js["E"][nom]["effort"] == pytest.approx(list(e["effort"])), nom
        assert js["E"][nom]["prosodie"] == pytest.approx(list(e["prosodie"])), nom
    dofs = set(js["dofs"])
    for nom, e in js["E"].items():
        assert set(e["posture"]) <= dofs, nom
        assert all(0 <= v <= 1 for v in e["au"].values()), nom
    assert set(js["schemaGestes"]) == set(js["gestes"]) and set(js["schemaPoses"]) == set(js["poses"])
    for nom, images in js["gestes"].items():
        assert images and all(images[i]["t"] <= images[i + 1]["t"] for i in range(len(images) - 1)), nom
        for im in images:
            for cle in (im.get("p") or {}):
                n = cle.replace("_X", "_d").replace("_Y", "_g")
                assert n in dofs or n.startswith("pointe_"), (nom, cle)


@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_toutes_les_commandes_repondent():
    """Chaque exemple du vocabulaire produit des actions valides ; fautes de frappe et formulations voisines
    sont reconnues ; une directive incomprise reçoit des suggestions au lieu d'être ignorée en silence."""
    out = node("""
      import { interpreter, EXEMPLES } from "./web/avatar/directives.js";
      import fs from "node:fs";
      const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
      const essais = ["lève le brass droit", "sautte", "fais la reverance", "marche vers le jardain", "fais semblant de dormir",
                      "fais le tour de la scène", "tourne sur toi-même", "fais les cent pas", "frappe à la porte", "pointe le pied droit"];
      const r = (t) => interpreter(t, S);
      console.log(JSON.stringify({
        n: EXEMPLES.length,
        echecs: EXEMPLES.filter((e) => { const x = r(e); return !x.actions.length || x.ignores.length; }),
        essais: Object.fromEntries(essais.map((t) => [t, r(t).actions.map((a) => a.nom || a.dof || a.type)])),
        incompris: r("fais une roue arrière en équilibre"),
      }));
    """)
    assert out["n"] >= 180 and out["echecs"] == []
    e = out["essais"]
    assert e["lève le brass droit"][0] == "epaule_d.flexion" and e["sautte"] == ["sauter"]
    assert e["fais la reverance"] == ["reverence"] and e["marche vers le jardain"] == ["deplacer"]
    assert e["fais semblant de dormir"] == ["dormir"] and len(e["fais le tour de la scène"]) == 5
    assert e["tourne sur toi-même"] == ["orienter"] and e["frappe à la porte"] == ["frapper_porte"]
    assert e["pointe le pied droit"] == ["cheville_d.flexion"]
    assert out["incompris"]["actions"] == [] and out["incompris"]["ignores"]
