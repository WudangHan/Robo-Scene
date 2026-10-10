"""Couche de sécurité logicielle du pont ROBO-SCÈNE.

Toute commande destinée au robot passe par ici : bornage articulaire,
limitation de vitesse, plafond de propulsion, verrou d'arrêt d'urgence.
Cette couche ne remplace PAS un arrêt d'urgence matériel (coupure de
l'alimentation des moteurs), exigé pour toute séance avec des personnes.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class CommandeRefusee(Exception):
    """Commande rejetée par la couche de sécurité (motif lisible)."""


@dataclass
class Limites:
    min_deg: list[float]
    max_deg: list[float]
    repos: list[float]
    vitesse_max_deg_s: float = 90.0
    propulsion_max: float = 0.6
    propulsion_active: bool = True


@dataclass
class Securite:
    limites: Limites
    arret_urgence: bool = False
    journal: list[str] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.limites.min_deg)

    # ── Arrêt d'urgence ────────────────────────────────────────
    def declencher_arret(self, motif: str) -> None:
        self.arret_urgence = True
        self.journal.append(f"ARRÊT D'URGENCE : {motif}")

    def rearmer(self) -> None:
        """Le réarmement est une action volontaire et distincte (ISO 13850)."""
        self.arret_urgence = False
        self.journal.append("Réarmement manuel")

    def _verifier_arme(self) -> None:
        if self.arret_urgence:
            raise CommandeRefusee("Arrêt d'urgence actif : réarmer avant toute commande")

    # ── Articulations ──────────────────────────────────────────
    def borner(self, i: int, deg: float) -> float:
        lo, hi = self.limites.min_deg[i], self.limites.max_deg[i]
        return max(lo, min(hi, float(deg)))

    def valider_articulations(
        self, cibles: list[float], actuelles: list[float], duree_ms: float
    ) -> tuple[list[float], float, list[str]]:
        """Retourne (cibles bornées, durée ajustée, avertissements).

        La durée est allongée si le mouvement demandé dépasse la vitesse
        maximale : on ralentit au lieu de refuser.
        """
        self._verifier_arme()
        if len(cibles) != self.n:
            raise CommandeRefusee(f"{len(cibles)} angles reçus, {self.n} attendus")
        avert: list[str] = []
        sures: list[float] = []
        for i, c in enumerate(cibles):
            if c is None:
                c = actuelles[i]
            try:
                c = float(c)
            except (TypeError, ValueError) as exc:
                raise CommandeRefusee(f"Angle invalide pour l'articulation {i}") from exc
            b = self.borner(i, c)
            if abs(b - c) > 1e-6:
                avert.append(f"Articulation {i} bornée : {c:.0f}° → {b:.0f}°")
            sures.append(b)
        ecart = max((abs(s - a) for s, a in zip(sures, actuelles)), default=0.0)
        duree_min = 1000.0 * ecart / self.limites.vitesse_max_deg_s
        duree = max(float(duree_ms or 0), duree_min)
        if duree > (duree_ms or 0) + 1:
            avert.append(f"Mouvement ralenti : {duree_ms or 0:.0f} → {duree:.0f} ms")
        return sures, duree, avert

    # ── Propulsion ─────────────────────────────────────────────
    def valider_propulsion(self, g: float, d: float) -> tuple[float, float, list[str]]:
        self._verifier_arme()
        if not self.limites.propulsion_active:
            raise CommandeRefusee("Propulsion désactivée dans la configuration")
        p = self.limites.propulsion_max
        avert = []
        out = []
        for v in (g, d):
            v = float(v)
            b = max(-p, min(p, v))
            if abs(b - v) > 1e-6:
                avert.append(f"Propulsion plafonnée à {p:.2f}")
            out.append(b)
        return out[0], out[1], avert
