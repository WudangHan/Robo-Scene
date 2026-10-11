"""Gouvernance, éthique et vie privée (cahier des fonctions, §3.6 : G-01 à G-07 ; R-08 ; P-04).

* G-01 consentements généralisés et retrait global attesté (retrait.py) ;
* G-02 verrou de collecte tant que l'avis éthique n'est pas consigné ;
* G-03 registre des systèmes synchronisé avec les versions adoptées (D13) ;
* G-04 EFVP : refus d'une fonction dont la version dépasse la couverture de l'EFVP, en présence de personnes ;
* G-05 aucune décision exclusivement automatisée concernant une personne (decisions.py) ;
* G-06 aucune identification biométrique : garde-fou de configuration et de contenu (biometrie.py) ;
* G-07 conservation et destruction journalisée (conservation.py) ;
* R-08 fiche d'incident pour tout arrêt d'urgence (incidents.py).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from .incidents import Incidents
from .decisions import Decisions


class VerrouGouvernance(PermissionError):
    """Action refusée par une règle de gouvernance ; le message dit laquelle et comment la lever."""


def _version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in str(v).split(".") if x.isdigit())


class Gouvernance:
    def __init__(self, dossier_regles: str | Path, dossier_donnees: str | Path):
        self.regles = Path(dossier_regles)
        self.donnees = Path(dossier_donnees) / "gouvernance"
        self.donnees.mkdir(parents=True, exist_ok=True)
        self.incidents = Incidents(self.donnees / "incidents")
        self.decisions = Decisions(self.donnees / "decisions_personnes.jsonl")
        self.recharger()

    def _yaml(self, nom: str) -> dict[str, Any]:
        p = self.regles / nom
        if not p.exists():
            return {}
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    def recharger(self) -> None:
        self.etat = self._yaml("etat.yaml")
        self.efvp = self._yaml("efvp.yaml")
        self.registre = self._yaml("registre_systemes.yaml")

    # ── G-02 : verrou de collecte ───────────────────────────
    @property
    def avis_ethique(self) -> bool:
        return bool((self.etat.get("avis_ethique") or {}).get("obtenu"))

    def exiger_avis_ethique(self, action: str) -> None:
        if not self.avis_ethique:
            raise VerrouGouvernance(
                f"{action} : refusé tant que l'avis éthique n'est pas consigné (jalon J02, EPTC 2). "
                "Les essais sans personne participante restent permis ; renseigner gouvernance/etat.yaml "
                "(avis_ethique.obtenu, comité, référence, date) une fois l'avis obtenu.")

    # ── G-04 : couverture de l'EFVP ─────────────────────────
    def efvp_ecarts(self) -> dict[str, dict[str, str | None]]:
        f, c = self.efvp.get("fonctions", {}), self.efvp.get("couverture", {})
        return {k: {"version": v, "couverte": c.get(k)} for k, v in f.items()
                if c.get(k) is None or _version(v) > _version(c[k])}

    def exiger_efvp(self, fonction: str) -> None:
        e = self.efvp_ecarts().get(fonction)
        if e:
            raise VerrouGouvernance(
                f"La fonction « {fonction} » (version {e['version']}) n'est pas couverte par l'EFVP en vigueur "
                f"(couverture : {e['couverte'] or 'aucune'}). Réviser l'EFVP, puis gouvernance/efvp.yaml (G-04).")

    def exiger_collecte(self, action: str, fonction: str) -> None:
        """Verrous cumulés avant toute collecte auprès de personnes participantes."""
        self.exiger_avis_ethique(action)
        self.exiger_efvp(fonction)

    # ── G-03 : registre des systèmes ────────────────────────
    def synchroniser_registre(self, resolus: dict[str, str]) -> list[str]:
        """Inscrit les versions adoptées (D13) dans le registre ; renvoie les changements."""
        s = self.registre.setdefault("systemes", {})
        nouv = {"SI-01": f"{resolus.get('claude-opus')} ; {resolus.get('claude-sonnet')}",
                "SI-08": f"{resolus.get('gpt-sol')} ; {resolus.get('gpt-luna')}"}
        changes = []
        for si, v in nouv.items():
            if si in s and str(s[si].get("version_courante")) != v and "None" not in v:
                changes.append(f"{si} : {s[si].get('version_courante')} → {v}")
                s[si]["version_courante"] = v
        if changes:
            journal = self.donnees / "registre_versions.jsonl"
            with journal.open("a", encoding="utf-8") as fo:
                for c in changes:
                    fo.write(json.dumps({"date": datetime.now().astimezone().isoformat(timespec="seconds"),
                                         "changement": c}, ensure_ascii=False) + "\n")
            p = self.regles / "registre_systemes.yaml"
            texte = p.read_text(encoding="utf-8")
            for si, v in nouv.items():
                texte = re.sub(rf"(  {si}:\n(?:    .*\n)*?    version_courante: ).*\n", rf"\g<1>{v}\n", texte)
            p.write_text(texte, encoding="utf-8")
        return changes

    # ── P-04 : revue trimestrielle ──────────────────────────
    def revue_due(self, aujourd_hui: date | None = None) -> dict[str, Any]:
        d = (self.etat.get("politique_ia") or {}).get("prochaine_revue")
        aujourd_hui = aujourd_hui or date.today()
        if not d:
            return {"date": None, "jours": None, "due": True}
        j = (date.fromisoformat(str(d)) - aujourd_hui).days
        return {"date": str(d), "jours": j, "due": j <= 14}

    def resume(self) -> dict[str, Any]:
        return {"avis_ethique": self.etat.get("avis_ethique"), "efvp_ecarts": self.efvp_ecarts(),
                "politique_ia": self.etat.get("politique_ia"), "revue": self.revue_due(),
                "assurance": self.etat.get("assurance_responsabilite_civile"),
                "incidents_ouverts": self.incidents.ouverts(), "systemes": self.registre.get("systemes", {}),
                "decisions_en_attente": self.decisions.en_attente()}
