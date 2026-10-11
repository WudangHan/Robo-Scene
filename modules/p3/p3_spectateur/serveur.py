"""Serveur local de l'interface spectateur (P3.2) : HTTP, flux SSE et entrée OSC.

    python -m p3_spectateur.serveur --titre "Essai 1" --provenance-affichee
    python -m p3_spectateur.serveur --port 8080 --osc 9000 --osc 8000 --exports ./exports

Le serveur ne journalise ni adresse IP ni contenu de réponse ; il n'envoie aucun témoin (cookie).
Il est conçu pour un réseau local de salle, sans accès à Internet.
"""
from __future__ import annotations

import argparse
import json
import queue
import socket
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .agregat import ErreurSeance, Seance

STATIQUE = Path(__file__).parent / "static"
TAILLE_MAX = 2048  # octets : une réponse tient en quelques dizaines d'octets
ENTETES_SECURITE = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                               "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
}


def fabriquer_gestionnaire(seance: Seance, journal=print, dossier_exports: Path | None = None):
    class Gestionnaire(BaseHTTPRequestHandler):
        server_version = "P3-SI06/0.1"
        sys_version = ""

        # Aucune journalisation de l'adresse du client (G.6, DO-04).
        def log_message(self, format, *args):  # noqa: A002
            pass

        # -------------------------------------------------------------- utilitaires
        def _envoyer(self, code: int, corps: bytes, type_: str = "application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", type_)
            self.send_header("Content-Length", str(len(corps)))
            for k, v in ENTETES_SECURITE.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(corps)

        def _json(self, code: int, obj):
            self._envoyer(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def _lire_json(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > TAILLE_MAX:
                raise ErreurSeance("Requête trop volumineuse.")
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError as e:
                raise ErreurSeance("JSON invalide.") from e

        def _regie_autorisee(self) -> bool:
            import secrets
            cle = self.headers.get("X-Cle-Regie") or parse_qs(urlparse(self.path).query).get("cle", [""])[0]
            return secrets.compare_digest(cle, seance.cle_regie)

        def _fichier(self, nom: str):
            corps = (STATIQUE / nom).read_bytes()
            self._envoyer(200, corps, "text/html; charset=utf-8")

        # -------------------------------------------------------------- GET
        def do_GET(self):  # noqa: N802
            chemin = urlparse(self.path).path
            if chemin in ("/", "/index.html"):
                return self._fichier("public.html")
            if chemin == "/regie":
                return self._fichier("regie.html")
            if chemin == "/api/seance":
                return self._json(200, {"titre": seance.titre, "close": seance.close,
                                        "delai_min_s": seance.delai_min_s,
                                        "condition_provenance_affichee": seance.afficher_provenance,
                                        **seance.evenement_provenance()})
            if chemin == "/api/flux":
                return self._flux()
            if chemin == "/api/regie/etat":
                if not self._regie_autorisee():
                    return self._json(403, {"erreur": "Clé de régie requise."})
                return self._json(200, seance.etat_regie())
            return self._json(404, {"erreur": "Introuvable."})

        def _flux(self):
            """Server-Sent Events : étiquette de provenance (si la condition H4 est active) et fin."""
            file: queue.Queue = queue.Queue(maxsize=50)

            def pousser(nom, donnees):
                file.put_nowait((nom, donnees))

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            for k, v in ENTETES_SECURITE.items():
                self.send_header(k, v)
            self.end_headers()
            seance.abonner(pousser)
            try:
                self._evenement("provenance", seance.evenement_provenance())
                while not getattr(self.server, "arret_demande", False):
                    try:
                        nom, donnees = file.get(timeout=15)
                        self._evenement(nom, donnees)
                        if nom == "fin":
                            break
                    except queue.Empty:
                        self.wfile.write(b": maintien\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                seance.desabonner(pousser)

        def _evenement(self, nom, donnees):
            self.wfile.write(f"event: {nom}\ndata: {json.dumps(donnees, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()

        # -------------------------------------------------------------- POST
        def do_POST(self):  # noqa: N802
            chemin = urlparse(self.path).path
            try:
                corps = self._lire_json()
                if chemin == "/api/rejoindre":
                    return self._json(200, {"jeton": seance.rejoindre(str(corps.get("code", "")))})
                if chemin == "/api/reponse":
                    cle = seance.repondre(str(corps.get("jeton", "")), emotion=corps.get("emotion"),
                                          v=corps.get("v"), a=corps.get("a"))
                    return self._json(200, {"emotion": cle})
                if chemin.startswith("/api/regie/"):
                    if not self._regie_autorisee():
                        return self._json(403, {"erreur": "Clé de régie requise."})
                    if chemin == "/api/regie/provenance":
                        seance.etiqueter(str(corps.get("etiquette", "")), corps.get("repere"))
                        return self._json(200, {"provenance": seance.provenance})
                    if chemin == "/api/regie/fin":
                        export = seance.terminer()
                        chemin_export = enregistrer_export(export, dossier_exports, journal)
                        return self._json(200, {"export": str(chemin_export) if chemin_export else None})
                return self._json(404, {"erreur": "Introuvable."})
            except ErreurSeance as e:
                return self._json(e.code_http, {"erreur": str(e)})

    return Gestionnaire


def enregistrer_export(export: dict, dossier: Path | None, journal=print) -> Path | None:
    if dossier is None:
        return None
    dossier.mkdir(parents=True, exist_ok=True)
    p = dossier / f"{datetime.now():%Y-%m-%d_%H%M}_P3-2_agregat_seance.json"
    p.write_text(json.dumps(export, ensure_ascii=False, indent=1), encoding="utf-8")
    journal(f"Agrégat de la séance enregistré : {p}")
    return p


def demarrer_osc(seance: Seance, port: int, dossier_exports: Path | None = None, journal=print, hote="0.0.0.0"):
    """Écoute les messages du pont scénique (P2.3) : /p3/provenance <étiquette> [repère], /p3/repere, /p3/fin."""
    from pythonosc.dispatcher import Dispatcher
    from pythonosc.osc_server import ThreadingOSCUDPServer

    d = Dispatcher()

    def provenance(_adr, *args):
        try:
            seance.etiqueter(str(args[0]), str(args[1]) if len(args) > 1 else None)
            journal(f"OSC : provenance « {seance.provenance} » (repère {seance.repere})")
        except (IndexError, ErreurSeance) as e:
            journal(f"OSC ignoré : /p3/provenance {list(args)} ({e})")

    def repere(_adr, *args):
        if args:
            seance.marquer_repere(str(args[0]))

    def fin(_adr, *args):
        if not seance.close:
            enregistrer_export(seance.terminer(), dossier_exports, journal)
            journal("OSC : fin de séance")

    d.map("/p3/provenance", provenance)
    d.map("/p3/repere", repere)
    d.map("/p3/fin", fin)
    serveur = ThreadingOSCUDPServer((hote, port), d)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    return serveur


def adresse_locale() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # aucun paquet n'est envoyé ; sert à connaître l'interface locale
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def creer_serveur(seance: Seance, hote="0.0.0.0", port=8080, dossier_exports: Path | None = None, journal=print):
    httpd = ThreadingHTTPServer((hote, port), fabriquer_gestionnaire(seance, journal, dossier_exports))
    httpd.daemon_threads = True
    return httpd


def main(argv=None):
    ap = argparse.ArgumentParser(description="Interface spectateur P3.2 — serveur local d'agrégation anonyme")
    ap.add_argument("--titre", default="Séance d'essai")
    ap.add_argument("--hote", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--osc", type=int, action="append", help="port(s) OSC d'écoute (défaut : 9000)")
    ap.add_argument("--provenance-affichee", action="store_true", help="condition H4 : le public voit l'étiquette")
    ap.add_argument("--fenetre", type=float, default=30.0, help="durée d'une fenêtre d'agrégation (s)")
    ap.add_argument("--delai", type=float, default=10.0, help="délai minimal entre deux réponses d'un appareil (s)")
    ap.add_argument("--seuil", type=int, default=5, help="seuil de diffusion des cellules à l'export")
    ap.add_argument("--exports", default="exports", help="dossier de l'agrégat de fin de séance")
    a = ap.parse_args(argv)

    seance = Seance(titre=a.titre, fenetre_s=a.fenetre, delai_min_s=a.delai, seuil_diffusion=a.seuil,
                    afficher_provenance=a.provenance_affichee)
    dossier = Path(a.exports)
    httpd = creer_serveur(seance, a.hote, a.port, dossier)
    ports_osc = a.osc or [9000]
    oscs = [demarrer_osc(seance, p, dossier) for p in ports_osc]
    ip = adresse_locale()
    print(f"Séance « {seance.titre} » — code à afficher en salle : {seance.code}")
    print(f"Public  : http://{ip}:{a.port}/?code={seance.code}")
    print(f"Régie   : http://127.0.0.1:{a.port}/regie?cle={seance.cle_regie}   (ne pas diffuser)")
    print(f"OSC     : ports {', '.join(map(str, ports_osc))} — /p3/provenance, /p3/repere, /p3/fin")
    print(f"Condition « provenance affichée » (H4) : {'oui' if seance.afficher_provenance else 'non'}")
    print("Ctrl+C pour arrêter (l'agrégat est enregistré si la séance n'a pas été close).")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.arret_demande = True
        if not seance.close:
            enregistrer_export(seance.terminer(), dossier)
        for o in oscs:
            o.shutdown()
        httpd.server_close()


if __name__ == "__main__":
    main()
