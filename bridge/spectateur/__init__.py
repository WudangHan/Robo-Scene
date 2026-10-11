"""Volet spectateur de la plateforme (S-01 à S-06) : rétroaction P3 en salle, tirage X.2, questionnaires.

* S-01/S-02 — séance P3 (serveur local du prototype P3.2, agrégation anonyme, seuil de diffusion) ouverte
  et close depuis la régie ; la condition « provenance affichée » (H4) vient du tirage scellé ;
* S-03 — tirage au sort des conditions X.2, scellé par empreinte (voir tirage.py) ;
* S-04 — l'étiquette de provenance est poussée par la conduite (OSC /p3/provenance) ;
* S-05 — passation des questionnaires I-7 et I-6 sur un serveur public distinct (port 8081 par défaut),
  sans adresse IP ni témoin ;
* S-06 — avis de transparence lu par le public avant toute réponse.

Verrous : en mode « public », toute collecte exige l'avis éthique et une EFVP à jour (G-02, G-04) ; le mode
« essai » reste ouvert pour les répétitions techniques, avec des données rangées à part et marquées.
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .. import _modules  # noqa: F401
from p3_spectateur.agregat import Seance as SeanceP3
from p3_spectateur.serveur import creer_serveur, demarrer_osc, enregistrer_export

from ..securite import CommandeRefusee
from .questionnaire import Instrument, ReponseInvalide, Stockage
from .tirage import Tirage

MODES = ("essai", "public")
FONCTION_EFVP = {"I-7": "P3_questionnaires", "I-6": "P3_questionnaires", "P3": "P3_spectateur"}


def avis_transparence(langue: str, *, essai: bool, seuil: int, conservation: dict[str, str]) -> dict[str, Any]:
    """S-06 : avis lu avant toute réponse. Les durées viennent de gouvernance/conservation.yaml."""
    duree = conservation.get("DO-03") or ("à fixer par le chercheur" if langue == "fr" else "to be set by the researcher")
    if langue == "en":
        points = [
            "This performance is part of a research project on artificial intelligence in theatre creation "
            "(independent, self-funded research led by Sylvain Gagné, Ph.D.).",
            "Some lines may have been proposed by an AI system and then chosen and reworked by the artists.",
            "Your answers are anonymous: no name, no IP address, no cookie is recorded.",
            f"Live reactions are only kept as group totals; groups smaller than {seuil} are hidden.",
            f"Questionnaire answers are kept until: {duree}.",
            "Answering is voluntary; you can stop at any time.",
        ]
        titre = "Before you answer"
    else:
        points = [
            "Cette représentation fait partie d'un projet de recherche sur l'intelligence artificielle dans la création "
            "théâtrale (recherche indépendante et autofinancée de Sylvain Gagné, Ph. D.).",
            "Certaines répliques peuvent avoir été proposées par un système d'IA, puis choisies et retravaillées par les artistes.",
            "Vos réponses sont anonymes : aucun nom, aucune adresse IP, aucun témoin (cookie) n'est enregistré.",
            f"Les réactions en direct ne sont conservées qu'en totaux de groupe ; un groupe de moins de {seuil} personnes est masqué.",
            f"Les réponses au questionnaire sont conservées jusqu'à : {duree}.",
            "Répondre est volontaire ; vous pouvez arrêter à tout moment.",
        ]
        titre = "Avant de répondre"
    if essai:
        points.insert(0, "TECHNICAL TRIAL — answers are not research data." if langue == "en"
                      else "ESSAI TECHNIQUE — les réponses ne sont pas des données de recherche.")
    return {"titre": titre, "points": points}


class GestionSpectateur:
    def __init__(self, ctl, cfg: dict[str, Any] | None = None):
        self.ctl = ctl
        self.cfg = cfg or {}
        self.dossier_q = Path(self.cfg.get("dossier_questionnaires") or (Path(_modules.RACINE) / "questionnaires"))
        self.tirage = Tirage(ctl.donnees)
        self.stockage = Stockage(ctl.donnees / "questionnaires")
        self.instruments: dict[str, Instrument] = {}
        self.recharger_instruments()
        self.p3: dict[str, Any] | None = None
        self.passation: dict[str, Any] | None = None
        self.serveur_public = None        # lancé par web.demarrer_public

    # ── Instruments ─────────────────────────────────────────
    def recharger_instruments(self) -> None:
        self.instruments = {}
        if self.dossier_q.exists():
            for f in sorted(self.dossier_q.glob("I-*.yaml")):
                ins = Instrument.charger(f)
                self.instruments[ins.id] = ins

    def _seuil(self) -> int:
        return int(self.cfg.get("seuil_diffusion", 5))

    def _conservation(self) -> dict[str, str]:
        try:
            d = yaml.safe_load((Path(self.ctl.gouv.regles) / "conservation.yaml").read_text(encoding="utf-8"))
            return {k: str(v.get("echeance") or "") for k, v in (d.get("jeux") or {}).items()}
        except (OSError, AttributeError, yaml.YAMLError):
            return {}

    def avis(self, langue: str = "fr", essai: bool | None = None) -> dict[str, Any]:
        e = essai if essai is not None else (not self.passation or self.passation["essai"])
        return avis_transparence(langue, essai=e, seuil=self._seuil(), conservation=self._conservation())

    def _verifier_mode(self, mode: str, fonction: str, action: str) -> bool:
        if mode not in MODES:
            raise CommandeRefusee(f"Mode : {' ou '.join(MODES)}")
        if mode == "public":
            self.ctl.gouv.exiger_collecte(action, fonction)     # lève VerrouGouvernance
        return mode == "essai"

    def _condition(self, id_representation: str, essai: bool, provenance_affichee: bool | None) -> dict[str, str] | None:
        c = self.tirage.condition(id_representation)
        if c is None and not essai and id_representation.startswith("X2-"):
            raise CommandeRefusee(f"{id_representation} absente du tirage scellé : effectuer ou vérifier le tirage")
        if c is None and provenance_affichee is not None:
            c = {"cond_support": "", "cond_provenance": "affichee" if provenance_affichee else "non_affichee"}
        return c

    # ── S-01/S-02 : séance P3 ───────────────────────────────
    def ouvrir_p3(self, *, id_representation: str, titre: str = "", mode: str = "essai",
                  provenance_affichee: bool | None = None, hote: str | None = None, port: int | None = None,
                  port_osc: int | None = None) -> dict[str, Any]:
        if self.p3:
            raise CommandeRefusee("Une séance P3 est déjà ouverte")
        essai = self._verifier_mode(mode, FONCTION_EFVP["P3"], "rétroaction du public P3")
        cond = self._condition(id_representation, essai, provenance_affichee) or {}
        affichee = cond.get("cond_provenance") == "affichee"
        s = SeanceP3(titre=titre or id_representation, fenetre_s=float(self.cfg.get("fenetre_s", 30)),
                     delai_min_s=float(self.cfg.get("delai_min_s", 10)), seuil_diffusion=self._seuil(),
                     afficher_provenance=affichee)
        exports = self.ctl.donnees / "p3" / ("essais" if essai else "")
        httpd = creer_serveur(s, hote or self.cfg.get("hote_public", "0.0.0.0"),
                              int(self.cfg.get("port_p3", 8080) if port is None else port), exports,
                              journal=self._journal)
        threading.Thread(target=httpd.serve_forever, daemon=True, name="p3-http").start()
        osc = demarrer_osc(s, int(self.cfg.get("port_osc_p3", 9000) if port_osc is None else port_osc), exports,
                           journal=self._journal, hote=self.cfg.get("hote_osc", "127.0.0.1"))
        self.p3 = {"seance": s, "httpd": httpd, "osc": osc, "id_representation": id_representation,
                   "condition": cond, "essai": essai, "exports": exports,
                   "ouverture": datetime.now().astimezone().isoformat(timespec="seconds")}
        self.ctl.seance.evenement("p3_ouverture", id_representation=id_representation, essai=essai,
                                  provenance_affichee=affichee)
        return self.etat()

    def etiqueter(self, etiquette: str, repere: str | None = None) -> None:
        if self.p3:
            self.p3["seance"].etiqueter(etiquette, repere)

    def fermer_p3(self) -> dict[str, Any]:
        if not self.p3:
            raise CommandeRefusee("Aucune séance P3 ouverte")
        p, self.p3 = self.p3, None
        s = p["seance"]
        chemin = None if s.close else enregistrer_export(s.terminer(), p["exports"], self._journal)
        p["httpd"].arret_demande = True
        p["osc"].shutdown()
        p["osc"].server_close()
        p["httpd"].shutdown()
        p["httpd"].server_close()
        if chemin:
            from ..pilotage.depots import consigner
            consigner(self.ctl.donnees, [chemin], f"Agrégat P3 de {p['id_representation']}"
                      + (" (essai)" if p["essai"] else ""))
        self.ctl.seance.evenement("p3_fermeture", id_representation=p["id_representation"],
                                  export=str(chemin) if chemin else None)
        return {"export": str(chemin) if chemin else None, **self.etat()}

    def _journal(self, msg: str) -> None:
        self.ctl.seance.evenement("p3", msg=msg)

    # ── S-05 : passation des questionnaires ─────────────────
    def ouvrir_passation(self, *, instrument: str, id_representation: str, mode: str = "essai",
                         provenance_affichee: bool | None = None, support: str | None = None) -> dict[str, Any]:
        ins = self.instruments.get(instrument)
        if ins is None:
            raise CommandeRefusee(f"Instrument inconnu : {instrument}")
        essai = self._verifier_mode(mode, FONCTION_EFVP.get(instrument, "P3_questionnaires"),
                                    f"questionnaire {instrument}")
        langues = [l for l in ("fr", "en") if not ins.manques(l)]
        if not essai and "fr" not in langues:
            raise CommandeRefusee("Instrument incomplet en français : " + ", ".join(ins.manques("fr")[:8])
                                  + (" …" if len(ins.manques("fr")) > 8 else ""))
        cond = self._condition(id_representation, essai, provenance_affichee) if instrument == "I-7" else None
        if cond is not None and support:
            cond = {**cond, "cond_support": support}
        self.passation = {"instrument": instrument, "id_representation": id_representation, "condition": cond,
                          "essai": essai, "langues": langues if not essai else ["fr", "en"],
                          "ouverture": datetime.now().astimezone().isoformat(timespec="seconds")}
        return self.etat()

    def fermer_passation(self) -> dict[str, Any]:
        p, self.passation = self.passation, None
        if p:
            ins = self.instruments[p["instrument"]]
            f = self.stockage.fichier(ins, p["id_representation"], p["essai"])
            if f.exists():
                from ..pilotage.depots import consigner
                consigner(self.ctl.donnees, [f], f"Réponses {p['instrument']} de {p['id_representation']}"
                          + (" (essai)" if p["essai"] else ""))
        return self.etat()

    def formulaire(self, langue: str) -> dict[str, Any]:
        p = self.passation
        if not p:
            raise CommandeRefusee("Aucun questionnaire ouvert")
        if langue not in p["langues"]:
            langue = p["langues"][0]
        ins = self.instruments[p["instrument"]]
        return {**ins.formulaire(langue, p["condition"], p["essai"]), "langues": p["langues"],
                "avis": self.avis(langue, p["essai"]), "pseudonyme_requis": not ins.anonyme}

    def recevoir(self, d: dict[str, Any]) -> dict[str, Any]:
        p = self.passation
        if not p:
            raise CommandeRefusee("Aucun questionnaire ouvert")
        ins = self.instruments[p["instrument"]]
        langue = d.get("langue") if d.get("langue") in p["langues"] else p["langues"][0]
        adm = d.get("admissibilite") or {}
        pres = d.get("presence")
        return self.stockage.enregistrer(
            ins, id_representation=p["id_representation"], condition=p["condition"], langue=langue,
            essai=p["essai"], admissibilite={k: bool(v) for k, v in adm.items()} if isinstance(adm, dict) else {},
            presence=None if pres is None else bool(pres), reponses=d.get("reponses") or {},
            pseudonyme=d.get("pseudonyme"))

    # ── État ────────────────────────────────────────────────
    def etat(self) -> dict[str, Any]:
        p3 = None
        if self.p3:
            s = self.p3["seance"]
            hote, port = self.p3["httpd"].server_address[:2]
            p3 = {"id_representation": self.p3["id_representation"], "essai": self.p3["essai"],
                  "condition": self.p3["condition"], "code": s.code, "port": port,
                  "osc": self.p3["osc"].server_address[1], "cle_regie": s.cle_regie,
                  **{k: v for k, v in s.etat_regie().items() if k not in ("code",)}}
        pa = None
        if self.passation:
            ins = self.instruments[self.passation["instrument"]]
            pa = {**self.passation, "reponses": self.stockage.compter(ins, self.passation["id_representation"],
                                                                      self.passation["essai"])}
        pub = None
        if self.serveur_public:
            pub = {"port": self.serveur_public.get("port"), "hote": self.serveur_public.get("hote")}
        return {"p3": p3, "passation": pa, "serveur_questionnaires": pub,
                "tirage": self.tirage.verifier(), "verrou_public": self._verrou_public(),
                "instruments": {k: {"titre": v.titre.get("fr"), "anonyme": v.anonyme, "enonces": len(v.enonces),
                                    "manques_fr": v.manques("fr"), "manques_en": len(v.manques("en"))}
                                for k, v in self.instruments.items()}}

    def _verrou_public(self) -> str | None:
        try:
            self.ctl.gouv.exiger_collecte("collecte auprès du public", "P3_questionnaires")
            return None
        except PermissionError as exc:
            return str(exc)

    def arreter(self) -> None:
        if self.p3:
            try:
                self.fermer_p3()
            except Exception:  # noqa: BLE001 — arrêt du serveur : ne pas bloquer la fermeture
                pass
        self.passation = None


__all__ = ["GestionSpectateur", "ReponseInvalide", "avis_transparence"]
