"""Tests des séquences gestuelles (P2.4) — sans robot ni SDK."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gestes_scene import ExecuteurFerme, RefusExecution, charger, valider  # noqa: E402
from gestes_scene.interface_ia import schema_outil  # noqa: E402
from gestes_scene.sequenceur import ErreurSequence, charger_sequences, composer, duree_transition  # noqa: E402
from gestes_scene.bibliotheque import POSE_NEUTRE  # noqa: E402


@pytest.fixture
def biblio():
    return charger()


def test_sequences_livrees_conformes(biblio):
    seqs = charger_sequences(biblio=biblio)
    assert set(seqs) == {"eveil", "cour_jardin", "surprise_joie", "fin_de_scene"}
    for s in seqs.values():
        assert valider(s) == [] and s.statut == "brouillon"


def test_transition_inseree_quand_l_enchainement_direct_depasse_les_limites(biblio):
    s = composer("t", {"elements": [{"geste": "regarder_cour"}, {"geste": "regarder_jardin"}]}, biblio)
    types = [e.type for e in s.plan]
    assert types == ["geste", "transition", "geste"]
    t = s.plan[1]
    assert t.fin_s - t.debut_s == pytest.approx(duree_transition(biblio["regarder_cour"].images_cles[-1], POSE_NEUTRE))


def test_liaison_directe_impossible_refusee(biblio):
    with pytest.raises(ErreurSequence, match="liaison directe impossible"):
        composer("t", {"elements": [{"geste": "regarder_cour"}, {"geste": "regarder_jardin", "liaison": "directe"}]}, biblio)


def test_regles_de_composition(biblio):
    with pytest.raises(ErreurSequence, match="bibliothèque fermée"):
        composer("t", {"elements": [{"geste": "saut_perilleux"}]}, biblio)
    with pytest.raises(ErreurSequence, match="aucune accélération"):
        composer("t", {"elements": [{"geste": "salut", "etirement": 0.5}]}, biblio)
    with pytest.raises(ErreurSequence, match="vide"):
        composer("t", {"elements": []}, biblio)
    s = composer("t", {"elements": [{"geste": "salut", "etirement": 2}]}, biblio)
    assert s.duree_totale == pytest.approx(2 * biblio["salut"].duree_totale)


def test_statut_effectif_est_le_plus_bas(biblio):
    biblio["acquiescer"].statut = "valide"
    s = composer("t", {"statut": "valide", "elements": [{"geste": "acquiescer"}, {"geste": "salut"}]}, biblio)
    assert s.statut == "brouillon"      # salut est encore en brouillon


def test_executeur_et_interface_ia_traitent_les_sequences_comme_des_noms(tmp_path):
    ex = ExecuteurFerme(journal=tmp_path / "j.jsonl")
    p = ex.proposer("fin_de_scene", source="P1/SI-01")
    with pytest.raises(RefusExecution):          # séquence en brouillon : interdite sur le robot
        ex.autoriser(p, "robot", "lente")
    assert ex.autoriser(p, "sim", "lente").nom == "fin_de_scene"
    enum = schema_outil()["input_schema"]["properties"]["geste"]["enum"]
    assert "fin_de_scene" in enum and "salut" in enum
