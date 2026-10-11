"""Volet spectateur : tirage scellé, questionnaires (S-05), séance P3, avis S-06, verrous G-02/G-04."""
from __future__ import annotations

import csv
import json
import socket
import time
from pathlib import Path

import pytest
import yaml
from aiohttp.test_utils import TestClient, TestServer

from bridge.gouvernance import Gouvernance, VerrouGouvernance
from bridge.spectateur import GestionSpectateur, avis_transparence
from bridge.spectateur.questionnaire import Instrument, ReponseInvalide, Stockage
from bridge.spectateur.tirage import Tirage, TirageExistant
from bridge.spectateur.web import app_publique

RACINE = Path(__file__).resolve().parent.parent


class FausseSeance:
    def __init__(self):
        self.evts = []

    def evenement(self, cat, **d):
        self.evts.append((cat, d))


class FauxCtl:
    def __init__(self, tmp: Path, avis=False):
        self.donnees = tmp / "donnees"
        self.donnees.mkdir()
        regles = tmp / "gouvernance"
        regles.mkdir()
        for f in ("efvp.yaml", "conservation.yaml", "registre_systemes.yaml"):
            (regles / f).write_text((RACINE / "gouvernance" / f).read_text(encoding="utf-8"), encoding="utf-8")
        etat = yaml.safe_load((RACINE / "gouvernance" / "etat.yaml").read_text(encoding="utf-8"))
        etat["avis_ethique"]["obtenu"] = avis
        (regles / "etat.yaml").write_text(yaml.safe_dump(etat, allow_unicode=True), encoding="utf-8")
        self.gouv = Gouvernance(regles, self.donnees)
        self.seance = FausseSeance()
        self.cfg = {}


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ── Instruments ─────────────────────────────────────────────
def test_instrument_I7_charge_et_signale_les_textes_manquants():
    ins = Instrument.charger(RACINE / "questionnaires" / "I-7.yaml")
    ids = [e.id for e in ins.enonces]
    assert {"AG_1", "AG_5", "MC_part_systeme", "ES_1", "PR_age"} <= set(ids)
    ag5 = next(e for e in ins.enonces if e.id == "AG_5")
    assert ag5.inverse is True and ag5.min == 1 and ag5.max == 7
    m = ins.manques("fr")
    assert "feuillet d'information (fr)" in m and "NE_COMP_1" in m and "AG_1" not in m
    # La partie « robot » (Godspeed) n'est montrée qu'en condition robot.
    sans_robot = {e.id for e in ins.visibles({"cond_support": "voix_surtitres"})}
    avec_robot = {e.id for e in ins.visibles({"cond_support": "robot"})}
    assert not any(i.startswith("GS_") for i in sans_robot) and any(i.startswith("GS_") for i in avec_robot)


def test_formulaire_public_sans_notes_ni_condition():
    ins = Instrument.charger(RACINE / "questionnaires" / "I-7.yaml")
    f = ins.formulaire("fr", {"cond_support": "robot", "cond_provenance": "affichee"}, essai=True)
    texte = json.dumps(f, ensure_ascii=False)
    assert "note" not in texte and "affichee" not in texte and "Busselle" not in texte
    assert "[NE_COMP_1 — texte à saisir]" in texte


def test_stockage_exclusions_et_validation(tmp_path):
    ins = Instrument.charger(RACINE / "questionnaires" / "I-7.yaml")
    st = Stockage(tmp_path)
    cond = {"cond_support": "robot", "cond_provenance": "affichee"}
    # Moins de 18 ans : rien n'est écrit.
    r = st.enregistrer(ins, id_representation="X2-01", condition=cond, langue="fr", essai=False,
                       admissibilite={}, presence=True, reponses={"AG_1": 5})
    assert r == {"enregistre": False, "motif": "admissibilite"} and not any(tmp_path.rglob("*.csv"))
    with pytest.raises(ReponseInvalide):
        st.enregistrer(ins, id_representation="X2-01", condition=cond, langue="fr", essai=False,
                       admissibilite={"majeur": True}, presence=True, reponses={"AG_1": 9})
    with pytest.raises(ReponseInvalide):
        st.enregistrer(ins, id_representation="X2-01", condition=cond, langue="fr", essai=False,
                       admissibilite={"majeur": True}, presence=True, reponses={"inconnu": 1})
    r = st.enregistrer(ins, id_representation="X2-01", condition=cond, langue="fr", essai=False,
                       admissibilite={"majeur": True}, presence=False,
                       reponses={"AG_1": 5, "AG_5": 2, "MC_part_systeme": 40, "MC_savait": "en_partie",
                                 "ES_ouverte": "=SOMME(A1)"})
    assert r["enregistre"] and r["id_reponse"].startswith("R")
    lignes = list(csv.DictReader((tmp_path / "I-7_X2-01.csv").open(encoding="utf-8"), delimiter=";"))
    l = lignes[0]
    assert l["AG_1"] == "5" and l["AG_2"] == "NA" and l["presence_complete"] == "0"
    assert l["cond_provenance"] == "affichee" and l["ES_ouverte"].startswith("'=")
    assert "ip" not in "".join(l).lower() and len(l["date"]) == 10


def test_I6_exige_un_pseudonyme(tmp_path):
    ins = Instrument.charger(RACINE / "questionnaires" / "I-6.yaml")
    st = Stockage(tmp_path)
    with pytest.raises(ReponseInvalide):
        st.enregistrer(ins, id_representation="AT-01", condition=None, langue="fr", essai=True,
                       admissibilite={}, presence=None, reponses={})
    assert st.enregistrer(ins, id_representation="AT-01", condition=None, langue="fr", essai=True,
                          admissibilite={}, presence=None, reponses={}, pseudonyme="P07")["enregistre"]
    assert (tmp_path / "essais" / "I-6_AT-01.csv").exists()


# ── Tirage ──────────────────────────────────────────────────
def test_tirage_scelle_et_verifiable(tmp_path):
    t = Tirage(tmp_path)
    with pytest.raises(ValueError):
        t.effectuer(8, 20271015, par="")
    r = t.effectuer(8, 20271015, par="SG")
    assert len(r["lignes"]) == 8 and len(r["sha256"]) == 64
    with pytest.raises(TirageExistant):
        t.effectuer(8, 1, par="SG")
    v = t.verifier()
    assert v["fichier_intact"] and v["rejouable"]
    assert t.condition("X2-01")["cond_provenance"] in ("affichee", "non_affichee")
    t.csv.write_text(t.csv.read_text(encoding="utf-8").replace("affichee", "AFFICHEE", 1), encoding="utf-8")
    assert not t.verifier()["fichier_intact"]


# ── Gestion : verrous, passation, P3 ────────────────────────
def test_mode_public_verrouille_sans_avis_ethique(tmp_path):
    g = GestionSpectateur(FauxCtl(tmp_path))
    with pytest.raises(VerrouGouvernance):
        g.ouvrir_passation(instrument="I-7", id_representation="X2-01", mode="public")
    with pytest.raises(VerrouGouvernance):
        g.ouvrir_p3(id_representation="X2-01", mode="public")
    assert g.etat()["verrou_public"]


def test_mode_public_exige_un_instrument_complet(tmp_path):
    ctl = FauxCtl(tmp_path, avis=True)
    ctl.gouv.efvp["couverture"]["P3_questionnaires"] = "1.0"
    g = GestionSpectateur(ctl)
    from bridge.securite import CommandeRefusee
    with pytest.raises(CommandeRefusee, match="incomplet"):
        g.ouvrir_passation(instrument="I-7", id_representation="X2-01", mode="public")


def test_avis_transparence_S06():
    a = avis_transparence("fr", essai=True, seuil=5, conservation={"DO-03": ""})
    t = " ".join(a["points"])
    assert "ESSAI" in t and "adresse IP" in t and "5" in t and "à fixer" in t
    assert "UQAM" not in t
    assert "IP address" in " ".join(avis_transparence("en", essai=False, seuil=5, conservation={})["points"])


async def test_serveur_public_passation_complete(tmp_path):
    ctl = FauxCtl(tmp_path)
    g = GestionSpectateur(ctl)
    g.tirage.effectuer(4, 7, par="SG")
    cond = g.tirage.condition("X2-01")
    async with TestClient(TestServer(app_publique(g))) as c:
        r = await c.get("/api/formulaire")
        assert r.status == 409 and (await r.json())["ferme"]
        g.ouvrir_passation(instrument="I-7", id_representation="X2-01", mode="essai")
        r = await c.get("/api/formulaire?langue=fr")
        d = await r.json()
        assert r.status == 200 and d["essai"] and d["avis"]["points"]
        assert "set-cookie" not in {k.lower() for k in r.headers} and r.headers["Cache-Control"] == "no-store"
        gs = any(e["id"].startswith("GS_") for p in d["parties"] for e in p["enonces"])
        assert gs == (cond["cond_support"] == "robot")
        r = await c.post("/api/reponses", json={"admissibilite": {"majeur": True}, "reponses": {"AG_1": 3}})
        assert r.status == 403
        r = await c.post("/api/reponses", json={"admissibilite": {"majeur": True}, "presence": True,
                                                 "reponses": {"AG_1": 3, "ES_1": 7}},
                         headers={"X-Questionnaire": "1"})
        assert r.status == 200 and (await r.json())["enregistre"]
        assert g.etat()["passation"]["reponses"] == 1
        g.fermer_passation()
    assert (ctl.donnees / "questionnaires" / "essais" / "I-7_X2-01.csv").exists()
    assert list((ctl.donnees / "depots").glob("*_tableau_depots.md"))


def test_seance_p3_essai_ouverture_osc_fermeture(tmp_path):
    from pythonosc.udp_client import SimpleUDPClient
    import urllib.request
    ctl = FauxCtl(tmp_path)
    g = GestionSpectateur(ctl, {"hote_public": "127.0.0.1"})
    port, port_osc = _port_libre(), _port_libre()
    e = g.ouvrir_p3(id_representation="ESSAI-1", mode="essai", provenance_affichee=True, port=port, port_osc=port_osc)
    assert e["p3"]["essai"] and e["p3"]["condition_provenance_affichee"]
    seance = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/seance", timeout=3).read())
    assert seance["condition_provenance_affichee"] is True
    SimpleUDPClient("127.0.0.1", port_osc).send_message("/p3/provenance", ["systeme", "3"])
    for _ in range(50):
        if g.etat()["p3"]["provenance"] == "systeme":
            break
        time.sleep(0.05)
    assert g.etat()["p3"]["provenance"] == "systeme" and g.etat()["p3"]["repere"] == "3"
    r = g.fermer_p3()
    assert r["p3"] is None and Path(r["export"]).parent.name == "essais"
    assert json.loads(Path(r["export"]).read_text(encoding="utf-8"))["systeme"] == "SI-06"
    assert [c for c, _ in ctl.seance.evts if c.startswith("p3_")] == ["p3_ouverture", "p3_fermeture"]
