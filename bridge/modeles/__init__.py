"""Service unique d'accès aux modèles de langage (décisions D03 et D13).

Toute partie de la plateforme qui veut un texte d'un modèle passe par `ServiceModeles.generer(role, …)` :
1. le routeur de sensibilité du prototype P1 (D03) examine le contenu : nom figurant sur la liste de blocage,
   courriel, téléphone, mention « confidentielle », mode hors ligne. Au moindre motif, la demande va au modèle
   local (SI-02) et, s'il est indisponible, elle est REFUSÉE — jamais de repli sur un service distant ;
2. sinon, le rôle (écriture, analyse, rapide, commande) désigne une famille : Claude Opus ou GPT Sol pour
   l'écriture et l'analyse, Claude Sonnet ou GPT Luna pour les tâches rapides ; la version est celle que la
   veille a fixée au début de la séance (catalogue.Catalogue) ;
3. la réponse porte la version exacte, les paramètres demandés et appliqués, et les écarts (A-08).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from .. import _modules  # noqa: F401
from atelier_p1.routeur import Routeur, charger_liste_blocage

from .catalogue import CLES_API, FAMILLES, Catalogue
from .clients import ClientAnthropic, ClientLocal, ClientOpenAI, ErreurModele, Reponse


class RefusSensibilite(Exception):
    """Contenu sensible et modèle local indisponible : génération refusée (D03, aucun repli distant)."""


class AucunModele(Exception):
    """Aucun fournisseur disponible pour ce rôle (aucune clé API) : l'appelant emploie sa voie déterministe."""


class ServiceModeles:
    def __init__(self, cfg: dict[str, Any] | None = None, dossier_etat: str | Path = "donnees", *,
                 clients: dict[str, Any] | None = None, listeurs=None):
        cfg = dict(cfg or {})
        self.cfg = cfg
        self.catalogue = Catalogue(cfg, dossier_etat, listeurs)
        self.routeur = Routeur(charger_liste_blocage(cfg.get("liste_blocage") or None))
        self.efforts = {"ecriture": "medium", "analyse": "medium", "rapide": "none", "commande": "none",
                        **dict(cfg.get("effort") or {})}
        self.plafond = int(cfg.get("plafond_jetons_seance", 200_000))
        self.jetons = {"anthropic": 0, "openai": 0, "ollama": 0}
        self._clients = clients or {}
        self.local = self._clients.get("ollama") or ClientLocal(cfg.get("local", FAMILLES["local"].reference),
                                                                cfg.get("url_local", "http://127.0.0.1:11434"),
                                                                secours=cfg.get("local_secours") or None)
        self.local_provisoire = bool(cfg.get("local_provisoire", True))

    # ── Séance ──────────────────────────────────────────────
    def ouvrir_seance(self, seance: str) -> dict[str, Any]:
        self.jetons = {k: 0 for k in self.jetons}
        resolus = self.catalogue.resoudre(seance)
        return {"seance": seance, "modeles": resolus, "notes": self.catalogue.notes}

    def _client(self, fournisseur: str):
        if fournisseur in self._clients:
            return self._clients[fournisseur]
        cle = os.environ.get(CLES_API.get(fournisseur, ""), "")
        if not cle:
            return None
        c = ClientAnthropic(cle) if fournisseur == "anthropic" else ClientOpenAI(cle)
        self._clients[fournisseur] = c
        return c

    def disponible(self, role: str = "analyse") -> bool:
        return any(self._client(FAMILLES[f].fournisseur) is not None for f in self.catalogue.familles_pour(role))

    def moteur(self, role: str = "analyse") -> str:
        for f in self.catalogue.familles_pour(role):
            m = self.catalogue.resolus.get(f) or self.catalogue.etat["courants"].get(f) or FAMILLES[f].reference
            if m and self._client(FAMILLES[f].fournisseur) is not None:
                return m
        return "déterministe"

    # ── Génération ──────────────────────────────────────────
    def generer_sync(self, role: str, systeme: str, contenu: str, *, temperature: float | None = None,
                     top_p: float | None = None, max_tokens: int = 1500, confidentielle: bool = False,
                     json_attendu: bool = False, famille: str | None = None) -> Reponse:
        decision = self.routeur.decider(contenu, (), confidentielle)
        if decision.cible == "local":
            if not self.local.disponible:
                raise RefusSensibilite("Contenu sensible (" + " ; ".join(decision.motifs) + ") et modèle local "
                                       "indisponible : génération refusée, sans repli sur un service distant (D03).")
            r = self.local.generer(self.local.modele, systeme, contenu, temperature=temperature, top_p=top_p,
                                   max_tokens=max_tokens, json_attendu=json_attendu)
            r.motifs_routage, r.famille = decision.motifs, "local"
            if self.local_provisoire:
                r.ecarts.append(f"SI-02 provisoire ({self.local.modele}), réservé aux essais jusqu'à l'évaluation "
                                "à l'aveugle")
            if getattr(self.local, "secours", None) and self.local.modele == self.local.secours:
                r.ecarts.append(f"SI-02 servi par le modèle de secours ({self.local.modele}) : modèle principal "
                                "absent d'Ollama")
            self.jetons["ollama"] += r.jetons_entree + r.jetons_sortie
            return r
        familles = [famille] if famille else self.catalogue.familles_pour(role)
        dernier: Exception | None = None
        for cle in familles:
            fam = FAMILLES[cle]
            client = self._client(fam.fournisseur)
            if client is None:
                continue
            if self.jetons[fam.fournisseur] >= self.plafond:
                dernier = ErreurModele(f"Plafond de jetons de la séance atteint pour {fam.fournisseur} (ENF-04)")
                continue
            modele = self.catalogue.resolus.get(cle) if self.catalogue.resolus else (
                self.catalogue.etat["courants"].get(cle) or fam.reference)
            if not modele:
                continue          # famille en attente (ex. GPT-6 Terra non publié) : jamais appelée
            try:
                r = client.generer(modele, systeme, contenu, temperature=temperature, top_p=top_p,
                                   max_tokens=max_tokens, effort=self.efforts.get(role, "none"))
            except ErreurModele as exc:
                dernier = exc
                continue
            r.famille, r.motifs_routage = cle, []
            self.jetons[fam.fournisseur] += r.jetons_entree + r.jetons_sortie
            return r
        if dernier:
            raise dernier
        raise AucunModele(f"Aucune clé API pour le rôle « {role} » ({', '.join(familles)}).")

    async def generer(self, role: str, systeme: str, contenu: str, **kw: Any) -> Reponse:
        return await asyncio.to_thread(self.generer_sync, role, systeme, contenu, **kw)

    def resume(self) -> dict[str, Any]:
        return {**self.catalogue.resume(), "local": {"modele": self.local.modele, "refus": self.local.refus,
                                                     "provisoire": self.local_provisoire},
                "jetons": self.jetons, "plafond": self.plafond}


__all__ = ["AucunModele", "ErreurModele", "RefusSensibilite", "Reponse", "ServiceModeles"]
