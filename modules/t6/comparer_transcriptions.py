"""Taux d'erreur sur les mots (WER) entre une transcription de référence et celle de SI-03 (fiche SI-03, G.5 v1.1).

Sert à choisir le modèle Whisper (large-v3 ou large-v3-turbo) sur des enregistrements FICTIFS lus par le
chercheur, jamais sur des données de personnes participantes :

    python3 comparer_transcriptions.py reference.txt large-v3.txt large-v3-turbo.txt

WER = (substitutions + suppressions + insertions) / nombre de mots de la référence, calculé par la distance
d'édition sur les mots, après normalisation (minuscules, ponctuation retirée, apostrophes et espaces unifiés).
Les hésitations notées (euh, hum) sont conservées : la convention de transcription T.6 les garde.
"""
from __future__ import annotations

import re
import sys
import unicodedata


def normaliser(texte: str) -> list[str]:
    t = unicodedata.normalize("NFC", texte or "").lower().replace("’", "'")
    t = re.sub(r"\[[^\]]*\]", " ", t)                      # annotations entre crochets ([rire], [inaudible])
    t = re.sub(r"[^\w'\s-]", " ", t)
    t = re.sub(r"(?<!\w)['-]|['-](?!\w)", " ", t)
    return t.split()


def distance(a: list[str], b: list[str]) -> int:
    prec = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cour = [i]
        for j, y in enumerate(b, 1):
            cour.append(min(prec[j] + 1, cour[j - 1] + 1, prec[j - 1] + (x != y)))
        prec = cour
    return prec[-1]


def wer(reference: str, hypothese: str) -> float:
    r, h = normaliser(reference), normaliser(hypothese)
    if not r:
        raise ValueError("référence vide")
    return round(distance(r, h) / len(r), 4)


def main(argv=None):
    a = argv if argv is not None else sys.argv[1:]
    if len(a) < 2:
        raise SystemExit(__doc__)
    ref = open(a[0], encoding="utf-8").read()
    for f in a[1:]:
        print(f"{f}\tWER = {wer(ref, open(f, encoding='utf-8').read()):.2%}")


if __name__ == "__main__":
    main()
