"""Décision D13 : veille des versions, rôles, routage de sensibilité sans repli, paramètres appliqués (A-08)."""
import json

import pytest

from bridge.modeles import AucunModele, RefusSensibilite, ServiceModeles
from bridge.modeles.catalogue import FAMILLES, Catalogue, plus_recent
from bridge.modeles.clients import ClientAnthropic, ClientOpenAI


def test_plus_recent_par_famille():
    ids = ["claude-opus-4-1", "claude-opus-5-5", "claude-opus-5-5-20260601", "claude-sonnet-5-5", "claude-opus-5"]
    assert plus_recent(ids, FAMILLES["claude-opus"]) == "claude-opus-5-5"
    oa = ["gpt-5.6-sol", "gpt-6-sol", "gpt-6.1-sol", "gpt-6.1-sol-pro", "gpt-6-luna", "gpt-6-luna-pro", "gpt-5.6-terra"]
    assert plus_recent(oa, FAMILLES["gpt-sol"]) == "gpt-6.1-sol"
    assert plus_recent(oa, FAMILLES["gpt-luna"]) == "gpt-6-luna"


def test_adoption_a_chaque_seance(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    listes = {"anthropic": ["claude-opus-5-5", "claude-sonnet-5-5"], "openai": ["gpt-6.1-sol", "gpt-6-luna"]}
    c = Catalogue({}, tmp_path, {k: (lambda cle, k=k: listes[k]) for k in listes})
    r1 = c.resoudre("20261011_P1_A_001")
    assert r1["claude-opus"] == "claude-opus-5-5" and r1["gpt-luna"] == "gpt-6-luna"
    # Un nouveau modèle paraît : il n'est adopté qu'à la séance suivante, et l'adoption est consignée
    listes["anthropic"].append("claude-opus-6")
    assert c.resolus["claude-opus"] == "claude-opus-5-5"
    r2 = c.resoudre("20261012_P1_A_001")
    assert r2["claude-opus"] == "claude-opus-6"
    h = json.loads((tmp_path / "adoptions_modeles.json").read_text())["historique"]
    assert h[-1] == {**h[-1], "famille": "claude-opus", "ancienne": "claude-opus-5-5", "nouvelle": "claude-opus-6"}
    # Jamais de retour en arrière silencieux
    listes["anthropic"].remove("claude-opus-6")
    assert c.resoudre("20261013_P1_A_001")["claude-opus"] == "claude-opus-6"
    assert any("n'apparaît plus" in n for n in c.notes)


class Faux:
    def __init__(self, f):
        self.f, self.appels = f, []
        self.disponible, self.modele, self.refus = True, "gemma4:12b", []

    def generer(self, modele, systeme, contenu, **kw):
        from bridge.modeles.clients import Reponse
        self.appels.append((modele, contenu, kw))
        return Reponse(f"[{self.f}] ok", self.f, {"anthropic": "SI-01", "openai": "SI-08", "ollama": "SI-02"}[self.f],
                       modele, modele, 3, 5, {}, {}, [], cible="local" if self.f == "ollama" else "distant")


def service(tmp_path, monkeypatch, **cfg):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    clients = {f: Faux(f) for f in ("anthropic", "openai", "ollama")}
    s = ServiceModeles(cfg, tmp_path, clients=clients, listeurs={"anthropic": lambda c: [], "openai": lambda c: []})
    return s, clients


def test_roles_et_fournisseur_prefere(tmp_path, monkeypatch):
    s, c = service(tmp_path, monkeypatch)
    s.ouvrir_seance("20261011_P1_A_001")
    assert s.generer_sync("ecriture", "sys", "Une scène").modele_exact == "claude-opus-5-5"
    assert s.generer_sync("rapide", "sys", "Surtitre").modele_exact == "claude-sonnet-5-5"
    s2, _ = service(tmp_path / "b", monkeypatch, fournisseur_prefere="openai")
    s2.ouvrir_seance("20261011_P1_A_002")
    assert s2.generer_sync("ecriture", "sys", "Une scène").modele_exact == "gpt-6.1-sol"
    assert s2.generer_sync("rapide", "sys", "x").modele_exact == "gpt-6-luna"


def test_sensible_va_au_local_sans_repli(tmp_path, monkeypatch):
    s, c = service(tmp_path, monkeypatch)
    r = s.generer_sync("ecriture", "sys", "Écrire à lea@exemple.org")
    assert r.fournisseur == "ollama" and "adresse de courriel détectée" in r.motifs_routage
    assert not c["anthropic"].appels
    c["ollama"].disponible = False
    with pytest.raises(RefusSensibilite):
        s.generer_sync("ecriture", "sys", "texte", confidentielle=True)
    assert not c["anthropic"].appels and not c["openai"].appels


def test_aucune_cle(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    s = ServiceModeles({}, tmp_path, clients={"ollama": Faux("ollama")})
    with pytest.raises(AucunModele):
        s.generer_sync("analyse", "sys", "Une question")


def test_parametres_appliques_openai_et_anthropic():
    envoyes = []

    def transport(url, corps, entetes, delai):
        envoyes.append(corps)
        if "responses" in url:
            return {"model": corps["model"] + "-2026-09-29", "usage": {"input_tokens": 4, "output_tokens": 6},
                    "output": [{"type": "reasoning"}, {"type": "message", "content": [{"type": "output_text", "text": "ok"}]}]}
        return {"model": corps["model"], "content": [{"type": "text", "text": "ok"}], "usage": {}}

    r = ClientOpenAI("k", transport=transport).generer("gpt-6.1-sol", "s", "c", temperature=0.7, effort="none")
    assert envoyes[-1]["reasoning"] == {"effort": "low"} and "temperature" not in envoyes[-1]
    assert r.texte == "ok" and r.modele_exact == "gpt-6.1-sol-2026-09-29" and len(r.ecarts) == 2
    r = ClientOpenAI("k", transport=transport).generer("gpt-6-luna", "s", "c", temperature=0.7, effort="none")
    assert envoyes[-1]["temperature"] == 0.7 and r.ecarts == []
    assert all(c.get("store") is False for c in envoyes)   # F-08 : aucun état d'application conservé chez OpenAI
    r = ClientAnthropic("k", transport=transport).generer("claude-opus-5-5", "s", "c", temperature=0.7, top_p=0.9)
    assert "top_p" not in envoyes[-1] and r.appliques == {"temperature": 0.7, "max_tokens": 1500}
    assert r.ecarts and "top_p" in r.ecarts[0]


def test_gpt_terra_en_attente_puis_adopte(tmp_path, monkeypatch):
    """GPT-6 Terra n'existe pas (vérifié le 12 oct. 2026) : la famille reste inutilisée, gpt-5.6-terra est
    refusé (génération antérieure), puis un GPT-6 Terra publié est adopté au début de la séance suivante."""
    from bridge.modeles.catalogue import Catalogue
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    liste = ["gpt-6.1-sol", "gpt-6-luna", "gpt-5.6-terra"]
    c = Catalogue({}, tmp_path, listeurs={"openai": lambda _k: liste, "anthropic": lambda _k: []})
    r = c.resoudre("20261012_X_A_001")
    assert r["gpt-terra"] == "" and c.choisir("rapide")[1] == "gpt-6-luna"
    liste.append("gpt-6-terra")
    r = c.resoudre("20261012_X_A_002")
    assert r["gpt-terra"] == "gpt-6-terra" and c.choisir("rapide")[1] == "gpt-6-terra"
    assert c.etat["historique"][-1]["nouvelle"] == "gpt-6-terra"


# ── SI-02 désigné (audit du 2026-10-16 : A-009, A-010, VP-14) ──────────────────────────────
LUCIOLE = "luciole-8b-instruct-1.1"            # identifiants LM Studio (serveur local depuis le 2026-10-16)
APERTUS = "apertus-8b-instruct-2509-si02"
LUCIOLE_OLLAMA = "hf.co/OpenLLM-France/Luciole-8B-Instruct-1.1-GGUF:Q4_K_M"


def test_config_designe_luciole_et_secours_local():
    import tomllib
    from pathlib import Path
    m = tomllib.loads(Path("config.toml").read_text(encoding="utf-8"))["modeles"]
    assert m["local"] == LUCIOLE and m["local_secours"] == APERTUS and m["local_provisoire"] is False
    assert m["api_local"] == "lmstudio" and m["url_local"] == "http://127.0.0.1:1234"
    assert FAMILLES["local"].reference == LUCIOLE


@pytest.mark.parametrize("etiquette", ["glm-5.1:cloud", "deepseek-v4-flash:cloud", "kimi-k2.6:cloud",
                                       "gpt-oss:120b-cloud", "qwen3:remote", "Mistral:REMOTE"])
def test_etiquettes_distantes_refusees_vp14(etiquette):
    from bridge.modeles.clients import ClientLocal
    c = ClientLocal(etiquette, lister=lambda: [{"name": etiquette}])
    assert c.refus and not c.disponible
    with pytest.raises(Exception):
        c.generer(etiquette, "s", "t")


def test_casse_ollama_et_entree_remote_refusee():
    from bridge.modeles.clients import ClientLocal
    c = ClientLocal(LUCIOLE_OLLAMA, lister=lambda: [{"name": LUCIOLE_OLLAMA.lower()}], api="ollama")
    assert c.disponible and c.modele == LUCIOLE_OLLAMA and c.url == "http://127.0.0.1:11434"
    # une entrée qui annonce un hôte distant n'est jamais retenue, même sous le bon nom
    c2 = ClientLocal(LUCIOLE_OLLAMA, lister=lambda: [{"name": LUCIOLE_OLLAMA, "remote_host": "https://ollama.com:443"}],
                     api="ollama")
    assert not c2.disponible


def test_lmstudio_casse_et_appareil_distant_refuse():
    from bridge.modeles.clients import ClientLocal
    c = ClientLocal(LUCIOLE, lister=lambda: [{"name": "Luciole-8B-Instruct-1.1", "id": "Luciole-8B-Instruct-1.1"}])
    assert c.api == "lmstudio" and c.url == "http://127.0.0.1:1234" and c.disponible
    # instance reliée d'une autre machine : jamais retenue, même sous le bon nom
    c2 = ClientLocal(LUCIOLE, lister=lambda: [{"name": LUCIOLE, "device": "Mac-mini-du-studio"}])
    assert not c2.disponible
    c3 = ClientLocal(LUCIOLE, url="http://192.168.1.20:1234", lister=lambda: [{"name": LUCIOLE}])
    assert c3.refus and not c3.disponible
    with pytest.raises(ValueError):
        ClientLocal(LUCIOLE, api="vllm")


def test_lmstudio_requete_compatible_openai_et_json_schema():
    from bridge.modeles.clients import ClientLocal
    recu = {}

    def transport(url, corps, entetes, delai):
        recu.update(url=url, corps=corps)
        return {"model": LUCIOLE, "choices": [{"message": {"content": '{"a": 1}', "reasoning_content": ""}}],
                "usage": {"prompt_tokens": 26, "completion_tokens": 9}}
    c = ClientLocal(LUCIOLE, transport=transport, lister=lambda: [{"name": LUCIOLE}])
    r = c.generer(LUCIOLE, "système", "contenu", temperature=0.7, top_p=0.9, max_tokens=300, json_attendu=True)
    assert recu["url"] == "http://127.0.0.1:1234/v1/chat/completions" and recu["corps"]["stream"] is False
    # LM Studio rejette « json_object » : seul « json_schema » est envoyé
    assert recu["corps"]["response_format"]["type"] == "json_schema"
    assert recu["corps"]["temperature"] == 0.7 and recu["corps"]["top_p"] == 0.9 and recu["corps"]["max_tokens"] == 300
    assert r.texte == '{"a": 1}' and r.fournisseur == "lmstudio" and r.cible == "local" and r.systeme == "SI-02"
    assert (r.jetons_entree, r.jetons_sortie) == (26, 9) and r.appliques["temperature"] == 0.7
    vide = ClientLocal(LUCIOLE, transport=lambda *a: {"choices": [{"message": {"content": "",
                                                                             "reasoning_content": "…"}}]})
    assert "reasoning_content" in vide.generer(LUCIOLE, "s", "t").ecarts[0]


def test_service_lmstudio_par_defaut(tmp_path):
    s = ServiceModeles({}, tmp_path)
    assert s.local.api == "lmstudio" and s.local.url == "http://127.0.0.1:1234" and s.local.modele == LUCIOLE
    assert s.resume()["local"]["serveur"] == "LM Studio"
    s2 = ServiceModeles({"api_local": "ollama", "local": LUCIOLE_OLLAMA}, tmp_path)
    assert s2.local.url == "http://127.0.0.1:11434" and s2.local.serveur == "Ollama"


def test_secours_local_seulement_si_principal_absent():
    from bridge.modeles.clients import ClientLocal
    tags = [{"name": "Apertus-8B-Instruct-2509-SI02"}]
    c = ClientLocal(LUCIOLE, secours=APERTUS, lister=lambda: tags)
    assert c.choisir() == APERTUS
    tags.append({"name": LUCIOLE})
    assert c.choisir() == LUCIOLE
    # un secours infonuagique est écarté sans invalider le principal
    c3 = ClientLocal(LUCIOLE, secours="glm-5.1:cloud", lister=lambda: [{"name": "glm-5.1:cloud"}])
    assert c3.refus == [] and c3.refus_secours and c3.choisir() is None


def test_aucun_modele_local_refus_sans_repli(tmp_path, monkeypatch):
    from bridge.modeles.clients import ClientLocal
    s, c = service(tmp_path, monkeypatch)
    s.local = ClientLocal(LUCIOLE, secours=APERTUS, lister=lambda: [])
    with pytest.raises(RefusSensibilite):
        s.generer_sync("analyse", "s", "Écrire à eloise@example.org", confidentielle=True)
    assert c["anthropic"].appels == [] and c["openai"].appels == []
