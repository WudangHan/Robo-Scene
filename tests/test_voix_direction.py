"""Tests des six voix de la direction d'exercices (page Partenaire, onglet Formation) :
python -m pytest -q tests/test_voix_direction.py — les tests du module JavaScript s'exécutent avec Node.js
s'il est installé ; sinon ils sont ignorés."""
import json
import shutil
import subprocess

import pytest

from bridge.serveur import RACINE

WEB = RACINE / "web"
NODE = shutil.which("node")
avec_node = pytest.mark.skipif(not NODE, reason="Node.js absent")

# Voix telles que les navigateurs les exposent (noms représentatifs de macOS, Chrome et Edge).
VOIX = [
    {"name": "Amélie", "lang": "fr-CA", "localService": True},
    {"name": "Nicolas", "lang": "fr-CA", "localService": True},
    {"name": "Thomas", "lang": "fr-FR", "localService": True},
    {"name": "Audrey (Premium)", "lang": "fr-FR", "localService": True},
    {"name": "Eddy (Français (Canada))", "lang": "fr-CA", "localService": True},
    {"name": "Microsoft Sylvie Online (Natural) - French (Canada)", "lang": "fr-CA", "localService": False},
    {"name": "Microsoft Antoine Online (Natural) - French (Canada)", "lang": "fr-CA", "localService": False},
    {"name": "Google français", "lang": "fr-FR", "localService": False},
    {"name": "Samantha", "lang": "en-US", "localService": True},
]


def js(corps: str):
    script = f"""
      import "./web/voix-direction.js";
      const V = globalThis.VoixDirection;
      const VOIX = {json.dumps(VOIX)};
      {corps}
    """
    r = subprocess.run([NODE, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@avec_node
def test_six_profils_complets():
    out = js("console.log(JSON.stringify(V.PROFILS));")
    assert len(out) == 6 and len({p["id"] for p in out}) == 6
    assert {p["genre"] for p in out} == {"f", "m"}
    for p in out:
        assert 0.75 <= p["debit"] <= 1.15 and 0.9 <= p["hauteur"] <= 1.08
        assert p["nom"] and p["role"] and p["description"]
        assert all(p["pauses"][k] > 0 for k in ("phrase", "question", "souffle", "fin"))


@avec_node
def test_attribution_naturelle_distincte_et_genree():
    out = js("""
      const a = V.attribuer(VOIX);
      console.log(JSON.stringify(Object.fromEntries(Object.entries(a).map(([k, v]) => [k, v && v.name]))));""")
    noms = list(out.values())
    assert all(noms)
    assert not any("Eddy" in n or n == "Samantha" for n in noms)      # ni voix ancienne ni voix étrangère
    assert len(set(noms)) == 6                                        # six voix distinctes quand il y en a assez
    assert "Natural" in out["mathilde"] and "Sylvie" in out["mathilde"]  # la voix la plus naturelle, fr-CA, féminine
    assert "Antoine" in out["etienne"]
    feminines = {"mathilde", "sophie", "claire"}
    for pid in feminines:
        assert not any(m in out[pid] for m in ("Antoine", "Nicolas", "Thomas")), (pid, out[pid])


@avec_node
def test_voix_locales_et_voix_imposee():
    out = js("""
      const loc = V.attribuer(VOIX, { localesSeulement: true });
      const imp = V.attribuer(VOIX, { imposees: { gabriel: "Thomas" } });
      const absente = V.attribuer(VOIX, { imposees: { gabriel: "Voix inexistante" } });
      console.log(JSON.stringify({ loc: Object.values(loc).map((v) => v.localService), imp: imp.gabriel.name, abs: absente.gabriel.name }));""")
    assert all(out["loc"])
    assert out["imp"] == "Thomas"
    assert out["abs"] != "Voix inexistante"


@avec_node
def test_aucune_voix_francaise():
    out = js("""console.log(JSON.stringify(Object.values(V.attribuer([{ name: "Samantha", lang: "en-US" }]))));""")
    assert out == [None] * 6


@avec_node
def test_rendu_humanise_borne_et_deterministe():
    texte = "Debout, en cercle (env. 2 min). Inspirez par le nez, p. ex. sur 4 temps. Êtes-vous prêts ? Marchez."
    out = js(f"""
      const t = {json.dumps(texte)};
      console.log(JSON.stringify({{ a: V.rendre(t, "gabriel"), b: V.rendre(t, "gabriel"), s: V.rendre(t, "sophie"),
                                   plat: V.rendre(t, "claire", {{ humaniser: false }}) }}));""")
    a, b, s, plat = out["a"], out["b"], out["s"], out["plat"]
    assert a == b                                               # même texte, même profil : même rendu
    assert [x["texte"] for x in a["segments"]] == [
        "Debout, en cercle, environ 2 minutes.", "Inspirez par le nez, par exemple sur 4 temps.", "Êtes-vous prêts ?", "Marchez."]
    for seg in a["segments"] + s["segments"]:
        assert 0.75 <= seg["debit"] <= 1.15 and 0.9 <= seg["hauteur"] <= 1.08 and seg["pause_apres_ms"] > 0
    assert a["segments"][1]["pause_apres_ms"] >= 1800            # temps de respiration après « Inspirez » (guide du souffle)
    assert sum(x["debit"] for x in a["segments"]) < sum(x["debit"] for x in s["segments"])   # Gabriel plus lent que Sophie
    assert len({x["debit"] for x in a["segments"]}) > 1          # variations d'une phrase à l'autre
    assert len({x["debit"] for x in plat["segments"][:-1]}) == 1  # prosodie non humanisée : tempo constant
    assert a["parler"] and a["duree_estimee_ms"] > s["duree_estimee_ms"]


@avec_node
def test_normalisation_prudente():
    out = js("""console.log(JSON.stringify([V.normaliser("Mesure 4/4, puis marche/course."), V.normaliser("Étapes 1re + 2e, etc."),
                                          V.normaliser("Score 3 + 4 = 7")]));""")
    assert out[0] == "Mesure 4/4, puis marche ou course."      # une fraction n'est pas lue « ou »
    assert out[1] == "Étapes première et deuxième, et cetera."
    assert out[2] == "Score 3 + 4 = 7"


def test_page_partenaire_integre_la_direction():
    html = (WEB / "partenaire.html").read_text(encoding="utf-8")
    js_page = (WEB / "partenaire.js").read_text(encoding="utf-8")
    assert 'id="d-profils"' in html and 'id="d-voix"' in html and 'id="d-locales"' in html and 'id="d-humain"' in html
    assert html.index("/static/voix-direction.js") < html.index("/static/partenaire.js")
    assert "n'imitent aucune personne réelle" in html
    # le guidage des exercices passe par la voix de direction, jamais par le robot virtuel
    guider = js_page[js_page.index("async guider()"):js_page.index("arreter() { this.guide = null")]
    assert "Direction.dire(s.texte)" in guider and "rendreSimple" not in guider
    assert "if (!tonale && !direction && Avatar.actif())" in js_page
