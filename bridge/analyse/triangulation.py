"""Q-02 — Croisement des agentivités déclarée, perçue et opératoire ; tableau des écarts (R.4 §5).

Critère d'acceptation du cahier : un tableau par atelier et par représentation. Toutes les mesures sont
ramenées sur [0, 1] pour que les écarts soient lisibles ; ce ramènement est une convention de présentation
(Inférence), non une équivalence psychométrique : un écart entre deux mesures de nature différente se lit
comme un signal à interpréter avec les entretiens (A.1), jamais comme une différence mesurée.

* Atelier : opératoire = part du système dans le texte final et écart moyen (Q-01) ; déclarée = I-6 B2
  (« les idées importantes venaient du système », (x − 1)/6) et indice des entretiens (Q-05).
* Représentation : perçue = MC_part_systeme / 100 et SC_AG ramené ((x − 1)/6) ; opératoire de scène = part des
  répliques jouées étiquetées « systeme » (+ ½ « mixte ») dans les traces SCENE des séances de la représentation.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


def _n(v):
    try:
        return None if v in (None, "", "NA") else float(v)
    except ValueError:
        return None


def _moy(xs):
    xs = [x for x in xs if x is not None]
    return round(mean(xs), 4) if xs else None


def _ecart(a, b):
    return None if a is None or b is None else round(a - b, 4)


def par_atelier(operatoire: dict[str, Any], i6: list[dict[str, str]],
                entretiens: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Une ligne par séance d'atelier (seance) ; déclarations moyennées sur les personnes de la séance."""
    lignes = []
    for s, ind in operatoire["par_seance"].items():
        personnes = {u["personne"] for u in operatoire["unites"] if u["seance"] == s and u["personne"]}
        b2 = [(_n(l.get("B2")) - 1) / 6 for l in i6 if l.get("pseudonyme") in personnes and _n(l.get("B2")) is not None]
        ent = [entretiens[p]["indice_declare_systeme"] for p in personnes if p in entretiens]
        op = ind.get("part_systeme_texte_final")
        decl = _moy(b2)
        lignes.append({"unite": s, "type": "atelier", "personnes": len(personnes),
                       "operatoire_part_systeme": op, "operatoire_ecart_moyen": ind.get("ecart_moyen"),
                       "declaree_I6_B2": decl, "declaree_entretiens": _moy(ent),
                       "ecart_declaree_moins_operatoire": _ecart(decl, op),
                       "ecart_entretiens_moins_operatoire": _ecart(_moy(ent), op)})
    return lignes


def operatoire_scene(evs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    par: dict[str, Counter] = defaultdict(Counter)
    for e in evs:
        if e["module"] == "SCENE" and e["operation"] == "attribution" and e["donnees"].get("jouee"):
            par[e["seance"]][e["donnees"].get("etiquette_declaree") or e["donnees"].get("etiquette")] += 1
    out = {}
    for s, c in par.items():
        n = sum(c.values())
        out[s] = {"repliques": n, "etiquettes": dict(c),
                  "part_systeme": round((c["systeme"] + 0.5 * c["mixte"]) / n, 4) if n else None}
    return out


def par_representation(i7_scores: list[dict[str, Any]], scene: dict[str, dict[str, Any]],
                       seances_par_representation: dict[str, list[str]]) -> list[dict[str, Any]]:
    g: dict[str, list] = defaultdict(list)
    for r in i7_scores:
        if not r.get("exclue"):
            g[r["id_representation"]].append(r)
    lignes = []
    for rep, rs in sorted(g.items()):
        mc = _moy([_n(r.get("MC_part_systeme")) / 100 for r in rs if _n(r.get("MC_part_systeme")) is not None])
        ag = _moy([(r["SC_AG"] - 1) / 6 for r in rs if r.get("SC_AG") is not None])
        sc = [scene[s] for s in seances_par_representation.get(rep, []) if s in scene]
        n = sum(x["repliques"] for x in sc)
        op = round(sum((x["part_systeme"] or 0) * x["repliques"] for x in sc) / n, 4) if n else None
        lignes.append({"unite": rep, "type": "representation", "reponses": len(rs),
                       "cond_provenance": rs[0].get("cond_provenance"), "cond_support": rs[0].get("cond_support"),
                       "percue_MC_part_systeme": mc, "percue_SC_AG_0_1": ag, "operatoire_scene_part_systeme": op,
                       "ecart_percue_moins_operatoire": _ecart(mc, op)})
    return lignes


def ecrire(lignes: list[dict[str, Any]], chemin: Path) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    cles = list(dict.fromkeys(k for l in lignes for k in l))
    with chemin.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cles, delimiter=";")
        w.writeheader()
        w.writerows(lignes)
    return chemin
