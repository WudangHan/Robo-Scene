"""Tests de pseudonymiser.py — données entièrement fictives."""
from pseudonymiser import Entree, charger_table, pseudonymiser, rapport

TABLE = [Entree("A07", "personne", ["Éloïse Tremblay", "Éloïse", "Mme Tremblay"]),
         Entree("VILLE-1", "lieu", ["Rimouski"]),
         Entree("ORG-2", "organisme", ["Théâtre de l'Exemple"])]

TEXTE = """CH : Comment s'est passée la répétition ?
A07 : Bien. ELOISE tremblay m'a dit que le Théâtre de l’Exemple voulait reprendre la scène à rimouski.
A07 : Mme Tremblay, enfin Éloïse, avait 34 ans à l'époque. Écrivez-moi à eloise@exemple.org ou au 418 555-0123.
A07 : Et Gaspard, le régisseur, était d'accord.
"""


def test_remplacements_sans_accents_ni_casse_et_formes_longues_d_abord():
    r = pseudonymiser(TEXTE, TABLE)
    assert "[A07] m'a dit" in r.texte and "[ORG-2]" in r.texte and "[VILLE-1]" in r.texte
    assert "[A07], enfin [A07]" in r.texte
    assert "Tremblay" not in r.texte and "loïse" not in r.texte and "eloise" not in r.texte
    assert r.remplacements["A07"] == 3


def test_alertes_pour_ce_que_l_outil_ne_traite_pas():
    r = pseudonymiser(TEXTE, TABLE)
    types = {t for _, t, _ in r.alertes}
    assert {"courriel masqué d'office", "téléphone masqué d'office", "nom propre possible"} <= types
    assert "[courriel masqué]" in r.texte and "[téléphone masqué]" in r.texte
    assert any(x == "Gaspard" for _, t, x in r.alertes if t == "nom propre possible")
    assert any(x == "34" for _, t, x in r.alertes)
    assert "Gaspard" in rapport(r, "essai.txt")


def test_mots_entiers_seulement():
    r = pseudonymiser("Rimouskois et Rimouski.", TABLE)
    assert r.texte == "Rimouskois et [VILLE-1]."


def test_chargement_table(tmp_path):
    f = tmp_path / "t.csv"
    f.write_text("pseudonyme;type;formes\nA01;personne;Prénom Fictif|Fictif\n;;\n", encoding="utf-8")
    t = charger_table(f)
    assert len(t) == 1 and t[0].formes == ["Prénom Fictif", "Fictif"]
