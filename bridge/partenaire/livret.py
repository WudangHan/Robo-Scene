"""Le livret d'exercices structuré : fiches, calendriers, grille d'auto-évaluation, séances.

    python -m bridge.partenaire.livret     (régénère partenaire/index/livret.json)

Le format constant du livret (titre, fiche technique, justification,
déroulement, variantes, note pédagogique) permet une extraction fidèle :
le partenaire restitue le texte du livret, il ne le réécrit pas.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

from .connaissances import RACINE, Bloc, lire_docx
from .texte_outils import normaliser

SOURCE = RACINE / "partenaire" / "sources" / "Livret_acteurs_Edition_integrale_enrichie_2026.docx"
CHEMIN = RACINE / "partenaire" / "index" / "livret.json"

ANNEES = {"I": 1, "II": 2, "III": 3}
_RE_PARTIE = re.compile(r"^Partie (I{1,3}) — .*\((\d+) heures\)")
_RE_CHAP = re.compile(r"^Chapitre (\d+)\s*:\s*(.+)$")
_RE_EX = re.compile(r"^Exercice (\d+)\.(\d+)\s*[–-]\s*«\s*(.+?)\s*»")
_RE_MIN = re.compile(r"\((\d+)\s*min(?:utes?)?\)")


def _nettoyer(t: str) -> str:
    return re.sub(r"[   ]+", " ", t).strip()


def _fiche(table: str) -> dict[str, str]:
    d = {}
    for ligne in table.splitlines():
        if "|" in ligne:
            k, _, v = ligne.partition("|")
            d[normaliser(k.strip())] = _nettoyer(v)
    return d


def _duree_min(s: str) -> int | None:
    m = re.search(r"(\d+)\s*minutes?", s or "")
    return int(m.group(1)) if m else None


def extraire(blocs: list[Bloc]) -> dict[str, Any]:
    exercices: list[dict[str, Any]] = []
    annees: dict[int, dict[str, Any]] = {}
    annee, heures, chapitre, titre_chap = 0, 0, 0, ""
    ex: dict[str, Any] | None = None
    zone = ""
    chapitre9: dict[int, list[str]] = {}

    def clore():
        nonlocal ex
        if ex:
            ex["duree_min"] = ex["duree_min"] or sum(e["minutes"] or 0 for e in ex["etapes"]) or None
            exercices.append(ex)
        ex = None

    for b in blocs:
        t = _nettoyer(b.texte)
        if m := _RE_PARTIE.match(t):
            clore()
            annee, heures = ANNEES[m.group(1)], int(m.group(2))
            annees.setdefault(annee, {"annee": annee, "heures": heures, "titre": t, "chapitres": {}})
            chapitre, zone = 0, ""
            continue
        if not annee:
            continue
        if (m := _RE_CHAP.match(t)) and b.niveau:
            clore()
            chapitre, titre_chap = int(m.group(1)), m.group(2)
            annees[annee]["chapitres"][chapitre] = titre_chap
            zone = "chap9" if chapitre == 9 else "intro"
            continue
        if t.startswith(("Conclusion de la", "Conclusion générale", "Bibliographie")):
            clore()
            zone = "hors"
            continue
        if zone == "chap9":
            chapitre9.setdefault(annee, []).append(t)
            continue
        if m := _RE_EX.match(t):
            clore()
            ex = {
                "id": f"A{annee}-{m.group(1)}.{m.group(2)}", "annee": annee, "chapitre": chapitre,
                "titre_chapitre": titre_chap, "numero": f"{m.group(1)}.{m.group(2)}",
                "titre": m.group(3), "duree_min": None, "objectif": "", "justification": [],
                "etapes": [], "variantes": [], "note": "", "citations": [],
            }
            zone = "fiche"
            continue
        if ex is None:
            continue
        if "Durée |" in t or "Objectif |" in t:
            f = _fiche(b.texte)
            ex["duree_min"] = _duree_min(f.get("duree", ""))
            ex["duree_texte"] = f.get("duree", "")
            ex["objectif"] = f.get("objectif", "")
            zone = "justification"
        elif t == "Déroulement":
            zone = "etapes"
        elif t == "Variantes":
            zone = "variantes"
        elif t.startswith("Note pédagogique"):
            ex["note"] = re.sub(r"^Note pédagogique\s*:\s*", "", t)
        elif t.startswith("«") and "—" in t:
            ex["citations"].append(t)
        elif zone == "justification":
            ex["justification"].append(t)
        elif zone == "etapes":
            mm = _RE_MIN.search(t)
            titre, _, corps = t.partition(":")
            court = len(titre) < 60 and corps
            ex["etapes"].append({
                "titre": re.sub(r"\s*\(.*?\)\s*$", "", titre).strip() if court else "",
                "texte": t, "minutes": int(mm.group(1)) if mm else None,
            })
        elif zone == "variantes":
            ex["variantes"].append(t)
    clore()

    # Calendriers et grille d'auto-évaluation (chapitres 9)
    calendriers, grille, criteres = {}, [], []
    for a, lignes in chapitre9.items():
        cal = []
        for t in lignes:
            if m := re.match(r"^Semaines (\d+) à (\d+) — ([^:]+):\s*(.*)$", t):
                refs = re.findall(r"\b(\d\.\d)\b", m.group(4))
                cal.append({"semaines": [int(m.group(1)), int(m.group(2))], "theme": m.group(3).strip(),
                            "description": m.group(4), "exercices": [f"A{a}-{r}" for r in refs]})
            elif a == 1 and t.startswith("Domaine |"):
                grille = [ln.split("|")[0].strip() for ln in t.splitlines()[1:] if "|" in ln]
            elif a == 1 and re.match(r"^[^:]{3,40}\(\d+ %\)\s*:", t):
                criteres.append(t)
        if cal:
            calendriers[a] = cal
    return {"source": SOURCE.name, "exercices": exercices,
            "annees": {a: {**v, "chapitres": {str(k): c for k, c in v["chapitres"].items()}}
                       for a, v in annees.items()},
            "calendriers": calendriers, "grille_auto_evaluation": grille,
            "criteres_evaluation": criteres}


def construire(source: Path = SOURCE, sortie: Path = CHEMIN) -> dict[str, Any]:
    donnees = extraire(lire_docx(source))
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")
    return donnees


class Livret:
    def __init__(self, donnees: dict[str, Any]):
        self.d = donnees
        self.exercices = donnees["exercices"]
        self.par_id = {e["id"]: e for e in self.exercices}

    @classmethod
    def charger(cls, chemin: Path = CHEMIN) -> "Livret":
        if chemin.exists():
            return cls(json.loads(chemin.read_text(encoding="utf-8")))
        if SOURCE.exists():
            return cls(construire())
        return cls({"exercices": [], "annees": {}, "calendriers": {}, "grille_auto_evaluation": [],
                    "criteres_evaluation": []})

    def sommaire(self) -> list[dict[str, Any]]:
        return [{k: e[k] for k in ("id", "annee", "chapitre", "titre_chapitre", "numero", "titre",
                                   "duree_min", "objectif")} for e in self.exercices]

    def chercher(self, texte: str) -> list[dict[str, Any]]:
        q = normaliser(texte)
        return [e for e in self.sommaire()
                if q in normaliser(e["titre"] + " " + e["objectif"] + " " + e["titre_chapitre"])]

    def planifier(self, annee: int, deja_faits: set[str] | None = None, graine: int | None = None,
                  chapitres: list[int] | None = None) -> dict[str, Any]:
        """Séance type du livret : échauffement 10-15 min, deux exercices de fond
        d'environ 20 min, une synthèse d'environ 15 min, un bilan collectif de 10 min."""
        rnd = random.Random(graine)
        deja = deja_faits or set()
        pool = [e for e in self.exercices if e["annee"] == annee and e["duree_min"]
                and (not chapitres or e["chapitre"] in chapitres)]

        def choisir(lo: int, hi: int, exclus: set[str]) -> dict | None:
            cand = [e for e in pool if lo <= e["duree_min"] <= hi and e["id"] not in exclus]
            neufs = [e for e in cand if e["id"] not in deja]
            choix = neufs or cand
            return rnd.choice(choix) if choix else None

        exclus: set[str] = set()
        plan = []
        echauffement = (self.par_id.get(f"A{annee}-1.2") if annee == 1 else None) or choisir(8, 15, exclus)
        for role, lo, hi in (("Échauffement", 0, 0), ("Exercice de fond", 15, 30),
                             ("Exercice de fond", 15, 30), ("Synthèse", 10, 20)):
            e = echauffement if role == "Échauffement" else choisir(lo, hi, exclus)
            if e:
                exclus.add(e["id"])
                plan.append({"role": role, "exercice": e["id"], "titre": e["titre"],
                             "duree_min": e["duree_min"]})
        plan.append({"role": "Bilan collectif", "exercice": None, "titre": "Bilan collectif",
                     "duree_min": 10})
        return {"annee": annee, "plan": plan, "duree_totale_min": sum(p["duree_min"] or 0 for p in plan),
                "regle": "Structure de séance type de la première année du livret (Partie I)."}


# Accompagnement du robot pendant un exercice (heuristique sur le titre et le texte)
def accompagnement(ex: dict[str, Any]) -> str:
    t = normaliser(ex["titre"] + " " + " ".join(s["texte"] for s in ex["etapes"]))
    if "respiration" in t or "souffle" in t:
        return "souffle"
    if "silence" in t:
        return "immobile"
    if "laban" in t or "mouvement" in t or "geste" in t:
        return "miroir_lent"
    return "attentif"


if __name__ == "__main__":
    d = construire()
    print(f"{len(d['exercices'])} exercices ; calendriers : {list(d['calendriers'])} ; "
          f"grille : {d['grille_auto_evaluation']}")
