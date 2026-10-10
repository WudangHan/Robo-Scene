"""Serveur-pont ROBO-SCÈNE.

    python -m bridge.serveur            (depuis le dossier robo-scene-console)
    python -m bridge.serveur --sim      (force le robot simulé)

Sert l'interface web sur http://127.0.0.1:8765 et relaie, à travers la
couche de sécurité, les commandes de l'interface vers le robot.
"""
from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import re
import time
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from aiohttp import WSMsgType, web

from .ia import Agent
from .journal import Seance
from .securite import CommandeRefusee, Limites, Securite
from .transports import TransportSerie, TransportSimule, TransportTCP

RACINE = Path(__file__).resolve().parent.parent


class Controleur:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        art = cfg["robot"]["articulations"]
        sec = cfg["securite"]
        self.noms: list[str] = art["noms"]
        self.limites = Limites(
            min_deg=[float(x) for x in art["min_deg"]],
            max_deg=[float(x) for x in art["max_deg"]],
            repos=[float(x) for x in art["repos"]],
            vitesse_max_deg_s=float(sec["vitesse_max_deg_s"]),
            propulsion_max=float(sec["propulsion_max"]),
            propulsion_active=bool(cfg["robot"]["propulsion"]["active"]),
        )
        self.securite = Securite(self.limites)
        self.ia_cfg = dict(cfg["ia"])
        self.agent = Agent(self.ia_cfg, self.noms)
        self.clients: set[web.WebSocketResponse] = set()
        self.etat: dict[str, Any] = {"deg": list(self.limites.repos), "drive": [0, 0]}
        self.lien = "deconnecte"
        self.derniere_tel = 0.0
        self.info_robot: dict[str, Any] = {}
        self.transport = None
        self.propulsion_jusqua = 0.0
        self.derniere_interface = time.monotonic()
        self.seq_tache: asyncio.Task | None = None
        self.seq_nom: str | None = None
        self.propositions: dict[str, dict] = {}
        self._ids = itertools.count(1)
        self._decim = 0
        self.dossier_seq = RACINE / "sequences"
        self.dossier_seq.mkdir(exist_ok=True)
        p = cfg["protocole"]
        self.seance = Seance(
            RACINE / p["dossier_corpus"], p["systeme"], p["type"], p.get("operatrice", ""),
            config={k: cfg[k] for k in ("robot", "securite", "ia")},
            transport=cfg["robot"]["transport"],
        )
        self.seance.meta["moteur_ia"] = self.agent.moteur
        from .partenaire.controleur import Partenaire
        self.partenaire = Partenaire(self, cfg.get("partenaire", {}))

    # ── Diffusion vers l'interface ────────────────────────────
    async def diffuser(self, msg: dict[str, Any]) -> None:
        if not self.clients:
            return
        data = json.dumps(msg, ensure_ascii=False)
        for ws in list(self.clients):
            try:
                await ws.send_str(data)
            except ConnectionResetError:
                self.clients.discard(ws)

    async def log(self, msg: str, niveau: str = "info") -> None:
        self.seance.evenement("journal", niveau=niveau, msg=msg)
        await self.diffuser({"type": "journal", "niveau": niveau, "msg": msg,
                             "ts": time.strftime("%H:%M:%S")})

    def config_interface(self) -> dict[str, Any]:
        return {
            "type": "config",
            "noms": self.noms,
            "min_deg": self.limites.min_deg,
            "max_deg": self.limites.max_deg,
            "repos": self.limites.repos,
            "propulsion": self.limites.propulsion_active,
            "propulsion_max": self.limites.propulsion_max,
            "vitesse_max": self.limites.vitesse_max_deg_s,
            "batterie_min_v": self.cfg["securite"]["batterie_min_v"],
            "seuil": self.ia_cfg["seuil_confiance"],
            "execution_auto": self.ia_cfg["execution_auto"],
            "moteur_ia": self.agent.moteur,
            "seance": self.seance.id,
            "transport": self.cfg["robot"]["transport"],
            "robot": self.cfg["robot"]["nom"],
        }

    # ── Connexion au robot ────────────────────────────────────
    def _creer_transport(self):
        r = self.cfg["robot"]
        t = r["transport"]
        if t == "serie":
            return TransportSerie(r["port_serie"], int(r["debit"]))
        if t == "tcp":
            return TransportTCP(r["hote_tcp"], int(r["port_tcp"]))
        return TransportSimule(len(self.noms), self.limites.repos,
                               self.limites.propulsion_active,
                               int(self.cfg["securite"]["chien_de_garde_ms"]))

    async def boucle_robot(self) -> None:
        while True:
            self.transport = self._creer_transport()
            try:
                await self.transport.ouvrir()
                self.lien = "connecte"
                await self.log(f"Lien établi ({self.transport.nom})")
                await self.transport.envoyer({"t": "hello"})
                while True:
                    msg = await self.transport.recevoir()
                    if msg.get("t") == "lien" and msg.get("etat") == "perdu":
                        raise ConnectionError(msg.get("msg", "lien perdu"))
                    await self._sur_message_robot(msg)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.lien = "deconnecte"
                await self.log(f"Lien robot indisponible : {exc} — nouvel essai dans 3 s", "alerte")
                try:
                    await self.transport.fermer()
                except Exception:
                    pass
                await asyncio.sleep(3)

    async def _sur_message_robot(self, msg: dict[str, Any]) -> None:
        t = msg.get("t")
        if t == "tel":
            self.derniere_tel = time.monotonic()
            self.etat.update({k: v for k, v in msg.items() if k != "t"})
            if msg.get("estop") and not self.securite.arret_urgence:
                # Arrêt déclenché côté robot (bouton physique, chien de garde…)
                self.securite.declencher_arret("signalé par le robot")
                self.seance.compter("arrets_urgence")
                await self.log("Arrêt d'urgence signalé par le robot", "alerte")
            self._decim += 1
            if self._decim % 4 == 0:  # télémétrie archivée à 5 Hz
                self.seance.evenement("tel", **{k: v for k, v in msg.items() if k != "t"})
        elif t == "info":
            self.info_robot = msg
            await self.log(f"Robot identifié : {msg.get('nom')} (micrologiciel {msg.get('fw')}, "
                           f"{msg.get('servos')} servos)")
            if int(msg.get("servos", len(self.noms))) != len(self.noms):
                await self.log("Le nombre de servos du robot diffère de la configuration !", "alerte")
        elif t == "err":
            await self.log(f"Robot : {msg.get('msg')}", "alerte")

    # ── Envoi de commandes (toujours via la sécurité) ─────────
    async def _envoyer(self, msg: dict[str, Any]) -> None:
        if self.lien != "connecte" or self.transport is None:
            raise CommandeRefusee("Robot non connecté")
        await self.transport.envoyer(msg)

    async def cmd_articulations(self, deg: list, ms: float, origine: str) -> float:
        actuelles = list(self.etat.get("deg") or self.limites.repos)
        sures, duree, avert = self.securite.valider_articulations(deg, actuelles, ms)
        await self._envoyer({"t": "servos", "deg": [round(d, 1) for d in sures], "ms": int(duree)})
        self.seance.compter("commandes")
        self.seance.evenement("cmd", type="articulations", origine=origine,
                              demande=deg, envoye=sures, ms=int(duree))
        for a in avert:
            await self.log(a, "avert")
        return duree

    async def cmd_propulsion(self, g: float, d: float, origine: str, ms: float = 400) -> None:
        g, d, avert = self.securite.valider_propulsion(g, d)
        await self._envoyer({"t": "drive", "l": round(g, 3), "r": round(d, 3)})
        self.propulsion_jusqua = time.monotonic() + max(0.0, ms) / 1000
        self.etat["drive"] = [g, d]
        if origine != "manette" or abs(g) + abs(d) == 0:
            self.seance.evenement("cmd", type="propulsion", origine=origine, g=g, d=d, ms=ms)
        self.seance.compter("commandes")
        for a in avert:
            await self.log(a, "avert")

    async def arret_urgence(self, motif: str) -> None:
        self.securite.declencher_arret(motif)
        self.seance.compter("arrets_urgence")
        self._arreter_sequence()
        try:
            if self.transport:
                await self.transport.envoyer({"t": "estop"})
        except Exception:
            pass
        await self.log(f"ARRÊT D'URGENCE — {motif}", "alerte")

    async def rearmer(self) -> None:
        self.securite.rearmer()
        if self.transport and self.lien == "connecte":
            await self.transport.envoyer({"t": "reset"})
        await self.log("Système réarmé par l'opératrice")

    # ── Boucles de surveillance ───────────────────────────────
    async def boucle_surveillance(self) -> None:
        cdg_ui = self.cfg["securite"]["interface_perdue_ms"] / 1000
        alerte_batt = False
        while True:
            await asyncio.sleep(0.2)
            now = time.monotonic()
            # Battement de cœur : sans lui, le micrologiciel coupe la propulsion
            if self.lien == "connecte":
                try:
                    await self.transport.envoyer({"t": "hb"})
                except Exception:
                    pass
            # Homme mort de la manette : la propulsion expire d'elle-même
            if any(abs(v) > 0 for v in self.etat.get("drive", [0, 0])) and now > self.propulsion_jusqua:
                try:
                    await self._envoyer({"t": "drive", "l": 0, "r": 0})
                except CommandeRefusee:
                    pass
                self.etat["drive"] = [0, 0]
            # Interface perdue : on arrête ce qui bouge
            if self.clients:
                self.derniere_interface = now
            elif now - self.derniere_interface > cdg_ui and (
                    self.seq_tache or any(self.etat.get("drive", [0, 0]))):
                self._arreter_sequence()
                try:
                    await self._envoyer({"t": "drive", "l": 0, "r": 0})
                except CommandeRefusee:
                    pass
                self.seance.evenement("securite", msg="interface perdue : mouvement interrompu")
            # Télémétrie muette
            if self.lien == "connecte" and self.derniere_tel and now - self.derniere_tel > 1.0:
                self.lien = "muet"
                await self.log("Plus de télémétrie depuis 1 s", "alerte")
            elif self.lien == "muet" and now - self.derniere_tel < 0.5:
                self.lien = "connecte"
            vb = self.etat.get("vbat")
            if vb is not None and vb < self.cfg["securite"]["batterie_min_v"] and not alerte_batt:
                alerte_batt = True
                await self.log(f"Batterie faible : {vb:.2f} V", "alerte")

    async def boucle_diffusion(self) -> None:
        while True:
            await asyncio.sleep(0.05)
            await self.diffuser({
                "type": "etat", **self.etat, "lien": self.lien,
                "arret": self.securite.arret_urgence, "sequence": self.seq_nom,
                "seance": self.seance.id,
            })

    # ── Séquences ─────────────────────────────────────────────
    def lister_sequences(self) -> list[str]:
        return sorted(p.stem for p in self.dossier_seq.glob("*.json"))

    def _chemin_seq(self, nom: str) -> Path:
        sur = re.sub(r"[^\w\- ]", "", nom, flags=re.UNICODE).strip()
        if not sur:
            raise CommandeRefusee("Nom de séquence invalide")
        return self.dossier_seq / f"{sur}.json"

    def lire_sequence(self, nom: str) -> dict:
        p = self._chemin_seq(nom)
        if not p.exists():
            raise CommandeRefusee(f"Séquence inconnue : {nom}")
        return json.loads(p.read_text(encoding="utf-8"))

    def enregistrer_sequence(self, seq: dict) -> str:
        images = seq.get("images") or []
        if not images:
            raise CommandeRefusee("Séquence vide")
        for im in images:
            if len(im.get("deg", [])) != len(self.noms):
                raise CommandeRefusee("Chaque image doit fixer tous les angles")
        p = self._chemin_seq(seq.get("nom", ""))
        p.write_text(json.dumps({"nom": p.stem, "images": images}, ensure_ascii=False, indent=2),
                     encoding="utf-8")
        return p.stem

    def _arreter_sequence(self) -> None:
        if self.seq_tache and not self.seq_tache.done():
            self.seq_tache.cancel()
        self.seq_tache = None
        self.seq_nom = None

    async def jouer_sequence(self, nom: str, origine: str) -> None:
        seq = self.lire_sequence(nom)
        await self.jouer_images(nom, seq["images"], origine)

    async def jouer_images(self, nom: str, images: list[dict[str, Any]], origine: str) -> None:
        """Joue une suite d'images clés (séquence enregistrée ou geste du partenaire),
        chacune passant par la couche de sécurité ; une seule suite à la fois."""
        self._arreter_sequence()
        self.seance.compter("sequences_jouees")
        self.seance.evenement("sequence", action="debut", nom=nom, origine=origine, images=len(images))

        async def jouer() -> None:
            try:
                for im in images:
                    duree = await self.cmd_articulations(im["deg"], float(im.get("ms", 800)), origine)
                    if im.get("roues") and self.limites.propulsion_active:
                        g, d = im["roues"]
                        await self.cmd_propulsion(g, d, origine, duree)
                    await asyncio.sleep((duree + float(im.get("pause_ms", 0))) / 1000)
                if not origine.startswith("partenaire:"):
                    await self.log(f"Séquence « {nom} » terminée")
                self.seance.evenement("sequence", action="fin", nom=nom)
            except CommandeRefusee as exc:
                await self.log(f"Séquence « {nom} » interrompue : {exc}", "alerte")
            except asyncio.CancelledError:
                self.seance.evenement("sequence", action="interrompue", nom=nom)
                raise
            finally:
                if self.seq_nom == nom:
                    self.seq_nom = None
                    self.seq_tache = None

        self.seq_nom = nom
        self.seq_tache = asyncio.create_task(jouer())
        if not origine.startswith("partenaire:"):
            await self.log(f"Séquence « {nom} » lancée ({len(images)} images)")

    # ── IA supervisée ─────────────────────────────────────────
    async def ia_demander(self, texte: str) -> None:
        self.seance.compter("propositions_ia")
        prop = await self.agent.proposer(
            texte, self.etat,
            {"min_deg": self.limites.min_deg, "max_deg": self.limites.max_deg,
             "repos": self.limites.repos, "propulsion_active": self.limites.propulsion_active},
            self.lister_sequences(),
        )
        conf_verif, motif = self._verifier_proposition(prop)
        prop["confiance_declaree"] = prop["confiance"]
        prop["confiance_verification"] = conf_verif
        prop["confiance"] = round(min(prop["confiance"], conf_verif), 3)
        prop["motif_verification"] = motif
        seuil = float(self.ia_cfg["seuil_confiance"])
        prop["statut"] = "a_valider" if prop["confiance"] >= seuil and prop["action"] != "aucune" else "bloquee"
        pid = f"P{next(self._ids):03d}"
        prop["id"] = pid
        prop["consigne"] = texte
        prop["seuil"] = seuil
        self.propositions[pid] = prop
        if prop["statut"] == "bloquee":
            self.seance.compter("ia_bloquees_seuil")
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
            return (1.0, "Séquence enregistrée") if p.get("nom") in self.lister_sequences() \
                else (0.0, "Séquence inexistante")
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
            await self.cmd_articulations(p["deg"], float(p.get("ms", 1000)), origine)
        elif a == "propulsion":
            await self.cmd_propulsion(float(p.get("g", 0)), float(p.get("d", 0)), origine,
                                      min(3000.0, float(p.get("ms", 1000))))
        elif a == "sequence":
            await self.jouer_sequence(p["nom"], origine)
        elif a == "repos":
            await self.cmd_articulations(list(self.limites.repos), 1500, origine)
        prop["statut"] = "executee_auto" if auto else "validee"
        self.seance.compter("ia_validees")
        self.seance.evenement("ia_decision", id=pid, decision=prop["statut"])
        await self.diffuser({"type": "ia_statut", "id": pid, "statut": prop["statut"]})
        await self.log(f"Proposition {pid} {'exécutée automatiquement' if auto else 'validée'} : {a}")

    async def ia_rejeter(self, pid: str) -> None:
        prop = self.propositions.get(pid)
        if not prop:
            return
        prop["statut"] = "rejetee"
        self.seance.compter("ia_rejetees")
        self.seance.evenement("ia_decision", id=pid, decision="rejetee")
        await self.diffuser({"type": "ia_statut", "id": pid, "statut": "rejetee"})

    # ── Messages de l'interface ───────────────────────────────
    async def traiter(self, ws: web.WebSocketResponse, m: dict[str, Any]) -> None:
        op = m.get("op")
        if isinstance(op, str) and op.startswith("p_"):
            await self._traiter_partenaire(ws, m)
            return
        try:
            if op == "estop":
                await self.arret_urgence(m.get("motif", "bouton de l'interface"))
            elif op == "rearmer":
                await self.rearmer()
            elif op == "articulations":
                await self.cmd_articulations(m["deg"], float(m.get("ms", 0)), "manuel")
            elif op == "articulation":
                deg = [None] * len(self.noms)
                deg[int(m["i"])] = float(m["deg"])
                await self.cmd_articulations(deg, float(m.get("ms", 0)), "manuel")
            elif op == "propulsion":
                await self.cmd_propulsion(float(m["g"]), float(m["d"]), "manette", 400)
            elif op == "repos":
                self._arreter_sequence()
                await self.cmd_articulations(list(self.limites.repos), 1500, "manuel")
            elif op == "seq_lister":
                await ws.send_json({"type": "sequences", "liste": self.lister_sequences()})
            elif op == "seq_lire":
                await ws.send_json({"type": "sequence", "sequence": self.lire_sequence(m["nom"])})
            elif op == "seq_enregistrer":
                nom = self.enregistrer_sequence(m["sequence"])
                await self.log(f"Séquence « {nom} » enregistrée")
                await self.diffuser({"type": "sequences", "liste": self.lister_sequences()})
            elif op == "seq_jouer":
                await self.jouer_sequence(m["nom"], "manuel")
            elif op == "seq_arreter":
                self._arreter_sequence()
                await self.log("Séquence arrêtée")
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
            elif op == "note":
                texte = str(m.get("texte", "")).strip()
                if texte:
                    self.seance.note(texte)
                    await self.log(f"Note : {texte}")
            elif op == "cloturer":
                self.seance.cloturer()
                await self.log(f"Séance {self.seance.id} clôturée ; nouvelle séance ouverte")
                p = self.cfg["protocole"]
                self.seance = Seance(RACINE / p["dossier_corpus"], p["systeme"], p["type"],
                                     p.get("operatrice", ""),
                                     {k: self.cfg[k] for k in ("robot", "securite", "ia")},
                                     self.cfg["robot"]["transport"])
                self.seance.meta["moteur_ia"] = self.agent.moteur
                await self.diffuser(self.config_interface())
        except CommandeRefusee as exc:
            self.seance.compter("commandes_refusees")
            self.seance.evenement("refus", op=op, motif=str(exc))
            await ws.send_json({"type": "journal", "niveau": "refus", "msg": str(exc),
                                "ts": time.strftime("%H:%M:%S")})
        except (KeyError, ValueError, TypeError) as exc:
            await ws.send_json({"type": "journal", "niveau": "alerte",
                                "msg": f"Message mal formé ({op}) : {exc}",
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


# ── Application web ───────────────────────────────────────────
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
    await ws.send_json({"type": "sequences", "liste": ctl.lister_sequences()})
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
            try:
                await ctl._envoyer({"t": "drive", "l": 0, "r": 0})
                ctl.etat["drive"] = [0, 0]
            except CommandeRefusee:
                pass
        await ctl.log("Interface déconnectée", "avert")
    return ws


async def index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(RACINE / "web" / "index.html")


async def page_partenaire(_: web.Request) -> web.FileResponse:
    return web.FileResponse(RACINE / "web" / "partenaire.html")


def creer_app(cfg: dict[str, Any]) -> web.Application:
    app = web.Application(client_max_size=8 * 1024 * 1024)
    app[CTL] = Controleur(cfg)

    async def demarrer(app: web.Application) -> None:
        ctl = app[CTL]
        app[TACHES] = [asyncio.create_task(ctl.boucle_robot()),
                         asyncio.create_task(ctl.boucle_surveillance()),
                         asyncio.create_task(ctl.boucle_diffusion())]

    async def arreter(app: web.Application) -> None:
        ctl = app[CTL]
        try:
            await ctl._envoyer({"t": "drive", "l": 0, "r": 0})
        except Exception:
            pass
        for t in app[TACHES]:
            t.cancel()
        if ctl.transport:
            await ctl.transport.fermer()
        ctl.seance.cloturer()

    app.on_startup.append(demarrer)
    app.on_cleanup.append(arreter)
    app.router.add_get("/", index)
    app.router.add_get("/partenaire", page_partenaire)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static", RACINE / "web")
    return app


def charger_config(chemin: Path) -> dict[str, Any]:
    with open(chemin, "rb") as f:
        return tomllib.load(f)


def main() -> None:
    ap = argparse.ArgumentParser(description="Console ROBO-SCÈNE")
    ap.add_argument("--config", default=str(RACINE / "config.toml"))
    ap.add_argument("--sim", action="store_true", help="forcer le robot simulé")
    ap.add_argument("--port", type=int)
    a = ap.parse_args()
    cfg = charger_config(Path(a.config))
    if a.sim:
        cfg["robot"]["transport"] = "sim"
    port = a.port or cfg["serveur"]["port"]
    print(f"Console ROBO-SCÈNE → http://{cfg['serveur']['hote']}:{port}  "
          f"(transport : {cfg['robot']['transport']})")
    web.run_app(creer_app(cfg), host=cfg["serveur"]["hote"], port=port, print=None)


if __name__ == "__main__":
    main()
