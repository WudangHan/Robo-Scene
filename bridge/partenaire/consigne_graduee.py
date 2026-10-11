"""O-01 / O-02 — Consigne graduée, du plus ouvert au plus précis, consignée comme variable.

Le cahier des fonctions (§4) rapporte l'observation de Kang et Lee : des scripts générés trop précis élargissent
la créativité des acteurs tout en restreignant leur liberté d'interprétation (Kang et Lee, ISEA 2025). (Inférence)
Le répétiteur et le moteur de variations proposent donc quatre registres de consigne ; le registre employé est
écrit dans le journal de répétition et dans la trace de consigne (champ « precision », 1 à 4), ce qui permet
à l'analyse (Q-01, par_precision_consigne) de comparer les registres plutôt que de présumer leur effet.

1. ouverte      — une piste, sans émotion nommée (« cherchez ce que la réplique cache ») ;
2. orientée     — une famille d'émotion, sans intensité ni qualité ;
3. précise      — émotion, intensité et qualités d'effort dominantes ;
4. prescriptive — variation complète : prosodie, effort et geste, à reproduire.
"""
from __future__ import annotations

from typing import Any

NIVEAUX = {1: "ouverte", 2: "orientée", 3: "précise", 4: "prescriptive"}
POLES = {"poids": ("léger", "fort"), "temps": ("soutenu", "soudain"), "espace": ("indirect", "direct"),
         "flux": ("libre", "contenu")}


def niveau(v: Any) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = 4
    return min(4, max(1, n))


def graduer(variation: dict[str, Any], description: dict[str, Any], precision: Any) -> dict[str, Any]:
    """Ce que voit l'interprète au registre demandé (la variation complète reste au journal)."""
    n = niveau(precision)
    emo, inten = variation.get("emotion", "neutre"), variation.get("intensite", 5)
    effort = description.get("effort", {})
    dominants = sorted(effort.items(), key=lambda kv: -abs(kv[1]))[:2]
    qualites = [POLES[a][1 if x > 0 else 0] for a, x in dominants if abs(x) >= 0.3]
    if n == 1:
        texte = "Consigne ouverte : cherchez ce que la réplique cache, et laissez la situation décider du ton."
    elif n == 2:
        texte = f"Consigne orientée : du côté de « {emo} »." + (f" Mélange possible : {variation['melange']}."
                                                                if variation.get("melange") else "")
    elif n == 3:
        texte = (f"Consigne précise : « {emo} », intensité {inten}/10"
                 + (f", qualités {' et '.join(qualites)}" if qualites else "") + ".")
    else:
        texte = (f"Consigne prescriptive : « {variation.get('etiquette') or emo} », intensité {inten}/10, style "
                 f"{variation.get('style', '')} ; effort " + ", ".join(f"{a} {x:+.1f}" for a, x in effort.items())
                 + " ; prosodie " + ", ".join(f"{k} {x:+.2f}" for k, x in description.get("prosodie", {}).items()) + ".")
    return {"precision": n, "registre": NIVEAUX[n], "texte": texte,
            "emotion": emo if n >= 2 else None, "intensite": inten if n >= 3 else None,
            "qualites": qualites if n >= 3 else [], "complete": n == 4}
