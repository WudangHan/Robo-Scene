"""Grille de relecture des biais narratifs (critère 5 de mise en service, fiche P1.1) : génération du lot d'essai
de 50 propositions et calcul de la fiabilité de la cotation.

    # 1) produire les 50 propositions (10 consignes × 5) dans une copie du classeur
    python -m atelier_p1.grille_biais generer P1-GB_Grille_biais_narratifs_v1.0.xlsx essai_grille.xlsx [--simule]
    # 2) après les deux passages de cotation : alpha de Krippendorff par dimension
    python -m atelier_p1.grille_biais fiabilite essai_grille.xlsx

Le générateur passe par le routeur D03 ; les consignes d'essai ne contiennent aucune donnée personnelle.
"""
from __future__ import annotations

import argparse
from collections import Counter
from itertools import permutations

DIMENSIONS = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"]


def alpha_krippendorff(unites, niveau: str = "nominal") -> float | None:
    """Alpha de Krippendorff (Hayes et Krippendorff, 2007), par la matrice de coïncidences.

    `unites` : une liste d'unités, chacune la liste des valeurs attribuées par les codeurs (None = manquante).
    `niveau` : « nominal », « ordinal » ou « intervalle ». Renvoie None si l'accord attendu est nul (une seule valeur).
    """
    o: Counter = Counter()
    for u in unites:
        v = [x for x in u if x is not None]
        m = len(v)
        if m < 2:
            continue                                   # une unité n'est pairable qu'avec au moins deux valeurs
        for a, b in permutations(range(m), 2):
            o[(v[a], v[b])] += 1 / (m - 1)
    valeurs = sorted({c for c, _ in o})
    n_c = {c: sum(o[(c, k)] for k in valeurs) for c in valeurs}
    n = sum(n_c.values())
    if n <= 1 or len(valeurs) < 2:
        return None

    def delta2(c, k):
        if c == k:
            return 0.0
        if niveau == "nominal":
            return 1.0
        if niveau == "intervalle":
            return float(c - k) ** 2
        if niveau == "ordinal":
            i, j = sorted((valeurs.index(c), valeurs.index(k)))
            somme = sum(n_c[valeurs[g]] for g in range(i, j + 1))
            return (somme - (n_c[c] + n_c[k]) / 2) ** 2
        raise ValueError("niveau : nominal, ordinal ou intervalle")

    d_o = sum(o[(c, k)] * delta2(c, k) for c in valeurs for k in valeurs) / n
    d_e = sum(n_c[c] * n_c[k] * delta2(c, k) for c in valeurs for k in valeurs) / (n * (n - 1))
    return None if d_e == 0 else round(1 - d_o / d_e, 4)


def fiabilite(classeur: str) -> dict:
    """Compare les onglets « Cotation » et « Recotation » : alpha ordinal (0-1-2) et nominal (présence ≥ 1)."""
    from openpyxl import load_workbook
    wb = load_workbook(classeur, data_only=True)
    p1 = {r[0]: r[4:12] for r in wb["Cotation"].iter_rows(min_row=5, values_only=True) if r[0]}
    p2 = {r[0]: r[1:9] for r in wb["Recotation"].iter_rows(min_row=5, values_only=True) if r[0]}
    res = {}
    for j, dim in enumerate(DIMENSIONS):
        unites = [[p1[i][j], p2.get(i, (None,) * 8)[j]] for i in p1]
        presence = [[None if x is None else int(x >= 1) for x in u] for u in unites]
        res[dim] = {"alpha_ordinal": alpha_krippendorff(unites, "ordinal"),
                    "alpha_presence": alpha_krippendorff(presence, "nominal"),
                    "paires": sum(1 for u in unites if None not in u)}
    return res


def generer(classeur: str, sortie: str, simule: bool = False, nb: int = 5) -> int:
    from openpyxl import load_workbook
    from .modeles import ModeleDistant, ModeleLocal, ModeleSimule
    from .routeur import Routeur
    wb = load_workbook(classeur)
    consignes = [(r[0], r[1], r[2]) for r in wb["Consignes d'essai"].iter_rows(min_row=5, values_only=True) if r[0]]
    routeur, distant, local = Routeur(), ModeleDistant(), ModeleLocal()
    ws, ligne = wb["Cotation"], 5
    for code, type_, texte in consignes:
        if simule:
            modele = ModeleSimule()
        else:
            modele = local if routeur.decider(texte).cible == "local" else distant
            if not modele.disponible:
                raise SystemExit(f"Modèle {modele.code} indisponible : clé API ou modèle local à configurer.")
        g = modele.generer(texte, type_, nb)
        for p in g.propositions[:nb]:
            ws.cell(row=ligne, column=2, value=code)
            ws.cell(row=ligne, column=3, value=f"{g.systeme} ({g.modele})")
            ws.cell(row=ligne, column=4, value=p)
            ligne += 1
    wb.save(sortie)
    return ligne - 5


def main(argv=None):
    ap = argparse.ArgumentParser(description="Grille de biais : génération du lot d'essai et fiabilité")
    sp = ap.add_subparsers(dest="cmd", required=True)
    g = sp.add_parser("generer"); g.add_argument("classeur"); g.add_argument("sortie"); g.add_argument("--simule", action="store_true")
    f = sp.add_parser("fiabilite"); f.add_argument("classeur")
    a = ap.parse_args(argv)
    if a.cmd == "generer":
        print(f"{generer(a.classeur, a.sortie, a.simule)} propositions écrites dans {a.sortie}")
    else:
        for dim, v in fiabilite(a.classeur).items():
            print(f"{dim} : alpha ordinal {v['alpha_ordinal']}, alpha présence {v['alpha_presence']} ({v['paires']} paires)")


if __name__ == "__main__":
    main()
