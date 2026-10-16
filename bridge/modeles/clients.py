"""Clients des fournisseurs : Anthropic (API Messages), OpenAI (API Responses), Ollama (local).

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


class ClientLocal:
    """SI-02 : modèle ouvert servi par Ollama sur cette machine ; refuse tout serveur ou modèle non local."""
    fournisseur = "ollama"

    def __init__(self, modele: str, url: str = "http://127.0.0.1:11434", delai: float = 180.0, transport=None,
                 secours: str | None = None, lister=None):
        from .. import _modules  # noqa: F401
        from atelier_p1.modeles import verifier_local
        self.principal, self.url, self.delai = modele, url.rstrip("/"), delai
        self.secours = secours or None
        self.modele = modele                       # modèle effectivement servi (le secours si le principal manque)
        self.refus = verifier_local(modele, self.url) if modele else ["aucun modèle local configuré"]
        # Un secours non conforme (cloud, remote, hôte distant) est écarté sans invalider le modèle principal.
        self.refus_secours = verifier_local(self.secours, self.url) if self.secours else []
        self.transport = transport or _post
        self._lister = lister or self._tags

    def _tags(self) -> list[dict]:
        with urllib.request.urlopen(self.url + "/api/tags", timeout=2) as r:
            return json.loads(r.read()).get("models", [])

    def _present(self, entrees: list[dict], nom: str) -> bool:
        from atelier_p1.modeles import entree_distante
        cibles = {nom.lower(), f"{nom}:latest".lower()}
        # Ollama traite les noms sans égard à la casse (« :Q4_K_M » ou « :q4_k_m ») ; une entrée distante est refusée
        return any(e.get("name", "").lower() in cibles and not entree_distante(e) for e in entrees)

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
        options = {k: v for k, v in {"temperature": temperature, "top_p": top_p, "num_predict": max_tokens}.items()
                   if v is not None}
        corps = {"model": self.modele, "stream": False, "options": options,
                 "messages": [{"role": "system", "content": systeme}, {"role": "user", "content": contenu}]}
        if json_attendu:
            corps["format"] = "json"
        r = self.transport(self.url + "/api/chat", corps, {}, self.delai)
        demandes = {k: v for k, v in {"temperature": temperature, "top_p": top_p, "max_tokens": max_tokens}.items()
                    if v is not None}
        return Reponse(r.get("message", {}).get("content", ""), "ollama", "SI-02", self.modele,
                       r.get("model", self.modele), int(r.get("prompt_eval_count", 0)), int(r.get("eval_count", 0)),
                       demandes, dict(demandes), [], cible="local")
