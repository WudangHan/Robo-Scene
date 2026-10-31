"""Voix humaine : partition prosodique, moteurs neuronaux (transports simulés), service hybride (cache, D03,
repli), routes du pont et client JavaScript. python -m pytest -q tests/test_voix.py"""
import asyncio
import base64
import json
import shutil
import subprocess
import xml.dom.minidom

import pytest

from bridge.partenaire import variations as V
from bridge.serveur import RACINE
from bridge.voix import partition as P
from bridge.voix.moteurs import (Audio, MoteurAzure, MoteurElevenLabs, MoteurOpenAI, MoteurPiper, concatener_wav,
                                 duree_wav_ms, mots_depuis_alignement, pcm_vers_wav)
from bridge.voix.service import ServiceVoix
from atelier_p1.routeur import Routeur

NODE = shutil.which("node")
TIRADE = "Hélas, mon ami, je ne reviendrai jamais. Tu m'entends ? Jamais… Adieu, adieu donc, et que le ciel te garde !"


def wav(ms=500, taux=24000):
    return pcm_vers_wav(b"\x01\x00" * int(taux * ms / 1000), taux)


# ── Partition ─────────────────────────────────────────────────────────────────────────────────────
def test_une_phrase_par_enonce_jamais_par_virgule():
    p = P.construire(TIRADE, V.variation("tristesse", 8))
    assert [s["texte"] for s in p["phrases"]] == ["Hélas, mon ami, je ne reviendrai jamais.", "Tu m'entends ?",
                                                  "Jamais…", "Adieu, adieu donc, et que le ciel te garde !"]
    assert [s["type"] for s in p["phrases"]] == ["assertion", "question", "suspension", "exclamation"]
    assert p["phrases"][-1]["pause_apres_ms"] == 0 and all(s["pause_apres_ms"] > 0 for s in p["phrases"][:-1])


def test_rendu_navigateur_ne_hache_plus_aux_virgules():
    r = V.rendu_voix(TIRADE, V.variation("tristesse", 8))
    assert len(r["segments"]) == 4 and "partition" in r
    assert all("," not in s["texte"][-1] for s in r["segments"])
    assert len({s["debit"] for s in r["segments"]}) > 1               # tempo propre à chaque phrase
    assert all(0.6 <= s["debit"] <= 1.6 and 0.4 <= s["hauteur"] <= 1.6 for s in r["segments"])
    mach = V.rendu_voix(TIRADE, V.variation("colère", 9), "machinique")
    assert "partition" not in mach and mach["hauteur"] == 0.6          # voie machinique inchangée


def test_partition_deterministe_et_arc():
    v = V.variation("colère", 9)
    a, b = P.construire(TIRADE, v), P.construire(TIRADE, v)
    assert a == b
    loc = [s["intensite_locale"] for s in a["phrases"]]
    assert loc[-1] > loc[0]                                             # la colère monte
    t = P.construire(TIRADE, V.variation("tristesse", 9))
    assert t["phrases"][0]["intensite_locale"] > t["phrases"][2]["intensite_locale"]   # la tristesse s'éteint
    assert P.construire("", v)["phrases"] == []


def test_insistance_et_chuchotement():
    p = P.construire("Je ne te pardonnerai jamais, entends-tu ?", V.variation("colère", 7))
    assert p["phrases"][0]["insistance"] == "jamais"
    assert P.construire("Viens VITE ici.", V.variation("peur", 6))["phrases"][0]["insistance"] == "VITE"
    ch = P.construire("Il nous écoute.", V.variation("peur", 6), marques={"chuchote": True})
    assert ch["phrases"][0]["qualite"] == "chuchotée" and ch["phrases"][0]["volume"] <= 0.45
    assert P.construire("Bon.", V.variation("neutre", 2))["phrases"][0]["insistance"] is None


def test_traductions_par_moteur():
    p = P.construire(TIRADE, V.variation("tristesse", 8), personnage="Alcmène")
    el = P.vers_elevenlabs(p)
    assert el["text"].startswith("[") and "[sad]" in el["text"] or "[crying]" in el["text"]
    assert "<break" not in el["text"] and 0.7 <= el["voice_settings"]["speed"] <= 1.2
    assert el["voice_settings"]["stability"] in (0.0, 0.5, 1.0)
    oa = P.vers_openai(p)
    assert "québécois" in oa["instructions"] and "Alcmène" in oa["instructions"] and "tristesse" in oa["instructions"]
    assert oa["input"] == P.texte_brut(p) and 0.8 <= oa["speed"] <= 1.25
    for emo in V.EMOTIONS:
        ssml = P.vers_ssml(P.construire(TIRADE + " Qui va là ?", V.variation(emo, 9)), "fr-CA-ThierryNeural")
        xml.dom.minidom.parseString(ssml)                               # SSML bien formé pour toute émotion
    assert 'xml:lang="fr-CA"' in ssml and "<break" in ssml
    pip = P.vers_piper(p)
    assert len(pip) == 4 and all(s["length_scale"] > 0 for s in pip)
    ironie = P.vers_ssml(P.construire("Toi & moi < eux ?", V.variation("ironie", 6)), "fr-CA-JeanNeural")
    xml.dom.minidom.parseString(ironie)                                 # échappement XML


# ── Moteurs (transports simulés : aucun appel réseau) ─────────────────────────────────────────────
def test_elevenlabs_requete_et_alignement(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "cle-test")
    vus = {}

    def transport(url, corps, entetes, delai):
        vus.update(url=url, corps=json.loads(corps), entetes=entetes)
        texte = "[sad] Oui… non."
        al = {"characters": list(texte), "character_start_times_seconds": [i * 0.05 for i in range(len(texte))]}
        return json.dumps({"audio_base64": base64.b64encode(b"\x00\x00" * 24000).decode(), "alignment": al}).encode(), "application/json"

    m = MoteurElevenLabs({"voix_partenaire": ["VOIX1"]}, transport)
    assert m.disponible() == (True, "")
    a = m.synthetiser(P.construire("Oui… non.", V.variation("tristesse", 6)), "VOIX1")
    assert "/v1/text-to-speech/VOIX1/with-timestamps" in vus["url"] and "pcm_24000" in vus["url"]
    assert vus["corps"]["model_id"] == "eleven_v3" and vus["corps"]["language_code"] == "fr"
    assert vus["entetes"]["xi-api-key"] == "cle-test"
    assert a.format == "wav" and a.duree_ms == 1000
    assert [w["mot"] for w in a.mots] == ["Oui", "non"] and a.mots[0]["t_ms"] == 300


def test_alignement_ignore_les_balises():
    al = {"characters": list("[sighs] Je pars"), "character_start_times_seconds": [i / 10 for i in range(15)]}
    assert mots_depuis_alignement(al) == [{"mot": "Je", "t_ms": 800}, {"mot": "pars", "t_ms": 1100}]


def test_azure_ssml_quebecois(monkeypatch):
    monkeypatch.setenv("AZURE_SPEECH_KEY", "k")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "canadacentral")
    vus = {}

    def transport(url, corps, entetes, delai):
        vus.update(url=url, ssml=corps.decode(), entetes=entetes)
        return wav(700), "audio/wav"

    m = MoteurAzure({"voix_partenaire": ["fr-CA-ThierryNeural"]}, transport)
    a = m.synthetiser(P.construire(TIRADE, V.variation("colère", 8)), "fr-CA-ThierryNeural")
    assert vus["url"] == "https://canadacentral.tts.speech.microsoft.com/cognitiveservices/v1"
    assert vus["entetes"]["X-Microsoft-OutputFormat"] == "riff-24khz-16bit-mono-pcm"
    assert 'name="fr-CA-ThierryNeural"' in vus["ssml"] and 'xml:lang="fr-CA"' in vus["ssml"]
    assert a.duree_ms == 700 and a.envoye["ssml"] == vus["ssml"]
    monkeypatch.delenv("AZURE_SPEECH_REGION")
    assert MoteurAzure({"voix_partenaire": ["x"]}).disponible()[0] is False


def test_openai_consigne_de_jeu(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    vus = {}

    def transport(url, corps, entetes, delai):
        vus.update(url=url, corps=json.loads(corps))
        return wav(400), "audio/wav"

    a = MoteurOpenAI({"voix_partenaire": ["ash"]}, transport).synthetiser(
        P.construire("Va-t'en !", V.variation("colère", 9)), "ash")
    assert vus["url"].endswith("/v1/audio/speech") and vus["corps"]["model"] == "gpt-4o-mini-tts"
    assert vus["corps"]["response_format"] == "wav" and "colère" in vus["corps"]["instructions"]
    assert a.voix == "ash" and a.duree_ms == 400


def test_piper_local_concatene_les_phrases():
    appels = []

    def executer(modele, texte, ls, ns, nw):
        appels.append((texte, ls))
        return wav(300, 22050)

    m = MoteurPiper({"voix_partenaire": ["fr_FR-tom-medium"]}, executer=executer)
    a = m.synthetiser(P.construire("Oui. Non !", V.variation("joie", 5)), "fr_FR-tom-medium")
    assert [t for t, _ in appels] == ["Oui.", "Non !"] and a.distant is False
    assert a.duree_ms >= 600 and duree_wav_ms(concatener_wav([(wav(100), 100)])) == 200


def test_moteur_sans_cle_ou_sans_voix_indisponible(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert MoteurElevenLabs({"voix_partenaire": ["x"]}).disponible()[0] is False
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    assert MoteurElevenLabs({}).disponible() == (False, "aucune voix configurée")


# ── Service hybride ───────────────────────────────────────────────────────────────────────────────
class Faux:
    def __init__(self, nom, distant=True, echec=False):
        self.nom, self.libelle, self.distant, self.echec, self.appels = nom, nom, distant, echec, 0
        self.cfg = {}

    def disponible(self):
        return True, ""

    def voix_pour(self, role, indice=0, profil=None):
        return f"{self.nom}-{role}-{profil or indice}"

    def empreinte(self):
        return {"moteur": self.nom}

    def synthetiser(self, part, voix):
        self.appels += 1
        if self.echec:
            from bridge.voix.moteurs import ErreurVoix
            raise ErreurVoix("quota dépassé")
        return Audio(wav(250), "wav", 250, self.nom, "m", voix, distant=self.distant)


def service(tmp_path, moteurs, routeur=None):
    return ServiceVoix({"ordre": list(moteurs)}, tmp_path, routeur=routeur, moteurs=moteurs)


def test_cache_et_nouvelle_prise(tmp_path):
    f = Faux("azure")
    s = service(tmp_path, {"azure": f})
    v = V.variation("joie", 6)
    a = asyncio.run(s.rendre("Quelle belle journée !", v, personnage="Sosie"))
    b = asyncio.run(s.rendre("Quelle belle journée !", v, personnage="Sosie"))
    assert a["statut"] == b["statut"] == "audio" and a["cle"] == b["cle"] and f.appels == 1
    assert s.chemin(a["url"].split("/")[-1]) is not None
    meta = json.loads((s.cache / f"{a['cle']}.json").read_text(encoding="utf-8"))
    assert meta["provenance"].startswith("machine") and meta["moteur"] == "azure" and meta["texte"]
    c = asyncio.run(s.rendre("Quelle belle journée !", v, personnage="Sosie", prise=1))
    assert c["cle"] != a["cle"] and f.appels == 2
    assert s.chemin("../config.toml") is None and s.chemin("a" * 64 + ".exe") is None


def test_repli_et_ordre_des_moteurs(tmp_path):
    casse, bon = Faux("elevenlabs", echec=True), Faux("openai")
    s = service(tmp_path, {"elevenlabs": casse, "openai": bon})
    r = asyncio.run(s.rendre("Bonjour.", None))
    assert r["moteur"] == "openai" and casse.appels == 1 and "quota" in s.etat()["moteurs"][0]["derniere_erreur"]
    vide = ServiceVoix({"ordre": []}, tmp_path, moteurs={})
    r = asyncio.run(vide.rendre("Bonjour, toi.", V.variation("joie", 5)))
    assert r["statut"] == "repli" and len(r["segments"]) == 1 and r["consigne"]


def test_d03_contenu_sensible_jamais_distant(tmp_path):
    distant, local = Faux("azure"), Faux("piper", distant=False)
    s = service(tmp_path, {"azure": distant, "piper": local}, Routeur(["eloise tremblay"]))
    r = asyncio.run(s.rendre("Éloïse Tremblay, écris-moi à eloise@exemple.ca.", None))
    assert r["moteur"] == "piper" and distant.appels == 0 and r["routage"]
    s2 = service(tmp_path, {"azure": Faux("azure")}, Routeur([]))
    r = asyncio.run(s2.rendre("Appelle le 418 555 1234.", None))
    assert r["statut"] == "repli" and r["local_seulement"] is True


def test_machinique_et_muet_restent_au_navigateur(tmp_path):
    f = Faux("azure")
    s = service(tmp_path, {"azure": f})
    assert asyncio.run(s.rendre("Bip.", None, regime="machinique"))["statut"] == "repli"
    assert asyncio.run(s.rendre("Bip.", None, parler=False))["statut"] == "repli"
    assert f.appels == 0


def test_distribution_et_prerendu(tmp_path):
    f = Faux("azure")
    s = service(tmp_path, {"azure": f})
    s.distribuer("Jupiter", "azure", "fr-CA-JeanNeural")
    r = asyncio.run(s.rendre("Je suis le maître.", None, personnage="Jupiter"))
    assert r["voix"] == "fr-CA-JeanNeural"
    vus = []

    async def progres(fait, total, r):
        vus.append((fait, total, r["statut"]))

    items = [{"id": "E1", "texte": "Un.", "personnage": "A"}, {"id": "E2", "texte": "Deux.", "personnage": "B", "indice": 1}]
    out = asyncio.run(s.prerendre(items, progres))
    assert [o["id"] for o in out] == ["E1", "E2"] and vus == [(1, 2, "audio"), (2, 2, "audio")]
    assert out[0]["voix"] != out[1]["voix"]
    with pytest.raises(ValueError):
        s.distribuer("X", "inconnu", "v")


def test_etat_sans_cle_par_defaut(tmp_path, monkeypatch):
    for k in ("ELEVENLABS_API_KEY", "AZURE_SPEECH_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    e = ServiceVoix({}, tmp_path).etat()
    assert [m["id"] for m in e["moteurs"]] == ["elevenlabs", "azure", "openai", "piper"]
    assert e["actif"] is None and all(m["motif"] for m in e["moteurs"])


# ── Pont : opérations voix_* et route /voix/ ──────────────────────────────────────────────────────
def test_pont_rendu_route_et_cors(tmp_path):
    from aiohttp.test_utils import TestClient, TestServer
    from bridge.serveur import charger_config, creer_app

    async def scenario():
        cfg = charger_config(RACINE / "config.toml")
        cfg["donnees"] = {"dossier": str(tmp_path)}
        cfg["protocole"]["dossier_corpus"] = str(tmp_path / "corpus")
        cfg["protocole"]["versionner_corpus"] = False
        app = creer_app(cfg)
        async with TestClient(TestServer(app)) as cl:
            from bridge.serveur import CTL
            ctl = app[CTL]
            ctl.voix.moteurs = {"azure": Faux("azure")}
            ctl.voix.ordre = ["azure"]
            ws = await cl.ws_connect("/ws")
            await ws.send_json({"op": "voix_etat"})
            await ws.send_json({"op": "voix_rendre", "jeton": "v1", "texte": "Bonjour, Sosie.", "variation": {"emotion": "joie", "intensite": 6}})
            vus = {}
            while len(vus) < 2:
                m = await ws.receive_json(timeout=10)
                if m.get("type") in ("voix_etat", "voix_rendu"):
                    vus[m["type"]] = m
            assert vus["voix_etat"]["actif"] == "azure"
            r = vus["voix_rendu"]
            assert r["jeton"] == "v1" and r["statut"] == "audio" and r["url"].startswith("/voix/")
            rep = await cl.get(r["url"], headers={"Origin": "https://robo-scene.netlify.app"})
            assert rep.status == 200 and rep.headers["Content-Type"] == "audio/wav"
            assert rep.headers["Access-Control-Allow-Origin"] == "https://robo-scene.netlify.app"
            assert (await rep.read())[:4] == b"RIFF"
            rep = await cl.get(r["url"], headers={"Origin": "https://malveillant.example"})
            assert "Access-Control-Allow-Origin" not in rep.headers
            assert (await cl.get("/voix/" + "0" * 64 + ".wav")).status == 404
            await ws.send_json({"op": "voix_prerendre", "jeton": "p1", "items": [{"id": "E1", "texte": "Un."}]})
            types = set()
            while "voix_progres" not in types:
                types.add((await ws.receive_json(timeout=10)).get("type"))
            assert "voix_prerendu_lance" in types
            await ws.close()

    asyncio.run(scenario())


# ── Client JavaScript ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.skipif(not NODE, reason="Node.js absent")
def test_client_js():
    script = """
      require("./web/voix-neurale.js");
      const V = globalThis.VoixNeurale;
      const envoyes = [];
      const c = V.creer({ envoyer: (op, d) => envoyes.push({ op, ...d }), urlWs: () => "wss://192.168.1.20:8765/ws" });
      const out = {};
      out.base = V.base("ws://127.0.0.1:8765/ws");
      c.surMessage({ type: "voix_etat", actif: "azure", moteurs: [] });
      out.actif = c.actif();
      const p = c.rendre({ texte: "Oui." }, 1000);
      c.surMessage({ type: "voix_rendu", jeton: envoyes[0].jeton, statut: "audio", url: "/voix/x.wav", duree_ms: 900 });
      p.then((r) => {
        out.url = r.url;
        c.surMessage({ type: "voix_progres", jeton: "p9", id: "E7", fait: 1, total: 1, statut: "audio", url: "/voix/y.wav" });
        out.pre = c.prerendu("E7").url;
        out.ignore = c.surMessage({ type: "etat" });
        out.items = V.itemsRepetition({ items: [
          { type: "replique", acteur: false, id: "E1", perso: "a", nom: "A", texte: "Un.", variation: {}, voix: { parler: true, type_voix: "humain", debit: 1, hauteur: 1, volume: 0.8 } },
          { type: "replique", acteur: true, id: "E2", perso: "b" },
          { type: "replique", acteur: false, id: "E3", perso: "c", nom: "C", texte: "Bip.", voix: { parler: true, type_voix: "machinique" } },
          { type: "replique", acteur: false, id: "E4", perso: "c", nom: "C", texte: "Trois.", voix: { parler: true, type_voix: "humain" } } ] }).map((x) => [x.id, x.indice]);
        console.log(JSON.stringify(out));
      });
    """
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["base"] == "http://127.0.0.1:8765" and out["actif"] is True
    assert out["url"] == "https://192.168.1.20:8765/voix/x.wav" and out["pre"].endswith("/voix/y.wav")
    assert out["ignore"] is False and out["items"] == [["E1", 0], ["E4", 1]]


# ── Robot physique : le SDK joue le son rendu par le pont, sinon se rabat sur sa synthèse embarquée ─
def test_sdk_audio_et_repli():
    import importlib.util
    spec = importlib.util.spec_from_file_location("robo_scene_sdk", RACINE / "sdk/python/robo_scene_sdk.py")
    sdk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sdk)

    class Robot(sdk.PiloteRobot):
        def __init__(self, sait_jouer):
            super().__init__()
            self.sait_jouer, self.joues, self.dits, self.sortie = sait_jouer, [], [], []
            self._ecrire = self.sortie.append

        def jouer_audio(self, donnees, format, texte=""):
            if self.sait_jouer:
                self.joues.append((donnees, format, texte))
            return self.sait_jouer

        def dire(self, texte):
            self.dits.append(texte)
            return True

    son = wav(100)
    msg = json.dumps({"t": "audio", "format": "wav", "texte": "Bonjour.", "b64": base64.b64encode(son).decode()})
    r = Robot(True)
    r.traiter(msg)
    assert r.joues == [(son, "wav", "Bonjour.")] and not r.dits
    r = Robot(False)
    r.traiter(msg)
    assert r.dits == ["Bonjour."]
    r = Robot(True)
    r.estop = True
    r.traiter(msg)
    assert not r.joues and "estop" in r.sortie[-1]


def test_pont_envoie_le_son_au_robot(tmp_path):
    from bridge.serveur import Controleur, charger_config

    async def scenario():
        cfg = charger_config(RACINE / "config.toml")
        cfg["donnees"] = {"dossier": str(tmp_path)}
        cfg["protocole"]["dossier_corpus"] = str(tmp_path / "corpus")
        cfg["protocole"]["versionner_corpus"] = False
        ctl = Controleur(cfg)
        ctl.voix.moteurs, ctl.voix.ordre = {"azure": Faux("azure")}, ["azure"]
        r = ctl.robot
        envoyes = []

        async def envoyer(m):
            envoyes.append(m)
        r.envoyer = envoyer
        r.securite._verifier_arme = lambda: None
        r.desc.capacites = ["dire"]
        await ctl.cmd_dire("Bonjour à tous.", "manuel")
        assert envoyes[-1] == {"t": "dire", "texte": "Bonjour à tous."}
        r.desc.capacites = ["dire", "audio"]
        await ctl.cmd_dire("Bonjour à tous.", "manuel")
        assert envoyes[-1]["t"] == "audio" and base64.b64decode(envoyes[-1]["b64"])[:4] == b"RIFF"

    asyncio.run(scenario())
