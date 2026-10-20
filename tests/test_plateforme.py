"""Plateforme intégrée : routes, scène (R-05, R-06, O-05, O-12), régie (P-01, P-04), gouvernance, saisies N-07."""
from __future__ import annotations

import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bridge.pilotage.fonctions import FONCTIONS
from bridge.serveur import CTL, RACINE, charger_config, creer_app

H = {"X-Plateforme": "1"}

CONDUITE = """
titre: "Essai plateforme"
divulgations: [voix_synthese]
projecteurs: {face: {canal: 1}}
reperes:
  - numero: "1"
    nom: "Ouverture"
    actions:
      - {lumiere: {face: 200}, transfert: 0}
      - {geste: salut}
  - numero: "2"
    nom: "Réplique"
    actions:
      - {provenance: mixte}
      - {replique: {texte: "Je me lève enfin."}}
      - {voix: "Bonsoir."}
"""


@pytest.fixture
def cfg(tmp_path):
    c = charger_config(RACINE / "config.toml")
    c["robot"]["transport"] = "sim"
    c["protocole"]["dossier_corpus"] = str(tmp_path / "corpus")
    c["protocole"]["versionner_corpus"] = False
    c["donnees"] = {"dossier": str(tmp_path / "donnees")}
    c["flotte"] = {"dossier_profils": "robots_absent"}
    c["scene"] = {"a_blanc": True, "p3_a_blanc": True}
    projet = tmp_path / "projet" / "09_Application_Regie" / "source"
    projet.mkdir(parents=True)
    (projet / "data.json").write_text(json.dumps({
        "projet": {"titre": "Essai"}, "taches": [{"id": "T01", "titre": "Tâche", "statut": "à faire"}],
        "decisions": [{"id": "D08", "titre": "Robot"}]}, ensure_ascii=False), encoding="utf-8")
    c["pilotage"] = {"dossier_projet": str(tmp_path / "projet"), "inventaire_mensuel": False}
    return c


def test_table_de_couverture_complete():
    ids = [f["id"] for f in FONCTIONS]
    attendus = ([f"N-0{i}" for i in range(1, 9)] + [f"A-0{i}" for i in range(1, 9)] + [f"R-0{i}" for i in range(1, 9)]
                + [f"S-0{i}" for i in range(1, 7)] + [f"Q-0{i}" for i in range(1, 6)] + [f"G-0{i}" for i in range(1, 8)]
                + [f"P-0{i}" for i in range(1, 5)] + [f"O-{i:02d}" for i in range(1, 15)])
    assert sorted(ids) == sorted(attendus) and len(ids) == len(set(ids))
    for f in FONCTIONS:
        for chemin in f["test"].split(" ; ") if f["test"] else []:
            assert (RACINE / chemin.split(" ")[0]).exists(), chemin


async def test_plateforme_bout_en_bout(cfg, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = creer_app(cfg)
    async with TestClient(TestServer(app)) as c:
        ctl = app[CTL]
        r = await c.get("/api/plateforme")
        d = await r.json()
        assert r.status == 200 and d["fonctions"]["total"] == 60 and d["regle_ia"] == "bibliotheque_fermee"

        # Écriture sans en-tête : refusée
        assert (await c.post("/api/scene/charger", json={"texte": CONDUITE})).status == 403

        # Scène : chargement, aperçu, simulation (sans SDK : contrôle statique déclaré), GO à blanc
        r = await c.post("/api/scene/charger", json={"texte": CONDUITE}, headers=H)
        e = await r.json()
        assert r.status == 200 and e["erreurs"] == [] and e["divulgations"] == ["voix_synthese"]
        ap = await (await c.post("/api/scene/apercu", json={}, headers=H)).json()
        assert ap["actions"][1]["etat"] == "jouable"
        sim = await (await c.post("/api/scene/simuler", json={}, headers=H)).json()
        assert sim["go_simules"] == 2 and sim["gestes"][0]["jumeau"] == "non"
        assert (await c.post("/api/scene/go", json={}, headers=H)).status == 200
        r = await c.post("/api/scene/go", json={}, headers=H)
        assert (await r.json())["repere"] == "2"
        for _ in range(50):
            import asyncio
            await asyncio.sleep(0.05)
            if any(ev["module"] == "SCENE" and ev["operation"] == "attribution" for ev in ctl.trace.lire()):
                break
        att = [ev for ev in ctl.trace.lire() if ev["module"] == "SCENE" and ev["operation"] == "attribution"]
        assert att and att[0]["donnees"]["etiquette"] == "mixte" and att[0]["donnees"]["jouee"]

        # Conduite invalide : voix sans divulgation, réplique sans provenance
        bad = CONDUITE.replace("divulgations: [voix_synthese]\n", "").replace("      - {provenance: mixte}\n", "")
        e = await (await c.post("/api/scene/charger", json={"texte": bad}, headers=H)).json()
        assert any("N-05" in x for x in e["erreurs"]) and any("O-12" in x for x in e["erreurs"])
        assert (await c.post("/api/scene/go", json={}, headers=H)).status == 400

        # R-06 : écho tracé comme sélection ; geste hors bibliothèque refusé
        r = await c.post("/api/scene/echo", json={"stimulus": "l'actrice tend la main", "geste": "salut"}, headers=H)
        assert r.status == 200
        cyc = (await r.json())["cycle"]
        ops = [ev["operation"] for ev in ctl.trace.lire() if ev["cycle"] == cyc]
        assert ops == ["consigne", "selection"]
        r = await c.post("/api/scene/echo", json={"stimulus": "x", "geste": "imitation_libre"}, headers=H)
        assert r.status == 400

        # N-07 et N-08 depuis les pages
        r = await c.post("/api/trace/de_tete", json={"description": "réplique coupée au plateau"}, headers=H)
        assert r.status == 200
        ev = ctl.trace.lire()[-1]
        assert ev["reconstitue"] and ev["operation"] == "transformation"
        r = await c.post("/api/trace/autre", json={"categorie": "improvisation", "description": "réponse au public"}, headers=H)
        assert r.status == 200

        # Régie : lecture, mise à jour consignée, régisseur sans clé (extractif), revue trimestrielle
        g = await (await c.get("/api/regie")).json()
        assert g["disponible"] and g["taches"][0]["id"] == "T01"
        r = await c.post("/api/regie/tache", json={"id": "T01", "statut": "fait", "par": "SG"}, headers=H)
        assert (await r.json())["statut"] == "fait"
        r = await c.post("/api/regie/tache", json={"id": "T01", "statut": "fini", "par": "SG"}, headers=H)
        assert r.status == 400
        q = await (await c.post("/api/regie/demander", json={"question": "Où en est la décision Robot ?"}, headers=H)).json()
        assert q["mode"] == "extractif"
        rv = await (await c.post("/api/regie/revue_trimestrielle", json={}, headers=H)).json()
        assert "ISO/IEC 42001" in rv["contenu"] and "Avis éthique" in rv["contenu"]

        # Gouvernance : arrêt d'urgence → fiche d'incident, clôture motivée ; purge exige confirmation
        await ctl.arret_urgence("essai", "test")
        gv = await (await c.get("/api/gouvernance")).json()
        inc = gv["incidents_ouverts"][0]
        r = await c.post("/api/gouvernance/incident_clore", json={"id": inc["id"], "gravite": "mineur",
                                                                  "cause": "essai", "mesures": "aucune", "par": "SG"},
                         headers=H)
        assert r.status == 200, await r.text()
        r = await c.post("/api/gouvernance/conservation_purger", json={"par": "SG"}, headers=H)
        assert r.status == 400

        # Atelier P1 monté ; spectateur monté ; pages servies
        assert (await c.get("/atelier/api/etat")).status == 200
        assert (await c.get("/spectateur/api/etat")).status == 200
        assert (await c.get("/api/fonctions")).status == 200
        for page in ("atelier", "scene", "spectateur", "recherche", "gouvernance", "regie", "surtitres"):
            r = await c.get(f"/{page}")
            html = await r.text()
            assert r.status == 200 and "i18n.js" in html and "data-nav" in html, page
        r = await c.get("/tableau-public", allow_redirects=False)
        assert r.status == 302 and r.headers["Location"] == "/static/tableau-public.html"
        # Aide : page et documents servis par le pont comme par Netlify (web/aide/)
        r = await c.get("/aide", allow_redirects=False)
        assert r.status == 302 and r.headers["Location"] == "/static/aide/index.html"
        html = await (await c.get("/static/aide/index.html")).text()
        for doc in ("Guide_plateforme_integree_ROBO-SCENE_v2.0.1.docx", "Repertoire_commandes_gestes_robot_ROBO-SCENE_v1.1_2026-10-20.docx"):
            assert f"/static/aide/{doc}" in html
            r = await c.get(f"/static/aide/{doc}")
            assert r.status == 200 and (await r.read())[:2] == b"PK"      # archive Word
        assert '"/atelier/api/' in await (await c.get("/atelier/p1")).text()


async def test_biometrie_op_mouvement(cfg):
    from bridge.gouvernance.biometrie import ViolationBiometrique
    app = creer_app(cfg)
    async with TestClient(TestServer(app)):
        p = app[CTL].partenaire
        imgs = [{"t": i * 0.1, "points": {"poignet_d": [0.1 * i, 0.2, 0.0]}} for i in range(6)]
        m = {"images": imgs}
        r = await p.op_mouvement(m)
        assert "images" not in m and "flux_secousse" in r["descripteurs"]
        p.cfg["conserver_video"] = True
        with pytest.raises(ViolationBiometrique):
            await p.op_mouvement({"images": imgs})
