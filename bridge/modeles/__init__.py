"""Service unique d'accès aux modèles de langage (décisions D03 et D13).

Toute partie de la plateforme qui veut un texte d'un modèle passe par `ServiceModeles.generer(role, …)` :
1. le routeur de sensibilité du prototype P1 (D03) examine le contenu : nom figurant sur la liste de blocage,
   courriel, téléphone, mention « confidentielle », mode hors ligne. Au moindre motif, la demande va au modèle
   local (SI-02) et, s'il est indisponible, elle est REFUSÉE — jamais de repli sur un service distant ;
2. sinon, le rôle (écriture, analyse, rapide, commande) désigne une famille : Claude Opus ou GPT Sol pour
   l'écriture et l'analyse, Claude Sonnet ou GPT Luna pour les tâches rapides ; la version est celle que la
   veille a fixée au début de la séance (catalogue.Catalogue) ;
3. la réponse porte la version exacte, les paramètres demandés et appliqués, et les écarts (A-08).

Choix du moteur par domaine (demande du 20 octobre 2026) : l'opératrice choisit, pour le robot, le chien, le drone
(et, par défaut, le reste de la plateforme), « auto » (ordre des rôles ci-dessus), une famille nuagique précise
(Claude, GPT, Grok, Gemini) ou un modèle chargé dans LM Studio (« local:<identifiant> »). Le choix est consigné ;
il ne lève jamais l'aiguillage D03 : un contenu sensible va au modèle local désigné (SI-02), ou il est refusé.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from .. import _modules  # noqa: F401
from atelier_p1.routeur import Routeur, charger_liste_blocage

from .catalogue import CLES_API, FAMILLES, Catalogue, cle_api
from .clients import ClientAnthropic, ClientGoogle, ClientLocal, ClientOpenAI, ClientXAI, ErreurModele, Reponse

DOMAINES = ("defaut", "robot", "chien", "drone")
CLASSES = {"anthropic": ClientAnthropic, "openai": ClientOpenAI, "xai": ClientXAI, "google": ClientGoogle}


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
        self.jetons = {**{f: 0 for f in CLES_API}, "local": 0}
        self.choix: dict[str, str] = {d: "auto" for d in DOMAINES}
        self.choix.update({k: str(v) for k, v in dict(cfg.get("choix") or {}).items() if k in DOMAINES})
        self.reseau_local = bool(cfg.get("reseau_local", False))
        self._locaux: dict[str, ClientLocal] = {}
        self._clients = clients or {}
        # SI-02 : serveur local choisi par « api_local » (lmstudio par défaut depuis le 16 oct. 2026, ou ollama)
        self.local = self._clients.get("local") or self._clients.get("ollama") or ClientLocal(
            cfg.get("local", FAMILLES["local"].reference), cfg.get("url_local") or None,
            secours=cfg.get("local_secours") or None, api=cfg.get("api_local", "lmstudio"),
            reseau_local=bool(cfg.get("reseau_local", False)))
        self.local_provisoire = bool(cfg.get("local_provisoire", True))

    # ── Séance ──────────────────────────────────────────────
    def ouvrir_seance(self, seance: str) -> dict[str, Any]:
        self.jetons = {k: 0 for k in self.jetons}
        resolus = self.catalogue.resoudre(seance)
        return {"seance": seance, "modeles": resolus, "notes": self.catalogue.notes}

    def _client(self, fournisseur: str):
        if fournisseur in self._clients:
            return self._clients[fournisseur]
        cle = cle_api(fournisseur)
        if not cle or fournisseur not in CLASSES:
            return None
        c = CLASSES[fournisseur](cle)
        self._clients[fournisseur] = c
        return c

    # ── Moteurs au choix (domaines robot, chien, drone) ─────
    def client_local(self, modele: str) -> ClientLocal:
        """Client LM Studio (ou Ollama) pour un modèle quelconque du serveur local : même serveur et mêmes contrôles
        (verifier_local) que SI-02."""
        if modele == self.local.principal:
            return self.local
        if modele not in self._locaux:
            self._locaux[modele] = ClientLocal(modele, self.local.url, api=self.local.api, reseau_local=self.reseau_local,
                                               transport=getattr(self.local, "transport", None),
                                               lister=getattr(self.local, "_lister", None))
        return self._locaux[modele]

    def modeles_locaux(self) -> list[str]:
        """Modèles de langage offerts par LM Studio (les modèles de plongement sont écartés) ; [] si injoignable."""
        try:
            entrees = self.local._lister()
        except Exception:
            return []
        from atelier_p1.modeles import entree_distante
        return sorted(e["name"] for e in entrees if e.get("name") and not entree_distante(e)
                      and "embed" not in e["name"].lower() and e.get("type", "llm") in ("llm", "vlm"))

    def moteurs(self) -> list[dict[str, Any]]:
        """Moteurs proposés à l'opératrice, avec leur disponibilité (clé API présente, modèle chargé)."""
        resolus = self.catalogue.resolus or self.catalogue.etat.get("courants", {})
        out = [{"id": "auto", "libelle": "Automatique (ordre des rôles)", "fournisseur": "", "disponible": True}]
        for cle, fam in FAMILLES.items():
            if cle == "local":
                continue
            version = resolus.get(cle) or fam.reference
            out.append({"id": cle, "libelle": fam.libelle, "fournisseur": fam.fournisseur, "version": version or "",
                        "disponible": bool(version) and self._client(fam.fournisseur) is not None,
                        "motif": "" if self._client(fam.fournisseur) is not None else f"clé {CLES_API[fam.fournisseur]} absente"
                        if version else "famille en attente (aucune version publiée)"})
        locaux = self.modeles_locaux()
        for m in locaux:
            refus = self.client_local(m).refus
            out.append({"id": f"local:{m}", "libelle": f"LM Studio : {m}", "fournisseur": "local", "version": m,
                        "disponible": not refus, "motif": " ; ".join(refus), "si02": m == self.local.principal})
        if not locaux:
            out.append({"id": "local:", "libelle": f"LM Studio ({self.local.url})", "fournisseur": "local",
                        "disponible": False, "motif": "serveur local injoignable ou aucun modèle chargé"})
        return out

    def choisir(self, domaine: str, moteur: str) -> str:
        if domaine not in DOMAINES:
            raise ValueError(f"domaine inconnu : {domaine} ({', '.join(DOMAINES)})")
        moteur = str(moteur or "auto")
        if moteur != "auto" and not moteur.startswith("local:") and (moteur not in FAMILLES or moteur == "local"):
            raise ValueError(f"moteur inconnu : {moteur}")
        if moteur.startswith("local:"):
            if not moteur[6:]:
                raise ValueError("modèle local non précisé")
            refus = self.client_local(moteur[6:]).refus
            if refus:
                raise ValueError("modèle local refusé : " + " ; ".join(refus))
        self.choix[domaine] = moteur
        return moteur

    def choix_pour(self, domaine: str | None) -> str:
        d = domaine if domaine in DOMAINES else "defaut"
        c = self.choix.get(d, "auto")
        return self.choix.get("defaut", "auto") if c == "auto" and d != "defaut" else c

    def disponible(self, role: str = "analyse", domaine: str | None = None) -> bool:
        c = self.choix_pour(domaine)
        if c.startswith("local:"):
            return self.client_local(c[6:]).disponible
        if c != "auto":
            return self._client(FAMILLES[c].fournisseur) is not None
        return any(self._client(FAMILLES[f].fournisseur) is not None for f in self.catalogue.familles_pour(role))

    def moteur(self, role: str = "analyse", domaine: str | None = None) -> str:
        c = self.choix_pour(domaine)
        if c.startswith("local:"):
            return c[6:] if self.client_local(c[6:]).disponible else "déterministe"
        if c != "auto":
            fam = FAMILLES[c]
            return (self.catalogue.resolus.get(c) or self.catalogue.etat["courants"].get(c) or fam.reference) \
                if self._client(fam.fournisseur) is not None else "déterministe"
        for f in self.catalogue.familles_pour(role):
            m = self.catalogue.resolus.get(f) or self.catalogue.etat["courants"].get(f) or FAMILLES[f].reference
            if m and self._client(FAMILLES[f].fournisseur) is not None:
                return m
        return "déterministe"

    # ── Génération ──────────────────────────────────────────
    def generer_sync(self, role: str, systeme: str, contenu: str, *, temperature: float | None = None,
                     top_p: float | None = None, max_tokens: int = 1500, confidentielle: bool = False,
                     json_attendu: bool = False, famille: str | None = None, domaine: str | None = None) -> Reponse:
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
                                f"absent de {getattr(self.local, 'serveur', 'serveur local')}")
            self.jetons["local"] += r.jetons_entree + r.jetons_sortie
            return r
        choix = self.choix_pour(domaine) if not famille else "auto"
        if choix.startswith("local:"):
            client = self.client_local(choix[6:])
            if not client.disponible:
                raise ErreurModele(f"Modèle local « {choix[6:]} » non chargé dans {client.serveur} ({client.url})")
            r = client.generer(client.modele, systeme, contenu, temperature=temperature, top_p=top_p,
                               max_tokens=max_tokens, json_attendu=json_attendu)
            r.famille, r.motifs_routage = "local", []
            r.ecarts.append(f"moteur choisi par l'opératrice pour « {domaine or 'defaut'} » : {client.modele} (LM Studio)")
            self.jetons["local"] += r.jetons_entree + r.jetons_sortie
            return r
        familles = [famille] if famille else ([choix] if choix != "auto" else self.catalogue.familles_pour(role))
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
                                   max_tokens=max_tokens, effort=self.efforts.get(role, "none"),
                                   json_attendu=json_attendu)
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
                                                     "serveur": getattr(self.local, "serveur", None),
                                                     "provisoire": self.local_provisoire,
                                                     "reseau_local": self.reseau_local},
                "choix": dict(self.choix),
                "jetons": self.jetons, "plafond": self.plafond}


__all__ = ["AucunModele", "ErreurModele", "RefusSensibilite", "Reponse", "ServiceModeles"]
