"""Serveur-pont ROBO-SCÈNE — plateforme « L'IA au service de la création théâtrale ».

    python -m bridge.serveur            (depuis le dossier du dépôt)
    python -m bridge.serveur --sim      (force la simulation de tous les robots)

Sert les interfaces web sur http://127.0.0.1:8765 et relaie, à travers la couche de sécurité de chaque robot,
les commandes vers la flotte (pilotes unifiés : ligne JSON, bus Hiwonder, ROS par rosbridge, MQTT, OSC, HTTP,
Reachy Mini, programme externe). Les modules de la plateforme (atelier P1, scène P2, spectateur P3, analyse,
gouvernance, pilotage) se greffent sur la même application (bridge.plateforme).
"""
from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import os
import time
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from aiohttp import WSMsgType, web

from .gouvernance import Gouvernance, VerrouGouvernance
from .ia import ACTIONS_FERMEES, Agent
from .journal import Seance
from .modeles import ServiceModeles
from .robots.bibliotheque import RefusBibliotheque, exigence, ralentir
from .robots.description import charger_profils, depuis_config_console
from .robots.flotte import RobotConnecte
from .securite import CommandeRefusee
from .trace import EvenementInvalide, JournalCocreation

RACINE = Path(__file__).resolve().parent.parent


class Controleur:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        p = cfg["protocole"]
        self.donnees = Path(cfg.get("donnees", {}).get("dossier") or (RACINE / "donnees"))
        if not self.donnees.is_absolute():
            self.donnees = RACINE / self.donnees
        self.donnees.mkdir(parents=True, exist_ok=True)
        self.racine_corpus = Path(p["dossier_corpus"])
        if not self.racine_corpus.is_absolute():
            self.racine_corpus = RACINE / self.racine_corpus
        self.gouv = Gouvernance(RACINE / "gouvernance", self.donnees)
        ds = Path(cfg.get("flotte", {}).get("dossier_sequences") or (RACINE / "sequences"))
        self.dossier_sequences = ds if ds.is_absolute() else RACINE / ds
        self.service = ServiceModeles(cfg.get("modeles", {}), self.donnees)
        # ── Flotte ──
        self.robots: dict[str, RobotConnecte] = {}
        d0 = depuis_config_console(cfg)
        self.robots[d0.id] = RobotConnecte(d0, self.dossier_sequences, self.donnees)
        fl = cfg.get("flotte", {})
        self.profils_disponibles = []
        dossier_profils = RACINE / fl.get("dossier_profils", "robots")
        if dossier_profils.exists():
            for d in charger_profils(dossier_profils):
                self.profils_disponibles.append(d)
                if d.actif and d.id not in self.robots:
                    if cfg.get("_forcer_sim"):
                        d.simulation = True
                    self.robots[d.id] = RobotConnecte(d, self.dossier_sequences / d.id, self.donnees)
        self.actif_id = fl.get("actif") if fl.get("actif") in self.robots else d0.id
        # ── IA supervisée ──
        self.ia_cfg = dict(cfg["ia"])
        self.ia_cfg.setdefault("regle", "bibliotheque_fermee")
        self.agent = Agent(self.ia_cfg, self.noms, self.service)
        self.clients: set[web.WebSocketResponse] = set()
        self.derniere_interface = time.monotonic()
        self.propositions: dict[str, dict] = {}
        self._ids = itertools.count(1)
        self._decim = 0
        self.observateur: dict[str, Any] | None = None
        self.pseudo_operatrice = p.get("pseudonyme_operatrice", "OP01")
        self._ouvrir_seance()
        from .partenaire.controleur import Partenaire
        self.partenaire = Partenaire(self, cfg.get("partenaire", {}))

    def _ouvrir_seance(self) -> None:
        p = self.cfg["protocole"]
        self.seance = Seance(self.racine_corpus, p["systeme"], p["type"], p.get("operatrice", ""),
                             config={k: self.cfg[k] for k in ("robot", "securite", "ia")},
                             transport=self.cfg["robot"]["transport"])
        self.seance.meta["regle_ia"] = self.ia_cfg["regle"]
        self.seance.meta["flotte"] = [r.desc.resume() for r in self.robots.values()]
        self.trace = JournalCocreation(self.racine_corpus, self.seance.id,
                                       versionner=bool(p.get("versionner_corpus", True)))
        self.seance.meta["journal_cocreation"] = str(self.trace.fichier)

    async def ouvrir_modeles(self) -> None:
        """Veille des versions au début de la séance (D13) ; consignée au journal et au registre G-03."""
        r = await asyncio.to_thread(self.service.ouvrir_seance, self.seance.id)
        self.seance.meta["modeles"] = {"versions": r["modeles"], "notes": r["notes"]}
        self.seance.sauvegarder()
        for n in r["notes"]:
            await self.log(f"Modèles : {n}")
        try:
            for c in self.gouv.synchroniser_registre(r["modeles"]):
                await self.log(f"Registre des systèmes mis à jour : {c}")
        except OSError:
            pass
        self.seance.meta["moteur_ia"] = self.agent.moteur

    # ── Robot actif (compatibilité avec la console et le partenaire) ──
    @property
    def robot(self) -> RobotConnecte:
        return self.robots[self.actif_id]

    @property
    def noms(self) -> list[str]:
        return self.robot.desc.noms

    @property
    def limites(self):
        return self.robot.limites

    @property
    def securite(self):
        return self.robot.securite

    @property
    def etat(self) -> dict[str, Any]:
        return self.robot.etat

    @property
    def lien(self) -> str:
        return self.robot.lien

    @property
    def transport(self):
        return self.robot.pilote

    @property
    def seq_nom(self):
        return self.robot.seq_nom

    def _r(self, robot: str | None) -> RobotConnecte:
        if robot is None:
            return self.robot
        if robot not in self.robots:
            raise CommandeRefusee(f"Robot inconnu : {robot}")
        return self.robots[robot]

    # ── Diffusion vers l'interface ────────────────────────────
    async def diffuser(self, msg: dict[str, Any]) -> None:
        if not self.clients:
            return
        data = json.dumps(msg, ensure_ascii=False)
        for ws in list(self.clients):
            try:
                await ws.send_str(data)
            except (ConnectionResetError, RuntimeError):
                self.clients.discard(ws)

    async def log(self, msg: str, niveau: str = "info") -> None:
        self.seance.evenement("journal", niveau=niveau, msg=msg)
        await self.diffuser({"type": "journal", "niveau": niveau, "msg": msg, "ts": time.strftime("%H:%M:%S")})

    def config_interface(self) -> dict[str, Any]:
        r = self.robot
        return {
            "type": "config", "robot_id": r.id, "noms": self.noms, "min_deg": self.limites.min_deg,
            "max_deg": self.limites.max_deg, "repos": self.limites.repos,
            "unites": [a.unite for a in r.desc.articulations], "propulsion": self.limites.propulsion_active,
            "propulsion_max": self.limites.propulsion_max, "vitesse_max": self.limites.vitesse_max_deg_s,
            "batterie_min_v": r.desc.batterie_min_v or self.cfg["securite"]["batterie_min_v"],
            "seuil": self.ia_cfg["seuil_confiance"], "execution_auto": self.ia_cfg["execution_auto"],
            "regle_ia": self.ia_cfg["regle"], "type_seance": self.cfg["protocole"]["type"],
            "moteur_ia": self.agent.moteur, "seance": self.seance.id,
            "transport": "simulation" if r.desc.simulation else r.desc.pilote, "robot": r.desc.nom,
            "simulation": r.desc.simulation, "rayon_exclusion_m": r.desc.rayon_exclusion_m,
            "observateur": self.observateur, "flotte": [x.resume() for x in self.robots.values()],
            "profils": [d.resume() for d in self.profils_disponibles],
            "statuts_sequences": self.statuts_sequences(),
        }

    # ── Réception depuis un robot ─────────────────────────────
    async def _sur_message_robot(self, r: RobotConnecte, msg: dict[str, Any]) -> None:
        t = msg.get("t")
        if t == "tel":
            r.derniere_tel = time.monotonic()
            r.etat.update({k: v for k, v in msg.items() if k != "t" and v is not None or k == "deg"})
            if msg.get("estop") and not r.securite.arret_urgence:
                # Arrêt déclenché côté robot (bouton physique, chien de garde…) : il vaut pour toute la flotte
                await self.arret_urgence(f"signalé par le robot {r.id}", origine="robot")
            self._decim += 1
            if self._decim % 4 == 0:  # télémétrie archivée à 5 Hz
                self.seance.evenement("tel", robot=r.id, **{k: v for k, v in msg.items() if k != "t"})
        elif t == "info":
            r.info = msg
            await self.log(f"[{r.id}] Robot identifié : {msg.get('nom')} ({msg.get('fw')}, {msg.get('servos')} axes)")
            if int(msg.get("servos", len(r.desc.noms))) != len(r.desc.noms):
                await self.log(f"[{r.id}] Le nombre d'axes du robot diffère de son profil !", "alerte")
        elif t == "err":
            await self.log(f"[{r.id}] {msg.get('msg')}", "info" if msg.get("niveau") == "info" else "alerte")

    # ── Envoi de commandes (toujours via la sécurité du robot visé) ─
    async def _envoyer(self, msg: dict[str, Any], robot: str | None = None) -> None:
        await self._r(robot).envoyer(msg)

    def _exiger_observateur(self, r: RobotConnecte) -> None:
        """Plan de prévention P2.1 v1.2 : un robot réel doté d'une zone d'exclusion ne bouge qu'en présence
        d'un observateur de sécurité déclaré pour la séance."""
        if r.reel and r.desc.rayon_exclusion_m and not self.observateur:
            raise CommandeRefusee(f"Observateur de sécurité requis pour {r.id} (zone d'exclusion de "
                                  f"{r.desc.rayon_exclusion_m} m, plan P2.1) : le déclarer présent avant tout mouvement")

    async def cmd_articulations(self, deg: list, ms: float, origine: str, robot: str | None = None) -> float:
        r = self._r(robot)
        self._exiger_observateur(r)
        actuelles = [x if x is not None else r.limites.repos[i] for i, x in enumerate(r.etat.get("deg") or r.limites.repos)]
        sures, duree, avert = r.securite.valider_articulations(deg, actuelles, ms)
        await r.envoyer({"t": "servos", "deg": [round(d, 1) for d in sures], "ms": int(duree)})
        self.seance.compter("commandes")
        self.seance.evenement("cmd", type="articulations", robot=r.id, origine=origine, demande=deg, envoye=sures,
                              ms=int(duree))
        for a in avert:
            await self.log(a, "avert")
        return duree

    async def cmd_propulsion(self, g: float, d: float, origine: str, ms: float = 400, robot: str | None = None) -> None:
        r = self._r(robot)
        self._exiger_observateur(r)
        g, d, avert = r.securite.valider_propulsion(g, d)
        if (g + d) > 0 and r.desc.rayon_exclusion_m and r.etat.get("dist") is not None \
                and r.etat["dist"] < r.desc.rayon_exclusion_m * 100:
            raise CommandeRefusee(f"Obstacle à {r.etat['dist']:.0f} cm, dans la zone d'exclusion de {r.id}")
        await r.envoyer({"t": "drive", "l": round(g, 3), "r": round(d, 3)})
        r.propulsion_jusqua = time.monotonic() + max(0.0, ms) / 1000
        r.etat["drive"] = [g, d]
        if origine != "manette" or abs(g) + abs(d) == 0:
            self.seance.evenement("cmd", type="propulsion", robot=r.id, origine=origine, g=g, d=d, ms=ms)
        self.seance.compter("commandes")
        for a in avert:
            await self.log(a, "avert")

    async def arret_urgence(self, motif: str, origine: str = "interface") -> None:
        """Arrêt global : tous les robots, toutes les séquences ; une fiche d'incident (R-08)."""
        for r in self.robots.values():
            r.securite.declencher_arret(motif)
            self._arreter_sequence(r.id)
            try:
                if r.pilote:
                    await r.pilote.envoyer({"t": "estop"})
            except Exception:
                pass
        self.seance.compter("arrets_urgence")
        try:
            fiche = self.gouv.incidents.creer(motif=motif, robot=self.actif_id, seance=self.seance.id, origine=origine,
                                              contexte={"robots": {r.id: {"deg": r.etat.get("deg"),
                                                                          "drive": r.etat.get("drive")}
                                                                   for r in self.robots.values()}})
            self.seance.evenement("incident", id=fiche["id"], motif=motif)
            await self.log(f"ARRÊT D'URGENCE — {motif} (fiche {fiche['id']} à qualifier sous 48 h)", "alerte")
        except OSError:
            await self.log(f"ARRÊT D'URGENCE — {motif}", "alerte")
        if hasattr(self, "scene"):
            self.scene.arret_logiciel()

    async def rearmer(self) -> None:
        for r in self.robots.values():
            r.securite.rearmer()
            if r.pilote and r.lien == "connecte":
                try:
                    await r.pilote.envoyer({"t": "reset"})
                except Exception:
                    pass
        await self.log("Système réarmé par l'opératrice (toute la flotte)")

    # ── Boucles de surveillance ───────────────────────────────
    async def boucle_surveillance(self) -> None:
        cdg_ui = self.cfg["securite"]["interface_perdue_ms"] / 1000
        while True:
            await asyncio.sleep(0.2)
            now = time.monotonic()
            for r in list(self.robots.values()):
                if r.lien == "connecte":
                    try:
                        await r.pilote.envoyer({"t": "hb"})
                    except Exception:
                        pass
                if any(abs(v) > 0 for v in r.etat.get("drive", [0, 0])) and now > r.propulsion_jusqua:
                    try:
                        await r.envoyer({"t": "drive", "l": 0, "r": 0})
                    except CommandeRefusee:
                        pass
                    r.etat["drive"] = [0, 0]
                if not self.clients and now - self.derniere_interface > cdg_ui and (
                        r.seq_tache or any(r.etat.get("drive", [0, 0]))):
                    self._arreter_sequence(r.id)
                    try:
                        await r.envoyer({"t": "drive", "l": 0, "r": 0})
                    except CommandeRefusee:
                        pass
                    self.seance.evenement("securite", robot=r.id, msg="interface perdue : mouvement interrompu")
                if r.muet(now):
                    r.lien = "muet"
                    await self.log(f"[{r.id}] Plus de télémétrie depuis 1 s", "alerte")
                elif r.lien == "muet" and now - r.derniere_tel < 0.5:
                    r.lien = "connecte"
                vb, seuil = r.etat.get("vbat"), r.desc.batterie_min_v or self.cfg["securite"]["batterie_min_v"]
                if vb is not None and seuil and vb < seuil and not r.alerte_batt:
                    r.alerte_batt = True
                    await self.log(f"[{r.id}] Batterie faible : {vb:.2f} V", "alerte")
            if self.clients:
                self.derniere_interface = now

    async def boucle_diffusion(self) -> None:
        n = 0
        while True:
            await asyncio.sleep(0.05)
            n += 1
            r = self.robot
            msg = {"type": "etat", **r.etat, "robot_id": r.id, "lien": r.lien, "arret": r.securite.arret_urgence,
                   "sequence": r.seq_nom, "seance": self.seance.id}
            if n % 10 == 0:
                msg["flotte"] = [x.resume() for x in self.robots.values()]
            await self.diffuser(msg)

    # ── Flotte ────────────────────────────────────────────────
    async def choisir_robot(self, rid: str) -> None:
        if rid not in self.robots:
            raise CommandeRefusee(f"Robot inconnu : {rid}")
        self.actif_id = rid
        self.agent.noms = self.noms
        await self.log(f"Robot actif : {self.robot.desc.nom} ({rid})")
        await self.diffuser(self.config_interface())
        await self.diffuser({"type": "sequences", "liste": self.lister_sequences()})

    async def activer_profil(self, rid: str, simulation: bool) -> None:
        d = next((x for x in self.profils_disponibles if x.id == rid), None)
        if d is None:
            raise CommandeRefusee(f"Profil inconnu : {rid}")
        if rid in self.robots:
            await self.robots[rid].arreter()
        from dataclasses import replace
        d = replace(d, simulation=bool(simulation) or bool(self.cfg.get("_forcer_sim")))
        r = RobotConnecte(d, self.dossier_sequences / d.id, self.donnees)
        if any(x.securite.arret_urgence for x in self.robots.values()):
            r.securite.declencher_arret("flotte à l'arrêt")
        self.robots[rid] = r
        r.demarrer(self._sur_message_robot, self.log)
        self.seance.evenement("flotte", action="activation", robot=rid, simulation=d.simulation)
        await self.log(f"Robot {rid} {'en simulation' if d.simulation else 'réel'} ajouté à la flotte")
        await self.diffuser(self.config_interface())

    async def retirer_robot(self, rid: str) -> None:
        if rid == next(iter(self.robots)):
            raise CommandeRefusee("Le robot de la console ne peut pas être retiré")
        r = self.robots.pop(rid, None)
        if r:
            self._arreter_sequence(rid)
            await r.arreter()
        if self.actif_id == rid:
            self.actif_id = next(iter(self.robots))
        await self.diffuser(self.config_interface())

    # ── Séquences (bibliothèque fermée du robot visé) ──────────
    def lister_sequences(self, robot: str | None = None) -> list[str]:
        return self._r(robot).biblio.lister()

    def statuts_sequences(self, robot: str | None = None) -> dict[str, str]:
        return self._r(robot).biblio.statuts()

    def lire_sequence(self, nom: str, robot: str | None = None) -> dict:
        try:
            return self._r(robot).biblio.lire(nom)
        except RefusBibliotheque as exc:
            raise CommandeRefusee(str(exc)) from exc

    def enregistrer_sequence(self, seq: dict, robot: str | None = None) -> str:
        try:
            return self._r(robot).biblio.enregistrer(seq)
        except RefusBibliotheque as exc:
            raise CommandeRefusee(str(exc)) from exc

    def _arreter_sequence(self, robot: str | None = "*") -> None:
        cibles = self.robots.values() if robot == "*" else [self._r(robot)]
        for r in cibles:
            if r.seq_tache and not r.seq_tache.done():
                r.seq_tache.cancel()
            r.seq_tache = None
            r.seq_nom = None

    async def jouer_sequence(self, nom: str, origine: str, robot: str | None = None) -> None:
        r = self._r(robot)
        seq = self.lire_sequence(nom, r.id)
        ok, facteur, motif = exigence(seq.get("statut", "brouillon"), r.reel)
        if not ok:
            raise CommandeRefusee(f"« {nom} » sur {r.id} : {motif}")
        if facteur < 1:
            await self.log(f"« {nom} » : {motif}", "avert")
        await self.jouer_images(nom, ralentir(seq["images"], facteur), origine, r.id,
                                essai=("robot" if r.reel else "sim", "lente" if facteur < 1 else "pleine"))

    async def jouer_images(self, nom: str, images: list[dict[str, Any]], origine: str, robot: str | None = None,
                           essai: tuple[str, str] | None = None) -> None:
        """Joue une suite d'images clés, chacune passant par la couche de sécurité ; une seule suite par robot.

        Les gestes calculés par le partenaire (variations, coprésence) ne figurent pas dans la bibliothèque
        fermée : sur un robot réel, ils ne sont permis que dans une séance S04 déclarée (règle « angles_s04 »)."""
        r = self._r(robot)
        if origine.startswith("partenaire:") and r.reel and self.ia_cfg["regle"] != "angles_s04":
            raise CommandeRefusee("Gestes calculés du partenaire refusés sur un robot réel hors séance S04 déclarée "
                                  "(bibliothèque fermée, G.5) ; employer la simulation")
        self._exiger_observateur(r)
        self._arreter_sequence(r.id)
        self.seance.compter("sequences_jouees")
        self.seance.evenement("sequence", action="debut", nom=nom, robot=r.id, origine=origine, images=len(images))

        async def jouer() -> None:
            complet = False
            try:
                for im in images:
                    duree = await self.cmd_articulations(im["deg"], float(im.get("ms", 800)), origine, r.id)
                    if im.get("roues") and r.limites.propulsion_active:
                        g, d = im["roues"]
                        await self.cmd_propulsion(g, d, origine, duree, r.id)
                    await asyncio.sleep((duree + float(im.get("pause_ms", 0))) / 1000)
                complet = True
                if not origine.startswith("partenaire:"):
                    await self.log(f"Séquence « {nom} » terminée ({r.id})")
                self.seance.evenement("sequence", action="fin", nom=nom, robot=r.id)
            except CommandeRefusee as exc:
                await self.log(f"Séquence « {nom} » interrompue : {exc}", "alerte")
            except asyncio.CancelledError:
                self.seance.evenement("sequence", action="interrompue", nom=nom, robot=r.id)
                raise
            finally:
                if essai:
                    try:
                        r.biblio.consigner_essai(nom, essai[0], essai[1], complet)
                    except (RefusBibliotheque, OSError):
                        pass
                if r.seq_nom == nom:
                    r.seq_nom = None
                    r.seq_tache = None

        r.seq_nom = nom
        r.seq_tache = asyncio.create_task(jouer())
        if not origine.startswith("partenaire:"):
            await self.log(f"Séquence « {nom} » lancée sur {r.id} ({len(images)} images)")

    # ── IA supervisée (journal des cinq opérations) ────────────
    def _tracer(self, operation: str, agent: tuple[str, str], donnees: dict, cycle: str | None) -> None:
        try:
            self.trace.emettre("CONSOLE", operation, agent, donnees, cycle=cycle)
        except (EvenementInvalide, OSError) as exc:
            self.seance.evenement("trace_refusee", operation=operation, motif=str(exc)[:300])

    async def ia_demander(self, texte: str) -> None:
        self.seance.compter("propositions_ia")
        pid = f"P{next(self._ids):03d}"
        cycle = f"{self.seance.id}-{pid}"
        self._tracer("consigne", ("personne", self.pseudo_operatrice), {"texte": texte, "robot": self.actif_id}, cycle)
        regle = self.ia_cfg["regle"]
        if regle == "angles_s04" and self.cfg["protocole"]["type"] != "S04":
            regle = "bibliotheque_fermee"   # le mode « angles proposés » est verrouillé hors séance S04
        prop = await self.agent.proposer(
            texte, self.etat,
            {"min_deg": self.limites.min_deg, "max_deg": self.limites.max_deg,
             "repos": self.limites.repos, "propulsion_active": self.limites.propulsion_active},
            self.lister_sequences(), regle)
        conf_verif, motif = self._verifier_proposition(prop)
        prop["confiance_declaree"] = prop["confiance"]
        prop["confiance_verification"] = conf_verif
        prop["confiance"] = round(min(prop["confiance"], conf_verif), 3)
        prop["motif_verification"] = motif
        seuil = float(self.ia_cfg["seuil_confiance"])
        if regle == "bibliotheque_fermee" and prop["action"] not in ACTIONS_FERMEES:
            prop["statut"] = "refusee_regle"
            prop["motif_verification"] = ("Règle de la bibliothèque fermée (G.5, P2.1 §6.4) : seuls des gestes "
                                          "nommés peuvent être proposés hors séance S04 déclarée")
            prop["confiance"] = 0.0
        else:
            prop["statut"] = "a_valider" if prop["confiance"] >= seuil and prop["action"] != "aucune" else "bloquee"
        prop.update({"id": pid, "consigne": texte, "seuil": seuil, "regle_effective": regle, "robot": self.actif_id,
                     "cycle": cycle})
        self.propositions[pid] = prop
        if prop["statut"] != "a_valider":
            self.seance.compter("ia_bloquees_seuil")
        tm = prop.pop("trace_modele")
        self._tracer("generation", ("systeme", tm["systeme"]),
                     {**tm, "type_texte": "geste", "consigne": prop["prompt"], "contexte": f"robot {self.actif_id}",
                      "propositions": [json.dumps({"action": prop["action"], "parametres": prop["parametres"]},
                                                  ensure_ascii=False)], "numero": 1}, cycle)
        if prop["statut"] != "a_valider":
            self._tracer("selection", ("personne", self.pseudo_operatrice),
                         {"generation": 1, "proposition": 1, "decision": "rejetee",
                          "motif": f"{prop['statut']} : {prop['motif_verification']}"[:200]}, cycle)
        self.seance.evenement("ia", **{k: v for k, v in prop.items()})
        await self.diffuser({"type": "ia_proposition",
                             **{k: v for k, v in prop.items() if k not in ("prompt", "brut")}})
        if prop["statut"] == "a_valider" and self.ia_cfg.get("execution_auto"):
            await self.ia_valider(pid, auto=True)

    def _verifier_proposition(self, prop: dict) -> tuple[float, str]:
        """Contrôle déterministe, indépendant du modèle."""
        a, p = prop.get("action"), prop.get("parametres", {})
        if a == "aucune":
            return 0.0, "Aucune action proposée"
        if a == "repos":
            return 1.0, "Position de repos (connue et sûre)"
        if a == "sequence":
            if p.get("nom") not in self.lister_sequences():
                return 0.0, "Séquence inexistante"
            ok, _, motif = exigence(self.statuts_sequences().get(p["nom"], "brouillon"), self.robot.reel)
            return (1.0, f"Séquence de la bibliothèque ({motif})") if ok else (0.0, motif)
        if a == "propulsion":
            if not self.limites.propulsion_active:
                return 0.0, "Robot sans propulsion"
            try:
                g, d, ms = float(p.get("g", 0)), float(p.get("d", 0)), float(p.get("ms", 0))
            except (TypeError, ValueError):
                return 0.0, "Paramètres de propulsion invalides"
            if ms > 3000:
                return 0.4, "Durée de déplacement trop longue (> 3 s)"
            dist = self.etat.get("dist")
            if (g + d) > 0 and dist is not None and dist < 40:
                return 0.3, f"Obstacle à {dist:.0f} cm devant le robot"
            if max(abs(g), abs(d)) > self.limites.propulsion_max:
                return 0.7, "Vitesse au-delà du plafond (sera plafonnée)"
            return 1.0, "Déplacement dans les limites"
        if a == "articulations":
            deg = p.get("deg")
            if not isinstance(deg, list) or len(deg) != len(self.noms):
                return 0.0, "Liste d'angles invalide"
            ecart_max = 0.0
            for i, v in enumerate(deg):
                if v is None:
                    continue
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    return 0.0, "Angle non numérique"
                ecart_max = max(ecart_max, abs(v - self.securite.borner(i, v)))
            if ecart_max > 10:
                return 0.5, f"Angle hors limites de {ecart_max:.0f}° (sera borné)"
            return 1.0, "Angles dans les limites"
        return 0.0, f"Action inconnue : {a}"

    async def ia_valider(self, pid: str, auto: bool = False) -> None:
        prop = self.propositions.get(pid)
        if not prop or prop["statut"] != "a_valider":
            raise CommandeRefusee("Proposition introuvable ou non validable")
        a, p = prop["action"], prop["parametres"]
        origine = f"ia:{pid}"
        if a == "articulations":
            await self.cmd_articulations(p["deg"], float(p.get("ms", 1000)), origine, prop["robot"])
        elif a == "propulsion":
            await self.cmd_propulsion(float(p.get("g", 0)), float(p.get("d", 0)), origine,
                                      min(3000.0, float(p.get("ms", 1000))), prop["robot"])
        elif a == "sequence":
            await self.jouer_sequence(p["nom"], origine, prop["robot"])
        elif a == "repos":
            await self.cmd_articulations(list(self._r(prop["robot"]).limites.repos), 1500, origine, prop["robot"])
        prop["statut"] = "executee_auto" if auto else "validee"
        self.seance.compter("ia_validees")
        self.seance.evenement("ia_decision", id=pid, decision=prop["statut"])
        c = prop["cycle"]
        self._tracer("selection", ("personne", self.pseudo_operatrice),
                     {"generation": 1, "proposition": 1, "decision": "retenue", "motif": prop["statut"]}, c)
        self._tracer("transformation", ("personne", self.pseudo_operatrice),
                     {"generation": 1, "proposition": 1, "version": f"{a} {json.dumps(p, ensure_ascii=False)}",
                      "ecart": 0.0, "conservation": 1.0, "note": "geste joué tel que proposé"}, c)
        self._tracer("attribution", ("personne", self.pseudo_operatrice),
                     {"generation": 1, "proposition": 1, "etiquette": "systeme",
                      "credit": f"proposition du système validée par {self.pseudo_operatrice}"}, c)
        await self.diffuser({"type": "ia_statut", "id": pid, "statut": prop["statut"]})
        await self.log(f"Proposition {pid} {'exécutée automatiquement' if auto else 'validée'} : {a}")

    async def ia_rejeter(self, pid: str) -> None:
        prop = self.propositions.get(pid)
        if not prop:
            return
        prop["statut"] = "rejetee"
        self.seance.compter("ia_rejetees")
        self.seance.evenement("ia_decision", id=pid, decision="rejetee")
        self._tracer("selection", ("personne", self.pseudo_operatrice),
                     {"generation": 1, "proposition": 1, "decision": "rejetee", "motif": "rejet de l'opératrice"},
                     prop["cycle"])
        await self.diffuser({"type": "ia_statut", "id": pid, "statut": "rejetee"})

    # ── Messages de l'interface ───────────────────────────────
    async def traiter(self, ws: web.WebSocketResponse, m: dict[str, Any]) -> None:
        op = m.get("op")
        if isinstance(op, str) and op.startswith("p_"):
            await self._traiter_partenaire(ws, m)
            return
        rob = m.get("robot")
        try:
            if op == "estop":
                await self.arret_urgence(m.get("motif", "bouton de l'interface"))
            elif op == "rearmer":
                await self.rearmer()
            elif op == "articulations":
                origine = "avatar" if m.get("origine") == "avatar" else "manuel"
                await self.cmd_articulations(m["deg"], float(m.get("ms", 0)), origine, rob)
            elif op == "articulation":
                deg = [None] * len(self._r(rob).desc.noms)
                deg[int(m["i"])] = float(m["deg"])
                await self.cmd_articulations(deg, float(m.get("ms", 0)), "manuel", rob)
            elif op == "propulsion":
                await self.cmd_propulsion(float(m["g"]), float(m["d"]), "manette", 400, rob)
            elif op == "repos":
                self._arreter_sequence(rob)
                await self.cmd_articulations(list(self._r(rob).limites.repos), 1500, "manuel", rob)
            elif op == "seq_lister":
                await ws.send_json({"type": "sequences", "liste": self.lister_sequences(rob),
                                    "statuts": self.statuts_sequences(rob)})
            elif op == "seq_lire":
                await ws.send_json({"type": "sequence", "sequence": self.lire_sequence(m["nom"], rob)})
            elif op == "seq_enregistrer":
                nom = self.enregistrer_sequence(m["sequence"], rob)
                await self.log(f"Séquence « {nom} » enregistrée (statut : brouillon tant qu'elle n'est pas validée)")
                await self.diffuser({"type": "sequences", "liste": self.lister_sequences(rob),
                                     "statuts": self.statuts_sequences(rob)})
            elif op == "seq_jouer":
                await self.jouer_sequence(m["nom"], "manuel", rob)
            elif op == "seq_arreter":
                self._arreter_sequence(rob or "*")
                await self.log("Séquence arrêtée")
            elif op == "seq_statut":
                try:
                    d = self._r(rob).biblio.promouvoir(m["nom"], m["statut"], m.get("auteur", ""), m.get("note", ""))
                except RefusBibliotheque as exc:
                    raise CommandeRefusee(str(exc)) from exc
                self.seance.evenement("validation_geste", robot=self._r(rob).id, nom=m["nom"], statut=d["statut"],
                                      auteur=m.get("auteur"))
                await self.log(f"« {m['nom']} » promue au statut « {d['statut']} » par {m.get('auteur')}")
                await self.diffuser({"type": "sequences", "liste": self.lister_sequences(rob),
                                     "statuts": self.statuts_sequences(rob)})
            elif op == "ia_demander":
                texte = str(m.get("texte", "")).strip()[:500]
                if texte:
                    await self.ia_demander(texte)
            elif op == "ia_valider":
                await self.ia_valider(m["id"])
            elif op == "ia_rejeter":
                await self.ia_rejeter(m["id"])
            elif op == "seuil":
                v = max(0.0, min(1.0, float(m["valeur"])))
                self.ia_cfg["seuil_confiance"] = v
                self.seance.meta["parametres"]["ia"]["seuil_confiance"] = v
                self.seance.sauvegarder()
                await self.log(f"Seuil de confiance réglé à {v:.2f}")
                await self.diffuser(self.config_interface())
            elif op == "regle_ia":
                v = m.get("valeur")
                if v not in ("bibliotheque_fermee", "angles_s04"):
                    raise CommandeRefusee("Règle inconnue")
                if v == "angles_s04" and self.cfg["protocole"]["type"] != "S04":
                    raise CommandeRefusee("Le mode « angles proposés » n'est permis que dans une séance S04 déclarée")
                self.ia_cfg["regle"] = v
                self.seance.meta["regle_ia"] = v
                self.seance.sauvegarder()
                await self.log(f"Règle de l'IA : {v}")
                await self.diffuser(self.config_interface())
            elif op == "observateur":
                if m.get("present"):
                    ini = str(m.get("initiales", "")).strip()[:12]
                    if not ini:
                        raise CommandeRefusee("Initiales de l'observateur requises")
                    self.observateur = {"initiales": ini, "depuis": time.strftime("%H:%M:%S")}
                else:
                    self.observateur = None
                self.seance.evenement("observateur", present=bool(self.observateur), initiales=(self.observateur or {}).get("initiales"))
                await self.log(f"Observateur de sécurité {'présent : ' + self.observateur['initiales'] if self.observateur else 'absent'}")
                await self.diffuser(self.config_interface())
            elif op == "robot_choisir":
                await self.choisir_robot(m["robot"])
            elif op == "robot_activer":
                await self.activer_profil(m["robot"], bool(m.get("simulation", True)))
            elif op == "robot_retirer":
                await self.retirer_robot(m["robot"])
            elif op == "note":
                texte = str(m.get("texte", "")).strip()
                if texte:
                    self.seance.note(texte)
                    await self.log(f"Note : {texte}")
            elif op == "transformation_de_tete":
                from .trace.saisies import transformation_de_tete
                transformation_de_tete(self.trace, pseudonyme=str(m.get("pseudonyme") or self.pseudo_operatrice),
                                       description=str(m.get("description", "")), cycle=m.get("cycle") or None,
                                       debut_saisie=m.get("debut"))
                await self.log("Transformation « de tête » consignée (trace reconstituée)")
            elif op == "operation_autre":
                from .trace.saisies import autre
                autre(self.trace, pseudonyme=str(m.get("pseudonyme") or self.pseudo_operatrice),
                      categorie=str(m.get("categorie", "")), description=str(m.get("description", "")))
                await self.log(f"Opération « autre » consignée ({m.get('categorie')})")
            elif op == "cloturer":
                self.seance.cloturer()
                await self.log(f"Séance {self.seance.id} clôturée ; nouvelle séance ouverte")
                self._ouvrir_seance()
                await self.ouvrir_modeles()
                await self.diffuser(self.config_interface())
        except CommandeRefusee as exc:
            self.seance.compter("commandes_refusees")
            self.seance.evenement("refus", op=op, motif=str(exc))
            await ws.send_json({"type": "journal", "niveau": "refus", "msg": str(exc),
                                "ts": time.strftime("%H:%M:%S")})
        except (VerrouGouvernance, EvenementInvalide, ValueError, KeyError, TypeError) as exc:
            niveau = "refus" if isinstance(exc, VerrouGouvernance) else "alerte"
            await ws.send_json({"type": "journal", "niveau": niveau,
                                "msg": f"{exc}" if niveau == "refus" else f"Message mal formé ({op}) : {exc}",
                                "ts": time.strftime("%H:%M:%S")})

    async def _traiter_partenaire(self, ws: web.WebSocketResponse, m: dict[str, Any]) -> None:
        op = m["op"]
        try:
            await self.partenaire.traiter(ws, m)
        except CommandeRefusee as exc:
            self.seance.compter("commandes_refusees")
            self.seance.evenement("refus", op=op, motif=str(exc))
            await ws.send_json({"type": "p_erreur", "op": op, "msg": str(exc)})
        except PermissionError as exc:
            await ws.send_json({"type": "p_erreur", "op": op, "msg": str(exc)})
        except (KeyError, ValueError, TypeError) as exc:
            await ws.send_json({"type": "p_erreur", "op": op, "msg": f"{exc}"})
        except Exception as exc:  # réseau (DraCor), fichier illisible…
            self.seance.evenement("erreur", op=op, msg=repr(exc))
            await ws.send_json({"type": "p_erreur", "op": op, "msg": f"{type(exc).__name__} : {exc}"})


CTL: web.AppKey["Controleur"] = web.AppKey("ctl")
TACHES: web.AppKey[list] = web.AppKey("taches")


def origine_autorisee(request: web.Request, autorisees: list[str]) -> bool:
    """Protection contre le détournement de WebSocket inter-sites : sans ce contrôle,
    n'importe quelle page ouverte dans le navigateur pourrait commander le robot."""
    origine = request.headers.get("Origin")
    if not origine:
        return True  # client hors navigateur (scripts locaux, tests)
    u = urlparse(origine)
    if u.hostname in ("127.0.0.1", "localhost", "::1"):
        return True  # page servie par cette machine
    if u.netloc and u.netloc == request.host:
        return True  # même origine (tablette sur le réseau de scène, hote = 0.0.0.0)
    return origine.rstrip("/") in {o.rstrip("/") for o in autorisees}


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    ctl: Controleur = request.app[CTL]
    if not origine_autorisee(request, ctl.cfg["serveur"].get("origines_autorisees", [])):
        ctl.seance.evenement("securite", msg="connexion refusée", origine=request.headers.get("Origin"))
        raise web.HTTPForbidden(text="Origine non autorisée par le pont ROBO-SCÈNE")
    ws = web.WebSocketResponse(heartbeat=5, max_msg_size=8 * 1024 * 1024)
    await ws.prepare(request)
    ctl.clients.add(ws)
    await ws.send_json(ctl.config_interface())
    await ws.send_json({"type": "sequences", "liste": ctl.lister_sequences(), "statuts": ctl.statuts_sequences()})
    await ctl.log("Interface connectée")
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    m = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                await ctl.traiter(ws, m)
    finally:
        ctl.clients.discard(ws)
        if not ctl.clients:
            ctl.derniere_interface = time.monotonic()
            # Propulsion coupée immédiatement si plus personne ne pilote
            for r in ctl.robots.values():
                try:
                    await r.envoyer({"t": "drive", "l": 0, "r": 0})
                    r.etat["drive"] = [0, 0]
                except CommandeRefusee:
                    pass
        await ctl.log("Interface déconnectée", "avert")
    return ws


def _page(nom: str):
    async def servir(_: web.Request) -> web.FileResponse:
        return web.FileResponse(RACINE / "web" / nom)
    return servir


@web.middleware
async def _revalider(request: web.Request, handler):
    """Pages et scripts de l'interface : toujours revalidés (ETag / Last-Modified), jamais pris tels quels dans le
    cache du navigateur ; sans cela, une mise à jour de web/ restait invisible tant que le cache n'expirait pas."""
    reponse = await handler(request)
    if request.method in ("GET", "HEAD") and not request.path.startswith(("/api", "/ws")):
        reponse.headers.setdefault("Cache-Control", "no-cache")
    return reponse


def creer_app(cfg: dict[str, Any]) -> web.Application:
    app = web.Application(client_max_size=16 * 1024 * 1024, middlewares=[_revalider])
    app[CTL] = ctl = Controleur(cfg)

    async def demarrer(app: web.Application) -> None:
        for r in ctl.robots.values():
            r.demarrer(ctl._sur_message_robot, ctl.log)
        app[TACHES] = [asyncio.create_task(ctl.boucle_surveillance()),
                       asyncio.create_task(ctl.boucle_diffusion()),
                       asyncio.create_task(ctl.ouvrir_modeles())]

    async def arreter(app: web.Application) -> None:
        for r in ctl.robots.values():
            try:
                await r.envoyer({"t": "drive", "l": 0, "r": 0})
            except Exception:
                pass
        for t in app[TACHES]:
            t.cancel()
        for r in ctl.robots.values():
            await r.arreter()
        ctl.seance.cloturer()

    app.on_startup.append(demarrer)
    app.on_cleanup.append(arreter)
    app.router.add_get("/", _page("index.html"))
    app.router.add_get("/console", _page("index.html"))      # même adresse que sur Netlify
    app.router.add_get("/partenaire", _page("partenaire.html"))
    app.router.add_get("/avatar", _page("avatar.html"))
    app.router.add_get("/ws", ws_handler)
    from . import plateforme
    plateforme.monter(app, ctl)
    app.router.add_static("/static", RACINE / "web")
    return app


def charger_config(chemin: Path) -> dict[str, Any]:
    with open(chemin, "rb") as f:
        return tomllib.load(f)


def main() -> None:
    ap = argparse.ArgumentParser(description="Plateforme ROBO-SCÈNE — L'IA au service de la création théâtrale")
    ap.add_argument("--config", default=str(RACINE / "config.toml"))
    ap.add_argument("--sim", action="store_true", help="forcer la simulation de tous les robots")
    ap.add_argument("--port", type=int)
    a = ap.parse_args()
    cfg = charger_config(Path(a.config))
    if a.sim:
        cfg["robot"]["transport"] = "sim"
        cfg["_forcer_sim"] = True
    port = a.port or cfg["serveur"]["port"]
    print(f"ROBO-SCÈNE → http://{cfg['serveur']['hote']}:{port}  (robot de la console : {cfg['robot']['transport']})")
    web.run_app(creer_app(cfg), host=cfg["serveur"]["hote"], port=port, print=None)


if __name__ == "__main__":
    main()
