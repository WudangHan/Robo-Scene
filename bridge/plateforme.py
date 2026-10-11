"""Montage de la plateforme intégrée sur l'application du pont (console ROBO-SCÈNE).

Toutes les routes JSON d'écriture exigent l'en-tête « X-Plateforme: 1 » : un en-tête personnalisé force une
requête de contrôle préalable que le pont ne valide pas pour une origine étrangère, ce qui ferme la porte aux
requêtes intersites ; la console est par ailleurs servie sur 127.0.0.1 par défaut.

Pages : /atelier, /scene, /spectateur, /recherche, /gouvernance, /regie, /surtitres, /tableau-public.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiohttp import web

from .gouvernance import VerrouGouvernance
from .securite import CommandeRefusee

RACINE = Path(__file__).resolve().parent.parent
PAGES = ("atelier", "scene", "spectateur", "recherche", "gouvernance", "regie", "surtitres", "tableau-public")
REFUS = (CommandeRefusee, VerrouGouvernance, ValueError, KeyError, FileNotFoundError, FileExistsError, PermissionError)


def _json(fn: Callable[[web.Request, dict], Awaitable[Any]]):
    async def gestion(request: web.Request) -> web.Response:
        if request.method == "POST":
            if request.headers.get("X-Plateforme") != "1":
                return web.json_response({"erreur": "Requête refusée (en-tête X-Plateforme manquant)."}, status=403)
            try:
                d = await request.json() if request.can_read_body else {}
            except json.JSONDecodeError:
                return web.json_response({"erreur": "JSON invalide"}, status=400)
            if not isinstance(d, dict):
                return web.json_response({"erreur": "Objet JSON attendu"}, status=400)
        else:
            d = dict(request.query)
        try:
            r = await fn(request, d)
            return web.json_response(r, dumps=lambda o: json.dumps(o, ensure_ascii=False, default=str))
        except VerrouGouvernance as exc:
            return web.json_response({"erreur": str(exc), "verrou": True}, status=409)
        except REFUS as exc:
            return web.json_response({"erreur": str(exc) or type(exc).__name__}, status=400)
    return gestion


def _thread(fn, *a, **k):
    return asyncio.to_thread(fn, *a, **k)


def monter(app: web.Application, ctl) -> None:
    from .accessibilite import Surtitrage
    from .atelier import web as atelier_web
    from .pilotage import depots, fonctions, rapports
    from .pilotage.regie import Regie
    from .scene import Scene, simuler
    from .spectateur import web as spectateur_web
    from .veille import Veille

    cfg = ctl.cfg
    ctl.racine = RACINE
    ctl.scene = Scene(ctl, cfg.get("scene", {}))
    ctl.surtitrage = Surtitrage(ctl)
    pil = cfg.get("pilotage", {})
    ctl.regie = Regie(pil.get("dossier_projet") or None, ctl.donnees / "pilotage" / "journal_regie.jsonl")
    ctl.veille = Veille(ctl.donnees)
    atelier_web.monter(app, ctl)
    ctl.spectateur = spectateur_web.monter(app, ctl)
    r = app.router

    async def au_demarrage(_app):
        ctl.scene.loop = asyncio.get_running_loop()
        sp = cfg.get("spectateur", {})
        if sp.get("questionnaires_au_demarrage"):
            await spectateur_web.demarrer_public(ctl.spectateur)
        d = pil.get("dossier_projet")
        if d and pil.get("inventaire_mensuel", True) and Path(d).exists() and not rapports.inventaire_du_mois_fait(Path(d)):
            async def inventaire():
                res = await _thread(rapports.lancer_inventaire, Path(d))
                await ctl.log(f"Inventaire mensuel (P-02) : code {res['code']}")
            asyncio.create_task(inventaire())

    async def a_l_arret(_app):
        await spectateur_web.arreter_public(ctl.spectateur)
        ctl.spectateur.arreter()

    app.on_startup.append(au_demarrage)
    app.on_cleanup.append(a_l_arret)

    for nom in PAGES:
        r.add_get(f"/{nom}", _page(f"{nom}.html"))

    # ── Vue d'ensemble ──────────────────────────────────────
    @_json
    async def etat(_req, _d):
        return {"fonctions": fonctions.table(), "gouvernance": ctl.gouv.resume(), "modeles": ctl.service.resume(),
                "seance": ctl.seance.id, "flotte": [x.resume() for x in ctl.robots.values()], "actif": ctl.actif_id,
                "regle_ia": ctl.ia_cfg["regle"], "scene": {"chargee": ctl.scene.conduite is not None},
                "spectateur": {"p3": bool(ctl.spectateur.p3), "passation": bool(ctl.spectateur.passation)}}
    r.add_get("/api/plateforme", etat)
    r.add_get("/api/fonctions", _json(lambda _r, _d: _async(fonctions.table())))

    # ── Scène (R-05, R-06, O-05, O-06, O-11, O-12) ──────────
    @_json
    async def scene_etat(_req, _d):
        return ctl.scene.etat()

    @_json
    async def scene_action(req, d):
        a, s = req.match_info["action"], ctl.scene
        if a == "charger":
            return s.charger(texte=d["texte"]) if d.get("texte") else s.charger(chemin=d.get("chemin"))
        if a == "go":
            return s.go()
        if a == "retour":
            return s.retour()
        if a == "arret":
            s.arret_logiciel()
            return s.etat()
        if a == "reprendre":
            return s.reprendre()
        if a == "apercu":
            return s.apercu()
        if a == "simuler":
            return await _thread(simuler, s)
        if a == "echo":
            return await echo(d)
        raise KeyError(f"Action inconnue : {a}")

    async def echo(d):
        """R-06 (D09, option A) : le robot répond par un geste CHOISI dans la bibliothèque fermée, jamais par
        imitation ; le choix humain est tracé comme opération de sélection."""
        stimulus, geste = str(d.get("stimulus", "")).strip(), str(d.get("geste", "")).strip()
        par = str(d.get("par") or ctl.pseudo_operatrice)
        rid = d.get("robot") or ctl.actif_id
        rob = ctl.robots.get(rid)
        if rob is None or not geste or not stimulus:
            raise ValueError("Stimulus, geste et robot requis")
        candidats = rob.biblio.lister()
        if geste not in candidats:
            raise CommandeRefusee(f"« {geste} » n'appartient pas à la bibliothèque fermée de {rid}")
        cycle = f"ECHO-{ctl.seance.id}-{len(ctl.trace.lire()) + 1}"
        ctl._tracer("consigne", ("personne", par), {"texte": stimulus, "mode": "echo", "robot": rid}, cycle)
        ctl._tracer("selection", ("personne", par), {"decision": "retenue", "geste": geste, "robot": rid,
                                                     "candidats": len(candidats),
                                                     "motif": str(d.get("motif") or "écho (D09, option A)")}, cycle)
        await ctl.jouer_sequence(geste, f"echo:{cycle}", rid)
        return {"cycle": cycle, "geste": geste, "robot": rid}

    r.add_get("/api/scene", scene_etat)
    r.add_post("/api/scene/{action}", scene_action)

    # ── Saisies de traçabilité depuis les pages (N-07, N-08) ─
    @_json
    async def saisie(req, d):
        from .trace import saisies
        a = req.match_info["action"]
        if a == "de_tete":
            ev = saisies.transformation_de_tete(ctl.trace, pseudonyme=d.get("pseudonyme") or ctl.pseudo_operatrice,
                                                description=d.get("description", ""), cycle=d.get("cycle"),
                                                version=d.get("version"), module=d.get("module", "SCENE"))
        elif a == "autre":
            ev = saisies.autre(ctl.trace, pseudonyme=d.get("pseudonyme") or ctl.pseudo_operatrice,
                               categorie=d.get("categorie", ""), description=d.get("description", ""))
        else:
            raise KeyError(a)
        return {"evenement": ev["id"]}
    r.add_post("/api/trace/{action}", saisie)

    # ── Régie (P-01 à P-04) ─────────────────────────────────
    @_json
    async def regie_lire(_req, _d):
        return {**ctl.regie.lire(), "depots": depots.lister(ctl.donnees)}

    @_json
    async def regie_action(req, d):
        a = req.match_info["action"]
        if a == "tache":
            return ctl.regie.mettre_a_jour_tache(d["id"], statut=d.get("statut"), livrable=d.get("livrable"),
                                                 note=d.get("note"), par=d.get("par", ""))
        if a == "demander":
            return await ctl.regie.demander(ctl.service, str(d.get("question", ""))[:1000])
        if a == "revue_trimestrielle":
            f = await _thread(rapports.revue_trimestrielle, ctl)
            depots.consigner(ctl.donnees, [f], "Revue trimestrielle de la politique d'IA (P-04)")
            return {"fichier": str(f), "contenu": f.read_text(encoding="utf-8")}
        if a == "inventaire":
            dp = pil.get("dossier_projet")
            if not dp:
                raise ValueError("Configurer [pilotage] dossier_projet")
            return await _thread(rapports.lancer_inventaire, Path(dp))
        raise KeyError(a)
    r.add_get("/api/regie", regie_lire)
    r.add_post("/api/regie/{action}", regie_action)

    # ── Gouvernance (G-01 à G-07, R-08) ─────────────────────
    @_json
    async def gouv_lire(_req, _d):
        from .gouvernance import conservation
        ctl.gouv.recharger()
        return {**ctl.gouv.resume(), "incidents": ctl.gouv.incidents.lister()[-50:],
                "conservation": conservation.etat(RACINE, RACINE / "gouvernance" / "conservation.yaml")}

    @_json
    async def gouv_action(req, d):
        from .gouvernance import conservation
        a = req.match_info["action"]
        if a == "incident_clore":
            return ctl.gouv.incidents.clore(d["id"], gravite=d.get("gravite", ""), cause=d.get("cause", ""),
                                            mesures=d.get("mesures", ""), par=d.get("par", ""),
                                            personnes_blessees=bool(d.get("personnes_blessees")))
        if a == "decision_valider":
            return ctl.gouv.decisions.valider(d["id"], validateur=d.get("par", ""), decision=d.get("decision", ""),
                                              motif=d.get("motif", ""))
        if a == "conservation_inventaire":
            return {"a_detruire": conservation.purger(RACINE, RACINE / "gouvernance" / "conservation.yaml",
                                                      ctl.donnees / "gouvernance" / "destructions.jsonl", executer=False)}
        if a == "conservation_purger":
            if d.get("confirmation") != "DÉTRUIRE" or not str(d.get("par", "")).strip():
                raise ValueError("Destruction irréversible : confirmation « DÉTRUIRE » et pseudonyme requis")
            return {"detruits": conservation.purger(RACINE, RACINE / "gouvernance" / "conservation.yaml",
                                                    ctl.donnees / "gouvernance" / "destructions.jsonl",
                                                    executer=True, par=d["par"])}
        raise KeyError(a)
    r.add_get("/api/gouvernance", gouv_lire)
    r.add_post("/api/gouvernance/{action}", gouv_action)

    # ── Analyse (Q-01 à Q-05, O-02) ─────────────────────────
    @_json
    async def analyse_action(req, d):
        from . import analyse
        from .analyse import entretiens
        from .analyse.juges import EtudeJuges
        a = req.match_info["action"]
        if a == "lancer":
            res = await _thread(analyse.lancer, ctl.donnees, ctl.racine_corpus, exclues=d.get("exclues") or [],
                                seances_par_representation=d.get("seances_par_representation") or {},
                                codeur=d.get("codeur"), exclure_reconstituees=bool(d.get("exclure_reconstituees")))
            out = Path(res["dossier"])
            depots.consigner(ctl.donnees, sorted(p for p in out.iterdir() if p.is_file()), "Analyse Q-01 à Q-05")
            return {"dossier": res["dossier"], "rapport": (out / "rapport.md").read_text(encoding="utf-8"),
                    "resultats": res["resultats"]}
        if a == "segmenter":
            return {"segments": entretiens.segmenter(d.get("texte", ""), d.get("pseudonyme", ""), d.get("document", ""))}
        if a == "suggerer":
            return await _thread(entretiens.suggerer, ctl.service, d["segment"], entretiens.livre())
        if a == "coder":
            c = entretiens.Codage(ctl.donnees / "analyse", d.get("codeur", ""))
            return c.coder(d["segment"], d.get("codes", []), statut=d.get("statut", "valide"), memo=d.get("memo", ""),
                           connus={x["code"] for x in entretiens.livre()})
        if a == "accord":
            ca = entretiens.Codage(ctl.donnees / "analyse", d["codeur_a"]).lire()
            cb = entretiens.Codage(ctl.donnees / "analyse", d["codeur_b"]).lire()
            return entretiens.accord(ca, cb, [x["code"] for x in entretiens.livre()])
        if a == "livre":
            return {"codes": entretiens.livre()}
        if a.startswith("juges_"):
            e = EtudeJuges(ctl.donnees, d.get("etude", ""))
            if a == "juges_definir":
                return e.definir(d["stimuli"], d["categories"])
            if a == "juges_sequence":
                return {"sequence": e.sequence(d["juge"])}
            if a == "juges_coter":
                e.coter(d["juge"], d["stimulus"], d["emotion"], d.get("intensite"))
                return {"ok": True}
            if a == "juges_resultats":
                return e.resultats()
        raise KeyError(a)
    r.add_post("/api/analyse/{action}", analyse_action)

    # ── Surtitres et audiodescription (O-06) ────────────────
    @_json
    async def surtitres_lire(_req, _d):
        return ctl.surtitrage.etat()

    @_json
    async def surtitres_action(req, d):
        a, st = req.match_info["action"], ctl.surtitrage
        if a == "importer":
            return st.importer_conduite()
        if a == "proposer":
            return await st.proposer(d.get("ids", []), d.get("langue", "en"),
                                     confidentielle=bool(d.get("confidentielle")), par=d.get("par", ""))
        if a == "valider":
            return st.valider(d["id"], d.get("langue", "en"), decision=d.get("decision", ""), par=d.get("par", ""),
                              texte=d.get("texte"))
        if a == "saisir":
            return st.saisir(d["id"], d.get("langue", "en"), d.get("texte", ""), d.get("par", ""))
        if a == "webvtt":
            f = st.webvtt(d.get("langue", "en"), d.get("type", "surtitre"))
            depots.consigner(ctl.donnees, [f], "Export WebVTT validé (O-06)")
            return {"fichier": str(f), "contenu": f.read_text(encoding="utf-8")}
        raise KeyError(a)
    r.add_get("/api/surtitres", surtitres_lire)
    r.add_post("/api/surtitres/{action}", surtitres_action)

    # ── Veille (O-08) ───────────────────────────────────────
    @_json
    async def veille_lire(_req, d):
        return {"notices": ctl.veille.lister(d.get("statut")), "bibliographie": ctl.veille.bibliographie()}

    @_json
    async def veille_action(req, d):
        a = req.match_info["action"]
        if a == "chercher":
            return await _thread(ctl.veille.chercher, str(d.get("requete", ""))[:300], d.get("sources"),
                                 int(d.get("n", 10)))
        if a == "verifier":
            return ctl.veille.verifier(d["cle"], statut=d.get("statut", ""), par=d.get("par", ""), note=d.get("note", ""))
        raise KeyError(a)
    r.add_get("/api/veille", veille_lire)
    r.add_post("/api/veille/{action}", veille_action)

    # ── Diffusion (O-07, O-09) ──────────────────────────────
    @_json
    async def diffusion_action(req, d):
        from .diffusion import c2pa, tableau_public
        a = req.match_info["action"]
        if a == "tableau_preparer":
            return tableau_public.preparer(ctl.donnees)
        if a == "tableau_publier":
            f = tableau_public.publier(ctl.donnees, RACINE / "web", d.get("par", ""))
            depots.consigner(ctl.donnees, [f], "Tableau public des indicateurs agrégés (O-09)")
            return {"fichier": str(f)}
        if a == "c2pa":
            f = (ctl.donnees / str(d.get("fichier", ""))).resolve()
            if ctl.donnees.resolve() not in f.parents:
                raise PermissionError("Fichier hors du dossier de données")
            dc = cfg.get("diffusion", {})
            res = await _thread(c2pa.produire, f, nature=d.get("nature", ""), titre=d.get("titre", ""),
                                auteurs=d.get("auteurs") or [], description_ia=d.get("description_ia"),
                                certificat=dc.get("c2pa_certificat"), cle=dc.get("c2pa_cle"))
            depots.consigner(ctl.donnees, [Path(res["fichier"])], f"Provenance C2PA ({res['mode']}) (O-07)")
            return res
        raise KeyError(a)
    r.add_post("/api/diffusion/{action}", diffusion_action)

    # ── Serveur public des questionnaires (S-05) ────────────
    @_json
    async def public_action(req, _d):
        a = req.match_info["action"]
        if a == "demarrer":
            if not ctl.spectateur.serveur_public:
                await spectateur_web.demarrer_public(ctl.spectateur)
        elif a == "arreter":
            await spectateur_web.arreter_public(ctl.spectateur)
        else:
            raise KeyError(a)
        return ctl.spectateur.etat()
    r.add_post("/api/questionnaires/{action}", public_action)


async def _async(v):
    return v


def _page(nom: str):
    async def servir(_: web.Request) -> web.StreamResponse:
        p = RACINE / "web" / nom
        if not p.exists():
            raise web.HTTPNotFound(text=f"Page {nom} absente")
        return web.FileResponse(p)
    return servir
