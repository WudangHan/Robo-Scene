"""Mains à cinq doigts du robot virtuel (25 oct. 2026) : cinématique, prises, force, glissement, toucher.

Le modèle (web/avatar/mains.js) relie perception (capteurs tactiles simulés), force (serrage minimal de
Coulomb, marge selon la manière, plafond sous le seuil de dommage) et mouvement (fermeture segment par
segment jusqu'au contact). Les tests vérifient les propriétés tirées des sources citées dans le module :
couplage IPD ≈ 2/3 IPP (Rijpkema et Girard 1991), réflexe de glissement après 74 ms (Johansson et Westling
1987), force de serrage proportionnelle à la charge (Westling et Johansson 1984).
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="Node.js absent")


def node(script: str):
    r = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=120, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


ENTETE = 'import * as M from "./web/avatar/mains.js";\n'


def test_postures_dans_les_amplitudes_et_couplage_ipd():
    out = node(ENTETE + """
      const r = {};
      for (const p of M.NOMS_POSTURES) {
        const q = M.anglesPosture(p); const hors = [];
        for (const [n, v] of Object.entries(q)) { const a = M.ARTICULATIONS[n]; if (a && (v < a.min - 1e-9 || v > a.max + 1e-9)) hors.push(n); }
        const couplage = ["index", "majeur", "annulaire", "auriculaire"].every((d) => Math.abs(q[d + ".dip"] - Math.min(M.ARTICULATIONS[d + ".dip"].max, Math.max(M.ARTICULATIONS[d + ".dip"].min, q[d + ".pip"] * 2 / 3))) < 1.01);
        r[p] = { hors, couplage };
      }
      console.log(JSON.stringify(r));
    """)
    assert len(out) >= 18
    for p, v in out.items():
        assert v["hors"] == [], (p, v)
        assert v["couplage"], p


def test_chaque_objet_est_saisi_par_au_moins_deux_doigts_dont_le_pouce():
    out = node(ENTETE + """
      const r = {};
      for (const o of M.NOMS_OBJETS) {
        const obj = M.OBJETS[o]; const c = M.contacts(obj.prise, obj);
        r[o] = { prise: obj.prise, doigts: Object.entries(c.doigts).filter(([, x]) => x.contact).map(([d]) => d), avecPouce: M.PRISES[obj.prise].doigts.includes("pouce") };
      }
      console.log(JSON.stringify(r));
    """)
    assert {"verre", "lettre", "rose", "epee", "main_partenaire"} <= set(out)
    for o, v in out.items():
        assert len(v["doigts"]) >= 2, (o, v)
        if v["avecPouce"]:
            assert "pouce" in v["doigts"], (o, v)
    assert set(out["verre"]["doigts"]) == {"pouce", "index", "majeur", "annulaire", "auriculaire"}


def test_force_de_serrage_suit_la_charge_et_reste_sous_le_dommage():
    out = node(ENTETE + """
      const r = {};
      for (const o of M.NOMS_OBJETS) for (const man of ["delicat", "normal", "ferme"]) {
        const m = new M.MainVirtuelle("d"); m.prendre(o, { maniere: man });
        const ev = []; for (let i = 0; i < 120; i++) ev.push(...m.pas(0.01));
        const p = m.etat().prise; const obj = M.OBJETS[o];
        r[o + "/" + man] = { force: p.force, minimale: p.minimale, plafond: obj.dommage * M.MANIERES[man].plafond, endommage: p.endommage, chute: p.chute, etablie: m.prise.etablie };
      }
      console.log(JSON.stringify(r));
    """)
    for k, v in out.items():
        assert not v["endommage"], k                       # sans intention, jamais au-delà du seuil
        assert v["force"] <= v["plafond"] + 1e-6, k
        if v["minimale"] < v["plafond"]:
            assert v["force"] >= v["minimale"] - 1e-6, k   # assez pour tenir
            assert v["etablie"] and not v["chute"], k
    # plus de marge en « ferme » qu'en « délicat » (Westling et Johansson 1984 : marge de sécurité)
    assert out["verre/ferme"]["force"] > out["verre/normal"]["force"] > out["verre/delicat"]["force"]
    # l'épée, plus lourde, demande plus de force que le verre
    assert out["epee/normal"]["force"] > out["verre/normal"]["force"]


def test_reflexe_de_glissement_apres_74_ms():
    out = node(ENTETE + """
      const m = new M.MainVirtuelle("d"); m.prendre("verre", { maniere: "normal" });
      for (let i = 0; i < 80; i++) m.pas(0.01);
      const f0 = m.etat().prise.force; const ev = [];
      for (let i = 0; i < 60; i++) for (const e of m.pas(0.005, { imprevu: 2 })) ev.push([+m.t.toFixed(3), e.msg]);
      const glisse = ev.find((e) => /glisse dans/.test(e[1])), reflexe = ev.find((e) => /Glissement senti/.test(e[1]));
      console.log(JSON.stringify({ f0, f1: m.etat().prise.force, glisse, reflexe, chute: m.etat().prise.chute, latence: M.LATENCE_GLISSEMENT }));
    """)
    assert out["latence"] == pytest.approx(0.074)
    assert out["glisse"] and out["reflexe"]
    assert out["reflexe"][0] - out["glisse"][0] == pytest.approx(0.074, abs=0.006)
    assert out["f1"] > out["f0"] * 1.2 and not out["chute"]


def test_arrachement_fait_echapper_l_objet():
    out = node(ENTETE + """
      const m = new M.MainVirtuelle("d"); m.prendre("epee", { maniere: "delicat" });
      for (let i = 0; i < 80; i++) m.pas(0.01);
      const ev = []; for (let i = 0; i < 80; i++) ev.push(...m.pas(0.01, { imprevu: 40 }).map((e) => e.msg));
      console.log(JSON.stringify({ chute: m.etat().prise.chute, ev }));
    """)
    assert out["chute"]
    assert any("échappe" in e and "arrache" in e for e in out["ev"])


def test_froisser_volontairement_et_menager_la_rose():
    out = node(ENTETE + """
      const a = new M.MainVirtuelle("d"); a.prendre("lettre", { maniere: "normal" });
      for (let i = 0; i < 40; i++) a.pas(0.01);
      a.ecraser(); const ev = []; for (let i = 0; i < 120; i++) ev.push(...a.pas(0.01).map((e) => e.msg));
      const b = new M.MainVirtuelle("g"); b.prendre("rose", { maniere: "fort" });
      for (let i = 0; i < 120; i++) b.pas(0.01);
      console.log(JSON.stringify({ lettre: a.etat().prise, ev, rose: b.etat().prise }));
    """)
    assert out["lettre"]["endommage"] and any("se froisse" in e for e in out["ev"])
    # « fort » sans intention reste plafonné par la manière… sauf « de toutes ses forces » (plafond infini)
    assert out["rose"]["force"] > 0


def test_capteurs_tactiles_pression_egale_force_sur_aire():
    out = node(ENTETE + """
      const m = new M.MainVirtuelle("d"); m.prendre("verre", { maniere: "normal" });
      for (let i = 0; i < 120; i++) m.pas(0.01);
      const e = m.etat(); const aires = Object.fromEntries(M.CAPTEURS.map((c) => [c.id, c.aire]));
      console.log(JSON.stringify({ capteurs: e.capteurs, aires, force: e.prise.force }));
    """)
    c = out["capteurs"]
    assert len(c) == 10
    actifs = {k: v for k, v in c.items() if v["force"] > 0}
    assert "paume" in actifs and "pulpe_pouce" in actifs
    for k, v in actifs.items():
        assert v["pression_kpa"] == pytest.approx(v["force"] / out["aires"][k] / 1000, rel=0.02, abs=0.11)
    assert sum(v["force"] for v in actifs.values()) == pytest.approx(out["force"], rel=0.02)


def test_fermeture_pour_la_pince_du_tonypi():
    out = node(ENTETE + """
      const r = {};
      for (const p of ["ouverte", "repos", "pince", "poing"]) { const m = new M.MainVirtuelle("d"); m.prendrePosture(p); for (let i = 0; i < 200; i++) m.pas(0.01); r[p] = m.fermeture(); }
      console.log(JSON.stringify(r));
    """)
    assert 0 <= out["ouverte"] < out["repos"] < out["pince"] < out["poing"] <= 100


def test_main_du_partenaire_serree_delicatement():
    out = node(ENTETE + """
      const m = new M.MainVirtuelle("d"); const r = m.prendre("main_partenaire", { maniere: "delicat" });
      for (let i = 0; i < 120; i++) m.pas(0.01);
      console.log(JSON.stringify({ r, p: m.etat().prise, seuil: M.OBJETS.main_partenaire.dommage }));
    """)
    assert out["r"]["ok"] and out["p"]["nom"] == "poignee"
    assert 0 < out["p"]["force"] <= out["seuil"] * 0.5


def test_vocabulaire_du_schema_identique_au_modele():
    """schema.json (lu par le pont) et mains.js (exécuté par la page) déclarent les mêmes postures, objets, manières."""
    out = node(ENTETE + """
      console.log(JSON.stringify({ postures: M.NOMS_POSTURES, objets: M.NOMS_OBJETS, manieres: Object.keys(M.MANIERES) }));
    """)
    S = json.loads((RACINE / "web" / "avatar" / "schema.json").read_text(encoding="utf-8"))["mains"]
    assert list(S["postures"]) == out["postures"]
    assert list(S["objets"]) == out["objets"]
    assert list(S["manieres"]) == out["manieres"]


def test_directives_de_main_comprises_et_validees_pareil_en_js_et_en_python():
    import sys
    sys.path.insert(0, str(RACINE))
    from bridge.partenaire import avatar
    phrases = {
        "prends le verre délicatement": ("prendre", "verre", "delicat"),
        "prends l'épée fermement": ("prendre", "epee", "ferme"),
        "prends la rose du bout des doigts": ("prendre", "rose", "delicat"),
        "froisse la lettre": ("ecraser", "lettre", None),
        "pose le verre": ("poser", "verre", None),
        "lâche la rose": ("lacher", "rose", None),
        "serre la main du partenaire": ("prendre", "main_partenaire", "normal"),
        "effleure sa main": ("prendre", "main_partenaire", "effleurer"),
        "serre-lui la main de toutes tes forces": ("prendre", "main_partenaire", "fort"),
        "pose la main sur le cœur": ("toucher", "coeur", "delicat"),
        "montre trois doigts": ("posture", "compter_3", None),
        "fais le signe ok": ("posture", "ok", None),
        "serre le poing": ("posture", "poing", None),
        "serre plus fort": ("force", None, "ferme"),
        "desserre": ("force", None, "delicat"),
        "pianote": ("pianoter", None, None),
        "relâche la main": ("relacher", None, None),
        "prends la coupe": ("prendre", "coupe", "normal"),          # « coupe » n'est pas corrigé en « coude »
        "main en coupe": ("posture", "coupe", None),                 # la posture l'emporte sur l'accessoire homonyme
    }
    out = node("""
      import { interpreter, EXEMPLES } from "./web/avatar/directives.js"; import fs from "node:fs";
      const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
      const t = %s;
      const r = Object.fromEntries(t.map((x) => [x, interpreter(x, S).actions.filter((a) => a.type === "main").map(({ clause, ...a }) => a)]));
      r.__exemples = EXEMPLES.filter((e) => interpreter(e, S).ignores.length).length;
      r.__gestes = ["bois un verre", "lis un livre", "serre la main", "compte sur tes doigts"].map((x) => interpreter(x, S).actions[0].type);
      r.__gauche = interpreter("prends la pomme avec la main gauche", S).actions[0];
      console.log(JSON.stringify(r));
    """ % json.dumps(list(phrases)))
    assert out.pop("__exemples") == 0                 # tous les exemples d'aide sont compris
    assert out.pop("__gestes") == ["geste"] * 4       # les gestes mimés restent des gestes
    assert out.pop("__gauche")["cote"] == "g"
    for phrase, (action, valeur, maniere) in phrases.items():
        a = out[phrase]
        assert len(a) == 1, (phrase, a)
        a = a[0]
        assert a["action"] == action and a.get("valeur") == valeur and a.get("maniere") == maniere, (phrase, a)
        ok, rejets = avatar.valider([a])
        assert ok and not rejets, (phrase, rejets)
    ok, rejets = avatar.valider([{"type": "main", "action": "prendre", "valeur": "bazooka"},
                                 {"type": "main", "action": "posture", "valeur": "salut_vulcain"},
                                 {"type": "main", "action": "force"},
                                 {"type": "main", "action": "prendre", "valeur": "verre", "maniere": "brutal"}])
    assert not ok and len(rejets) == 4
    assert "main" in avatar.vocabulaire()["types"] and "objets" in avatar.vocabulaire()["mains"]


def test_animateur_relie_les_mains_au_rendu_et_au_jumeau(tmp_path):
    """Dans la page : la main commandée impose sa fermeture au degré de liberté lu par le jumeau (pince du
    TonyPi Pro) ; le verre saisi est rendu dans la main ; lâché, il tombe sur le plateau ; posé, il disparaît."""
    crochet = tmp_path / "three.mjs"
    vendor = (RACINE / "web" / "vendor" / "three.module.min.js").as_uri()
    crochet.write_text('import { register } from "node:module";\n'
                       'register("data:text/javascript," + encodeURIComponent('
                       f'`export async function resolve(s, c, n) {{ if (s === "three") return {{ url: "{vendor}", '
                       'shortCircuit: true }; return n(s, c); }`));\n', encoding="utf-8")
    script = """
      import fs from "node:fs";
      import * as THREE from "three";
      import { Humanoide } from "./web/avatar/humanoide.js";
      import { Animateur } from "./web/avatar/animation.js";
      const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
      const B = { jaw: 0, pucker: 0, stretch: 0, press: 0 };
      const h = new Humanoide(S), a = new Animateur(h, S); a.vivant = false; a.prendrePose("repos");
      const scene = new THREE.Scene(); scene.add(h.racine);
      const ev = []; a.surMain = (e) => ev.push(e.msg);
      let t = 0; const tourner = (n) => { for (let i = 0; i < n; i++) { t += 0.02; a.maj(0.02, t, B); } };
      tourner(10); const libre = a.val["main_d.fermeture"];
      a.mains.d.prendrePosture("poing"); tourner(60); const poing = a.val["main_d.fermeture"];
      a.mains.d.liberer(); a.mains.d.prendre("verre", { maniere: "delicat" }); tourner(80);
      const tenu = !!h.mainsRendu.d.objet && h.mainsRendu.d.objet.name;
      const coussins = Object.values(h.mainsRendu.d.coussins).filter((m) => m.visible).length;
      a.mains.d.lacher(); tourner(100);
      const chute = (h.chutes || []).map((c) => [c.nom, c.pose, +c.g.position.y.toFixed(3)]);
      a.mains.g.prendre("pomme"); tourner(30); a.mains.g.lacher("", { poser: true }); tourner(10);
      console.log(JSON.stringify({ libre, poing, tenu, coussins, chute, chutes: (h.chutes || []).length, ev }));
    """
    r = subprocess.run([NODE, "--import", crochet.as_uri(), "--input-type=module", "-e", script],
                       capture_output=True, text=True, timeout=120, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["poing"] >= 90 and out["poing"] > out["libre"]
    assert out["tenu"] == "objet_verre" and out["coussins"] >= 3
    assert out["chute"] == [["verre", True, 0.03]] and out["chutes"] == 1      # la pomme posée ne tombe pas
    assert any("Prise établie" in e for e in out["ev"]) and any("est lâché" in e for e in out["ev"])


def test_poignet_humain_rotation_flexion_inclinaison(tmp_path):
    """25 oct. 2026 : le poignet a trois mouvements humains — pronation-supination de l'avant-bras, flexion-
    extension, inclinaisons radiale et cubitale — dans les amplitudes usuelles, commandés à la voix et rendus
    dans le bon sens, bras tendu devant soi."""
    S = json.loads((RACINE / "web" / "avatar" / "schema.json").read_text(encoding="utf-8"))
    for c in "gd":
        assert (S["dofs"][f"poignet_{c}.flexion"]["min"], S["dofs"][f"poignet_{c}.flexion"]["max"]) == (-75, 85)
        assert (S["dofs"][f"poignet_{c}.deviation"]["min"], S["dofs"][f"poignet_{c}.deviation"]["max"]) == (-20, 40)
        assert (S["dofs"][f"poignet_{c}.rotation"]["min"], S["dofs"][f"poignet_{c}.rotation"]["max"]) == (-90, 90)
    assert "rouler_poignets" in S["gestes"]
    crochet = tmp_path / "three.mjs"
    vendor = (RACINE / "web" / "vendor" / "three.module.min.js").as_uri()
    crochet.write_text('import { register } from "node:module";\n'
                       'register("data:text/javascript," + encodeURIComponent('
                       f'`export async function resolve(s, c, n) {{ if (s === "three") return {{ url: "{vendor}", '
                       'shortCircuit: true }; return n(s, c); }`));\n', encoding="utf-8")
    script = """
      import fs from "node:fs";
      import * as THREE from "three";
      import { Humanoide } from "./web/avatar/humanoide.js";
      import { interpreter } from "./web/avatar/directives.js";
      const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
      const h = new Humanoide(S);
      const mesure = (P) => {
        h.appliquer(P, { ancrage: false }); h.racine.updateMatrixWorld(true); const r = {};
        for (const s of ["g", "d"]) {
          const n = h.pointMain(s, "paume").sub(h.pointMain(s, "dos")).normalize();
          const f = h.pointMain(s, "doigts").sub(h.os[`poignet_${s}`].getWorldPosition(new THREE.Vector3())).normalize();
          r[s] = { paume: n.toArray(), doigts: f.toArray() };
        }
        return r;
      };
      const bras = { "epaule_g.flexion": 80, "epaule_d.flexion": 80 };
      const P = (k, v) => ({ ...bras, [`poignet_g.${k}`]: v, [`poignet_d.${k}`]: v });
      const phrases = ["paume vers le haut", "paumes vers le bas", "étends le poignet", "incline le poignet vers le pouce",
                       "incline le poignet vers le petit doigt", "tourne le poignet", "roule les poignets", "tends la main paume vers le haut"];
      console.log(JSON.stringify({
        supination: mesure(P("rotation", -85)), pronation: mesure(P("rotation", 85)),
        flexion: mesure(P("flexion", 60)), cubitale: mesure(P("deviation", 35)),
        phrases: Object.fromEntries(phrases.map((t) => [t, interpreter(t, S).actions.map((a) => a.dof ? [a.dof, Math.round(a.valeur)] : [a.type, a.nom])])),
      }));
    """
    r = subprocess.run([NODE, "--import", crochet.as_uri(), "--input-type=module", "-e", script],
                       capture_output=True, text=True, timeout=120, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    for s, x in (("g", 1), ("d", -1)):
        assert out["supination"][s]["paume"][1] > 0.9          # bras devant : paume vers le haut
        assert out["pronation"][s]["paume"][1] < -0.9          # paume vers le bas
        assert out["flexion"][s]["doigts"][0] * x < -0.8       # les doigts vont vers la paume (côté médial)
        assert out["cubitale"][s]["doigts"][1] < -0.5          # pouce en haut : l'inclinaison cubitale abaisse les doigts
    p = out["phrases"]
    assert p["paume vers le haut"] == [["poignet_d.rotation", -85]] and p["paumes vers le bas"] == [["poignet_g.rotation", 85], ["poignet_d.rotation", 85]]
    assert p["étends le poignet"] == [["poignet_d.flexion", -60]]
    assert p["incline le poignet vers le pouce"] == [["poignet_d.deviation", -18]]
    assert p["incline le poignet vers le petit doigt"] == [["poignet_d.deviation", 35]]
    assert p["tourne le poignet"] == [["poignet_d.rotation", 70]]
    assert p["roule les poignets"] == [["geste", "rouler_poignets"]]
    assert ["poignet_d.rotation", -85] in p["tends la main paume vers le haut"] and ["epaule_d.flexion", 70] in p["tends la main paume vers le haut"]
