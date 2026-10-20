"""Pilote embarqué ROBO-SCÈNE pour le Hiwonder TonyPi Pro — à exécuter sur le Raspberry Pi 5 du robot.

    sudo systemctl stop tonypi.service           # libère la carte contrôleur et la caméra (service de Hiwonder)
    python3 tonypi_embarque.py --profil tonypi_pro.toml --tcp 3333 [--camera 8080] [--capteurs toucher,ultrasons]
            [--tts "espeak-ng -v fr -s 150"] [--a-blanc]

Copier sur le robot : ce fichier, robo_scene_sdk.py et robots/tonypi_pro.toml (même dossier). Le SDK de Hiwonder
(paquet « hiwonder », installé sur l'image du robot) parle à la carte contrôleur par /dev/ttyAMA0 à 1 Mbit/s.
Profil côté pont : robots/tonypi_pro.toml (pilote = "ligne_json", mode = "tcp", port = 3333).

Ce que fait le pilote (langage unifié, PROTOCOLE.md v2.1) :
* « servos » : 16 servos de bus du corps, 2 des mains (17, 18), 2 servos PWM de la tête ; degrés relatifs à la
  position debout, convertis avec le zéro et le sens du profil, bornés une seconde fois ici ;
* « geste » : groupe d'actions natif de Hiwonder (/home/pi/TonyPi/ActionGroups), SEULEMENT s'il figure dans la liste
  fermée `gestes_natifs` du profil ; un seul à la fois ; événement « geste » (debut, fin, interrompu) ;
* « drive » : la marche passe par les groupes natifs (avancer, reculer, tourner) ; chien de garde de 500 ms ;
* « estop » : interrompt le geste et la marche, puis FIGE les servos (commande d'arrêt du bus) ; jamais de coupure
  du couple, qui ferait tomber le robot ;
* télémétrie à 20 Hz : positions (relues deux fois par seconde hors geste ; sinon cibles, « estimee »), batterie,
  centrale inertielle (tangage, roulis), distance des ultrasons ; événements « chute » (le robot se fige ; le relevé
  reste une décision humaine prise sur la page), « toucher », « bouton », « manette » ;
* « dire » (commande de synthèse vocale choisie), « lumiere » (DEL des ultrasons et de la carte), « afficher »
  (matrice de points) ;
* --camera : flux MJPEG de la caméra de tête, affiché seulement (aucun enregistrement, garde-fou G-06).

--a-blanc : aucun accès au matériel ; les commandes natives sont affichées sur la sortie d'erreur (essais sur
ordinateur, vérification des conversions avant le premier contact avec le robot).
"""
from __future__ import annotations

import argparse
import math
import os
import shlex
import subprocess
import sys
import threading
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from robo_scene_sdk import PiloteRobot  # noqa: E402

try:
    import tomllib
except ModuleNotFoundError:                     # Python < 3.11
    tomllib = None

BUS_PAS_PAR_DEG, PWM_US_PAR_DEG = 1000 / 240, 2000 / 180
MARCHE = {"avant": "go_forward", "arriere": "back", "gauche": "turn_left", "droite": "turn_right"}


# ── Conversions (identiques à bridge/robots/tonypi.py ; vérifiées par tests/test_tonypi.py) ──
def genre(a: dict) -> str:
    return "pwm" if str(a.get("id", "")).startswith("pwm:") else "bus"


def numero(a: dict) -> int:
    return int(str(a["id"]).split(":")[-1])


def vers_natif(a: dict, v: float) -> int:
    pwm = genre(a) == "pwm"
    k = float(a.get("pas_par_unite") or (PWM_US_PAR_DEG if pwm else BUS_PAS_PAR_DEG))
    p = int(round(float(a.get("zero", 1500 if pwm else 500)) + int(a.get("sens", 1)) * float(v) * k))
    return max(500, min(2500, p)) if pwm else max(0, min(1000, p))


def depuis_natif(a: dict, p: float) -> float:
    pwm = genre(a) == "pwm"
    k = float(a.get("pas_par_unite") or (PWM_US_PAR_DEG if pwm else BUS_PAS_PAR_DEG))
    return round(int(a.get("sens", 1)) * (float(p) - float(a.get("zero", 1500 if pwm else 500))) / k, 1) + 0.0


def mode_marche(g: float, d: float, seuil: float = 0.15) -> str | None:
    """Commande différentielle (−1 à 1) → groupe de marche natif, ou None (arrêt)."""
    if abs(g) < seuil and abs(d) < seuil:
        return None
    if g > seuil and d > seuil and abs(g - d) < 0.35:
        return MARCHE["avant"]
    if g < -seuil and d < -seuil and abs(g - d) < 0.35:
        return MARCHE["arriere"]
    return MARCHE["droite"] if g > d else MARCHE["gauche"]


def chute_selon_imu(ax: float, az: float) -> str | None:
    """Même critère que le relevé automatique de Hiwonder (RPCServer.standup) : angle autour de l'axe y de la carte ;
    proche de 0° : tombé en avant ; proche de 180° : tombé en arrière ; debout : voisin de ±90°."""
    a = abs(math.degrees(math.atan2(ax, az)))
    if a < 30:
        return "avant"
    if a > 150:
        return "arriere"
    return None


class Materiel:
    """Accès à la carte Hiwonder ; en mode « à blanc », affiche les commandes sans toucher au matériel."""

    def __init__(self, a_blanc: bool, dossier_actions: str):
        self.a_blanc, self.dossier = a_blanc, dossier_actions
        self.board = self.AGC = None
        if not a_blanc:
            import hiwonder.ActionGroupControl as AGC   # crée la liaison avec la carte (une seule, partagée)
            self.AGC, self.board = AGC, AGC.board
            self.board.enable_reception(True)

    def _trace(self, *x: Any) -> None:
        print("[à blanc]", *x, file=sys.stderr, flush=True)

    def bus(self, s: float, positions: list[list[int]]) -> None:
        self._trace("bus", s, positions) if self.a_blanc else self.board.bus_servo_set_position(s, positions)

    def pwm(self, s: float, positions: list[list[int]]) -> None:
        self._trace("pwm", s, positions) if self.a_blanc else self.board.pwm_servo_set_position(s, positions)

    def figer(self, ids: list[int]) -> None:
        if self.a_blanc:
            return self._trace("arrêt du bus", ids)
        self.AGC.stopActionGroup(); self.AGC.stopAction()
        self.board.bus_servo_stop(ids)              # fige à la position courante ; le couple reste appliqué

    def jouer(self, nom: str, fois: int = 1) -> None:
        if self.a_blanc:
            self._trace("groupe d'actions", nom, fois); time.sleep(1.0)
        else:
            self.AGC.runActionGroup(nom, fois, path=self.dossier.rstrip("/") + "/")

    def arreter_groupe(self) -> None:
        self._trace("arrêt du groupe") if self.a_blanc else self.AGC.stopActionGroup()

    def lire_bus(self, i: int) -> int | None:
        if self.a_blanc:
            return None
        r = self.board.bus_servo_read_position(i)
        return r[0] if r else None

    def batterie(self) -> float | None:
        if self.a_blanc:
            return None
        mv = self.board.get_battery()
        return round(mv / 1000, 2) if mv else None

    def imu(self):
        return None if self.a_blanc else self.board.get_imu()

    def manette(self):
        return None if self.a_blanc else self.board.get_gamepad()

    def bouton(self):
        return None if self.a_blanc else self.board.get_button()

    def del_carte(self, rgb: list[int]) -> None:
        self._trace("DEL carte", rgb) if self.a_blanc else self.board.set_rgb([(1, *rgb), (2, *rgb)])


class TonyPi(PiloteRobot):
    nom = "TonyPi Pro"
    version = "1.0.0"
    propulsion = True

    def __init__(self, profil: dict, a_blanc: bool = False, dossier_actions: str = "/home/pi/TonyPi/ActionGroups",
                 tts: str = "", capteurs: tuple[str, ...] = ()):
        self.arts = profil["articulations"]
        self.articulations = [(a["nom"], float(a["min"]), float(a["max"]), float(a.get("repos", 0))) for a in self.arts]
        r = profil.get("robot", {})
        self.gestes = list(r.get("gestes_natifs", []))
        self.dynamiques = set(r.get("gestes_dynamiques", []))
        super().__init__()
        self.hw = Materiel(a_blanc, dossier_actions)
        self.tts = shlex.split(tts) if tts else []
        self.ids_bus = [numero(a) for a in self.arts if genre(a) == "bus"]
        self.geste_en_cours: str | None = None
        self.marche: str | None = None
        self._fil_geste: threading.Thread | None = None
        self.etat: dict[str, Any] = {"estimee": True}
        self.chute: str | None = None
        self.capteurs = set(capteurs)
        self.sonar = None
        if "ultrasons" in self.capteurs and not a_blanc:
            import hiwonder.Sonar as Sonar
            self.sonar = Sonar.Sonar()
        self.toucher = None
        if "toucher" in self.capteurs and not a_blanc:
            import gpiod
            self.toucher = gpiod.Chip("gpiochip4").get_line(22)
            self.toucher.request(consumer="robo-scene", type=gpiod.LINE_REQ_DIR_IN, flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_UP)
        self._actif = True
        threading.Thread(target=self._surveiller, daemon=True).start()

    def info_extra(self) -> dict[str, Any]:
        return {"gestes": self.gestes, "capteurs": sorted(self.capteurs), "a_blanc": self.hw.a_blanc}

    # ── Servos ──────────────────────────────────────────────
    def appliquer_servos(self, deg: list[float], ms: int) -> None:
        if self.geste_en_cours or self.marche:
            self._interrompre("commande d'articulations")
        bus, pwm = [], []
        for a, v in zip(self.arts, deg):
            (pwm if genre(a) == "pwm" else bus).append([numero(a), vers_natif(a, v)])
        s = max(0.02, ms / 1000)
        if bus:
            self.hw.bus(s, bus)
        if pwm:
            self.hw.pwm(s, pwm)

    def figer(self) -> None:
        self.marche = None
        self.hw.figer(self.ids_bus)
        if self.geste_en_cours:
            self.evenement("geste", nom=self.geste_en_cours, etat="interrompu")
            self.geste_en_cours = None

    def arreter_geste(self) -> None:
        self._interrompre("arrêt demandé")

    def _interrompre(self, motif: str) -> None:
        self.hw.arreter_groupe()
        if self._fil_geste and self._fil_geste.is_alive():
            self._fil_geste.join(timeout=3)
        if self.geste_en_cours:
            self.evenement("geste", nom=self.geste_en_cours, etat="interrompu", motif=motif)
        self.geste_en_cours = self.marche = None

    # ── Gestes natifs et marche ─────────────────────────────
    def geste(self, nom: str) -> bool:
        if nom not in self.gestes:
            return False                                  # liste fermée du profil
        if self.chute and nom not in ("stand_up_front", "stand_up_back"):
            self._envoyer({"t": "err", "msg": f"robot tombé ({self.chute}) : seul le relevé est permis"})
            return True
        self._interrompre("nouveau geste")
        self.geste_en_cours = nom

        def jouer() -> None:
            self.evenement("geste", nom=nom, etat="debut", dynamique=nom in self.dynamiques)
            try:
                self.hw.jouer(nom, 1)
            finally:
                if self.geste_en_cours == nom:
                    self.geste_en_cours = None
                    if nom in ("stand_up_front", "stand_up_back"):
                        self.chute = None
                    self.evenement("geste", nom=nom, etat="fin")
        self._fil_geste = threading.Thread(target=jouer, daemon=True)
        self._fil_geste.start()
        return True

    def appliquer_propulsion(self, gauche: float, droite: float) -> None:
        mode = None if self.chute else mode_marche(gauche, droite)
        if mode == self.marche:
            return
        self._interrompre("changement de marche")
        self.marche = mode
        if mode:
            self.geste_en_cours = mode
            self._fil_geste = threading.Thread(target=self.hw.jouer, args=(mode, 0), daemon=True)   # 0 : en boucle
            self._fil_geste.start()
            self.evenement("marche", mode=mode)

    # ── Voix, lumières, affichage ───────────────────────────
    def dire(self, texte: str) -> bool:
        if not self.tts or not texte.strip():
            return False
        subprocess.Popen([*self.tts, texte], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    def lumiere(self, m: dict[str, Any]) -> bool:
        rgb = [max(0, min(255, int(x))) for x in (m.get("rgb") or [0, 0, 0])[:3]]
        if self.sonar is not None:
            self.sonar.setRGBMode(0); self.sonar.setRGB(0, tuple(rgb)); self.sonar.setRGB(1, tuple(rgb))
        self.hw.del_carte(rgb)
        return True

    # ── Télémétrie et événements ────────────────────────────
    def lire_etat(self) -> dict[str, Any]:
        return {k: v for k, v in self.etat.items() if v is not None}

    def _surveiller(self) -> None:
        n, chute_depuis, touche_avant = 0, None, 1
        while self._actif:
            n += 1
            time.sleep(0.05)
            imu = self.hw.imu()
            if imu:
                ax, ay, az = imu[0], imu[1], imu[2]
                self.etat["imu"] = {"tangage": round(math.degrees(math.atan2(ax, math.hypot(ay, az))), 1),
                                    "roulis": round(math.degrees(math.atan2(ay, az)), 1)}
                c = chute_selon_imu(ax, az)
                if c and not self.chute:
                    chute_depuis = chute_depuis or time.monotonic()
                    if time.monotonic() - chute_depuis > 1.0:          # même durée que le relevé de Hiwonder
                        self.chute = c
                        self.figer()
                        self.estop = True                              # verrou : le relevé exige un « reset » humain
                        self.evenement("chute", sens=c, releve=f"stand_up_{'front' if c == 'avant' else 'back'}")
                elif not c:
                    chute_depuis = None
            self.etat["chute"] = self.chute
            if n % 20 == 0:
                self.etat["vbat"] = self.hw.batterie() or self.etat.get("vbat")
            if self.sonar is not None and n % 4 == 0:
                mm = self.sonar.getDistance()
                self.etat["dist"] = round(mm / 10, 1) if mm and mm < 5000 else None
            if self.toucher is not None:
                v = self.toucher.get_value()
                if v == 0 and touche_avant == 1:
                    self.evenement("toucher")
                touche_avant = v
            b = self.hw.bouton()
            if b:
                self.evenement("bouton", numero=b[0], appui_long=bool(b[1]))
            g = self.hw.manette()
            if g:
                self.evenement("manette", donnees=list(g) if not isinstance(g, dict) else g)
            if n % 10 == 0 and not self.geste_en_cours and not self.hw.a_blanc:
                self._relire_positions()

    def _relire_positions(self) -> None:
        mesure = list(self.deg)
        complet = True
        for k, a in enumerate(self.arts):
            if genre(a) != "bus":
                continue
            p = self.hw.lire_bus(numero(a))
            if p is None:
                complet = False
            else:
                mesure[k] = depuis_natif(a, p)
        self.deg = mesure
        self.etat["estimee"] = not complet


def charger_profil(chemin: str) -> dict:
    if tomllib is None:
        raise SystemExit("Python 3.11 ou plus requis (tomllib) pour lire le profil")
    with open(chemin, "rb") as f:
        return tomllib.load(f)


def servir_mjpeg(port: int, camera: int = 0) -> None:
    """Flux MJPEG de la caméra de tête (affichage seul : rien n'est écrit sur disque)."""
    import cv2
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    cap = cv2.VideoCapture(camera)
    verrou, image = threading.Lock(), [None]

    def capter() -> None:
        while True:
            ok, im = cap.read()
            if ok:
                with verrou:
                    image[0] = cv2.imencode(".jpg", im, [int(cv2.IMWRITE_JPEG_QUALITY), 75])[1].tobytes()
            else:
                time.sleep(0.1)
    threading.Thread(target=capter, daemon=True).start()

    class Flux(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=image")
            self.end_headers()
            try:
                while True:
                    with verrou:
                        j = image[0]
                    if j:
                        self.wfile.write(b"--image\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(j)).encode() + b"\r\n\r\n" + j + b"\r\n")
                    time.sleep(1 / 20)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *a):
            pass
    threading.Thread(target=ThreadingHTTPServer(("0.0.0.0", port), Flux).serve_forever, daemon=True).start()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profil", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "tonypi_pro.toml"))
    ap.add_argument("--tcp", type=int, default=3333)
    ap.add_argument("--actions", default="/home/pi/TonyPi/ActionGroups")
    ap.add_argument("--tts", default="", help='commande de synthèse vocale, ex. "espeak-ng -v fr -s 150"')
    ap.add_argument("--capteurs", default="", help="liste séparée par des virgules : ultrasons, toucher")
    ap.add_argument("--camera", type=int, default=0, help="port du flux MJPEG (0 : pas de flux)")
    ap.add_argument("--a-blanc", action="store_true")
    a = ap.parse_args()
    if a.camera:
        servir_mjpeg(a.camera)
    robot = TonyPi(charger_profil(a.profil), a.a_blanc, a.actions, a.tts,
                   tuple(x.strip() for x in a.capteurs.split(",") if x.strip()))
    robot.servir_tcp(a.tcp)
