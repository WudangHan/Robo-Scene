"""Style « humain » du robot virtuel (25 oct. 2026) : corps MakeHuman (CC0) lié au squelette du robot.

Vérifie : les données construites (outils/humain/construire_humain.py) ; la licence ; l'habillage qui suit le
squelette (le bout du majeur du corps humain reste sur celui du robot, bras levé compris) ; le passage d'un style
à l'autre ; les tons de peau de l'échelle de Monk et les consignes « version humaine », « peau Monk 8 »."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
WEB = RACINE / "web"
NODE = shutil.which("node")
MONK = ["#f6ede4", "#f3e7db", "#f7ead0", "#eadaba", "#d7bd96", "#a07e56", "#825c43", "#604134", "#3a312a", "#292420"]


def test_donnees_du_corps_et_licences():
    meta = json.loads((WEB / "avatar" / "humain" / "corps.json").read_text(encoding="utf-8"))
    assert "CC0" in meta["source"]
    assert (WEB / "avatar" / "humain" / "corps.bin").stat().st_size == sum(
        0 for _ in ()) + max(d["offset"] + _taille(d) for d in meta["tableaux"].values()) + _pad(meta)
    assert len(meta["noeuds"]) == 52 and {"pouce0_g", "auriculaire2_d", "machoire", "paupiere_g"} <= set(meta["noeuds"])
    assert abs(meta["morphologie"]["hauteur_m"] - 1.785) < 1e-9
    lic = (WEB / "avatar" / "humain" / "LICENCE.md").read_text(encoding="utf-8")
    assert "CC0" in lic and "MakeHuman" in lic and "Monk" in lic and "CC BY 4.0" in lic
    S = json.loads((WEB / "avatar" / "schema.json").read_text(encoding="utf-8"))["apparence"]
    assert S["style"] == ["stylisé", "humain"]
    assert [f"Monk {i:02d}" for i in range(1, 11)] == [p for p in S["peau"] if p.startswith("Monk")]


def _taille(d):
    n = 1
    for x in d["forme"]:
        n *= x
    return n * {"float32": 4, "uint32": 4, "uint8": 1}[d["type"]]


def _pad(meta):
    fin = max(d["offset"] + _taille(d) for d in meta["tableaux"].values())
    return (-fin) % 4


@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_habillage_suit_le_squelette_et_changement_de_style(tmp_path):
    crochet = tmp_path / "three.mjs"
    vendor = (WEB / "vendor" / "three.module.min.js").as_uri()
    crochet.write_text('import { register } from "node:module";\n'
                       'register("data:text/javascript," + encodeURIComponent('
                       f'`export async function resolve(s, c, n) {{ if (s === "three") return {{ url: "{vendor}", '
                       'shortCircuit: true }; return n(s, c); }`));\n', encoding="utf-8")
    script = """
      import fs from "node:fs";
      import * as THREE from "three";
      import { Humanoide, PEAUX } from "./web/avatar/humanoide.js";
      import { CorpsHumain, TONS_MONK } from "./web/avatar/humain.js";
      import { interpreter } from "./web/avatar/directives.js";
      const S = JSON.parse(fs.readFileSync("./web/avatar/schema.json", "utf8"));
      const meta = JSON.parse(fs.readFileSync("./web/avatar/humain/corps.json", "utf8"));
      const buf = fs.readFileSync("./web/avatar/humain/corps.bin"); const bin = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
      const T = { float32: Float32Array, uint8: Uint8Array, uint32: Uint32Array };
      const t = Object.fromEntries(Object.entries(meta.tableaux).map(([n, d]) => [n, new T[d.type](bin, d.offset, d.forme.reduce((a, b) => a * b, 1))]));
      const h = new Humanoide(S); h.humain = new CorpsHumain(h, { meta, t });
      const vu = (o) => { for (let x = o; x; x = x.parent) if (!x.visible) return false; return true; };
      const visibles = () => { let n = 0; h.racine.traverse((o) => { if (o.isMesh && o.userData.zone && vu(o)) n++; }); return n; };
      const avant = visibles();
      h.appliquerApparence({ style: "humain" });
      const m = h.humain.mesh, pos = m.geometry.attributes.position, v = new THREE.Vector3();
      const tip = new THREE.Vector3(...meta.pivots.majeur3_g); let best = -1, bd = 9;
      for (let i = 0; i < pos.count; i++) { v.fromBufferAttribute(pos, i); const d = v.distanceTo(tip); if (d < bd) { bd = d; best = i; } }
      const ecart = (P) => { h.appliquer(P, { ancrage: false }); h.racine.updateMatrixWorld(true); m.skeleton.update();
        const p = m.getVertexPosition(best, new THREE.Vector3()).applyMatrix4(m.matrixWorld); return p.distanceTo(h.pointMain("g", "doigts")); };
      const r = { avant, humain: visibles(), repos: ecart({}), leve: ecart({ "epaule_g.flexion": 170, "coude_g.flexion": 30, "poignet_g.rotation": 60 }),
                  poing: ecart({ "main_g.fermeture": 100 }), cuisse: h.cuisse, cheveux: !!h.humain.cheveux };
      h.appliquerApparence({ style: "stylisé" });
      r.retour = visibles(); r.corpsVisible = m.visible;
      r.monk = TONS_MONK; r.peaux = Object.fromEntries(Object.entries(PEAUX).filter(([k]) => k.startsWith("Monk")));
      r.phrases = ["passe en version humaine", "peau monk 8", "redeviens stylisé", "deviens humain"].map((x) => interpreter(x, S).actions.map((a) => [a.cle, a.valeur]));
      console.log(JSON.stringify(r));
    """
    p = subprocess.run([NODE, "--import", crochet.as_uri(), "--input-type=module", "-e", script],
                       capture_output=True, text=True, timeout=120, cwd=RACINE)
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout.strip().splitlines()[-1])
    assert r["humain"] == 0 and r["avant"] > 20 and r["retour"] == r["avant"] and not r["corpsVisible"]
    assert r["repos"] < 0.02 and r["leve"] < 0.02 and r["poing"] < 0.02         # peau du majeur sur le majeur du robot
    assert 0.42 < r["cuisse"] < 0.44 and r["cheveux"]
    assert r["monk"] == MONK and list(r["peaux"].values()) == MONK
    assert r["phrases"] == [[["style", "humain"]], [["peau", "Monk 08"]], [["style", "stylisé"]], [["style", "humain"]]]
