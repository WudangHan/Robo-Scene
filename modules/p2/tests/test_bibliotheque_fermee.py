"""Tests de la bibliothèque fermée (sans robot ni SDK) : python -m pytest code/tests"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gestes_scene import charger, valider, echantillonner, ExecuteurFerme, RefusExecution  # noqa: E402
from gestes_scene.interface_ia import schema_outil, recevoir_appel  # noqa: E402


@pytest.fixture
def ex(tmp_path):
    return ExecuteurFerme(journal=tmp_path / "journal.jsonl")


def test_bibliotheque_conforme():
    for nom, g in charger().items():
        assert valider(g) == [], (nom, valider(g))


def test_geste_hors_bibliotheque_refuse(ex):
    with pytest.raises(RefusExecution):
        ex.proposer("saut_perilleux", source="P1/SI-01")
    lignes = [json.loads(l) for l in ex.journal.read_text(encoding="utf-8").splitlines()]
    assert lignes[-1]["evenement"] == "proposition_refusee"


def test_confirmation_humaine_obligatoire(ex):
    p = ex.proposer("acquiescer", source="P1/SI-01")
    with pytest.raises(RefusExecution):
        ex.executer(p, confirmation_operateur=False, cible="sim", mini=object())


def test_brouillon_interdit_sur_robot(ex):
    p = ex.proposer("salut", source="operateur")
    with pytest.raises(RefusExecution):
        ex.autoriser(p, "robot", "lente")


def test_pleine_vitesse_robot_exige_valide(ex):
    ex.gestes["salut"].statut = "valide_robot_lent"
    p = ex.proposer("salut", source="operateur")
    with pytest.raises(RefusExecution):
        ex.autoriser(p, "robot", "pleine")
    ex.gestes["salut"].statut = "valide"
    assert ex.autoriser(p, "robot", "pleine").nom == "salut"


def test_outil_ia_sans_parametre_moteur(ex):
    s = schema_outil()
    assert set(s["input_schema"]["properties"]) == {"geste", "motif"}
    assert s["input_schema"]["additionalProperties"] is False
    with pytest.raises(ValueError):
        recevoir_appel(ex, {"geste": "joie", "vitesse": 3.0})
    assert recevoir_appel(ex, {"geste": "joie", "motif": "fin heureuse"}).geste == "joie"


def test_limite_detectee():
    g = charger()["tristesse"]
    g.images_cles[0].tete["pitch"] = 55
    assert any("pitch" in e for e in valider(g))


def test_echantillonnage_continu():
    g = charger()["refuser"]
    pts = list(echantillonner(g, frequence=50))
    assert abs(pts[-1][0] - g.duree_totale) < 0.05
    yaws = [p[1]["yaw"] for p in pts]
    assert max(yaws) <= 20.0 + 1e-6 and min(yaws) >= -20.0 - 1e-6
