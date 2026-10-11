"""O-09 — Tableau public des indicateurs agrégés, pour le site du projet.

Conditions : seuil d'anonymat de cinq et aucune donnée individuelle (cahier §4 ; principe « anonymat des
publics », P3.2) ; validation humaine avant toute diffusion (G.5). Le flux est donc en deux temps :
1. `preparer()` calcule un brouillon dans donnees/diffusion/ à partir du dernier dossier d'analyse (Q-04) ;
   tout groupe de moins de cinq réponses est retiré, jamais arrondi ni fusionné en silence ;
2. `publier(par)` recopie le brouillon validé dans web/donnees-publiques/tableau-public.json, lu par la page
   web/tableau-public.html (déployable sur le site statique), avec le nom de la personne qui a validé.
Aucun pseudonyme, aucune réponse, aucun identifiant de séance n'entre dans le tableau.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

SEUIL = 5


def _dernier(dossier_analyse: Path) -> Path | None:
    ds = sorted(p for p in dossier_analyse.glob("*/resultats.json"))
    return ds[-1] if ds else None


def preparer(donnees: Path, seuil: int = SEUIL) -> dict[str, Any]:
    f = _dernier(Path(donnees) / "analyse")
    if f is None:
        raise FileNotFoundError("Aucune analyse : lancer d'abord l'analyse (Q-01 à Q-05)")
    r = json.loads(f.read_text(encoding="utf-8"))
    retires = []
    reps = []
    for x in r["Q02_triangulation"]["representations"]:
        if (x.get("reponses") or 0) < seuil:
            retires.append("une représentation sous le seuil")
            continue
        reps.append({k: x.get(k) for k in ("cond_provenance", "cond_support", "reponses", "percue_MC_part_systeme",
                                           "percue_SC_AG_0_1", "operatoire_scene_part_systeme")})
    p3 = {}
    for cond, table in (r.get("Q03_P3", {}).get("tables") or {}).items():
        p3[cond] = {}
        for prov, emo in table.items():
            n = sum(emo.values())
            if n >= seuil:
                p3[cond][prov] = {"n": n, "emotions": {k: v for k, v in emo.items() if v}}
            else:
                retires.append(f"P3 {cond}/{prov} sous le seuil")
    op = r["Q01_operatoire"]["ensemble"]
    t = {
        "titre": "L'IA au service de la création théâtrale — indicateurs agrégés",
        "affiliation": "Recherche indépendante autofinancée — Sylvain Gagné, Ph. D.",
        "genere": datetime.now().astimezone().isoformat(timespec="seconds"), "analyse": f.parent.name,
        "seuil_anonymat": seuil,
        "cocreation": {k: op.get(k) for k in ("propositions", "taux_retention", "ecart_moyen", "conservation_moyenne",
                                              "part_systeme_texte_final")} if (op.get("propositions") or 0) >= seuil else None,
        "representations": reps, "retroaction_p3": p3,
        "hypotheses": {h: {"soutenue": r["Q03_X2"][h].get("soutenue"), "calculable": r["Q03_X2"][h].get("calculable", True)}
                       for h in ("H4a", "H4b", "H2")} | {"H4": {"soutenue": r["Q03_X2"]["H4"]["soutenue"]}},
        "lecture": "Agrégats seulement ; groupes de moins de cinq réponses retirés. Résultats préliminaires tant "
                   "que le rapport final n'est pas déposé.",
        "groupes_retires": len(retires), "valide": None,
    }
    d = Path(donnees) / "diffusion"
    d.mkdir(parents=True, exist_ok=True)
    (d / "tableau-public.brouillon.json").write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    return t


def publier(donnees: Path, racine_web: Path, par: str) -> Path:
    if not par.strip():
        raise ValueError("Validation humaine requise : indiquer qui publie")
    b = Path(donnees) / "diffusion" / "tableau-public.brouillon.json"
    if not b.exists():
        raise FileNotFoundError("Aucun brouillon : préparer d'abord le tableau")
    t = json.loads(b.read_text(encoding="utf-8"))
    t["valide"] = {"par": par, "date": datetime.now().astimezone().isoformat(timespec="seconds")}
    sortie = Path(racine_web) / "donnees-publiques" / "tableau-public.json"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.copy2(sortie, Path(donnees) / "diffusion" / f"{datetime.now():%Y-%m-%d}_tableau-public.json")
    return sortie
