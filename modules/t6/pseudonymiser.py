"""Pseudonymisation des transcriptions d'entretiens (repère T.6 ; plan de gestion des données G.6, DO-02 et DO-09).

    python pseudonymiser.py TRANSCRIPTION_BRUTE.txt \\
        --table "/Volumes/<volume chiffré>/DO-09_table_pseudonymes.csv" \\
        --sortie "…/04_Terrain_et_etudes_de_cas/Entretiens_pseudonymises/E-A07-01.txt" \\
        --rapport "/Volumes/<volume chiffré>/controles/E-A07-01_controle.txt"

La table (CSV UTF-8, séparateur « ; ») ne quitte jamais le volume chiffré :
    pseudonyme;type;formes
    A07;personne;Éloïse Tremblay|Éloïse|Mme Tremblay
    VILLE-1;lieu;Rimouski
    ORG-2;organisme;Théâtre de l'Exemple

L'outil masque d'office courriels, téléphones et codes postaux, remplace chaque forme de la table par [pseudonyme] (comparaison sans accents ni casse, sur des mots entiers, des formes
les plus longues aux plus courtes), puis écrit un rapport de contrôle qui signale ce qu'il n'a pas pu traiter :
courriels, téléphones, codes postaux, nombres pouvant identifier, et mots à majuscule absents de la table.
Le rapport cite des passages bruts : il se range dans le volume chiffré, jamais dans le dossier du projet.
Aucune donnée n'est transmise à un service externe : le traitement est entièrement local.
"""
from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

RE_COURRIEL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
RE_TELEPHONE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
RE_CODE_POSTAL = re.compile(r"\b[A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d\b")
RE_NOMBRE = re.compile(r"\b\d{2,}\b")
RE_MAJUSCULE = re.compile(r"(?<![.!?:]\s)(?<!^)\b([A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ'’-]{2,})\b", re.M)
RE_LOCUTEUR = re.compile(r"^\s*([A-Z]{1,4}\d{0,3}|CH)\s*:", re.M)

# Mots à majuscule fréquents qui ne désignent pas des personnes (complété au besoin, une ligne par mot).
COURANTS = {"Je", "Tu", "Il", "Elle", "On", "Nous", "Vous", "Ils", "Elles", "Et", "Mais", "Donc", "Alors", "Oui",
            "Non", "Bon", "Ben", "Puis", "Parce", "Quand", "Comme", "Ça", "Ce", "Cette", "Les", "Le", "La", "Un",
            "Une", "Des", "Dans", "Pour", "Avec", "Sur", "Après", "Avant", "Ah", "Oh", "Euh", "Mm", "Hum", "Ok",
            "Claude", "IA", "Canada", "Québec", "Ontario", "Montréal", "Ottawa", "Toronto", "Vancouver"}


def plier(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").casefold()


@dataclass
class Entree:
    pseudonyme: str
    type: str
    formes: list[str]


@dataclass
class Resultat:
    texte: str
    remplacements: dict[str, int] = field(default_factory=dict)
    alertes: list[tuple[int, str, str]] = field(default_factory=list)   # (ligne, type, extrait)


def charger_table(chemin: str | Path) -> list[Entree]:
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    table = []
    for l in lignes:
        formes = [x.strip() for x in (l.get("formes") or "").split("|") if x.strip()]
        if l.get("pseudonyme") and formes:
            table.append(Entree(l["pseudonyme"].strip(), (l.get("type") or "autre").strip(), formes))
    return table


def _motif(forme: str) -> re.Pattern:
    """Motif qui reconnaît la forme quels que soient accents et casse, sur des mots entiers."""
    morceaux = []
    for c in forme:
        base = plier(c)
        if c.isspace():
            morceaux.append(r"\s+")
        elif base.isalpha():
            variantes = {c, c.lower(), c.upper()} | {x for x in _ACCENTS.get(base, "")} | {x.upper() for x in _ACCENTS.get(base, "")}
            morceaux.append("[" + "".join(sorted(re.escape(v) for v in variantes)) + "]")
        elif c in "'’":
            morceaux.append("['’]")
        else:
            morceaux.append(re.escape(c))
    return re.compile(r"(?<![\w])" + "".join(morceaux) + r"(?![\w])")


_ACCENTS = {"a": "aàâä", "e": "eéèêë", "i": "iîï", "o": "oôö", "u": "uùûü", "c": "cç", "y": "yÿ"}


def pseudonymiser(texte: str, table: list[Entree], courants: set[str] | None = None) -> Resultat:
    courants = COURANTS | (courants or set())
    formes = sorted(((f, e.pseudonyme) for e in table for f in e.formes), key=lambda x: -len(x[0]))
    res = Resultat(texte)
    # 1) Coordonnées : toujours masquées d'office, avant tout autre remplacement (elles identifient à coup sûr).
    for rx, typ in ((RE_COURRIEL, "courriel"), (RE_TELEPHONE, "téléphone"), (RE_CODE_POSTAL, "code postal")):
        def masquer(m, typ=typ):
            no = res.texte.count("\n", 0, m.start()) + 1
            res.alertes.append((no, f"{typ} masqué d'office", m.group(0)))
            return f"[{typ} masqué]"
        res.texte = rx.sub(masquer, res.texte)
    # 2) Personnes, lieux, organismes de la table : formes les plus longues d'abord.
    for forme, ps in formes:
        res.texte, n = _motif(forme).subn(f"[{ps}]", res.texte)
        if n:
            res.remplacements[ps] = res.remplacements.get(ps, 0) + n
    connus = {plier(f) for f, _ in formes}
    for no, ligne in enumerate(res.texte.splitlines(), 1):
        sans_loc = re.sub(r"\[[^\]]*\]", " ", RE_LOCUTEUR.sub("", ligne))
        for m in RE_NOMBRE.finditer(sans_loc):
            res.alertes.append((no, "nombre (âge, adresse, date ?)", m.group(0)))
        for m in RE_MAJUSCULE.finditer(sans_loc):
            mot = m.group(1)
            if mot not in courants and plier(mot) not in connus:
                res.alertes.append((no, "nom propre possible", mot))
    return res


def rapport(res: Resultat, source: str) -> str:
    l = [f"Rapport de contrôle — {source}", "À conserver dans le volume chiffré (cite des passages bruts).", "",
         "Remplacements effectués :"]
    l += [f"  [{ps}] × {n}" for ps, n in sorted(res.remplacements.items())] or ["  aucun"]
    l += ["", f"Alertes à vérifier à la main ({len(res.alertes)}) :"]
    l += [f"  ligne {no:>4} · {typ} · {extrait}" for no, typ, extrait in res.alertes] or ["  aucune"]
    l += ["", "La transcription n'est versée au dossier du projet qu'après examen de chaque alerte (protocole T.6, § 5)."]
    return "\n".join(l) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pseudonymisation locale d'une transcription (T.6)")
    ap.add_argument("transcription")
    ap.add_argument("--table", required=True, help="table des pseudonymes (volume chiffré)")
    ap.add_argument("--sortie", required=True, help="transcription pseudonymisée")
    ap.add_argument("--rapport", required=True, help="rapport de contrôle (volume chiffré)")
    a = ap.parse_args(argv)
    res = pseudonymiser(Path(a.transcription).read_text(encoding="utf-8"), charger_table(a.table))
    Path(a.sortie).write_text(res.texte, encoding="utf-8")
    Path(a.rapport).write_text(rapport(res, Path(a.transcription).name), encoding="utf-8")
    print(f"{sum(res.remplacements.values())} remplacements ; {len(res.alertes)} alertes à vérifier ; rapport : {a.rapport}")


if __name__ == "__main__":
    main()
