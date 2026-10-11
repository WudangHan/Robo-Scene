"""Analyse et réponse aux questions de recherche (cahier des fonctions §3.5 : Q-01 à Q-05) et O-02.

`lancer(ctl, …)` produit un dossier daté donnees/analyse/AAAA-MM-JJ_HHMM/ qui se suffit à lui-même (Q-04) :
* données d'entrée dérivées (scores_I7.csv, unites_operatoires.csv, triangulation_*.csv, tables P3) ;
* résultats (resultats.json, rapport.md) ;
* script R de l'analyse principale (A2_analyse_principale.R) et ses paramètres (parametres.csv) ;
* manifeste.json : empreinte SHA-256 de chaque fichier d'entrée et de sortie, version du code (commit Git),
  versions de Python et des bibliothèques, paramètres et commande de régénération.
Un tiers régénère les tableaux avec : python -m bridge.analyse --donnees <dossier> [--exclure X2-03 …].
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import _modules
from . import entretiens, operatoire, statistiques, triangulation

ICI = Path(__file__).parent


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _version_code() -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(_modules.RACINE), "rev-parse", "HEAD"], capture_output=True, text=True,
                           timeout=10)
        etat = subprocess.run(["git", "-C", str(_modules.RACINE), "status", "--porcelain", "bridge"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
        return r.stdout.strip() + ("+modifications" if etat else "") if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _versions() -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version
    v = {"python": platform.python_version()}
    for p in ("scipy", "numpy", "statsmodels", "pandas", "pyyaml"):
        try:
            v[p] = version(p)
        except PackageNotFoundError:
            pass
    return v


def _ecrire_csv(lignes: list[dict[str, Any]], chemin: Path) -> Path:
    cles = list(dict.fromkeys(k for l in lignes for k in l)) or ["vide"]
    with chemin.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cles, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows([{k: ("NA" if v is None else v) for k, v in l.items()} for l in lignes])
    return chemin


def lancer(donnees: Path, racine_corpus: Path, *, exclues: list[str] | None = None,
           seances_par_representation: dict[str, list[str]] | None = None, codeur: str | None = None,
           exclure_reconstituees: bool = False, sortie: Path | None = None) -> dict[str, Any]:
    donnees, racine_corpus = Path(donnees), Path(racine_corpus)
    out = sortie or donnees / "analyse" / datetime.now().strftime("%Y-%m-%d_%H%M")
    out.mkdir(parents=True, exist_ok=True)
    entrees: list[Path] = []

    # Q-01
    traces = sorted(racine_corpus.glob("traces/*/*.jsonl"))
    entrees += traces
    evs = operatoire.charger_traces(racine_corpus)
    op = operatoire.agentivite_operatoire(evs, exclure_reconstituees=exclure_reconstituees)
    _ecrire_csv(op["unites"], out / "unites_operatoires.csv")

    # Q-03 (public X.2) — données de recherche seulement : les essais (sous-dossier essais/) sont exclus
    f_i7 = sorted((donnees / "questionnaires").glob("I-7_*.csv"))
    f_i6 = sorted((donnees / "questionnaires").glob("I-6_*.csv"))
    entrees += f_i7 + f_i6
    i7 = statistiques.scores_I7(statistiques.lire_csv(f_i7))
    i6 = statistiques.lire_csv(f_i6)
    _ecrire_csv(i7, out / "scores_I7.csv")
    x2 = statistiques.tests_X2(i7, set(exclues or []))
    x2_sens = statistiques.tests_X2(i7, set(exclues or []), restreindre_coherentes=True)
    art = statistiques.tests_artistes(i6, op["par_personne"])
    f_p3 = sorted((donnees / "p3").glob("*.json"))
    entrees += f_p3
    p3 = statistiques.tables_p3([json.loads(p.read_text(encoding="utf-8")) for p in f_p3])

    # Q-05 et Q-02
    decl: dict[str, Any] = {}
    if codeur:
        c = entretiens.Codage(donnees / "analyse", codeur)
        if c.fichier.exists():
            entrees.append(c.fichier)
        decl = entretiens.agentivite_declaree(c.lire())
    tri_a = triangulation.par_atelier(op, i6, decl)
    tri_r = triangulation.par_representation(i7, triangulation.operatoire_scene(evs), seances_par_representation or {})
    _ecrire_csv(tri_a, out / "triangulation_ateliers.csv")
    _ecrire_csv(tri_r, out / "triangulation_representations.csv")

    # Script R et paramètres
    shutil.copy2(ICI / "A2_analyse_principale.R", out / "A2_analyse_principale.R")
    with (out / "parametres.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["representations_exclues", "borne_non_inferiorite_et", "alpha"])
        w.writerow(["|".join(exclues or []), statistiques.BORNE_NI, statistiques.ALPHA])

    resultats = {"date": datetime.now().astimezone().isoformat(timespec="seconds"),
                 "Q01_operatoire": {k: v for k, v in op.items() if k != "unites"},
                 "Q03_X2": x2, "Q03_X2_sensibilite_manipulation": x2_sens, "Q03_artistes": art,
                 "Q03_P3": p3, "Q05_declaree": decl,
                 "Q02_triangulation": {"ateliers": tri_a, "representations": tri_r}}
    (out / "resultats.json").write_text(json.dumps(resultats, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out / "rapport.md").write_text(rapport(resultats), encoding="utf-8")

    sorties = sorted(p for p in out.iterdir() if p.is_file() and p.name != "manifeste.json")
    manifeste = {
        "fonction": "Q-04", "date": resultats["date"], "version_code": _version_code(), "versions": _versions(),
        "parametres": {"exclues": exclues or [], "seances_par_representation": seances_par_representation or {},
                       "codeur": codeur, "exclure_reconstituees": exclure_reconstituees,
                       "borne_non_inferiorite": statistiques.BORNE_NI, "alpha": statistiques.ALPHA},
        "commande": "python -m bridge.analyse --donnees <dossier donnees> --corpus <dossier corpus>"
                    + "".join(f" --exclure {x}" for x in exclues or []) + (f" --codeur {codeur}" if codeur else ""),
        "entrees": [{"fichier": str(p), "sha256": _sha(p)} for p in entrees],
        "sorties": [{"fichier": p.name, "sha256": _sha(p)} for p in sorties],
        "note": "Les essais techniques (sous-dossiers essais/) ne sont jamais lus par l'analyse.",
    }
    (out / "manifeste.json").write_text(json.dumps(manifeste, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"dossier": str(out), "resultats": resultats, "manifeste": manifeste}


def _f(v, n=3):
    return "—" if v is None else (f"{v:.{n}f}" if isinstance(v, float) else str(v))


def rapport(r: dict[str, Any]) -> str:
    x2, art, op = r["Q03_X2"], r["Q03_artistes"], r["Q01_operatoire"]["ensemble"]

    def test(nom, t):
        if not t.get("calculable"):
            return f"| {nom} | non calculable : {t.get('motif', '')} | | |"
        return f"| {nom} | {_f(t.get('difference'))} | t = {_f(t['t'])}, ddl = {_f(t['ddl'], 1)}, p = {_f(t['p'], 4)} | " \
               f"{'oui' if t.get('soutenue') else 'non'} |"

    l = [f"# Analyse — {r['date'][:16]}", "",
         "*Rapport produit par la plateforme (Q-01 à Q-05). L'analyse confirmatoire de référence est le modèle mixte "
         "du script R joint (A.2 §5.1) ; les tests ci-dessous sont l'analyse au niveau des représentations qui le double.*", "",
         "## Q-01 — Agentivité opératoire (ensemble)", "",
         f"- Propositions : {op['propositions']} ; retenues : {op['retenues']} (taux {_f(op['taux_retention'])}).",
         f"- Écart moyen : {_f(op['ecart_moyen'])} ; conservation moyenne : {_f(op['conservation_moyenne'])} ; "
         f"transformations reconstituées : {op['reconstituees']}.",
         f"- (Inférence) Part du système dans le texte final : {_f(op['part_systeme_texte_final'])}.", "",
         "## Q-03 — Présentations X.2", "",
         f"Réponses : {x2['n_reponses']} ; retenues : {x2['n_retenues']} ; représentations exclues : "
         f"{', '.join(x2['representations_exclues']) or 'aucune'}.", "",
         "| Hypothèse | Différence | Test | Soutenue |", "|---|---|---|---|",
         test("H4a — agentivité perçue (bilatérale)", x2["H4a"]),
         test("H4b — engagement, non-infériorité (−0,4 ET)", x2["H4b"]),
         test("H2 — robot > texte (unilatérale)", x2["H2"]), "",
         f"**H4 soutenue : {'oui' if x2['H4']['soutenue'] else 'non'}** (H4a et H4b exigées ensemble).", "",
         "## Q-03 — Volet artistes (exploratoire)", ""]
    for h in ("H1", "H3"):
        t = art[h]
        l.append(f"- {h} ({t['mesures']}) : " + (f"ρ = {_f(t['rho'])}, IC 95 % bootstrap {t['ic95_bootstrap']}, n = {t['n']}"
                                                if t.get("calculable") else f"non calculable ({t.get('motif')})"))
    l += ["", "## Q-02 — Triangulation", "",
          f"- Ateliers : {len(r['Q02_triangulation']['ateliers'])} ligne(s) ; représentations : "
          f"{len(r['Q02_triangulation']['representations'])} ligne(s) (voir les CSV).", "",
          "## Fichiers", "", "Voir manifeste.json (empreintes SHA-256, versions, commande de régénération).", ""]
    return "\n".join(l)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Régénère l'analyse (Q-01 à Q-05) à partir des données")
    ap.add_argument("--donnees", default=str(_modules.RACINE / "donnees"))
    ap.add_argument("--corpus", default=str(_modules.RACINE / "corpus"))
    ap.add_argument("--exclure", action="append", default=[])
    ap.add_argument("--codeur")
    ap.add_argument("--sortie")
    a = ap.parse_args(argv)
    r = lancer(Path(a.donnees), Path(a.corpus), exclues=a.exclure, codeur=a.codeur,
               sortie=Path(a.sortie) if a.sortie else None)
    print(r["dossier"])


if __name__ == "__main__":
    main(sys.argv[1:])
