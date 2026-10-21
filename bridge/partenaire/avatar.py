"""Robot virtuel : validation des actions et interprétation assistée (Claude) des directives.

La page web interprète elle-même les directives courantes (règles en français, hors ligne).
Le pont n'intervient que pour ce que ces règles ne comprennent pas, si un modèle est disponible
(service unique des modèles, rôle « commande ») : il soumet la consigne avec le vocabulaire autorisé, puis revalide
la proposition contre web/avatar/schema.json (même règle que web/avatar/directives.js).
L'interface présente ensuite la proposition à l'utilisateur, qui la valide ou la rejette."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA_CHEMIN = Path(__file__).resolve().parents[2] / "web" / "avatar" / "schema.json"
_SCHEMA: dict[str, Any] | None = None

TYPES = {"articulation", "emotion", "visage", "geste", "pose", "deplacer", "orienter", "regard", "dire",
         "apparence", "camera", "lumiere", "vitesse", "memoriser", "rappeler", "arret", "repeter", "annuler", "aide"}
APPARENCE_CLES = {"taille", "carrure", "corpulence", "age", "cheveux", "barbe", "manches", "peau", "haut", "bas",
                  "chaussures", "couleur_cheveux", "moustache", "yeux", "matiere", "chapeau", "couleur_chapeau", "cou", "cape",
                  "jupe", "gants", "accessoire", "habillage"}


def schema() -> dict[str, Any]:
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = json.loads(SCHEMA_CHEMIN.read_text(encoding="utf-8"))
    return _SCHEMA


def _borne(v: Any, a: float, b: float) -> float:
    return max(a, min(b, float(v)))


def valider(actions: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Renvoie (actions acceptées et bornées, rejets motivés)."""
    S = schema()
    ok: list[dict[str, Any]] = []
    rejets: list[dict[str, Any]] = []
    for a in actions if isinstance(actions, list) else []:
        if not isinstance(a, dict) or a.get("type") not in TYPES:
            rejets.append({"action": a, "motif": "type d'action inconnu"})
            continue
        x = dict(a)
        t = x["type"]
        try:
            if t == "articulation":
                d = S["dofs"].get(x.get("dof"))
                if not d:
                    raise ValueError("articulation inconnue")
                etendue = d["max"] - d["min"]
                x["valeur"] = _borne(x["valeur"], -etendue, etendue) if x.get("relatif") else _borne(x["valeur"], d["min"], d["max"])
            elif t == "emotion":
                if x.get("nom") not in S["emotions"]:
                    raise ValueError("émotion inconnue")
                x["intensite"] = _borne(x.get("intensite", 7), -10 if x.get("relatif") else 0, 10)
            elif t == "geste" and x.get("nom") not in S["gestes"]:
                raise ValueError("geste inconnu")
            elif t == "pose" and x.get("nom") not in S["poses"]:
                raise ValueError("pose inconnue")
            elif t == "regard" and x.get("cible") not in S["regards"]:
                raise ValueError("cible de regard inconnue")
            elif t == "camera" and x.get("vue") not in S["vues"]:
                raise ValueError("vue inconnue")
            elif t == "lumiere" and x.get("mode") not in S["lumieres"]:
                raise ValueError("éclairage inconnu")
            elif t == "dire":
                x["texte"] = str(x.get("texte", ""))[:600]
                if not x["texte"].strip():
                    raise ValueError("texte vide")
            elif t == "visage":
                x["au"] = {k: _borne(v, 0, 1) for k, v in (x.get("au") or {}).items()
                           if re.fullmatch(r"au\d{1,2}(_[gd])?", str(k)) and isinstance(v, (int, float))}
            elif t == "deplacer":
                P = S["plateau"]
                if "x" in x:
                    x["x"] = _borne(x["x"], *P["x"])
                if "z" in x:
                    x["z"] = _borne(x["z"], *P["z"])
                for k in ("avant", "lateral"):
                    if k in x:
                        x[k] = _borne(x[k], -3, 3)
            elif t == "orienter":
                x["angle"] = _borne(x.get("angle", 0), -360, 360)
            elif t == "vitesse":
                x["facteur"] = _borne(x.get("facteur", 1), 0.2, 3)
            elif t == "apparence":
                cle = x.get("cle")
                if cle not in APPARENCE_CLES:
                    raise ValueError("attribut d'apparence inconnu")
                A = S["apparence"]
                if cle in ("taille", "carrure", "corpulence", "age"):
                    r = A[cle]
                    e = r["max"] - r["min"]
                    x["valeur"] = _borne(x["valeur"], -e, e) if x.get("relatif") else _borne(x["valeur"], r["min"], r["max"])
                elif cle in ("cheveux", "barbe", "manches", "peau", "matiere", "chapeau", "cou", "cape", "jupe") \
                        and x.get("valeur") not in A[cle]:
                    raise ValueError(f"valeur inconnue pour {cle}")
                elif cle == "habillage" and x.get("valeur") not in A.get("habillages", {}):
                    raise ValueError("habillage inconnu")
                elif cle == "gants":
                    x["valeur"] = bool(x.get("valeur"))
                elif cle in ("haut", "bas", "chaussures", "couleur_cheveux", "couleur_chapeau", "accessoire"):
                    v = str(x.get("valeur", ""))
                    if v not in A["couleurs"] and not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
                        raise ValueError("couleur inconnue")
            elif t in ("memoriser", "rappeler"):
                x["nom"] = str(x.get("nom") or "pose")[:40]
            if "vitesse" in x and t != "vitesse":
                x["vitesse"] = _borne(x["vitesse"], 0.2, 3)
        except (ValueError, TypeError, KeyError) as exc:
            rejets.append({"action": a, "motif": str(exc) or "valeur invalide"})
            continue
        ok.append(x)
    return ok, rejets


SYSTEME = """Tu traduis des directives de mise en scène, en français, en actions pour un robot virtuel humanoïde
(personnage masculin en 3D). Réponds UNIQUEMENT par un objet JSON :
{"actions": [...], "confiance": nombre entre 0 et 1, "justification": "une phrase en français"}.
N'utilise que le vocabulaire fourni (types, articulations et bornes, émotions, gestes, poses, regards, vues,
lumières, attributs d'apparence). Angles en degrés ; « gauche » et « droite » sont ceux du personnage ;
« cour » est à la gauche du personnage face au public, « jardin » à sa droite. Si la directive est ambiguë,
dangereuse ou hors du vocabulaire, renvoie peu ou pas d'actions et une confiance basse. Ne fais jamais
dire au personnage un texte que l'utilisateur n'a pas fourni."""


def vocabulaire() -> dict[str, Any]:
    S = schema()
    return {
        "types": {
            "articulation": {"dof": "nom", "valeur": "degrés (ou cm, %)", "relatif": "booléen facultatif"},
            "emotion": {"nom": S["emotions"], "intensite": "0 à 10"},
            "visage": {"au": "unités d'action FACS au1…au46 (suffixe _g/_d pour un côté), 0 à 1", "tenir": True},
            "geste": {"nom": S["gestes"], "cote": "g|d", "repetitions": "1 à 8", "direction": "devant|gauche|droite|haut|bas"},
            "pose": {"nom": S["poses"]},
            "deplacer": {"x": S["plateau"]["x"], "z": S["plateau"]["z"], "avant": "mètres", "lateral": "mètres"},
            "orienter": {"angle": "degrés (+ vers la gauche du personnage)", "relatif": "booléen"},
            "regard": {"cible": S["regards"]},
            "dire": {"texte": "texte fourni par l'utilisateur", "maniere": "chuchote|crie"},
            "apparence": {"cle": sorted(APPARENCE_CLES), "valeur": "voir bornes", "relatif": "booléen"},
            "camera": {"vue": S["vues"]}, "lumiere": {"mode": S["lumieres"]}, "vitesse": {"facteur": "0,2 à 3"},
        },
        "articulations": {k: [v["min"], v["max"], v["libelle"]] for k, v in S["dofs"].items()},
        "lieux": S["lieux"],
        "apparence": {k: v for k, v in S["apparence"].items() if k not in ("couleurs", "habillages")}
        | {"couleurs": sorted(S["apparence"]["couleurs"]),
           "habillages": {k: h["libelle"] for k, h in S["apparence"].get("habillages", {}).items()}},
    }


def _extraire_json(texte: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", texte, re.S)
    if not m:
        raise ValueError("aucun objet JSON")
    return json.loads(m.group(0))


async def interpreter(service: Any, texte: str, etat: dict[str, Any] | None) -> dict[str, Any]:
    """Interprétation par le service unique des modèles (rôle « commande », D13), revalidée.
    `service` : ServiceModeles disponible pour ce rôle, ou None (voie déterministe seule)."""
    texte = str(texte or "").strip()[:600]
    if service is None:
        return {"actions": [], "rejets": [], "confiance": 0.0, "moteur": "aucun", "texte": texte, "trace": None,
                "justification": "Aucun modèle disponible sur le pont : seules les règles locales s'appliquent."}
    contenu = (f"Directive : {texte}\n\nÉtat actuel : {json.dumps(etat or {}, ensure_ascii=False)[:3000]}\n\n"
               f"Vocabulaire autorisé : {json.dumps(vocabulaire(), ensure_ascii=False)}")
    moteur = "modèle"
    try:
        # température seule (jamais avec top_p) ; le routeur de sensibilité du service s'applique (D03)
        r = await service.generer("commande", SYSTEME, contenu, temperature=0.2, max_tokens=900, json_attendu=True,
                                  domaine="robot")
        moteur = r.modele_exact or r.modele_demande
        trace = {**r.trace(), "famille": r.famille}
        d = _extraire_json(r.texte)
    except Exception as exc:  # refus de sensibilité, réseau, quota, JSON invalide
        return {"actions": [], "rejets": [], "confiance": 0.0, "moteur": moteur, "texte": texte, "trace": None,
                "justification": f"Interprétation impossible ({type(exc).__name__} : {str(exc)[:160]})."}
    ok, rejets = valider(d.get("actions"))
    try:
        confiance = max(0.0, min(1.0, float(d.get("confiance", 0))))
    except (TypeError, ValueError):
        confiance = 0.0
    if rejets:
        confiance = min(confiance, 0.5)
    return {"actions": ok, "rejets": rejets, "confiance": confiance, "moteur": moteur, "texte": texte,
            "trace": trace, "justification": str(d.get("justification", ""))[:400]}
