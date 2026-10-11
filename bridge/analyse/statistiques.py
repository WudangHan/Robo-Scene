"""Q-03 — Tests de H1 à H4 selon le plan d'analyse statistique A.2 v1.0 (préenregistrement, 5 oct. 2026).

Règles reprises du plan A.2 (§3, §5, §7, §8) :
* scores : engagement (SC_NE) si au moins 10 des 12 énoncés ; agentivité perçue (SC_AG) si au moins 5 des 6,
  AG_5 inversé (8 − x sur l'échelle 1–7) ; aucune imputation ;
* exclusions : moins de 18 ans (jamais enregistré, voir S-05) ou présence incomplète ; représentations
  interrompues ou modifiées exclues de l'analyse principale ; aucune exclusion sur la base des réponses ;
* H4a : différence d'agentivité perçue entre conditions de provenance, bilatérale ;
  H4b : non-infériorité de l'engagement, borne −0,4 écart-type ; H4 soutenue seulement si H4a ET H4b ;
* H2 : agentivité perçue, robot > texte, unilatérale (si le facteur « support » existe) ;
* analyse au niveau des représentations (test t sur les moyennes par représentation) qui double le modèle
  mixte ; le modèle mixte de référence (lme4 + pbkrtest, Kenward-Roger) et la sensibilité ordinale
  (ordinal::clmm) sont dans le script R joint, à exécuter par le chercheur ;
* sensibilité « vérification de manipulation » restreinte aux réponses cohérentes avec la condition ;
* H1 et H3 (artistes, exploratoires) : corrélation de rang de Spearman, intervalle par rééchantillonnage,
  et proportion d'artistes dont la déclaration excède la mesure en rangs centiles.

(Inférence) Choix d'exécution que le plan ne fixe pas et que la plateforme déclare : test t de Welch au
niveau des représentations ; écart-type de référence de H4b = écart-type individuel de SC_NE sur l'ensemble
des répondants retenus ; règle de cohérence de la manipulation (affichée ↔ MC_savait « oui » ou « en_partie » ;
non affichée ↔ « non ») ; énoncé B7 de I-6 retenu comme évaluation esthétique pour H3.
"""
from __future__ import annotations

import csv
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev
from typing import Any

ALPHA = 0.05
BORNE_NI = 0.4
AG = [f"AG_{i}" for i in range(1, 7)]
ES = ["ES_1", "ES_2", "ES_3"]


def lire_csv(fichiers: list[Path]) -> list[dict[str, str]]:
    lignes = []
    for f in fichiers:
        with Path(f).open(encoding="utf-8") as o:
            lignes += list(csv.DictReader(o, delimiter=";"))
    return lignes


def _num(v: Any) -> float | None:
    try:
        return None if v in (None, "", "NA") else float(v)
    except ValueError:
        return None


def _score(valeurs: list[float | None], minimum: int) -> float | None:
    v = [x for x in valeurs if x is not None]
    return round(mean(v), 4) if len(v) >= minimum else None


def scores_I7(lignes: list[dict[str, str]], inverses_ne: set[str] | None = None) -> list[dict[str, Any]]:
    """Ajoute SC_NE, SC_AG, SC_ES et l'indicateur d'exclusion à chaque réponse."""
    sortie = []
    for l in lignes:
        ne_ids = sorted(k for k in l if k.startswith("NE_"))
        ne = [(8 - x) if (x is not None and k in (inverses_ne or set())) else x
              for k in ne_ids for x in [_num(l.get(k))]]
        ag = [(8 - x) if (x is not None and k == "AG_5") else x for k in AG for x in [_num(l.get(k))]]
        es = [_num(l.get(k)) for k in ES]
        r = {**l, "SC_NE": _score(ne, 10) if len(ne_ids) == 12 else None, "SC_AG": _score(ag, 5),
             "SC_ES": _score(es, 3)}
        r["exclue"] = "presence_incomplete" if str(l.get("presence_complete", "")) == "0" else ""
        sortie.append(r)
    return sortie


def coherente(l: dict[str, Any]) -> bool:
    s, p = l.get("MC_savait"), l.get("cond_provenance")
    return (p == "affichee" and s in ("oui", "en_partie")) or (p == "non_affichee" and s == "non")


def par_representation(rows: list[dict[str, Any]], var: str) -> list[dict[str, Any]]:
    g: dict[str, list] = defaultdict(list)
    cond: dict[str, tuple[str, str]] = {}
    for r in rows:
        if r[var] is not None:
            g[r["id_representation"]].append(r[var])
            cond[r["id_representation"]] = (r.get("cond_provenance", ""), r.get("cond_support", ""))
    return [{"id_representation": k, "n": len(v), "moyenne": mean(v), "cond_provenance": cond[k][0],
             "cond_support": cond[k][1]} for k, v in sorted(g.items())]


def _welch(a: list[float], b: list[float], alternative: str = "two-sided", decalage: float = 0.0) -> dict[str, Any]:
    from scipy import stats
    if len(a) < 2 or len(b) < 2:
        return {"calculable": False, "motif": f"au moins deux représentations par condition (a={len(a)}, b={len(b)})"}
    r = stats.ttest_ind([x + decalage for x in a], b, equal_var=False, alternative=alternative)
    return {"calculable": True, "t": round(float(r.statistic), 4), "p": round(float(r.pvalue), 5),
            "ddl": round(float(getattr(r, "df", float("nan"))), 2), "moyenne_a": round(mean(a), 4),
            "moyenne_b": round(mean(b), 4), "difference": round(mean(a) - mean(b), 4),
            "representations_a": len(a), "representations_b": len(b)}


def _mixte(rows: list[dict[str, Any]], var: str) -> dict[str, Any]:
    """Complément Python (statsmodels, REML, sans Kenward-Roger) : la référence reste le script R."""
    try:
        import pandas as pd
        import statsmodels.formula.api as smf
    except ImportError:
        return {"calculable": False, "motif": "statsmodels ou pandas absent"}
    d = pd.DataFrame([{"y": r[var], "rep": r["id_representation"],
                       "prov": 0.5 if r.get("cond_provenance") == "affichee" else -0.5,
                       "supp": 0.5 if r.get("cond_support") == "robot" else -0.5} for r in rows if r[var] is not None])
    if d["rep"].nunique() < 3 or len(d) < 6:
        return {"calculable": False, "motif": "trop peu de représentations"}
    formule = "y ~ prov * supp" if d["supp"].nunique() > 1 else "y ~ prov"
    import warnings
    try:
        with warnings.catch_warnings(record=True) as avis:
            warnings.simplefilter("always")
            m = smf.mixedlm(formule, d, groups=d["rep"]).fit(reml=True)
        return {"calculable": True, "formule": formule + " + (1|representation)",
                "avertissements": sorted({str(a.message)[:160] for a in avis}),
                "variance_representation": round(float(m.cov_re.iloc[0, 0]), 6),
                "coefficients": {k: round(float(v), 4) for k, v in m.params.items()},
                "erreurs_types": {k: round(float(v), 4) for k, v in m.bse.items()},
                "note": "Approximation (statsmodels MixedLM, ddl asymptotiques) ; résultat de référence : script R."}
    except Exception as exc:  # noqa: BLE001 — convergence
        return {"calculable": False, "motif": f"modèle non estimé : {exc}"}


def tests_X2(rows: list[dict[str, Any]], exclues: set[str] | None = None, restreindre_coherentes: bool = False) -> dict[str, Any]:
    exclues = exclues or set()
    base = [r for r in rows if not r["exclue"] and r["id_representation"] not in exclues]
    if restreindre_coherentes:
        base = [r for r in base if coherente(r)]
    ag = par_representation(base, "SC_AG")
    ne = par_representation(base, "SC_NE")

    def moy(lst, cle, val):
        return [x["moyenne"] for x in lst if x[cle] == val]

    h4a = _welch(moy(ag, "cond_provenance", "affichee"), moy(ag, "cond_provenance", "non_affichee"))
    ne_ind = [r["SC_NE"] for r in base if r["SC_NE"] is not None]
    sd = stdev(ne_ind) if len(ne_ind) > 1 else None
    if sd:
        delta = BORNE_NI * sd
        h4b = _welch(moy(ne, "cond_provenance", "affichee"), moy(ne, "cond_provenance", "non_affichee"),
                     alternative="greater", decalage=delta)
        h4b.update(borne=round(-delta, 4), ecart_type_reference=round(sd, 4),
                   hypothese_nulle="différence (affichée − non affichée) ≤ −0,4 écart-type")
    else:
        h4b = {"calculable": False, "motif": "écart-type de SC_NE incalculable"}
    supports = {r.get("cond_support") for r in base}
    if {"robot", "voix_surtitres"} <= supports:
        h2 = _welch(moy(ag, "cond_support", "robot"), moy(ag, "cond_support", "voix_surtitres"), alternative="greater")
    else:
        h2 = {"calculable": False, "motif": "facteur « support » absent (D08) : H2 non testée"}
    ok = lambda t: t.get("calculable") and t["p"] < ALPHA  # noqa: E731
    return {
        "n_reponses": len(rows), "n_retenues": len(base), "representations_exclues": sorted(exclues),
        "restreint_coherentes": restreindre_coherentes,
        "H4a": {**h4a, "soutenue": bool(ok(h4a))}, "H4b": {**h4b, "soutenue": bool(ok(h4b))},
        "H4": {"soutenue": bool(ok(h4a) and ok(h4b)), "regle": "H4a ET H4b au seuil de 0,05 (A.2 §3)"},
        "H2": {**h2, "soutenue": bool(ok(h2))},
        "moyennes_par_representation": {"SC_AG": ag, "SC_NE": ne},
        "mixte_python": {"SC_AG": _mixte(base, "SC_AG"), "SC_NE": _mixte(base, "SC_NE")},
    }


# ── Volet artistes (H1, H3) ─────────────────────────────────
def _rangs_centiles(xs: list[float]) -> list[float]:
    from scipy.stats import rankdata
    r = rankdata(xs)
    return [float((x - 0.5) / len(xs)) for x in r]


def spearman_bootstrap(x: list[float], y: list[float], b: int = 10_000, graine: int = 20261005) -> dict[str, Any]:
    from scipy.stats import spearmanr
    n = len(x)
    if n < 4:
        return {"calculable": False, "n": n, "motif": "au moins quatre artistes"}
    rho = float(spearmanr(x, y).statistic)
    rng = random.Random(graine)
    bs = []
    for _ in range(b):
        idx = [rng.randrange(n) for _ in range(n)]
        xs, ys = [x[i] for i in idx], [y[i] for i in idx]
        if len(set(xs)) > 1 and len(set(ys)) > 1:
            bs.append(float(spearmanr(xs, ys).statistic))
    bs.sort()
    lo, hi = (bs[int(0.025 * len(bs))], bs[int(0.975 * len(bs)) - 1]) if bs else (None, None)
    return {"calculable": True, "n": n, "rho": round(rho, 4), "ic95_bootstrap": [round(lo, 4), round(hi, 4)] if bs else None,
            "reechantillons": len(bs), "graine": graine, "statut": "exploratoire (A.2 §8)"}


def tests_artistes(i6: list[dict[str, str]], operatoire_par_personne: dict[str, dict[str, Any]]) -> dict[str, Any]:
    decl: dict[str, list] = defaultdict(list)
    est: dict[str, list] = defaultdict(list)
    for l in i6:
        p = l.get("pseudonyme")
        if not p:
            continue
        if _num(l.get("B8")) is not None:
            decl[p].append(_num(l["B8"]))
        if _num(l.get("B7")) is not None:
            est[p].append(_num(l["B7"]))
    ecarts = {p: v["ecart_moyen"] for p, v in operatoire_par_personne.items() if v.get("ecart_moyen") is not None}
    h1_p = sorted(set(decl) & set(ecarts))
    h1 = spearman_bootstrap([mean(decl[p]) for p in h1_p], [ecarts[p] for p in h1_p])
    if len(h1_p) >= 2:
        rd = _rangs_centiles([mean(decl[p]) for p in h1_p])
        rm = _rangs_centiles([ecarts[p] for p in h1_p])
        exc = sum(1 for a, b in zip(rd, rm) if a > b)
        h1["declaration_excede_mesure"] = {"n": exc, "proportion": round(exc / len(h1_p), 4)}
    h3_p = sorted(set(est) & set(ecarts))
    h3 = spearman_bootstrap([ecarts[p] for p in h3_p], [mean(est[p]) for p in h3_p])
    return {"H1": {**h1, "mesures": "I-6 B8 (déclarée) × écart moyen I-5 (opératoire)"},
            "H3": {**h3, "mesures": "écart moyen I-5 × I-6 B7 (Inférence : B7 comme évaluation esthétique)"}}


# ── Données P3 (A.2 §5.3) ───────────────────────────────────
def tables_p3(exports: list[dict[str, Any]]) -> dict[str, Any]:
    """Tables de contingence descriptives (émotion × étiquette de provenance), par condition ; cellules
    masquées exclues ; aucune statistique inférentielle."""
    tables: dict[str, dict[str, dict[str, int]]] = {}
    masquees = 0
    for e in exports:
        cond = "affichee" if e.get("condition_provenance_affichee") else "non_affichee"
        t = tables.setdefault(cond, {})
        for c in e.get("cellules", []):
            if c.get("masquee"):
                masquees += 1
                continue
            ligne = t.setdefault(c["provenance"], {})
            for k, v in c.get("emotions", {}).items():
                ligne[k] = ligne.get(k, 0) + v
    return {"tables": tables, "cellules_masquees_ignorees": masquees, "statut": "descriptif (A.2 §5.3)"}
