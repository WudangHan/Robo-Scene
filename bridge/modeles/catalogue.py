"""Catalogue des modèles de langage et veille des versions (décision D13).

Règle demandée par le chercheur : toujours employer la version la plus récente de chaque famille —
Claude Opus et Claude Sonnet (Anthropic), GPT Sol et GPT Luna (OpenAI) — sans jamais changer de modèle
au cours d'une séance, pour que les traces d'une même séance restent comparables entre elles.

Fonctionnement :
* au début de chaque séance, `resoudre()` interroge la liste des modèles publiée par chaque fournisseur
  (GET /v1/models), retient pour chaque famille l'identifiant de version la plus élevée, et consigne toute
  adoption nouvelle (ancienne version → nouvelle) dans `adoptions.json` et au journal de séance ;
* la séance utilise ensuite ce choix figé ; la version exacte renvoyée par le fournisseur est inscrite
  dans chaque trace de génération (N-02) ;
* sans réseau ou sans clé, la dernière version adoptée (ou la version de référence) est conservée, et le
  motif est consigné.

Versions de référence vérifiées le 11 octobre 2026 : claude-opus-5-5 et claude-sonnet-5-5 (Anthropic) ;
gpt-6.1-sol et gpt-6-luna (OpenAI, guide « Using GPT-6 »). Vérification du 12 octobre 2026 : aucun GPT-6 Terra
n'est publié (seul existe gpt-5.6-terra, de la génération précédente) ; la famille « gpt-terra » est donc
déclarée « en attente » : elle n'est jamais employée tant qu'aucun identifiant de génération 6 ou plus n'apparaît
dans la liste du fournisseur, puis elle est adoptée automatiquement au début de la séance suivante.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from ..tls import contexte as _tls


@dataclass(frozen=True)
class Famille:
    cle: str
    fournisseur: str            # anthropic | openai | local (LM Studio ou Ollama)
    motif: str | None           # expression régulière des identifiants de la famille (alias, sans date)
    reference: str              # version de référence si la veille est impossible
    systeme: str                # code du registre G.5
    libelle: str
    generation_min: int = 0     # génération minimale acceptée (0 : toute version de la famille)


FAMILLES: dict[str, Famille] = {
    "claude-opus": Famille("claude-opus", "anthropic", r"^claude-opus-(\d+)(?:-(\d+))?$", "claude-opus-5-5",
                           "SI-01", "Claude Opus (Anthropic)"),
    "claude-sonnet": Famille("claude-sonnet", "anthropic", r"^claude-sonnet-(\d+)(?:-(\d+))?$", "claude-sonnet-5-5",
                             "SI-01", "Claude Sonnet (Anthropic)"),
    "gpt-sol": Famille("gpt-sol", "openai", r"^gpt-(\d+)(?:\.(\d+))?-sol$", "gpt-6.1-sol",
                       "SI-08", "GPT Sol (OpenAI)"),
    "gpt-terra": Famille("gpt-terra", "openai", r"^gpt-(\d+)(?:\.(\d+))?-terra$", "",
                         "SI-08", "GPT Terra (OpenAI)", generation_min=6),
    "gpt-luna": Famille("gpt-luna", "openai", r"^gpt-(\d+)(?:\.(\d+))?-luna$", "gpt-6-luna",
                        "SI-08", "GPT Luna (OpenAI)"),
    "local": Famille("local", "local", None, "luciole-8b-instruct-1.1", "SI-02",
                     "Modèle local (LM Studio)"),
}

# Rôles : ordre de préférence des familles ; le premier fournisseur disponible est retenu.
ROLES_DEFAUT: dict[str, list[str]] = {
    "ecriture": ["claude-opus", "gpt-sol"],     # atelier P1, scènes, monologues, dialogues
    "analyse": ["claude-opus", "gpt-sol"],      # analyse dramaturgique, conseiller, régisseur IA
    "rapide": ["claude-sonnet", "gpt-terra", "gpt-luna"],    # variations, surtitres, tâches courtes
    "commande": ["claude-sonnet", "gpt-terra", "gpt-luna"],  # gestes nommés (bibliothèque fermée)
}

CLES_API = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def version(identifiant: str, famille: Famille) -> tuple[int, int] | None:
    if not famille.motif:
        return None
    m = re.match(famille.motif, identifiant)
    if not m or int(m.group(1)) < famille.generation_min:
        return None
    return int(m.group(1)), int(m.group(2) or 0)


def plus_recent(identifiants: list[str], famille: Famille) -> str | None:
    candidats = [(v, i) for i in identifiants if (v := version(i, famille))]
    return max(candidats)[1] if candidats else None


def _get_json(url: str, entetes: dict[str, str], delai: float = 8.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=entetes)
    with urllib.request.urlopen(req, timeout=delai, context=_tls()) as r:
        return json.loads(r.read().decode("utf-8"))


def lister_anthropic(cle: str) -> list[str]:
    ids, apres = [], None
    for _ in range(10):  # pagination prudente
        url = "https://api.anthropic.com/v1/models?limit=1000" + (f"&after_id={apres}" if apres else "")
        d = _get_json(url, {"x-api-key": cle, "anthropic-version": "2023-06-01"})
        ids += [m["id"] for m in d.get("data", [])]
        if not d.get("has_more"):
            break
        apres = d.get("last_id")
    return ids


def lister_openai(cle: str) -> list[str]:
    d = _get_json("https://api.openai.com/v1/models", {"Authorization": f"Bearer {cle}"})
    return [m["id"] for m in d.get("data", [])]


LISTEURS: dict[str, Callable[[str], list[str]]] = {"anthropic": lister_anthropic, "openai": lister_openai}


class Catalogue:
    def __init__(self, cfg: dict[str, Any] | None = None, dossier_etat: str | Path = "donnees",
                 listeurs: dict[str, Callable[[str], list[str]]] | None = None):
        cfg = cfg or {}
        self.politique = cfg.get("politique_version", "seance")   # seance | epinglee
        self.epinglees: dict[str, str] = dict(cfg.get("epinglees", {}))
        self.local = cfg.get("local", FAMILLES["local"].reference)
        self.roles = {**ROLES_DEFAUT, **{k: list(v) for k, v in (cfg.get("roles") or {}).items()}}
        self.fournisseur_prefere = cfg.get("fournisseur_prefere", "anthropic")
        self.listeurs = listeurs or LISTEURS
        self.dossier = Path(dossier_etat)
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.fichier = self.dossier / "adoptions_modeles.json"
        self.etat = self._lire()
        self.resolus: dict[str, str] = {}
        self.notes: list[str] = []

    def _lire(self) -> dict[str, Any]:
        if self.fichier.exists():
            return json.loads(self.fichier.read_text(encoding="utf-8"))
        return {"courants": {}, "historique": []}

    def _ecrire(self) -> None:
        tmp = self.fichier.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.etat, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.fichier)

    def disponible(self, fournisseur: str) -> bool:
        if fournisseur in ("local", "ollama"):
            return True
        return bool(os.environ.get(CLES_API.get(fournisseur, ""), ""))

    def resoudre(self, seance: str) -> dict[str, str]:
        """Fixe, pour la séance qui commence, la version de chaque famille. À appeler une fois par séance."""
        self.notes = []
        listes: dict[str, list[str] | None] = {}
        for f in ("anthropic", "openai"):
            cle = os.environ.get(CLES_API[f], "")
            if not cle or self.politique == "epinglee":
                listes[f] = None
                continue
            try:
                listes[f] = self.listeurs[f](cle)
            except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
                listes[f] = None
                self.notes.append(f"Veille {f} impossible ({type(exc).__name__}) : versions précédentes conservées.")
        resolus: dict[str, str] = {}
        for cle, fam in FAMILLES.items():
            if cle == "local":
                resolus[cle] = self.local
                continue
            courant = self.epinglees.get(cle) or self.etat["courants"].get(cle) or fam.reference
            ids = listes.get(fam.fournisseur)
            nouveau = plus_recent(ids, fam) if ids else None
            if self.politique == "epinglee" or not nouveau:
                resolus[cle] = courant
                continue
            # On n'adopte qu'une version strictement plus récente (jamais de retour en arrière silencieux)
            if version(nouveau, fam) > (version(courant, fam) or (0, 0)):
                self.etat["historique"].append({"date": datetime.now().astimezone().isoformat(timespec="seconds"),
                                                "seance": seance, "famille": cle, "ancienne": courant,
                                                "nouvelle": nouveau})
                self.notes.append(f"{fam.libelle} : adoption de {nouveau} (remplace {courant}).")
                courant = nouveau
            elif courant and courant not in ids:
                self.notes.append(f"{fam.libelle} : {courant} n'apparaît plus dans la liste du fournisseur.")
            resolus[cle] = courant
        self.etat["courants"] = {k: v for k, v in resolus.items() if k != "local"}
        self.etat["derniere_seance"] = seance
        self._ecrire()
        self.resolus = resolus
        return resolus

    def familles_pour(self, role: str) -> list[str]:
        fams = list(self.roles.get(role, self.roles["analyse"]))
        # Le fournisseur préféré passe en tête, à rôle égal
        fams.sort(key=lambda c: 0 if FAMILLES[c].fournisseur == self.fournisseur_prefere else 1)
        return fams

    def choisir(self, role: str) -> tuple[Famille, str] | None:
        """Première famille disponible pour le rôle, avec la version fixée pour la séance."""
        if not self.resolus:
            self.resolus = {**{k: (self.epinglees.get(k) or self.etat["courants"].get(k) or f.reference)
                               for k, f in FAMILLES.items() if k != "local"}, "local": self.local}
        for cle in self.familles_pour(role):
            fam = FAMILLES[cle]
            if self.resolus.get(cle) and self.disponible(fam.fournisseur):   # famille « en attente » ignorée
                return fam, self.resolus[cle]
        return None

    def resume(self) -> dict[str, Any]:
        return {"politique": self.politique, "resolus": self.resolus or self.etat.get("courants", {}),
                "disponibles": {f: self.disponible(f) for f in ("anthropic", "openai")},
                "roles": {r: self.familles_pour(r) for r in self.roles},
                "notes": self.notes, "historique": self.etat.get("historique", [])[-10:]}
