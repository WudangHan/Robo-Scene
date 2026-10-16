"""Modèle de pièce, lecteurs (texte brut, Word, TEI) et répertoire DraCor.

Une pièce est un dictionnaire sérialisable :
    {id, titre, auteur, annee, source{type, ref, licence, url}, personnages[{id, nom, genre}],
     scenes[{id, acte, titre}], elements[{id, type: replique|didascalie, scene, perso, nom,
     texte, vers, didascalies[]}]}
"""
from __future__ import annotations

import gzip
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .connaissances import RACINE, lire_docx
from .texte_outils import mots, normaliser
from ..tls import contexte as _tls

DOSSIER_PIECES = RACINE / "partenaire" / "pieces"
DOSSIER_REPERTOIRE = RACINE / "partenaire" / "repertoire"
DRACOR = "https://dracor.org/api/v1"
TEI = "{http://www.tei-c.org/ns/1.0}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normaliser(s)).strip("-")[:60] or "piece"


def _espaces(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


# ─────────────────────────────────────────────────────────────
#  Texte brut et Word
# ─────────────────────────────────────────────────────────────
_NUM = r"(?:[IVXLC]+|\d+|PREMI[ÈE]RE?|[Pp]remi[èe]re?|PREMIER|UNIQUE|[Uu]nique|DERNI[ÈE]RE|[Dd]erni[èe]re)\b"
_RE_ACTE = re.compile(rf"^\s*(?:(?:ACTE|Acte|TABLEAU|Tableau)\s+{_NUM}|PROLOGUE|Prologue|ÉPILOGUE|Épilogue)")
_RE_SCENE = re.compile(rf"^\s*(?:SC[ÈE]NE|Sc[èe]ne)\s+{_NUM}")
_RE_DISTRIB = re.compile(r"^\s*(PERSONNAGES|DISTRIBUTION|ACTEURS|Personnages|Distribution)\s*:?\s*$")
_NOM = r"[A-ZÉÈÊÀÂÎÏÔÛÇŒ][A-ZÉÈÊÀÂÎÏÔÛÇŒ'’\- ]{0,30}[A-ZÉÈÊÀÂÎÏÔÛÇŒ]"
_RE_LOCUTEUR_MAJ = re.compile(rf"^\s*({_NOM}|[A-ZÉÈ])\s*(?:[.:]\s*[—–-]?|[—–-])\s*(.*)$")
_RE_LOCUTEUR_SEUL = re.compile(rf"^\s*({_NOM})\s*[.:]?\s*$")
_RE_LOCUTEUR_MIXTE = re.compile(r"^\s*([A-ZÉÈÀÂÎÔÛÇ][\wÀ-ÿ'’\-]{1,20}(?: [\wÀ-ÿ'’\-]{1,20}){0,2})\s*:\s*(.*)$")
_RE_DIDA = re.compile(r"\(([^()]{1,200})\)|\[([^\[\]]{1,200})\]")


def _extraire_didascalies(t: str) -> tuple[str, list[str]]:
    didas = [a or b for a, b in _RE_DIDA.findall(t)]
    reste = _espaces(_RE_DIDA.sub(" ", t))
    reste = re.sub(r"^[—–-]\s*", "", reste)
    return reste, [_espaces(d) for d in didas]


def lire_texte(texte: str, titre: str = "", auteur: str = "") -> dict[str, Any]:
    lignes = texte.replace("\r\n", "\n").split("\n")
    # Préambule (titre, distribution) : ignoré jusqu'au premier acte ou à la première scène
    debut = next((i for i, ln in enumerate(lignes) if _RE_ACTE.match(ln) or _RE_SCENE.match(ln)), 0)
    distribution = []
    en_distrib = False
    for ln in lignes[:debut]:
        if _RE_DISTRIB.match(ln):
            en_distrib = True
        elif en_distrib and (m := re.match(rf"^\s*({_NOM})\s*,\s*(.+)$", ln)):
            distribution.append({"nom": m.group(1).strip(), "description": m.group(2).strip()})
    lignes = lignes[debut:]
    # Premier passage : candidats « Nom : » en casse mixte, retenus s'ils reviennent au moins deux fois
    mixtes: dict[str, int] = {}
    for ln in lignes:
        if m := _RE_LOCUTEUR_MIXTE.match(ln):
            mixtes[m.group(1).strip()] = mixtes.get(m.group(1).strip(), 0) + 1
    noms_mixtes = {n for n, c in mixtes.items() if c >= 2 and len(n.split()) <= 3}

    acte, scene_titre = "", ""
    scenes: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    courant: dict[str, Any] | None = None

    def scene_courante() -> str:
        if not scenes:
            scenes.append({"id": "1", "acte": acte, "titre": scene_titre or "Scène unique"})
        return scenes[-1]["id"]

    def nouvelle_replique(nom: str, debut: str) -> dict[str, Any]:
        el = {"type": "replique", "scene": scene_courante(), "nom": nom.strip(" .:"),
              "perso": _slug(nom), "lignes": [], "vers": False}
        elements.append(el)
        if debut.strip():
            el["lignes"].append(debut.strip())
        return el

    for ln in lignes:
        brut = ln.rstrip()
        if not brut.strip():
            continue
        if _RE_ACTE.match(brut) and len(brut) < 80:
            acte = _espaces(brut)
            courant = None
            continue
        if _RE_SCENE.match(brut) and len(brut) < 160:
            scene_titre = _espaces(brut)
            scenes.append({"id": str(len(scenes) + 1), "acte": acte, "titre": scene_titre})
            courant = None
            continue
        s = brut.strip()
        if (s.startswith("(") and s.endswith(")")) or (s.startswith("[") and s.endswith("]")):
            elements.append({"type": "didascalie", "scene": scene_courante(), "texte": s[1:-1].strip()})
            courant = None
            continue
        m = _RE_LOCUTEUR_MAJ.match(brut)
        if m and m.group(1).strip() not in ("I", "A") and not _RE_ACTE.match(m.group(1)):
            courant = nouvelle_replique(m.group(1), m.group(2))
            continue
        m = _RE_LOCUTEUR_SEUL.match(brut)
        if m and len(m.group(1)) >= 2:
            courant = nouvelle_replique(m.group(1), "")
            continue
        m = _RE_LOCUTEUR_MIXTE.match(brut)
        if m and m.group(1).strip() in noms_mixtes:
            courant = nouvelle_replique(m.group(1), m.group(2))
            continue
        if courant is not None:
            courant["lignes"].append(s)
        else:
            elements.append({"type": "didascalie", "scene": scene_courante(), "texte": s})

    for el in elements:
        if el["type"] == "replique":
            brut = "\n".join(el.pop("lignes"))
            el["texte"], el["didascalies"] = _extraire_didascalies(brut)
            el["vers"] = len(brut.splitlines()) > 1 and all(len(l) < 70 for l in brut.splitlines())
    elements = [e for e in elements if e["type"] == "didascalie" or e["texte"]]
    persos = [{"id": _slug(d["nom"]), "nom": d["nom"], "genre": None, "description": d["description"]}
              for d in distribution]
    return _finaliser({"titre": titre or "Texte importé", "auteur": auteur, "annee": None,
                       "source": {"type": "texte"}, "personnages": persos, "scenes": scenes,
                       "elements": elements})


def lire_docx_piece(chemin: Path, titre: str = "", auteur: str = "") -> dict[str, Any]:
    blocs = lire_docx(chemin)
    p = lire_texte("\n".join(b.texte for b in blocs), titre or chemin.stem, auteur)
    p["source"] = {"type": "docx", "ref": chemin.name}
    return p


# ─────────────────────────────────────────────────────────────
#  TEI (DraCor, Théâtre classique…)
# ─────────────────────────────────────────────────────────────
def _texte_el(el: ET.Element, exclure_stage: bool = True) -> str:
    morceaux = [el.text or ""]
    for sub in el:
        if not (exclure_stage and sub.tag == TEI + "stage"):
            morceaux.append(_texte_el(sub, exclure_stage))
        morceaux.append(sub.tail or "")
    return "".join(morceaux)


def lire_tei(xml: str | bytes, source: dict[str, Any] | None = None) -> dict[str, Any]:
    racine = ET.fromstring(xml)
    def _premier(chemin: str) -> str:
        el = racine.find(chemin)
        return _espaces(_texte_el(el)) if el is not None else ""

    titre = _premier(f".//{TEI}titleStmt/{TEI}title")
    aut = racine.find(f".//{TEI}titleStmt/{TEI}author")
    auteur = ""
    if aut is not None:
        pn = aut.find(f".//{TEI}persName")
        auteur = _espaces(_texte_el(pn if pn is not None else aut))
        auteur = re.sub(r"\s*\b(Q\d+|\d{6,})\b", "", auteur).strip()
    licence = racine.find(f".//{TEI}availability//{TEI}licence")
    lic = ""
    if licence is not None:
        ab = licence.find(TEI + "ab")
        lic = _espaces(_texte_el(ab if ab is not None else licence))
    personnages = []
    for pers in racine.iter(TEI + "person"):
        nom = pers.find(TEI + "persName")
        personnages.append({"id": pers.get(XML_ID, ""), "nom": _espaces(_texte_el(nom)) if nom is not None else "",
                            "genre": (pers.get("sex") or "").lower() or None})
    noms = {p["id"]: p["nom"] for p in personnages}
    scenes: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    corps = racine.find(f".//{TEI}text/{TEI}body")

    def parcourir(div: ET.Element, actes: list[str]) -> None:
        tete = div.find(TEI + "head")
        t = _espaces(_texte_el(tete)) if tete is not None else ""
        enfants_div = [c for c in div if c.tag == TEI + "div"]
        a_sp = any(c.tag in (TEI + "sp", TEI + "stage") for c in div)
        if a_sp:
            sid = str(len(scenes) + 1)
            scenes.append({"id": sid, "acte": " · ".join(actes), "titre": t or f"Scène {sid}"})
            for c in div:
                if c.tag == TEI + "stage":
                    elements.append({"type": "didascalie", "scene": sid, "texte": _espaces(_texte_el(c, False))})
                elif c.tag == TEI + "sp":
                    who = (c.get("who") or "").split()[0].lstrip("#") if c.get("who") else ""
                    spk = c.find(TEI + "speaker")
                    nom = _espaces(_texte_el(spk)).strip(" .") if spk is not None else noms.get(who, who)
                    vers = c.find(TEI + "l") is not None
                    lignes = [_espaces(_texte_el(x)) for x in c if x.tag in (TEI + "l", TEI + "p", TEI + "lg")]
                    didas = []
                    for st in c.iter(TEI + "stage"):
                        didas.append({"texte": _espaces(_texte_el(st, False)), "type": st.get("type")})
                    texte = ("\n" if vers else " ").join(l for l in lignes if l)
                    if texte:
                        elements.append({"type": "replique", "scene": sid, "perso": who or _slug(nom),
                                         "nom": nom, "texte": texte, "vers": vers,
                                         "didascalies": [d["texte"] for d in didas],
                                         "didascalies_types": [d["type"] for d in didas if d["type"]]})
        for c in enfants_div:
            parcourir(c, actes + ([t] if t and not a_sp else []))

    if corps is not None:
        for d in corps:
            if d.tag == TEI + "div":
                parcourir(d, [])
    piece = {"titre": titre, "auteur": auteur, "annee": None, "source": {"type": "tei", "licence": lic,
             **(source or {})}, "personnages": personnages, "scenes": scenes, "elements": elements}
    return _finaliser(piece)


def _finaliser(p: dict[str, Any]) -> dict[str, Any]:
    vus: dict[str, dict] = {x["id"]: x for x in p.get("personnages", []) if x.get("id")}
    for i, el in enumerate(p["elements"], 1):
        el["id"] = f"E{i:04d}"
        if el["type"] == "replique":
            if el["perso"] not in vus:
                vus[el["perso"]] = {"id": el["perso"], "nom": el["nom"], "genre": None}
            el["mots"] = len(mots(el["texte"]))
    parlants = {e["perso"] for e in p["elements"] if e["type"] == "replique"}
    p["personnages"] = [v for v in vus.values() if v["id"] in parlants]
    p.setdefault("id", _slug(f"{p.get('auteur', '')} {p['titre']}"))
    return p


# ─────────────────────────────────────────────────────────────
#  Bibliothèque locale de pièces
# ─────────────────────────────────────────────────────────────
class Bibliotheque:
    def __init__(self, dossier: Path | None = None):
        self.dossier = dossier or DOSSIER_PIECES
        self.dossier.mkdir(parents=True, exist_ok=True)

    def lister(self) -> list[dict[str, Any]]:
        out = []
        for f in sorted(self.dossier.glob("*.json")):
            try:
                p = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            out.append({"id": p["id"], "titre": p["titre"], "auteur": p.get("auteur", ""),
                        "personnages": len(p["personnages"]), "scenes": len(p["scenes"]),
                        "licence": p.get("source", {}).get("licence", ""),
                        "source": p.get("source", {}).get("type", "")})
        return out

    def lire(self, pid: str) -> dict[str, Any]:
        f = self.dossier / f"{_slug(pid)}.json"
        if not f.exists():
            raise KeyError(f"Pièce inconnue : {pid}")
        return json.loads(f.read_text(encoding="utf-8"))

    def enregistrer(self, piece: dict[str, Any]) -> str:
        piece["id"] = _slug(piece["id"])
        (self.dossier / f"{piece['id']}.json").write_text(
            json.dumps(piece, ensure_ascii=False, indent=1), encoding="utf-8")
        return piece["id"]

    def supprimer(self, pid: str) -> None:
        (self.dossier / f"{_slug(pid)}.json").unlink(missing_ok=True)


# ─────────────────────────────────────────────────────────────
#  Répertoire DraCor (pièces du domaine public encodées en TEI)
# ─────────────────────────────────────────────────────────────
CHAMPS_CATALOGUE = ("name", "title", "subtitle", "firstAuthor", "yearNormalized", "normalizedGenre",
                    "numOfSpeakers", "numOfSpeakersMale", "numOfSpeakersFemale", "numOfActs",
                    "numOfScenes", "wordCountSp")


def _http(url: str, delai: float = 40) -> bytes:
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", "Accept": "application/json, */*",
                                               "User-Agent": "ROBO-SCENE-partenaire/2.0"})
    with urllib.request.urlopen(req, timeout=delai, context=_tls()) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip" or data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
        return data


class RepertoireDraCor:
    def __init__(self, dossier: Path = DOSSIER_REPERTOIRE, base: str = DRACOR):
        self.dossier, self.base = dossier, base
        self.dossier.mkdir(parents=True, exist_ok=True)

    def corpus(self) -> list[dict[str, str]]:
        f = self.dossier / "dracor_corpus.json"
        if not f.exists():
            data = json.loads(_http(f"{self.base}/corpora"))
            f.write_text(json.dumps([{"name": c["name"], "title": c.get("title", "")} for c in data],
                                    ensure_ascii=False), encoding="utf-8")
        return json.loads(f.read_text(encoding="utf-8"))

    def catalogue(self, corpus: str = "fre", rafraichir: bool = False) -> list[dict[str, Any]]:
        corpus = re.sub(r"[^a-z]", "", corpus)
        f = self.dossier / f"dracor_{corpus}.json"
        if rafraichir or not f.exists():
            data = json.loads(_http(f"{self.base}/corpora/{corpus}/metadata", 90))
            data = [{k: d.get(k) for k in CHAMPS_CATALOGUE} for d in data]
            f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return json.loads(f.read_text(encoding="utf-8"))

    def chercher(self, corpus: str = "fre", texte: str = "", genre: str = "", hommes: int | None = None,
                 femmes: int | None = None, min_perso: int | None = None, max_perso: int | None = None,
                 annee_min: int | None = None, annee_max: int | None = None, limite: int = 60) -> dict[str, Any]:
        q = normaliser(texte)
        res = []
        for d in self.catalogue(corpus):
            n = d.get("numOfSpeakers") or 0
            if q and q not in normaliser(f"{d.get('title', '')} {d.get('firstAuthor', '')}"):
                continue
            if genre and (d.get("normalizedGenre") or "") != genre:
                continue
            if hommes is not None and d.get("numOfSpeakersMale") != hommes:
                continue
            if femmes is not None and d.get("numOfSpeakersFemale") != femmes:
                continue
            if min_perso is not None and n < min_perso:
                continue
            if max_perso is not None and n > max_perso:
                continue
            a = d.get("yearNormalized")
            if annee_min is not None and (a is None or a < annee_min):
                continue
            if annee_max is not None and (a is None or a > annee_max):
                continue
            res.append(d)
        res.sort(key=lambda d: (d.get("yearNormalized") or 0, d.get("title") or ""))
        return {"total": len(res), "resultats": res[:limite],
                "genres": sorted({d.get("normalizedGenre") for d in self.catalogue(corpus) if d.get("normalizedGenre")})}

    def importer(self, corpus: str, nom: str) -> dict[str, Any]:
        corpus, nom = re.sub(r"[^a-z]", "", corpus), re.sub(r"[^a-z0-9\-]", "", nom)
        xml = _http(f"{self.base}/corpora/{corpus}/plays/{urllib.parse.quote(nom)}/tei", 90)
        meta = next((d for d in self.catalogue(corpus) if d["name"] == nom), {})
        p = lire_tei(xml, {"ref": f"dracor:{corpus}/{nom}",
                           "url": f"https://dracor.org/{corpus}/{nom}"})
        p["id"] = f"dracor-{corpus}-{nom}"
        p["annee"] = meta.get("yearNormalized")
        p["genre"] = meta.get("normalizedGenre")
        if not p["auteur"]:
            p["auteur"] = meta.get("firstAuthor", "")
        return p


# Répertoires externes vérifiés le 10 octobre 2026. Leurs textes sont, pour la
# plupart, protégés par le droit d'auteur : le partenaire n'en aspire pas le
# contenu ; il ouvre leur moteur de recherche, et vous importez ensuite le texte
# que vous détenez légalement (collage, .txt, .docx).
REPERTOIRES_EXTERNES = [
    {"nom": "Centre des auteurs dramatiques (CEAD)", "url": "https://cead.qc.ca/repertoire",
     "portee": "Théâtre québécois et franco-canadien ; répertoire avec recherche détaillée.",
     "acces": "Catalogue en ligne ; textes et droits via le CEAD et les auteurs."},
    {"nom": "Playwrights Guild of Canada", "url": "https://playwrightsguild.ca",
     "portee": "Théâtre canadien anglophone (et traductions).",
     "acces": "Catalogue ; textes et licences via la Guilde."},
    {"nom": "Le Proscenium", "url": "https://www.leproscenium.com",
     "portee": "Plus de 10 000 textes d'auteurs francophones vivants ; distribution affichée (ex. « 2H 5Fe »), genres, durée.",
     "acces": "Lecture gratuite d'extraits ou de textes ; texte intégral et autorisation de jeu auprès de l'auteur."},
    {"nom": "Théâtre-contemporain.net", "url": "https://www.theatre-contemporain.net",
     "portee": "Écritures contemporaines, fiches de textes et de spectacles.",
     "acces": "Catalogue ; textes chez les éditeurs."},
    {"nom": "Doollee", "url": "https://www.doollee.com",
     "portee": "Guide des pièces écrites ou traduites en anglais depuis 1956 (plus de 190 000 pièces) ; archive figée depuis 2021.",
     "acces": "Métadonnées seulement."},
    {"nom": "Folger Shakespeare", "url": "https://shakespeare.folger.edu/download",
     "portee": "Œuvres de Shakespeare en anglais, téléchargeables (dont TEI).",
     "acces": "Téléchargement gratuit selon les conditions d'utilisation du Folger."},
    {"nom": "DraCor (intégré)", "url": "https://dracor.org",
     "portee": "24 corpus dont français (1 940 pièces), Shakespeare, anglais, grec, latin, italien, espagnol, allemand, russe.",
     "acces": "Intégré au partenaire : recherche croisée et import du texte intégral (licence affichée par pièce)."},
]


if __name__ == "__main__":
    r = RepertoireDraCor()
    for c in ("fre", "shake"):
        print(c, len(r.catalogue(c, rafraichir=True)))
