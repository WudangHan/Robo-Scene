"""Noyau de traçabilité : schéma (N-02), dépôt et commits (N-03), écart (N-04), PROV (N-06),
saisies de tête (N-07), catégorie ouverte (N-08), complétude (N-01)."""
import json
import subprocess

import pytest
from rdflib import Graph

from bridge.trace import EvenementInvalide, JournalCocreation, identifiant_seance, valider
from bridge.trace.ecart import ecart_transformation, mesurer, taux_conservation
from bridge.trace.provenance import en_turtle
from bridge.trace.saisies import autre, consigner_revue, revue_autres, transformation_de_tete


def gen(props, **k):
    return {"systeme": "SI-01", "version_modele": "claude-opus-5-5", "type_texte": "B", "consigne": "Écris…",
            "contexte": "Acte I", "parametres_demandes": {"temperature": 0.7}, "parametres_appliques": {"temperature": 0.7},
            "jetons_entree": 12, "jetons_sortie": 40, "propositions": props, **k}


def cycle_complet(j, cyc="C01"):
    j.emettre("P1", "consigne", ("personne", "A01"), {"texte": "Une porte qui ne se ferme pas"}, cycle=cyc)
    j.emettre("P1", "generation", ("systeme", "SI-01"), gen(["Prop un.", "Prop deux."], numero=1), cycle=cyc)
    j.emettre("P1", "selection", ("personne", "A01"), {"generation": 1, "proposition": 1, "decision": "retenue",
                                                       "motif": "silence"}, cycle=cyc)
    j.emettre("P1", "selection", ("personne", "A01"), {"generation": 1, "proposition": 2, "decision": "rejetee",
                                                       "motif": "cliché"}, cycle=cyc)
    j.emettre("P1", "transformation", ("personne", "A01"), {"generation": 1, "proposition": 1,
                                                            "version": "Prop un, réécrite.", **mesurer("Prop un.", "Prop un, réécrite.")},
              cycle=cyc)
    j.emettre("P1", "attribution", ("personne", "A01"), {"generation": 1, "proposition": 1, "etiquette": "mixte",
                                                         "credit": "A01"}, cycle=cyc)


def test_identifiant_et_schema(tmp_path):
    sid = identifiant_seance(tmp_path / "traces", "P1", "ATELIER", "20261011")
    assert sid == "20261011_P1_ATELIER_001"
    with pytest.raises(ValueError):
        JournalCocreation(tmp_path, "seance-libre")
    j = JournalCocreation(tmp_path, sid)
    with pytest.raises(EvenementInvalide):       # génération sans version du modèle
        j.emettre("P1", "generation", ("systeme", "SI-01"), {"propositions": ["x"]}, cycle="C1")
    with pytest.raises(EvenementInvalide):       # « autre » exige une catégorie
        j.emettre("P1", "autre", ("personne", "A01"), {"description": "x"})
    with pytest.raises(EvenementInvalide):       # étiquette hors liste
        j.emettre("P1", "attribution", ("personne", "A01"), {"etiquette": "machine", "credit": "A01"}, cycle="C1")
    assert j.lire() == []


def test_generation_deposee_et_commit(tmp_path):
    j = JournalCocreation(tmp_path, "20261011_P1_ATELIER_001")
    cycle_complet(j)
    ev = [e for e in j.lire() if e["operation"] == "generation"][0]
    d = ev["donnees"]
    assert d["identifiant_generation"] == "20261011_CLAUDE-OPUS-5-5_B_001"
    assert (tmp_path / d["fichier_texte"]).read_text(encoding="utf-8").startswith("[1] Prop un.")
    meta = json.loads((tmp_path / d["fichier_meta"]).read_text(encoding="utf-8"))
    assert meta["consigne_integrale"] == "Écris…" and meta["longueur_jetons"] == {"entree": 12, "sortie": 40}
    log = subprocess.run(["git", "log", "--format=%H %s"], cwd=tmp_path, capture_output=True, text=True).stdout
    assert d["commit"] and d["commit"] in log and "Génération 20261011_CLAUDE-OPUS-5-5_B_001" in log
    for e in j.lire():
        assert valider({k: v for k, v in e.items()}) == [] or e["operation"] == "generation"


def test_completude(tmp_path):
    j = JournalCocreation(tmp_path, "20261011_P1_ATELIER_002", versionner=False)
    cycle_complet(j, "C01")
    assert j.completude()["conforme"]
    j.emettre("P1", "consigne", ("personne", "A02"), {"texte": "Un silence"}, cycle="C02")
    j.emettre("P1", "generation", ("systeme", "SI-01"), gen(["Seule."]), cycle="C02")
    c = j.completude()
    assert not c["conforme"] and c["manques"][0]["manque"] == "selection"
    # Un motif d'absence consigné satisfait le critère
    j.emettre("P1", "selection", ("personne", "A02"), {"absence": True, "motif": "séance interrompue"}, cycle="C02")
    assert j.completude()["conforme"]


def test_ecart_cas_etalons():
    assert ecart_transformation("La porte.", "La porte.") == 0.0
    assert taux_conservation("La porte reste ouverte", "La porte reste ouverte") == 1.0
    assert ecart_transformation("abc", "xyz") == 1.0
    assert taux_conservation("La porte reste ouverte", "Un ciel sans nuages") == 0.0
    # Proposition gardée puis prolongée : écart notable, conservation complète
    m = mesurer("Elle compte jusqu'à trois.", "Elle compte jusqu'à trois, puis se tait, longtemps, devant nous.")
    assert m["conservation"] == 1.0 and m["ecart"] > 0.4


def test_export_prov(tmp_path):
    j = JournalCocreation(tmp_path, "20261011_P1_ATELIER_003", versionner=False)
    cycle_complet(j)
    g = Graph().parse(data=en_turtle(j.lire()), format="turtle")
    q = """PREFIX prov: <http://www.w3.org/ns/prov#>
           SELECT ?v ?p WHERE { ?v prov:wasDerivedFrom ?p . ?p prov:wasGeneratedBy ?g . ?g prov:wasAssociatedWith ?a }"""
    assert len(list(g.query(q))) == 1


def test_saisies_de_tete_et_autres(tmp_path):
    j = JournalCocreation(tmp_path, "20261011_SCENE_REPET_001", versionner=False)
    import time
    t0 = time.time()
    e = transformation_de_tete(j, pseudonyme="A03", description="Réplique dite à l'envers au plateau",
                               cycle="C01", generation=1, proposition=1, debut_saisie=t0)
    assert e["reconstitue"] and e["donnees"]["delai_saisie_s"] < 30
    autre(j, pseudonyme="A03", categorie="improvisation_collective", description="Le groupe a recomposé la scène")
    r = revue_autres(j.lire())
    assert r["par_categorie"] == {"improvisation_collective": 1} and r["reconstituees"] == 1
    with pytest.raises(ValueError):
        consigner_revue(tmp_path, j.seance, [{"categorie": "x", "decision": "ecartee"}], "SG")
    f = consigner_revue(tmp_path, j.seance, [{"categorie": "improvisation_collective",
                                              "decision": "nouvelle_categorie", "justification": "Récurrente"}], "SG")
    assert f.exists()
