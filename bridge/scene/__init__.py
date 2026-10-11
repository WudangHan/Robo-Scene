"""Scène : pont scénique P2.3 relié à la flotte (R-05, R-06, O-05, O-11, O-12 ; N-05).

La conduite (YAML du prototype P2.3) est jouée repère par repère, sous le GO de la régie :
* lumière (sACN / E1.31), son (QLab par OSC), OSC libre et provenance vers l'interface P3, comme dans P2.3 ;
* gestes : toujours par la bibliothèque fermée du robot visé (champ « robot » facultatif : conduite
  multi-robots), avec les exigences de statut de P2.1 (brouillon refusé sur robot réel, vitesse réduite avant
  « valide ») et l'observateur exigé pour un robot doté d'une zone d'exclusion ;
* répliques : diffusées aux surtitres et consignées avec leur étiquette de provenance (N-05) ;
* voix : voix de synthèse du robot, seulement si la conduite déclare la divulgation (O-12).

L'ARRÊT logiciel de la conduite annule les actions différées, met le son en panique, fige la lumière et
suspend les gestes ; il est aussi déclenché par l'arrêt d'urgence global de la flotte.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .. import _modules  # noqa: F401
from pont_scenique.conduite import Conduite, charger, valider
from pont_scenique.moteur import Moteur
from pont_scenique.sorties import SortieDMX, SortieOSC, SortieQLab

from ..robots.bibliotheque import RefusBibliotheque, exigence
from ..securite import CommandeRefusee
from ..trace import EvenementInvalide


class MoteurFlotte(Moteur):
    """Moteur P2.3 dont les gestes, répliques et voix passent par la plateforme."""

    def __init__(self, conduite: Conduite, scene: "Scene", **kw):
        super().__init__(conduite, gestes=None, **kw)
        self.scene = scene
        self.gestes_suspendus = False

    def arret(self):
        super().arret()
        self.gestes_suspendus = True
        self.scene._appeler(self.scene._arreter_gestes())

    def reprendre_gestes(self):
        self.gestes_suspendus = False
        self.journal("Gestes réautorisés par la régie.")

    def _executer(self, r, a):
        if a.type in ("geste", "replique", "voix", "provenance"):
            self.historique.append((datetime.now().strftime("%H:%M:%S.%f")[:-3], r.numero, a.type))
            try:
                if a.type == "geste":
                    if self.gestes_suspendus:
                        self.journal(f"Geste « {a.valeur} » ignoré : gestes suspendus après ARRÊT")
                        return
                    self.scene._appeler(self.scene._geste(a.valeur, a.robot, r.numero))
                elif a.type == "replique":
                    self.scene._appeler(self.scene._replique(a.valeur, r.numero))
                elif a.type == "voix":
                    self.scene._appeler(self.scene.ctl.diffuser({"type": "voix", "repere": r.numero,
                                                                 **(a.valeur if isinstance(a.valeur, dict) else {"texte": a.valeur})}))
                elif a.type == "provenance":
                    self.scene.provenance = a.valeur
                    if self.osc_p3:
                        self.osc_p3.envoyer("/p3/provenance", a.valeur, r.numero)
            except Exception as e:
                self.journal(f"⚠ Repère {r.numero}, action {a.type} : {e}")
            return
        super()._executer(r, a)


class Scene:
    def __init__(self, ctl, cfg: dict[str, Any] | None = None):
        self.ctl = ctl
        self.cfg = cfg or {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self.conduite: Conduite | None = None
        self.moteur: MoteurFlotte | None = None
        self.source = None
        self.lignes: list[str] = []
        self.provenance: str | None = None
        self.erreurs: list[str] = []
        self._dmx = None

    # ── Utilitaires ─────────────────────────────────────────
    def journal(self, msg: str) -> None:
        ligne = f"{datetime.now():%H:%M:%S} {msg}"
        self.lignes.append(ligne)
        self.lignes = self.lignes[-300:]
        self.ctl.seance.evenement("scene", msg=msg)
        if self.loop:
            self._appeler(self.ctl.diffuser({"type": "scene_journal", "ligne": ligne}))

    def _appeler(self, coro):
        if coro is None:
            return None
        try:
            courante = asyncio.get_running_loop()
        except RuntimeError:
            courante = None
        if courante is self.loop and courante is not None:
            return asyncio.ensure_future(coro)
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def gestes_connus(self) -> set[str]:
        return {n for r in self.ctl.robots.values() for n in r.biblio.lister()}

    # ── Chargement ──────────────────────────────────────────
    def charger(self, *, chemin: str | Path | None = None, texte: str | None = None) -> dict[str, Any]:
        if texte is not None:
            c = _charger_texte(texte)
            self.source = "texte"
        else:
            chemin = Path(chemin or (_modules.CHEMINS["p2"] / "pont_scenique" / "conduite_exemple.yaml"))
            c = charger(chemin)
            self.source = str(chemin)
        self.erreurs = valider(c, self.gestes_connus())
        for r in c.reperes:
            for a in r.actions:
                if a.type == "geste" and a.robot and a.robot not in self.ctl.robots:
                    self.erreurs.append(f"Repère {r.numero} : robot « {a.robot} » absent de la flotte")
        self.conduite = c
        a_blanc = bool(self.cfg.get("a_blanc", True))
        if self._dmx:
            self._dmx.fermer()
        self._dmx = SortieDMX(univers=int(self.cfg.get("univers_dmx", 1)), a_blanc=a_blanc, journal=self.journal)
        self.moteur = MoteurFlotte(
            c, self, qlab=SortieQLab(self.cfg.get("hote_qlab", "127.0.0.1"), int(self.cfg.get("port_qlab", 53000)),
                                     a_blanc=a_blanc, journal=self.journal),
            dmx=self._dmx, osc_p3=SortieOSC(self.cfg.get("hote_p3", "127.0.0.1"), int(self.cfg.get("port_osc_p3", 9000)),
                                             a_blanc=bool(self.cfg.get("p3_a_blanc", False)), journal=self.journal),
            osc_libre=SortieOSC(self.cfg.get("hote_osc", "127.0.0.1"), int(self.cfg.get("port_osc", 9000)),
                                a_blanc=a_blanc, journal=self.journal),
            journal=self.journal)
        self.journal(f"Conduite chargée : {c.titre} ({len(c.reperes)} repères, {len(self.erreurs)} erreur(s))")
        return self.etat()

    def etat(self) -> dict[str, Any]:
        c, m = self.conduite, self.moteur
        return {"chargee": c is not None, "titre": c.titre if c else None, "source": self.source,
                "erreurs": self.erreurs, "a_blanc": bool(self.cfg.get("a_blanc", True)),
                "reperes": [{"numero": r.numero, "nom": r.nom,
                             "actions": [{"type": a.type, "valeur": a.valeur, "delai": a.delai, "robot": a.robot}
                                         for a in r.actions]} for r in c.reperes] if c else [],
                "index": m.index if m else -1, "prochain": m.prochain.numero if m and m.prochain else None,
                "gestes_suspendus": bool(m and m.gestes_suspendus), "provenance": self.provenance,
                "divulgations": c.divulgations if c else [], "journal": self.lignes[-40:]}

    # ── Régie ───────────────────────────────────────────────
    def go(self) -> dict[str, Any]:
        if not self.moteur:
            raise CommandeRefusee("Aucune conduite chargée")
        if self.erreurs:
            raise CommandeRefusee("Conduite invalide : " + " ; ".join(self.erreurs[:3]))
        if any(r.securite.arret_urgence for r in self.ctl.robots.values()):
            raise CommandeRefusee("Arrêt d'urgence actif : réarmer avant le GO")
        r = self.moteur.go()
        return {"repere": r.numero if r else None, **self.etat()}

    def retour(self) -> dict[str, Any]:
        if self.moteur:
            self.moteur.retour()
        return self.etat()

    def arret_logiciel(self) -> None:
        if self.moteur:
            self.moteur.arret()

    def reprendre(self) -> dict[str, Any]:
        if self.moteur:
            self.moteur.reprendre_gestes()
        return self.etat()

    async def _arreter_gestes(self):
        self.ctl._arreter_sequence("*")

    async def _geste(self, nom: str, robot: str | None, repere: str) -> None:
        try:
            await self.ctl.jouer_sequence(nom, f"conduite:{repere}", robot)
            self.journal(f"Geste « {nom} » ({robot or self.ctl.actif_id}) au repère {repere}")
        except CommandeRefusee as exc:
            self.journal(f"⚠ Geste refusé au repère {repere} : {exc}")

    async def _replique(self, valeur: Any, repere: str) -> None:
        d = valeur if isinstance(valeur, dict) else {"texte": str(valeur)}
        etiquette = self.provenance or "aucune"
        await self.ctl.diffuser({"type": "surtitre", "repere": repere, "texte": d.get("texte", ""),
                                 "en": d.get("en"), "provenance": etiquette})
        try:
            self.ctl.trace.emettre("SCENE", "attribution", ("personne", self.ctl.pseudo_operatrice),
                                   {"etiquette": etiquette if etiquette in ("humaine", "systeme", "mixte") else "humaine",
                                    "credit": f"conduite « {self.conduite.titre} », repère {repere}",
                                    "texte": d.get("texte", ""), "repere": repere, "jouee": True,
                                    "etiquette_declaree": etiquette})
        except (EvenementInvalide, OSError):
            pass

    # ── O-05 : prévisualisation de la conduite ──────────────
    def apercu(self) -> dict[str, Any]:
        if not self.conduite:
            raise CommandeRefusee("Aucune conduite chargée")
        lignes, problemes, total = [], list(self.erreurs), 0.0
        for r in self.conduite.reperes:
            occupation: dict[str, list[tuple[float, float, str]]] = {}
            fin_repere = 0.0
            for a in r.actions:
                ligne = {"repere": r.numero, "type": a.type, "valeur": a.valeur, "debut_s": a.delai}
                if a.type == "geste":
                    rid = a.robot or self.ctl.actif_id
                    rob = self.ctl.robots.get(rid)
                    if rob is None:
                        ligne.update(etat="robot absent")
                    else:
                        try:
                            seq = rob.biblio.lire(a.valeur)
                            ok, facteur, motif = exigence(seq.get("statut", "brouillon"), rob.reel)
                            duree = sum(float(i.get("ms", 800)) + float(i.get("pause_ms", 0)) for i in seq["images"]) / 1000
                            duree = duree / facteur if facteur else duree
                            ligne.update(robot=rid, statut=seq.get("statut"), duree_s=round(duree, 2),
                                         fin_s=round(a.delai + duree, 2), etat="jouable" if ok else "refusé",
                                         motif=motif, simulation=not rob.reel)
                            if not ok:
                                problemes.append(f"Repère {r.numero} : « {a.valeur} » sur {rid} — {motif}")
                            for d0, f0, n0 in occupation.get(rid, []):
                                if a.delai < f0 and a.delai + duree > d0:
                                    problemes.append(f"Repère {r.numero} : « {a.valeur} » chevauche « {n0} » sur {rid} "
                                                     "(un seul geste à la fois par robot : le second interrompt le premier)")
                            occupation.setdefault(rid, []).append((a.delai, a.delai + duree, a.valeur))
                            fin_repere = max(fin_repere, a.delai + duree)
                        except RefusBibliotheque as exc:
                            ligne.update(etat="introuvable", motif=str(exc))
                else:
                    fin_repere = max(fin_repere, a.delai + a.transfert)
                lignes.append(ligne)
            total += fin_repere
        return {"titre": self.conduite.titre, "actions": lignes, "problemes": problemes,
                "duree_minimale_s": round(total, 1), "jouable": not problemes,
                "note": "Durées hors temps de jeu entre les GO ; vitesse réduite comptée pour les gestes non « valide »."}


def _charger_texte(texte: str) -> Conduite:
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        f.write(texte)
        nom = f.name
    try:
        return charger(nom)
    finally:
        Path(nom).unlink(missing_ok=True)
