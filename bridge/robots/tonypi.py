"""Hiwonder TonyPi Pro : conversions entre les unités ROBO-SCÈNE et les unités natives, et groupes d'actions .d6a.

Unités ROBO-SCÈNE (robots/tonypi_pro.toml) : degrés relatifs à la position debout officielle (groupe « stand »),
pourcentage de fermeture pour les mains. Unités natives (SDK Hiwonder, github.com/Hiwonder/TonyPi) :
* servos de bus 1 à 18 : position 0–1000 pour 240° (milieu 500) ;
* servos PWM de la tête (« pwm:1 » tangage, « pwm:2 » lacet) : impulsion 500–2500 µs pour 180°.

Un groupe d'actions .d6a est une base SQLite à une table « ActionGroup » : Index, Time (ms), Servo1 … Servo18
(positions de bus ; la tête n'y figure pas). Ce module lit et écrit ce format pour convertir les gestes de Hiwonder en
séquences ROBO-SCÈNE (bibliothèque fermée, statut « brouillon ») et inversement (logiciel PC de Hiwonder).

Les fichiers .d6a de Hiwonder ne sont pas versionnés dans ce dépôt public (aucune licence déclarée par Hiwonder) :
l'outil outils/hiwonder_tonypi.py les convertit depuis la copie du robot de l'utilisateur.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

BUS_PAS_PAR_DEG = 1000 / 240          # 4,1667 pas par degré
PWM_US_PAR_DEG = 2000 / 180           # 11,111 µs par degré
BUS_MIN, BUS_MAX = 0, 1000
PWM_MIN, PWM_MAX = 500, 2500
N_BUS_D6A = 18


def genre(art: Any) -> str:
    """« bus » (id entier 1–18) ou « pwm » (id « pwm:1 » ou « pwm:2 »)."""
    i = art.id if not isinstance(art, dict) else art.get("id")
    return "pwm" if isinstance(i, str) and i.startswith("pwm:") else "bus"


def numero(art: Any) -> int:
    i = art.id if not isinstance(art, dict) else art.get("id")
    return int(str(i).split(":")[-1])


def _champ(art: Any, nom: str, defaut: Any = None) -> Any:
    v = art.get(nom, defaut) if isinstance(art, dict) else getattr(art, nom, defaut)
    return defaut if v is None else v


def echelle(art: Any) -> float:
    """Pas natifs par unité ROBO-SCÈNE (degré ou %)."""
    return float(_champ(art, "pas_par_unite", PWM_US_PAR_DEG if genre(art) == "pwm" else BUS_PAS_PAR_DEG))


def vers_natif(art: Any, valeur: float) -> int:
    """Valeur ROBO-SCÈNE (degrés relatifs au debout, ou %) → position native, bornée à la course du servo."""
    zero = float(_champ(art, "zero", 1500 if genre(art) == "pwm" else 500))
    p = int(round(zero + int(_champ(art, "sens", 1)) * float(valeur) * echelle(art)))
    lo, hi = (PWM_MIN, PWM_MAX) if genre(art) == "pwm" else (BUS_MIN, BUS_MAX)
    return max(lo, min(hi, p))


def depuis_natif(art: Any, pas: float) -> float:
    zero = float(_champ(art, "zero", 1500 if genre(art) == "pwm" else 500))
    return round(int(_champ(art, "sens", 1)) * (float(pas) - zero) / echelle(art), 2) + 0.0   # jamais « -0.0 »


# ── Groupes d'actions .d6a ──────────────────────────────────
def lire_d6a(chemin: str | Path) -> list[dict[str, Any]]:
    """Images d'un groupe d'actions : [{"ms": durée, "pas": {1: position, …, 18: position}}]. Lecture seule."""
    c = sqlite3.connect(f"file:{Path(chemin).resolve()}?mode=ro", uri=True)
    try:
        cols = [r[1] for r in c.execute("pragma table_info(ActionGroup)")]
        lignes = c.execute('select * from ActionGroup order by "Index"').fetchall()
    finally:
        c.close()
    if not cols or cols[:2] != ["Index", "Time"]:
        raise ValueError(f"{chemin} : table ActionGroup inattendue ({cols[:3]})")
    images = []
    for r in lignes:
        pas = {int(n[5:]): int(v) for n, v in zip(cols[2:], r[2:]) if n.startswith("Servo") and v is not None}
        images.append({"ms": int(r[1]), "pas": pas})
    return images


def ecrire_d6a(chemin: str | Path, images: Iterable[dict[str, Any]]) -> None:
    """Écrit un groupe d'actions lisible par le logiciel PC et le SDK de Hiwonder (18 servos de bus)."""
    p = Path(chemin)
    if p.exists():
        p.unlink()
    c = sqlite3.connect(p)
    try:
        cols = ", ".join(f"Servo{i} INTEGER" for i in range(1, N_BUS_D6A + 1))
        c.execute(f'CREATE TABLE ActionGroup("Index" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE, Time INT, {cols})')
        for k, im in enumerate(images, start=1):
            pas = [int(im["pas"].get(i, 500)) for i in range(1, N_BUS_D6A + 1)]
            c.execute(f"INSERT INTO ActionGroup VALUES ({', '.join('?' * (N_BUS_D6A + 2))})", [k, int(im["ms"]), *pas])
        c.commit()
    finally:
        c.close()


def d6a_vers_sequence(images: list[dict[str, Any]], articulations: list[Any], nom: str, source: str = "") -> dict[str, Any]:
    """Groupe d'actions → séquence ROBO-SCÈNE (degrés du profil ; la tête, absente des .d6a, reste à 0)."""
    seq = []
    for im in images:
        deg = []
        for a in articulations:
            if genre(a) == "bus" and numero(a) in im["pas"]:
                deg.append(depuis_natif(a, im["pas"][numero(a)]))
            else:
                deg.append(float(_champ(a, "repos", 0.0)))
        seq.append({"deg": deg, "ms": max(20, int(im["ms"]))})
    return {"nom": nom, "statut": "brouillon", "images": seq,
            "origine": {"type": "groupe_actions_hiwonder", "source": source,
                        "note": "Converti d'un groupe d'actions .d6a ; à valider en simulation puis sur le robot."}}


def sequence_vers_d6a(sequence: dict[str, Any], articulations: list[Any]) -> list[dict[str, Any]]:
    """Séquence ROBO-SCÈNE → images .d6a (servos de bus seulement ; les servos absents restent à 500)."""
    out = []
    for im in sequence["images"]:
        pas = {}
        for a, v in zip(articulations, im["deg"]):
            if genre(a) == "bus" and v is not None:
                pas[numero(a)] = vers_natif(a, v)
        out.append({"ms": int(im.get("ms", 800)), "pas": pas})
        if im.get("pause_ms"):
            out.append({"ms": int(im["pause_ms"]), "pas": dict(pas)})
    return out


def enveloppe(dossier: str | Path) -> dict[int, tuple[int, int]]:
    """Positions extrêmes de chaque servo de bus sur l'ensemble des groupes d'actions d'un dossier."""
    env: dict[int, list[int]] = {}
    for f in sorted(Path(dossier).glob("*.d6a")):
        try:
            images = lire_d6a(f)
        except (sqlite3.DatabaseError, ValueError):
            continue
        for im in images:
            for i, v in im["pas"].items():
                e = env.setdefault(i, [v, v])
                e[0], e[1] = min(e[0], v), max(e[1], v)
    return {i: (lo, hi) for i, (lo, hi) in sorted(env.items())}
