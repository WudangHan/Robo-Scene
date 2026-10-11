"""Q-05 — Codage des entretiens (agentivité déclarée) en traitement local seulement (D03).

* Les transcriptions (jeu DO-02, pseudonymisées) sont lues sur le poste, découpées en segments (paragraphes).
* Une pré-codification facultative est demandée au modèle LOCAL seulement : l'appel passe par le service des
  modèles avec « confidentielle=True », ce qui force la cible locale et refuse la génération si le modèle local
  est indisponible (aucun repli distant). La réponse est en outre contrôlée : toute réponse qui ne viendrait
  pas de la famille « local » est rejetée.
* Toute suggestion porte le statut « suggéré » ; seul un codage validé par une personne entre dans l'analyse.
* Accord intercodeurs : alpha de Krippendorff (fonction du prototype P1, grille_biais.alpha_krippendorff),
  nominal, sur la présence de chaque code par segment, comme le prévoit l'onglet « Fiabilité » du livre A.1.
* (Inférence) Indice d'agentivité déclarée au système, par personne : (AG-DECL-SYS + ½ AG-PARTAGE) /
  (AG-DECL-SOI + AG-DECL-SYS + AG-PARTAGE), sur les codages validés ; choix de la plateforme, à valider.
"""
from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .. import _modules  # noqa: F401
from atelier_p1.grille_biais import alpha_krippendorff

LIVRE = Path(_modules.RACINE) / "analyse" / "livre_de_codes_A1.yaml"
CODES_AGENTIVITE = ("AG-DECL-SOI", "AG-DECL-SYS", "AG-PARTAGE")


class TraitementDistantRefuse(RuntimeError):
    pass


def livre(chemin: Path = LIVRE) -> list[dict[str, Any]]:
    return yaml.safe_load(chemin.read_text(encoding="utf-8"))["codes"]


def segmenter(texte: str, pseudonyme: str, document: str) -> list[dict[str, Any]]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", texte) if p.strip()]
    return [{"document": document, "pseudonyme": pseudonyme, "segment": i, "texte": p} for i, p in enumerate(paras, 1)]


SYSTEME = """Tu aides à coder un entretien de recherche selon un livre de codes fermé.
Pour le segment fourni, réponds UNIQUEMENT par un objet JSON {"codes": ["CODE", ...], "justification": "…"}.
N'emploie que des codes du livre ; aucun code si aucun ne s'applique. Tu proposes ; une personne décide."""


def suggerer(service, segment: dict[str, Any], codes: list[dict[str, Any]]) -> dict[str, Any]:
    """Pré-codification par le modèle local (D03)."""
    resume = "\n".join(f"{c['code']} — {c.get('libelle', '')} : {c.get('definition', '')} "
                       f"(utiliser quand : {c.get('utiliser_quand', '')})" for c in codes if c.get("definition"))
    r = service.generer_sync("analyse", SYSTEME, f"Livre de codes :\n{resume}\n\nSegment :\n{segment['texte']}",
                             temperature=0.0, max_tokens=400, confidentielle=True, json_attendu=True)
    if getattr(r, "famille", None) != "local":
        raise TraitementDistantRefuse("Réponse non locale : rejetée (D03)")
    m = re.search(r"\{.*\}", r.texte, re.S)
    d = json.loads(m.group(0)) if m else {"codes": []}
    connus = {c["code"] for c in codes}
    return {"codes": [c for c in d.get("codes", []) if c in connus],
            "codes_rejetes": [c for c in d.get("codes", []) if c not in connus],
            "justification": str(d.get("justification", ""))[:500], "modele": r.modele_exact, "statut": "suggéré"}


class Codage:
    """Codages d'un codeur (pseudonyme de codeur) : fichier JSON Lines dans donnees/analyse/entretiens/."""

    def __init__(self, dossier: str | Path, codeur: str):
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,20}", codeur or ""):
            raise ValueError("Codeur : 2 à 20 caractères alphanumériques (pseudonyme)")
        self.dossier = Path(dossier) / "entretiens"
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.codeur = codeur
        self.fichier = self.dossier / f"codage_{codeur}.jsonl"

    def coder(self, segment: dict[str, Any], codes: list[str], *, statut: str = "valide", memo: str = "",
              connus: set[str] | None = None) -> dict[str, Any]:
        if statut not in ("valide", "suggéré"):
            raise ValueError("Statut : valide ou suggéré")
        if connus is not None and (inconnus := [c for c in codes if c not in connus]):
            raise ValueError(f"Codes absents du livre : {', '.join(inconnus)}")
        l = {"date": datetime.now().astimezone().isoformat(timespec="seconds"), "codeur": self.codeur,
             "document": segment["document"], "pseudonyme": segment["pseudonyme"], "segment": segment["segment"],
             "codes": sorted(set(codes)), "statut": statut, "memo": memo[:500]}
        with self.fichier.open("a", encoding="utf-8") as f:
            f.write(json.dumps(l, ensure_ascii=False) + "\n")
        return l

    def lire(self, valides_seulement: bool = True) -> list[dict[str, Any]]:
        if not self.fichier.exists():
            return []
        dernier: dict[tuple, dict] = {}
        for x in map(json.loads, self.fichier.read_text(encoding="utf-8").splitlines()):
            dernier[(x["document"], x["segment"])] = x     # la dernière décision fait foi
        return [x for x in dernier.values() if x["statut"] == "valide" or not valides_seulement]


def accord(codages_a: list[dict[str, Any]], codages_b: list[dict[str, Any]], codes: list[str]) -> dict[str, Any]:
    a = {(x["document"], x["segment"]): set(x["codes"]) for x in codages_a}
    b = {(x["document"], x["segment"]): set(x["codes"]) for x in codages_b}
    communs = sorted(set(a) & set(b))
    res = {}
    for c in codes:
        unites = [[int(c in a[k]), int(c in b[k])] for k in communs]
        if any(sum(u) for u in unites):
            res[c] = alpha_krippendorff(unites, "nominal")
    return {"segments_communs": len(communs), "alpha_par_code": res,
            "note": "Alpha nominal sur la présence du code ; None quand le code n'a qu'une valeur observée."}


def agentivite_declaree(codages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    par: dict[str, dict[str, int]] = {}
    for x in codages:
        c = par.setdefault(x["pseudonyme"], {k: 0 for k in CODES_AGENTIVITE})
        for k in CODES_AGENTIVITE:
            c[k] += int(k in x["codes"])
    out = {}
    for p, c in par.items():
        tot = sum(c.values())
        out[p] = {**c, "indice_declare_systeme": round((c["AG-DECL-SYS"] + 0.5 * c["AG-PARTAGE"]) / tot, 4) if tot else None}
    return out


def exporter_csv(codages: list[dict[str, Any]], chemin: Path) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["document", "pseudonyme", "segment", "codeur", "codes", "statut", "date"])
        for x in codages:
            w.writerow([x["document"], x["pseudonyme"], x["segment"], x["codeur"], "|".join(x["codes"]), x["statut"], x["date"]])
    return chemin
