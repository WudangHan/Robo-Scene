"""Sol praticable du chien de scène : la même règle que web/chien/sol.js, lue dans le même fichier
web/drone/salle.json (bloc « sol »). Les tests vérifient que les deux implantations rendent le même verdict."""
from __future__ import annotations

import math
from typing import Any, Sequence

from ..drone.zones import charger_salle  # noqa: F401  (même fichier de description de la salle)


def _dans(b: dict, x: float, z: float) -> bool:
    return b["x"][0] <= x <= b["x"][1] and b["z"][0] <= z <= b["z"][1]


def _dist_rect(b: dict, x: float, z: float) -> float:
    return math.hypot(max(b["x"][0] - x, 0, x - b["x"][1]), max(b["z"][0] - z, 0, z - b["z"][1]))


def surface_de(salle: dict, x: float, z: float, mode: str = "plateau") -> dict | None:
    S = salle["sol"]
    for i in (S["modes"].get(mode) or S["modes"]["plateau"])["surfaces"]:
        s = next((u for u in S["surfaces"] if u["id"] == i), None)
        if s and _dans(s, x, z):
            return s
    return None


def hauteur_sol(salle: dict, x: float, z: float, mode: str = "salle_vide") -> float | None:
    s = surface_de(salle, x, z, mode)
    if not s:
        return None
    u = (z - s["z"][0]) / (s["z"][1] - s["z"][0])
    return s["y0"] + (s["y1"] - s["y0"]) * u


def vitesse_max(salle: dict, x: float, z: float, mode: str = "plateau") -> float:
    R = salle["sol"]["regles"]
    s = surface_de(salle, x, z, mode)
    v = min(R["vitesse_max_m_s"], s["vitesse_max_m_s"] if s else R["vitesse_max_m_s"])
    if mode == "representation" and s and s["id"] != "plateau":
        v = min(v, R["vitesse_max_representation_m_s"])
    return v


def verifier(salle: dict, p: Sequence[float], mode: str = "plateau", interpretes: Sequence = ()) -> dict[str, Any]:
    S = salle["sol"]
    R = S["regles"]
    mode = mode if mode in S["modes"] else "plateau"
    try:
        x, z = float(p[0]), float(p[1])
        if not (math.isfinite(x) and math.isfinite(z)):
            raise ValueError
    except (TypeError, ValueError, IndexError):
        return {"ok": False, "motif": "Position invalide", "surface": None}
    r = R["rayon_m"]
    s = surface_de(salle, x, z, mode)
    if not s:
        return {"ok": False, "motif": "Hors du sol praticable dans ce mode", "surface": None}
    for dx in (-r, 0, r):
        for dz in (-r, 0, r):
            if not surface_de(salle, x + dx, z + dz, mode):
                return {"ok": False, "motif": f"Trop près d'un bord (nez de scène, fosse, rangées) — rayon {r} m",
                        "surface": s["id"]}
    obstacles = [o for i in S["obstacles"] for o in salle["obstacles"] if o["id"] == i] + list(S.get("decor") or [])
    for o in obstacles:
        for dx in (-r, 0, r):
            for dz in (-r, 0, r):
                if _dans(o, x + dx, z + dz):
                    return {"ok": False, "motif": f"Trop près : {o['libelle']}", "surface": s["id"], "obstacle": o["id"]}
    if S["modes"][mode]["public"] == "marge":
        for b in salle["public"]:
            if _dist_rect(b, x, z) < r + R["marge_public_m"]:
                return {"ok": False, "motif": f"Trop près du public : {b['libelle']} (marge {R['marge_public_m']} m)",
                        "surface": s["id"], "public": b["id"]}
    for i, it in enumerate(interpretes or ()):
        ix, iz = (it["x"], it["z"]) if isinstance(it, dict) else (it[0], it[1])
        if math.hypot(x - ix, z - iz) < R["rayon_interpretes_m"]:
            return {"ok": False, "motif": f"Trop près de l'interprète {i + 1} ({R['rayon_interpretes_m']} m)",
                    "surface": s["id"]}
    return {"ok": True, "motif": "", "surface": s["id"]}


def verifier_trajet(salle: dict, a, b, mode: str = "plateau", interpretes: Sequence = (), pas: float = 0.05):
    d = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(1, math.ceil(d / pas))
    for i in range(n + 1):
        u = i / n
        p = [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u]
        v = verifier(salle, p, mode, interpretes)
        if not v["ok"]:
            return {**v, "point": p, "fraction": u}
    return {"ok": True, "motif": ""}


def point(salle: dict, cible: Any) -> list[float]:
    if isinstance(cible, (list, tuple)) and len(cible) == 2 and all(isinstance(v, (int, float)) for v in cible):
        return [float(v) for v in cible]
    if isinstance(cible, str) and cible in salle["sol"]["reperes"]:
        return [float(v) for v in salle["sol"]["reperes"][cible]]
    raise ValueError(f"Repère inconnu : {cible!r}")
