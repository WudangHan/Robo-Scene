"""Commandes en langage naturel (voix ou texte) et flèches du clavier des pages Drone et Chien
(web/drone/commande.js) : grammaire française, repères nommés, conversions de repère, garde-fous.

python -m pytest -q tests/test_commandes.py — exige Node.js."""
import json
import math
import shutil
import subprocess

import pytest

from bridge.drone.zones import charger_salle
from bridge.serveur import RACINE

NODE = shutil.which("node")
SALLE = charger_salle()
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js absent")


def interpreter(phrases, robot):
    rep = SALLE["reperes"] if robot == "drone" else SALLE["sol"]["reperes"]
    js = f"""
import {{ interpreter }} from "./web/drone/commande.js";
const rep = {json.dumps(rep)};
console.log(JSON.stringify({json.dumps(phrases)}.map((p) => interpreter(p, "{robot}", rep))));
"""
    r = subprocess.run([NODE, "--input-type=module", "-e", js], capture_output=True, text=True, timeout=60, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def une(phrase, robot="drone"):
    r = interpreter([phrase], robot)[0]
    assert not r["inconnu"], (phrase, r)
    return r["actions"]


@pytest.mark.parametrize("phrase,attendu", [
    ("décolle", [{"type": "decoller", "hauteur": None}]),
    ("décolle à 2 mètres", [{"type": "decoller", "hauteur": 2}]),
    ("atterris", [{"type": "atterrir"}]),
    ("stop", [{"type": "arreter"}]),
    ("reste là", [{"type": "arreter"}]),
    ("arrêt d'urgence", [{"type": "urgence"}]),
    ("reviens à la base", [{"type": "retour"}]),
    ("va au centre", [{"type": "aller", "repere": "centre"}]),
    ("va au centre de la salle", [{"type": "aller", "repere": "salle_centre"}]),
    ("va à l'avant-scène", [{"type": "aller", "repere": "avant_scene"}]),
    ("regarde la salle", [{"type": "regarder", "cible": "salle"}]),
    ("demi-tour", [{"type": "tourner", "angle": 180}]),
    ("tourne à gauche", [{"type": "tourner", "angle": 90}]),
    ("tourne à droite de 45 degrés", [{"type": "tourner", "angle": -45}]),
    ("GO", [{"type": "go"}]),
])
def test_drone_commandes_simples(phrase, attendu):
    assert une(phrase) == attendu


def test_drone_distances_et_unites():
    assert une("avance de 2 mètres") == [{"type": "deplacer", "droite": 0, "avant": 2, "haut": 0}]
    assert une("recule de 50 centimètres") == [{"type": "deplacer", "droite": 0, "avant": -0.5, "haut": 0}]
    assert une("à gauche d'un mètre et demi") == [{"type": "deplacer", "droite": -1.5, "avant": 0, "haut": 0}]
    assert une("monte") == [{"type": "deplacer", "droite": 0, "avant": 0, "haut": 0.5}]   # altitude : 0,5 m par défaut
    assert une("descends d'un mètre")[0]["haut"] == -1


def test_enchainement_et_partie_inconnue():
    r = interpreter(["décolle puis va au centre", "va côté cour puis fais la roue"], "drone")
    assert r[0]["actions"] == [{"type": "decoller", "hauteur": None}, {"type": "aller", "repere": "centre"}]
    assert r[1]["actions"] == [{"type": "aller", "repere": "cour"}] and r[1]["inconnu"] == ["fais la roue"]
    assert interpreter(["chante une chanson"], "drone")[0]["actions"] == []


def test_chien_commandes():
    assert une("lève-toi", "chien") == [{"type": "lever"}]
    assert une("couché", "chien") == [{"type": "coucher"}]
    assert une("assis", "chien") == [{"type": "posture", "nom": "assis"}]
    assert une("donne la patte", "chien") == [{"type": "posture", "nom": "patte"}]
    assert une("joyeux", "chien") == [{"type": "allure", "nom": "joyeux"}]
    assert une("avance de 3 pas", "chien") == [{"type": "deplacer", "droite": 0, "avant": 0.9, "haut": 0}]
    assert une("va en haut de l'escalier cour", "chien") == [{"type": "aller", "repere": "haut_escalier_cour"}]
    assert une("reviens à ta place", "chien") == [{"type": "retour"}]
    # le chien ne vole pas : « monte » sans repère n'est pas une commande du chien
    assert interpreter(["monte"], "chien")[0]["actions"] == []
    # la voix ne commande jamais la coupure des moteurs
    for p in ("coupe les moteurs", "coupure"):
        assert all(a["type"] not in ("couper", "coupure") for a in interpreter([p], "chien")[0]["actions"] + interpreter([p], "drone")[0]["actions"])


def test_fleches_et_point_relatif():
    js = """
import { flechesVersManche, pointRelatif } from "./web/drone/commande.js";
const r = (v) => v.map((x) => Math.round(x * 1000) / 1000 + 0);
console.log(JSON.stringify({
  robot: r(flechesVersManche(true, false, true, false, "robot", 1.2)),
  scene_face_salle: [r(flechesVersManche(true, false, false, false, "scene", 0)), r(flechesVersManche(false, false, false, true, "scene", 0))],
  scene_face_lointain: [r(flechesVersManche(true, false, false, false, "scene", Math.PI)), r(flechesVersManche(false, false, false, true, "scene", Math.PI))],
  rien: r(flechesVersManche(false, false, false, false, "scene", 0.3)),
  avant_face_salle: r(pointRelatif([1, 2], 0, 0, 1)),
  gauche_face_salle: r(pointRelatif([1, 2], 0, -1, 0)),
  avant_face_cour: r(pointRelatif([0, 0], Math.PI / 2, 0, 2)),
}));
"""
    r = subprocess.run([NODE, "--input-type=module", "-e", js], capture_output=True, text=True, timeout=60, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["robot"] == [-1, 1]                                  # ↑ + ← : avant et gauche du robot, quel que soit le lacet
    # robot face à la salle (lacet 0) : ↑ (vers le lointain) = reculer ; → (vers cour, x+) = sa gauche
    assert d["scene_face_salle"] == [[0, -1], [-1, 0]]
    # robot face au lointain (lacet π) : ↑ = avancer ; → (cour) = sa droite
    assert d["scene_face_lointain"] == [[0, 1], [1, 0]]
    assert d["rien"] == [0, 0]
    assert d["avant_face_salle"] == [1, 3]                        # avancer face à la salle : z croît
    assert d["gauche_face_salle"] == [2, 2]                       # face à la salle, la gauche du robot est côté cour (x+)
    assert [round(x, 6) for x in d["avant_face_cour"]] == [2, 0]  # lacet π/2 : avant = x+ (cour)
    assert math.isfinite(sum(d["avant_face_cour"]))


def test_aide_vocale_entierement_comprise():
    js = """
import { AIDE_VOIX, interpreter } from "./web/drone/commande.js";
const fs = await import("node:fs");
const salle = JSON.parse(fs.readFileSync("./web/drone/salle.json", "utf8"));
const out = {};
for (const robot of ["drone", "chien"]) {
  const rep = robot === "drone" ? salle.reperes : salle.sol.reperes;
  out[robot] = AIDE_VOIX[robot].map((p) => [p, interpreter(p, robot, rep)]).filter(([, r]) => !r.actions.length || r.inconnu.length).map(([p]) => p);
}
console.log(JSON.stringify(out));
"""
    r = subprocess.run([NODE, "--input-type=module", "-e", js], capture_output=True, text=True, timeout=60, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {"drone": [], "chien": []}     # chaque exemple affiché dans la page est compris
