"""Jumeau numérique sans affichage du Reachy Mini (repère P2.2).

Joue chaque geste de la bibliothèque fermée dans le modèle MuJoCo officiel fourni avec le
SDK Reachy Mini, en calculant les consignes articulaires par la cinématique inverse du SDK,
puis produit un rapport de validation (suivi de trajectoire, échecs de cinématique inverse,
contacts) et, si le rendu est disponible, une planche d'images par geste.

Usage :
    python jumeau.py                         # tous les gestes
    python jumeau.py acquiescer salut        # gestes choisis
    python jumeau.py --sans-images
    python jumeau.py --sequences             # séquences P2.4 (rapport_validation_sequences.json)

Prérequis : pip install "reachy-mini[mujoco]" pyyaml pillow
Le rapport PROPOSE un statut ; seul l'opérateur modifie le statut dans le fichier YAML.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))  # modules/p2 : gestes_scene
from gestes_scene import charger, valider, echantillonner, charger_sequences  # noqa: E402


def _importer_sdk():
    """Importe les modules du SDK. Si les liaisons GStreamer (gi) manquent — cas d'un serveur
    sans interface —, un module factice est installé : seules la cinématique et le modèle
    MuJoCo sont utilisés ici, jamais l'audio ni la vidéo."""
    try:
        import gi  # noqa: F401
    except ImportError:
        gi = types.ModuleType("gi")
        rep = types.ModuleType("gi.repository")

        class _Factice:
            def __getattr__(self, k):
                return _Factice()

            def __call__(self, *a, **k):
                return _Factice()

        for n in ("GLib", "Gst", "GstApp", "GObject", "GstVideo", "GstAudio"):
            setattr(rep, n, _Factice())
        gi.repository = rep
        gi.require_version = lambda *a, **k: None
        sys.modules["gi"], sys.modules["gi.repository"] = gi, rep
    import mujoco
    from importlib.resources import files
    import reachy_mini
    from reachy_mini.kinematics.analytical_kinematics import AnalyticalKinematics
    from reachy_mini.utils import create_head_pose
    from reachy_mini.daemon.backend.mujoco.utils import get_actuator_names, get_joint_addr_from_name
    return mujoco, files, reachy_mini, AnalyticalKinematics, create_head_pose, get_actuator_names, get_joint_addr_from_name


class Jumeau:
    def __init__(self, scene: str = "empty", images: bool = True):
        (self.mj, files, rm, AK, self.pose, actuateurs, adresse) = _importer_sdk()
        racine = str(files(rm).joinpath("descriptions/reachy_mini/mjcf/"))
        self.m = self.mj.MjModel.from_xml_path(f"{racine}/scenes/{scene}.xml")
        self.m.opt.timestep = 0.002          # 500 Hz, comme le simulateur du SDK
        self.d = self.mj.MjData(self.m)
        self.noms = actuateurs(self.m)       # yaw_body, stewart_1..6, right_antenna, left_antenna
        self.adr = np.array([adresse(self.m, n) for n in self.noms]).ravel()
        self.kin = AK(automatic_body_yaw=False)
        self.site = self.mj.mj_name2id(self.m, self.mj.mjtObj.mjOBJ_SITE, "head")
        self.rendu = None
        if images:
            try:
                self.rendu = self.mj.Renderer(self.m, 240, 320)
            except Exception as e:  # pas de contexte OpenGL : rapport sans images
                print("Rendu indisponible :", e)

    def _consigne(self, tete, ant, by):
        P = self.pose(x=tete["x"], y=tete["y"], z=tete["z"], roll=tete["roll"], pitch=tete["pitch"],
                      yaw=tete["yaw"], mm=True, degrees=True)
        q = np.asarray(self.kin.ik(P, body_yaw=math.radians(by)), dtype=float)
        if q.shape != (7,) or not np.all(np.isfinite(q)):
            raise ValueError("cinématique inverse sans solution")
        return P, q, np.radians(ant)

    def _repos(self):
        self.mj.mj_resetData(self.m, self.d)
        P, q, a = self._consigne({c: 0.0 for c in ("x", "y", "z", "roll", "pitch", "yaw")}, (0, 0), 0)
        self.d.qpos[self.adr[:7]] = q
        self.d.ctrl[:7], self.d.ctrl[-2:] = q, -a
        self.mj.mj_forward(self.m, self.d)
        for _ in range(300):
            self.mj.mj_step(self.m, self.d)
        self.z0 = float(self.d.site_xpos[self.site][2])  # hauteur de la tête au neutre

    def jouer(self, geste, facteur_vitesse=1.0, images_max=6):
        self._repos()
        pas_par_consigne = 10                         # consignes à 50 Hz
        ecarts_pos, ecarts_ang, echecs, contacts_max = [], [], 0, 0
        vues, traj = [], list(echantillonner(geste, frequence=50, facteur_vitesse=facteur_vitesse))
        cadence = max(1, len(traj) // images_max)
        q_prec = None
        for i, (t, tete, ant, by) in enumerate(traj):
            try:
                P, q, a = self._consigne(tete, ant, by)
                q_prec = q
            except ValueError:
                echecs += 1
                if q_prec is None:
                    continue
                q, a = q_prec, np.radians(ant)
            self.d.ctrl[:7], self.d.ctrl[-2:] = q, -a
            for _ in range(pas_par_consigne):
                self.mj.mj_step(self.m, self.d)
            # écart entre consigne articulaire et position atteinte (suivi des moteurs simulés)
            atteint = self.d.qpos[self.adr[:7]]
            ecarts_ang.append(float(np.max(np.abs(atteint - q))))
            # écart de position de la tête : vertical seulement, mesuré par rapport au neutre
            ecarts_pos.append(abs((float(self.d.site_xpos[self.site][2]) - self.z0) * 1000 - tete["z"]))
            contacts_max = max(contacts_max, int(self.d.ncon))
            if self.rendu is not None and i % cadence == 0 and len(vues) < images_max:
                self.rendu.update_scene(self.d, camera=self._camera())
                vues.append((t, self.rendu.render().copy()))
        return {
            "geste": geste.nom,
            "duree_s": round(traj[-1][0], 2) if traj else 0,
            "facteur_vitesse": facteur_vitesse,
            "echecs_ik": echecs,
            "ecart_articulaire_max_rad": round(max(ecarts_ang, default=0), 4),
            "ecart_vertical_max_mm": round(max(ecarts_pos, default=0), 2),
            "contacts_max": contacts_max,
        }, vues

    def _camera(self):
        cam = self.mj.MjvCamera()
        cam.type = self.mj.mjtCamera.mjCAMERA_FREE
        cam.distance, cam.azimuth, cam.elevation = 0.75, 160, -15
        cam.lookat[:] = [0, 0, 0.15]
        return cam


def planche(vues, chemin, titre):
    from PIL import Image, ImageDraw, ImageFont
    if not vues:
        return
    try:
        police = ImageFont.truetype("DejaVuSans.ttf", 13)
    except OSError:
        try:
            police = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 13)  # macOS
        except OSError:
            police = ImageFont.load_default()
    h, w = vues[0][1].shape[:2]
    img = Image.new("RGB", (w * len(vues), h + 22), (20, 18, 15))
    dr = ImageDraw.Draw(img)
    dr.text((6, 4), titre, fill=(217, 178, 92), font=police)
    for i, (t, v) in enumerate(vues):
        img.paste(Image.fromarray(v), (i * w, 22))
        dr.text((i * w + 6, 26), f"t = {t:.1f} s", fill=(240, 240, 240), font=police)
    img.save(chemin)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gestes", nargs="*")
    ap.add_argument("--sans-images", action="store_true")
    ap.add_argument("--sequences", action="store_true", help="valider les séquences P2.4 au lieu des gestes")
    ap.add_argument("--sortie", default=str(ICI / "rapports"))
    a = ap.parse_args()
    sortie = Path(a.sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    biblio = charger()
    if a.sequences:
        biblio = charger_sequences(biblio=biblio)       # gestes composites, joués d'un seul tenant
    noms = a.gestes or list(biblio)
    j = Jumeau(images=not a.sans_images)
    # Seuils d'acceptation (inférence, à recalibrer) : aucun échec de cinématique inverse,
    # suivi articulaire < 0,15 rad, écart vertical < 5 mm, aucun contact (auto-collision),
    # conformité aux limites statiques.
    resultats = []
    for n in noms:
        g = biblio[n]
        violations = valider(g)
        for f, etiquette in ((0.5, "lente"), (1.0, "pleine")):
            r, vues = j.jouer(g, facteur_vitesse=f, images_max=8 if a.sequences else 6)
            r["vitesse"] = etiquette
            r["violations_limites"] = violations
            r["conforme"] = (not violations and r["echecs_ik"] == 0
                             and r["ecart_articulaire_max_rad"] < 0.15 and r["ecart_vertical_max_mm"] < 5
                             and r["contacts_max"] == 0)
            resultats.append(r)
            if f == 1.0 and vues:
                planche(vues, sortie / (f"seq_{n}.png" if a.sequences else f"{n}.png"), f"{n} — {g.description.get('fr', '')}")
            print(f"{n:16} {etiquette:6} IK✗={r['echecs_ik']}  suivi={r['ecart_articulaire_max_rad']:.3f} rad  "
                  f"Δz={r['ecart_vertical_max_mm']:.1f} mm  contacts={r['contacts_max']}  {'✓' if r['conforme'] else '✗'}")
    rapport = {
        "date": datetime.now(timezone.utc).isoformat(),
        "outil": "jumeau.py v1.1 — modèle MuJoCo et cinématique du SDK Reachy Mini",
        "seuils": {"echecs_ik": 0, "ecart_articulaire_max_rad": 0.15, "ecart_vertical_max_mm": 5, "contacts_max": 0},
        "resultats": resultats,
        "statut_propose": {n: ("valide_sim" if all(r["conforme"] for r in resultats if r["geste"] == n)
                               else "brouillon") for n in noms},
        "rappel": "Le statut proposé n'est appliqué qu'après revue humaine (plan P2.1, §6.5).",
    }
    nom_rapport = "rapport_validation_sequences.json" if a.sequences else "rapport_validation_sim.json"
    (sortie / nom_rapport).write_text(json.dumps(rapport, ensure_ascii=False, indent=1),
                                                        encoding="utf-8")
    print("Rapport :", sortie / nom_rapport)


if __name__ == "__main__":
    main()
