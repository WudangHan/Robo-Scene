"""Contrôleur du partenaire de théâtre : messages « p_* » de l'interface, état de répétition,
incarnation robotique (toujours via la couche de sécurité du pont), journalisation."""
from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web

from . import avatar as avatar_mod, consigne_graduee, copresence, dramaturgie, livret as livret_mod, texte as texte_mod, variations
from .agents import Agents, envelopper
from .analyse_jeu import descripteurs_mouvement, mesure_replique, synthese_passage, trajectoire
from .connaissances import DOMAINES, Index
from .stockage import CONSENTEMENTS, Stockage
from .texte_outils import mots

if TYPE_CHECKING:
    from ..serveur import Controleur

DEFAUTS = {"modele": "claude-sonnet-5-5", "temperature_analyse": 0.3, "temperature_variation": 0.7,
           "incarnation": False, "souffleur_delai_s": 4.0, "fin_replique_silence_ms": 1200,
           "regime": "humain", "ia_active": True}


def masquer(texte: str, niveau: int) -> str:
    """Mémorisation progressive : 0 texte entier ; 1 initiales ; 2 premier mot ; 3 masqué."""
    if niveau <= 0:
        return texte
    if niveau >= 3:
        return "…"
    if niveau == 2:
        m = texte.split()
        return (m[0] + " …") if m else "…"
    return re.sub(r"([A-Za-zÀ-ÿœæ])([A-Za-zÀ-ÿœæ'’\-]*)", lambda m: m.group(1) + "·" * min(3, len(m.group(2))), texte)


class Partenaire:
    def __init__(self, ctl: "Controleur", cfg: dict[str, Any]):
        self.ctl = ctl
        self.cfg = {**DEFAUTS, **(cfg or {})}
        self.index = Index.charger()
        self.livret = livret_mod.Livret.charger()
        self.biblio = texte_mod.Bibliotheque()
        self.repertoire = texte_mod.RepertoireDraCor()
        self.pedagogie_cfg = dict((getattr(ctl, "cfg", {}) or {}).get("pedagogie", {}))
        self.mode = "pedagogie" if self.pedagogie_cfg.get("actif") else "recherche"
        self.stockage = self._stockage()
        self.agents = Agents(self.cfg, self.index, getattr(ctl, "service", None))
        self.incarnation = bool(self.cfg["incarnation"])
        self.repetition: dict[str, Any] | None = None
        self.piece_indexee: str | None = None
        self.cop: dict[str, Any] | None = None

    # ── Utilitaires ─────────────────────────────────────────
    def _limites(self) -> tuple[list[str], list[float], list[float], list[float]]:
        L = self.ctl.limites
        return self.ctl.noms, L.repos, L.min_deg, L.max_deg

    def _dossier_ett(self) -> Path:
        from .stockage import RACINE as RACINE_STOCKAGE
        d = Path(self.pedagogie_cfg.get("dossier") or (RACINE_STOCKAGE / "donnees_ett"))
        return d if d.is_absolute() else RACINE_STOCKAGE / d

    def _stockage(self) -> Stockage:
        """O-10 : en mode pédagogique (É.T.T.), profils et passages sont rangés à part des données de recherche."""
        return Stockage(self._dossier_ett() / "acteurs") if self.mode == "pedagogie" else Stockage()

    def _journal(self, action: str, **d: Any) -> None:
        if self.mode == "pedagogie":
            import json as _json
            f = self._dossier_ett() / "journal_pedagogique.jsonl"
            f.parent.mkdir(parents=True, exist_ok=True)
            with f.open("a", encoding="utf-8") as o:
                o.write(_json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": action, **d},
                                    ensure_ascii=False, default=str) + "\n")
            return
        self.ctl.seance.evenement("partenaire", action=action, **d)

    def _recherche(self, acteur: str | None) -> bool:
        """Aucune donnée ne passe à la recherche en mode pédagogique, même avec un consentement « recherche »."""
        return self.mode == "recherche" and self.stockage.a_consenti(acteur, "recherche")

    async def op_mode(self, m):
        mode = m.get("mode")
        if mode not in ("recherche", "pedagogie"):
            raise ValueError("Mode : recherche ou pedagogie")
        if self.repetition:
            raise ValueError("Terminer la répétition en cours avant de changer de mode")
        self.mode = mode
        self.stockage = self._stockage()
        return {"mode": self.mode, "acteurs": self.stockage.lister()}

    async def _incarner(self, nom: str, images: list[dict[str, Any]], origine: str) -> bool:
        if not self.incarnation or not images:
            return False
        await self.ctl.jouer_images(nom, images, origine)
        return True

    def _indexer_piece(self, piece: dict[str, Any]) -> None:
        """Ajoute la pièce étudiée à la base de connaissances (une entrée par scène)."""
        if self.piece_indexee == piece["id"]:
            return
        base = [p for p in self.index.passages if not p["source"].startswith("piece:")]
        extra = []
        for s in piece["scenes"]:
            reps = [e for e in piece["elements"] if e["scene"] == s["id"]]
            texte = "\n".join(f"{e.get('nom', 'DIDASCALIE')} : {e['texte']}" for e in reps)
            if texte:
                extra.append({"id": f"K9{int(s['id']):04d}" if s["id"].isdigit() else f"K9{len(extra):04d}",
                              "source": f"piece:{piece['id']}", "titre_source": piece["titre"],
                              "section": f"{s['acte']} {s['titre']}".strip(), "page": None,
                              "texte": texte[:6000], "domaines": ["dramaturgie", "jeu"]})
        self.index.__init__(base + extra)
        self.piece_indexee = piece["id"]

    # ── Point d'entrée des messages ─────────────────────────
    async def traiter(self, ws: web.WebSocketResponse, m: dict[str, Any]) -> None:
        op = m["op"]
        f = getattr(self, "op_" + op[2:], None)
        if f is None:
            raise ValueError(f"opération inconnue : {op}")
        rep = await f(m)
        if rep is not None:
            await ws.send_json({"type": op, **rep})

    # ── État général ────────────────────────────────────────
    async def op_etat(self, m):
        return {"moteur_ia": self.agents.moteur, "passages": len(self.index.passages),
                "exercices": len(self.livret.exercices), "pieces": self.biblio.lister(),
                "acteurs": self.stockage.lister(), "consentements": CONSENTEMENTS,
                "emotions": list(variations.EMOTIONS), "styles": list(variations.STYLES),
                "situations": copresence.SITUATIONS, "incarnation": self.incarnation,
                "regime": self.cfg["regime"], "souffleur_delai_s": self.cfg["souffleur_delai_s"],
                "fin_replique_silence_ms": self.cfg["fin_replique_silence_ms"],
                "grille": self.livret.d.get("grille_auto_evaluation", []),
                "domaines": list(DOMAINES),
                "corpus_dracor": ["fre", "shake", "eng", "ger", "ita", "span", "greek", "rom", "rus"],
                "repertoires_externes": texte_mod.REPERTOIRES_EXTERNES, "mode": self.mode}

    async def op_incarnation(self, m):
        self.incarnation = bool(m.get("actif"))
        self._journal("incarnation", actif=self.incarnation)
        await self.ctl.log(f"Incarnation robotique du partenaire {'activée' if self.incarnation else 'désactivée'}")
        return {"incarnation": self.incarnation}

    # ── Formation ───────────────────────────────────────────
    async def op_livret(self, m):
        return {"exercices": self.livret.sommaire(), "annees": self.livret.d.get("annees", {}),
                "calendriers": self.livret.d.get("calendriers", {}),
                "criteres": self.livret.d.get("criteres_evaluation", []), "source": self.livret.d.get("source")}

    async def op_exercice(self, m):
        e = self.livret.par_id.get(m["id"])
        if not e:
            raise KeyError(m["id"])
        return envelopper("formation", {"exercice": e, "accompagnement": livret_mod.accompagnement(e)})

    async def op_seance(self, m):
        faits = set()
        if m.get("acteur"):
            faits = {x["exercice"] for x in self.stockage.profil(m["acteur"])["exercices"]}
        return envelopper("formation", self.livret.planifier(int(m.get("annee", 1)), faits, m.get("graine")))

    async def op_exercice_noter(self, m):
        p = self.stockage.noter_exercice(m["acteur"], m["id"], m.get("note", ""))
        self._journal("exercice", acteur=m["acteur"], exercice=m["id"])
        return {"acteur": p["id"], "exercices": p["exercices"][-20:]}

    async def op_auto_eval(self, m):
        p = self.stockage.auto_evaluer(m["acteur"], m["notes"], m.get("commentaire", ""))
        return {"acteur": p["id"], "auto_evaluations": p["auto_evaluations"][-12:]}

    async def op_accompagner(self, m):
        """Accompagnement robotique d'un exercice : souffle (4 temps), immobile, miroir lent, attentif."""
        mode = m.get("mode", "attentif")
        noms, repos, mn, mx = self._limites()
        idx = variations._indices_articulations(noms)
        ep, te = idx.get("epaule", 1), idx.get("tete", len(noms) - 1)
        tps = float(m.get("temps_s", 4))
        cycles = max(1, min(30, int(m.get("cycles", 6))))
        if mode == "stop":
            self.ctl._arreter_sequence()
            return {"mode": "stop"}
        images: list[dict[str, Any]] = []
        for _ in range(cycles):
            if mode == "souffle":   # inspirer, retenir, expirer, retenir à vide (exercice 1.2)
                haut = list(repos)
                haut[ep] = min(mx[ep], repos[ep] + 18)
                images += [{"deg": haut, "ms": int(tps * 1000)}, {"deg": haut, "ms": int(tps * 1000)},
                           {"deg": list(repos), "ms": int(tps * 1000)}, {"deg": list(repos), "ms": int(tps * 1000)}]
            elif mode == "miroir_lent":
                a = list(repos)
                a[ep] = repos[ep] + 20
                a[te] = repos[te] - 10
                images += [{"deg": [max(mn[i], min(mx[i], x)) for i, x in enumerate(a)], "ms": 3000},
                           {"deg": list(repos), "ms": 3000}]
            elif mode == "immobile":
                images += [{"deg": list(repos), "ms": 4000}]
            else:
                a = list(repos)
                a[te] = repos[te] + 6
                images += [{"deg": a, "ms": 2500}, {"deg": list(repos), "ms": 2500}]
        joue = await self._incarner(f"accompagnement:{mode}", images, "partenaire:formation")
        return {"mode": mode, "joue": joue, "images": len(images),
                "note": None if joue else "Incarnation désactivée : accompagnement affiché seulement."}

    # ── Répertoire et pièces ────────────────────────────────
    async def op_repertoire(self, m):
        r = await asyncio.to_thread(
            self.repertoire.chercher, m.get("corpus", "fre"), m.get("texte", ""), m.get("genre", ""),
            _int(m.get("hommes")), _int(m.get("femmes")), _int(m.get("min_perso")), _int(m.get("max_perso")),
            _int(m.get("annee_min")), _int(m.get("annee_max")))
        return {"corpus": m.get("corpus", "fre"), **r}

    async def op_importer_dracor(self, m):
        p = await asyncio.to_thread(self.repertoire.importer, m["corpus"], m["nom"])
        pid = self.biblio.enregistrer(p)
        self._journal("import", piece=pid, source="dracor")
        await self.ctl.log(f"Pièce importée : {p['titre']} ({p['auteur']}) — licence {p['source'].get('licence') or 'non précisée'}")
        return {"id": pid, "pieces": self.biblio.lister()}

    async def op_importer_texte(self, m):
        texte = str(m.get("texte", ""))
        if len(texte) > 2_000_000:
            raise ValueError("Texte trop long")
        p = texte_mod.lire_texte(texte, m.get("titre", ""), m.get("auteur", ""))
        if not any(e["type"] == "replique" for e in p["elements"]):
            raise ValueError("Aucune réplique reconnue : vérifiez le format « NOM. — réplique » ou « NOM : réplique »")
        p["source"] = {"type": "texte", "licence": m.get("licence", "")}
        pid = self.biblio.enregistrer(p)
        self._journal("import", piece=pid, source="texte")
        return {"id": pid, "pieces": self.biblio.lister(), "repliques": sum(e["type"] == "replique" for e in p["elements"]),
                "personnages": [x["nom"] for x in p["personnages"]]}

    async def op_importer_docx(self, m):
        import base64
        import tempfile
        donnees = base64.b64decode(m["contenu"], validate=True)
        if len(donnees) > 15_000_000:
            raise ValueError("Fichier trop volumineux")
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "piece.docx"
            f.write_bytes(donnees)
            p = texte_mod.lire_docx_piece(f, m.get("titre", ""), m.get("auteur", ""))
        if not any(e["type"] == "replique" for e in p["elements"]):
            raise ValueError("Aucune réplique reconnue dans le document Word")
        pid = self.biblio.enregistrer(p)
        self._journal("import", piece=pid, source="docx")
        return {"id": pid, "pieces": self.biblio.lister(), "repliques": sum(e["type"] == "replique" for e in p["elements"]),
                "personnages": [x["nom"] for x in p["personnages"]]}

    async def op_pieces(self, m):
        return {"pieces": self.biblio.lister()}

    async def op_piece(self, m):
        p = self.biblio.lire(m["id"])
        self._indexer_piece(p)
        return {"piece": p}

    async def op_piece_supprimer(self, m):
        self.biblio.supprimer(m["id"])
        return {"pieces": self.biblio.lister()}

    async def op_exporter_tei(self, m):
        """O-03 : export TEI (aller-retour vérifié par l'importeur) dans donnees/tei/."""
        from ..pilotage.depots import consigner
        from .tei_export import exporter
        p = self.biblio.lire(m["id"])
        xml = exporter(p, licence=m.get("licence"))
        d = self.ctl.donnees / "tei"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{p['id']}.xml"
        f.write_text(xml, encoding="utf-8")
        consigner(self.ctl.donnees, [f], f"Export TEI de « {p['titre']} » (O-03)")
        retour = texte_mod.lire_tei(xml.encode("utf-8"))
        return {"fichier": str(f), "octets": len(xml.encode("utf-8")),
                "aller_retour": {"repliques": sum(1 for e in retour["elements"] if e["type"] == "replique"),
                                 "scenes": len(retour["scenes"]), "personnages": len(retour["personnages"])}}

    async def op_analyser(self, m):
        p = self.biblio.lire(m["id"])
        self._indexer_piece(p)
        return await self.agents.analyser_piece(p)

    async def op_fiche(self, m):
        return envelopper("analyste_piece", {"fiche": dramaturgie.fiche_personnage(self.biblio.lire(m["id"]), m["perso"])})

    # ── Variations émotionnelles ────────────────────────────
    async def op_variations(self, m):
        r = await self.agents.variations(self.biblio.lire(m["piece"]), m["replique"])
        # O-01/O-02 : chaque proposition est aussi rendue aux quatre registres de consigne
        donnees = r.get("donnees", r)
        for v in donnees.get("propositions", []):
            v["consignes_graduees"] = {n: consigne_graduee.graduer(v, variations.decrire(v), n)["texte"]
                                       for n in consigne_graduee.NIVEAUX}
        from ..analyse.juges import statut_regimes
        donnees["validation_regimes"] = statut_regimes(self.ctl.donnees)   # O-02 : statut avant usage analytique
        return r

    def _variation_depuis(self, d: dict[str, Any]) -> dict[str, Any]:
        return variations.variation(d.get("emotion", "neutre"), int(d.get("intensite", 5)), d.get("melange"),
                                    float(d.get("part_melange", 0.4)), d.get("style", "réalisme psychologique"),
                                    d.get("etiquette", ""), d.get("justification", ""), d.get("source", "manuel"),
                                    d.get("effort"))

    async def op_rendu(self, m):
        """Aperçu (et, si l'incarnation est active, exécution) d'une variation sur un texte."""
        v = self._variation_depuis(m["variation"])
        regime = m.get("regime", self.cfg["regime"])
        voix = variations.rendu_voix(m["texte"], v, regime)
        noms, repos, mn, mx = self._limites()
        geste = variations.rendu_geste(v, voix["duree_estimee_ms"], noms, repos, mn, mx, regime, m.get("graine", ""))
        joue = await self._incarner(f"variation:{v['etiquette']}", geste, "partenaire:variation") if m.get("jouer") else False
        self._journal("variation", etiquette=v["etiquette"], regime=regime, joue=joue)
        return envelopper("variation", {"variation": v, "description": variations.decrire(v), "voix": voix,
                                        "geste": geste, "joue": joue})

    # ── Répétiteur ──────────────────────────────────────────
    async def op_repet_demarrer(self, m):
        p = self.biblio.lire(m["piece"])
        self._indexer_piece(p)
        roles = set(m.get("roles") or [])
        if not roles:
            raise ValueError("Choisissez au moins un rôle pour l'acteur")
        scenes = set(m.get("scenes") or [s["id"] for s in p["scenes"]])
        niveau = max(0, min(3, int(m.get("niveau", 0))))
        regime = m.get("regime", self.cfg["regime"])
        mode_var = m.get("variation_mode", "lecture")  # lecture | cycle | fixe | aucune
        acteur = m.get("acteur") or None
        passes = len(self.stockage.passages(acteur, p["id"], "+".join(sorted(roles)))) if acteur else 0
        fixe = self._variation_depuis(m["variation"]) if mode_var == "fixe" and m.get("variation") else None
        style = m.get("style", "réalisme psychologique")
        precision = consigne_graduee.niveau(m.get("precision_consigne", 4))   # O-01 : registre consigné
        items = []
        for e in p["elements"]:
            if e["scene"] not in scenes:
                continue
            if e["type"] == "didascalie":
                items.append({"id": e["id"], "type": "didascalie", "texte": e["texte"]})
                continue
            acteur_dit = e["perso"] in roles
            it = {"id": e["id"], "type": "replique", "nom": e["nom"], "perso": e["perso"], "acteur": acteur_dit,
                  "didascalies": e.get("didascalies", [])}
            if acteur_dit:
                it["affiche"] = masquer(e["texte"], niveau)
                it["souffle"] = " ".join(e["texte"].split()[:4])
                it["mots"] = len(mots(e["texte"]))
                if m.get("consignes"):
                    pr = variations.propositions(e["texte"], e.get("didascalies"))["propositions"]
                    vc = pr[passes % len(pr)]
                    it["consigne"] = consigne_graduee.graduer(vc, variations.decrire(vc), precision)["texte"]
            else:
                it["texte"] = e["texte"]
                if mode_var == "aucune":
                    v = variations.variation("neutre", 1, style=style, etiquette="lecture blanche")
                elif fixe:
                    v = fixe
                else:
                    pr = variations.propositions(e["texte"], e.get("didascalies"), e.get("didascalies_types"))["propositions"]
                    v = pr[passes % len(pr)] if mode_var == "cycle" else pr[0]
                    v = {**v, "style": style}
                it["variation"] = v
                it["effort"] = variations.decrire(v)["effort"]
                it["voix"] = variations.rendu_voix(e["texte"], v, regime,
                                                   variations.indices(e["texte"], e.get("didascalies"))["marques"])
            items.append(it)
        if not any(i.get("acteur") for i in items):
            raise ValueError("Le rôle choisi ne parle pas dans les scènes retenues")
        rid = f"R{int(time.time())}"
        self.repetition = {"id": rid, "piece": p["id"], "titre": p["titre"], "roles": sorted(roles),
                           "acteur": acteur, "niveau": niveau, "regime": regime, "variation_mode": mode_var,
                           "style": style, "passage": passes + 1, "mesures": [], "mouvement": [],
                           "textes": {e["id"]: e["texte"] for e in p["elements"]}, "debut": time.time(),
                           "perturbation": m.get("perturbation"), "precision_consigne": precision}
        self._journal("repetition", etape="debut", id=rid, piece=p["id"], roles=sorted(roles), niveau=niveau,
                      regime=regime, variation_mode=mode_var, passage=passes + 1, precision_consigne=precision,
                      acteur=acteur if self._recherche(acteur) else None)
        return envelopper("repetiteur", {"repetition": rid, "titre": p["titre"], "passage": passes + 1,
                                         "items": items, "souffleur_delai_s": float(m.get("souffleur_delai_s",
                                                                                          self.cfg["souffleur_delai_s"])),
                                         "fin_replique_silence_ms": self.cfg["fin_replique_silence_ms"],
                                         "licence": p.get("source", {}).get("licence", "")})

    async def op_repet_geste(self, m):
        """Le robot incarne la réplique qu'il donne (geste borné, via la couche de sécurité)."""
        r = self.repetition
        if not r:
            return None
        v = self._variation_depuis(m["variation"])
        noms, repos, mn, mx = self._limites()
        geste = variations.rendu_geste(v, int(m.get("duree_ms", 2500)), noms, repos, mn, mx, r["regime"], m["replique"])
        joue = await self._incarner(f"replique:{m['replique']}", geste, "partenaire:repetiteur")
        return {"replique": m["replique"], "joue": joue}

    async def op_repet_mesure(self, m):
        r = self.repetition
        if not r or m.get("repetition") != r["id"]:
            raise ValueError("Aucune répétition en cours")
        if m.get("transcription") and not self.stockage.a_consenti(r["acteur"], "transcription"):
            m = {**m, "transcription": None}
        mesure = {"replique": m["replique"], **mesure_replique(r["textes"].get(m["replique"], ""), m)}
        r["mesures"].append(mesure)
        return {"mesure": mesure}

    async def op_mouvement(self, m):
        """O-04 : descripteurs de mouvement seulement (G-06) ; les points de pose reçus ne sont ni conservés ni
        journalisés, et tout résultat qui ressemblerait à des données brutes est refusé par le garde-fou."""
        from ..gouvernance.biometrie import nettoyer, verifier_config
        verifier_config(self.cfg)
        r = self.repetition
        d = nettoyer(descripteurs_mouvement(m.get("images", [])))
        m.pop("images", None)
        if r and self.stockage.a_consenti(r["acteur"], "camera") and "erreur" not in d:
            r["mouvement"].append({"replique": m.get("replique"), **d})
        return {"descripteurs": d}

    async def op_repet_terminer(self, m):
        r, self.repetition = self.repetition, None
        if not r:
            return None
        self.ctl._arreter_sequence()
        passage = {"repetition": r["id"], "piece": r["piece"], "roles": r["roles"], "niveau": r["niveau"],
                   "regime": r["regime"], "variation_mode": r["variation_mode"], "style": r["style"],
                   "perturbation": r.get("perturbation"), "precision_consigne": r.get("precision_consigne"),
                   "duree_s": round(time.time() - r["debut"], 1),
                   "mesures": r["mesures"], "mouvement": r["mouvement"],
                   "synthese": synthese_passage(r["mesures"]), "interrompu": bool(m.get("interrompu"))}
        conserve, traj = False, None
        if r["acteur"]:
            try:
                passages = self.stockage.ajouter_passage(r["acteur"], r["piece"], "+".join(r["roles"]), passage)
                conserve, traj = True, trajectoire(passages)
            except PermissionError:
                pass
        self._journal("repetition", etape="fin", id=r["id"], synthese=passage["synthese"], conserve=conserve,
                      mesures=r["mesures"] if self._recherche(r["acteur"]) else None)
        return {"passage": {k: passage[k] for k in ("synthese", "duree_s", "interrompu")},
                "conserve": conserve, "trajectoire": traj, "retour": self.agents.retour_jeu(passage, traj)}

    async def op_trajectoire(self, m):
        ps = self.stockage.passages(m["acteur"], m["piece"], "+".join(sorted(m["roles"])))
        return {"trajectoire": trajectoire(ps) if ps else None,
                "passages": [{"numero": p["numero"], "ts": p["ts"], "synthese": p["synthese"],
                              "variation_mode": p["variation_mode"], "regime": p["regime"],
                              "perturbation": p.get("perturbation")} for p in ps]}

    # ── Acteurs et consentements ────────────────────────────
    async def op_acteurs(self, m):
        return {"acteurs": self.stockage.lister()}

    async def op_acteur_creer(self, m):
        p = self.stockage.creer(m["pseudonyme"], int(m.get("annee", 1)))
        return {"acteur": p, "acteurs": self.stockage.lister()}

    async def op_acteur(self, m):
        return {"acteur": self.stockage.profil(m["id"])}

    async def op_consentir(self, m):
        p = self.stockage.consentir(m["acteur"], m["cle"], bool(m["accorde"]))
        self._journal("consentement", acteur=p["id"], cle=m["cle"], accorde=bool(m["accorde"]))
        return {"acteur": p, "acteurs": self.stockage.lister()}

    async def op_acteur_retirer(self, m):
        self.stockage.retirer(m["id"])
        self._journal("retrait", acteur="(retiré)")
        await self.ctl.log("Données d'un acteur effacées (droit de retrait)")
        return {"acteurs": self.stockage.lister()}

    # ── Conseiller ──────────────────────────────────────────
    async def op_question(self, m):
        q = str(m.get("texte", "")).strip()[:800]
        if not q:
            return None
        rep = await self.agents.conseiller(q, m.get("domaines") or None)
        self._journal("question", question=q, mode=rep.get("mode"), citations=rep.get("citations"))
        return rep

    # ── Partition de coprésence ─────────────────────────────
    async def op_cop_plan_type(self, m):
        return {"plan": copresence.plan_type_cas_a()}

    async def op_cop_sceller(self, m):
        e = copresence.sceller(m["plan"])
        self.ctl.seance.meta.setdefault("plans_scelles", []).append({"empreinte": e, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
        self.ctl.seance.sauvegarder()
        self._journal("plan_scelle", empreinte=e)
        await self.ctl.log(f"Plan de perturbations scellé : {e[:12]}…")
        return {"empreinte": e}

    async def op_cop_desceller(self, m):
        d = copresence.desceller(m["empreinte"])
        self._journal("plan_descelle", empreinte=m["empreinte"], integre=d["integre"])
        return d

    async def op_cop_jouer(self, m):
        plan = copresence.charger(m["empreinte"])["plan"] if m.get("empreinte") else None
        noms, repos, mn, mx = self._limites()
        idx = variations._indices_articulations(noms)
        images = copresence.generer(m["situation"], float(m.get("duree_s", 60)), float(m.get("tempo", 60)),
                                    repos, mn, mx, idx, plan)
        for im in images:
            if im["perturbation"]:
                self._journal("perturbation", situation=m["situation"], t=im["t"], code=im["perturbation"],
                              empreinte=(m.get("empreinte") or "")[:16])
        self._journal("situation", situation=m["situation"], duree_s=m.get("duree_s"), tempo=m.get("tempo"),
                      empreinte=(m.get("empreinte") or "")[:16] or None)
        joue = await self._incarner(f"coprésence:{m['situation']}", images, "partenaire:copresence")
        # L'interface de plateau ne reçoit pas le détail des perturbations (plan scellé)
        return {"situation": m["situation"], "description": copresence.SITUATIONS[m["situation"]],
                "joue": joue, "duree_s": round(sum(i["ms"] for i in images) / 1000, 1)}

    # ── Robot virtuel ───────────────────────────────────────
    async def op_avatar_etat(self, m):
        dispo = self.agents.service is not None and self.agents.service.disponible("commande", domaine="robot")
        return {"moteur": self.agents.service.moteur("commande", domaine="robot") if dispo else "déterministe",
                "schema_version": avatar_mod.schema().get("version")}

    async def op_avatar_interpreter(self, m):
        service = self.agents.service if (self.agents.service is not None and
                                          self.agents.service.disponible("commande", domaine="robot")) else None
        r = await avatar_mod.interpreter(service, m.get("texte", ""), m.get("etat"))
        self._journal("avatar_interpretation", texte=r["texte"], moteur=r["moteur"], confiance=r["confiance"],
                      actions=r["actions"], rejets=[x["motif"] for x in r["rejets"]], justification=r["justification"],
                      trace=r["trace"])
        return r

    async def op_avatar_journal(self, m):
        ev = m.get("evenement") if isinstance(m.get("evenement"), dict) else {}
        propre = {k: ev[k] for k in ("texte", "origine", "source", "decision", "confiance") if k in ev and isinstance(ev[k], (str, int, float))}
        actions, _ = avatar_mod.valider(ev.get("actions"))
        propre["actions"] = actions[:40]
        if isinstance(ev.get("ignores"), list):
            propre["ignores"] = [str(x)[:200] for x in ev["ignores"][:20]]
        if "texte" in propre:
            propre["texte"] = str(propre["texte"])[:600]
        self._journal("avatar_directive", **propre)
        return None


def _int(v: Any) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None

