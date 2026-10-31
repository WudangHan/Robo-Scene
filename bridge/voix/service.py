"""Service vocal hybride : moteurs neuronaux dirigeables, cache local, pré-rendu, repli local.

Ordre de décision pour chaque réplique :
1. régime « machinique » ou style muet : aucune voix neuronale (la voie non anthropomorphe reste celle du
   navigateur) ;
2. routeur de sensibilité D03 (le même que pour les modèles de langage) : au moindre motif, seuls les moteurs
   LOCAUX (Piper) sont admis ; à défaut, repli sur la voix du navigateur limitée aux voix locales ;
3. sinon, les moteurs dans l'ordre de config.toml [voix].ordre, en sautant ceux qui ne sont pas disponibles
   (clé absente, voix non configurée) ; une erreur de réseau ou de quota fait passer au suivant ;
4. le son est rangé dans donnees/voix/cache sous une clé qui dépend du texte, de la partition, du moteur et de
   la voix : une réplique déjà rendue ne coûte plus rien et sonne toujours pareil (séances comparables), sauf si
   l'opératrice demande une « nouvelle prise ».

Chaque rendu est consigné (moteur, modèle, voix, commande envoyée, durée) dans les métadonnées du cache et
dans le journal de séance : la provenance de chaque voix entendue reste traçable (G.5, N-05).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from . import partition as P
from .moteurs import CLASSES, Audio, ErreurVoix, Moteur

# Voix proposées par défaut (modifiables dans config.toml). Les voix Azure fr-CA sont celles de la liste de
# l'éditeur ; les identifiants ElevenLabs dépendent du compte (bibliothèque de voix) et restent à choisir.
DEFAUTS: dict[str, Any] = {
    "ordre": ["elevenlabs", "azure", "openai", "piper"],
    "langue": "fr-CA",
    "dossier_cache": "voix/cache",
    "prerendu": True,
    "elevenlabs": {"modele": "eleven_v3", "voix_partenaire": [], "voix_avatar": [], "direction": {}},
    "azure": {"region": "canadacentral",
              "voix_partenaire": ["fr-CA-ThierryNeural", "fr-CA-SylvieNeural", "fr-CA-AntoineNeural", "fr-CA-JeanNeural"],
              "voix_avatar": ["fr-CA-AntoineNeural"],
              "direction": {"mathilde": "fr-CA-SylvieNeural", "etienne": "fr-CA-ThierryNeural",
                            "sophie": "fr-FR-DeniseNeural", "gabriel": "fr-CA-JeanNeural",
                            "claire": "fr-FR-EloiseNeural", "laurent": "fr-FR-HenriNeural"}},
    "openai": {"modele": "gpt-4o-mini-tts", "accent": "québécois",
               "voix_partenaire": ["ash", "coral", "onyx", "sage"], "voix_avatar": ["ash"],
               "direction": {"mathilde": "coral", "etienne": "onyx", "sophie": "nova", "gabriel": "sage",
                             "claire": "shimmer", "laurent": "ash"}},
    "piper": {"voix_partenaire": [], "dossier_modeles": "~/.local/share/piper"},
}
NOM_FICHIER = re.compile(r"^[0-9a-f]{64}\.(wav|mp3)$")


def _fusion(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = _fusion(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


class ServiceVoix:
    def __init__(self, cfg: dict[str, Any] | None, dossier_donnees: Path, routeur=None,
                 journal: Callable[..., None] | None = None, moteurs: dict[str, Moteur] | None = None):
        self.cfg = _fusion(DEFAUTS, cfg or {})
        self.routeur = routeur
        self.journal = journal or (lambda *a, **k: None)
        d = Path(self.cfg["dossier_cache"])
        self.cache = d if d.is_absolute() else Path(dossier_donnees) / d
        self.fichier_distribution = self.cache.parent / "distribution.json"
        self.moteurs: dict[str, Moteur] = moteurs or {n: CLASSES[n](self.cfg.get(n, {})) for n in CLASSES}
        self.ordre = [n for n in self.cfg["ordre"] if n in self.moteurs]
        self.erreurs: dict[str, str] = {}
        self._verrous: dict[str, asyncio.Lock] = {}

    # ── État et distribution ─────────────────────────────────────────────────────────────────────────
    def etat(self) -> dict[str, Any]:
        ms = []
        for n in self.ordre:
            ok, motif = self.moteurs[n].disponible()
            ms.append({"id": n, "libelle": self.moteurs[n].libelle, "disponible": ok, "motif": motif,
                       "distant": self.moteurs[n].distant, "derniere_erreur": self.erreurs.get(n, "")})
        actif = next((m["id"] for m in ms if m["disponible"]), None)
        return {"moteurs": ms, "actif": actif, "langue": self.cfg["langue"], "distribution": self.distribution(),
                "repli": "voix du navigateur, une phrase par énoncé"}

    def distribution(self) -> dict[str, Any]:
        try:
            return json.loads(self.fichier_distribution.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def distribuer(self, personnage: str, moteur: str, voix: str) -> dict[str, Any]:
        """Fixe la voix d'un personnage pour un moteur (« » pour revenir à l'attribution automatique)."""
        if moteur not in self.moteurs:
            raise ValueError(f"moteur inconnu : {moteur}")
        d = self.distribution()
        d.setdefault(personnage, {})
        if voix:
            d[personnage][moteur] = str(voix)[:120]
        else:
            d[personnage].pop(moteur, None)
        self.fichier_distribution.parent.mkdir(parents=True, exist_ok=True)
        self.fichier_distribution.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        return d

    def _voix(self, moteur: Moteur, role: str, personnage: str, indice: int, profil: str | None) -> str:
        impose = (self.distribution().get(personnage) or {}).get(moteur.nom) if personnage else None
        return impose or moteur.voix_pour(role, indice, profil)

    # ── Cache ────────────────────────────────────────────────────────────────────────────────────────
    def _cle(self, moteur: Moteur, voix: str, part: dict[str, Any], prise: int) -> str:
        brut = json.dumps({"e": moteur.empreinte(), "v": voix, "p": part["phrases"], "emo": part["emotion"],
                           "i": part["intensite"], "m": part.get("melange"), "s": part.get("style"),
                           "pers": part.get("personnage"), "prise": prise, "version": P.VERSION},
                          ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(brut.encode("utf-8")).hexdigest()

    def chemin(self, nom: str) -> Path | None:
        if not NOM_FICHIER.match(nom or ""):
            return None
        p = self.cache / nom
        return p if p.exists() else None

    def _depuis_cache(self, cle: str) -> dict[str, Any] | None:
        meta = self.cache / f"{cle}.json"
        if not meta.exists():
            return None
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
        except ValueError:
            return None
        return m if (self.cache / m["fichier"]).exists() else None

    def _ranger(self, cle: str, a: Audio, part: dict[str, Any], motifs: list[str]) -> dict[str, Any]:
        self.cache.mkdir(parents=True, exist_ok=True)
        fichier = f"{cle}.{a.format}"
        (self.cache / fichier).write_bytes(a.donnees)
        meta = {"cle": cle, "fichier": fichier, "format": a.format, "duree_ms": a.duree_ms, "moteur": a.moteur,
                "modele": a.modele, "voix": a.voix, "distant": a.distant, "mots": a.mots, "envoye": a.envoye,
                "texte": P.texte_brut(part), "emotion": part["emotion"], "intensite": part["intensite"],
                "personnage": part.get("personnage", ""), "routage": motifs,
                "cree": time.strftime("%Y-%m-%dT%H:%M:%S"), "provenance": "machine (synthèse vocale)"}
        (self.cache / f"{cle}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        return meta

    # ── Rendu ────────────────────────────────────────────────────────────────────────────────────────
    def partition(self, texte: str, variation: dict[str, Any] | None, regime: str = "humain",
                  marques: dict[str, Any] | None = None, personnage: str = "",
                  base: dict[str, float] | None = None) -> dict[str, Any]:
        return P.construire(texte, variation, regime=regime, marques=marques, personnage=personnage,
                            langue=self.cfg["langue"], base=base)

    def _candidats(self, texte: str, confidentiel: bool) -> tuple[list[Moteur], list[str]]:
        motifs: list[str] = []
        if self.routeur is not None:
            dec = self.routeur.decider(texte, confidentielle=confidentiel)
            motifs = list(dec.motifs)
        elif confidentiel:
            motifs = ["contenu marqué confidentiel"]
        ms = [self.moteurs[n] for n in self.ordre]
        if motifs:
            ms = [m for m in ms if not m.distant]
        return [m for m in ms if m.disponible()[0]], motifs

    async def rendre(self, texte: str, variation: dict[str, Any] | None = None, *, regime: str = "humain",
                     marques: dict[str, Any] | None = None, personnage: str = "", role: str = "partenaire",
                     indice: int = 0, profil: str | None = None, base: dict[str, float] | None = None,
                     confidentiel: bool = False, prise: int = 0, moteur: str | None = None,
                     parler: bool = True) -> dict[str, Any]:
        part = self.partition(texte, variation, regime, marques, personnage, base)
        repli = {"statut": "repli", "partition": part, "segments": P.vers_navigateur(part),
                 "consigne": P.consigne_jeu(part)}
        if not parler or not part["phrases"]:
            return {**repli, "motif": "réplique muette"}
        if regime == "machinique":
            return {**repli, "motif": "voie machinique : voix non humaine voulue"}
        candidats, motifs = self._candidats(texte, confidentiel)
        if moteur:
            candidats = [m for m in candidats if m.nom == moteur]
        if not candidats:
            return {**repli, "motif": ("contenu sensible (D03) et aucun moteur local disponible" if motifs
                                       else "aucun moteur neuronal disponible"),
                    "local_seulement": bool(motifs), "routage": motifs}
        erreurs = []
        for m in candidats:
            voix = self._voix(m, role, personnage, indice, profil)
            if not voix:
                continue
            cle = self._cle(m, voix, part, prise)
            verrou = self._verrous.setdefault(cle, asyncio.Lock())
            async with verrou:
                meta = self._depuis_cache(cle)
                if meta is None:
                    try:
                        a = await asyncio.to_thread(m.synthetiser, part, voix)
                    except (ErreurVoix, OSError, ValueError) as e:
                        self.erreurs[m.nom] = str(e)[:200]
                        erreurs.append(f"{m.nom} : {e}")
                        continue
                    if not a.donnees:
                        erreurs.append(f"{m.nom} : audio vide")
                        continue
                    meta = self._ranger(cle, a, part, motifs)
                    self.erreurs.pop(m.nom, None)
                    self.journal("voix", moteur=m.nom, modele=a.modele, voix=voix, cle=cle, duree_ms=a.duree_ms,
                                 personnage=personnage, role=role, distant=a.distant)
            self._verrous.pop(cle, None)
            return {"statut": "audio", "url": f"/voix/{meta['fichier']}", "cle": cle, "format": meta["format"],
                    "duree_ms": meta["duree_ms"], "moteur": meta["moteur"], "modele": meta["modele"],
                    "voix": meta["voix"], "mots": meta.get("mots", []), "partition": part,
                    "segments": repli["segments"], "consigne": repli["consigne"], "routage": motifs}
        return {**repli, "motif": "échec des moteurs : " + " ; ".join(erreurs)[:400], "routage": motifs}

    async def prerendre(self, items: list[dict[str, Any]], progres: Callable[[int, int, dict], Awaitable[None]] | None = None
                        ) -> list[dict[str, Any]]:
        """Pré-rendu d'une répétition : chaque item = {id, texte, variation, regime, marques, personnage, indice,
        base, parler}. Les répliques sont rendues l'une après l'autre (quotas des éditeurs)."""
        out = []
        for k, it in enumerate(items):
            r = await self.rendre(it["texte"], it.get("variation"), regime=it.get("regime", "humain"),
                                  marques=it.get("marques"), personnage=it.get("personnage", ""),
                                  indice=int(it.get("indice", 0)), base=it.get("base"), parler=it.get("parler", True))
            r["id"] = it.get("id")
            out.append(r)
            if progres:
                await progres(k + 1, len(items), r)
        return out
