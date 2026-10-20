"""Clients des fournisseurs : Anthropic (API Messages), OpenAI (API Responses), xAI (Grok, Chat Completions),
Google (Gemini, generateContent), LM Studio ou Ollama (local).

Chaque client consigne ce qui a été DEMANDÉ et ce qui a été réellement APPLIQUÉ, et signale l'écart
(fonction A-08 du cahier) : un paramètre ignoré ou retiré par compatibilité n'est jamais passé sous silence.

Règles vérifiées dans la documentation des fournisseurs (11 octobre 2026) :
* Anthropic : pour les modèles récents, `temperature` et `top_p` ne peuvent être fixés ensemble ; seule la
  température est envoyée (comportement déjà documenté dans le README de la console).
* OpenAI (guide « Using GPT-6 ») : `reasoning.effort` ∈ none, low, medium, high, xhigh, max ; GPT-6 Sol et
  Luna acceptent `none`, GPT-6 Astra et 6.1 Sol ne l'acceptent pas (employer `low`) ; dès que l'effort
  n'est pas `none`, `temperature`, `top_p` et `top_logprobs` doivent être retirés.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any
from ..tls import contexte as _tls


class ErreurModele(Exception):
    pass


@dataclass
class Reponse:
    texte: str
    fournisseur: str
    systeme: str
    modele_demande: str
    modele_exact: str
    jetons_entree: int = 0
    jetons_sortie: int = 0
    demandes: dict[str, Any] = field(default_factory=dict)
    appliques: dict[str, Any] = field(default_factory=dict)
    ecarts: list[str] = field(default_factory=list)
    cible: str = "distant"
    motifs_routage: list[str] = field(default_factory=list)
    famille: str = ""

    def trace(self) -> dict[str, Any]:
        """Champs exigés par le schéma de génération (N-02)."""
        return {"systeme": self.systeme, "version_modele": self.modele_exact, "fournisseur": self.fournisseur,
                "parametres_demandes": self.demandes, "parametres_appliques": self.appliques,
                "ecarts_parametres": self.ecarts, "jetons_entree": self.jetons_entree,
                "jetons_sortie": self.jetons_sortie}


def _post(url: str, corps: dict, entetes: dict, delai: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(corps).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **entetes}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=delai, context=_tls()) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ErreurModele(f"HTTP {e.code} : {e.read().decode('utf-8', 'replace')[:400]}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErreurModele(f"Service injoignable : {e}") from e


class ClientAnthropic:
    fournisseur = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, cle: str, delai: float = 90.0, transport=None):
        self.cle, self.delai, self.transport = cle, delai, transport or _post

    def generer(self, modele: str, systeme: str, contenu: str, *, temperature: float | None = None,
                top_p: float | None = None, max_tokens: int = 1500, **_: Any) -> Reponse:
        demandes = {k: v for k, v in {"temperature": temperature, "top_p": top_p, "max_tokens": max_tokens}.items()
                    if v is not None}
        corps: dict[str, Any] = {"model": modele, "max_tokens": max_tokens, "system": systeme,
                                 "messages": [{"role": "user", "content": contenu}]}
        ecarts = []
        if temperature is not None:
            corps["temperature"] = temperature
            if top_p is not None:
                ecarts.append("top_p retiré : l'API refuse temperature et top_p simultanément")
        elif top_p is not None:
            corps["top_p"] = top_p
        r = self.transport(self.URL, corps, {"x-api-key": self.cle, "anthropic-version": "2023-06-01"}, self.delai)
        texte = "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
        u = r.get("usage", {})
        appliques = {k: corps[k] for k in ("temperature", "top_p", "max_tokens") if k in corps}
        return Reponse(texte, "anthropic", "SI-01", modele, r.get("model", modele), int(u.get("input_tokens", 0)),
                       int(u.get("output_tokens", 0)), demandes, appliques, ecarts)


SANS_NONE = re.compile(r"^gpt-\d+\.\d+-sol$|astra")   # 6.1 Sol et Astra : pas d'effort « none »


class ClientOpenAI:
    fournisseur = "openai"
    URL = "https://api.openai.com/v1/responses"

    def __init__(self, cle: str, delai: float = 120.0, transport=None):
        self.cle, self.delai, self.transport = cle, delai, transport or _post

    def generer(self, modele: str, systeme: str, contenu: str, *, temperature: float | None = None,
                top_p: float | None = None, max_tokens: int = 1500, effort: str = "none", **_: Any) -> Reponse:
        demandes = {k: v for k, v in {"temperature": temperature, "top_p": top_p, "max_tokens": max_tokens,
                                      "effort": effort}.items() if v is not None}
        ecarts: list[str] = []
        if effort == "none" and SANS_NONE.search(modele):
            effort = "low"
            ecarts.append(f"effort « none » non accepté par {modele} : « low » appliqué")
        # store=False : la réponse n'est pas conservée comme « état d'application » (30 jours par défaut sur
        # /v1/responses, guide « Data controls in the OpenAI platform ») ; fiche fournisseur F-08.
        corps: dict[str, Any] = {"model": modele, "instructions": systeme, "input": contenu, "store": False,
                                 "max_output_tokens": max_tokens, "reasoning": {"effort": effort}}
        if effort == "none":
            if temperature is not None:
                corps["temperature"] = temperature
            if top_p is not None:
                corps["top_p"] = top_p
        else:
            for k, v in (("temperature", temperature), ("top_p", top_p)):
                if v is not None:
                    ecarts.append(f"{k} retiré : non pris en charge quand l'effort de raisonnement est « {effort} »")
        try:
            r = self.transport(self.URL, corps, {"Authorization": f"Bearer {self.cle}"}, self.delai)
        except ErreurModele as exc:
            # Version future qui refuserait « none » : un seul nouvel essai avec « low », consigné
            if effort == "none" and "effort" in str(exc):
                corps["reasoning"] = {"effort": "low"}
                for k in ("temperature", "top_p"):
                    if corps.pop(k, None) is not None:
                        ecarts.append(f"{k} retiré après refus de l'effort « none »")
                ecarts.append(f"effort « none » refusé par {modele} : « low » appliqué")
                r = self.transport(self.URL, corps, {"Authorization": f"Bearer {self.cle}"}, self.delai)
            else:
                raise
        texte = r.get("output_text") or "".join(
            c.get("text", "") for item in r.get("output", []) if item.get("type") == "message"
            for c in item.get("content", []) if c.get("type") == "output_text")
        u = r.get("usage", {})
        appliques = {"max_tokens": max_tokens, "effort": corps["reasoning"]["effort"],
                     **{k: corps[k] for k in ("temperature", "top_p") if k in corps}}
        return Reponse(texte, "openai", "SI-08", modele, r.get("model", modele), int(u.get("input_tokens", 0)),
                       int(u.get("output_tokens", 0)), demandes, appliques, ecarts)


class ClientXAI:
    """Grok par l'API de xAI (https://api.x.ai/v1, Chat Completions, compatible avec le format d'OpenAI ; docs.x.ai,
    consulté le 20 oct. 2026). La documentation de Grok 4.7 ne mentionne ni température ni plafond de sortie pour ce
    point d'accès : les deux sont envoyés (paramètres du format OpenAI) et consignés comme demandés ; le modèle
    renvoyé par le service est inscrit tel quel."""
    fournisseur = "xai"
    URL = "https://api.x.ai/v1/chat/completions"

    def __init__(self, cle: str, delai: float = 120.0, transport=None):
        self.cle, self.delai, self.transport = cle, delai, transport or _post

    def generer(self, modele: str, systeme: str, contenu: str, *, temperature: float | None = None,
                top_p: float | None = None, max_tokens: int = 1500, json_attendu: bool = False, **_: Any) -> Reponse:
        demandes = {k: v for k, v in {"temperature": temperature, "top_p": top_p, "max_tokens": max_tokens}.items()
                    if v is not None}
        corps: dict[str, Any] = {"model": modele, "stream": False, "max_tokens": max_tokens,
                                 "messages": [{"role": "system", "content": systeme}, {"role": "user", "content": contenu}]}
        ecarts: list[str] = []
        if temperature is not None:
            corps["temperature"] = temperature
        if top_p is not None:
            corps["top_p"] = top_p
        if json_attendu:
            corps["response_format"] = {"type": "json_object"}
        r = self.transport(self.URL, corps, {"Authorization": f"Bearer {self.cle}"}, self.delai)
        msg = ((r.get("choices") or [{}])[0]).get("message", {}) or {}
        u = r.get("usage", {}) or {}
        appliques = {k: corps[k] for k in ("temperature", "top_p", "max_tokens") if k in corps}
        return Reponse(msg.get("content") or "", "xai", "SI-09", modele, r.get("model", modele),
                       int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0)), demandes, appliques, ecarts)


def gemini_sans_echantillonnage(modele: str) -> bool:
    """Vrai pour Argon et pour tout Gemini de version 3.6 ou plus (température et top_p ignorés ou refusés)."""
    if "argon" in modele:
        return True
    m = re.match(r"^gemini-(\d+)(?:\.(\d+))?", modele)
    return bool(m) and (int(m.group(1)), int(m.group(2) or 0)) >= (3, 6)


class ClientGoogle:
    """Gemini par l'API Gemini de Google (models.generateContent, en-tête x-goog-api-key ; ai.google.dev, consulté le
    20 oct. 2026). Pour Gemini 4 Argon, la page « Latest model » demande de retirer temperature, top_p et top_k
    (ignorés) ; selon une source secondaire (AI Weekly, 22 juil. 2026), ils le sont aussi depuis Gemini 3.6 Flash et
    les générations suivantes renverraient une erreur 400. Par prudence, ils ne sont envoyés qu'aux modèles antérieurs
    à 3.6 ; l'écart est consigné (A-08)."""
    fournisseur = "google"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent"

    def __init__(self, cle: str, delai: float = 120.0, transport=None):
        self.cle, self.delai, self.transport = cle, delai, transport or _post

    def generer(self, modele: str, systeme: str, contenu: str, *, temperature: float | None = None,
                top_p: float | None = None, max_tokens: int = 1500, json_attendu: bool = False, **_: Any) -> Reponse:
        demandes = {k: v for k, v in {"temperature": temperature, "top_p": top_p, "max_tokens": max_tokens}.items()
                    if v is not None}
        config: dict[str, Any] = {"maxOutputTokens": max_tokens}
        ecarts: list[str] = []
        sans_echantillonnage = gemini_sans_echantillonnage(modele)
        for k, cle in (("temperature", "temperature"), ("top_p", "topP")):
            v = demandes.get(k)
            if v is None:
                continue
            if sans_echantillonnage:
                ecarts.append(f"{k} retiré : ignoré par {modele} (documentation du Gemini API)")
            else:
                config[cle] = v
        if json_attendu:
            config["responseMimeType"] = "application/json"
        corps = {"systemInstruction": {"parts": [{"text": systeme}]},
                 "contents": [{"role": "user", "parts": [{"text": contenu}]}], "generationConfig": config}
        r = self.transport(self.URL.format(modele=modele), corps, {"x-goog-api-key": self.cle}, self.delai)
        cand = (r.get("candidates") or [{}])[0]
        texte = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
        if not texte and cand.get("finishReason") not in (None, "STOP"):
            ecarts.append(f"réponse vide (finishReason : {cand.get('finishReason')})")
        u = r.get("usageMetadata", {}) or {}
        appliques = {"max_tokens": max_tokens, **({"temperature": config["temperature"]} if "temperature" in config else {}),
                     **({"top_p": config["topP"]} if "topP" in config else {})}
        return Reponse(texte, "google", "SI-10", modele, r.get("modelVersion", modele),
                       int(u.get("promptTokenCount", 0)), int(u.get("candidatesTokenCount", 0)), demandes, appliques, ecarts)


class ClientLocal:
    """SI-02 : modèle ouvert servi sur cette machine par LM Studio (défaut) ou Ollama.

    Refuse tout serveur ou modèle non local ; le choix du serveur (« api ») ne change rien à la règle D03.
    """

    def __init__(self, modele: str, url: str | None = None, delai: float = 180.0, transport=None,
                 secours: str | None = None, lister=None, api: str = "lmstudio", reseau_local: bool = False):
        from .. import _modules  # noqa: F401
        from atelier_p1.modeles import API_LOCALES, NOMS_SERVEURS, verifier_local
        self.api = (api or "lmstudio").lower()
        if self.api not in API_LOCALES:
            raise ValueError(f"serveur local inconnu : {self.api} (lmstudio ou ollama)")
        self.serveur = NOMS_SERVEURS[self.api]
        self.principal, self.url, self.delai = modele, (url or API_LOCALES[self.api]).rstrip("/"), delai
        self.secours = secours or None
        self.modele = modele                       # modèle effectivement servi (le secours si le principal manque)
        self.reseau_local = bool(reseau_local)
        self.refus = verifier_local(modele, self.url, self.reseau_local) if modele else ["aucun modèle local configuré"]
        # Un secours non conforme (cloud, remote, hôte distant) est écarté sans invalider le modèle principal.
        self.refus_secours = verifier_local(self.secours, self.url, self.reseau_local) if self.secours else []
        self.transport = transport or _post
        self._lister = lister or self._liste

    @property
    def fournisseur(self) -> str:
        return self.api

    def _liste(self) -> list[dict]:
        from atelier_p1.modeles import lister_locaux
        return lister_locaux(self.url, self.api)

    def _present(self, entrees: list[dict], nom: str) -> bool:
        from atelier_p1.modeles import present_localement
        # noms comparés sans égard à la casse ; une entrée annoncée comme distante est refusée
        return present_localement(entrees, nom) is True

    def choisir(self) -> str | None:
        """Modèle local à servir : le principal s'il est installé, sinon le secours ; None si aucun (D03 : refus)."""
        if self.refus:
            return None
        try:
            entrees = self._lister()
        except (urllib.error.URLError, OSError, ValueError):
            return None
        if self._present(entrees, self.principal):
            self.modele = self.principal
            return self.modele
        if self.secours and not self.refus_secours and self._present(entrees, self.secours):
            self.modele = self.secours
            return self.modele
        return None

    @property
    def disponible(self) -> bool:
        return self.choisir() is not None

    def generer(self, modele: str, systeme: str, contenu: str, *, temperature: float | None = None,
                top_p: float | None = None, max_tokens: int = 1500, json_attendu: bool = False, **_: Any) -> Reponse:
        if self.refus:
            raise ErreurModele("SI-02 refusé, traitement non local : " + " ; ".join(self.refus))
        if self.modele == self.secours and self.refus_secours:
            raise ErreurModele("SI-02 (secours) refusé, traitement non local : " + " ; ".join(self.refus_secours))
        from atelier_p1.modeles import chat_local
        # LM Studio n'accepte que « json_schema » : un objet JSON quelconque est demandé par un schéma minimal.
        r = chat_local(self.url, self.api, self.modele, systeme, contenu, delai=self.delai, temperature=temperature,
                       top_p=top_p, max_tokens=max_tokens, schema={"type": "object"} if json_attendu else None,
                       transport=self.transport)
        demandes = {k: v for k, v in {"temperature": temperature, "top_p": top_p, "max_tokens": max_tokens}.items()
                    if v is not None}
        return Reponse(r["texte"], self.api, "SI-02", self.modele, r["modele"], r["jetons_entree"],
                       r["jetons_sortie"], demandes, dict(demandes), list(r["ecarts"]), cible="local")
