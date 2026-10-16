"""O-08 — Veille bibliographique semi-automatisée alimentant R.1 et l'atlas v2.

Condition du cahier : « toute référence vérifiée par une personne avant usage ». Les notices trouvées entrent donc
avec le statut « à vérifier » ; seule une personne peut les passer à « vérifiée » (avec une note de vérification)
ou « écartée ». Seules les notices vérifiées sont exportées en bibliographie MLA (9e éd.).

Sources interrogées (interfaces publiques, sans clé) :
* Crossref REST API — https://api.crossref.org/works?query=…&rows=… ;
* arXiv API — http://export.arxiv.org/api/query?search_query=all:…&max_results=… (Atom) ;
* Semantic Scholar Graph API — https://api.semanticscholar.org/graph/v1/paper/search?query=…&fields=…
Les notices sont dédoublonnées par DOI, puis par titre normalisé. Le module ne télécharge aucun texte intégral.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from ..tls import contexte as _tls

STATUTS = ("à vérifier", "vérifiée", "écartée")
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juill.", "août", "sept.", "oct.", "nov.", "déc."]


def _get(url: str, delai: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ROBO-SCENE-veille/1.0 (recherche universitaire)"})
    with urllib.request.urlopen(req, timeout=delai, context=_tls()) as r:
        return r.read()


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def crossref(requete: str, n: int = 10, get: Callable[[str], bytes] = _get) -> list[dict[str, Any]]:
    d = json.loads(get("https://api.crossref.org/works?" + urllib.parse.urlencode({"query": requete, "rows": n})))
    out = []
    for it in d.get("message", {}).get("items", []):
        date = (it.get("issued") or {}).get("date-parts", [[None]])[0]
        out.append({"source": "crossref", "titre": (it.get("title") or [""])[0],
                    "auteurs": [{"nom": a.get("family", ""), "prenom": a.get("given", "")} for a in it.get("author", [])],
                    "annee": date[0] if date else None, "revue": (it.get("container-title") or [""])[0],
                    "volume": it.get("volume"), "numero": it.get("issue"), "pages": it.get("page"),
                    "doi": it.get("DOI"), "url": it.get("URL"), "type": it.get("type")})
    return out


def arxiv(requete: str, n: int = 10, get: Callable[[str], bytes] = _get) -> list[dict[str, Any]]:
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": f"all:{requete}", "start": 0, "max_results": n})
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    racine = ET.fromstring(get(url))
    out = []
    for e in racine.findall("a:entry", ns):
        noms = [x.findtext("a:name", "", ns) for x in e.findall("a:author", ns)]
        pub = e.findtext("a:published", "", ns)
        aid = e.findtext("a:id", "", ns).rsplit("/abs/", 1)[-1]
        out.append({"source": "arxiv", "titre": " ".join(e.findtext("a:title", "", ns).split()),
                    "auteurs": [{"nom": n.split()[-1] if n else "", "prenom": " ".join(n.split()[:-1])} for n in noms],
                    "annee": int(pub[:4]) if pub[:4].isdigit() else None, "revue": "arXiv", "arxiv": aid,
                    "doi": e.findtext("arxiv:doi", None, ns), "url": f"https://arxiv.org/abs/{aid}",
                    "date_depot": pub[:10], "type": "preprint"})
    return out


def semantic_scholar(requete: str, n: int = 10, get: Callable[[str], bytes] = _get) -> list[dict[str, Any]]:
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(
        {"query": requete, "limit": n, "fields": "title,authors,year,venue,externalIds,url"})
    out = []
    for p in json.loads(get(url)).get("data", []):
        noms = [a.get("name", "") for a in p.get("authors", [])]
        ext = p.get("externalIds") or {}
        out.append({"source": "semantic_scholar", "titre": p.get("title", ""),
                    "auteurs": [{"nom": n.split()[-1] if n else "", "prenom": " ".join(n.split()[:-1])} for n in noms],
                    "annee": p.get("year"), "revue": p.get("venue"), "doi": ext.get("DOI"),
                    "arxiv": ext.get("ArXiv"), "url": p.get("url")})
    return out


SOURCES = {"crossref": crossref, "arxiv": arxiv, "semantic_scholar": semantic_scholar}


def mla(r: dict[str, Any]) -> str:
    """Notice MLA 9e éd. (conventions françaises du projet : « et al. », « vol. », « no », « p. »)."""
    a = r.get("auteurs") or []
    if not a:
        aut = ""
    elif len(a) == 1:
        aut = f"{a[0]['nom']}, {a[0]['prenom']}".strip(", ") + ". "
    elif len(a) == 2:
        aut = f"{a[0]['nom']}, {a[0]['prenom']}, et {a[1]['prenom']} {a[1]['nom']}. ".replace("  ", " ")
    else:
        aut = f"{a[0]['nom']}, {a[0]['prenom']}, et al. "
    titre = (r.get("titre") or "").rstrip(".")
    morceaux = [f"{aut}« {titre}. »"]
    if r.get("revue"):
        morceaux.append(f"*{r['revue']}*,")
    for cle, pre in (("volume", "vol. "), ("numero", "no ")):
        if r.get(cle):
            morceaux.append(f"{pre}{r[cle]},")
    if r.get("annee"):
        morceaux.append(f"{r['annee']},")
    if r.get("pages"):
        morceaux.append(f"p. {str(r['pages']).replace('-', '–')},")
    lien = f"https://doi.org/{r['doi']}" if r.get("doi") else r.get("url") or ""
    texte = " ".join(morceaux).rstrip(",")
    if lien:
        texte += f", {lien}"
    if not r.get("doi") and r.get("consulte"):
        d = datetime.fromisoformat(r["consulte"])
        texte += f". Consulté le {d.day} {MOIS[d.month - 1]} {d.year}"
    return texte + "."


class Veille:
    def __init__(self, dossier_donnees: str | Path, get: Callable[[str], bytes] = _get):
        self.dossier = Path(dossier_donnees) / "veille"
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.fichier = self.dossier / "notices.json"
        self.get = get
        self.notices: dict[str, dict[str, Any]] = (json.loads(self.fichier.read_text(encoding="utf-8"))
                                                  if self.fichier.exists() else {})

    def _sauver(self) -> None:
        self.fichier.write_text(json.dumps(self.notices, ensure_ascii=False, indent=1), encoding="utf-8")

    def _cle(self, r: dict[str, Any]) -> str:
        return ("doi:" + r["doi"].lower()) if r.get("doi") else "titre:" + _norm(r.get("titre", ""))[:120]

    def chercher(self, requete: str, sources: list[str] | None = None, n: int = 10) -> dict[str, Any]:
        nouvelles, erreurs = 0, {}
        maintenant = datetime.now().astimezone().isoformat(timespec="seconds")
        for s in sources or list(SOURCES):
            try:
                for r in SOURCES[s](requete, n, self.get):
                    k = self._cle(r)
                    if not r.get("titre"):
                        continue
                    if k in self.notices:
                        self.notices[k]["sources"] = sorted(set(self.notices[k]["sources"]) | {s})
                        continue
                    self.notices[k] = {**r, "cle": k, "sources": [s], "requete": requete, "consulte": maintenant,
                                       "statut": "à vérifier", "verification": None}
                    nouvelles += 1
            except Exception as exc:  # noqa: BLE001 — une source injoignable n'arrête pas les autres
                erreurs[s] = f"{type(exc).__name__}: {str(exc)[:200]}"
        self._sauver()
        return {"nouvelles": nouvelles, "erreurs": erreurs, "a_verifier": self.compter("à vérifier")}

    def verifier(self, cle: str, *, statut: str, par: str, note: str = "") -> dict[str, Any]:
        if statut not in STATUTS[1:]:
            raise ValueError("Statut : vérifiée ou écartée")
        if not par.strip():
            raise ValueError("Indiquer qui vérifie")
        if statut == "vérifiée" and not note.strip():
            raise ValueError("Décrire la vérification (ex. : notice de l'éditeur consultée, pagination confirmée)")
        n = self.notices[cle]
        n.update(statut=statut, verification={"par": par, "note": note[:500],
                                              "date": datetime.now().astimezone().isoformat(timespec="seconds")})
        self._sauver()
        return n

    def compter(self, statut: str) -> int:
        return sum(1 for n in self.notices.values() if n["statut"] == statut)

    def lister(self, statut: str | None = None) -> list[dict[str, Any]]:
        return sorted((n for n in self.notices.values() if statut is None or n["statut"] == statut),
                      key=lambda n: (-(n.get("annee") or 0), n.get("titre", "")))

    def bibliographie(self) -> str:
        """Ouvrages cités, MLA 9e éd., notices vérifiées seulement, ordre alphabétique."""
        v = sorted(self.lister("vérifiée"), key=lambda n: _norm((n.get("auteurs") or [{"nom": n.get("titre", "")}])[0]["nom"]))
        return "\n\n".join(mla(n) for n in v)
