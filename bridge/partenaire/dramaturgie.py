"""Analyse dramaturgique déterministe et vérifiable d'une pièce.

Mesures classiques de la dramaturgie computationnelle : distribution de la
parole, configurations (présence des personnages par scène), réseau de
coprésence au sens de Moretti, tirades, stichomythies, didascalies.
Limite assumée : la présence est déduite de la PRISE DE PAROLE ; un
personnage muet en scène n'est pas compté.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Any


def repliques(piece: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in piece["elements"] if e["type"] == "replique"]


def analyser(piece: dict[str, Any]) -> dict[str, Any]:
    reps = repliques(piece)
    noms = {p["id"]: p["nom"] for p in piece["personnages"]}
    genres = {p["id"]: p.get("genre") for p in piece["personnages"]}
    total_mots = sum(r["mots"] for r in reps) or 1
    scenes = [s["id"] for s in piece["scenes"]]
    par_scene: dict[str, list[dict]] = defaultdict(list)
    for r in reps:
        par_scene[r["scene"]].append(r)

    # Personnages
    stats = {}
    for pid in noms:
        rs = [r for r in reps if r["perso"] == pid]
        if not rs:
            continue
        sc = sorted({r["scene"] for r in rs}, key=scenes.index)
        stats[pid] = {
            "id": pid, "nom": noms[pid], "genre": genres.get(pid),
            "repliques": len(rs), "mots": sum(r["mots"] for r in rs),
            "part_parole": round(sum(r["mots"] for r in rs) / total_mots, 4),
            "scenes": len(sc), "premiere_scene": sc[0], "derniere_scene": sc[-1],
            "plus_longue": max(rs, key=lambda r: r["mots"])["id"],
            "mots_par_replique": round(sum(r["mots"] for r in rs) / len(rs), 1),
            "par_scene": [sum(r["mots"] for r in par_scene[s] if r["perso"] == pid) for s in scenes],
        }
    classement = sorted(stats.values(), key=lambda s: -s["mots"])

    # Configurations et réseau de coprésence (personnages parlant dans une même scène)
    configs = {s: sorted({r["perso"] for r in par_scene[s]}) for s in scenes}
    aretes: Counter = Counter()
    for s, ps in configs.items():
        for a, b in combinations(ps, 2):
            aretes[tuple(sorted((a, b)))] += 1
    degre = Counter()
    for (a, b) in aretes:
        degre[a] += 1
        degre[b] += 1
    n = len(stats)
    densite = round(2 * len(aretes) / (n * (n - 1)), 3) if n > 1 else 0.0

    # Échanges adressés : qui répond à qui (succession de répliques dans une scène)
    echanges: Counter = Counter()
    for s in scenes:
        rs = par_scene[s]
        for a, b in zip(rs, rs[1:]):
            if a["perso"] != b["perso"]:
                echanges[(a["perso"], b["perso"])] += 1

    # Stichomythies : au moins 4 répliques brèves (≤ 12 mots) alternant entre deux personnages
    stichos = []
    for s in scenes:
        rs = par_scene[s]
        i = 0
        while i < len(rs):
            j = i
            while (j + 1 < len(rs) and rs[j + 1]["mots"] <= 12 and rs[j]["mots"] <= 12
                   and rs[j + 1]["perso"] != rs[j]["perso"]
                   and (j - i < 1 or rs[j + 1]["perso"] == rs[j - 1]["perso"])):
                j += 1
            if j - i + 1 >= 4:
                stichos.append({"scene": s, "debut": rs[i]["id"], "fin": rs[j]["id"], "longueur": j - i + 1,
                                "personnages": sorted({rs[i]["perso"], rs[i + 1]["perso"]})})
                i = j + 1
            else:
                i += 1

    tirades = sorted(reps, key=lambda r: -r["mots"])[:8]
    didas = [e for e in piece["elements"] if e["type"] == "didascalie"]
    nb_didas_int = sum(len(r.get("didascalies", [])) for r in reps)
    return {
        "titre": piece["titre"], "auteur": piece.get("auteur", ""),
        "vue": {"scenes": len(scenes), "actes": len({s["acte"] for s in piece["scenes"] if s["acte"]}),
                "repliques": len(reps), "mots": total_mots, "personnages": n,
                "en_vers": round(sum(r["vers"] for r in reps) / len(reps), 2) if reps else 0,
                "didascalies": len(didas) + nb_didas_int,
                "mots_par_replique": round(total_mots / len(reps), 1) if reps else 0},
        "personnages": classement,
        "configurations": [{"scene": s, "titre": next(x["titre"] for x in piece["scenes"] if x["id"] == s),
                            "presents": configs[s], "mots": sum(r["mots"] for r in par_scene[s])}
                           for s in scenes],
        "reseau": {"noeuds": [{"id": p, "nom": noms[p], "degre": degre.get(p, 0), "mots": stats[p]["mots"]}
                              for p in stats],
                   "aretes": [{"a": a, "b": b, "scenes": w} for (a, b), w in aretes.most_common()],
                   "densite": densite},
        "echanges": [{"de": a, "vers": b, "n": c} for (a, b), c in echanges.most_common(20)],
        "stichomythies": stichos,
        "tirades": [{"id": r["id"], "nom": r["nom"], "scene": r["scene"], "mots": r["mots"],
                     "incipit": r["texte"][:120]} for r in tirades],
        "limites": ["La présence en scène est déduite de la prise de parole : un personnage muet n'est pas compté.",
                    "Le comptage des mots porte sur le texte prononcé, didascalies exclues."],
    }


def fiche_personnage(piece: dict[str, Any], pid: str) -> dict[str, Any]:
    """Matériaux textuels vérifiables pour les questions de Stanislavski et les quatre couches
    (livret, deuxième année, exercices 2.1 et 2.2) : l'interprétation reste à l'acteur."""
    reps = [r for r in repliques(piece) if r["perso"] == pid]
    if not reps:
        raise KeyError(pid)
    autres = repliques(piece)
    mentions = [r for r in autres if r["perso"] != pid and
                any(n.lower() in r["texte"].lower() for n in {reps[0]["nom"].title(), reps[0]["nom"]})]
    didas = [d for r in reps for d in r.get("didascalies", [])]
    return {
        "personnage": reps[0]["nom"],
        "premiere_replique": {"id": reps[0]["id"], "texte": reps[0]["texte"]},
        "derniere_replique": {"id": reps[-1]["id"], "texte": reps[-1]["texte"]},
        "plus_longue": max(reps, key=lambda r: r["mots"])["texte"],
        "didascalies": didas[:30],
        "ce_que_les_autres_disent": [{"id": r["id"], "nom": r["nom"], "texte": r["texte"]} for r in mentions[:12]],
        "questions_stanislavski": ["Qui suis-je ?", "Où suis-je ?", "Que veux-je ?",
                                   "Qu'est-ce qui m'en empêche ?", "Que suis-je prêt à faire pour l'obtenir ?"],
        "quatre_couches": ["Couche physique", "Couche sociale", "Couche psychologique",
                           "Couche spirituelle ou métaphysique"],
        "source_grille": "Livret d'exercices pour acteurs, 2e année, exercices 2.1 et 2.2",
    }


def citation_verifiee(piece: dict[str, Any], citation: str) -> str | None:
    """Renvoie l'identifiant de la réplique contenant exactement la citation, sinon None."""
    from .texte_outils import normaliser
    c = " ".join(normaliser(citation).split())
    if len(c) < 6:
        return None
    for e in piece["elements"]:
        if c in " ".join(normaliser(e["texte"]).split()):
            return e["id"]
    return None
