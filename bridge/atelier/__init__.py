"""Atelier dramaturgique P1 intégré à la plateforme (A-01 à A-08).

Le moteur reste celui du prototype P1 (modules/p1/atelier_p1, 20 tests) : cinq opérations, routeur de
sensibilité D03 sans repli, verrou de mise en service, journal I-5, exports PROV/CSV. La plateforme y ajoute :
* les appels réels par le service unique des modèles (D13) : Claude Opus 5.5 ou GPT-6.1 Sol au choix, version
  la plus récente fixée au début de la séance ;
* la consignation des paramètres demandés et appliqués par génération (A-08) ;
* le miroir de chaque événement dans le journal unifié des cinq opérations (N-01), avec dépôt Git (N-03) ;
* le taux de conservation à côté de l'écart (N-04) ;
* les verrous de gouvernance en mode « atelier » : avis éthique (G-02), EFVP (G-04), consentement
  « atelier_p1 » de chaque pseudonyme (G-01), SI-02 non provisoire (critère 4 de mise en service).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import _modules  # noqa: F401
from atelier_p1.atelier import Atelier, ErreurAtelier
from atelier_p1.corpus import charger_corpus
from atelier_p1.modeles import SYSTEME, TYPES, Generation, ModeleLocal, ModeleSimule, construire_consigne, \
    extraire_propositions

from ..gouvernance import VerrouGouvernance
from ..modeles import AucunModele, RefusSensibilite
from ..modeles.clients import ErreurModele as ErreurService
from ..trace import EvenementInvalide, JournalCocreation, identifiant_seance
from ..trace.ecart import taux_conservation


class ModeleUnifie:
    """Adaptateur : le « modèle distant » de P1 devient le service unique des modèles (D13)."""

    def __init__(self, service, famille: str, temperature: float | None = 0.7, max_tokens: int = 1500):
        from ..modeles.catalogue import FAMILLES
        self.service, self.famille = service, famille
        self.temperature, self.max_tokens = temperature, max_tokens
        self.code = FAMILLES[famille].systeme
        self.derniere: dict[str, Any] | None = None

    @property
    def modele(self) -> str:
        from ..modeles.catalogue import FAMILLES
        return self.service.catalogue.resolus.get(self.famille) or FAMILLES[self.famille].reference

    @property
    def disponible(self) -> bool:
        from ..modeles.catalogue import FAMILLES
        return self.service._client(FAMILLES[self.famille].fournisseur) is not None

    def generer(self, texte: str, type_: str, nb: int, extraits=()) -> Generation:
        from atelier_p1.modeles import ErreurModele
        try:
            r = self.service.generer_sync("ecriture", SYSTEME, construire_consigne(texte, type_, nb, extraits),
                                          temperature=self.temperature, max_tokens=self.max_tokens, famille=self.famille)
        except (ErreurService, AucunModele, RefusSensibilite) as exc:
            raise ErreurModele(str(exc)) from exc
        self.derniere = r.trace()
        return Generation(extraire_propositions(r.texte, nb), r.systeme, r.modele_exact, r.jetons_entree,
                          r.jetons_sortie, r.texte)


class AtelierTrace(Atelier):
    """Atelier P1 dont chaque événement est aussi écrit dans le journal unifié."""

    def __init__(self, *a, journal: JournalCocreation, distant_unifie: ModeleUnifie | None = None, **k):
        self.journal = journal
        self.distant_unifie = distant_unifie
        self.parametres_local = {"format": "json"}
        self.erreurs_trace: list[str] = []
        super().__init__(*a, **k)

    def _miroir(self, operation: str, agent: tuple[str, str], donnees: dict, cycle: str | None,
                **kw) -> None:
        try:
            self.journal.emettre("P1", operation, agent, donnees, cycle=cycle, **kw)
        except (EvenementInvalide, OSError) as exc:
            self.erreurs_trace.append(f"{operation} : {exc}")

    def _ecrire(self, evenement: str, **d):
        super()._ecrire(evenement, **d)
        cyc = d.get("cycle")
        c = self.cycles.get(cyc) if cyc else None
        pseudo = c.pseudonyme if c else d.get("pseudonyme")
        if evenement == "consigne":
            self._miroir("consigne", ("personne", d["pseudonyme"]),
                         {"texte": d["consigne"], "type": d["type"], "extraits": d["extraits"],
                          "confidentielle": d["confidentielle"],
                          "precision": getattr(self, "precision_courante", None)}, cyc)   # O-01
        elif evenement == "generation":
            trace = (self.distant_unifie.derniere if self.distant_unifie and d["systeme"] == self.distant_unifie.code
                     else None) or {"parametres_demandes": dict(self.parametres_local) if d["systeme"] == "SI-02" else {},
                                    "parametres_appliques": dict(self.parametres_local) if d["systeme"] == "SI-02" else {},
                                    "ecarts_parametres": []}
            self._miroir("generation", ("systeme", d["systeme"]),
                         {"systeme": d["systeme"], "version_modele": d["version_modele"], "type_texte": c.type,
                          "consigne": c.consigne, "contexte": ", ".join(c.extraits) or None,
                          "parametres_demandes": trace["parametres_demandes"],
                          "parametres_appliques": trace["parametres_appliques"],
                          "ecarts_parametres": trace.get("ecarts_parametres", []),
                          "jetons_entree": int(d["jetons_entree"]), "jetons_sortie": int(d["jetons_sortie"]),
                          "propositions": d["propositions"], "numero": d["numero"],
                          "cible": d["cible"], "motifs_routage": d["motifs_routage"]}, cyc)
        elif evenement == "selection":
            dd = {"generation": d.get("generation"), "proposition": d.get("proposition"),
                  "decision": d["decision"], "motif": d.get("motif", "")}
            self._miroir("selection", ("personne", pseudo), dd, cyc)
        elif evenement == "transformation":
            p = self._prop(cyc, d["generation"], d["proposition"])
            self._miroir("transformation", ("personne", pseudo),
                         {"generation": d["generation"], "proposition": d["proposition"],
                          "version": d["version_transformee"], "ecart": d["ecart_transformation"],
                          "conservation": taux_conservation(p.texte, d["version_transformee"])}, cyc)
        elif evenement == "attribution":
            self._miroir("attribution", ("personne", pseudo),
                         {"generation": d["generation"], "proposition": d["proposition"],
                          "etiquette": d["etiquette"], "credit": d["credit"], "suggestion": d.get("suggestion")}, cyc)
        elif evenement == "segment_humain":
            self._miroir("autre", ("personne", d["pseudonyme"]), {"description": "Écriture directe sans proposition",
                                                                  "texte": d["texte"]}, None,
                         categorie_autre="ecriture_directe")


class GestionAteliers:
    """Ouverture et conduite des séances d'atelier depuis l'interface web."""

    def __init__(self, ctl, cfg: dict[str, Any] | None = None):
        self.ctl = ctl
        self.cfg = cfg or {}
        self.racine_p1 = _modules.CHEMINS["p1"]
        self.atelier: AtelierTrace | None = None
        self.seance_unifiee: str | None = None

    def _verifier_atelier(self, pseudonymes: list[str]) -> None:
        g = self.ctl.gouv
        g.exiger_collecte("Atelier P1 avec des artistes", "P1_atelier")
        stock = self.ctl.partenaire.stockage
        manquants = [p for p in pseudonymes if not stock.a_consenti(_aid(stock, p), "atelier_p1")]
        if manquants:
            raise VerrouGouvernance(f"Consentement « atelier_p1 » absent pour : {', '.join(manquants)} (G-01)")
        if self.ctl.service.local_provisoire:
            raise VerrouGouvernance(f"SI-02 est provisoire ({self.ctl.service.local.modele}) : mode atelier refusé "
                                    "tant que l'évaluation à l'aveugle n'a pas désigné le modèle local "
                                    "(critère 4 de mise en service)")

    def ouvrir(self, *, pseudonymes: list[str], mode: str = "essai", famille: str = "claude-opus",
               simule: bool = False, type_: str = "ATELIER") -> dict[str, Any]:
        pseudonymes = [p.strip() for p in pseudonymes if p.strip()]
        if not pseudonymes:
            raise ErreurAtelier("Au moins un pseudonyme (jamais un nom)")
        if mode == "atelier":
            self._verifier_atelier(pseudonymes)
        c = self.cfg
        racine = self.ctl.racine_corpus
        sid = identifiant_seance(racine / "traces" / __import__("datetime").datetime.now().strftime("%Y%m%d"),
                                 "P1", type_)
        journal = JournalCocreation(racine, sid, versionner=bool(self.ctl.cfg["protocole"].get("versionner_corpus", True)))
        distant = ModeleUnifie(self.ctl.service, famille, float(c.get("temperature", 0.7)))
        sl = self.ctl.service.local
        choisi = sl.choisir() if hasattr(sl, "choisir") else None     # principal, sinon secours (toujours local)
        local = ModeleLocal(choisi or sl.modele, sl.url)
        dossier_journal = Path(c.get("dossier_journal") or (self.ctl.donnees / "p1" / "journaux"))
        mise_en_service = Path(c.get("mise_en_service") or (self.racine_p1 / "config" / "mise_en_service.yaml"))
        from atelier_p1.routeur import charger_liste_blocage
        self.atelier = AtelierTrace(
            seance=sid, pseudonymes=pseudonymes, corpus=charger_corpus(self.racine_p1 / "corpus"),
            distant=distant, local=local, simule=ModeleSimule(), dossier_journal=dossier_journal,
            liste_blocage=charger_liste_blocage(self.ctl.cfg.get("modeles", {}).get("liste_blocage") or None),
            mode=mode, mise_en_service=mise_en_service, plafond_jetons=int(c.get("plafond_jetons", 200_000)),
            forcer_simule=simule, journal=journal, distant_unifie=distant)
        self.seance_unifiee = sid
        return self.etat()

    def exiger(self) -> AtelierTrace:
        if self.atelier is None:
            raise ErreurAtelier("Aucune séance d'atelier ouverte")
        return self.atelier

    def etat(self) -> dict[str, Any]:
        a = self.atelier
        if a is None:
            return {"ouverte": False, "types": TYPES,
                    "familles": ["claude-opus", "gpt-sol"], "modeles": self.ctl.service.resume()["resolus"]}
        return {
            "ouverte": True, "seance": a.seance, "mode": a.mode, "hors_ligne": a.hors_ligne,
            "pseudonymes": a.pseudonymes, "types": TYPES, "corpus": [e.public() for e in a.corpus.values()],
            "jetons": a.jetons, "plafond_jetons": a.plafond, "simule": a.forcer_simule,
            "modeles": {"distant": {"code": a.distant.code, "modele": a.distant.modele, "disponible": a.distant.disponible,
                                    "famille": getattr(a.distant, "famille", None)},
                        "local": {"code": a.local.code, "modele": a.local.modele or "(non configuré)",
                                  "disponible": a.local.disponible, "provisoire": self.ctl.service.local_provisoire}},
            "cycles": [{"id": c.id, "pseudonyme": c.pseudonyme, "type": c.type, "consigne": c.consigne,
                        "extraits": c.extraits,
                        "generations": [{"systeme": g.systeme, "modele": g.modele, "cible": g.cible,
                                         "motifs": g.motifs_routage,
                                         "propositions": [{**p.__dict__, "conservation": taux_conservation(p.texte, p.version)
                                                           if p.version is not None else None} for p in g.propositions]}
                                        for g in c.generations]} for c in a.cycles.values()],
            "texte_final": a.segments, "indicateurs": a.indicateurs(),
            "completude": a.journal.completude(), "erreurs_trace": a.erreurs_trace[-5:],
            "journal_unifie": str(a.journal.fichier), "precision_consigne": getattr(a, "precision_courante", None),
        }


def _aid(stock, pseudo: str) -> str | None:
    try:
        return stock.profil(pseudo)["id"]
    except KeyError:
        return None
