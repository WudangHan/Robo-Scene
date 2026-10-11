"""Interface d'atelier locale (P1.3) : application web servie sur 127.0.0.1 seulement.

    python -m atelier_p1.serveur --seance S01 --pseudonymes A01 A02 A03                 # essai, modèles réels
    python -m atelier_p1.serveur --seance ESSAI --pseudonymes T1 --simule                # essai sans réseau
    python -m atelier_p1.serveur --seance S03 --pseudonymes A07 --mode atelier \\
        --liste-blocage "/Volumes/Projet_chiffre/liste_blocage.txt" --journal "/Volumes/Projet_chiffre/journaux"
"""
from __future__ import annotations

import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .atelier import Atelier, ErreurAtelier
from .corpus import charger_corpus
from .modeles import TYPES, ModeleDistant, ModeleLocal, ModeleSimule
from .routeur import charger_liste_blocage

ICI = Path(__file__).resolve().parent
TAILLE_MAX = 64_000


def fabriquer_gestionnaire(atelier: Atelier):
    class G(BaseHTTPRequestHandler):
        server_version = "SI-04/0.1"
        sys_version = ""

        def log_message(self, format, *args):  # noqa: A002 — rien n'est journalisé hors du journal I-5
            pass

        def _envoyer(self, code, corps: bytes, type_="application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", type_)
            self.send_header("Content-Length", str(len(corps)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                             "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(corps)

        def _json(self, code, obj):
            self._envoyer(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def etat(self):
            a = atelier
            return {
                "seance": a.seance, "mode": a.mode, "hors_ligne": a.hors_ligne, "pseudonymes": a.pseudonymes,
                "types": TYPES, "corpus": [e.public() for e in a.corpus.values()], "jetons": a.jetons,
                "plafond_jetons": a.plafond, "simule": a.forcer_simule,
                "modeles": {"distant": {"code": a.distant.code, "modele": a.distant.modele, "disponible": a.distant.disponible},
                            "local": {"code": a.local.code, "modele": a.local.modele or "(non configuré)",
                                      "disponible": a.local.disponible}},
                "cycles": [{"id": c.id, "pseudonyme": c.pseudonyme, "type": c.type, "consigne": c.consigne,
                            "extraits": c.extraits,
                            "generations": [{"systeme": g.systeme, "modele": g.modele, "cible": g.cible,
                                             "motifs": g.motifs_routage, "propositions": [p.__dict__ for p in g.propositions]}
                                            for g in c.generations]} for c in a.cycles.values()],
                "texte_final": a.segments, "indicateurs": a.indicateurs(),
            }

        def do_GET(self):  # noqa: N802
            chemin = urlparse(self.path).path
            if chemin in ("/", "/index.html"):
                return self._envoyer(200, (ICI / "static" / "atelier.html").read_bytes(), "text/html; charset=utf-8")
            if chemin == "/api/etat":
                return self._json(200, self.etat())
            return self._json(404, {"erreur": "Introuvable."})

        def do_POST(self):  # noqa: N802
            # Protection minimale contre les requêtes intersites : en-tête propre à l'application exigé.
            if self.headers.get("X-Atelier") != "1":
                return self._json(403, {"erreur": "Requête refusée."})
            n = int(self.headers.get("Content-Length") or 0)
            if n > TAILLE_MAX:
                return self._json(413, {"erreur": "Requête trop volumineuse."})
            try:
                d = json.loads(self.rfile.read(n) or b"{}")
                chemin = urlparse(self.path).path
                a = atelier
                if chemin == "/api/consigne":
                    a.consigner(d.get("pseudonyme", ""), d.get("texte", ""), d.get("type", "libre"),
                                int(d.get("nb", 3)), d.get("extraits", []), bool(d.get("confidentielle")))
                elif chemin == "/api/redemander":
                    a.redemander(d["cycle"], d.get("motif", ""))
                elif chemin == "/api/decision":
                    a.decider(d["cycle"], int(d["gen"]), int(d["prop"]), d["decision"], d.get("motif", ""))
                elif chemin == "/api/transformer":
                    a.transformer(d["cycle"], int(d["gen"]), int(d["prop"]), d.get("texte", ""))
                elif chemin == "/api/attribuer":
                    a.attribuer(d["cycle"], int(d["gen"]), int(d["prop"]), d.get("etiquette") or None, d.get("credit", ""))
                elif chemin == "/api/segment":
                    a.segment_humain(d.get("pseudonyme", ""), d.get("texte", ""))
                elif chemin == "/api/reetiqueter":
                    a.reetiqueter(int(d["index"]), d["etiquette"])
                elif chemin == "/api/hors_ligne":
                    a.regler_hors_ligne(bool(d.get("actif")))
                elif chemin == "/api/exporter":
                    chemins = a.exporter()
                    return self._json(200, {"export": {k: str(v) for k, v in chemins.items()}, **self.etat()})
                else:
                    return self._json(404, {"erreur": "Introuvable."})
                return self._json(200, self.etat())
            except ErreurAtelier as e:
                return self._json(400, {"erreur": str(e), **self.etat()})
            except (KeyError, ValueError, json.JSONDecodeError) as e:
                return self._json(400, {"erreur": f"Requête invalide ({e.__class__.__name__})."})

    return G


def main(argv=None):
    ap = argparse.ArgumentParser(description="Atelier dramaturgique P1.3 (SI-04) — interface locale")
    ap.add_argument("--seance", required=True, help="identifiant de séance, ex. S01")
    ap.add_argument("--pseudonymes", nargs="+", required=True, help="pseudonymes des artistes (jamais de noms)")
    ap.add_argument("--mode", choices=["essai", "atelier"], default="essai")
    ap.add_argument("--mise-en-service", default=str(ICI.parent / "config" / "mise_en_service.yaml"))
    ap.add_argument("--corpus", default=str(ICI.parent / "corpus"))
    ap.add_argument("--liste-blocage", default=None, help="fichier HORS du dossier du projet (volume chiffré)")
    ap.add_argument("--journal", default="journaux", help="dossier du journal I-5 (volume chiffré recommandé)")
    ap.add_argument("--modele-distant", default="claude-opus-5-5")
    ap.add_argument("--modele-local", default=None, help="nom du modèle Ollama (ou variable ATELIER_MODELE_LOCAL)")
    ap.add_argument("--simule", action="store_true", help="générateur simulé, sans réseau (mode essai seulement)")
    ap.add_argument("--plafond-jetons", type=int, default=200_000)
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--sans-navigateur", action="store_true")
    a = ap.parse_args(argv)

    atelier = Atelier(seance=a.seance, pseudonymes=a.pseudonymes, corpus=charger_corpus(a.corpus),
                      distant=ModeleDistant(a.modele_distant), local=ModeleLocal(a.modele_local),
                      simule=ModeleSimule(), dossier_journal=a.journal,
                      liste_blocage=charger_liste_blocage(a.liste_blocage), mode=a.mode,
                      mise_en_service=a.mise_en_service, plafond_jetons=a.plafond_jetons, forcer_simule=a.simule)
    httpd = ThreadingHTTPServer(("127.0.0.1", a.port), fabriquer_gestionnaire(atelier))
    url = f"http://127.0.0.1:{a.port}/"
    print(f"Atelier {a.seance} ({a.mode}) — {url}")
    print(f"Journal I-5 : {atelier.fichier}")
    if not a.liste_blocage:
        print("⚠ Aucune liste de blocage chargée : à fournir avant tout atelier réel (ENF-01).")
    if not a.sans_navigateur:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nExport final…", {k: str(v) for k, v in atelier.exporter().items()})
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
