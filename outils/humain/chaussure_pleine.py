"""Pied chaussé du corps humain (25 oct. 2026) : comble les orteils et la voûte plantaire.

Le pied du maillage MakeHuman a des orteils séparés ; une chaussure de lutte les enveloppe. Chaque sommet du pied est
repoussé, depuis l'axe du pied, jusqu'à l'enveloppe convexe du pied et du bas de la cheville : la forme devient celle
d'une chaussure fermée (pointe arrondie, semelle plane), avec la même densité de sommets que la peau (les motifs des
modèles de chaussures y restent nets). Les normales sont lissées sur les faces de l'enveloppe.

Opération idempotente (les points déjà sur l'enveloppe ne bougent pas). Appelée par construire_humain.py ; peut aussi
corriger un corps.bin déjà construit :  python outils/humain/chaussure_pleine.py web/avatar/humain
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull

PIED, JAMBE = 10, 9


def combler_orteils(P, N, REG, chevilles):
    """P, N : (n, 3) float32 modifiés sur place ; REG : régions ; chevilles : {"g": [x, y, z], "d": [...]}."""
    for cote, signe in (("g", 1), ("d", -1)):
        cy = chevilles[cote][1]
        cote_ok = np.sign(P[:, 0]) == signe
        pied = np.where(cote_ok & (REG == PIED))[0]
        env = np.where(cote_ok & ((REG == PIED) | ((REG == JAMBE) & (P[:, 1] < cy + 0.01))))[0]
        H = ConvexHull(P[env].astype(np.float64))
        n, d = H.equations[:, :3], H.equations[:, 3]
        aires = np.array([np.linalg.norm(np.cross(*(P[env][s[1:]] - P[env][s[0]]))) / 2 for s in H.simplices])
        Q = P[pied].astype(np.float64)
        centre_global = P[env].mean(axis=0)
        for k, v in enumerate(Q):
            bande = P[pied][np.abs(P[pied][:, 2] - v[2]) < 0.01]
            c = np.array([bande[:, 0].mean(), (bande[:, 1].min() + bande[:, 1].max()) / 2, v[2]]) if len(bande) else centre_global
            if np.any(n @ c + d > -1e-4):
                c = centre_global
            u = v - c
            L = np.linalg.norm(u)
            if L < 1e-6:
                continue
            u /= L
            nu = n @ u
            t = np.min(np.where(nu > 1e-9, -(d + n @ c) / np.where(nu > 1e-9, nu, 1), np.inf))
            p = c + t * u
            proches = np.abs(n @ p + d) < 0.004
            m = (n[proches] * aires[proches, None]).sum(axis=0)
            P[pied[k]] = p
            N[pied[k]] = m / (np.linalg.norm(m) or 1)
    return P, N


def corriger(dossier: Path):
    meta = json.loads((dossier / "corps.json").read_text(encoding="utf-8"))
    buf = bytearray((dossier / "corps.bin").read_bytes())
    T = meta["tableaux"]

    def vue(nom, dt):
        d = T[nom]
        return np.frombuffer(buf, dtype=dt, count=int(np.prod(d["forme"])), offset=d["offset"]).reshape(d["forme"])

    P, N, REG = vue("position", np.float32), vue("normale", np.float32), vue("region", np.uint8)
    P2, N2 = P.copy(), N.copy()
    combler_orteils(P2, N2, REG, {c: meta["pivots"][f"cheville_{c}"] for c in "gd"})
    P[...] = P2
    N[...] = N2
    (dossier / "corps.bin").write_bytes(bytes(buf))
    print("pied chaussé :", int((REG == PIED).sum()), "sommets repoussés sur l'enveloppe")


if __name__ == "__main__":
    corriger(Path(sys.argv[1] if len(sys.argv) > 1 else "web/avatar/humain"))
