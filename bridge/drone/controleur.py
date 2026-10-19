"""Contrôleur du drone réel : toute commande venue de la page « Drone » passe par ici avant d'atteindre l'appareil.

Chaîne de sécurité (dans l'ordre) :
  1. autorisation de configuration : un adaptateur réel n'est ouvert que si [drone] reel_autorise = true ; le mode
     « représentation » (public présent) n'est permis que si [drone] vol_en_representation = true ;
  2. conditions de vol réel : observateur de sécurité déclaré (plan P2.1), liste de contrôle cochée et signée,
     salle vide confirmée par des initiales en mode « salle vide », arrêt d'urgence non actif ;
  3. zones : chaque destination et chaque segment sont vérifiés (bridge/drone/zones.py, même règle que la page) ;
     les consignes de vitesse sont filtrées par le point d'arrêt prévu, comme dans le drone virtuel ;
  4. plafonds de vitesse et d'accélération ; trajets découpés selon une loi à secousse minimale, consignes à 10 Hz ;
  5. chiens de garde : page muette → stationnaire puis atterrissage ; télémétrie hors zone → stationnaire ;
  6. arrêt d'urgence GLOBAL de la plateforme → atterrissage immédiat ; coupure des moteurs à part, confirmée.
Aucune image n'est reçue ni conservée ici (G-06) : la vidéo va directement de la caméra à la page.
"""
from __future__ import annotations

import asyncio
import math
import time
from typing import Any

from ..securite import CommandeRefusee
from . import zones
from .adaptateurs import ADAPTATEURS, DESCRIPTIONS, Repere

PERIODE = 0.1


def _min_jerk(p0, p1, T, t):
    s = max(0.0, min(1.0, t / T))
    f = s ** 3 * (10 - 15 * s + 6 * s * s)
    return [a + (b - a) * f for a, b in zip(p0, p1)]


def duree_min(R: dict, a, b, duree: float | None = None, vitesse: float | None = None) -> float:
    """Même calcul que web/drone/vol.js (dureeMin) : pics de vitesse 1,875 d/T et d'accélération 5,7735 d/T²."""
    dh = math.hypot(b[0] - a[0], b[2] - a[2])
    dv = abs(b[1] - a[1])
    d = math.hypot(dh, dv)
    tmin = max(0.5, 1.875 * dh / R["vitesse_max_h_m_s"], 1.875 * dv / R["vitesse_max_v_m_s"],
               math.sqrt(5.7735 * d / R["acceleration_max_m_s2"]))
    t = duree if duree is not None else (1.875 * d / vitesse if vitesse else tmin)
    return max(float(t), tmin)


class DroneControleur:
    def __init__(self, ctl, cfg: dict[str, Any]):
        from ..gouvernance.biometrie import verifier_config
        verifier_config(cfg)                 # G-06 : aucune option de conservation d'images ou de vidéo
        self.ctl = ctl
        self.cfg = cfg
        self.salle = zones.charger_salle(cfg.get("salle") or None)
        self.R = self.salle["regles"]
        self.mode = "plateau"
        self.salle_vide_par: str | None = None
        self.interpretes: list[dict] = []
        self.coches: set[str] = set()
        self.liste_par = ""
        self.adaptateur = None
        self.urgence = False
        self.tel: dict[str, Any] = {}
        self.dernier_hb = 0.0
        self.etape_hb = 0
        self.trajet: asyncio.Task | None = None
        self.v_jusqua = 0.0
        self.alerte_zone = False
        rep = cfg.get("repere", {})
        self.repere = Repere(rep.get("origine", self.salle["aire"]["centre"]), float(rep.get("cap_deg", 0.0)))

    # ── État ─────────────────────────────────────────────────
    @property
    def reel(self) -> bool:
        return bool(self.adaptateur and self.adaptateur.reel)

    @property
    def en_vol(self) -> bool:
        return self.tel.get("etat") in ("decollage", "vol", "atterrissage")

    def etat(self) -> dict[str, Any]:
        ids = [c["id"] for c in self.salle["liste_controle"]]
        return {"type": "drone_etat", "adaptateur": self.adaptateur.nom if self.adaptateur else None,
                "reel": self.reel, "mode": self.mode, "salle_vide_par": self.salle_vide_par, "urgence": self.urgence,
                "liste": sorted(self.coches), "liste_complete": set(ids) <= self.coches, "liste_par": self.liste_par,
                "interpretes": self.interpretes, "observateur": self.ctl.observateur,
                "reel_autorise": bool(self.cfg.get("reel_autorise")),
                "vol_en_representation": bool(self.cfg.get("vol_en_representation")),
                "adaptateurs": {k: DESCRIPTIONS[k] for k in ADAPTATEURS},
                "position_mesuree": bool(self.adaptateur.position_mesuree) if self.adaptateur else None,
                "camera": {k: self.cfg.get(k) for k in ("whep_url",)}}

    async def _journal(self, action: str, **d: Any) -> None:
        self.ctl.seance.evenement("drone", action=action, adaptateur=self.adaptateur.nom if self.adaptateur else None,
                                  reel=self.reel, mode=self.mode, **d)

    async def _diffuser_etat(self) -> None:
        await self.ctl.diffuser(self.etat())

    # ── Liaison ──────────────────────────────────────────────
    async def connecter(self, nom: str) -> None:
        if nom not in ADAPTATEURS:
            raise CommandeRefusee(f"Adaptateur inconnu : {nom} ; disponibles : {', '.join(ADAPTATEURS)}")
        cls = ADAPTATEURS[nom]
        if cls.reel and not self.cfg.get("reel_autorise"):
            raise CommandeRefusee("Drone réel non autorisé : [drone] reel_autorise = false dans config.toml "
                                  "(à activer après le relevé de la salle, l'autorisation du lieu et l'assurance)")
        await self.deconnecter()
        a = cls(dict(self.cfg.get(nom, {})), self.repere)
        try:
            await a.ouvrir(self._sur_tel)
        except (OSError, ConnectionError) as exc:
            try:
                await a.fermer()
            except Exception:
                pass
            raise CommandeRefusee(f"Liaison impossible ({nom}) : {exc}") from exc
        self.adaptateur = a
        self.tel = dict(a.tel)
        await self._journal("connexion")
        await self.ctl.log(f"Drone : liaison établie ({DESCRIPTIONS[nom]})")
        await self._diffuser_etat()

    async def deconnecter(self) -> None:
        if not self.adaptateur:
            return
        if self.en_vol:
            raise CommandeRefusee("Déconnexion refusée : le drone est en vol (atterrir d'abord)")
        self._annuler_trajet()
        await self.adaptateur.fermer()
        await self._journal("deconnexion")
        self.adaptateur = None
        self.tel = {}
        await self.ctl.log("Drone : liaison fermée")
        await self._diffuser_etat()

    def _sur_tel(self, tel: dict[str, Any]) -> None:
        self.tel = tel

    # ── Réglages de séance ───────────────────────────────────
    async def regler_mode(self, mode: str, par: str = "") -> None:
        if mode not in self.salle["modes"]:
            raise CommandeRefusee(f"Mode inconnu : {mode}")
        if self.en_vol and mode != self.mode:
            raise CommandeRefusee("Changement de mode refusé en vol")
        if mode == "salle_vide" and not par.strip():
            raise CommandeRefusee("Mode « salle vide » : initiales de la personne qui a vérifié la salle requises")
        if mode == "representation" and self.reel and not self.cfg.get("vol_en_representation"):
            raise CommandeRefusee("Vol réel en représentation non autorisé ([drone] vol_en_representation = false)")
        self.mode = mode
        self.salle_vide_par = par.strip()[:12] if mode == "salle_vide" else None
        await self._journal("mode", par=self.salle_vide_par)
        await self.ctl.log(f"Drone : mode « {self.salle['modes'][mode]['libelle']} »"
                           + (f" (salle vérifiée vide par {self.salle_vide_par})" if self.salle_vide_par else ""))
        await self._diffuser_etat()

    async def regler_interpretes(self, liste: list) -> None:
        propre = []
        for it in liste[:12]:
            propre.append({"x": float(it["x"]), "z": float(it["z"])})
        self.interpretes = propre
        await self._diffuser_etat()

    async def cocher(self, coches: list[str], par: str) -> None:
        ids = {c["id"] for c in self.salle["liste_controle"]}
        coches = {c for c in coches if c in ids}
        if ids <= coches and not par.strip():
            raise CommandeRefusee("Liste de contrôle : initiales de la personne qui l'a vérifiée requises")
        if self.en_vol:
            raise CommandeRefusee("Liste de contrôle : modification refusée en vol")
        self.coches, self.liste_par = coches, par.strip()[:12]
        await self._journal("liste_controle", coches=sorted(self.coches), par=self.liste_par, complete=ids <= coches)
        await self._diffuser_etat()

    # ── Vérifications ────────────────────────────────────────
    def _exiger_liaison(self):
        if not self.adaptateur:
            raise CommandeRefusee("Aucun drone relié")

    def _exiger_vol_permis(self):
        self._exiger_liaison()
        if self.urgence or any(r.securite.arret_urgence for r in self.ctl.robots.values()):
            raise CommandeRefusee("Arrêt d'urgence actif : réarmer avant toute commande")
        if not self.reel:
            return
        if not self.ctl.observateur:
            raise CommandeRefusee("Observateur de sécurité requis pour un vol réel (plan P2.1) : le déclarer dans la console")
        ids = {c["id"] for c in self.salle["liste_controle"]}
        if not ids <= self.coches or not self.liste_par:
            manque = [c["texte"] for c in self.salle["liste_controle"] if c["id"] not in self.coches]
            raise CommandeRefusee("Liste de contrôle avant vol incomplète" + (f" : {manque[0]}" if manque else " (initiales)"))
        if self.mode == "representation" and not self.cfg.get("vol_en_representation"):
            raise CommandeRefusee("Vol réel en représentation non autorisé ([drone] vol_en_representation = false)")

    def _verifier(self, p) -> None:
        v = zones.verifier(self.salle, p, self.mode, self.interpretes)
        if not v["ok"]:
            raise CommandeRefusee(f"Destination refusée : {v['motif']}")

    # ── Commandes ────────────────────────────────────────────
    async def armer(self):
        self._exiger_vol_permis()
        await self.adaptateur.armer()
        await self._journal("armer")

    async def decoller(self, hauteur: float = 1.5):
        self._exiger_vol_permis()
        if self.en_vol:
            raise CommandeRefusee("Le drone est déjà en vol")
        hauteur = max(0.6, min(float(hauteur), 3.0))
        p = list(self.tel.get("p") or self.repere.o)
        cible = [p[0], self.repere.o[1] + hauteur, p[2]]
        self._verifier(cible)
        await self.adaptateur.armer()
        await self.adaptateur.decoller(hauteur)
        self.dernier_hb = time.monotonic()
        await self._journal("decoller", hauteur=hauteur)
        await self.ctl.log(f"Drone : décollage à {hauteur:.1f} m ({'réel' if self.reel else 'simulé dans le pont'})")

    async def atterrir(self, motif: str = ""):
        self._exiger_liaison()
        self._annuler_trajet()
        await self.adaptateur.atterrir()
        await self._journal("atterrir", motif=motif)
        await self.ctl.log(f"Drone : atterrissage{f' ({motif})' if motif else ''}", "avert" if motif else "info")

    async def stationnaire(self, motif: str = ""):
        self._exiger_liaison()
        self._annuler_trajet()
        await self.adaptateur.stationnaire()
        if motif:
            await self._journal("stationnaire", motif=motif)
            await self.ctl.log(f"Drone : vol stationnaire ({motif})", "avert")

    async def aller(self, p, duree: float | None = None, vitesse: float | None = None, lacet: float | None = None):
        self._exiger_vol_permis()
        if not self.en_vol:
            raise CommandeRefusee("Le drone doit être en vol")
        p = zones.point(self.salle, p)
        self._verifier(p)
        depart = list(self.tel.get("p") or p)
        seg = zones.verifier_segment(self.salle, depart, p, self.mode, self.interpretes)
        if not seg["ok"]:
            raise CommandeRefusee(f"Trajet refusé à {round(seg['fraction'] * 100)} % : {seg['motif']}")
        vitesse = min(float(vitesse), self.R["vitesse_max_h_m_s"]) if vitesse else None
        T = duree_min(self.R, depart, p, float(duree) if duree else None, vitesse)
        self._annuler_trajet()
        if self.adaptateur.flux_position:
            self.trajet = asyncio.create_task(self._suivre(depart, p, T, lacet))
        else:
            self.trajet = asyncio.create_task(self.adaptateur.aller(p, lacet, math.dist(depart, p) / T))
        await self._journal("aller", vers=[round(x, 3) for x in p], duree=round(T, 2), lacet=lacet)
        return T

    async def _suivre(self, p0, p1, T, lacet):
        t0 = time.monotonic()
        try:
            while True:
                t = time.monotonic() - t0
                await self.adaptateur.position(_min_jerk(p0, p1, T, t), lacet)
                if t >= T:
                    return
                await asyncio.sleep(PERIODE)
        except asyncio.CancelledError:
            pass

    def _annuler_trajet(self):
        if self.trajet and not self.trajet.done():
            self.trajet.cancel()
        self.trajet = None

    async def vitesse(self, v, lacet_vitesse: float = 0.0):
        """Pilotage manuel (manettes) : consigne valable 0,5 s ; renvoyée par la page tant que la manette est tenue."""
        self._exiger_vol_permis()
        if not self.en_vol:
            return
        R = self.R
        v = [float(x) for x in v]
        h = math.hypot(v[0], v[2])
        if h > R["vitesse_max_h_m_s"]:
            v[0], v[2] = v[0] * R["vitesse_max_h_m_s"] / h, v[2] * R["vitesse_max_h_m_s"] / h
        v[1] = max(-R["vitesse_max_v_m_s"], min(R["vitesse_max_v_m_s"], v[1]))
        v = self._filtrer(v)
        wz = max(-R["vitesse_lacet_max_deg_s"], min(R["vitesse_lacet_max_deg_s"], float(lacet_vitesse)))
        self._annuler_trajet()
        self.v_jusqua = time.monotonic() + 0.5
        self.dernier_hb = time.monotonic()
        await self.adaptateur.vitesse(v, wz)

    def _filtrer(self, v):
        """Même freinage que le drone virtuel : point d'arrêt prévu ; composantes fautives retirées."""
        p = self.tel.get("p")
        if not p:
            return [0.0, 0.0, 0.0]
        a = self.R["acceleration_max_m_s2"]
        v0 = self.tel.get("v") or [0.0, 0.0, 0.0]

        def ok(w):
            s = math.sqrt(sum(x * x for x in w))
            t = s / (2 * a) + 0.25
            return zones.verifier(self.salle, [p[i] + v0[i] * 0.35 + w[i] * t for i in range(3)], self.mode,
                                  self.interpretes)["ok"]

        if not zones.verifier(self.salle, p, self.mode, self.interpretes)["ok"] or ok(v):
            return v
        for axes in ((0,), (1,), (2,), (0, 2), (0, 1), (1, 2)):
            w = list(v)
            for i in axes:
                w[i] = 0.0
            if ok(w):
                return w
        return [0.0, 0.0, 0.0]

    def battement(self):
        self.dernier_hb = time.monotonic()

    async def arret_urgence(self, motif: str) -> None:
        """Appelé par l'arrêt d'urgence GLOBAL de la plateforme : atterrissage immédiat, verrou jusqu'au réarmement."""
        self.urgence = True
        self._annuler_trajet()
        if self.adaptateur and self.en_vol:
            try:
                await self.adaptateur.urgence()
            except Exception as exc:
                await self.ctl.log(f"Drone : échec de l'atterrissage d'urgence ({exc})", "alerte")
        await self._journal("arret_urgence", motif=motif)
        await self._diffuser_etat()

    async def couper(self, confirmation: str):
        """Coupure des moteurs : dernier recours si le drone est hors de contrôle ; il tombe."""
        self._exiger_liaison()
        if confirmation != "COUPER":
            raise CommandeRefusee("Coupure des moteurs : confirmation « COUPER » requise")
        self._annuler_trajet()
        await self.adaptateur.couper()
        await self._journal("coupure_moteurs")
        await self.ctl.arret_urgence("coupure des moteurs du drone", origine="drone")

    def rearmer(self) -> None:
        self.urgence = False

    # ── Boucle : télémétrie, chiens de garde ─────────────────
    async def boucle(self) -> None:
        n = 0
        while True:
            await asyncio.sleep(PERIODE)
            if not self.adaptateur:
                continue
            n += 1
            now = time.monotonic()
            try:
                await self._surveiller(now)
            except CommandeRefusee:
                pass
            except Exception as exc:     # liaison rompue pendant une consigne
                await self.ctl.log(f"Drone : {type(exc).__name__} : {exc}", "alerte")
            t = self.tel
            await self.ctl.diffuser({"type": "drone_tel", "p": t.get("p"), "v": t.get("v"), "lacet": t.get("lacet"),
                                     "batterie": t.get("batterie"), "arme": t.get("arme"), "etat": t.get("etat"),
                                     "mode_autopilote": t.get("mode_autopilote"), "position": t.get("position"),
                                     "adaptateur": self.adaptateur.nom, "reel": self.reel, "urgence": self.urgence,
                                     "texte": t.get("texte")})
            if n % 2 == 0 and self.en_vol:
                self.ctl.seance.evenement("drone_tel", p=t.get("p"), lacet=t.get("lacet"), batterie=t.get("batterie"),
                                          etat=t.get("etat"))

    async def _surveiller(self, now: float) -> None:
        if not self.en_vol or self.tel.get("etat") == "atterrissage" or self.urgence:
            self.etape_hb = 0
            return
        R = self.R
        muet = now - self.dernier_hb
        if muet > R["perte_liaison_atterrir_s"] and self.etape_hb < 2:
            self.etape_hb = 2
            await self.atterrir("page de pilotage muette")
        elif muet > R["perte_liaison_stationnaire_s"] and self.etape_hb < 1:
            self.etape_hb = 1
            await self.stationnaire("page de pilotage muette")
        elif muet <= R["perte_liaison_stationnaire_s"]:
            self.etape_hb = 0
        p = self.tel.get("p")
        if p and self.adaptateur.position_mesuree:
            v = zones.verifier(self.salle, p, self.mode, self.interpretes)
            if not v["ok"] and not self.alerte_zone:
                self.alerte_zone = True
                await self.stationnaire(f"hors zone : {v['motif']}")
            elif v["ok"]:
                self.alerte_zone = False
        b = self.tel.get("batterie")
        if b is not None and b <= R["batterie_critique_pct"]:
            await self.atterrir(f"batterie critique ({b:.0f} %)")
