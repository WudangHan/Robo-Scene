"""Routes du volet spectateur.

* Sur la console (127.0.0.1 par défaut) : /spectateur/api/… pour la régie (tirage, séance P3, passation).
* Serveur public distinct (0.0.0.0:8081 par défaut) : questionnaire seulement — aucune route de régie,
  aucune adresse IP journalisée (access_log désactivé), aucun témoin, en-têtes de sécurité stricts.
"""
from __future__ import annotations

import json
from pathlib import Path

from aiohttp import web

from ..gouvernance import VerrouGouvernance
from ..securite import CommandeRefusee
from . import GestionSpectateur
from .questionnaire import ReponseInvalide
from .tirage import TirageExistant

STATIQUE = Path(__file__).parent / "static"
ENTETES = {
    "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                               "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'",
}
REFUS = (CommandeRefusee, VerrouGouvernance, ReponseInvalide, TirageExistant, ValueError, KeyError)


def monter(app: web.Application, ctl) -> GestionSpectateur:
    g = GestionSpectateur(ctl, ctl.cfg.get("spectateur", {}))

    async def etat(_):
        return web.json_response(g.etat())

    async def post(request: web.Request) -> web.Response:
        if request.headers.get("X-Regie") != "1":
            return web.json_response({"erreur": "Requête refusée."}, status=403)
        try:
            d = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"erreur": "JSON invalide"}, status=400)
        action = request.match_info["action"]
        try:
            if action == "tirage":
                r = g.tirage.effectuer(int(d["representations"]), int(d["graine"]), bool(d.get("sans_support")),
                                       d.get("par", ""))
                from ..pilotage.depots import consigner
                consigner(ctl.donnees, [g.tirage.csv, g.tirage.meta], "Tirage scellé des conditions X.2")
                return web.json_response({"tirage": r, **g.etat()})
            if action == "p3_ouvrir":
                return web.json_response(g.ouvrir_p3(id_representation=str(d.get("id_representation", "")).strip()
                                                     or "ESSAI", titre=d.get("titre", ""), mode=d.get("mode", "essai"),
                                                     provenance_affichee=d.get("provenance_affichee")))
            if action == "p3_fermer":
                return web.json_response(g.fermer_p3())
            if action == "p3_etiquette":
                g.etiqueter(str(d.get("etiquette", "")), d.get("repere"))
                return web.json_response(g.etat())
            if action == "passation_ouvrir":
                return web.json_response(g.ouvrir_passation(
                    instrument=d.get("instrument", "I-7"), id_representation=str(d.get("id_representation", "ESSAI")),
                    mode=d.get("mode", "essai"), provenance_affichee=d.get("provenance_affichee"),
                    support=d.get("support")))
            if action == "passation_fermer":
                return web.json_response(g.fermer_passation())
            if action == "instruments_recharger":
                g.recharger_instruments()
                return web.json_response(g.etat())
            return web.json_response({"erreur": f"Action inconnue : {action}"}, status=404)
        except REFUS as exc:
            return web.json_response({"erreur": str(exc), **g.etat()}, status=409 if isinstance(exc, VerrouGouvernance)
                                     else 400)

    async def avis(request):
        return web.json_response(g.avis(request.query.get("langue", "fr")))

    app.router.add_get("/spectateur/api/etat", etat)
    app.router.add_get("/spectateur/api/avis", avis)
    app.router.add_post("/spectateur/api/{action}", post)
    return g


def app_publique(g: GestionSpectateur) -> web.Application:
    @web.middleware
    async def entetes(request, handler):
        try:
            r = await handler(request)
        except web.HTTPException as exc:
            r = exc
        for k, v in ENTETES.items():
            r.headers[k] = v
        r.headers.popall("Set-Cookie", None)  # aucune pose de témoin
        return r

    app = web.Application(middlewares=[entetes], client_max_size=32 * 1024)

    async def page(_):
        return web.FileResponse(STATIQUE / "questionnaire.html")

    async def formulaire(request):
        try:
            return web.json_response(g.formulaire(request.query.get("langue", "fr")))
        except CommandeRefusee as exc:
            return web.json_response({"ferme": True, "erreur": str(exc), "avis": g.avis(request.query.get("langue", "fr"))},
                                     status=409)

    async def reponse(request):
        if request.headers.get("X-Questionnaire") != "1":
            return web.json_response({"erreur": "Requête refusée."}, status=403)
        try:
            d = await request.json()
            if not isinstance(d, dict):
                raise ReponseInvalide("Objet JSON attendu")
            return web.json_response(g.recevoir(d))
        except json.JSONDecodeError:
            return web.json_response({"erreur": "JSON invalide"}, status=400)
        except (CommandeRefusee, ReponseInvalide) as exc:
            return web.json_response({"erreur": str(exc)}, status=400)

    app.router.add_get("/", page)
    app.router.add_get("/api/formulaire", formulaire)
    app.router.add_post("/api/reponses", reponse)
    return app


async def demarrer_public(g: GestionSpectateur, hote: str | None = None, port: int | None = None) -> dict:
    hote = hote or g.cfg.get("hote_public", "0.0.0.0")
    port = int(g.cfg.get("port_questionnaires", 8081) if port is None else port)
    runner = web.AppRunner(app_publique(g), access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, hote, port)
    await site.start()
    reel = site._server.sockets[0].getsockname()[1] if getattr(site, "_server", None) else port
    g.serveur_public = {"runner": runner, "hote": hote, "port": reel}
    return g.serveur_public


async def arreter_public(g: GestionSpectateur) -> None:
    if g.serveur_public:
        await g.serveur_public["runner"].cleanup()
        g.serveur_public = None
