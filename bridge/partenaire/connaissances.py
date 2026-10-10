"""Base de connaissances du partenaire : ingestion de documents et recherche BM25.

    python -m bridge.partenaire.connaissances            (reconstruit l'index)
    python -m bridge.partenaire.connaissances "question"  (interroge l'index)

Formats lus sans dépendance : .docx, .md, .txt, .html ; .pdf avec pypdf
ou, à défaut, l'utilitaire pdftotext. Chaque passage garde sa source,
sa section et, pour un PDF, sa page : le partenaire ne cite jamais un
passage dont il ne peut donner l'origine.
"""
from __future__ import annotations

import html
import json
import math
import re
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .texte_outils import jetons, normaliser

RACINE = Path(__file__).resolve().parents[2]
DOSSIER_SOURCES = RACINE / "partenaire" / "sources"
CHEMIN_INDEX = RACINE / "partenaire" / "index" / "corpus.json"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Domaines du spectacle (étiquetage heuristique pour le filtrage des recherches)
DOMAINES: dict[str, tuple[str, ...]] = {
    "jeu": ("acteur", "jeu", "interpret", "personnage", "role", "presence", "emotion", "stanislavski",
            "meisner", "improvis", "sous-texte", "intention"),
    "voix": ("voix", "vocal", "souffle", "respiration", "diction", "articulation", "resonance", "projection"),
    "corps": ("corps", "mouvement", "geste", "laban", "posture", "marche", "ancrage", "choregraph", "effort"),
    "dramaturgie": ("dramaturg", "texte", "piece", "scene", "acte", "replique", "fable", "conflit",
                    "tragedie", "comedie", "postdramatique", "ecriture"),
    "mise_en_scene": ("mise en scene", "metteur", "direction", "repetition", "plateau", "partition"),
    "scenographie": ("scenograph", "lumiere", "eclairage", "son", "acoustique", "costume", "espace scenique",
                     "decor", "projection mapping"),
    "pedagogie": ("formation", "exercice", "seance", "formateur", "apprentissage", "pedagog", "etudiant"),
    "robotique": ("robot", "humanoide", "cobot", "servo", "actionneur", "ros 2", "capteur", "unitree",
                  "pepper", "bras robotique"),
    "ia": ("intelligence artificielle", " ia ", "agi", "asi", "apprentissage automatique", "modele",
           "algorithm", "llm", "renforcement", "neuronal"),
    "ethique": ("ethique", "consentement", "securite", "risque", "responsab", "iso", "donnees", "vie privee"),
    "recherche": ("hypothese", "methodolog", "protocole", "trajectoire", "relation", "mecanisme",
                  "recherche-creation", "inference", "variable"),
}


# ─────────────────────────────────────────────────────────────
#  Extraction de texte
# ─────────────────────────────────────────────────────────────
@dataclass
class Bloc:
    texte: str
    niveau: int = 0          # 0 = paragraphe ; 1..3 = titre
    page: int | None = None


def _texte_noeud(p: ET.Element) -> str:
    morceaux = []
    for el in p.iter():
        if el.tag == W + "t" and el.text:
            morceaux.append(el.text)
        elif el.tag in (W + "tab",):
            morceaux.append("\t")
        elif el.tag in (W + "br", W + "cr"):
            morceaux.append("\n")
    return "".join(morceaux).strip()


def lire_docx(chemin: Path) -> list[Bloc]:
    with zipfile.ZipFile(chemin) as z:
        racine = ET.fromstring(z.read("word/document.xml"))
    corps = racine.find(W + "body")
    blocs: list[Bloc] = []
    for el in list(corps) if corps is not None else []:
        if el.tag == W + "p":
            t = _texte_noeud(el)
            if not t:
                continue
            style = el.find(f"{W}pPr/{W}pStyle")
            val = (style.get(W + "val") if style is not None else "") or ""
            m = re.search(r"(?:heading|titre)\s*(\d)", val, re.I)
            niveau = int(m.group(1)) if m else (1 if val.lower() in ("title", "titre") else 0)
            blocs.append(Bloc(t, min(niveau, 3)))
        elif el.tag == W + "tbl":
            lignes = []
            for tr in el.iter(W + "tr"):
                cellules = [_texte_noeud(tc) for tc in tr.iter(W + "tc")]
                cellules = [c for c in cellules if c]
                if cellules:
                    lignes.append(" | ".join(cellules))
            if lignes:
                blocs.append(Bloc("\n".join(lignes)))
    return blocs


def lire_pdf(chemin: Path) -> list[Bloc]:
    pages: list[str] = []
    try:
        from pypdf import PdfReader  # facultatif
        pages = [(p.extract_text() or "") for p in PdfReader(str(chemin)).pages]
    except Exception:
        if shutil.which("pdftotext"):
            sortie = subprocess.run(["pdftotext", "-layout", str(chemin), "-"],
                                    capture_output=True, text=True, check=False).stdout
            pages = sortie.split("\f")
    blocs = []
    for i, txt in enumerate(pages, 1):
        for para in re.split(r"\n\s*\n", txt):
            para = re.sub(r"\s+", " ", para).strip()
            if len(para) > 30:
                blocs.append(Bloc(para, 0, i))
    return blocs


def lire_html(chemin: Path) -> list[Bloc]:
    s = chemin.read_text(encoding="utf-8", errors="replace")
    s = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", s)
    blocs = []
    for m in re.finditer(r"(?is)<(h[1-4]|p|li|div)[^>]*>(.*?)</\1>", s):
        t = html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) > 2 and not re.search(r"<(p|div|li)", m.group(2), re.I):
            niveau = int(m.group(1)[1]) if m.group(1).lower().startswith("h") else 0
            blocs.append(Bloc(t, min(niveau, 3)))
    return blocs


def lire_markdown(chemin: Path) -> list[Bloc]:
    blocs = []
    for para in re.split(r"\n\s*\n", chemin.read_text(encoding="utf-8", errors="replace")):
        para = para.strip()
        if not para or para.startswith("```"):
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", para)
        if m and "\n" not in para:
            blocs.append(Bloc(m.group(2).strip(), min(len(m.group(1)), 3)))
        else:
            blocs.append(Bloc(re.sub(r"[*_`#>]", "", para)))
    return blocs


LECTEURS = {".docx": lire_docx, ".pdf": lire_pdf, ".html": lire_html, ".htm": lire_html,
            ".md": lire_markdown, ".txt": lire_markdown}

_COURRIEL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def _titre_section(b: Bloc) -> bool:
    if b.niveau:
        return True
    t = b.texte
    return bool(len(t) < 120 and re.match(
        r"^(Partie|Chapitre|Annexe|Exercice|Axe|Conclusion|Introduction|\d+(\.\d+)*\.?\s+[A-ZÉÀ])", t))


def decouper(blocs: list[Bloc], source: str, titre: str, cible: int = 170) -> list[dict[str, Any]]:
    """Regroupe les paragraphes en passages d'environ `cible` mots sous leur section."""
    passages, tampon, section, page = [], [], "", None

    def vider():
        if tampon:
            texte = "\n".join(tampon).strip()
            if len(texte.split()) >= 8:
                passages.append({"source": source, "titre_source": titre, "section": section,
                                 "page": page, "texte": texte})
            tampon.clear()

    for b in blocs:
        if _titre_section(b) and b.page is None:
            vider()
            section = b.texte[:160]
            continue
        if b.page is not None and b.page != page:
            vider()
            page = b.page
        tampon.append(_COURRIEL.sub("[courriel retiré]", b.texte))
        if sum(len(t.split()) for t in tampon) >= cible:
            vider()
    vider()
    return passages


def etiqueter(texte: str) -> list[str]:
    t = " " + normaliser(texte) + " "
    return [d for d, cles in DOMAINES.items() if sum(t.count(c) for c in cles) >= 2] or ["general"]


TITRES_CONNUS = {
    "Livret_acteurs": "Livret d'exercices pour acteurs (Gagné, 2026)",
    "Programme_de_recherche": "Programme de recherche ROBO-SCÈNE 2026, version révisée",
    "Edition_restructuree": "ROBO-SCÈNE 2026 — édition restructurée",
    "Dossier_experimental": "ROBO-SCÈNE — dossier expérimental, chapitres 7 à 9",
    "AGI_to_ASI": "Genewein et al., « From AGI to ASI » (arXiv:2606.12683, 2026)",
    "Postdoctorat": "L'Acteur augmenté — dramaturgie computationnelle (programme de recherche)",
    "Theatre_du_Triomphe": "Site Web du Théâtre du Triomphe",
}


def construire_index(dossier: Path = DOSSIER_SOURCES, sortie: Path = CHEMIN_INDEX) -> dict[str, Any]:
    passages: list[dict[str, Any]] = []
    rapport = []
    for f in sorted(dossier.iterdir()):
        lecteur = LECTEURS.get(f.suffix.lower())
        if not lecteur or f.name.startswith("."):
            continue
        titre = next((v for k, v in TITRES_CONNUS.items() if k in f.name), f.stem.replace("_", " "))
        try:
            p = decouper(lecteur(f), f.name, titre)
        except Exception as exc:  # fichier corrompu : on le signale et on continue
            rapport.append({"source": f.name, "erreur": str(exc)})
            continue
        passages.extend(p)
        rapport.append({"source": f.name, "passages": len(p)})
    for i, p in enumerate(passages):
        p["id"] = f"K{i:05d}"
        p["domaines"] = etiqueter(p["section"] + " " + p["texte"])
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps({"version": 1, "passages": passages, "rapport": rapport},
                                 ensure_ascii=False), encoding="utf-8")
    return {"passages": len(passages), "rapport": rapport}


# ─────────────────────────────────────────────────────────────
#  Recherche BM25 (Robertson et Zaragoza)
# ─────────────────────────────────────────────────────────────
class Index:
    def __init__(self, passages: list[dict[str, Any]], k1: float = 1.4, b: float = 0.75):
        self.passages = passages
        self.k1, self.b = k1, b
        self.tf: list[Counter] = []
        self.df: Counter = Counter()
        for p in passages:
            # la section compte double : elle résume le passage
            c = Counter(jetons(p.get("section", "")) * 2 + jetons(p["texte"]))
            self.tf.append(c)
            self.df.update(c.keys())
        self.longueurs = [sum(c.values()) for c in self.tf]
        self.moy = (sum(self.longueurs) / len(self.longueurs)) if self.longueurs else 1.0
        self.n = len(passages)

    @classmethod
    def charger(cls, chemin: Path = CHEMIN_INDEX, extra: list[dict[str, Any]] | None = None) -> "Index":
        passages = []
        if chemin.exists():
            passages = json.loads(chemin.read_text(encoding="utf-8"))["passages"]
        return cls(passages + (extra or []))

    def ajouter(self, nouveaux: list[dict[str, Any]]) -> None:
        self.__init__(self.passages + nouveaux, self.k1, self.b)

    def idf(self, t: str) -> float:
        d = self.df.get(t, 0)
        return math.log(1 + (self.n - d + 0.5) / (d + 0.5))

    def rechercher(self, question: str, k: int = 6, domaines: list[str] | None = None,
                   sources: list[str] | None = None) -> list[dict[str, Any]]:
        q = jetons(question)
        if not q or not self.n:
            return []
        scores = []
        for i, tf in enumerate(self.tf):
            p = self.passages[i]
            if domaines and not set(domaines) & set(p.get("domaines", [])):
                continue
            if sources and not any(s in p["source"] for s in sources):
                continue
            s = 0.0
            for t in q:
                f = tf.get(t)
                if f:
                    s += self.idf(t) * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * self.longueurs[i] / self.moy))
            if s > 0:
                scores.append((s, i))
        scores.sort(reverse=True)
        return [{**self.passages[i], "score": round(s, 3)} for s, i in scores[:k]]


def reference(p: dict[str, Any]) -> str:
    """Référence lisible d'un passage : titre, section, page."""
    morceaux = [p.get("titre_source") or p["source"]]
    if p.get("section"):
        morceaux.append(p["section"])
    if p.get("page"):
        morceaux.append(f"p. {p['page']}")
    return " — ".join(morceaux)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        idx = Index.charger()
        for r in idx.rechercher(" ".join(sys.argv[1:])):
            print(f"[{r['id']}] {r['score']:.2f}  {reference(r)}\n    {r['texte'][:220]}…\n")
    else:
        print(json.dumps(construire_index(), ensure_ascii=False, indent=2))
