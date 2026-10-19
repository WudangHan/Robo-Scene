"""Contrôleur du chien réel : toute commande venue de la page « Chien » passe par ici avant d'atteindre le robot.

Même chaîne de sécurité que le drone (bridge/drone/controleur.py), transposée au sol :
  1. autorisation de configuration : [chien] reel_autorise ; [chien] marche_en_representation ;
  2. conditions : observateur de sécurité (plan P2.1), liste de contrôle cochée et signée, salle vérifiée vide en
     mode « salle vide », aucun arrêt d'urgence ;
  3. sol praticable (bridge/chien/sol.py, même règle que la page) pour chaque destination et chaque trajet ;
     consignes de vitesse filtrées par le point d'arrêt prévu ;
  4. plafonds de vitesse par surface (escaliers lents, salle plus lente en représentation) ; trajets suivis par
     poursuite d'une référence à secousse minimale, consignes à 10 Hz ;
  5. chiens de garde : page muette → arrêt (0,5 s) puis couché (3 s) ; télémétrie hors zone → arrêt ;
  6. ARRÊT global → arrêt puis couché ; coupure des moteurs à part, confirmée.
Aucune image n'est reçue ni conservée ici (G-06).
"""
from __future__ import annotations

import asyncio
import math
import time
from typing import Any

from ..securite import CommandeRefusee
from . import sol
from .adaptateurs import ADAPTATEURS, DESCRIPTIONS, POSTURES, RepereSol

PERIODE = 0.1


def duree_marche(salle: dict, a, b, mode: str, duree: float | None = None) -> float:
    """Même calcul que web/chien/chien.js (dureeMarche), à l'allure neutre."""
    R = salle["sol"]["regles"]
    d = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(1, math.ceil(d / 0.1))
    vmin = min(sol.vitesse_max(salle, a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n, mode) for i in range(n + 1))
    tmin = max(0.6, 1.875 * d / vmin, math.sqrt(5.7735 * d / R["acceleration_max_m_s2"]))
    return max(float(duree) if duree else tmin, tmin)


class ChienControleur:
    def __init__(self, ctl, cfg: dict[str, Any]):
        from ..gouvernance.biometrie import verifier_config
        verifier_config(cfg)
        from ..drone.zones import charger_salle
        self.ctl = ctl
        self.cfg = cfg
        self.salle = charger_salle(cfg.get("salle") or None)
        self.R = self.salle["sol"]["regles"]
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
        self.alerte_zone = False
        rep = cfg.get("repere", {})
        a = self.salle["sol"]["aire"]
        self.repere = RepereSol(rep.get("origine", a["centre"]), float(rep.get("cap_deg", a.get("lacet", 0))),
                                float(rep.get("y0", 0.0)))

    # ── État ─────────────────────────────────────────────────
    @property
    def reel(self) -> bool:
        return bool(self.adaptateur and self.adaptateur.reel)

    @property
    def debout(self) -> bool:
        return self.tel.get("etat") == "debout"

    def xz(self) -> list[float] | None:
        p = self.tel.get("p")
        return [p[0], p[2]] if p else None

    def etat(self) -> dict[str, Any]:
        ids = [c["id"] for c in self.salle["sol"]["liste_controle"]]
        return {"type": "chien_etat", "adaptateur": self.adaptateur.nom if self.adaptateur else None,
                "reel": self.reel, "mode": self.mode, "salle_vide_par": self.salle_vide_par, "urgence": self.urgence,
                "liste": sorted(self.coches), "liste_complete": set(ids) <= self.coches, "liste_par": self.liste_par,
                "interpretes": self.interpretes, "observateur": self.ctl.observateur,
                "reel_autorise": bool(self.cfg.get("reel_autorise")),
                "marche_en_representation": bool(self.cfg.get("marche_en_representation")),
                "adaptateurs": {k: DESCRIPTIONS[k] for k in ADAPTATEURS},
                "position_mesuree": bool(self.adaptateur.position_mesuree) if self.adaptateur else None,
                "camera": {"whep_url": self.cfg.get("whep_url")}}

    async def _journal(self, action: str, **d: Any) -> None:
        self.ctl.seance.evenement("chien", action=action, adaptateur=self.adaptateur.nom if self.adaptateur else None,
                                  reel=self.reel, mode=self.mode, **d)

    async def _diffuser_etat(self) -> None:
        await self.ctl.diffuser(self.etat())

    # ── Liaison ──────────────────────────────────────────────
    async def connecter(self, nom: str) -> None:
        if nom not in ADAPTATEURS:
            raise CommandeRefusee(f"Adaptateur inconnu : {nom} ; disponibles : {', '.join(ADAPTATEURS)}")
        cls = ADAPTATEURS[nom]
        if cls.reel and not self.cfg.get("reel_autorise"):
            raise CommandeRefusee("Chien réel non autorisé : [chien] reel_autorise = false dans config.toml "
                                  "(à activer après le relevé du sol, l'autorisation du lieu et l'assurance)")
        await self.deconnecter()
        a = cls(dict(self.cfg.get(nom, {})), self.repere)
        try:
            await a.ouvrir(self._sur_tel)
        except (OSError, ConnectionError, ImportError) as exc:
            try:
                await a.fermer()
            except Exception:
                pass
            raise CommandeRefusee(f"Liaison impossible ({nom}) : {exc}") from exc
        self.adaptateur = a
        self.tel = dict(a.tel)
        await self._journal("connexion")
        await self.ctl.log(f"Chien : liaison établie ({DESCRIPTIONS[nom]})")
        await self._diffuser_etat()

    async def deconnecter(self) -> None:
        if not self.adaptateur:
            return
        if self.debout:
            raise CommandeRefusee("Déconnexion refusée : le robot est debout (le coucher d'abord)")
        self._annuler_trajet()
        await self.adaptateur.fermer()
        await self._journal("deconnexion")
        self.adaptateur = None
        self.tel = {}
        await self.ctl.log("Chien : liaison fermée")
        await self._diffuser_etat()

    def _sur_tel(self, tel: dict[str, Any]) -> None:
        self.tel = tel

    # ── Réglages de séance ───────────────────────────────────
    async def regler_mode(self, mode: str, par: str = "") -> None:
        if mode not in self.salle["sol"]["modes"]:
            raise CommandeRefusee(f"Mode inconnu : {mode}")
        if self.trajet and not self.trajet.done() and mode != self.mode:
            raise CommandeRefusee("Changement de mode refusé pendant la marche")
        if mode == "salle_vide" and not par.strip():
            raise CommandeRefusee("Mode « salle vide » : initiales de la personne qui a vérifié la salle requises")
        if mode == "representation" and self.reel and not self.cfg.get("marche_en_representation"):
            raise CommandeRefusee("Marche réelle en représentation non autorisée ([chien] marche_en_representation = false)")
        self.mode = mode
        self.salle_vide_par = par.strip()[:12] if mode == "salle_vide" else None
        await self._journal("mode", par=self.salle_vide_par)
        await self.ctl.log(f"Chien : mode « {mode} »" + (f" (salle vérifiée vide par {self.salle_vide_par})" if self.salle_vide_par else ""))
        await self._diffuser_etat()

    async def regler_interpretes(self, liste: list) -> None:
        self.interpretes = [{"x": float(it["x"]), "z": float(it["z"])} for it in liste[:12]]
        await self._diffuser_etat()

    async def cocher(self, coches: list[str], par: str) -> None:
        ids = {c["id"] for c in self.salle["sol"]["liste_controle"]}
        coches = {c for c in coches if c in ids}
        if ids <= coches and not par.strip():
            raise CommandeRefusee("Liste de contrôle : initiales de la personne qui l'a vérifiée requises")
        if self.debout:
            raise CommandeRefusee("Liste de contrôle : modification refusée robot debout")
        self.coches, self.liste_par = coches, par.strip()[:12]
        await self._journal("liste_controle", coches=sorted(self.coches), par=self.liste_par, complete=ids <= coches)
        await self._diffuser_etat()

    # ── Vérifications ────────────────────────────────────────
    def _exiger_liaison(self):
        if not self.adaptateur:
            raise CommandeRefusee("Aucun chien relié")

    def _exiger_marche_permise(self):
        self._exiger_liaison()
        if self.urgence or any(r.securite.arret_urgence for r in self.ctl.robots.values()):
            raise CommandeRefusee("Arrêt d'urgence actif : réarmer avant toute commande")
        if self.tel.get("etat") == "affaisse":
            raise CommandeRefusee("Moteurs coupés : relever le robot à la main, puis réarmer")
        if not self.reel:
            return
        if not self.ctl.observateur:
            raise CommandeRefusee("Observateur de sécurité requis pour un robot réel (plan P2.1) : le déclarer dans la Console")
        ids = {c["id"] for c in self.salle["sol"]["liste_controle"]}
        if not ids <= self.coches or not self.liste_par:
            manque = [c["texte"] for c in self.salle["sol"]["liste_controle"] if c["id"] not in self.coches]
            raise CommandeRefusee("Liste de contrôle incomplète" + (f" : {manque[0]}" if manque else " (initiales)"))
        if self.mode == "representation" and not self.cfg.get("marche_en_representation"):
            raise CommandeRefusee("Marche réelle en représentation non autorisée ([chien] marche_en_representation = false)")

    # ── Commandes ────────────────────────────────────────────
    async def posture(self, nom: str):
        if nom not in POSTURES:
            raise CommandeRefusee(f"Posture inconnue : {nom}")
        if nom == "couche":                     # se coucher est toujours permis : c'est la position sûre
            self._exiger_liaison()
            self._annuler_trajet()
            await self.adaptateur.arreter()
        else:
            self._exiger_marche_permise()
            p = self.xz()
            if p and not sol.verifier(self.salle, p, self.mode, self.interpretes)["ok"]:
                raise CommandeRefusee("Posture refusée : le robot est hors du sol praticable de ce mode")
            self._annuler_trajet()
            await self.adaptateur.arreter()
        await self.adaptateur.posture(nom)
        self.dernier_hb = time.monotonic()
        await self._journal("posture", nom=nom)
        await self.ctl.log(f"Chien : posture « {nom} » ({'réel' if self.reel else 'simulé dans le pont'})")

    async def arreter(self, motif: str = ""):
        self._exiger_liaison()
        self._annuler_trajet()
        await self.adaptateur.arreter()
        if motif:
            await self._journal("arret", motif=motif)
            await self.ctl.log(f"Chien : arrêt ({motif})", "avert")

    async def aller(self, cible, duree: float | None = None, lacet: float | None = None):
        self._exiger_marche_permise()
        if not self.debout:
            raise CommandeRefusee("Le robot doit être debout pour marcher")
        p1 = sol.point(self.salle, cible)
        v = sol.verifier(self.salle, p1, self.mode, self.interpretes)
        if not v["ok"]:
            raise CommandeRefusee(f"Destination refusée : {v['motif']}")
        p0 = self.xz() or p1
        t = sol.verifier_trajet(self.salle, p0, p1, self.mode, self.interpretes)
        if not t["ok"]:
            raise CommandeRefusee(f"Trajet refusé à {round(t['fraction'] * 100)} % : {t['motif']}")
        T = duree_marche(self.salle, p0, p1, self.mode, duree)
        self._annuler_trajet()
        self.trajet = asyncio.create_task(self._suivre(p0, p1, T, lacet))
        await self._journal("aller", vers=[round(x, 3) for x in p1], duree=round(T, 2), lacet=lacet)
        return T

    async def _suivre(self, p0, p1, T, lacet_final):
        """Poursuite d'une référence à secousse minimale ; le robot s'oriente dans le sens de la marche."""
        t0 = time.monotonic()
        dx, dz = p1[0] - p0[0], p1[1] - p0[1]
        cap = math.atan2(dx, dz) if math.hypot(dx, dz) > 0.3 else None
        try:
            while True:
                t = time.monotonic() - t0
                s = max(0.0, min(1.0, t / T))
                f = s ** 3 * (10 - 15 * s + 6 * s * s)
                df = 30 * s * s * (1 - s) ** 2 / T
                ref = [p0[0] + dx * f, p0[1] + dz * f]
                p = self.xz() or ref
                vw = [dx * df + 1.5 * (ref[0] - p[0]), dz * df + 1.5 * (ref[1] - p[1])]
                vmax = sol.vitesse_max(self.salle, p[0], p[1], self.mode)
                n = math.hypot(*vw)
                if n > vmax:
                    vw = [vw[0] * vmax / n, vw[1] * vmax / n]
                vw = self._filtrer(vw)
                psi = math.radians(self.tel.get("lacet") or 0.0)
                but = cap if (cap is not None and s < 0.97) else (math.radians(lacet_final) if lacet_final is not None else None)
                wz = 0.0
                if but is not None:
                    e = math.atan2(math.sin(but - psi), math.cos(but - psi))
                    wz = max(-self.R["vitesse_lacet_max_deg_s"], min(self.R["vitesse_lacet_max_deg_s"], math.degrees(e) * 2.0))
                avant = vw[0] * math.sin(psi) + vw[1] * math.cos(psi)
                gauche = vw[0] * math.cos(psi) - vw[1] * math.sin(psi)
                await self.adaptateur.vitesse(avant, gauche, wz)
                if t >= T and (but is None or abs(wz) < 3):
                    await self.adaptateur.arreter()
                    return
                if t > T + 6:
                    await self.adaptateur.arreter()
                    return
                await asyncio.sleep(PERIODE)
        except asyncio.CancelledError:
            pass

    def _annuler_trajet(self):
        if self.trajet and not self.trajet.done():
            self.trajet.cancel()
        self.trajet = None

    async def vitesse(self, v, lacet_vitesse: float = 0.0):
        """Pilotage manuel : v = [avant, gauche] dans le repère du corps ; consigne valable 0,5 s."""
        self._exiger_marche_permise()
        if not self.debout:
            return
        psi = math.radians(self.tel.get("lacet") or 0.0)
        av, ga = float(v[0]), float(v[1])
        vw = [av * math.sin(psi) + ga * math.cos(psi), av * math.cos(psi) - ga * math.sin(psi)]
        p = self.xz() or [0.0, 0.0]
        vmax = sol.vitesse_max(self.salle, p[0], p[1], self.mode)
        n = math.hypot(*vw)
        if n > vmax:
            vw = [vw[0] * vmax / n, vw[1] * vmax / n]
        vw = self._filtrer(vw)
        wz = max(-self.R["vitesse_lacet_max_deg_s"], min(self.R["vitesse_lacet_max_deg_s"], float(lacet_vitesse)))
        self._annuler_trajet()
        self.dernier_hb = time.monotonic()
        await self.adaptateur.vitesse(vw[0] * math.sin(psi) + vw[1] * math.cos(psi),
                                      vw[0] * math.cos(psi) - vw[1] * math.sin(psi), wz)

    def _filtrer(self, vw):
        p = self.xz()
        if not p:
            return [0.0, 0.0]
        a = self.R["acceleration_max_m_s2"]
        v0 = self.tel.get("v") or [0.0, 0.0]

        def ok(w):
            s = math.hypot(*w)
            t = s / (2 * a) + 0.2
            q = [p[0] + v0[0] * 0.2 + w[0] * t, p[1] + v0[1] * 0.2 + w[1] * t]
            return sol.verifier(self.salle, q, self.mode, self.interpretes)["ok"]

        if not sol.verifier(self.salle, p, self.mode, self.interpretes)["ok"] or ok(vw):
            return list(vw)
        for i in (0, 1):
            w = list(vw)
            w[i] = 0.0
            if ok(w):
                return w
        return [0.0, 0.0]

    def battement(self):
        self.dernier_hb = time.monotonic()

    async def arret_urgence(self, motif: str) -> None:
        """ARRÊT global de la plateforme : arrêt puis couché, verrou jusqu'au réarmement."""
        self.urgence = True
        self._annuler_trajet()
        if self.adaptateur:
            try:
                await self.adaptateur.urgence()
            except Exception as exc:
                await self.ctl.log(f"Chien : échec de l'arrêt d'urgence ({exc})", "alerte")
        await self._journal("arret_urgence", motif=motif)
        await self._diffuser_etat()

    async def couper(self, confirmation: str):
        self._exiger_liaison()
        if confirmation != "COUPER":
            raise CommandeRefusee("Coupure des moteurs : confirmation « COUPER » requise")
        self._annuler_trajet()
        await self.adaptateur.couper()
        await self._journal("coupure_moteurs")
        await self.ctl.arret_urgence("coupure des moteurs du chien", origine="chien")

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
            try:
                await self._surveiller(time.monotonic())
            except CommandeRefusee:
                pass
            except Exception as exc:
                await self.ctl.log(f"Chien : {type(exc).__name__} : {exc}", "alerte")
            t = self.tel
            await self.ctl.diffuser({"type": "chien_tel", "p": t.get("p"), "v": t.get("v"), "lacet": t.get("lacet"),
                                     "batterie": t.get("batterie"), "etat": t.get("etat"), "posture": t.get("posture"),
                                     "position": t.get("position"), "adaptateur": self.adaptateur.nom, "reel": self.reel,
                                     "urgence": self.urgence})
            if n % 2 == 0 and self.debout:
                self.ctl.seance.evenement("chien_tel", p=t.get("p"), lacet=t.get("lacet"), batterie=t.get("batterie"),
                                          posture=t.get("posture"))

    async def _surveiller(self, now: float) -> None:
        if not self.debout or self.urgence:
            self.etape_hb = 0
            return
        R = self.R
        muet = now - self.dernier_hb
        if muet > R["perte_liaison_coucher_s"] and self.etape_hb < 2:
            self.etape_hb = 2
            await self.posture("couche")
            await self.ctl.log("Chien : page de pilotage muette — couché", "avert")
        elif muet > R["perte_liaison_arret_s"] and self.etape_hb < 1:
            self.etape_hb = 1
            await self.arreter("page de pilotage muette")
        elif muet <= R["perte_liaison_arret_s"]:
            self.etape_hb = 0
        p = self.xz()
        if p and self.adaptateur.position_mesuree:
            v = sol.verifier(self.salle, p, self.mode, self.interpretes)
            if not v["ok"] and not self.alerte_zone:
                self.alerte_zone = True
                await self.arreter(f"hors zone : {v['motif']}")
            elif v["ok"]:
                self.alerte_zone = False
        b = self.tel.get("batterie")
        if b is not None and b <= R["batterie_critique_pct"]:
            await self.posture("couche")
