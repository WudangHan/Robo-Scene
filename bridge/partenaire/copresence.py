"""Partition de coprésence et plan de perturbations pré-enregistré (dossier expérimental, ch. 7).

Quatre situations : attente partagée, marche accordée, adresse au public, silence tenu.
Trois familles de perturbations : P1 (tempo ±20 %), P2 (substitution d'un geste homologue,
probabilité 0,15 sur un segment), P3 (changement ponctuel de partenaire, consigné).

Le plan est SCELLÉ : son empreinte SHA-256 est inscrite dans les métadonnées de la séance
avant toute exécution ; l'acteur et les observateurs n'en voient que l'empreinte. Le
descellement, après la séance, vérifie que le plan exécuté est bien celui qui fut scellé.
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from .connaissances import RACINE

DOSSIER_PLANS = RACINE / "partenaire" / "donnees" / "plans"

SITUATIONS = {
    "attente_partagee": "Attente partagée : respiration lente, regard qui se pose sur le partenaire.",
    "marche_accordee": "Marche accordée : pulsation régulière du corps sur le tempo commun.",
    "adresse_public": "Adresse au public : orientation franche vers la salle, tenue.",
    "silence_tenu": "Silence tenu : immobilité complète, tenue de la pose.",
}


def _canonique(plan: dict[str, Any]) -> bytes:
    return json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def valider_plan(plan: dict[str, Any]) -> dict[str, Any]:
    perts = []
    for p in plan.get("perturbations", []):
        code = p.get("code")
        if code == "P1":
            f = float(p.get("facteur", 1.2))
            if not 0.5 <= f <= 1.5:
                raise ValueError("P1 : facteur de tempo hors de [0,5 ; 1,5]")
            perts.append({"code": "P1", "situation": p.get("situation"), "debut_s": float(p.get("debut_s", 0)),
                          "duree_s": float(p.get("duree_s", 60)), "facteur": f})
        elif code == "P2":
            q = float(p.get("probabilite", 0.15))
            if not 0 <= q <= 1:
                raise ValueError("P2 : probabilité hors de [0 ; 1]")
            perts.append({"code": "P2", "situation": p.get("situation"), "debut_s": float(p.get("debut_s", 0)),
                          "duree_s": float(p.get("duree_s", 300)), "probabilite": q})
        elif code == "P3":
            perts.append({"code": "P3", "remplacant": str(p.get("remplacant", ""))[:40],
                          "remarque": str(p.get("remarque", ""))[:300]})
        else:
            raise ValueError(f"Perturbation inconnue : {code}")
    return {"seance": str(plan.get("seance", ""))[:20], "graine": int(plan.get("graine", 0)),
            "perturbations": perts}


def sceller(plan: dict[str, Any], dossier: Path | None = None) -> str:
    dossier = dossier or DOSSIER_PLANS
    plan = valider_plan(plan)
    empreinte = hashlib.sha256(_canonique(plan)).hexdigest()
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / f"{empreinte}.json").write_text(json.dumps(
        {"plan": plan, "scelle_le": datetime.now().astimezone().isoformat(timespec="seconds")},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return empreinte


def charger(empreinte: str, dossier: Path | None = None) -> dict[str, Any]:
    dossier = dossier or DOSSIER_PLANS
    f = dossier / f"{''.join(c for c in empreinte if c in '0123456789abcdef')}.json"
    if not f.exists():
        raise KeyError("Plan scellé introuvable")
    return json.loads(f.read_text(encoding="utf-8"))


def desceller(empreinte: str, dossier: Path | None = None) -> dict[str, Any]:
    d = charger(empreinte, dossier)
    recalc = hashlib.sha256(_canonique(d["plan"])).hexdigest()
    return {**d, "empreinte": empreinte, "integre": recalc == empreinte}


def _actives(plan: dict[str, Any] | None, situation: str, t: float) -> list[dict[str, Any]]:
    if not plan:
        return []
    return [p for p in plan["perturbations"] if p["code"] in ("P1", "P2")
            and (p.get("situation") in (None, "", situation))
            and p["debut_s"] <= t < p["debut_s"] + p["duree_s"]]


def generer(situation: str, duree_s: float, tempo_bpm: float, repos: list[float], min_deg: list[float],
            max_deg: list[float], idx: dict[str, int], plan: dict[str, Any] | None = None,
            ampleur: float = 1.0) -> list[dict[str, Any]]:
    """Images clés d'une situation ; chaque image indique la perturbation appliquée, le cas échéant."""
    if situation not in SITUATIONS:
        raise ValueError(f"Situation inconnue : {situation}")
    rnd = random.Random((plan or {}).get("graine", 0) * 1009 + len(situation))
    n = len(repos)
    ep, te, ba = idx.get("epaule", 1 % n), idx.get("tete", n - 1), idx.get("base", 0)

    def borner(d: list[float]) -> list[float]:
        return [round(max(min_deg[i], min(max_deg[i], x)), 1) for i, x in enumerate(d)]

    images, t = [], 0.0
    beat = 60.0 / max(20.0, min(180.0, tempo_bpm))
    k = 0
    while t < duree_s:
        act = _actives(plan, situation, t)
        facteur = next((p["facteur"] for p in act if p["code"] == "P1"), 1.0)
        p2 = next((p for p in act if p["code"] == "P2"), None)
        deg = list(repos)
        if situation == "attente_partagee":
            dur = 4 * beat / facteur
            deg[ep] = repos[ep] + 6 * ampleur * (1 if k % 2 == 0 else -0.3)
            if k % 4 == 3:
                deg[ba] = repos[ba] + 15 * ampleur
        elif situation == "marche_accordee":
            dur = beat / facteur
            deg[te] = repos[te] + (5 if k % 2 == 0 else -5) * ampleur
            deg[ep] = repos[ep] + (8 if k % 2 == 0 else 0) * ampleur
        elif situation == "adresse_public":
            dur = 2 * beat / facteur
            deg[te] = repos[te] + 10 * ampleur
            deg[ba] = repos[ba]
        else:  # silence_tenu
            dur = min(2.0, duree_s - t) or 2.0
        perturbation = "P1" if facteur != 1.0 else None
        if p2 and situation != "silence_tenu" and rnd.random() < p2["probabilite"]:
            # Geste homologue : même durée, même ampleur, articulation et sens permutés
            ecarts = [d - r for d, r in zip(deg, repos)]
            deg = [repos[i] - ecarts[(i + 1) % n] for i in range(n)]
            perturbation = "P2" if not perturbation else "P1+P2"
        images.append({"deg": borner(deg), "ms": int(dur * 1000), "t": round(t, 2), "perturbation": perturbation})
        t += dur
        k += 1
    images.append({"deg": borner(list(repos)), "ms": 1200, "t": round(t, 2), "perturbation": None})
    return images


def plan_type_cas_a() -> dict[str, Any]:
    """Paramétrage proposé au tableau 2.3 du dossier expérimental (marqué « Inférence » dans la source)."""
    return {"seance": "S7-S9", "graine": 2026, "perturbations": [
        {"code": "P1", "situation": "marche_accordee", "debut_s": 20, "duree_s": 60, "facteur": 1.2},
        {"code": "P2", "situation": "attente_partagee", "debut_s": 0, "duree_s": 300, "probabilite": 0.15},
        {"code": "P3", "remplacant": "", "remarque": "Remplacement du comédien titulaire pour une séance (S9)."},
    ]}

