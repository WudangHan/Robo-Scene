"""Tests du partenaire de théâtre : python -m pytest -q tests/test_partenaire.py"""
import asyncio
import json
import math
from itertools import product

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bridge.partenaire import agents as ag
from bridge.partenaire import copresence, dramaturgie, stockage, texte, variations
from bridge.partenaire.analyse_jeu import descripteurs_mouvement, mesure_replique, precision_texte, trajectoire
from bridge.partenaire.connaissances import Index
from bridge.partenaire.livret import Livret, accompagnement
from bridge.serveur import CTL, RACINE, charger_config, creer_app

DEMO = (RACINE / "partenaire" / "demo" / "le_souffleur.txt").read_text(encoding="utf-8")
NOMS, REPOS = ["Base", "Épaule", "Coude", "Tête"], [90.0] * 4
MIN, MAX = [10, 20, 15, 30], [170, 160, 165, 150]


def run(c):
    return asyncio.run(c)


@pytest.fixture
def demo():
    p = texte.lire_texte(DEMO, "Le Souffleur", "démo")
    p["id"] = "demo-le-souffleur"
    return p


@pytest.fixture
def isole(tmp_path, monkeypatch):
    """Redirige toutes les écritures du partenaire vers un dossier temporaire."""
    monkeypatch.setattr(stockage, "DOSSIER", tmp_path / "donnees")
    monkeypatch.setattr(copresence, "DOSSIER_PLANS", tmp_path / "plans")
    monkeypatch.setattr(texte, "DOSSIER_PIECES", tmp_path / "pieces")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return tmp_path


# ── Base de connaissances et livret ─────────────────────────
def test_index_et_recherche():
    idx = Index.charger()
    assert len(idx.passages) >= 400
    assert all(p.get("source") and p.get("id") for p in idx.passages)
    r = idx.rechercher("respiration en quatre temps trac", k=3)
    assert "Livret" in r[0]["source"] and "1.2" in r[0]["section"]
    r = idx.rechercher("plan de perturbations pré-enregistré", k=3)
    assert any("Dossier" in x["source"] for x in r)


def test_livret_complet():
    L = Livret.charger()
    assert len(L.exercices) == 97
    assert {e["annee"] for e in L.exercices} == {1, 2, 3}
    assert all(e["duree_min"] and e["etapes"] and e["objectif"] for e in L.exercices)
    cal = L.d["calendriers"]["1"] if "1" in L.d["calendriers"] else L.d["calendriers"][1]
    assert all(x in L.par_id for c in cal for x in c["exercices"])
    plan = L.planifier(1, graine=7)
    assert [p["role"] for p in plan["plan"]][0] == "Échauffement" and plan["plan"][-1]["role"] == "Bilan collectif"
    assert accompagnement(L.par_id["A1-1.2"]) == "souffle" and accompagnement(L.par_id["A1-1.4"]) == "immobile"


# ── Textes et dramaturgie ───────────────────────────────────
def test_lecture_texte_brut(demo):
    reps = [e for e in demo["elements"] if e["type"] == "replique"]
    assert len(reps) == 17 and {p["nom"] for p in demo["personnages"]} == {"MARGOT", "LE SOUFFLEUR"}
    colere = next(r for r in reps if "Facile à dire" in r["texte"])
    assert colere["didascalies"] == ["avec colère"] and not colere["texte"].startswith("—")
    assert sum(e["type"] == "didascalie" for e in demo["elements"]) == 3


TEI_MINI = """<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc><titleStmt><title>Essai</title>
<author><persName>Anonyme</persName><idno>Q1</idno></author></titleStmt><publicationStmt><availability><licence>
<ab>CC0</ab></licence></availability></publicationStmt></fileDesc><profileDesc><particDesc><listPerson>
<person xml:id="a" sex="FEMALE"><persName>Ana</persName></person><person xml:id="b" sex="MALE"><persName>Bo</persName></person>
</listPerson></particDesc></profileDesc></teiHeader><text><body><div type="act"><head>ACTE I</head>
<div type="scene"><head>SCÈNE 1</head><stage>Nuit.</stage><sp who="#a"><speaker>ANA.</speaker><l>Qui va là ?</l>
<stage type="toward">À Bo.</stage><l>Réponds !</l></sp><sp who="#b"><speaker>BO.</speaker><p>Moi.</p></sp></div></div></body></text></TEI>"""


def test_lecture_tei():
    p = texte.lire_tei(TEI_MINI)
    assert p["titre"] == "Essai" and p["auteur"] == "Anonyme" and p["source"]["licence"] == "CC0"
    assert [x["genre"] for x in p["personnages"]] == ["female", "male"]
    r = [e for e in p["elements"] if e["type"] == "replique"]
    assert r[0]["texte"] == "Qui va là ?\nRéponds !" and r[0]["didascalies"] == ["À Bo."] and r[0]["vers"]
    assert p["elements"][0] == {**p["elements"][0], "type": "didascalie", "texte": "Nuit."}


def test_analyse_dramaturgique(demo):
    a = dramaturgie.analyser(demo)
    assert a["vue"]["repliques"] == 17 and a["vue"]["personnages"] == 2
    assert abs(sum(p["part_parole"] for p in a["personnages"]) - 1) < 0.01
    assert a["stichomythies"] and a["reseau"]["densite"] == 1.0
    assert dramaturgie.citation_verifiee(demo, "Le texte vient toujours après le souffle")
    assert dramaturgie.citation_verifiee(demo, "Une phrase qui n'existe pas dans la pièce") is None
    f = dramaturgie.fiche_personnage(demo, "margot")
    assert f["premiere_replique"]["texte"].startswith("Il y a quelqu'un")


def test_misanthrope_si_present():
    try:
        p = texte.Bibliotheque().lire("dracor-fre-moliere-misanthrope")
    except KeyError:
        pytest.skip("pièce non importée")
    a = dramaturgie.analyser(p)
    assert a["personnages"][0]["nom"] == "Alceste" and a["vue"]["actes"] == 5


# ── Variations émotionnelles ────────────────────────────────
def test_indices_et_propositions():
    pr = variations.propositions("Facile à dire, pour vous ! Dans votre trou !", ["avec colère"])
    assert pr["indices"]["candidats"][0]["emotion"] == "colère"
    lect, contre, mel = pr["propositions"]
    assert lect["emotion"] == "colère" and contre["emotion"] == "tendresse" and mel["melange"]
    neutre = variations.propositions("Alors commençons.")["propositions"][0]
    assert neutre["emotion"] == "neutre"


def test_rendus_bornes_et_deterministes():
    for emo, style, regime, inten in product(variations.EMOTIONS, variations.STYLES, ("humain", "machinique"), (1, 10)):
        v = variations.variation(emo, inten, style=style)
        voix = variations.rendu_voix("Je reviens de loin… et je n'ai pas peur !", v, regime)
        assert 0.6 <= voix["debit"] <= 1.6 and 0.15 <= voix["volume"] <= 1
        g = variations.rendu_geste(v, 3000, NOMS, REPOS, MIN, MAX, regime, "E1")
        assert g == variations.rendu_geste(v, 3000, NOMS, REPOS, MIN, MAX, regime, "E1")
        for im in g:
            assert all(MIN[i] <= d <= MAX[i] for i, d in enumerate(im["deg"])) and im["ms"] > 0
        assert g[-1]["deg"] == REPOS
    assert variations.rendu_voix("Oui.", variations.variation(style="film muet"))["parler"] is False
    assert variations.rendu_voix("Oui.", variations.variation("colère", 9), "machinique")["hauteur"] == 0.6


def test_voie_machinique_lisible():
    """Un effort soudain produit des pas plus courts qu'un effort soutenu ; un effort fort, plus d'ampleur."""
    def geste(eff):
        v = variations.variation(effort=eff)
        return variations.rendu_geste(v, 6000, NOMS, REPOS, MIN, MAX, "machinique", "x")
    soudain = geste({"temps": 1, "poids": 1, "espace": 1, "flux": -1})
    soutenu = geste({"temps": -1, "poids": -1, "espace": 1, "flux": -1})
    assert soudain[0]["ms"] < soutenu[0]["ms"]
    amp = lambda g: max(abs(im["deg"][1] - 90) for im in g)  # noqa: E731
    assert amp(soudain) > amp(soutenu)
    contenu = geste({"temps": 0, "poids": 0, "espace": 1, "flux": 1})
    assert any(a["deg"] == b["deg"] for a, b in zip(contenu, contenu[1:]))  # tenues marquées


# ── Analyse du jeu ──────────────────────────────────────────
def test_precision_et_mesures():
    r = precision_texte("Je reviens de loin et je n'ai pas peur", "je reviens de très loin et je n'ai peur")
    assert r["precision"] == 0.9 and r["omissions"] == ["pas"] and r["ajouts"] == ["tres"]
    m = mesure_replique("Pardon. Je suis injuste.", {"latence_ms": 600, "duree_ms": 1500, "pauses_ms": [300, 100]})
    assert m["pauses"] == 1 and 3 < m["debit_syl_s"] < 8
    assert mesure_replique("Pardon. Je suis injuste.", {"duree_ms": 320})["debit_syl_s"] is None


def test_descripteurs_mouvement():
    def mvt(f):
        return [{"t": i / 30, "points": {"poignet_d": [f(i / 30), 0.5], "nez": [0.5, 0.2]}} for i in range(60)]
    lent = descripteurs_mouvement(mvt(lambda t: 0.3 + 0.2 * math.sin(t * 1.5)))
    vif = descripteurs_mouvement(mvt(lambda t: 0.3 + 0.2 * (int(t * 6) % 2)))
    assert vif["temps_acceleration"] > lent["temps_acceleration"] and vif["flux_secousse"] > lent["flux_secousse"]
    assert descripteurs_mouvement([])["erreur"]


def test_trajectoire_stabilisation():
    ps = [{"synthese": {"latence_mediane_ms": l, "latence_dispersion_ms": d, "souffles": s, "precision_moyenne": None}}
          for l, d, s in [(900, 400, 4), (800, 300, 3), (700, 200, 1)]]
    t = trajectoire(ps)
    assert t["tendances"]["dispersion"]["pente"] < 0 and any("stabilisation" in x for x in t["lecture"])


# ── Consentements ───────────────────────────────────────────
def test_consentement_et_retrait(isole):
    s = stockage.Stockage()
    a = s.creer("Comédienne B", 2)
    with pytest.raises(PermissionError):
        s.ajouter_passage(a["id"], "p", "r", {"synthese": {}})
    s.consentir(a["id"], "mesures_vocales", True)
    assert len(s.ajouter_passage(a["id"], "p", "r", {"synthese": {}})) == 1
    s.consentir(a["id"], "mesures_vocales", False)
    assert not s.a_consenti(a["id"], "mesures_vocales") and len(s.profil(a["id"])["historique_consentements"]) == 2
    s.retirer(a["id"])
    assert s.lister() == [] and not (isole / "donnees" / "acteurs" / a["id"]).exists()


# ── Coprésence ──────────────────────────────────────────────
def test_plan_scelle(isole):
    e = copresence.sceller(copresence.plan_type_cas_a())
    assert len(e) == 64 and copresence.desceller(e)["integre"]
    f = isole / "plans" / f"{e}.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d["plan"]["perturbations"][0]["facteur"] = 1.5          # falsification a posteriori
    f.write_text(json.dumps(d), encoding="utf-8")
    assert copresence.desceller(e)["integre"] is False
    with pytest.raises(ValueError):
        copresence.sceller({"perturbations": [{"code": "P1", "facteur": 3}]})


def test_perturbations_appliquees():
    idx = variations._indices_articulations(NOMS)
    plan = copresence.valider_plan(copresence.plan_type_cas_a())
    base = copresence.generer("marche_accordee", 60, 60, REPOS, MIN, MAX, idx, None)
    pert = copresence.generer("marche_accordee", 60, 60, REPOS, MIN, MAX, idx, plan)
    p1 = [im for im in pert if im["perturbation"] == "P1"]
    assert p1 and p1[0]["ms"] == pytest.approx(base[0]["ms"] / 1.2, abs=1)
    att = copresence.generer("attente_partagee", 300, 60, REPOS, MIN, MAX, idx, plan)
    taux = sum(1 for im in att if im["perturbation"] == "P2") / len(att)
    assert 0.03 < taux < 0.35
    assert all(im["perturbation"] is None for im in copresence.generer("silence_tenu", 10, 60, REPOS, MIN, MAX, idx, plan))


# ── Agents : convention et garde-fous ───────────────────────
class _Faux:
    """Service des modèles factice (aucun appel réseau) : même interface que bridge.modeles.ServiceModeles."""

    def __init__(self, texte, fournisseur="anthropic"):
        self.texte, self.fournisseur, self.appel = texte, fournisseur, None

    def disponible(self, role="analyse"):
        return True

    def moteur(self, role="analyse"):
        return "claude-opus-5-5"

    async def generer(self, role, systeme, contenu, **kw):
        from bridge.modeles.clients import Reponse
        self.appel = {"role": role, "systeme": systeme, **kw}
        return Reponse(self.texte, self.fournisseur, "SI-01", "claude-opus-5-5", "claude-opus-5-5", 1, 1,
                       {k: v for k, v in kw.items() if v is not None}, {}, [], famille="claude-opus")


def test_convention_agents():
    conv = json.loads((RACINE / "bridge" / "partenaire" / "convention_agents.json").read_text(encoding="utf-8"))
    assert all("agent_type" in v["prompt_addition"] for v in conv.values())
    for t in ag.NOMS:
        e = ag.envelopper(t, {"x": 1})
        assert {"agent_type", "agent_name", "timestamp"} <= set(e) and e["agent_type"] == t


def test_conseiller_retire_les_references_inventees():
    idx = Index.charger()
    a = ag.Agents({"modele": "test"}, idx)
    vraie = idx.rechercher("respiration de scène", k=1)[0]["id"]
    a.service = _Faux(json.dumps({"reponse": f"La respiration régule le trac [{vraie}]. Autre fait [K99999].",
                                 "citations": [vraie, "K99999"]}))
    r = run(a.conseiller("respiration de scène"))
    assert r["citations"] == [vraie] and r["references_retirees"] == ["K99999"] and "[K99999]" not in r["reponse"]
    assert "top_p" not in a.service.appel and a.service.appel["role"] == "analyse"


def test_analyste_retire_les_citations_introuvables(demo):
    a = ag.Agents({"modele": "test"}, Index([]))
    a.service = _Faux(json.dumps({"fable": "…", "modele_actantiel": {}, "citations": [
        {"texte": "Le texte vient toujours après le souffle", "commentaire": "ok"},
        {"texte": "Je suis la reine des abeilles", "commentaire": "inventée"}]}))
    r = run(a.analyser_piece(demo))
    assert [c["texte"] for c in r["interpretation"]["citations"]] == ["Le texte vient toujours après le souffle"]
    assert len(r["citations_retirees"]) == 1


def test_variations_claude_filtrees(demo):
    a = ag.Agents({"modele": "test"}, Index([]))
    a.service = _Faux(json.dumps({"propositions": [
        {"emotion": "colère", "intensite": 8, "style": "tragédie grecque", "etiquette": "fureur",
         "indice": "Facile à dire", "justification": "…"},
        {"emotion": "extase cosmique", "intensite": 5}]}))
    rid = next(e["id"] for e in demo["elements"] if "Facile à dire" in e.get("texte", ""))
    r = run(a.variations(demo, rid))
    assert r["propositions"][0]["source"] == "claude" and r["propositions"][0]["indice_verifie"]
    assert all(p["emotion"] in variations.EMOTIONS for p in r["propositions"]) and len(r["propositions"]) == 3


# ── Bout en bout par le pont (robot simulé) ─────────────────
@pytest.fixture
def cfg(tmp_path):
    c = charger_config(RACINE / "config.toml")
    c["robot"]["transport"] = "sim"
    c["protocole"]["dossier_corpus"] = str(tmp_path / "corpus")
    c["donnees"] = {"dossier": str(tmp_path / "donnees")}
    c["flotte"] = {"dossier_profils": "robots_absent"}
    return c


async def recevoir(ws, typ, delai=6.0):
    async def boucle():
        while True:
            m = json.loads((await ws.receive()).data)
            if m["type"] in (typ, "p_erreur"):
                return m
    return await asyncio.wait_for(boucle(), delai)


def test_repetition_par_le_pont(cfg, isole, demo):
    texte.Bibliotheque().enregistrer(demo)

    async def scenario():
        app = creer_app(cfg)
        async with TestClient(TestServer(app)) as cl:
            ws = await cl.ws_connect("/ws")
            ctl = app[CTL]

            async def op(o, **d):
                await ws.send_json({"op": o, **d})
                return await recevoir(ws, o)

            await op("p_acteur_creer", pseudonyme="Testeuse", annee=1)
            await op("p_consentir", acteur="testeuse", cle="mesures_vocales", accorde=True)
            await op("p_incarnation", actif=True)
            for passage in range(3):
                plan = await op("p_repet_demarrer", piece="demo-le-souffleur", roles=["margot"], acteur="testeuse",
                                niveau=passage, variation_mode="cycle")
                assert plan["agent_type"] == "repetiteur" and plan["passage"] == passage + 1
                items = plan["items"]
                robot = next(i for i in items if i["type"] == "replique" and not i["acteur"])
                assert robot["voix"]["segments"] and robot["variation"]["etiquette"]
                await op("p_repet_geste", replique=robot["id"], variation=robot["variation"], duree_ms=1500)
                for k, it in enumerate(i for i in items if i.get("acteur")):
                    if passage == 2:
                        assert it["affiche"] in ("…",) or it["affiche"].endswith("…")
                    r = await op("p_repet_mesure", repetition=plan["repetition"], replique=it["id"],
                                 latence_ms=900 - 200 * passage + 30 * (k % 3) * (2 - passage), duree_ms=2000,
                                 pauses_ms=[], souffles=2 - passage)
                    assert r["mesure"]["latence_ms"] is not None
                fin = await op("p_repet_terminer")
                assert fin["conserve"] and fin["retour"]["agent_type"] == "analyste_jeu"
            assert fin["trajectoire"]["passages"] == 3
            assert fin["trajectoire"]["tendances"]["souffles"]["pente"] < 0
            # Le geste du partenaire passe par le pont : la séquence a été lancée sur le robot simulé
            journal = ctl.seance.chemin_evt.read_text(encoding="utf-8")
            assert '"origine": "partenaire:repetiteur"' in journal
            # Plan scellé inscrit dans les métadonnées de séance
            s = await op("p_cop_sceller", plan=copresence.plan_type_cas_a())
            assert ctl.seance.meta["plans_scelles"][0]["empreinte"] == s["empreinte"]
            r = await op("p_cop_jouer", situation="silence_tenu", duree_s=3, tempo=60, empreinte=s["empreinte"])
            assert r["joue"] and "perturbation" not in json.dumps(r)
            # Arrêt d'urgence : les gestes suivants sont refusés par la couche de sécurité
            await ws.send_json({"op": "estop"})
            await asyncio.sleep(0.3)
            await op("p_rendu", texte="Encore une fois.", variation={"emotion": "joie", "intensite": 6}, jouer=True)
            await asyncio.sleep(0.3)
            assert ctl.securite.arret_urgence
            journal = ctl.seance.chemin_evt.read_text(encoding="utf-8")
            apres = journal[journal.index("ARRÊT D'URGENCE"):]
            assert "variation:joie » interrompue : Arrêt d'urgence actif" in apres
            # Droit de retrait
            r = await op("p_acteur_retirer", id="testeuse")
            assert r["acteurs"] == []
            await ws.close()

    run(scenario())


def test_import_texte_et_erreur_lisible(cfg, isole):
    async def scenario():
        app = creer_app(cfg)
        async with TestClient(TestServer(app)) as cl:
            ws = await cl.ws_connect("/ws")
            await ws.send_json({"op": "p_importer_texte", "titre": "Vide", "texte": "rien de dramatique ici"})
            e = await recevoir(ws, "p_importer_texte")
            assert e["type"] == "p_erreur" and "Aucune réplique" in e["msg"]
            await ws.send_json({"op": "p_importer_texte", "titre": "Le Souffleur", "texte": DEMO})
            ok = await recevoir(ws, "p_importer_texte")
            assert ok["repliques"] == 17
            await ws.close()

    run(scenario())


@pytest.mark.skipif(not (RACINE / "partenaire" / "repertoire" / "dracor_fre.json").exists(), reason="catalogue absent")
def test_catalogue_dracor_hors_ligne():
    r = texte.RepertoireDraCor().chercher("fre", hommes=2, femmes=3)
    assert r["total"] > 0 and all(x["numOfSpeakersMale"] == 2 and x["numOfSpeakersFemale"] == 3 for x in r["resultats"])
    assert "Comedy" in r["genres"]





def test_syllabes_e_caducs_et_terminaison_ent():
    """Audit du 2026-10-16 (chantier 5) : débit syllabique pondéré par les e caducs."""
    from bridge.partenaire.texte_outils import syllabes
    cas = {"porte": 1, "portes": 1, "étoile": 2, "aimée": 2, "le": 1, "je": 1,
           "moment": 2, "souvent": 2,                     # -ent nasal : conservé
           "ils parlent": 2, "elles ne se parlent": 4,    # -ent verbal muet après « ils », « elles »
           "l'homme": 1, "qu'il vienne": 2, "Je ne reviendrai pas.": 6}
    assert {t: syllabes(t) for t in cas} == cas
