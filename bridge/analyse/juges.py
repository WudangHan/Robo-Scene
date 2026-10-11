"""O-02 — Validation par juges des variations émotionnelles (régimes « humain » et « machinique »).

Le cahier pose la condition : « heuristiques non validées : validation par juges avant tout usage analytique ».
Protocole outillé ici :
1. une étude rassemble des stimuli (variation rendue : voix et geste) dont l'émotion visée et le régime sont
   connus de la plateforme mais cachés aux juges, présentés dans un ordre propre à chaque juge (graine) ;
2. chaque juge (pseudonyme) étiquette l'émotion perçue (catégorie fermée) et l'intensité (1–9) ;
3. l'accord entre juges est mesuré par l'alpha de Krippendorff (fonction du prototype P1), nominal pour
   l'émotion, intervalle pour l'intensité ; la justesse est la part d'étiquettes égales à l'émotion visée.

Seuils : Krippendorff retient α ≥ 0,800 et tolère 0,667 ≤ α < 0,800 pour des conclusions provisoires (Krippendorff,
*Content Analysis*, 2e éd., Sage, 2004, p. 241-243, d'après la notice « Krippendorff's alpha » de Wikipédia,
consultée le 11 oct. 2026 ; pagination à confirmer dans l'ouvrage). La
plateforme en déduit trois statuts par régime : « non validé », « exploratoire » (≥ 0,667), « validé » (≥ 0,800).
"""
from __future__ import annotations

import json
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import _modules  # noqa: F401
from atelier_p1.grille_biais import alpha_krippendorff

SEUIL_PROVISOIRE, SEUIL_VALIDE = 0.667, 0.800


class EtudeJuges:
    def __init__(self, dossier_donnees: str | Path, nom: str):
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", nom):
            raise ValueError("Nom d'étude : 2 à 40 caractères alphanumériques")
        self.dossier = Path(dossier_donnees) / "analyse" / "juges"
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.nom = nom
        self.f_stimuli = self.dossier / f"{nom}_stimuli.json"
        self.f_cotes = self.dossier / f"{nom}_cotes.jsonl"

    def definir(self, stimuli: list[dict[str, Any]], categories: list[str]) -> dict[str, Any]:
        """stimuli : {id, regime, emotion_visee, intensite_visee, rendu} ; le rendu est ce que voit le juge."""
        if self.f_stimuli.exists():
            raise FileExistsError("Étude déjà définie : en créer une autre plutôt que de la modifier")
        for s in stimuli:
            if s.get("regime") not in ("humain", "machinique") or s.get("emotion_visee") not in categories:
                raise ValueError(f"Stimulus {s.get('id')} : régime ou émotion visée invalide")
        d = {"nom": self.nom, "categories": categories, "stimuli": stimuli,
             "date": datetime.now().astimezone().isoformat(timespec="seconds")}
        self.f_stimuli.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        return {"stimuli": len(stimuli)}

    def _etude(self) -> dict[str, Any]:
        return json.loads(self.f_stimuli.read_text(encoding="utf-8"))

    def sequence(self, juge: str) -> list[dict[str, Any]]:
        """Ordre propre au juge, sans l'émotion visée ni le régime (aveugle)."""
        e = self._etude()
        ordre = list(e["stimuli"])
        random.Random(f"{self.nom}:{juge}").shuffle(ordre)
        return [{"id": s["id"], "rendu": s.get("rendu")} for s in ordre]

    def coter(self, juge: str, stimulus: str, emotion: str, intensite: int | None = None) -> None:
        e = self._etude()
        if emotion not in e["categories"]:
            raise ValueError("Catégorie inconnue")
        if stimulus not in {s["id"] for s in e["stimuli"]}:
            raise ValueError("Stimulus inconnu")
        if intensite is not None and not (1 <= int(intensite) <= 9):
            raise ValueError("Intensité : 1 à 9")
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,20}", juge):
            raise ValueError("Juge : pseudonyme")
        with self.f_cotes.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"juge": juge, "stimulus": stimulus, "emotion": emotion,
                                "intensite": None if intensite is None else int(intensite),
                                "date": datetime.now().astimezone().isoformat(timespec="seconds")},
                               ensure_ascii=False) + "\n")

    def resultats(self) -> dict[str, Any]:
        e = self._etude()
        cotes: dict[tuple[str, str], dict] = {}
        if self.f_cotes.exists():
            for x in map(json.loads, self.f_cotes.read_text(encoding="utf-8").splitlines()):
                cotes[(x["stimulus"], x["juge"])] = x          # dernière cote du juge
        juges = sorted({j for _, j in cotes})
        par_regime: dict[str, dict[str, Any]] = {}
        for regime in ("humain", "machinique"):
            st = [s for s in e["stimuli"] if s["regime"] == regime]
            emo = [[(cotes.get((s["id"], j)) or {}).get("emotion") for j in juges] for s in st]
            inten = [[(cotes.get((s["id"], j)) or {}).get("intensite") for j in juges] for s in st]
            justes = [c == s["emotion_visee"] for s, ligne in zip(st, emo) for c in ligne if c is not None]
            a = alpha_krippendorff(emo, "nominal") if st else None
            par_regime[regime] = {
                "stimuli": len(st), "alpha_emotion": a,
                "alpha_intensite": alpha_krippendorff(inten, "intervalle") if st else None,
                "justesse": round(sum(justes) / len(justes), 4) if justes else None,
                "statut": "validé" if a is not None and a >= SEUIL_VALIDE else
                          "exploratoire" if a is not None and a >= SEUIL_PROVISOIRE else "non validé"}
        r = {"etude": self.nom, "juges": len(juges), "par_regime": par_regime,
             "seuils": {"provisoire": SEUIL_PROVISOIRE, "valide": SEUIL_VALIDE}}
        (self.dossier / f"{self.nom}_resultats.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        return r


def statut_regimes(dossier_donnees: str | Path) -> dict[str, str]:
    """Meilleur statut obtenu par régime, toutes études confondues (lu par le partenaire et l'analyse)."""
    rang = {"non validé": 0, "exploratoire": 1, "validé": 2}
    meilleur = {"humain": "non validé", "machinique": "non validé"}
    for f in (Path(dossier_donnees) / "analyse" / "juges").glob("*_resultats.json"):
        for reg, v in json.loads(f.read_text(encoding="utf-8"))["par_regime"].items():
            if rang[v["statut"]] > rang[meilleur[reg]]:
                meilleur[reg] = v["statut"]
    return meilleur
