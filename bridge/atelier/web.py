"""Routes HTTP de l'atelier P1 (même API que le prototype, préfixée par /atelier/api)."""
from __future__ import annotations

import json

from aiohttp import web

from .. import _modules  # noqa: F401
from atelier_p1.atelier import ErreurAtelier

from ..gouvernance import VerrouGouvernance
from . import GestionAteliers


def monter(app: web.Application, ctl) -> GestionAteliers:
    g = GestionAteliers(ctl, ctl.cfg.get("atelier", {}))

    def erreur(exc: Exception, code: int = 400) -> web.Response:
        return web.json_response({"erreur": str(exc), **g.etat()}, status=code)

    async def etat(_):
        return web.json_response(g.etat())

    async def post(request: web.Request) -> web.Response:
        if request.headers.get("X-Atelier") != "1":           # protection inter-sites du prototype
            return web.json_response({"erreur": "Requête refusée."}, status=403)
        action = request.match_info["action"]
        try:
            d = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"erreur": "JSON invalide"}, status=400)
        try:
            if action == "ouvrir":
                return web.json_response(g.ouvrir(pseudonymes=d.get("pseudonymes", []), mode=d.get("mode", "essai"),
                                                  famille=d.get("famille", "claude-opus"), simule=bool(d.get("simule"))))
            a = g.exiger()
            if action == "consigne":
                await _thread(a.consigner, d.get("pseudonyme", ""), d.get("texte", ""), d.get("type", "libre"),
                              int(d.get("nb", 3)), d.get("extraits", []), bool(d.get("confidentielle")))
            elif action == "redemander":
                await _thread(a.redemander, d["cycle"], d.get("motif", ""))
            elif action == "decision":
                a.decider(d["cycle"], int(d["gen"]), int(d["prop"]), d["decision"], d.get("motif", ""))
            elif action == "transformer":
                a.transformer(d["cycle"], int(d["gen"]), int(d["prop"]), d.get("texte", ""))
            elif action == "attribuer":
                a.attribuer(d["cycle"], int(d["gen"]), int(d["prop"]), d.get("etiquette") or None, d.get("credit", ""))
            elif action == "segment":
                a.segment_humain(d.get("pseudonyme", ""), d.get("texte", ""))
            elif action == "reetiqueter":
                a.reetiqueter(int(d["index"]), d["etiquette"])
            elif action == "hors_ligne":
                a.regler_hors_ligne(bool(d.get("actif")))
            elif action == "exporter":
                chemins = a.exporter()
                from ..trace.provenance import en_turtle
                ttl = a.journal.fichier.with_suffix(".prov.ttl")
                ttl.write_text(en_turtle(a.journal.lire()), encoding="utf-8")
                from ..pilotage.depots import consigner
                consigner(ctl.donnees, [*chemins.values(), ttl], "Exports de l'atelier P1 (I-5, registre P1-2, PROV-O)")
                return web.json_response({"export": {**{k: str(v) for k, v in chemins.items()}, "prov": str(ttl)},
                                          **g.etat()})
            else:
                return web.json_response({"erreur": "Introuvable."}, status=404)
            return web.json_response(g.etat())
        except VerrouGouvernance as exc:
            return erreur(exc, 403)
        except ErreurAtelier as exc:
            return erreur(exc)
        except (KeyError, ValueError) as exc:
            return erreur(ValueError(f"Requête invalide ({exc.__class__.__name__} : {exc})"))

    app.router.add_get("/atelier/api/etat", etat)
    app.router.add_post("/atelier/api/{action}", post)
    return g


async def _thread(fn, *a):
    import asyncio
    return await asyncio.to_thread(fn, *a)
