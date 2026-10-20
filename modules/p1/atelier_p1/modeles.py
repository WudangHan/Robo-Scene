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


def hote_reseau_prive(hote: str) -> bool:
    """Adresse d'un réseau privé (RFC 1918, liens locaux IPv6) ou nom mDNS « .local » : un poste de l'équipe joint
    par le Wi-Fi de la salle, jamais un service sur Internet."""
    import ipaddress
    if hote.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(hote)
    except ValueError:
        return False
    return (ip.is_private or ip.is_link_local) and not ip.is_loopback and not ip.is_unspecified


def verifier_local(modele: str, url: str, reseau_prive: bool = False) -> list[str]:
    """Motifs pour lesquels SI-02 ne serait PAS un traitement local (liste vide = conforme à D03 et G.6).

    Deux fuites possibles sans que le code appelant le sache : un serveur de modèles (LM Studio ou Ollama)
    situé sur une autre machine, et les modèles exécutés ailleurs mais appelés par la même API locale (étiquette
    « -cloud » d'Ollama, entrée annoncée comme distante ; registre G.5 v1.1, fiche SI-02).
    """
    motifs = []
    hote = (urllib.parse.urlsplit(url).hostname or "").lower()
    # reseau_prive (option [modeles] reseau_local = true, décision consignée) : LM Studio d'un autre poste de l'équipe
    # sur le réseau Wi-Fi local de la salle ; un hôte public reste refusé.
    if hote not in HOTES_LOCAUX and not (reseau_prive and hote_reseau_prive(hote)):
        motifs.append(f"serveur de modèles non local ({hote or 'hôte illisible'})")
    if RE_DISTANT.search(modele or ""):
        motifs.append(f"modèle « {modele} » exécuté hors de cette machine (étiquette cloud ou remote, VP-14)")
    return motifs


# Étiquettes Ollama exécutées hors poste : « :cloud », « -cloud », « :remote »… (EFVP v1.1, VP-14)
RE_DISTANT = re.compile(r"cloud|remote", re.I)


def entree_distante(entree: dict) -> bool:
    """Vrai si une entrée de la liste des modèles annonce un modèle servi ailleurs.

    Ollama : remote_host, remote_model… ; LM Studio : champ « device » autre que local (instances reliées).
    """
    if RE_DISTANT.search(entree.get("name", "") or ""):
        return True
    if any(str(k).startswith("remote") and v for k, v in entree.items()):
        return True
    appareil = entree.get("device")
    return bool(appareil) and str(appareil).lower() not in ("local", "this device", "cet appareil")


NUM_CTX = 8192

# ── Serveurs locaux de modèles ouverts (SI-02) ────────────────────────────────
# LM Studio (par défaut depuis le 16 oct. 2026) : API compatible OpenAI, /v1/models et /v1/chat/completions ;
# la sortie structurée n'accepte que response_format « json_schema » ou « text » (vérifié sur le poste :
# « json_object » est rejeté). Ollama : /api/tags et /api/chat, conservé pour la comparabilité des essais.
API_LOCALES = {"lmstudio": "http://127.0.0.1:1234", "ollama": "http://127.0.0.1:11434"}
NOMS_SERVEURS = {"lmstudio": "LM Studio", "ollama": "Ollama"}
SCHEMA_PROPOSITIONS = {"type": "object", "properties": {"propositions": {"type": "array", "items": {"type": "string"}}},
                       "required": ["propositions"]}


def api_par_defaut() -> str:
    api = os.environ.get("ATELIER_API_LOCALE", "lmstudio").strip().lower()
    return api if api in API_LOCALES else "lmstudio"


def lister_locaux(url: str, api: str, delai: float = 2.0) -> list[dict]:
    """Modèles offerts par le serveur local, sous une forme commune : [{"name": …, …champs d'origine}]."""
    chemin = "/v1/models" if api == "lmstudio" else "/api/tags"
    with urllib.request.urlopen(url.rstrip("/") + chemin, timeout=delai) as r:
        d = json.loads(r.read())
    if api == "lmstudio":
        return [{**e, "name": e.get("id", "")} for e in d.get("data", [])]
    return d.get("models", [])


def present_localement(entrees: list[dict], nom: str) -> bool | None:
    """True si le modèle est offert localement, False s'il est absent, None s'il est annoncé comme distant."""
    cibles = {nom.lower(), f"{nom}:latest".lower()}       # noms comparés sans égard à la casse
    for e in entrees:
        if (e.get("name", "") or "").lower() in cibles:
            return None if entree_distante(e) else True
    return False


def chat_local(url: str, api: str, modele: str, systeme: str, contenu: str, *, delai: float = 180.0,
               temperature: float | None = None, top_p: float | None = None, max_tokens: int | None = None,
               schema: dict | None = None, transport=None) -> dict:
    """Un échange avec le serveur local ; renvoie {texte, modele, jetons_entree, jetons_sortie, ecarts}."""
    poster = transport or _post_json
    messages = [{"role": "system", "content": systeme}, {"role": "user", "content": contenu}]
    ecarts: list[str] = []
    if api == "lmstudio":
        corps = {"model": modele, "stream": False, "messages": messages,
                 **{k: v for k, v in {"temperature": temperature, "top_p": top_p, "max_tokens": max_tokens}.items()
                    if v is not None}}
        if schema is not None:
            corps["response_format"] = {"type": "json_schema", "json_schema": {"name": "reponse", "schema": schema}}
        r = poster(url.rstrip("/") + "/v1/chat/completions", corps, {}, delai)
        msg = ((r.get("choices") or [{}])[0]).get("message", {}) or {}
        texte = msg.get("content") or ""
        if not texte and msg.get("reasoning_content"):
            ecarts.append("réponse versée dans le seul champ de délibération (reasoning_content) : contenu vide")
        u = r.get("usage", {}) or {}
        return {"texte": texte, "modele": r.get("model", modele), "jetons_entree": int(u.get("prompt_tokens", 0)),
                "jetons_sortie": int(u.get("completion_tokens", 0)), "ecarts": ecarts}
    options = {k: v for k, v in {"temperature": temperature, "top_p": top_p, "num_predict": max_tokens}.items()
               if v is not None}
    # Contexte borné : un réglage global d'Ollama (OLLAMA_CONTEXT_LENGTH, p. ex. 262 144) ferait déborder
    # un grand modèle sur le processeur ; une consigne et ses extraits tiennent dans 8 192 jetons.
    options["num_ctx"] = NUM_CTX
    # Sans délibération : pour un modèle « à raisonnement », Ollama verserait sinon toute la sortie dans
    # le champ « thinking » et laisserait « content » vide.
    corps = {"model": modele, "stream": False, "think": False, "options": options, "messages": messages}
    if schema is not None:
        corps["format"] = "json"
    r = poster(url.rstrip("/") + "/api/chat", corps, {}, delai)
    return {"texte": r.get("message", {}).get("content", ""), "modele": r.get("model", modele),
            "jetons_entree": int(r.get("prompt_eval_count", 0)), "jetons_sortie": int(r.get("eval_count", 0)),
            "ecarts": ecarts}


class ModeleLocal:
    """SI-02 : modèle ouvert servi sur cette machine par LM Studio (défaut) ou Ollama ; fiche SI-02 (G.5).

    Refuse tout serveur non local et tout modèle annoncé comme distant : une consigne sensible ne quitte
    jamais la machine.
    """
    code = "SI-02"

    def __init__(self, modele: str | None = None, url: str | None = None, delai: float = 180.0,
                 api: str | None = None):
        self.api = (api or api_par_defaut()).lower()
        if self.api not in API_LOCALES:
            raise ValueError(f"serveur local inconnu : {self.api} (lmstudio ou ollama)")
        self.modele = modele or os.environ.get("ATELIER_MODELE_LOCAL", "")
        self.url = (url or os.environ.get("ATELIER_URL_LOCALE") or API_LOCALES[self.api]).rstrip("/")
        self.delai = delai
        self.refus = verifier_local(self.modele, self.url) if self.modele else []

    @property
    def serveur(self) -> str:
        return NOMS_SERVEURS[self.api]

    @property
    def disponible(self) -> bool:
        if not self.modele or self.refus:
            return False
        try:
            entrees = lister_locaux(self.url, self.api)
        except (urllib.error.URLError, OSError, ValueError):
            return False
        etat = present_localement(entrees, self.modele)
        if etat is None:                      # par prudence : une entrée annoncée comme distante est refusée
            self.refus = [f"{self.serveur} annonce « {self.modele} » comme modèle distant"]
            return False
        return etat

    def generer(self, texte: str, type_: str, nb: int, extraits=()) -> Generation:
        if not self.modele:
            raise ErreurModele("Aucun modèle local configuré (ATELIER_MODELE_LOCAL).")
        if self.refus:
            raise ErreurModele("SI-02 refusé, traitement non local : " + " ; ".join(self.refus))
        r = chat_local(self.url, self.api, self.modele, SYSTEME, construire_consigne(texte, type_, nb, extraits),
                       delai=self.delai, schema=SCHEMA_PROPOSITIONS)
        return Generation(extraire_propositions(r["texte"], nb), self.code, r["modele"], r["jetons_entree"],
                          r["jetons_sortie"], r["texte"])


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
