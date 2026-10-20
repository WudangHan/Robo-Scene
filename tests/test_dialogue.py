"""Moteurs d'IA au choix (Claude, GPT, Grok, Gemini, LM Studio) et dialogue parlé du robot, du chien et du drone."""
import asyncio
import json

import pytest

from bridge.dialogue import Dialogue, nettoyer_oral, valider_mobile, valider_robot
from bridge.modeles import ServiceModeles
from bridge.modeles.catalogue import FAMILLES, plus_recent
from bridge.modeles.clients import ClientGoogle, ClientLocal, ClientXAI, Reponse
from bridge.serveur import contexte_https
from atelier_p1.modeles import verifier_local

REPERES = ["centre", "avant-scene", "cour", "jardin"]


# ── Clients nuagiques ────────────────────────────────────────
def test_client_xai_requete_et_reponse():
    vus = []

    def transport(url, corps, entetes, delai):
        vus.append((url, corps, entetes))
        return {"model": "grok-4.7-0918", "choices": [{"message": {"content": '{"reponse": "Bonjour"}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4}}

    r = ClientXAI("cle", transport=transport).generer("grok-4.7", "sys", "Bonjour", temperature=0.7, max_tokens=300,
                                                      json_attendu=True)
    url, corps, entetes = vus[0]
    assert url == "https://api.x.ai/v1/chat/completions" and entetes["Authorization"] == "Bearer cle"
    assert corps["temperature"] == 0.7 and corps["max_tokens"] == 300 and corps["response_format"]["type"] == "json_object"
    assert corps["messages"][0] == {"role": "system", "content": "sys"}
    assert (r.fournisseur, r.systeme, r.modele_exact, r.jetons_entree) == ("xai", "SI-09", "grok-4.7-0918", 12)


def test_client_google_argon_ecarte_temperature_flash_la_garde():
    vus = []

    def transport(url, corps, entetes, delai):
        vus.append((url, corps, entetes))
        return {"candidates": [{"content": {"parts": [{"text": "réflexion", "thought": True}, {"text": "Réponse"}]}}],
                "usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 3}, "modelVersion": "gemini-4-argon-001"}

    c = ClientGoogle("cle", transport=transport)
    r = c.generer("gemini-4-argon", "sys", "q", temperature=0.7, top_p=0.9, json_attendu=True)
    url, corps, entetes = vus[0]
    assert url.endswith("/models/gemini-4-argon:generateContent") and entetes["x-goog-api-key"] == "cle"
    g = corps["generationConfig"]
    assert "temperature" not in g and "topP" not in g and g["responseMimeType"] == "application/json"
    assert corps["systemInstruction"]["parts"][0]["text"] == "sys"
    assert r.texte == "Réponse" and r.systeme == "SI-10" and r.modele_exact == "gemini-4-argon-001" and r.ecarts
    c.generer("gemini-3.8-flash", "sys", "q", temperature=0.7)
    assert "temperature" not in vus[1][1]["generationConfig"]                 # Gemini ≥ 3.6 : retirée, écart consigné
    c.generer("gemini-2.5-flash", "sys", "q", temperature=0.7)
    assert vus[2][1]["generationConfig"]["temperature"] == 0.7


def test_familles_grok_et_gemini():
    assert plus_recent(["grok-4", "grok-4.7", "grok-5", "grok-code-fast-1"], FAMILLES["grok"]) == "grok-5"
    assert plus_recent(["grok-4.20", "grok-4.7", "grok-4.1"], FAMILLES["grok"]) == "grok-4.7"   # 4.20 précède 4.7
    ids = ["gemini-4-argon", "gemini-3.5-argon", "gemini-4-flash", "gemini-3.8-flash", "gemini-4-flash-lite",
           "gemini-4-flash-tts"]
    assert plus_recent(ids, FAMILLES["gemini-argon"]) == "gemini-4-argon"
    assert plus_recent(ids, FAMILLES["gemini-flash"]) == "gemini-4-flash"


# ── LM Studio sur le réseau Wi-Fi local ──────────────────────
def test_reseau_local_sur_option_seulement():
    m = "luciole-8b-instruct-1.1"
    assert verifier_local(m, "http://127.0.0.1:1234") == []
    assert verifier_local(m, "http://192.168.1.20:1234")                     # refusé par défaut
    assert verifier_local(m, "http://192.168.1.20:1234", True) == []          # permis par l'option
    assert verifier_local(m, "http://studio.local:1234", True) == []
    assert verifier_local(m, "http://8.8.8.8:1234", True)                     # hôte public : toujours refusé
    assert verifier_local("gpt-oss:cloud", "http://192.168.1.20:1234", True)  # étiquette distante : refusée


# ── Service : moteur choisi par machine ──────────────────────
class FauxNuage:
    def __init__(self, f, si):
        self.f, self.si, self.appels = f, si, []

    def generer(self, modele, systeme, contenu, **kw):
        self.appels.append(modele)
        return Reponse('{"reponse": "ok", "actions": []}', self.f, self.si, modele, modele, 2, 2)


def service(tmp_path, monkeypatch, **cfg):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.setenv(k, "x")
    appels = []

    def transport(url, corps, entetes, delai):
        appels.append(corps["model"])
        return {"model": corps["model"], "choices": [{"message": {"content": '{"reponse": "local", "actions": []}'}}]}

    entrees = [{"name": "luciole-8b-instruct-1.1"}, {"name": "qwen3-14b"},
               {"name": "text-embedding-nomic", "type": "embeddings"}, {"name": "mistral-small", "device": "Studio du voisin"}]
    local = ClientLocal("luciole-8b-instruct-1.1", transport=transport, lister=lambda: entrees,
                        reseau_local=cfg.get("reseau_local", False))
    nuages = {"anthropic": FauxNuage("anthropic", "SI-01"), "openai": FauxNuage("openai", "SI-08"),
              "xai": FauxNuage("xai", "SI-09"), "google": FauxNuage("google", "SI-10"), "local": local}
    s = ServiceModeles(cfg, tmp_path, clients=nuages, listeurs={f: (lambda c: []) for f in ("anthropic", "openai", "xai", "google")})
    s.ouvrir_seance("20261020_P1_A_001")
    return s, nuages, appels


def test_choix_par_machine(tmp_path, monkeypatch):
    s, n, appels = service(tmp_path, monkeypatch)
    ids = [m["id"] for m in s.moteurs()]
    assert {"auto", "claude-sonnet", "grok", "gemini-argon", "gemini-flash"} <= set(ids)
    assert "local:qwen3-14b" in ids and "local:luciole-8b-instruct-1.1" in ids
    assert not any("embed" in i or "mistral" in i for i in ids)            # plongement et instance distante écartés
    s.choisir("chien", "grok")
    s.choisir("drone", "local:qwen3-14b")
    s.choisir("robot", "gemini-flash")
    assert s.generer_sync("rapide", "sys", "Bonjour", domaine="chien").systeme == "SI-09"
    assert s.generer_sync("rapide", "sys", "Bonjour", domaine="robot").systeme == "SI-10"
    r = s.generer_sync("rapide", "sys", "Bonjour", domaine="drone")
    assert r.modele_exact == "qwen3-14b" and appels[-1] == "qwen3-14b"
    assert s.generer_sync("rapide", "sys", "Bonjour").systeme == "SI-01"   # hors domaine : ordre des rôles
    assert s.resume()["choix"]["drone"] == "local:qwen3-14b"
    with pytest.raises(ValueError):
        s.choisir("chien", "inconnu")
    with pytest.raises(ValueError):
        s.choisir("grille", "grok")


def test_d03_prime_sur_le_choix(tmp_path, monkeypatch):
    s, n, appels = service(tmp_path, monkeypatch)
    s.choisir("chien", "grok")
    r = s.generer_sync("rapide", "sys", "Écrire à lea@exemple.org", domaine="chien")
    assert r.systeme == "SI-02" and appels[-1] == "luciole-8b-instruct-1.1" and not n["xai"].appels


def test_lmstudio_sur_le_wifi(tmp_path, monkeypatch):
    s = ServiceModeles({"url_local": "http://192.168.1.20:1234"}, tmp_path)
    assert s.local.refus                                                      # sans l'option : refusé
    s2 = ServiceModeles({"url_local": "http://192.168.1.20:1234", "reseau_local": True}, tmp_path / "b")
    assert s2.local.refus == [] and s2.reseau_local


# ── Dialogue ─────────────────────────────────────────────────
def test_vocabulaire_ferme_mobile():
    ok, rejets = valider_mobile("chien", [
        {"type": "lever"}, {"type": "aller", "repere": "centre"}, {"type": "aller", "repere": "loge"},
        {"type": "deplacer", "avant": 12}, {"type": "posture", "nom": "assis"}, {"type": "urgence"},
        {"type": "decoller"}, {"type": "allure", "nom": "joyeux"}], REPERES)
    assert [a["type"] for a in ok] == ["lever", "aller", "deplacer", "posture", "allure"]
    assert ok[2]["avant"] == 3                                                 # borné
    motifs = " ".join(r["motif"] for r in rejets)
    assert "repère inexistant" in motifs and "interdit au modèle" in motifs and "type d'action inconnu" in motifs
    ok, _ = valider_mobile("drone", [{"type": "decoller", "hauteur": 9}, {"type": "deplacer", "haut": 1}], REPERES)
    assert ok == [{"type": "decoller", "hauteur": 3}, {"type": "deplacer", "avant": 0, "droite": 0, "haut": 1}]


def test_vocabulaire_robot():
    ok, rejets = valider_robot([{"type": "geste", "nom": "saluer"}, {"type": "articulation", "dof": "x"},
                                {"type": "emotion", "nom": "joie", "intensite": 50}])
    assert any(r["motif"] == "type non permis en dialogue" for r in rejets)
    assert all(a["type"] in ("geste", "emotion") for a in ok)


class ServiceFaux:
    def __init__(self, texte="", dispo=True):
        self.texte, self.dispo, self.vus = texte, dispo, []

    def disponible(self, role="analyse", domaine=None):
        return self.dispo

    async def generer(self, role, systeme, contenu, **kw):
        self.vus.append((systeme, contenu, kw))
        return Reponse(self.texte, "xai", "SI-09", "grok-4.7", "grok-4.7", 1, 1, famille="grok")


def test_dialogue_reponse_actions_et_memoire():
    sf = ServiceFaux(json.dumps({"reponse": "**Avec plaisir !** 🐶 Je peux m'asseoir si on me le permet.",
                                 "actions": [{"type": "posture", "nom": "assis"}, {"type": "urgence"}]}))
    d = Dialogue(sf)
    r = asyncio.run(d.repondre("chien", "Tu peux t'asseoir ?", reperes=REPERES, contexte="debout au centre"))
    assert r["reponse"] == "Avec plaisir ! Je peux m'asseoir si on me le permet."
    assert r["actions"] == [{"type": "posture", "nom": "assis"}] and len(r["rejets"]) == 1
    assert r["moteur"] == "grok-4.7" and sf.vus[0][2]["domaine"] == "chien" and sf.vus[0][2]["json_attendu"]
    assert "debout au centre" in sf.vus[0][0] and "centre" in sf.vus[0][0]
    asyncio.run(d.repondre("chien", "Et maintenant ?", reperes=REPERES))
    assert "Tu peux t'asseoir ?" in sf.vus[1][1]                               # mémoire courte
    d.oublier("chien")
    asyncio.run(d.repondre("chien", "Bonjour", reperes=REPERES))
    assert "Tu peux t'asseoir" not in sf.vus[2][1]


def test_dialogue_sans_moteur_et_refus():
    d = Dialogue(ServiceFaux(dispo=False))
    r = asyncio.run(d.repondre("drone", "Bonjour !"))
    assert r["moteur"] == "déterministe" and r["reponse"].startswith("Bonjour")
    with pytest.raises(ValueError):
        asyncio.run(d.repondre("grille-pain", "Bonjour"))
    with pytest.raises(ValueError):
        asyncio.run(d.repondre("robot", "   "))

    class Refus(ServiceFaux):
        async def generer(self, *a, **kw):
            raise RuntimeError("contenu sensible sans modèle local")
    r = asyncio.run(Dialogue(Refus()).repondre("robot", "Bonjour"))
    assert r["actions"] == [] and "RuntimeError" in r["erreur"]


def test_nettoyer_oral_coupe_a_une_fin_de_phrase():
    t = nettoyer_oral("# Titre\n" + "Une phrase assez longue pour le test. " * 30)
    assert len(t) <= 600 and t.endswith(".") and "#" not in t


# ── HTTPS du pont (micro des tablettes en Wi-Fi) ─────────────
def test_https_facultatif(tmp_path):
    assert contexte_https({}, tmp_path) is None
    with pytest.raises(SystemExit):
        contexte_https({"certificat": "c.pem"}, tmp_path)
    with pytest.raises(SystemExit):
        contexte_https({"certificat": "c.pem", "cle": "k.pem"}, tmp_path)
