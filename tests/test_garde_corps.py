"""Mouvements des bras du robot virtuel (26 oct. 2026) : garde-corps, gestes harmonisés, aisselles.

1. Garde-corps (web/avatar/garde.js) : pendant les gestes programmés, y compris ceux à contact (main sur le cœur,
   salut militaire…), la main et l'avant-bras n'entrent pas dans le corps (tête, cou, tronc, bassin, cuisses),
   pour le robot stylisé comme pour le corps humain.
2. Bras levés : l'abduction s'applique après la flexion (ordre ZXY) ; « bras au ciel » forme un V, le poing
   levé reste à l'extérieur de la tête, et l'élévation de l'omoplate ne fait plus pencher le bras vers la tête.
3. Aisselles du corps humain : bras levé à 170°, le sternum ne suit plus le bras (poids adoucis, os à mi-rotation)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
WEB = RACINE / "web"
NODE = shutil.which("node")
GESTES = ["croiser_bras", "montre", "se_designer", "mains_dos", "bercer", "main_coeur", "salut_militaire", "gratter_tete",
          "reflechir", "bras_au_ciel", "poing_leve", "mains_jointes"]

ENTETE = """
  import fs from "node:fs"; import * as THREE from "three";
  import { Humanoide } from "./web/avatar/humanoide.js"; import { CorpsHumain } from "./web/avatar/humain.js";
  import { Animateur } from "./web/avatar/animation.js"; import { GESTES, CONTACTS } from "./web/avatar/emotions.js";
  import { GardeCorps } from "./web/avatar/garde.js";
  const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
  const meta = JSON.parse(fs.readFileSync("./web/avatar/humain/corps.json", "utf8"));
  const buf = fs.readFileSync("./web/avatar/humain/corps.bin"); const bin = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
  const T = { float32: Float32Array, uint8: Uint8Array, uint32: Uint32Array };
  const t = Object.fromEntries(Object.entries(meta.tableaux).map(([n, d]) => [n, new T[d.type](bin, d.offset, d.forme.reduce((a, b) => a * b, 1))]));
  const B = { jaw: 0, pucker: 0, stretch: 0, press: 0 };
"""


def _node(tmp_path, script):
    crochet = tmp_path / "three.mjs"
    vendor = (WEB / "vendor" / "three.module.min.js").as_uri()
    crochet.write_text('import { register } from "node:module";\n'
                       'register("data:text/javascript," + encodeURIComponent('
                       f'`export async function resolve(s, c, n) {{ if (s === "three") return {{ url: "{vendor}", '
                       'shortCircuit: true }; return n(s, c); }`));\n', encoding="utf-8")
    r = subprocess.run([NODE, "--import", crochet.as_uri(), "--input-type=module", "-e", ENTETE + script],
                       capture_output=True, text=True, timeout=300, cwd=RACINE)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(not NODE, reason="Node.js absent")
@pytest.mark.parametrize("style", ["stylisé", "humain"])
def test_la_main_n_entre_pas_dans_le_corps(tmp_path, style):
    out = _node(tmp_path, """
      const h = new Humanoide(S); h.humain = new CorpsHumain(h, { meta, t }); h.appliquerApparence({ style: "%s" });
      const a = new Animateur(h, S); a.vivant = false; const g = new GardeCorps(h);
      let tps = 0; const pas = (n) => { for (let i = 0; i < n; i++) { tps += 0.02; a.maj(0.02, tps, B); } };
      a.prendrePose("repos"); pas(40); g.construire("test");
      const res = {};
      for (const nom of %s) {
        a.prendrePose("repos"); a.definirContacts(null); pas(60);
        const images = GESTES[nom](1, "devant"), contacts = CONTACTS[nom] || {}; let pire = 0, tp = 0;
        const suivre = (d) => { for (let i = 0; i < Math.max(1, Math.round(d / 0.02)); i++) { pas(1); const m = g.mesurer(); pire = Math.max(pire, m.g.profondeur, m.d.profondeur); } };
        for (const [i, im] of images.entries()) {
          suivre(im.t - tp); tp = im.t; if (im.fin) { a.definirContacts(null); a.prendrePose("repos"); continue; }
          for (const [c, v] of Object.entries(im.p || {})) { const n = c.replace("_X", "_d").replace("_Y", "_g"); if (n.startsWith("pointe_")) continue; if (n in a.base) { a.base[n] = v; a.vitesseDof[n] = 1.4; } }
          if (i in contacts) a.definirContacts(contacts[i], "d");
        }
        suivre(0.6); res[nom] = +(pire * 100).toFixed(1);
      }
      console.log(JSON.stringify(res));
    """ % (style, json.dumps(GESTES)))
    trop = {k: v for k, v in out.items() if v > 1.5}
    assert not trop, f"main ou avant-bras dans le corps (cm) : {trop}"


@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_bras_leves_et_aisselles(tmp_path):
    out = _node(tmp_path, """
      const h = new Humanoide(S); h.humain = new CorpsHumain(h, { meta, t }); h.appliquerApparence({ style: "humain" });
      const O = h.os, V = (o) => o.getWorldPosition(new THREE.Vector3());
      const dir = (P, s = "g") => { h.appliquer(P, { ancrage: false, evitement: false }); h.racine.updateMatrixWorld(true); return V(O[`coude_${s}`]).sub(V(O[`epaule_${s}`])).normalize(); };
      const ciel = GESTES.bras_au_ciel(1)[0].p, poing = GESTES.poing_leve(1)[0].p;
      const P2 = {}; for (const [k, v] of Object.entries(poing)) P2[k.replace("_X", "_d")] = v;
      const r = { leve: dir({ "epaule_g.flexion": 170 }).toArray(), ciel_g: dir(ciel, "g").toArray(), ciel_d: dir(ciel, "d").toArray(), poing_d: dir(P2, "d").toArray() };
      // aisselle : déplacement des sommets du sternum (|x| < 6 cm, tronc) quand les deux bras montent à 170°
      const m = h.humain.mesh, reg = h.humain.region, pos = (P) => { h.appliquer(P, { ancrage: false, evitement: false }); h.racine.updateMatrixWorld(true); m.skeleton.update();
        const out = [], v = new THREE.Vector3(); for (let i = 0; i < h.humain.nOriginal; i++) if (reg[i] === 2 && Math.abs(h.humain.repos[3 * i]) < 0.06) { m.getVertexPosition(i, v); out.push(v.clone()); } return out; };
      const a = pos({}), b = pos({ "epaule_g.flexion": 170, "epaule_d.flexion": 170 });
      r.sternum = Math.max(...a.map((p, i) => p.distanceTo(b[i])));
      console.log(JSON.stringify(r));
    """)
    assert out["leve"][0] > 0.05 and out["leve"][1] > 0.9          # bras levé : vers le haut, légèrement en dehors
    assert out["ciel_g"][0] > 0.3 and out["ciel_d"][0] < -0.3        # bras au ciel : un V, pas de bras croisés
    assert out["ciel_g"][1] > 0.75
    assert out["poing_d"][0] < -0.05 and out["poing_d"][1] > 0.9     # poing levé : à l'extérieur de la tête
    assert out["sternum"] < 0.02                                     # le sternum ne suit plus le bras
