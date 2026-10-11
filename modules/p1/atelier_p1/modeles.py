"""Modèles de génération : distant (SI-01), local (SI-02) et simulé (essais sans réseau).

Aucun modèle n'est entraîné ni affiné : le corpus n'est fourni qu'en contexte (P1.1, section 4 ; P1.2).
Seule la bibliothèque standard est employée pour les appels réseau.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

TYPES = {
    "situation": "une situation dramatique (lieu, personnages en présence, enjeu)",
    "contrainte": "une réponse à une contrainte d'écriture",
    "amorce": "une suite possible à une amorce de réplique",
    "repere": "une proposition pour un repère scénique (didascalie, entrée, jeu muet)",
    "libre": "une proposition répondant librement à la consigne",
}

SYSTEME = (
    "Tu assistes des artistes de théâtre dans un atelier d'écriture de recherche. Tu proposes ; ce sont les "
    "artistes qui choisissent, réécrivent et signent. Écris en français, sauf si la consigne demande une autre "
    "langue. Propose des pistes nettement différentes les unes des autres, brèves (au plus 120 mots chacune), "
    "jouables sur un plateau. Évite les stéréotypes de genre, culturels ou liés au handicap ; ne donne pas aux "
    "personnages des traits convenus selon leur genre ou leur origine. Les extraits fournis servent d'exemples "
    "de ton ou de contrainte : ne les recopie pas et n'en reprends aucun vers ou aucune phrase. Réponds "
    "uniquement par un objet JSON de la forme {\"propositions\": [\"…\", \"…\"]}."
)


@dataclass
class Generation:
    propositions: list[str]
    systeme: str                 # code du registre G.5 : SI-01, SI-02 ou SIMULE
    modele: str                  # identifiant ou version renvoyée par le fournisseur
    jetons_entree: int = 0
    jetons_sortie: int = 0
    brut: str = field(default="", repr=False)


class ErreurModele(Exception):
    pass


def construire_consigne(texte: str, type_: str, nb: int, extraits=()) -> str:
    morceaux = [f"Consigne de l'artiste ({TYPES.get(type_, TYPES['libre'])}) :\n{texte.strip()}",
                f"Nombre de propositions demandé : {nb}."]
    for e in extraits:
        morceaux.append(f"Extrait d'exemple {e.code} — {e.mention()} :\n\"\"\"\n{e.texte}\n\"\"\"")
    return "\n\n".join(morceaux)


def extraire_propositions(brut: str, nb: int) -> list[str]:
    """Lit le JSON demandé ; à défaut, découpe une liste numérotée. Tronque ou complète à `nb` au plus."""
    texte = (brut or "").strip()
    m = re.search(r"\{.*\}", texte, re.S)
    if m:
        try:
            props = json.loads(m.group(0)).get("propositions", [])
            props = [str(p).strip() for p in props if str(p).strip()]
            if props:
                return props[:nb]
        except (json.JSONDecodeError, AttributeError):
            pass
    lignes = [re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", l).strip() for l in texte.split("\n")]
    props = [l for l in lignes if l]
    if not props:
        raise ErreurModele("Réponse du modèle vide ou illisible.")
    return props[:nb]


def _post_json(url: str, corps: dict, entetes: dict, delai: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(corps).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **entetes}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=delai) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise ErreurModele(f"HTTP {e.code} : {detail}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErreurModele(f"Service injoignable : {e}") from e


class ModeleDistant:
    """SI-01 : Claude par l'API Messages d'Anthropic (décision D03). Consignes non sensibles seulement."""
    code = "SI-01"
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, modele: str = "claude-opus-5-5", cle: str | None = None, max_jetons: int = 1500,
                 delai: float = 60.0):
        self.modele, self.max_jetons, self.delai = modele, max_jetons, delai
        self.cle = cle or os.environ.get("ANTHROPIC_API_KEY", "")

    @property
    def disponible(self) -> bool:
        return bool(self.cle)

    def generer(self, texte: str, type_: str, nb: int, extraits=()) -> Generation:
        if not self.disponible:
            raise ErreurModele("Clé ANTHROPIC_API_KEY absente : modèle distant indisponible.")
        r = _post_json(self.URL, {
            "model": self.modele, "max_tokens": self.max_jetons, "system": SYSTEME,
            "messages": [{"role": "user", "content": construire_consigne(texte, type_, nb, extraits)}],
        }, {"x-api-key": self.cle, "anthropic-version": "2023-06-01"}, self.delai)
        brut = "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
        u = r.get("usage", {})
        return Generation(extraire_propositions(brut, nb), self.code, r.get("model", self.modele),
                          int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0)), brut)


HOTES_LOCAUX = {"127.0.0.1", "localhost", "::1"}


def verifier_local(modele: str, url: str) -> list[str]:
    """Motifs pour lesquels SI-02 ne serait PAS un traitement local (liste vide = conforme à D03 et G.6).

    Deux fuites possibles sans que le code appelant le sache : un serveur Ollama situé sur une autre machine,
    et les « modèles infonuagiques » d'Ollama (étiquette « -cloud »), exécutés sur les serveurs d'ollama.com
    alors qu'ils s'appellent par la même API locale (registre G.5 v1.1, fiche SI-02).
    """
    motifs = []
    hote = (urllib.parse.urlsplit(url).hostname or "").lower()
    if hote not in HOTES_LOCAUX:
        motifs.append(f"serveur Ollama non local ({hote or 'hôte illisible'})")
    if re.search(r"cloud", modele or "", re.I):
        motifs.append(f"modèle « {modele} » exécuté dans le nuage d'Ollama (étiquette cloud)")
    return motifs


class ModeleLocal:
    """SI-02 : modèle ouvert servi localement par Ollama (http://127.0.0.1:11434) ; fiche SI-02 (G.5 v1.1).

    Refuse tout serveur non local et tout modèle infonuagique : une consigne sensible ne quitte jamais la machine.
    """
    code = "SI-02"

    def __init__(self, modele: str | None = None, url: str = "http://127.0.0.1:11434", delai: float = 180.0):
        self.modele = modele or os.environ.get("ATELIER_MODELE_LOCAL", "")
        self.url, self.delai = url.rstrip("/"), delai
        self.refus = verifier_local(self.modele, self.url) if self.modele else []

    @property
    def disponible(self) -> bool:
        if not self.modele or self.refus:
            return False
        try:
            with urllib.request.urlopen(self.url + "/api/tags", timeout=2) as r:
                entrees = json.loads(r.read()).get("models", [])
        except (urllib.error.URLError, OSError, ValueError):
            return False
        for m in entrees:
            if m.get("name", "") in (self.modele, f"{self.modele}:latest"):
                # par prudence : une entrée qui annonce un hôte ou un modèle distant est refusée
                if any(k.startswith("remote") and v for k, v in m.items()):
                    self.refus = [f"Ollama annonce « {self.modele} » comme modèle distant"]
                    return False
                return True
        return False

    def generer(self, texte: str, type_: str, nb: int, extraits=()) -> Generation:
        if not self.modele:
            raise ErreurModele("Aucun modèle local configuré (ATELIER_MODELE_LOCAL).")
        if self.refus:
            raise ErreurModele("SI-02 refusé, traitement non local : " + " ; ".join(self.refus))
        r = _post_json(self.url + "/api/chat", {
            "model": self.modele, "stream": False, "format": "json",
            "messages": [{"role": "system", "content": SYSTEME},
                         {"role": "user", "content": construire_consigne(texte, type_, nb, extraits)}],
        }, {}, self.delai)
        brut = r.get("message", {}).get("content", "")
        return Generation(extraire_propositions(brut, nb), self.code, r.get("model", self.modele),
                          int(r.get("prompt_eval_count", 0)), int(r.get("eval_count", 0)), brut)


class ModeleSimule:
    """Générateur déterministe, sans réseau, pour les essais du logiciel et la formation (jamais en atelier réel)."""
    code = "SIMULE"
    modele = "simule-0.1"
    disponible = True

    AMORCES = ["Et si personne n'était venu ?", "On recommence, mais à voix basse.",
               "La porte reste ouverte ; personne n'ose la fermer.", "Elle compte jusqu'à trois, puis se tait.",
               "Il rit, trop tôt, et tout le monde le remarque."]

    def generer(self, texte: str, type_: str, nb: int, extraits=()) -> Generation:
        graine = sum(map(ord, texte)) % len(self.AMORCES)
        props = [f"[simulé] {self.AMORCES[(graine + i) % len(self.AMORCES)]}" for i in range(nb)]
        return Generation(props, self.code, self.modele, len(texte.split()), sum(len(p.split()) for p in props),
                          json.dumps({"propositions": props}, ensure_ascii=False))
