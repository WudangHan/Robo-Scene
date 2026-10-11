"""Extensions du §4 : O-01, O-03, O-06, O-07, O-08, O-09, O-10."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bridge.accessibilite import Surtitrage
from bridge.diffusion import c2pa, tableau_public
from bridge.partenaire import consigne_graduee, texte as texte_mod, variations
from bridge.partenaire.tei_export import exporter
from bridge.trace import JournalCocreation
from bridge.veille import Veille, mla


# ── O-01 ────────────────────────────────────────────────────
def test_consigne_graduee_quatre_registres():
    v = variations.variation("colère", 7, etiquette="colère rentrée")
    d = variations.decrire(v)
    g = {n: consigne_graduee.graduer(v, d, n) for n in (1, 2, 3, 4)}
    assert "colère" not in g[1]["texte"] and g[1]["emotion"] is None
    assert "colère" in g[2]["texte"] and g[2]["intensite"] is None
    assert "7/10" in g[3]["texte"] and g[3]["qualites"]
    assert g[4]["complete"] and "prosodie" in g[4]["texte"]
    assert consigne_graduee.niveau("x") == 4 and consigne_graduee.niveau(9) == 4 and consigne_graduee.niveau(0) == 1


# ── O-03 ────────────────────────────────────────────────────
def test_tei_aller_retour():
    p = texte_mod.lire_texte("ACTE I\nSCÈNE 1\nMARIE. — Tu es là ? (Elle se retourne.)\nPAUL. — Depuis toujours.\n"
                             "SCÈNE 2\nMARIE. — Alors parle.", titre="Essai TEI", auteur="Anonyme")
    xml = exporter(p, licence="CC BY 4.0")
    assert xml.startswith("<?xml") and "particDesc" in xml and "CC BY 4.0" in xml
    r = texte_mod.lire_tei(xml.encode("utf-8"))
    rep = lambda q: [(e["nom"], e["texte"]) for e in q["elements"] if e["type"] == "replique"]  # noqa: E731
    assert rep(r) == rep(p) and len(r["scenes"]) == len(p["scenes"]) and r["titre"] == "Essai TEI"
    assert {x["nom"] for x in r["personnages"]} == {x["nom"] for x in p["personnages"]}


# ── O-06 ────────────────────────────────────────────────────
class Rep:
    def __init__(self, texte):
        self.texte, self.systeme, self.modele_exact = texte, "SI-01", "claude-opus-5-5"

    def trace(self):
        return {"systeme": "SI-01", "version_modele": "claude-opus-5-5", "parametres_demandes": {},
                "parametres_appliques": {}, "ecarts_parametres": [], "jetons_entree": 3, "jetons_sortie": 5}


class Service:
    def __init__(self):
        self.kw = None

    async def generer(self, role, systeme, contenu, **kw):
        self.kw = kw
        ids = [l[1:l.index("]")] for l in contenu.splitlines() if l.startswith("[")]
        return Rep(json.dumps({"items": [{"id": i, "texte": f"EN {i}"} for i in ids]}))


class Ctl:
    def __init__(self, tmp):
        self.donnees = tmp
        self.trace = JournalCocreation(tmp / "corpus", "20261011_SIMULE_S04_001", versionner=False)
        self.service = Service()
        self.pseudo_operatrice = "OP01"


async def test_surtitrage_valide_avant_diffusion(tmp_path):
    from types import SimpleNamespace
    from pont_scenique.conduite import Action, Conduite, Repere
    ctl = Ctl(tmp_path)
    ctl.scene = SimpleNamespace(conduite=Conduite("T", {}, [
        Repere("1", "Ouverture", [Action("geste", "salut", 0.0), Action("provenance", "humaine", 0.0),
                                  Action("replique", {"texte": "Bonsoir."}, 0.0)]),
        Repere("2", "Suite", [Action("provenance", "systeme", 0.0), Action("replique", {"texte": "Déjà ?", "en": "Already?"}, 0.0)]),
    ], []))
    st = Surtitrage(ctl)
    e = st.importer_conduite()
    ids = [x["id"] for x in e["elements"]]
    assert "1-AD" in ids and "1-2" in ids
    assert st.valide("2", "en") == "Already?"          # version humaine de la conduite
    await st.proposer(["1-2"], "en", confidentielle=True)
    assert ctl.service.kw["confidentielle"] is True
    assert st.valide("1", "en") is None                 # rien n'est diffusé avant validation
    with pytest.raises(ValueError):
        st.valider("1-2", "en", decision="valide", par="")
    st.valider("1-2", "en", decision="valide", par="T01", texte="Good evening.")
    assert st.valide("1", "en") == "Good evening."
    v = st.elements["1-2"]["versions"]["en"]
    assert v["etiquette"] == "mixte" and v["ecart"] > 0
    ops = [x["operation"] for x in ctl.trace.lire()]
    assert ops == ["consigne", "generation", "selection", "transformation", "attribution"]
    assert ctl.trace.completude()["conforme"]
    vtt = st.webvtt("en").read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT") and "Good evening." in vtt and "provenance=mixte" in vtt and "Already?" in vtt


# ── O-07 ────────────────────────────────────────────────────
def test_c2pa_compagnon_non_signe(tmp_path):
    f = tmp_path / "affiche.png"
    f.write_bytes(b"\x89PNG\r\n")
    with pytest.raises(ValueError):
        c2pa.produire(f, nature="mixte", titre="Affiche", auteurs=["S. Gagné"])
    r = c2pa.produire(f, nature="mixte", titre="Affiche", auteurs=["S. Gagné"],
                      description_ia="Fond généré par un système d'IA, retravaillé par l'équipe.", outil="outil_absent")
    assert r["mode"] == "non_signe"
    d = json.loads(Path(r["fichier"]).read_text(encoding="utf-8"))
    assert "NON SIGNÉ" in d["avertissement"] and len(d["sha256"]) == 64
    act = d["definition"]["assertions"][0]
    assert act["label"] == "c2pa.actions.v2"
    assert act["data"]["actions"][0]["digitalSourceType"].endswith("compositeWithTrainedAlgorithmicMedia")


# ── O-08 ────────────────────────────────────────────────────
CROSSREF = {"message": {"items": [{"title": ["Measuring Narrative Engagement"], "DOI": "10.1080/15213260903287259",
                                   "author": [{"family": "Busselle", "given": "Rick"}, {"family": "Bilandzic", "given": "Helena"}],
                                   "issued": {"date-parts": [[2009]]}, "container-title": ["Media Psychology"],
                                   "volume": "12", "issue": "4", "page": "321-347"}]}}
S2 = {"data": [{"title": "Measuring narrative engagement", "authors": [{"name": "Rick Busselle"}], "year": 2009,
                "venue": "Media Psychology", "externalIds": {"DOI": "10.1080/15213260903287259"}}]}
ARXIV = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2501.00001v1</id>
<title>Robots on Stage</title><published>2025-01-02T00:00:00Z</published><author><name>Ada Lovelace</name></author></entry></feed>"""


def faux_get(url: str) -> bytes:
    if "crossref" in url:
        return json.dumps(CROSSREF).encode()
    if "semanticscholar" in url:
        return json.dumps(S2).encode()
    if "arxiv" in url:
        return ARXIV
    raise OSError("injoignable")


def test_veille_dedoublonne_et_exige_verification(tmp_path):
    v = Veille(tmp_path, get=faux_get)
    r = v.chercher("narrative engagement")
    assert r["nouvelles"] == 2 and r["a_verifier"] == 2 and not r["erreurs"]
    k = "doi:10.1080/15213260903287259"
    assert set(v.notices[k]["sources"]) == {"crossref", "semantic_scholar"}
    assert v.bibliographie() == ""                        # rien n'est exporté avant vérification
    with pytest.raises(ValueError):
        v.verifier(k, statut="vérifiée", par="SG")         # note de vérification exigée
    v.verifier(k, statut="vérifiée", par="SG", note="Notice de l'éditeur consultée")
    b = v.bibliographie()
    assert b == ("Busselle, Rick, et Helena Bilandzic. « Measuring Narrative Engagement. » *Media Psychology*, "
                 "vol. 12, no 4, 2009, p. 321–347, https://doi.org/10.1080/15213260903287259.")
    v2 = Veille(tmp_path, get=lambda u: (_ for _ in ()).throw(OSError("réseau")))
    assert set(v2.chercher("x")["erreurs"]) == {"crossref", "arxiv", "semantic_scholar"}


def test_mla_trois_auteurs_et_url():
    r = {"auteurs": [{"nom": "A", "prenom": "B"}, {"nom": "C", "prenom": "D"}, {"nom": "E", "prenom": "F"}],
         "titre": "T", "revue": "arXiv", "annee": 2025, "url": "https://arxiv.org/abs/1", "consulte": "2026-10-11T10:00:00"}
    assert mla(r) == "A, B, et al. « T. » *arXiv*, 2025, https://arxiv.org/abs/1. Consulté le 11 oct. 2026."


# ── O-09 ────────────────────────────────────────────────────
def test_tableau_public_seuil_et_validation(tmp_path):
    d = tmp_path / "donnees" / "analyse" / "2026-10-11_1200"
    d.mkdir(parents=True)
    res = {"Q02_triangulation": {"representations": [
        {"unite": "X2-01", "reponses": 25, "cond_provenance": "affichee", "percue_MC_part_systeme": 0.4},
        {"unite": "X2-02", "reponses": 3, "cond_provenance": "non_affichee"}]},
        "Q03_P3": {"tables": {"affichee": {"systeme": {"joie": 4, "peur": 3}, "humaine": {"joie": 2}}}},
        "Q01_operatoire": {"ensemble": {"propositions": 12, "taux_retention": 0.5}},
        "Q03_X2": {"H4a": {"soutenue": False, "calculable": False}, "H4b": {"soutenue": False},
                   "H2": {"soutenue": False}, "H4": {"soutenue": False}}}
    (d / "resultats.json").write_text(json.dumps(res), encoding="utf-8")
    t = tableau_public.preparer(tmp_path / "donnees")
    texte = json.dumps(t, ensure_ascii=False)
    assert "X2-01" not in texte and len(t["representations"]) == 1 and t["groupes_retires"] == 2
    assert t["retroaction_p3"]["affichee"] == {"systeme": {"n": 7, "emotions": {"joie": 4, "peur": 3}}}
    assert "UQAM" not in texte and t["valide"] is None
    with pytest.raises(ValueError):
        tableau_public.publier(tmp_path / "donnees", tmp_path / "web", "")
    f = tableau_public.publier(tmp_path / "donnees", tmp_path / "web", "SG")
    assert json.loads(f.read_text(encoding="utf-8"))["valide"]["par"] == "SG"


# ── O-10 ────────────────────────────────────────────────────
async def test_mode_pedagogique_separe(tmp_path, monkeypatch):
    from bridge.partenaire.controleur import Partenaire

    class Seance:
        def __init__(self):
            self.evts = []

        def evenement(self, cat, **d):
            self.evts.append(cat)

    class C:
        cfg = {"pedagogie": {"actif": True, "dossier": str(tmp_path / "ett")}}
        seance = Seance()
        service = None
        donnees = tmp_path

    p = Partenaire(C(), {})
    assert p.mode == "pedagogie" and str(p.stockage.dossier).startswith(str(tmp_path / "ett"))
    a = p.stockage.creer("ELEVE1")
    p.stockage.consentir(a["id"], "recherche", True)
    assert not p._recherche(a["id"])                  # jamais vers la recherche en mode pédagogique
    p._journal("essai", x=1)
    assert (tmp_path / "ett" / "journal_pedagogique.jsonl").exists() and C.seance.evts == []
    r = await p.op_mode({"mode": "recherche"})
    assert r["mode"] == "recherche" and all(x["pseudonyme"] != "ELEVE1" for x in r["acteurs"])
