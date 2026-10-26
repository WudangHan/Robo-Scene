"""Modèles de chaussures et de maillots de lutte du robot humain (25 oct. 2026).

Huit modèles de chaussures et sept de maillots, d'après les photographies fournies (couleurs et types de motifs
seulement : aucun logo, drapeau ni inscription) ; consignes vocales ; validation côté pont ; peinture du corps humain
(chaque modèle donne des couleurs distinctes, coupes du maillot) ; pied chaussé (orteils comblés) et maillage affiné."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from bridge.partenaire import avatar

RACINE = Path(__file__).resolve().parents[1]
WEB = RACINE / "web"
NODE = shutil.which("node")
S = json.loads((WEB / "avatar" / "schema.json").read_text(encoding="utf-8"))
CHAUSSURES = ["bleu_chevrons", "noir_orange", "noir_violet", "marine_blanc", "noir_argent_violet", "blanc_noir_lime", "blanc_or", "bleu_blanc_argent"]
MAILLOTS = ["bleu_chine", "rouge_chine", "rouge_graphique", "bleu_roi", "bleu_graphique", "blanc_rouge", "noir_flancs"]


def test_modeles_au_schema_et_validation():
    A = S["apparence"]
    assert list(A["modeles_chaussures"]) == ["uni", *CHAUSSURES] and list(A["modeles_maillot"]) == ["uni", *MAILLOTS]
    for m in CHAUSSURES:
        c = A["modeles_chaussures"][m]
        assert {"tige", "accent", "lacets", "semelle", "col"} <= set(c["couleurs"]) and 0.1 <= c["hauteur"] <= 0.17
    for m in MAILLOTS:
        assert {"corps", "liseres"} <= set(A["modeles_maillot"][m]["couleurs"])
    ok, rejets = avatar.valider([{"type": "apparence", "cle": "modele_maillot", "valeur": "blanc_rouge"},
                                 {"type": "apparence", "cle": "modele_chaussures", "valeur": "blanc_or"},
                                 {"type": "apparence", "cle": "modele_maillot", "valeur": "pailleté"},
                                 {"type": "apparence", "cle": "modele_chaussures", "valeur": "marque_x"}])
    assert len(ok) == 2 and len(rejets) == 2


def _node(tmp_path, script):
    crochet = tmp_path / "three.mjs"
    vendor = (WEB / "vendor" / "three.module.min.js").as_uri()
    crochet.write_text('import { register } from "node:module";\n'
                       'register("data:text/javascript," + encodeURIComponent('
                       f'`export async function resolve(s, c, n) {{ if (s === "three") return {{ url: "{vendor}", '
                       'shortCircuit: true }; return n(s, c); }`));\n', encoding="utf-8")
    r = subprocess.run([NODE, "--import", crochet.as_uri(), "--input-type=module", "-e", script],
                       capture_output=True, text=True, timeout=180, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_consignes_et_peinture(tmp_path):
    out = _node(tmp_path, """
      import fs from "node:fs";
      import { Humanoide } from "./web/avatar/humanoide.js";
      import { CorpsHumain } from "./web/avatar/humain.js";
      import { interpreter } from "./web/avatar/directives.js";
      const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
      const meta = JSON.parse(fs.readFileSync("./web/avatar/humain/corps.json", "utf8"));
      const buf = fs.readFileSync("./web/avatar/humain/corps.bin"); const bin = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
      const T = { float32: Float32Array, uint8: Uint8Array, uint32: Uint32Array };
      const t = Object.fromEntries(Object.entries(meta.tableaux).map(([n, d]) => [n, new T[d.type](bin, d.offset, d.forme.reduce((a, b) => a * b, 1))]));
      const h = new Humanoide(S); h.humain = new CorpsHumain(h, { meta, t });
      const H = h.humain, r = H.region, p = H.repos, c = H.couleurs;
      const moyenne = (test) => { const m = [0, 0, 0]; let n = 0; for (let i = 0; i < r.length; i++) if (test(i)) { for (let j = 0; j < 3; j++) m[j] += c[3 * i + j]; n++; } return m.map((x) => +(x / n).toFixed(3)); };
      h.appliquerApparence({ style: "humain", manches: "sans", coupe_bas: "cuissard" });
      const pieds = {}, maillots = {};
      for (const m of Object.keys(S.apparence.modeles_chaussures)) { h.appliquerApparence({ modele_chaussures: m }); pieds[m] = moyenne((i) => r[i] === 10); }
      for (const m of Object.keys(S.apparence.modeles_maillot)) { h.appliquerApparence({ modele_maillot: m }); maillots[m] = moyenne((i) => r[i] === 2 || r[i] === 3); }
      // coupes (sans GPU) : peau dans l'encolure, liseré autour, couture sous la poitrine du modèle blanc
      H.gpu = false; h.appliquerApparence({ modele_maillot: "blanc_rouge" });
      const P = meta.pivots, ys = (P.epaule_g[1] + P.epaule_d[1]) / 2, rouge = [0, 0, 0], peau = H.uniformes.uPeau.value;
      let liseres = 0, encolure = 0;
      for (let i = 0; i < r.length; i++) if (r[i] === 2) {
        const x = Math.abs(p[3 * i]), y = p[3 * i + 1], z = p[3 * i + 2];
        if (z > 0.05 && x < 0.03 && y > ys - 0.02) encolure += Math.abs(c[3 * i] - peau.r) < 1e-6 ? 1 : 0;
        if (Math.abs(c[3 * i] - H.uniformes.uLiser.value.r) < 1e-6 && Math.abs(c[3 * i + 1] - H.uniformes.uLiser.value.g) < 1e-6) liseres++;
      }
      const phrases = ["mets les chaussures blanches à lacets lime", "mets les chaussures à liserés dorés", "mets les chaussures bleues et blanches",
        "mets des chaussures vertes", "mets le maillot de lutte bleu chiné", "mets le maillot de lutte rouge à motifs", "mets le maillot de lutte bleu roi",
        "mets le maillot de lutte blanc à liserés rouges", "mets le maillot de lutte noir à flancs en maille", "mets un haut rouge et un pantalon noir"];
      console.log(JSON.stringify({ pieds, maillots, liseres, encolure, sommets: r.length, triangles: H.mesh.geometry.index.count / 3,
        phrases: Object.fromEntries(phrases.map((x) => [x, interpreter(x, S).actions.map((a) => [a.cle, a.valeur])])) }));
    """)
    distincts = lambda d: len({tuple(v) for v in d.values()}) == len(d)
    assert distincts(out["pieds"]) and distincts(out["maillots"])
    assert out["liseres"] > 50 and out["encolure"] > 0
    assert out["sommets"] > 60000 and out["triangles"] > 4 * 26756              # maillage affiné au chargement
    p = out["phrases"]
    assert ["modele_chaussures", "blanc_noir_lime"] in p["mets les chaussures blanches à lacets lime"]
    assert ["modele_chaussures", "blanc_or"] in p["mets les chaussures à liserés dorés"]
    assert ["modele_chaussures", "bleu_blanc_argent"] in p["mets les chaussures bleues et blanches"]
    assert p["mets des chaussures vertes"] == [["chaussures", "vert"], ["modele_chaussures", "uni"]]
    for phrase, m in (("bleu chiné", "bleu_chine"), ("rouge à motifs", "rouge_graphique"), ("bleu roi", "bleu_roi"),
                      ("blanc à liserés rouges", "blanc_rouge"), ("noir à flancs en maille", "noir_flancs")):
        assert p[f"mets le maillot de lutte {phrase}"] == [["manches", "sans"], ["coupe_bas", "cuissard"], ["modele_maillot", m]]
    assert p["mets un haut rouge et un pantalon noir"] == [["haut", "rouge"], ["bas", "noir"], ["coupe_bas", "pantalon"]]


def test_pied_chausse_orteils_combles():
    sys.path.insert(0, str(RACINE / "outils" / "humain"))
    from chaussure_pleine import combler_orteils
    meta = json.loads((WEB / "avatar" / "humain" / "corps.json").read_text(encoding="utf-8"))
    buf = (WEB / "avatar" / "humain" / "corps.bin").read_bytes()
    T = meta["tableaux"]
    vue = lambda n, dt: np.frombuffer(buf, dtype=dt, count=int(np.prod(T[n]["forme"])), offset=T[n]["offset"]).reshape(T[n]["forme"]).copy()
    P, N, R = vue("position", np.float32), vue("normale", np.float32), vue("region", np.uint8)
    P2, N2 = P.copy(), N.copy()
    combler_orteils(P2, N2, R, {c: meta["pivots"][f"cheville_{c}"] for c in "gd"})
    assert np.abs(P2 - P).max() < 2e-3                                          # déjà sur l'enveloppe : idempotent
    pied = P[(R == 10) & (P[:, 0] > 0)]
    assert pied[:, 1].min() > -0.01                                              # semelle au sol, pas dessous


@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_sangles_du_protege_oreilles_par_dessus_la_tete(tmp_path):
    """26 oct. 2026 : les sangles passent par-dessus le crâne, plaquées sur lui (stylisé et humain) ; la mentonnière
    passe sous le menton, jamais sous l'occiput."""
    out = _node(tmp_path, """
      import fs from "node:fs";
      import { Humanoide } from "./web/avatar/humanoide.js";
      import { CorpsHumain } from "./web/avatar/humain.js";
      const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
      const meta = JSON.parse(fs.readFileSync("./web/avatar/humain/corps.json", "utf8"));
      const buf = fs.readFileSync("./web/avatar/humain/corps.bin"); const bin = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
      const T = { float32: Float32Array, uint8: Uint8Array, uint32: Uint32Array };
      const t = Object.fromEntries(Object.entries(meta.tableaux).map(([n, d]) => [n, new T[d.type](bin, d.offset, d.forme.reduce((a, b) => a * b, 1))]));
      const h = new Humanoide(S); h.humain = new CorpsHumain(h, { meta, t });
      const mesure = () => h.sangles.map((m) => { const p = m.geometry.attributes.position; let ymax = -9, ymin = 9, zdos = 9, zbas = 0, ybas = 9;
        for (let i = 0; i < p.count; i++) { const y = p.getY(i), z = p.getZ(i); ymax = Math.max(ymax, y); if (y < ybas) { ybas = y; zbas = z; } if (z < -0.04) zdos = Math.min(zdos, y); }
        return { ymax: +ymax.toFixed(3), ybas: +ybas.toFixed(3), zbas: +zbas.toFixed(3), zdos: +zdos.toFixed(3), n: p.count }; });
      h.appliquerApparence({ habillage: "lutteur", chapeau: "protège-oreilles" }); const stylise = mesure();
      h.appliquerApparence({ style: "humain" }); const humain = mesure();
      console.log(JSON.stringify({ stylise, humain }));
    """)
    for cas in (out["stylise"], out["humain"]):
        avant, arriere, menton = cas
        assert avant["n"] > 50 and arriere["n"] > 50 and menton["n"] > 50
        assert avant["ymax"] > 0.08 and arriere["ymax"] > 0.06                  # par-dessus le crâne
        assert arriere["zdos"] > -0.01                                           # jamais sous l'occiput
        assert menton["ybas"] < -0.06 and menton["zbas"] > 0.02                  # sous le menton, à l'avant
