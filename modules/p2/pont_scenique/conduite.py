"""Chargement et validation d'une conduite (liste de repères)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

TYPES_ACTION = ("lumiere", "son", "osc", "geste", "provenance", "replique", "voix")
# Extension plateforme Robo-Scène (11 oct. 2026) :
#   geste    : champ facultatif « robot » (conduite multi-robots, O-11) ;
#   replique : texte dit en scène (surtitres O-06) ; le repère doit porter une provenance (N-05) ;
#   voix     : voix de synthèse du robot (O-12) ; la conduite doit déclarer « divulgations: [voix_synthese] ».
PROVENANCES = ("humaine", "systeme", "mixte")


@dataclass
class Action:
    type: str
    valeur: Any
    delai: float = 0.0
    transfert: float = 0.0
    robot: str | None = None


@dataclass
class Repere:
    numero: str
    nom: str
    actions: list[Action] = field(default_factory=list)


@dataclass
class Conduite:
    titre: str
    projecteurs: dict[str, int]
    reperes: list[Repere]
    divulgations: list[str] = field(default_factory=list)


def _action(brut: dict, n: str) -> Action:
    types = [t for t in TYPES_ACTION if t in brut]
    if len(types) != 1:
        raise ValueError(f"Repère {n} : chaque action doit avoir exactement un type parmi {TYPES_ACTION}")
    t = types[0]
    autres = set(brut) - {t, "delai", "transfert"} - ({"robot"} if t == "geste" else set())
    if autres:
        raise ValueError(f"Repère {n} : champs inconnus {sorted(autres)}")
    a = Action(t, brut[t], float(brut.get("delai", 0.0)), float(brut.get("transfert", 0.0)), brut.get("robot"))
    if a.delai < 0 or a.transfert < 0:
        raise ValueError(f"Repère {n} : délai et transfert doivent être positifs")
    return a


def charger(chemin: str | Path) -> Conduite:
    with open(chemin, encoding="utf-8") as f:
        d = yaml.safe_load(f)
    proj = {nom: int(v["canal"]) for nom, v in (d.get("projecteurs") or {}).items()}
    reperes = [Repere(str(r["numero"]), r.get("nom", ""), [_action(a, str(r["numero"])) for a in r.get("actions", [])])
               for r in d["reperes"]]
    return Conduite(d.get("titre", ""), proj, reperes, list(d.get("divulgations") or []))


def valider(c: Conduite, gestes_connus: set[str] | None = None) -> list[str]:
    """Retourne la liste des erreurs de la conduite (vide si elle est jouable)."""
    pb: list[str] = []
    vus = set()
    for canal in c.projecteurs.values():
        if not 1 <= canal <= 512:
            pb.append(f"Canal DMX {canal} hors de 1 à 512")
    for r in c.reperes:
        if r.numero in vus:
            pb.append(f"Numéro de repère en double : {r.numero}")
        vus.add(r.numero)
        for a in r.actions:
            if a.type == "lumiere":
                for proj, niveau in a.valeur.items():
                    if proj not in c.projecteurs:
                        pb.append(f"Repère {r.numero} : projecteur inconnu « {proj} »")
                    if not 0 <= int(niveau) <= 255:
                        pb.append(f"Repère {r.numero} : niveau {niveau} hors de 0 à 255")
            elif a.type == "geste":
                if gestes_connus is not None and a.valeur not in gestes_connus:
                    pb.append(f"Repère {r.numero} : geste « {a.valeur} » absent de la bibliothèque fermée")
            elif a.type == "provenance":
                if a.valeur not in PROVENANCES:
                    pb.append(f"Repère {r.numero} : provenance « {a.valeur} » invalide {PROVENANCES}")
            elif a.type == "osc":
                if not isinstance(a.valeur, dict) or not str(a.valeur.get("adresse", "")).startswith("/"):
                    pb.append(f"Repère {r.numero} : message OSC sans adresse commençant par « / »")
            elif a.type == "son":
                if not str(a.valeur).strip():
                    pb.append(f"Repère {r.numero} : numéro de cue QLab vide")
            elif a.type == "replique":
                texte = a.valeur.get("texte") if isinstance(a.valeur, dict) else a.valeur
                if not str(texte or "").strip():
                    pb.append(f"Repère {r.numero} : réplique vide")
                if not any(x.type == "provenance" for x in r.actions):
                    pb.append(f"Repère {r.numero} : réplique sans étiquette de provenance (N-05)")
            elif a.type == "voix":
                if "voix_synthese" not in c.divulgations:
                    pb.append(f"Repère {r.numero} : voix de synthèse sans divulgation déclarée "
                              "(ajouter « divulgations: [voix_synthese] » à la conduite, O-12)")
    return pb
