"""Construction du corps humain du robot virtuel (style « humain », 25 oct. 2026).

Source : maillage de base et cibles de morphologie de MakeHuman (hm08), squelette « default » et ses poids,
yeux « high-poly » — ressources publiées sous licence CC0 par la communauté MakeHuman (fichier
LICENSE.ASSETS.md du dépôt makehumancommunity/makehuman). Le script :
  1. lit le maillage de base et applique les cibles « macro » d'un homme jeune, athlétique et musclé
     (genre 1, âge 25 ans, musculature 1, poids 0,45, mélange ethnique par défaut), puis les cibles locales de
     définition musculaire (pectoraux, dorsaux, torse en V, deltoïdes, bras, avant-bras, cuisses, mollets) ;
  2. met le corps à l'échelle du robot (1,785 m) et le recale sur son squelette (pieds au sol, hanches en z = 0) ;
  3. le replace dans la pose de repos du robot : bras le long du corps (et non en A), avant-bras, mains,
     jambes et pieds orientés comme ceux du robot (habillage par mélange linéaire avec les poids MakeHuman) ;
  4. réduit les 163 os de MakeHuman aux nœuds pilotés par le robot (bassin, tronc, cou, tête, mâchoire,
     paupières, clavicules, bras, avant-bras, mains, 15 phalanges par main, cuisses, jambes, pieds) ;
  5. écrit web/avatar/humain/corps.bin et corps.json (positions, UV, indices, 4 influences par sommet,
     région anatomique, pivots de liaison, yeux ajustés par la méthode des « mhclo » de MakeHuman).

Usage : python outils/humain/construire_humain.py <dossier data de MakeHuman> [--sortie web/avatar/humain]
"""
from __future__ import annotations

import argparse
import json
import sys
import struct
from pathlib import Path

import numpy as np

RACINE = Path(__file__).resolve().parents[2]
SQUELETTE = json.loads((Path(__file__).with_name("squelette_robot.json")).read_text(encoding="utf-8"))

# ── Morphologie (Inférence : réglage choisi pour une carrure de lutteur universitaire) ──
GENRE, AGE, MUSCLE, POIDS = 1.0, 0.5, 1.0, 0.45     # musculature maximale, peu de masse grasse (26 oct. 2026)
# définition musculaire locale (cibles CC0 de MakeHuman, 0 à 1) : pectoraux, dorsaux, torse en V, deltoïdes,
# biceps et triceps, avant-bras, cuisses, mollets — demandée pour une silhouette de lutteur plus dessinée
DEFINITION = {
    "torso/torso-muscle-pectoral-incr": 1.0, "torso/torso-muscle-dorsi-incr": 0.8, "torso/torso-vshape-incr": 0.6,
    **{f"armslegs/{c}-{m}-incr": v for c in "lr" for m, v in (("upperarm-muscle", 1.0), ("upperarm-shoulder-muscle", 0.9),
       ("lowerarm-muscle", 0.8), ("upperleg-muscle", 1.0), ("lowerleg-muscle", 1.0))},
}
HAUTEUR = 1.785                                   # m, sommet du crâne du robot stylisé
DOIGTS = ["pouce", "index", "majeur", "annulaire", "auriculaire"]


def lire_obj(chemin: Path):
    v, vt, faces, groupe = [], [], [], None
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        if ligne.startswith("v "):
            v.append([float(x) for x in ligne.split()[1:4]])
        elif ligne.startswith("vt "):
            vt.append([float(x) for x in ligne.split()[1:3]])
        elif ligne.startswith("g "):
            groupe = ligne.split()[1]
        elif ligne.startswith("f "):
            idx = [tuple(int(t) - 1 if t else -1 for t in (p.split("/") + ["", ""])[:2]) for p in ligne.split()[1:]]
            faces.append((groupe, idx))
    return np.array(v), np.array(vt), faces


def lire_cible(chemin: Path, n: int) -> np.ndarray:
    d = np.zeros((n, 3))
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        if ligne and not ligne.startswith("#"):
            i, x, y, z = ligne.split()
            d[int(i)] = (float(x), float(y), float(z))
    return d


def appliquer_cibles(data: Path, v: np.ndarray) -> np.ndarray:
    """Cibles macro de MakeHuman (même pondération que apps/human.py : _setMuscleVals, _setWeightVals)."""
    m = {"max": max(0.0, MUSCLE * 2 - 1), "min": max(0.0, 1 - MUSCLE * 2)}
    m["average"] = 1 - m["max"] - m["min"]
    w = {"max": max(0.0, POIDS * 2 - 1), "min": max(0.0, 1 - POIDS * 2)}
    w["average"] = 1 - w["max"] - w["min"]
    macro = data / "targets" / "macrodetails"
    out = v.copy()
    for mk, mv in m.items():
        for wk, wv in w.items():
            if mv * wv > 0:
                out += mv * wv * lire_cible(macro / f"universal-male-young-{mk}muscle-{wk}weight.target", len(v))
    for race in ("african", "asian", "caucasian"):                      # mélange ethnique par défaut : 1/3 chacun
        out += (1 / 3) * lire_cible(macro / f"{race}-male-young.target", len(v))
    for nom, poids in DEFINITION.items():                               # définition musculaire locale
        out += poids * lire_cible(data / "targets" / f"{nom}.target", len(v))
    return out


def lire_squelette(data: Path, v: np.ndarray):
    sk = json.loads((data / "rigs" / "default.mhskel").read_text(encoding="utf-8"))
    joints = {k: v[idx].mean(axis=0) for k, idx in sk["joints"].items()}
    os_ = {}
    for nom, b in sk["bones"].items():
        os_[nom] = {"parent": b["parent"], "tete": joints[b["head"]], "queue": joints[b["tail"]]}
    poids = json.loads((data / "rigs" / sk["weights_file"]).read_text(encoding="utf-8"))["weights"]
    return os_, poids


def ordre_topologique(os_):
    ordre, vus = [], set()
    def visite(n):
        if n in vus:
            return
        p = os_[n]["parent"]
        if p:
            visite(p)
        vus.add(n); ordre.append(n)
    for n in os_:
        visite(n)
    return ordre


def arc(a, b):
    """Rotation la plus courte qui amène la direction a sur la direction b (matrice 3×3)."""
    a = a / np.linalg.norm(a); b = b / np.linalg.norm(b)
    c = np.cross(a, b); s = np.linalg.norm(c); d = float(np.dot(a, b))
    if s < 1e-9:
        return np.eye(3) if d > 0 else -np.eye(3)
    k = c / s
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    ang = np.arctan2(s, d)
    return np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * K @ K


def rot_axe(axe, ang):
    k = axe / np.linalg.norm(axe)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * K @ K


def T(R, pivot):
    """Transformation affine 4×4 : rotation R autour du point pivot."""
    M = np.eye(4); M[:3, :3] = R; M[:3, 3] = pivot - R @ pivot
    return M


def appl(M, p):
    return M[:3, :3] @ p + M[:3, 3]


def reposer(os_, poids, v, cote_cibles):
    """Pose de repos du robot : rotations des os des membres (habillage linéaire, poids de MakeHuman)."""
    ordre = ordre_topologique(os_)
    M = {}
    for n in ordre:
        p = os_[n]["parent"]
        Mp = M[p] if p else np.eye(4)
        M[n] = Mp
        if n not in cote_cibles:
            continue
        ref_tete, ref_queue, cible, torsion = cote_cibles[n]
        h = appl(Mp, os_[ref_tete]["tete"]); t = appl(Mp, os_[ref_queue]["tete"])
        R = arc(t - h, cible)
        if torsion is not None:                                   # torsion autour du segment (pouce vers l'avant)
            ref_os, voulu = torsion
            r = R @ (appl(Mp, os_[ref_os]["tete"]) - h)
            axe = cible / np.linalg.norm(cible)
            r_p = r - axe * np.dot(r, axe); v_p = voulu - axe * np.dot(voulu, axe)
            ang = np.arctan2(np.dot(np.cross(r_p, v_p), axe), np.dot(r_p, v_p))
            R = rot_axe(axe, ang) @ R
        M[n] = T(R, h) @ Mp
    # habillage : v' = Σ w_b M_b v
    out = np.zeros_like(v); tot = np.zeros(len(v))
    for nom, liste in poids.items():
        if nom not in M:
            continue
        idx = np.array([i for i, _ in liste]); w = np.array([x for _, x in liste])
        vv = v[idx] @ M[nom][:3, :3].T + M[nom][:3, 3]
        np.add.at(out, idx, vv * w[:, None]); np.add.at(tot, idx, w)
    seul = tot < 1e-6
    out[seul] = v[seul]; out[~seul] /= tot[~seul, None]
    joints = {n: {"tete": appl(M[n], os_[n]["tete"]), "queue": appl(M[n], os_[n]["queue"])} for n in os_}
    return out, joints, M


GALBE: dict = {}


def galbe_masculin(v, corps, joints):
    """Silhouette masculine du bassin sous le vêtement (demande du 25 oct. 2026) : le maillage de base de MakeHuman
    est lisse à l'entrejambe ; on lui donne le relief qu'on voit sous un maillot de lutte d'une pièce, par un
    renflement doux vers l'avant centré sous le pubis (gaussienne anisotrope). (Inférence) Amplitude et étendue
    choisies d'après les photographies de compétition fournies ; la région reste toujours couverte par le bas."""
    v = v.copy()
    hl, hr = joints["upperleg01.L"]["tete"], joints["upperleg01.R"]["tete"]
    idx = np.array(corps)
    P = v[idx]
    # sommets de la ligne médiane du maillage symétrique (x = 0 exactement) : les cuisses très musclées s'approchent
    # du plan médian sans y être, et ne doivent pas être prises pour la fourche (26 oct. 2026)
    milieu = (np.abs(P[:, 0]) < 1e-5) & (P[:, 1] > hl[1] - 0.2) & (P[:, 1] < hl[1])
    fourche = P[milieu, 1].min()                           # point le plus bas du bassin, entre les jambes
    pubis = milieu & (P[:, 1] < fourche + 0.07)
    zf = P[pubis, 2].max()                                 # avant du pubis
    yc = fourche + 0.03
    sx, sy, A = 0.026, 0.032, 0.012
    w = np.exp(-(P[:, 0] ** 2) / (2 * sx * sx) - ((P[:, 1] - yc) ** 2) / (2 * sy * sy))
    devant = np.clip((P[:, 2] - (zf - 0.05)) / 0.03, 0, 1)  # face avant seulement, fondu vers l'arrière
    d = A * w * devant
    v[idx, 2] += d
    v[idx, 1] -= 0.3 * d                                   # légère retombée vers le bas
    # le maillage est peu dense à cet endroit : un volume dédié (ellipsoïde habillé, construit dans la page)
    # donne le relief net du vêtement ; on en exporte le centre et les rayons
    GALBE.update({"centre": [0.0, float(fourche + 0.028), float(zf - 0.012)], "rayons": [0.041, 0.06, 0.031], "inclinaison": 0.5})
    return v


def noeud_de(os_nom: str, os_) -> str | None:
    """Nœud du robot qui pilote un os de MakeHuman."""
    s = None
    if os_nom.endswith(".L"):
        s = "g"
    elif os_nom.endswith(".R"):
        s = "d"
    base = os_nom.split(".")[0]
    if base in ("root", "pelvis", "spine05"):
        return "bassin"
    if base in ("spine04", "spine03"):
        return "lombaires"
    if base in ("spine02", "spine01", "breast"):
        return "poitrine"
    if base in ("neck01", "neck02"):
        return "cou"
    if base in ("clavicle", "shoulder01"):
        return f"clav_{s}"
    if base in ("upperarm01", "upperarm02"):
        return f"epaule_{s}"
    if base in ("lowerarm01", "lowerarm02"):
        return f"coude_{s}"
    if base == "wrist" or base.startswith("metacarpal"):
        return f"main_{s}"
    if base.startswith("finger"):
        f, k = base[6:].split("-")
        return f"{DOIGTS[int(f) - 1]}{int(k) - 1}_{s}"
    if base in ("upperleg01", "upperleg02"):
        return f"hanche_{s}"
    if base in ("lowerleg01", "lowerleg02"):
        return f"genou_{s}"
    if base == "foot" or base.startswith("toe"):
        return f"cheville_{s}"
    if base == "orbicularis03":
        return f"paupiere_{s}"
    # visage : sous la mâchoire → mâchoire, sinon tête
    n = os_nom
    while n:
        if n == "jaw":
            return "machoire"
        if n == "head":
            return "tete"
        n = os_[n]["parent"]
    return "tete"


REGIONS = {"tete": 0, "cou": 1, "poitrine": 2, "lombaires": 3, "bassin": 4, "clav": 2, "epaule": 5, "coude": 6, "main": 7,
           "hanche": 8, "genou": 9, "cheville": 10, "machoire": 0, "paupiere": 0}


def region(noeud: str) -> int:
    base = noeud.split("_")[0]
    if base in REGIONS:
        return REGIONS[base]
    return 7                                                       # phalanges : main


def ajuster_mhclo(chemin_mhclo: Path, v_corps: np.ndarray, v_obj: np.ndarray) -> np.ndarray:
    """Ajustement d'un « proxy » MakeHuman (fichier .mhclo) sur le corps : chaque sommet est une combinaison de
    trois sommets du corps plus un décalage mis à l'échelle (méthode de proxy.py de MakeHuman)."""
    lignes = chemin_mhclo.read_text(encoding="utf-8").splitlines()
    echelle = {}
    refs = []
    dans = False
    for l in lignes:
        p = l.split()
        if not p:
            continue
        if p[0] in ("x_scale", "y_scale", "z_scale"):
            a, b, s = int(p[1]), int(p[2]), float(p[3])
            k = "xyz".index(p[0][0])
            echelle[k] = abs(v_corps[a][k] - v_corps[b][k]) / s
        elif p[0] == "verts":
            dans = True
        elif dans and len(p) == 9:
            refs.append(p)
        elif dans and len(p) == 1:
            refs.append(p)
    out = np.zeros((len(refs), 3))
    sc = np.array([echelle.get(0, 1), echelle.get(1, 1), echelle.get(2, 1)])
    for i, p in enumerate(refs):
        if len(p) == 1:
            out[i] = v_corps[int(p[0])]
        else:
            a, b, c = (int(x) for x in p[:3]); wa, wb, wc = (float(x) for x in p[3:6]); d = np.array([float(x) for x in p[6:9]])
            out[i] = wa * v_corps[a] + wb * v_corps[b] + wc * v_corps[c] + d * sc
    assert len(out) == len(v_obj), (len(out), len(v_obj))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("--sortie", type=Path, default=RACINE / "web" / "avatar" / "humain")
    a = ap.parse_args()
    data = a.data
    v0, vt, faces = lire_obj(data / "3dobjs" / "base.obj")
    v = appliquer_cibles(data, v0)
    os_, poids = lire_squelette(data, v)

    # échelle (décimètres → mètres, hauteur du robot) ; repère : MakeHuman regarde vers +z, sa gauche en +x (comme le robot)
    corps = sorted({i for g, f in faces if g == "body" for i, _ in f})
    ymin, ymax = v[corps, 1].min(), v[corps, 1].max()
    k = HAUTEUR / (ymax - ymin)
    hz = (os_["upperleg01.L"]["tete"][2] + os_["upperleg01.R"]["tete"][2]) / 2
    def norm(p):
        return (p - np.array([0.0, ymin, hz])) * k
    v = norm(v)
    for b in os_.values():
        b["tete"] = norm(b["tete"]); b["queue"] = norm(b["queue"])

    S = {k_: np.array(x) for k_, x in SQUELETTE.items() if k_ != "boite"}
    cibles = {}
    for c, s in (("L", "g"), ("R", "d")):
        ep, co, po, ha, ge, ch, pt = (S[f"{n}_{s}"] for n in ("epaule", "coude", "poignet", "hanche", "genou", "cheville", "contact_pointe"))
        avant = np.array([0.0, 0.0, 1.0])
        cibles[f"upperarm01.{c}"] = ("upperarm01." + c, "lowerarm01." + c, co - ep, None)
        cibles[f"lowerarm01.{c}"] = ("lowerarm01." + c, "wrist." + c, po - co, ("finger1-1." + c, avant))
        cibles[f"wrist.{c}"] = ("wrist." + c, "finger3-1." + c, po - co, ("finger1-1." + c, avant))
        cibles[f"upperleg01.{c}"] = ("upperleg01." + c, "lowerleg01." + c, ge - ha, None)
        cibles[f"lowerleg01.{c}"] = ("lowerleg01." + c, "foot." + c, ch - ge, None)
        pied = pt - ch; pied[1] = 0
        cibles[f"foot.{c}"] = ("foot." + c, "toe3-1." + c, None, None)       # orientation horizontale traitée ci-dessous
    # le pied : seulement la direction horizontale (le pied reste à plat)
    for c, s in (("L", "g"), ("R", "d")):
        b = os_[f"foot.{c}"]; t = os_[f"toe3-1.{c}"]["tete"]
        d = t - b["tete"]; voulu = S[f"contact_pointe_{s}"] - S[f"cheville_{s}"]
        voulu = np.array([voulu[0], d[1], voulu[2]])
        voulu = voulu / np.linalg.norm(voulu) * np.linalg.norm(d)
        cibles[f"foot.{c}"] = (f"foot.{c}", f"toe3-1.{c}", voulu, None)
    v_rep, joints, M = reposer(os_, poids, v, cibles)
    v_rep = galbe_masculin(v_rep, corps, joints)

    # nœuds pilotés, poids réduits à 4 influences
    noeuds = []
    index_noeud = {}
    def id_noeud(n):
        if n not in index_noeud:
            index_noeud[n] = len(noeuds); noeuds.append(n)
        return index_noeud[n]
    acc = [dict() for _ in range(len(v))]
    for nom, liste in poids.items():
        if nom not in os_:
            continue
        nd = id_noeud(noeud_de(nom, os_))
        for i, w in liste:
            acc[i][nd] = acc[i].get(nd, 0) + w

    # sommets du corps seulement, renumérotés
    garder = np.array(corps)
    nouveau = -np.ones(len(v), dtype=np.int64); nouveau[garder] = np.arange(len(garder))
    # UV : MakeHuman associe des UV par coin de face ; on prend la première UV vue pour chaque sommet (couture : doublons)
    uv_sommet = {}
    tris = []
    cles = {}
    sommets = []           # (indice d'origine, indice uv)
    def sommet(vi, ti):
        key = (vi, ti if ti >= 0 else -1)
        if key not in cles:
            cles[key] = len(sommets); sommets.append(key)
        return cles[key]
    for g, f in faces:
        if g != "body":
            continue
        ids = [sommet(vi, ti) for vi, ti in f]
        for j in range(1, len(ids) - 1):
            tris.append((ids[0], ids[j], ids[j + 1]))
    n = len(sommets)
    P = np.array([v_rep[vi] for vi, _ in sommets], dtype=np.float32)
    UV = np.array([vt[ti] if ti >= 0 else (0, 0) for _, ti in sommets], dtype=np.float32)
    J = np.zeros((n, 4), dtype=np.uint8); W = np.zeros((n, 4), dtype=np.float32); REG = np.zeros(n, dtype=np.uint8)
    for k_, (vi, _) in enumerate(sommets):
        it = sorted(acc[vi].items(), key=lambda x: -x[1])[:4]
        s_ = sum(w for _, w in it) or 1
        for j, (nd, w) in enumerate(it):
            J[k_, j] = nd; W[k_, j] = w / s_
        REG[k_] = region(noeuds[it[0][0]]) if it else 0
    I = np.array(tris, dtype=np.uint32)
    # normales lissées par sommet d'origine (pas de couture visible aux coutures d'UV)
    orig = np.array([vi for vi, _ in sommets])
    nrm = np.zeros((len(v_rep), 3))
    for g, f in faces:
        if g != "body":
            continue
        pts = [v_rep[vi] for vi, _ in f]
        nf = np.cross(pts[1] - pts[0], pts[2] - pts[0]) + (np.cross(pts[2] - pts[0], pts[3] - pts[0]) if len(pts) > 3 else 0)
        for vi, _ in f:
            nrm[vi] += nf
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    N = nrm[orig].astype(np.float32)

    # pivots de liaison (position MakeHuman, dans la pose de repos du robot) de chaque nœud
    piv = {}
    def jt(nom, quoi="tete"):
        return joints[nom][quoi].tolist()
    piv["bassin"] = S["bassin"].tolist(); piv["lombaires"] = S["lombaires"].tolist(); piv["poitrine"] = S["poitrine"].tolist()
    piv["cou"] = jt("neck01"); piv["tete"] = jt("head"); piv["machoire"] = jt("jaw")
    for c, s in (("L", "g"), ("R", "d")):
        piv[f"clav_{s}"] = jt(f"clavicle.{c}"); piv[f"epaule_{s}"] = jt(f"upperarm01.{c}"); piv[f"coude_{s}"] = jt(f"lowerarm01.{c}")
        piv[f"main_{s}"] = jt(f"wrist.{c}"); piv[f"hanche_{s}"] = jt(f"upperleg01.{c}"); piv[f"genou_{s}"] = jt(f"lowerleg01.{c}")
        piv[f"cheville_{s}"] = jt(f"foot.{c}"); piv[f"paupiere_{s}"] = jt(f"eye.{c}")
        for f_, d in enumerate(DOIGTS):
            for kk in range(3):
                piv[f"{d}{kk}_{s}"] = jt(f"finger{f_ + 1}-{kk + 1}.{c}")
        piv[f"{'pouce'}3_{s}"] = jt(f"finger1-3.{c}", "queue")
        for f_, d in enumerate(DOIGTS[1:], start=2):
            piv[f"{d}3_{s}"] = jt(f"finger{f_}-3.{c}", "queue")
        piv[f"oeil_{s}"] = jt(f"eye.{c}")

    # appuis des pieds (talon, pointe), relatifs à la cheville, pour l'ancrage au sol
    pieds = {}
    for c, s_ in (("L", "g"), ("R", "d")):
        ids = [k_ for k_, (vi, _) in enumerate(sommets) if REG[k_] == 10 and (P[k_][0] > 0) == (c == "L")]
        pp = P[ids]; ch = np.array(piv[f"cheville_{s_}"])
        sol = pp[:, 1].min()
        pieds[s_] = {"talon": [0.0, float(sol - ch[1]), float(pp[:, 2].min() - ch[2] + 0.015)],
                     "pointe": [0.0, float(sol - ch[1]), float(pp[:, 2].max() - ch[2] - 0.02)]}
    # yeux : maillage « high-poly » ajusté au corps par son .mhclo, puis replacé comme la tête (aucune rotation de tête au repos)
    yo_v, yo_vt, yo_f = lire_obj(data / "eyes" / "high-poly" / "high-poly.obj")
    yeux = ajuster_mhclo(data / "eyes" / "high-poly" / "high-poly.mhclo", v, yo_v)
    # les yeux suivent l'habillage de la tête (poids de « head » : translation nulle au repos)
    cy, cyt, ytris = {}, [], []
    ysom = []
    for g, f in yo_f:
        ids = []
        for vi, ti in f:
            key = (vi, ti)
            if key not in cy:
                cy[key] = len(ysom); ysom.append(key)
            ids.append(cy[key])
        for j in range(1, len(ids) - 1):
            ytris.append((ids[0], ids[j], ids[j + 1]))
    YP = np.array([yeux[vi] for vi, _ in ysom], dtype=np.float32)
    YUV = np.array([yo_vt[ti] if ti >= 0 else (0, 0) for _, ti in ysom], dtype=np.float32)
    YC = np.array([0 if yeux[vi][0] > 0 else 1 for vi, _ in ysom], dtype=np.uint8)     # 0 : œil gauche (x > 0)
    YI = np.array(ytris, dtype=np.uint32)

    # régions fines utiles à la peinture des vêtements et des cheveux (repère du corps au repos)
    a.sortie.mkdir(parents=True, exist_ok=True)
    blocs, meta, off = [], {}, 0
    def ajoute(nom, arr):
        nonlocal off
        b = arr.tobytes(); meta[nom] = {"offset": off, "type": str(arr.dtype), "forme": list(arr.shape)}
        blocs.append(b); off += len(b)
        pad = (-off) % 4
        if pad:
            blocs.append(b"\0" * pad); off += pad
    # pied chaussé : orteils et voûte comblés jusqu'à l'enveloppe convexe du pied (chaussure_pleine.py)
    sys.path.insert(0, str(Path(__file__).parent))
    from chaussure_pleine import combler_orteils
    combler_orteils(P, N, REG, {c: piv[f"cheville_{c}"] for c in "gd"})
    for nom, arr in (("position", P), ("normale", N), ("uv", UV), ("noeud", J), ("poids", W), ("region", REG), ("indice", I),
                     ("yeux_position", YP), ("yeux_uv", YUV), ("yeux_cote", YC), ("yeux_indice", YI)):
        ajoute(nom, arr)
    (a.sortie / "corps.bin").write_bytes(b"".join(blocs))
    # texture des yeux (MakeHuman, CC0), réduite ; l'iris est recoloré dans la page
    from PIL import Image
    # (canal alpha conservé : la cornée, transparente, est peinte dans le disque bleuté de la texture)
    Image.open(data / "eyes" / "materials" / "brown_eye.png").convert("RGBA").resize((512, 512), Image.LANCZOS).save(a.sortie / "oeil.png", optimize=True)
    (a.sortie / "corps.json").write_text(json.dumps({
        "source": "MakeHuman hm08 (CC0) : base.obj, cibles macrodetails, rigs/default, eyes/high-poly",
        "morphologie": {"genre": GENRE, "age": AGE, "muscle": MUSCLE, "poids": POIDS, "hauteur_m": HAUTEUR, "definition": DEFINITION},
        "noeuds": noeuds, "pieds": pieds, "galbe": GALBE, "tete": {"demi_largeur": round(float(np.abs(P[REG == 0][:, 0]).max()), 4)}, "pivots": {k_: [round(x, 5) for x in p] for k_, p in piv.items()}, "tableaux": meta,
        "regions": {"tete": 0, "cou": 1, "tronc": 2, "taille": 3, "bassin": 4, "bras": 5, "avantbras": 6, "main": 7, "cuisse": 8, "jambe": 9, "pied": 10},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{n} sommets, {len(I)} triangles, {len(noeuds)} nœuds, yeux {len(YP)} sommets ; {off / 1024:.0f} Kio")
    for kk in ("epaule_g", "coude_g", "main_g", "hanche_g", "genou_g", "cheville_g", "cou", "tete"):
        print(kk, "MH", np.round(piv[kk], 3), "robot", SQUELETTE.get(kk.replace("main", "poignet"), "—"))


if __name__ == "__main__":
    main()
