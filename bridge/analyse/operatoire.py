"""Q-01 — Agentivité opératoire calculée à partir des traces des cinq opérations (R.4 §5 et §8 ; QR1).

R.4 nomme les indicateurs : « taux de conservation et de transformation des propositions ». Le module les
calcule tels quels, par séance et par personne, et y ajoute un indice synthétique :

* taux de rétention : propositions retenues / propositions générées (opération 3) ;
* écart moyen : distance d'édition normalisée de I-5 entre proposition retenue et version transformée (op. 4) ;
* conservation moyenne : part des mots de la proposition qui subsistent, dans l'ordre, dans la version ;
* (Inférence) part du système dans le texte final : mots de propositions conservés / mots du texte final,
  l'écriture directe (« ecriture_directe ») comptant pour des mots entièrement humains. C'est le choix
  d'opérationnalisation de la plateforme ; il est déclaré ici et doit être validé par le chercheur avant
  tout usage confirmatoire (il n'est pas fixé par le plan A.2, qui utilise l'écart moyen pour H1 et H3).

Les transformations « reconstituées » (N-07) sont comptées et signalées à part ; l'analyse peut les exclure.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from ..trace.ecart import mesurer

MOTS = re.compile(r"[\wÀ-ÿœæ'’-]+")


def n_mots(t: str | None) -> int:
    return len(MOTS.findall(t or ""))


def charger_traces(racine_corpus: str | Path, seances: Iterable[str] | None = None) -> list[dict[str, Any]]:
    """Lit corpus/traces/AAAAMMJJ/*.jsonl (toutes les séances, ou celles demandées)."""
    voulu = set(seances) if seances else None
    evs = []
    for f in sorted(Path(racine_corpus).glob("traces/*/*.jsonl")):
        if voulu and f.stem not in voulu:
            continue
        evs += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    return evs


def _moy(xs: list[float]) -> float | None:
    return round(mean(xs), 4) if xs else None


def _cycles(evs: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, list]]:
    par: dict[tuple[str, str], dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for e in evs:
        if e.get("cycle"):
            par[(e["seance"], e["cycle"])][e["operation"]].append(e)
    return par


def unites(evs: list[dict[str, Any]], *, exclure_reconstituees: bool = False) -> list[dict[str, Any]]:
    """Une ligne par proposition générée : décision, version, écart, conservation, attribution, personne."""
    lignes = []
    for (seance, cyc), ops in _cycles(evs).items():
        gens = ops.get("generation", [])
        consigne = (ops.get("consigne") or [{}])[0]
        for gi, g in enumerate(gens, 1):
            d = g["donnees"]
            for pi, prop in enumerate(d.get("propositions", []), 1):
                cle = (gi, pi)

                def lie(op):
                    return [x for x in ops.get(op, []) if (x["donnees"].get("generation"), x["donnees"].get("proposition")) == cle]

                sel = lie("selection")
                tr = [x for x in lie("transformation") if not (exclure_reconstituees and x.get("reconstitue"))]
                at = lie("attribution")
                dec = sel[-1]["donnees"].get("decision") if sel else None
                t = tr[-1] if tr else None
                td = dict(t["donnees"]) if t else {}
                if t and td.get("ecart") is None and td.get("version"):
                    td.update(mesurer(prop, td["version"]))       # saisie « de tête » avec version : mesurée ici
                lignes.append({
                    "seance": seance, "cycle": cyc, "module": g["module"], "generation": gi, "proposition": pi,
                    "systeme": d.get("systeme"), "version_modele": d.get("version_modele"),
                    "type_texte": d.get("type_texte"),
                    "personne": (consigne.get("agent") or {}).get("id") or (sel[-1]["agent"]["id"] if sel else None),
                    "precision_consigne": (consigne.get("donnees") or {}).get("precision"),
                    "decision": dec, "mots_proposition": n_mots(prop),
                    "transformee": t is not None, "reconstituee": bool(t and t.get("reconstitue")),
                    "ecart": td.get("ecart"), "conservation": td.get("conservation"),
                    "mots_version": n_mots(td.get("version")) if t else None,
                    "etiquette": at[-1]["donnees"].get("etiquette") if at else None,
                })
    return lignes


def indicateurs(lignes: list[dict[str, Any]], segments_humains: int = 0) -> dict[str, Any]:
    n = len(lignes)
    dec = Counter(l["decision"] for l in lignes)
    ret = [l for l in lignes if l["decision"] == "retenue"]
    tr = [l for l in ret if l["transformee"] and l["ecart"] is not None]
    mots_sys = sum((l["conservation"] or 0) * l["mots_proposition"] for l in tr)
    mots_fin = sum(l["mots_version"] or 0 for l in tr) + segments_humains
    return {
        "propositions": n, "retenues": dec["retenue"], "rejetees": dec["rejetee"], "redemandees": dec["redemandee"],
        "sans_decision": dec[None], "taux_retention": round(dec["retenue"] / n, 4) if n else None,
        "transformations": len(tr), "reconstituees": sum(1 for l in ret if l["reconstituee"]),
        "ecart_moyen": _moy([float(l["ecart"]) for l in tr]),
        "conservation_moyenne": _moy([float(l["conservation"]) for l in tr if l["conservation"] is not None]),
        "mots_texte_final": mots_fin, "mots_ecriture_directe": segments_humains,
        "part_systeme_texte_final": round(mots_sys / mots_fin, 4) if mots_fin else None,
        "attributions": dict(Counter(l["etiquette"] for l in ret if l["etiquette"])),
    }


def _segments(evs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in evs if e["operation"] == "autre" and e.get("categorie_autre") == "ecriture_directe"]


def agentivite_operatoire(evs: list[dict[str, Any]], *, exclure_reconstituees: bool = False) -> dict[str, Any]:
    """Indicateurs par séance, par personne et pour l'ensemble."""
    lignes = unites(evs, exclure_reconstituees=exclure_reconstituees)
    segs = _segments(evs)

    def mots_segs(filtre) -> int:
        return sum(n_mots(s["donnees"].get("texte")) for s in segs if filtre(s))

    par_seance = {s: indicateurs([l for l in lignes if l["seance"] == s], mots_segs(lambda e, s=s: e["seance"] == s))
                  for s in sorted({l["seance"] for l in lignes} | {e["seance"] for e in segs})}
    personnes = sorted({l["personne"] for l in lignes if l["personne"]} | {s["agent"]["id"] for s in segs})
    par_personne = {p: indicateurs([l for l in lignes if l["personne"] == p],
                                   mots_segs(lambda e, p=p: e["agent"]["id"] == p)) for p in personnes}
    par_precision = {str(k): indicateurs([l for l in lignes if l["precision_consigne"] == k])
                     for k in sorted({l["precision_consigne"] for l in lignes if l["precision_consigne"] is not None})}
    return {"ensemble": indicateurs(lignes, mots_segs(lambda e: True)), "par_seance": par_seance,
            "par_personne": par_personne, "par_precision_consigne": par_precision,
            "exclure_reconstituees": exclure_reconstituees, "unites": lignes,
            "definitions": {
                "taux_retention": "retenues / propositions générées (R.4, opération 3)",
                "ecart_moyen": "moyenne de la distance d'édition normalisée I-5 (R.4, opération 4 ; A.2 §8)",
                "conservation_moyenne": "part des mots de la proposition conservés dans l'ordre (N-04)",
                "part_systeme_texte_final": "(Inférence) mots conservés des propositions / mots du texte final, "
                                            "écriture directe comprise ; indice de la plateforme à valider"}}
