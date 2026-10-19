"""Zones de vol du drone : la même règle que web/drone/geofence.js, lue dans le même fichier web/drone/salle.json.

Le pont n'envoie au drone réel aucune consigne de position ni de vitesse qui sortirait des volumes ouverts par le mode
de vol, toucherait un obstacle, survolerait le public en représentation ou entrerait dans le cylindre d'un interprète ;
les tests vérifient que ce module et le module du navigateur rendent le même verdict sur des milliers de points.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Sequence

RACINE = Path(__file__).resolve().parent.parent.parent
FICHIER_SALLE = RACINE / "web" / "drone" / "salle.json"


def charger_salle(chemin: Path | str | None = None) -> dict[str, Any]:
    with open(chemin or FICHIER_SALLE, encoding="utf-8") as f:
        return json.load(f)


def _dedans(b: dict, p: Sequence[float], m: float = 0.0) -> bool:
    return (b["x"][0] - m <= p[0] <= b["x"][1] + m and b["y"][0] - m <= p[1] <= b["y"][1] + m
            and b["z"][0] - m <= p[2] <= b["z"][1] + m)


def _dedans_xz(b: dict, p: Sequence[float], m: float = 0.0) -> bool:
    return b["x"][0] - m <= p[0] <= b["x"][1] + m and b["z"][0] - m <= p[2] <= b["z"][1] + m


def _decalages(m: float):
    for dx in (-m, 0, m):
        for dy in (0, m):
            for dz in (-m, 0, m):
                yield dx, dy, dz


def volume_de(salle: dict, p: Sequence[float], mode: str = "plateau") -> str | None:
    for i in (salle["modes"].get(mode) or salle["modes"]["plateau"])["volumes"]:
        if _dedans(salle["volumes"][i], p):
            return i
    return None


def verifier(salle: dict, p: Sequence[float], mode: str = "plateau",
             interpretes: Sequence[Sequence[float]] = ()) -> dict[str, Any]:
    R = salle["regles"]
    mode = mode if mode in salle["modes"] else "plateau"
    M = salle["modes"][mode]
    m = R["marge_m"]
    try:
        p = [float(v) for v in p]
        if len(p) != 3 or not all(math.isfinite(v) for v in p):
            raise ValueError
    except (TypeError, ValueError):
        return {"ok": False, "motif": "Position invalide", "zone": None}
    zone = volume_de(salle, p, mode)
    if not zone:
        return {"ok": False, "motif": f"Hors des volumes ouverts en mode « {M['libelle']} »", "zone": None}
    vols = [salle["volumes"][i] for i in M["volumes"]]
    for dx, dy, dz in _decalages(m):
        q = (p[0] + dx, p[1] + dy, p[2] + dz)
        if not any(_dedans(v, q) for v in vols):
            return {"ok": False, "motif": f"Trop près de la limite du volume (marge {m} m)", "zone": zone}
    for o in salle["obstacles"]:
        if _dedans(o, p, m):
            return {"ok": False, "motif": f"Trop près : {o['libelle']} (marge {m} m)", "zone": zone, "obstacle": o["id"]}
    aire = salle["aire"]
    d_aire = math.hypot(p[0] - aire["centre"][0], p[2] - aire["centre"][2])
    if p[1] - salle["volumes"][zone]["y"][0] < R["hauteur_min_m"] and d_aire > aire["rayon"]:
        return {"ok": False, "motif": f"Trop bas (moins de {R['hauteur_min_m']} m du sol hors de l'aire de décollage)",
                "zone": zone}
    if "salle" in M["volumes"]:
        for b in salle["public"]:
            if M["public"] == "colonnes" and _dedans_xz(b, p, R["marge_public_m"]):
                return {"ok": False, "motif": f"Survol du public interdit : {b['libelle']} (marge {R['marge_public_m']} m)",
                        "zone": zone, "public": b["id"]}
            if M["public"] == "fauteuils":
                f = {"x": b["x"], "y": [b["y"][0], b["y"][0] + R["hauteur_fauteuils_m"]], "z": b["z"]}
                if _dedans(f, p, m):
                    return {"ok": False, "motif": f"Trop près des fauteuils : {b['libelle']}", "zone": zone, "public": b["id"]}
    for i, it in enumerate(interpretes or ()):
        x, z = (it["x"], it["z"]) if isinstance(it, dict) else (it[0], it[1])
        if math.hypot(p[0] - x, p[2] - z) < R["rayon_interpretes_m"] and p[1] < R["hauteur_interpretes_m"]:
            return {"ok": False, "motif": f"Trop près de l'interprète {i + 1} ({R['rayon_interpretes_m']} m sous "
                                          f"{R['hauteur_interpretes_m']} m)", "zone": zone}
    return {"ok": True, "motif": "", "zone": zone}


def verifier_segment(salle: dict, a: Sequence[float], b: Sequence[float], mode: str = "plateau",
                     interpretes: Sequence = (), pas: float = 0.05) -> dict[str, Any]:
    d = math.dist(a, b)
    n = max(1, math.ceil(d / pas))
    for i in range(n + 1):
        u = i / n
        p = [a[k] + (b[k] - a[k]) * u for k in range(3)]
        v = verifier(salle, p, mode, interpretes)
        if not v["ok"]:
            return {**v, "point": p, "fraction": u}
    return {"ok": True, "motif": ""}


def point(salle: dict, cible: Any) -> list[float]:
    if isinstance(cible, (list, tuple)) and len(cible) == 3 and all(isinstance(v, (int, float)) for v in cible):
        return [float(v) for v in cible]
    if isinstance(cible, str) and cible in salle["reperes"]:
        return [float(v) for v in salle["reperes"][cible]]
    raise ValueError(f"Repère inconnu : {cible!r}")
