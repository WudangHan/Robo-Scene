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


@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_phonetisation_francaise_des_visemes():
    """Audit du 2026-10-16 (chantier 5) : digrammes, nasales, lettres muettes et liaisons."""
    cas = ["où", "bonjour", "moi", "photo", "ils parlent", "les amis", "les copains", "temps", "chanter", "la mer",
           "quel", "beau", "bien", "est-il", "les hommes"]
    out = node(f"""
      import {{ visemes }} from "./web/avatar/parole.js";
      const cas = {json.dumps(cas)};
      const f = (t) => visemes(t).filter((s) => s.v !== "repos" || s.muet)
        .map((s) => t.toLowerCase().substr(s.i, s.n) + ":" + (s.muet ? "-" : s.v)).join(" ");
      console.log(JSON.stringify(Object.fromEntries(cas.map((c) => [c, f(c)]))));
    """)
    attendu = {
        "où": "où:ou",
        "bonjour": "b:pbm on:on j:ch ou:ou r:r",
        "moi": "m:pbm o:ou i:a",                                         # /wa/
        "photo": "ph:fv o:o t:dent o:o",
        "ils parlent": "i:i l:dent s:- p:pbm a:a r:r l:dent e:- n:- t:-",  # -ent verbal muet
        "les amis": "l:dent e:e s:dent a:a m:pbm i:i s:-",               # liaison
        "les copains": "l:dent e:e s:- c:k o:o p:pbm ain:in s:-",
        "temps": "t:dent em:an p:- s:-",
        "chanter": "ch:ch an:an t:dent e:e r:-",
        "la mer": "l:dent a:a m:pbm e:e r:r",
        "quel": "q:k u:- e:e l:dent",
        "beau": "b:pbm eau:o",
        "bien": "b:pbm i:i en:in",
        "est-il": "e:e s:- t:dent i:i l:dent",
        "les hommes": "l:dent e:e s:dent h:- o:o m:pbm m:pbm e:- s:-",
    }
    assert out == attendu


@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_ancrage_plantaire(tmp_path):
    """Audit du 2026-10-16 (chantier 5) : aucun pied ne flotte ni ne s'enfonce, hors saut et hors tabouret."""
    crochet = tmp_path / "three.mjs"
    vendor = (WEB / "vendor" / "three.module.min.js").as_uri()
    crochet.write_text('import { register } from "node:module";\n'
                       'register("data:text/javascript," + encodeURIComponent('
                       f'`export async function resolve(s, c, n) {{ if (s === "three") return {{ url: "{vendor}", '
                       'shortCircuit: true }; return n(s, c); }`));\n', encoding="utf-8")
    script = """
      import fs from "node:fs";
      import { Humanoide } from "./web/avatar/humanoide.js";
      import { POSES } from "./web/avatar/emotions.js";
      const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
      const mesure = (P, extra = {}) => { const H = new Humanoide(S); H.appliquer(P, extra); H.racine.updateMatrixWorld(true);
        return { g: H.hauteurSemelle("g"), d: H.hauteurSemelle("d"), genou: H.os.genou_g.rotation.x * 180 / Math.PI }; };
      const out = {};
      for (const [nom, P] of Object.entries(POSES)) if (!["assis", "penseur"].includes(nom)) out[nom] = mesure(P);
      out.flechi = mesure({ "genou_g.flexion": 40, "genou_d.flexion": 40 });
      out.abaisse = mesure({ "bassin.abaissement": 30 });
      out.saut = mesure({ "bassin.elevation": 30 });
      out.jambe_levee = mesure({ "hanche_g.flexion": 80 });
      out.sans_ancrage = mesure({ "bassin.abaissement": 30 }, { ancrage: false });
      console.log(JSON.stringify(out));
    """
    r = subprocess.run([NODE, "--import", crochet.as_uri(), "--input-type=module", "-e", script],
                       capture_output=True, text=True, timeout=60, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    for nom in [n for n in out if n not in ("saut", "jambe_levee", "sans_ancrage")]:
        appui = min(out[nom]["g"], out[nom]["d"])
        assert abs(appui) < 0.006, (nom, out[nom])        # pied d'appui au contact du plateau (± 6 mm)
    assert out["abaisse"]["genou"] > 60                   # l'abaissement est absorbé par la flexion du genou
    assert out["saut"]["g"] > 0.25 and out["saut"]["d"] > 0.25        # le saut quitte le sol
    assert out["jambe_levee"]["g"] > 0.3 and abs(out["jambe_levee"]["d"]) < 0.006
    assert out["sans_ancrage"]["g"] < -0.25               # témoin : sans la passe, le pied s'enfonçait


@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_anti_echo_de_la_dictee():
    """16 oct. 2026 : le micro captait « Pardon, je n'ai pas compris… » et le robot se répondait sans fin."""
    out = node("""
      import { estEcho } from "./web/avatar/parole.js";
      const dits = ["Pardon, je n'ai pas compris. Dites « aide » pour connaître mes commandes.", "Je ne reviendrai pas."];
      const cas = ["pardon je n'ai pas compris dites aide pour connaitre mes commandes", "dites aide pour connaître mes commandes",
                   "je n'ai pas compris", "Je ne reviendrai pas", "lève le bras droit", "aide", "sois très en colère",
                   "pardon"];
      console.log(JSON.stringify(Object.fromEntries(cas.map((c) => [c, estEcho(c, dits)]))));
    """)
    assert out == {"pardon je n'ai pas compris dites aide pour connaitre mes commandes": True,
                   "dites aide pour connaître mes commandes": True, "je n'ai pas compris": True,
                   "Je ne reviendrai pas": True, "lève le bras droit": False,
                   "aide": False, "sois très en colère": False, "pardon": False}   # directives d'un mot : jamais un écho


@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_geste_tenu_pour_les_boutons_en_bascule(tmp_path):
    """16 oct. 2026 : un bouton de geste fait le geste et le TIENT ; sans « tenir », le geste revient seul."""
    crochet = tmp_path / "three.mjs"
    vendor = (WEB / "vendor" / "three.module.min.js").as_uri()
    crochet.write_text('import { register } from "node:module";\n'
                       'register("data:text/javascript," + encodeURIComponent('
                       f'`export async function resolve(s, c, n) {{ if (s === "three") return {{ url: "{vendor}", '
                       'shortCircuit: true }; return n(s, c); }`));\n', encoding="utf-8")
    script = """
      import fs from "node:fs";
      import { Humanoide } from "./web/avatar/humanoide.js";
      import { Animateur } from "./web/avatar/animation.js";
      const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
      const a = new Animateur(new Humanoide(S), S);
      a.prendrePose("repos"); a.vitesse = 20;
      const repos = a.instantane();
      const ecart = () => Math.max(...Object.keys(repos).map((k) => Math.abs((a.base[k] || 0) - (repos[k] || 0))));
      await a.jouerGeste("bras_au_ciel", { tenir: true });
      const tenu = ecart();
      a.restaurer(repos);
      await a.jouerGeste("bras_au_ciel");
      const libre = ecart();
      console.log(JSON.stringify({ tenu, libre }));
    """
    r = subprocess.run([NODE, "--import", crochet.as_uri(), "--input-type=module", "-e", script],
                       capture_output=True, text=True, timeout=60, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["tenu"] > 60          # bras levés et tenus (degrés)
    assert out["libre"] < 1e-6       # sans bascule : retour automatique à la position d'avant


@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_contact_main_visage(tmp_path):
    """16 oct. 2026 : la main qui devait toucher le visage s'arrêtait au bas du cou ; elle se pose désormais sur le
    repère visé (bouche, menton, yeux, front, tempe, oreille, crâne), même quand la tête bouge."""
    crochet = tmp_path / "three.mjs"
    vendor = (WEB / "vendor" / "three.module.min.js").as_uri()
    crochet.write_text('import { register } from "node:module";\n'
                       'register("data:text/javascript," + encodeURIComponent('
                       f'`export async function resolve(s, c, n) {{ if (s === "three") return {{ url: "{vendor}", '
                       'shortCircuit: true }; return n(s, c); }`));\n', encoding="utf-8")
    script = """
      import fs from "node:fs";
      import { Humanoide, REPERES_VISAGE } from "./web/avatar/humanoide.js";
      import { Animateur } from "./web/avatar/animation.js";
      import { CONTACTS, GESTES } from "./web/avatar/emotions.js";
      const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
      const B = { jaw: 0, pucker: 0, stretch: 0, press: 0 };
      const out = {};
      for (const nom of Object.keys(CONTACTS)) {
        for (const regard of ["public", "haut"]) {
          const h = new Humanoide(S), a = new Animateur(h, S);
          a.vivant = false; a.vitesse = 25; a.prendrePose("repos");
          await a.jouerGeste(nom, { tenir: true });
          a.regardMode = regard;
          let t = 0; for (let i = 0; i < 200; i++) { t += 0.02; a.maj(0.02, t, B); }
          h.racine.updateMatrixWorld(true);
          const spec = Object.values(CONTACTS[nom]).at(-1);
          const ecarts = Object.entries(spec).map(([k, [point, rep, dec]]) => {
            const s = k === "X" ? "d" : k, r = REPERES_VISAGE[rep];
            const l = h.visage.g.worldToLocal(h.pointMain(s, point));
            return Math.hypot(l.x - r[0] - dec[0], l.y - r[1] - dec[1], l.z - r[2] - dec[2]);
          });
          out[`${nom}/${regard}`] = Math.max(...ecarts);
        }
      }
      // témoin : sans la passe de contact, « réfléchir » laissait le poing sous le menton, vers le cou
      const h = new Humanoide(S), a = new Animateur(h, S); a.vivant = false; a.vitesse = 25; a.prendrePose("repos");
      await a.jouerGeste("reflechir", { tenir: true }); a.definirContacts(null);
      let t = 0; for (let i = 0; i < 200; i++) { t += 0.02; a.maj(0.02, t, B); }
      h.racine.updateMatrixWorld(true);
      const l = h.visage.g.worldToLocal(h.pointMain("d", "poing"));
      out.temoin_y = l.y;
      out.inconnus = Object.keys(CONTACTS).filter((n) => !GESTES[n]);
      console.log(JSON.stringify(out));
    """
    r = subprocess.run([NODE, "--import", crochet.as_uri(), "--input-type=module", "-e", script],
                       capture_output=True, text=True, timeout=120, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out.pop("inconnus") == []
    temoin = out.pop("temoin_y")
    assert temoin < -0.13                                  # sans correction : au niveau du cou (> 13 cm sous le centre de la tête)
    for cle, ecart in out.items():
        assert ecart < 0.02, (cle, ecart)                  # main posée sur le repère visé (± 2 cm), tête levée ou non


# ── Ce que voit le robot : caméra des yeux et caméra réelle (comme le drone et le chien) ──
def test_vue_du_robot_page_et_scene():
    html = (WEB / "avatar.html").read_text(encoding="utf-8")
    for ident in ("pip", "cam-virtuelle", "cam-reelle", "cam-surimp", "pip-taille", "pip-masquer", "pip-visible",
                  "suivre-regard", "zoom", "b-photo", "b-rec", "cam-liste", "b-capture", "whep-url", "b-whep", "b-cam-fermer"):
        assert f'id="{ident}"' in html, ident
    assert 'data-onglet="camera"' in html and 'id="ong-camera"' in html
    assert "jamais enregistré" in html                                   # garde-fou G-06 affiché
    scene = (WEB / "avatar" / "scene.js").read_text(encoding="utf-8")
    # même interface que les théâtres du drone et du chien, pour réutiliser web/drone/camera4k.js
    assert "rendreCamera(rendu)" in scene and "majCameraYeux()" in scene and "salleDansLeChamp()" in scene
    assert "h.layers.set(1)" in scene and "this.camera.layers.enable(1)" in scene   # halos d'édition hors de la vue du robot
    app = (WEB / "avatar" / "app.js").read_text(encoding="utf-8")
    assert 'from "../drone/camera4k.js"' in app and "vueRobot?.rendre()" in app
    # le flux réel n'est jamais enregistré : seule la caméra virtuelle a un enregistreur
    bloc = app[app.index("vueRobot = (() => {"):app.index("window.ROBOT_VIRTUEL.vue")]
    assert "MediaRecorder" not in bloc and "cam.demarrerEnregistrement" in bloc and "flux.demarrer" not in bloc


@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_habillages(tmp_path):
    """Habillages (21 oct. 2026) : chaque habillage n'emploie que des valeurs du schéma ; les directives
    d'habillage et d'accessoires sont comprises ; un habillage ne touche jamais le corps ; JS et Python valident pareil."""
    S = avatar.schema()
    A = S["apparence"]
    assert len(A["habillages"]) >= 12
    for k, h in A["habillages"].items():
        v = h["valeurs"]
        for cle in ("matiere", "chapeau", "cou", "cape", "jupe", "manches"):
            assert v[cle] in A[cle], (k, cle)
        for cle in ("haut", "bas", "chaussures", "couleur_chapeau", "accessoire"):
            assert v[cle] in A["couleurs"], (k, cle)
        assert not {"taille", "age", "peau", "cheveux", "barbe", "yeux"} & set(v)
    ok, rejets = avatar.valider([{"type": "apparence", "cle": "habillage", "valeur": "monarque"},
                                     {"type": "apparence", "cle": "chapeau", "valeur": "melon"},
                                     {"type": "apparence", "cle": "habillage", "valeur": "astronaute"},
                                     {"type": "apparence", "cle": "chapeau", "valeur": "sombrero"}])
    assert len(ok) == 2 and len(rejets) == 2
    out = node("""
      import { interpreter } from "./web/avatar/directives.js";
      import fs from "node:fs";
      const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
      const t = ["habille-toi en monarque", "mets ton habit de soirée", "déguise-toi en clown", "mets un chapeau melon noir",
                 "mets un haut-de-forme", "enlève ton chapeau", "mets une cape rouge", "enlève ta cape", "mets une cravate bordeaux",
                 "mets des gants blancs", "mets une robe longue rouge", "lève le bras en haut", "habille-toi en survêtement",
                 "habille-toi en danseur", "habille-toi en danseuse", "mets une cape violette", "chemise verte", "mets une cape blanche"];
      console.log(JSON.stringify(Object.fromEntries(t.map((x) => [x, interpreter(x, S).actions.filter((a) => a.type === "apparence").map((a) => [a.cle, a.valeur])]))));
    """)
    assert out["habille-toi en monarque"] == [["habillage", "monarque"]]
    assert out["mets ton habit de soirée"] == [["habillage", "soiree"]]
    assert out["déguise-toi en clown"] == [["habillage", "clown"]]
    assert out["mets un chapeau melon noir"] == [["chapeau", "melon"], ["couleur_chapeau", "noir"]]
    assert out["mets un haut-de-forme"] == [["chapeau", "haut-de-forme"]]      # pas lu comme le « haut » du costume
    assert out["enlève ton chapeau"] == [["chapeau", "aucun"]] and out["enlève ta cape"] == [["cape", "aucune"]]
    assert out["mets une cape rouge"] == [["cape", "longue"], ["accessoire", "rouge"]]
    assert out["mets une cravate bordeaux"] == [["cou", "cravate"], ["accessoire", "bordeaux"]]
    assert out["mets des gants blancs"] == [["gants", True], ["accessoire", "blanc"]]
    assert out["mets une robe longue rouge"] == [["jupe", "longue"], ["bas", "rouge"]]
    assert out["lève le bras en haut"] == [] and out["habille-toi en survêtement"] == [["habillage", "sport"]]
    # 24 oct. 2026 : l'habillage l'emporte sur le geste « danser » ; couleurs accordées au féminin
    assert out["habille-toi en danseur"] == [["habillage", "danseur"]] == out["habille-toi en danseuse"]
    assert out["mets une cape violette"] == [["cape", "longue"], ["accessoire", "violet"]]
    assert out["chemise verte"] == [["haut", "vert"]] and out["mets une cape blanche"][-1] == ["accessoire", "blanc"]
    # rendu : chaque habillage s'applique sans erreur et ne montre que ses accessoires
    crochet = tmp_path / "three.mjs"
    vendor = (WEB / "vendor" / "three.module.min.js").as_uri()
    crochet.write_text('import { register } from "node:module";\n'
                       'register("data:text/javascript," + encodeURIComponent('
                       f'`export async function resolve(s, c, n) {{ if (s === "three") return {{ url: "{vendor}", '
                       'shortCircuit: true }; return n(s, c); }`));\n', encoding="utf-8")
    script = """
      import fs from "node:fs";
      import { Humanoide } from "./web/avatar/humanoide.js";
      const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
      const H = new Humanoide(S); const avant = { ...H.apparence };
      const out = {};
      for (const [k, h] of Object.entries(S.apparence.habillages)) {
        H.appliquerApparence({ ...h.valeurs, habillage: k });
        out[k] = Object.entries(H.os.acc).filter(([, g]) => g.visible).map(([n]) => n).sort();
      }
      out.corps = ["taille", "age", "peau", "cheveux", "barbe"].every((c) => H.apparence[c] === avant[c]);
      console.log(JSON.stringify(out));
    """
    r = subprocess.run([NODE, "--import", crochet.as_uri(), "--input-type=module", "-e", script],
                       capture_output=True, text=True, timeout=60, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout)
    assert o["repetition"] == [] and o["monarque"] == ["cape_longue", "couronne"]
    assert o["soiree"] == ["haut-de-forme", "nœud papillon"] and o["robe_soiree"] == ["foulard", "jupe_longue"]
    assert o["corps"]
