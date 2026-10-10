"""Agents du partenaire : conseiller, analyste dramaturgique, variations, retour de jeu.

Convention de sortie (fichier convention_agents.json fourni par l'équipe) : toute
réponse d'agent porte agent_type, agent_name et timestamp.

Garde-fous contre la fabrication :
* le conseiller ne peut citer que les passages qu'on lui a fournis ; toute
  référence inconnue est retirée et signalée ;
* l'analyste dramaturgique ne conserve que les citations retrouvées mot pour mot
  dans la pièce ;
* sans clé API, chaque agent répond par une voie déterministe et le dit.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

from . import dramaturgie, variations
from .connaissances import Index, reference

NOMS = {
    "formation": "Compagnon de formation",
    "repetiteur": "Répétiteur",
    "analyste_jeu": "Analyste du jeu",
    "analyste_piece": "Analyste dramaturgique",
    "conseiller": "Conseiller du spectacle",
    "variation": "Moteur de variations",
    "regie": "Régie de coprésence",
}

CADRE = """Tu es un agent du partenaire de théâtre ROBO-SCÈNE (robot de scène, IA supervisée).
Règles impératives :
- Réponds en français soutenu et précis.
- N'invente jamais de fait, de référence, de citation, de page ou d'URL.
- Tu n'attribues au robot ni conscience, ni émotion vécue, ni intention humaine.
- Toute affirmation que les sources fournies n'établissent pas commence par « (Inférence) ».
- Réponds UNIQUEMENT par un objet JSON valide, sans texte autour."""


def envelopper(agent_type: str, donnees: dict[str, Any]) -> dict[str, Any]:
    return {"agent_type": agent_type, "agent_name": NOMS[agent_type],
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"), **donnees}


def _json(texte: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", texte, re.S)
    if not m:
        raise ValueError("réponse sans JSON")
    return json.loads(m.group(0))


class Agents:
    def __init__(self, cfg: dict[str, Any], index: Index):
        self.cfg = cfg
        self.index = index
        self.client = None
        if cfg.get("ia_active", True) and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                from anthropic import AsyncAnthropic
                self.client = AsyncAnthropic()
            except ImportError:
                self.client = None

    @property
    def moteur(self) -> str:
        return f"claude:{self.cfg.get('modele')}" if self.client else "déterministe"

    async def _appel(self, consigne: str, contenu: str, temperature: float, max_tokens: int = 1800) -> dict[str, Any]:
        rep = await self.client.messages.create(
            model=self.cfg.get("modele", "claude-sonnet-5-5"), max_tokens=max_tokens,
            temperature=temperature, system=CADRE + "\n" + consigne,
            messages=[{"role": "user", "content": contenu}])
        return _json("".join(b.text for b in rep.content if getattr(b, "type", "") == "text"))

    # ── Conseiller du spectacle (formation, jeu, mise en scène, scénographie, robotique, IA) ──
    async def conseiller(self, question: str, domaines: list[str] | None = None) -> dict[str, Any]:
        passages = self.index.rechercher(question, k=7, domaines=domaines or None)
        refs = {p["id"]: p for p in passages}
        sources = [{"id": p["id"], "reference": reference(p), "extrait": p["texte"][:500]} for p in passages]
        if not passages:
            return envelopper("conseiller", {"question": question, "mode": "aucune source",
                                             "reponse": "Aucun passage de la base de connaissances ne répond à "
                                                        "cette question. Ajoutez des documents dans "
                                                        "partenaire/sources puis reconstruisez l'index.",
                                             "sources": []})
        if self.client:
            try:
                contenu = f"Question : {question}\n\nPassages autorisés :\n" + "\n\n".join(
                    f"[{p['id']}] ({reference(p)})\n{p['texte']}" for p in passages)
                d = await self._appel(
                    'Réponds à la question à partir des seuls passages fournis. Format : {"reponse": "texte où '
                    'chaque phrase sourcée se termine par [Kxxxxx]", "citations": ["Kxxxxx", ...]}. Si les '
                    'passages ne suffisent pas, dis-le.', contenu, float(self.cfg.get("temperature_analyse", 0.3)))
                texte = str(d.get("reponse", ""))
                citees = set(re.findall(r"\[(K\d{5})\]", texte)) | set(d.get("citations") or [])
                inconnues = sorted(c for c in citees if c not in refs)
                for c in inconnues:
                    texte = texte.replace(f"[{c}]", "[référence retirée]")
                return envelopper("conseiller", {"question": question, "mode": self.moteur, "reponse": texte,
                                                 "citations": sorted(c for c in citees if c in refs),
                                                 "references_retirees": inconnues, "sources": sources})
            except Exception as exc:
                repli = f"Repli extractif ({type(exc).__name__})."
        else:
            repli = "Réponse extractive : passages les plus pertinents, sans synthèse générée."
        return envelopper("conseiller", {"question": question, "mode": "extractif", "reponse": repli,
                                         "citations": [p["id"] for p in passages[:3]], "sources": sources})

    # ── Analyste dramaturgique ──
    async def analyser_piece(self, piece: dict[str, Any]) -> dict[str, Any]:
        stats = dramaturgie.analyser(piece)
        sortie = {"piece": piece["titre"], "auteur": piece.get("auteur", ""), "statistiques": stats,
                  "licence": piece.get("source", {}).get("licence", "")}
        if not self.client:
            return envelopper("analyste_piece", {**sortie, "mode": "déterministe", "interpretation": None,
                                                 "note": "Analyse interprétative disponible avec une clé API."})
        persos = ", ".join(f"{p['nom']} ({p['part_parole']:.0%} de la parole)" for p in stats["personnages"][:8])
        extraits = []
        for s in piece["scenes"][:2] + piece["scenes"][-1:]:
            reps = [e for e in piece["elements"] if e["scene"] == s["id"] and e["type"] == "replique"][:10]
            extraits.append(f"— {s['acte']} {s['titre']}\n" + "\n".join(f"{r['nom']} : {r['texte']}" for r in reps))
        for t in stats["tirades"][:3]:
            r = next(e for e in piece["elements"] if e["id"] == t["id"])
            extraits.append(f"— Tirade de {r['nom']} :\n{r['texte']}")
        contenu = (f"Pièce : {piece['titre']} ({piece.get('auteur', '')}). Personnages : {persos}.\n"
                   f"Configurations : {len(stats['configurations'])} scènes ; densité du réseau : "
                   f"{stats['reseau']['densite']}.\n\nExtraits :\n" + "\n\n".join(extraits))
        try:
            d = await self._appel(
                'Produis une analyse dramaturgique. Format : {"fable": "...", "modele_actantiel": {"sujet": "...", '
                '"objet": "...", "destinateur": "...", "destinataire": "...", "adjuvants": ["..."], '
                '"opposants": ["..."]}, "enjeux": ["..."], "pistes_de_jeu": ["..."], '
                '"partenaire_robotique": ["où et comment un robot partenaire pourrait intervenir sans se substituer '
                'aux interprètes"], "citations": [{"texte": "citation exacte des extraits", "commentaire": "..."}]}. '
                'Les citations doivent être recopiées mot pour mot depuis les extraits.',
                contenu, float(self.cfg.get("temperature_analyse", 0.3)), 2500)
            gardees, retirees = [], []
            for c in d.get("citations", []) or []:
                rid = dramaturgie.citation_verifiee(piece, str(c.get("texte", "")))
                (gardees if rid else retirees).append({**c, "replique": rid})
            d["citations"] = gardees
            return envelopper("analyste_piece", {**sortie, "mode": self.moteur, "interpretation": d,
                                                 "citations_retirees": retirees})
        except Exception as exc:
            return envelopper("analyste_piece", {**sortie, "mode": "déterministe", "interpretation": None,
                                                 "note": f"Analyse interprétative indisponible ({type(exc).__name__})."})

    # ── Variations émotionnelles d'une réplique ──
    async def variations(self, piece: dict[str, Any], rid: str) -> dict[str, Any]:
        el = next((e for e in piece["elements"] if e["id"] == rid and e["type"] == "replique"), None)
        if el is None:
            raise KeyError(rid)
        base = variations.propositions(el["texte"], el.get("didascalies"), el.get("didascalies_types"))
        out = {"replique": rid, "personnage": el["nom"], "texte": el["texte"], "indices": base["indices"],
               "propositions": base["propositions"], "mode": "règles"}
        if not self.client:
            return envelopper("variation", out)
        voisins = [e for e in piece["elements"] if e["scene"] == el["scene"] and e["type"] == "replique"]
        i = next(k for k, e in enumerate(voisins) if e["id"] == rid)
        contexte = "\n".join(f"{e['nom']} : {e['texte']}" for e in voisins[max(0, i - 4): i + 3])
        try:
            d = await self._appel(
                "Propose trois variations de jeu pour la réplique cible, fondées sur le texte. Émotions permises : "
                + ", ".join(variations.EMOTIONS) + ". Styles permis : " + ", ".join(variations.STYLES) +
                '. Format : {"propositions": [{"emotion": "...", "intensite": 1-10, "melange": null ou "...", '
                '"style": "...", "etiquette": "...", "indice": "mots exacts du texte qui la justifient", '
                '"justification": "..."}]}',
                f"Contexte :\n{contexte}\n\nRéplique cible ({el['nom']}) : {el['texte']}\n"
                f"Didascalies : {el.get('didascalies')}", float(self.cfg.get("temperature_variation", 0.7)))
            props = []
            for p in d.get("propositions", [])[:3]:
                try:
                    v = variations.variation(p.get("emotion", "neutre"), int(p.get("intensite", 5)), p.get("melange"),
                                             0.4, p.get("style", "réalisme psychologique"), p.get("etiquette", ""),
                                             p.get("justification", ""), source="claude")
                except (ValueError, TypeError):
                    continue
                indice = str(p.get("indice", ""))
                v["indice_verifie"] = bool(indice) and dramaturgie.citation_verifiee(
                    {"elements": voisins}, indice) is not None
                props.append(v)
            if props:
                out.update({"propositions": props + base["propositions"][len(props):], "mode": self.moteur})
        except Exception as exc:
            out["note"] = f"Propositions par règles ({type(exc).__name__})."
        return envelopper("variation", out)

    # ── Retour de jeu (déterministe : il commente des mesures, il ne juge pas l'art) ──
    @staticmethod
    def retour_jeu(passage: dict[str, Any], trajectoire: dict[str, Any] | None = None) -> dict[str, Any]:
        s = passage["synthese"]
        obs = []
        if s.get("latence_mediane_ms") is not None:
            l = s["latence_mediane_ms"]
            obs.append(f"Reprise de réplique médiane : {l / 1000:.2f} s" +
                       (" — reprises tardives : travailler l'écoute de la fin de réplique (livret, 1re année, "
                        "exercice 8.2 « Cercle d'écoute »)." if l > 1500 else "."))
        if s.get("chevauchements"):
            obs.append(f"{s['chevauchements']} chevauchement(s) : la réplique a commencé avant la fin de la précédente.")
        if s.get("souffles"):
            obs.append(f"{s['souffles']} appel(s) au souffleur.")
        if s.get("precision_moyenne") is not None:
            obs.append(f"Fidélité au texte : {s['precision_moyenne']:.0%}.")
        if s.get("debit_median"):
            d = s["debit_median"]
            obs.append(f"Débit médian : {d:.1f} syllabes/s" + (" (rapide)." if d > 6.5 else " (lent)." if d < 3.5 else "."))
        erreurs = [(m["replique"], m["texte"]) for m in passage["mesures"] if m.get("texte") and
                   (m["texte"]["omissions"] or m["texte"]["substitutions"])]
        return envelopper("analyste_jeu", {"observations": obs, "erreurs_texte": erreurs[:10],
                                           "trajectoire": (trajectoire or {}).get("lecture", []),
                                           "avertissement": "Mesures d'indices observables ; l'appréciation "
                                                            "artistique revient à l'acteur et à l'équipe."})
