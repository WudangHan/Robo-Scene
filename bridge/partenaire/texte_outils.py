"""Outils lexicaux communs (français) : normalisation, jetons, racinisation légère."""
from __future__ import annotations

import re
import unicodedata

MOTS_VIDES = set("""
a à ai aie aient aies ait alors as au aucun aucune aupres auquel aura aurai auraient aurais aurait
auras aurez auriez aurions aurons auront aussi autre autres aux auxquelles auxquels avaient avais
avait avant avec avez aviez avions avoir avons ayant ayez ayons c ça car ce ceci cela celle celles
celui cependant ces cet cette ceux chaque chez ci comme comment d dans de des desquelles desquels
deux devrait doit donc dont du duquel elle elles en encore entre es est et etaient etais etait
etant ete etes etiez etions etre eu eue eues eurent eus eusse eussent eusses eussiez eussions eut
eux fait fois font furent fus fusse fussent fut ici il ils j je jusqu l la le les leur leurs lui
m ma mais me meme memes mes moi mon n ne ni nos notre nous on ont or ou par parce pas peu peut
plus pour pourquoi qu quand que quel quelle quelles quels qui quoi s sa sans se sera serai seraient
serais serait seras serez seriez serions serons seront ses si sien son sont sous soyez soyons
suis sur t ta te tes toi ton tous tout toute toutes tres tu un une unes uns vers voici voila vos
votre vous y
""".split())

_SUFFIXES = ("issements", "issement", "atrices", "atrice", "ations", "ation", "ements", "ement",
             "euses", "euse", "eurs", "eur", "istes", "iste", "ites", "ite", "ives", "ive", "ifs",
             "iques", "ique", "ables", "able", "ances", "ance", "ences", "ence", "es", "s", "x", "e")


def sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normaliser(s: str) -> str:
    s = sans_accents(s.lower()).replace("œ", "oe").replace("æ", "ae")
    return re.sub(r"[’'`]", " ", s)


def mots(s: str) -> list[str]:
    """Mots normalisés (sans accents, minuscules), apostrophes séparées."""
    return re.findall(r"[a-z0-9]+", normaliser(s))


def raciner(m: str) -> str:
    if len(m) <= 4:
        return m
    for suf in _SUFFIXES:
        if m.endswith(suf) and len(m) - len(suf) >= 4:
            return m[: -len(suf)]
    return m


def jetons(s: str) -> list[str]:
    return [raciner(m) for m in mots(s) if m not in MOTS_VIDES and len(m) > 1]


def syllabes(texte: str) -> int:
    """Estimation du nombre de syllabes orales (groupes vocaliques).

    Approximation : le « e » final muet et les élisions ne sont pas
    traités finement ; suffisante pour un débit relatif, non pour la
    métrique du vers.
    """
    n = 0
    for m in re.findall(r"[a-zàâäéèêëîïôöùûüÿœæ]+", texte.lower()):
        groupes = re.findall(r"[aàâäeéèêëiîïoôöuùûüyÿœæ]+", m)
        k = len(groupes)
        if k > 1 and re.search(r"(?<![aeiouy])e(s|nt)?$", m):
            k -= 1
        n += max(1, k)
    return n
