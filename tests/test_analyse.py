"""Analyse Q-01 à Q-05 et O-02 sur un jeu de traces et de réponses fictif (critère d'acceptation de Q-01)."""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

import pytest

from bridge.analyse import entretiens, lancer, operatoire, statistiques, triangulation
from bridge.analyse.juges import EtudeJuges, statut_regimes
from bridge.trace import JournalCocreation
from bridge.trace.saisies import transformation_de_tete

SEANCE = "20261011_SIMULE_A_001"


def _gen(props):
    return {"systeme": "SIMULE", "version_modele": "simule-1", "type_texte": "A", "consigne": "c",
            "parametres_demandes": {}, "parametres_appliques": {}, "jetons_entree": 1, "jetons_sortie": 1,
            "propositions": props}


def traces_fictives(racine: Path) -> JournalCocreation:
    j = JournalCocreation(racine, SEANCE, versionner=False)
    P, S = ("personne", "P01"), ("systeme", "SIMULE")
    j.emettre("P1", "consigne", P, {"texte": "Une dispute", "precision": 2}, cycle="C1")
    j.emettre("P1", "generation", S, _gen(["un deux trois quatre", "cinq six"]), cycle="C1")
    j.emettre("P1", "selection", P, {"generation": 1, "proposition": 1, "decision": "retenue", "motif": "rythme"}, cycle="C1")
    j.emettre("P1", "selection", P, {"generation": 1, "proposition": 2, "decision": "rejetee", "motif": "plat"}, cycle="C1")
    j.emettre("P1", "transformation", P, {"generation": 1, "proposition": 1, "version": "un deux trois quatre cinq six sept huit",
                                          "ecart": 0.5, "conservation": 1.0}, cycle="C1")
    j.emettre("P1", "attribution", P, {"generation": 1, "proposition": 1, "etiquette": "mixte", "credit": "P01"}, cycle="C1")
    # Second cycle : P02, transformation reconstituée avec version (mesurée par l'analyse)
    Q = ("personne", "P02")
    j.emettre("P1", "consigne", Q, {"texte": "Un aveu", "precision": 4}, cycle="C2")
    j.emettre("P1", "generation", S, _gen(["alpha beta gamma delta"]), cycle="C2")
    j.emettre("P1", "selection", Q, {"generation": 1, "proposition": 1, "decision": "retenue", "motif": "juste"}, cycle="C2")
    transformation_de_tete(j, pseudonyme="P02", description="réplique raccourcie au plateau", cycle="C2",
                           generation=1, proposition=1, version="alpha delta", module="P1")
    j.emettre("P1", "autre", Q, {"description": "Écriture directe", "texte": "mot mot mot mot"}, categorie_autre="ecriture_directe")
    return j


def test_Q01_agentivite_operatoire_jeu_fictif(tmp_path):
    traces_fictives(tmp_path / "corpus")
    evs = operatoire.charger_traces(tmp_path / "corpus")
    r = operatoire.agentivite_operatoire(evs)
    e = r["ensemble"]
    assert (e["propositions"], e["retenues"], e["rejetees"]) == (3, 2, 1)
    assert e["taux_retention"] == pytest.approx(2 / 3, abs=1e-4)
    assert e["reconstituees"] == 1 and e["transformations"] == 2
    # Mots conservés : 4 (C1) + 0,5 × 4 (C2 : « alpha delta ») ; texte final : 8 + 2 + 4 (écriture directe).
    assert e["part_systeme_texte_final"] == pytest.approx(6 / 14, abs=1e-4)
    assert r["par_personne"]["P01"]["ecart_moyen"] == 0.5
    assert r["par_personne"]["P02"]["mots_ecriture_directe"] == 4
    assert set(r["par_precision_consigne"]) == {"2", "4"}
    # Reproductible : deux calculs identiques
    assert operatoire.agentivite_operatoire(evs)["ensemble"] == e
    sans = operatoire.agentivite_operatoire(evs, exclure_reconstituees=True)["ensemble"]
    assert sans["transformations"] == 1


def _ligne(rep, prov, supp, base, rng, presence=1):
    l = {"id_reponse": f"R{rng.random()}", "id_representation": rep, "cond_provenance": prov, "cond_support": supp,
         "presence_complete": str(presence), "MC_savait": "oui" if prov == "affichee" else "non",
         "MC_part_systeme": str(rng.randint(0, 100))}
    for i in range(1, 13):
        l[f"NE_{i:02d}"] = str(max(1, min(7, round(base + rng.gauss(0, 1)))))
    for i in range(1, 7):
        v = max(1, min(7, round(base + (1 if prov == "affichee" else 0) + rng.gauss(0, 1))))
        l[f"AG_{i}"] = str(8 - v if i == 5 else v)
    for k in ("ES_1", "ES_2", "ES_3"):
        l[k] = str(rng.randint(1, 7))
    return l


def test_scores_regles_A2():
    l = {f"NE_{i:02d}": "4" for i in range(1, 13)}
    l.update({"AG_1": "7", "AG_2": "7", "AG_3": "7", "AG_4": "7", "AG_5": "1", "AG_6": "NA",
              "ES_1": "5", "ES_2": "5", "ES_3": "NA", "presence_complete": "1"})
    r = statistiques.scores_I7([l])[0]
    assert r["SC_NE"] == 4 and r["SC_AG"] == 7 and r["SC_ES"] is None   # AG_5 inversé ; ES incomplet
    l.update({"NE_01": "NA", "NE_02": "NA", "NE_03": "NA"})
    assert statistiques.scores_I7([l])[0]["SC_NE"] is None                # moins de 10 énoncés sur 12
    assert statistiques.scores_I7([{**l, "presence_complete": "0"}])[0]["exclue"] == "presence_incomplete"


def test_tests_X2_plan_2x2():
    rng = random.Random(3)
    lignes = []
    for k, (prov, supp) in enumerate([("affichee", "robot"), ("non_affichee", "robot"), ("affichee", "voix_surtitres"),
                                      ("non_affichee", "voix_surtitres")] * 2):
        lignes += [_ligne(f"X2-{k + 1:02d}", prov, supp, 4, rng) for _ in range(25)]
    lignes.append(_ligne("X2-01", "affichee", "robot", 4, rng, presence=0))
    sc = statistiques.scores_I7(lignes)
    r = statistiques.tests_X2(sc, exclues={"X2-08"})
    assert r["n_retenues"] == 175 and r["representations_exclues"] == ["X2-08"]
    assert r["H4a"]["calculable"] and r["H4a"]["difference"] > 0.5
    assert r["H4b"]["calculable"] and r["H4b"]["borne"] < 0
    assert r["H2"]["calculable"]
    assert r["H4"]["soutenue"] == (r["H4a"]["soutenue"] and r["H4b"]["soutenue"])
    assert r["mixte_python"]["SC_AG"]["calculable"]
    s = statistiques.tests_X2(sc, restreindre_coherentes=True)
    assert s["restreint_coherentes"] and s["n_retenues"] == 200


def test_H2_non_testee_sans_support():
    rng = random.Random(1)
    lignes = [_ligne(f"X2-{k:02d}", p, "robot_ou_voix_selon_disponibilite", 4, rng)
              for k, p in enumerate(["affichee", "non_affichee"] * 2) for _ in range(5)]
    r = statistiques.tests_X2(statistiques.scores_I7(lignes))
    assert not r["H2"]["calculable"] and "D08" in r["H2"]["motif"]


def test_artistes_H1_H3():
    i6 = [{"pseudonyme": f"P{i:02d}", "B8": str(1 + i % 7), "B7": str(7 - i % 7)} for i in range(10)]
    op = {f"P{i:02d}": {"ecart_moyen": i / 10} for i in range(10)}
    r = statistiques.tests_artistes(i6, op)
    assert r["H1"]["calculable"] and -1 <= r["H1"]["rho"] <= 1 and len(r["H1"]["ic95_bootstrap"]) == 2
    assert 0 <= r["H1"]["declaration_excede_mesure"]["proportion"] <= 1
    assert r["H3"]["n"] == 10


def test_tables_p3_ignorent_les_cellules_masquees():
    exp = [{"condition_provenance_affichee": True, "cellules": [
        {"provenance": "systeme", "masquee": False, "emotions": {"joie": 4, "peur": 2}},
        {"provenance": "humaine", "masquee": True, "n": None}]}]
    t = statistiques.tables_p3(exp)
    assert t["tables"]["affichee"]["systeme"] == {"joie": 4, "peur": 2} and t["cellules_masquees_ignorees"] == 1


# ── Q-05 ────────────────────────────────────────────────────
class Rep:
    def __init__(self, famille, texte='{"codes": ["AG-DECL-SOI", "INVENTE"], "justification": "j"}'):
        self.famille, self.texte, self.modele_exact = famille, texte, "gemma4:12b"


class Service:
    def __init__(self, famille):
        self.famille, self.appels = famille, []

    def generer_sync(self, role, systeme, contenu, **kw):
        self.appels.append(kw)
        return Rep(self.famille)


def test_Q05_codage_local_seulement(tmp_path):
    codes = entretiens.livre()
    assert {"AG-DECL-SOI", "AG-DECL-SYS", "AG-PARTAGE", "OP-TRANS"} <= {c["code"] for c in codes}
    seg = entretiens.segmenter("C'est moi qui ai tout choisi.\n\nC'est lui qui a eu l'idée.", "P01", "E01")[0]
    s = Service("local")
    r = entretiens.suggerer(s, seg, codes)
    assert s.appels[0]["confidentielle"] is True and r["codes"] == ["AG-DECL-SOI"] and r["codes_rejetes"] == ["INVENTE"]
    assert r["statut"] == "suggéré"
    with pytest.raises(entretiens.TraitementDistantRefuse):
        entretiens.suggerer(Service("claude-opus"), seg, codes)


def test_Q05_codages_accord_et_indice(tmp_path):
    connus = {c["code"] for c in entretiens.livre()}
    segs = entretiens.segmenter("a\n\nb\n\nc\n\nd", "P01", "E01")
    a, b = entretiens.Codage(tmp_path, "C1"), entretiens.Codage(tmp_path, "C2")
    jeux = [["AG-DECL-SOI"], ["AG-DECL-SYS"], ["AG-PARTAGE"], ["AG-DECL-SOI"]]
    for s, c in zip(segs, jeux):
        a.coder(s, c, connus=connus)
        b.coder(s, c, connus=connus)
    a.coder(segs[3], ["AG-DECL-SYS"], statut="suggéré")      # une suggestion n'écrase pas l'analyse validée…
    assert len(a.lire()) == 3                                # …mais la dernière décision fait foi : segment en attente
    with pytest.raises(ValueError):
        a.coder(segs[0], ["XX"], connus=connus)
    acc = entretiens.accord(b.lire(), b.lire(), ["AG-DECL-SOI", "AG-DECL-SYS"])
    assert acc["segments_communs"] == 4 and acc["alpha_par_code"]["AG-DECL-SOI"] == 1.0
    ind = entretiens.agentivite_declaree(b.lire())["P01"]
    assert ind["indice_declare_systeme"] == pytest.approx((1 + 0.5) / 4)


# ── O-02 ────────────────────────────────────────────────────
def test_O02_validation_par_juges(tmp_path):
    e = EtudeJuges(tmp_path, "etude1")
    st = [{"id": f"S{i}", "regime": "humain" if i < 6 else "machinique", "emotion_visee": ["joie", "colere", "peur"][i % 3],
           "rendu": {"voix": "…"}} for i in range(12)]
    e.definir(st, ["joie", "colere", "peur", "tristesse"])
    with pytest.raises(FileExistsError):
        e.definir(st, ["joie"])
    seq = e.sequence("J1")
    assert "emotion_visee" not in json.dumps(seq) and seq != e.sequence("J2")
    for j in ("J1", "J2", "J3"):
        for s in st:
            emo = s["emotion_visee"] if s["regime"] == "humain" else random.Random(f"{j}{s['id']}").choice(["joie", "peur", "tristesse"])
            e.coter(j, s["id"], emo, 5)
    r = e.resultats()
    assert r["par_regime"]["humain"]["statut"] == "validé" and r["par_regime"]["humain"]["justesse"] == 1.0
    assert r["par_regime"]["machinique"]["statut"] in ("non validé", "exploratoire")
    assert statut_regimes(tmp_path)["humain"] == "validé"


# ── Q-02 et Q-04 ────────────────────────────────────────────
def test_lancer_dossier_reproductible(tmp_path):
    traces_fictives(tmp_path / "corpus")
    donnees = tmp_path / "donnees"
    (donnees / "questionnaires" / "essais").mkdir(parents=True)
    rng = random.Random(5)
    lignes = [_ligne(f"X2-{k + 1:02d}", p, "voix_surtitres", 4, rng) for k, p in enumerate(["affichee", "non_affichee"] * 2)
              for _ in range(6)]
    with (donnees / "questionnaires" / "I-7_tout.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0]), delimiter=";")
        w.writeheader()
        w.writerows(lignes)
    (donnees / "questionnaires" / "essais" / "I-7_ESSAI.csv").write_text("id_reponse\nX\n", encoding="utf-8")
    with (donnees / "questionnaires" / "I-6_AT.csv").open("w", newline="", encoding="utf-8") as f:
        f.write("pseudonyme;B2;B7;B8\nP01;5;6;7\nP02;2;4;3\n")
    r = lancer(donnees, tmp_path / "corpus", exclues=["X2-04"], sortie=tmp_path / "sortie")
    out = Path(r["dossier"])
    for f in ("scores_I7.csv", "unites_operatoires.csv", "triangulation_ateliers.csv", "resultats.json", "rapport.md",
              "A2_analyse_principale.R", "parametres.csv", "manifeste.json"):
        assert (out / f).exists(), f
    m = json.loads((out / "manifeste.json").read_text(encoding="utf-8"))
    assert all(len(x["sha256"]) == 64 for x in m["entrees"] + m["sorties"])
    assert not any("essais" in x["fichier"] for x in m["entrees"])
    assert "--exclure X2-04" in m["commande"]
    tri = r["resultats"]["Q02_triangulation"]["ateliers"][0]
    assert tri["declaree_I6_B2"] is not None and tri["operatoire_part_systeme"] is not None
    assert "H4 soutenue" in (out / "rapport.md").read_text(encoding="utf-8")
    # Régénération : mêmes tableaux (hors date)
    r2 = lancer(donnees, tmp_path / "corpus", exclues=["X2-04"], sortie=tmp_path / "sortie2")
    assert (out / "scores_I7.csv").read_bytes() == (Path(r2["dossier"]) / "scores_I7.csv").read_bytes()


def test_triangulation_scene():
    evs = [{"module": "SCENE", "operation": "attribution", "seance": "S1",
            "donnees": {"jouee": True, "etiquette_declaree": e, "etiquette": "humaine"}} for e in ("systeme", "mixte", "humaine", "humaine")]
    sc = triangulation.operatoire_scene(evs)
    assert sc["S1"]["part_systeme"] == pytest.approx(1.5 / 4)
