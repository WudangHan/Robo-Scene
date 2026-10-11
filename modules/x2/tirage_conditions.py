"""Tirage au sort des conditions des présentations X.2 (plan d'analyse A.2, section 2.2).

    python tirage_conditions.py --representations 8 --graine 20271015 --sortie tirage_X2.csv
    python tirage_conditions.py --representations 16 --sans-support --graine 20271015 --sortie tirage_X2.csv

Plan 2 × 2 (support × provenance) : blocs de quatre représentations, une par case, ordre tiré au hasard dans
chaque bloc. Sans le facteur « support » (robot indisponible, décision D08) : blocs de deux.
La graine et l'empreinte SHA-256 du fichier produit sont publiées avec le préenregistrement AVANT la première
représentation : tout tirage ultérieur se vérifie en rejouant la même commande.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import random

CASES_2X2 = [("robot", "affichee"), ("robot", "non_affichee"), ("voix_surtitres", "affichee"), ("voix_surtitres", "non_affichee")]
CASES_1 = [("robot_ou_voix_selon_disponibilite", "affichee"), ("robot_ou_voix_selon_disponibilite", "non_affichee")]


def tirer(n: int, graine: int, sans_support: bool = False) -> list[dict]:
    cases = CASES_1 if sans_support else CASES_2X2
    if n % len(cases):
        raise ValueError(f"Le nombre de représentations doit être un multiple de {len(cases)}.")
    rng = random.Random(graine)
    lignes = []
    for b in range(n // len(cases)):
        bloc = cases[:]
        rng.shuffle(bloc)
        for support, provenance in bloc:
            lignes.append({"id_representation": f"X2-{len(lignes) + 1:02d}", "bloc": b + 1,
                           "cond_support": support, "cond_provenance": provenance})
    return lignes


def en_csv(lignes: list[dict]) -> str:
    f = io.StringIO()
    w = csv.DictWriter(f, fieldnames=list(lignes[0]), delimiter=";", lineterminator="\n")
    w.writeheader(); w.writerows(lignes)
    return f.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Tirage au sort des conditions X.2")
    ap.add_argument("--representations", type=int, required=True)
    ap.add_argument("--graine", type=int, required=True)
    ap.add_argument("--sans-support", action="store_true")
    ap.add_argument("--sortie", default="tirage_X2.csv")
    a = ap.parse_args(argv)
    texte = en_csv(tirer(a.representations, a.graine, a.sans_support))
    open(a.sortie, "w", encoding="utf-8").write(texte)
    print(texte)
    print("SHA-256 :", hashlib.sha256(texte.encode("utf-8")).hexdigest())


if __name__ == "__main__":
    main()
