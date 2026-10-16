"""Tests de bout en bout sur le robot simulé : python -m pytest -q"""
import asyncio
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bridge.securite import CommandeRefusee, Limites, Securite
from bridge.serveur import CTL, RACINE, charger_config, creer_app


# ── Couche de sécurité ─────────────────────────────────────
def lim():
    return Limites([10, 20], [170, 160], [90, 90], vitesse_max_deg_s=90, propulsion_max=0.5)


def test_bornage_et_ralentissement():
    s = Securite(lim())
    sures, duree, avert = s.valider_articulations([200, None], [90, 90], 0)
    assert sures == [170, 90]
    assert duree == pytest.approx(1000 * 80 / 90)
    assert any("bornée" in a for a in avert) and any("ralenti" in a for a in avert)


def test_arret_urgence_verrouille():
    s = Securite(lim())
    s.declencher_arret("test")
    with pytest.raises(CommandeRefusee):
        s.valider_articulations([90, 90], [90, 90], 500)
    with pytest.raises(CommandeRefusee):
        s.valider_propulsion(0.2, 0.2)
    s.rearmer()
    assert s.valider_propulsion(0.9, -0.9)[:2] == (0.5, -0.5)


# ── Bout en bout ───────────────────────────────────────────
@pytest.fixture
def cfg(tmp_path):
    c = charger_config(RACINE / "config.toml")
    c["robot"]["transport"] = "sim"
    c["protocole"]["dossier_corpus"] = str(tmp_path / "corpus")
    c["ia"]["execution_auto"] = False
    c["donnees"] = {"dossier": str(tmp_path / "donnees")}
    c["flotte"] = {"dossier_profils": "robots_absent"}
    return c


async def attendre(ws, pred, delai=4.0):
    async def boucle():
        while True:
            m = json.loads((await ws.receive()).data)
            if pred(m):
                return m
    return await asyncio.wait_for(boucle(), delai)


def run(coro):
    return asyncio.run(coro)


def test_scenario_complet(cfg, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # moteur de règles, déterministe

    async def scenario():
        app = creer_app(cfg)
        async with TestClient(TestServer(app)) as cl:
            ws = await cl.ws_connect("/ws")
            conf = await attendre(ws, lambda m: m["type"] == "config")
            assert conf["noms"] == ["Base", "Épaule", "Coude", "Tête"]
            await attendre(ws, lambda m: m["type"] == "etat" and m["lien"] == "connecte")

            # 1. Commande hors limites → bornée, ralentie, puis atteinte
            await ws.send_json({"op": "articulation", "i": 1, "deg": 999, "ms": 0})
            await attendre(ws, lambda m: m["type"] == "etat" and abs(m["deg"][1] - 160) < 0.5, 3)

            # 2. Arrêt d'urgence : commandes refusées jusqu'au réarmement
            await ws.send_json({"op": "estop"})
            await attendre(ws, lambda m: m["type"] == "etat" and m["arret"] and m.get("estop"))
            await ws.send_json({"op": "repos"})
            await attendre(ws, lambda m: m["type"] == "journal" and m["niveau"] == "refus")
            await ws.send_json({"op": "rearmer"})
            await attendre(ws, lambda m: m["type"] == "etat" and not m["arret"] and not m.get("estop"))

            # 3. Propulsion : homme mort → arrêt automatique
            await ws.send_json({"op": "propulsion", "g": 0.4, "d": 0.4})
            await attendre(ws, lambda m: m["type"] == "etat" and m["drive"][0] > 0)
            await attendre(ws, lambda m: m["type"] == "etat" and m["drive"] == [0, 0], 2)

            # 4. IA : proposition validable puis exécutée ; consigne obscure bloquée
            await ws.send_json({"op": "ia_demander", "texte": "fais le salut"})
            p = await attendre(ws, lambda m: m["type"] == "ia_proposition")
            assert p["action"] == "sequence" and p["statut"] == "a_valider"
            await ws.send_json({"op": "ia_valider", "id": p["id"]})
            await attendre(ws, lambda m: m["type"] == "etat" and m["sequence"] == "salut")
            await ws.send_json({"op": "seq_arreter"})
            await ws.send_json({"op": "ia_demander", "texte": "chante une chanson"})
            p2 = await attendre(ws, lambda m: m["type"] == "ia_proposition")
            assert p2["statut"] == "bloquee"
            await ws.send_json({"op": "ia_valider", "id": p2["id"]})
            await attendre(ws, lambda m: m["type"] == "journal" and m["niveau"] == "refus")

            # 5. Note observationnelle
            await ws.send_json({"op": "note", "texte": "Réaction du public au salut"})
            await attendre(ws, lambda m: m["type"] == "journal" and "Note" in m["msg"])
            await ws.close()
            return app[CTL].seance

    seance = run(scenario())
    meta = json.loads(seance.chemin_meta.read_text(encoding="utf-8"))
    assert meta["identifiant"].endswith("_ESP32_S04_001")
    assert meta["fin"] is not None
    c = meta["compteurs"]
    assert c["arrets_urgence"] >= 1 and c["commandes_refusees"] >= 2
    assert c["propositions_ia"] == 2 and c["ia_validees"] == 1 and c["ia_bloquees_seuil"] == 1
    assert meta["notes_observationnelles"][0]["texte"].startswith("Réaction")
    lignes = [json.loads(l) for l in seance.chemin_evt.read_text(encoding="utf-8").splitlines()]
    cats = {l["cat"] for l in lignes}
    assert {"cmd", "ia", "ia_decision", "tel", "refus", "sequence"} <= cats
    ia = next(l for l in lignes if l["cat"] == "ia")
    assert "prompt" in ia  # le prompt intégral est archivé (exigence 6.1)


def test_obstacle_fait_baisser_la_confiance(cfg, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    async def scenario():
        app = creer_app(cfg)
        async with TestClient(TestServer(app)) as cl:
            ws = await cl.ws_connect("/ws")
            await attendre(ws, lambda m: m["type"] == "etat" and m["lien"] == "connecte" and m.get("dist") is not None)
            await ws.send_json({"op": "ia_demander", "texte": "avance"})
            return await attendre(ws, lambda m: m["type"] == "ia_proposition")

    # La télémétrie peut réécrire dist entre-temps : on fige la valeur
    from bridge import transports
    monkeypatch.setattr(transports.TransportSimule, "_distance_mur", staticmethod(lambda *a: 0.25))
    cfg["ia"]["regle"] = "angles_s04"      # séance S04 déclarée : propositions de déplacement permises
    p = run(scenario())
    assert p["action"] == "propulsion"
    assert p["confiance_verification"] <= 0.3 and p["statut"] == "bloquee"


def test_sequence_enregistrement_et_numerotation(cfg):
    async def scenario():
        noms = []
        for _ in range(2):
            app = creer_app(cfg)
            async with TestClient(TestServer(app)) as cl:
                ws = await cl.ws_connect("/ws")
                await attendre(ws, lambda m: m["type"] == "config")
                await ws.send_json({"op": "seq_enregistrer", "sequence": {
                    "nom": "test auto", "images": [{"deg": [90, 90, 90, 90], "ms": 300}]}})
                await attendre(ws, lambda m: m["type"] == "sequences" and "test auto" in m["liste"])
                noms.append(app[CTL].seance.id)
        return noms

    try:
        ids = run(scenario())
        assert ids[0].endswith("_001") and ids[1].endswith("_002")
    finally:
        (RACINE / "sequences" / "test auto.json").unlink(missing_ok=True)


# ── Moteur de modèle simulé (aucun appel réseau) ───────────
class _Service:
    def __init__(self, texte=None, erreur=None):
        self.texte, self.erreur, self.appel = texte, erreur, None

    def disponible(self, role="analyse"):
        return True

    def moteur(self, role="analyse"):
        return "claude-sonnet-5-5"

    async def generer(self, role, systeme, contenu, **kw):
        from bridge.modeles.clients import Reponse
        self.appel = {"role": role, "systeme": systeme, **kw}
        if self.erreur:
            raise self.erreur
        return Reponse(self.texte, "anthropic", "SI-01", "claude-sonnet-5-5", "claude-sonnet-5-5", 5, 9,
                       {"temperature": kw.get("temperature")}, {"temperature": kw.get("temperature")}, [])


LIMS = {"min_deg": [10, 20, 15, 30], "max_deg": [170, 160, 165, 150],
        "repos": [90] * 4, "propulsion_active": True}


def test_moteur_modele_analyse_et_parametres():
    from bridge.ia import Agent
    a = Agent({"temperature": 0.2, "max_tokens": 300}, ["Base", "Épaule", "Coude", "Tête"],
              _Service('```json\n{"action":"repos","parametres":{},"confiance":0.92,"justification":"ok"}\n```'))
    p = run(a.proposer("reviens au repos", {"deg": [90] * 4}, LIMS, []))
    assert p["action"] == "repos" and p["confiance"] == 0.92 and p["moteur"] == "anthropic:claude-sonnet-5-5"
    kw = a.service.appel
    assert kw["role"] == "commande" and kw["temperature"] == 0.2 and "top_p" not in kw
    assert "bibliothèque fermée" in kw["systeme"]          # règle par défaut (G.5)
    assert p["trace_modele"]["version_modele"] == "claude-sonnet-5-5"


def test_moteur_modele_repli_sur_regles():
    from bridge.ia import Agent
    a = Agent({}, ["Base", "Épaule", "Coude", "Tête"], _Service(erreur=TimeoutError()))
    p = run(a.proposer("stop", {}, LIMS, []))
    assert p["moteur"] == "regles (repli)" and p["action"] == "propulsion"


# ── Simulation dans le navigateur (audit du 2026-10-16, chantier 3) ─────────────────────────
def test_simulateur_navigateur_reproduit_le_pont():
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js absent")
    script = """
      import fs from "node:fs";
      globalThis.window = globalThis;
      new Function(fs.readFileSync("./web/simulateur.js", "utf8"))();
      const recus = [];
      const ws = new window.ROBO_SIMULATEUR.PontSimule();
      ws.onmessage = (e) => recus.push(JSON.parse(e.data));
      const pause = (ms) => new Promise((r) => setTimeout(r, ms));
      await pause(50);
      ws.send(JSON.stringify({ op: "articulation", i: 1, deg: 400, ms: 0 }));    // borné à 160°, vitesse plafonnée
      await pause(400);
      const milieu = recus.filter((m) => m.type === "etat").at(-1).deg[1];
      ws.send(JSON.stringify({ op: "estop", motif: "essai" }));
      ws.send(JSON.stringify({ op: "propulsion", g: 1, d: 1 }));
      await pause(120);
      const apresArret = recus.filter((m) => m.type === "etat").at(-1);
      ws.send(JSON.stringify({ op: "ia_demander", texte: "lève le bras" }));
      ws.close();
      console.log(JSON.stringify({ config: recus.find((m) => m.type === "config"), milieu, apresArret,
        journaux: recus.filter((m) => m.type === "journal").map((m) => m.niveau + ":" + m.msg),
        dist: window.ROBO_SIMULATEUR.distanceMur(0, 0, 0) }));
    """
    r = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60,
                       cwd=RACINE)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    cfg = charger_config(RACINE / "config.toml")
    assert out["config"]["noms"] == cfg["robot"]["articulations"]["noms"]          # mêmes articulations que le pont
    assert out["config"]["simulation"] is True and out["config"]["execution_auto"] is False
    assert 90 < out["milieu"] < 160                       # 90 °/s : la cible de 160° n'est pas atteinte en 0,4 s
    assert out["apresArret"]["arret"] is True and out["apresArret"]["drive"] == [0, 0]
    assert any(j.startswith("refus:Commande refusée") for j in out["journaux"])
    assert any("IA supervisée indisponible" in j for j in out["journaux"])          # aucune requête IA hors pont
    assert out["dist"] == 2.0


# ── Journaux de séance : compteurs persistés et clôture a posteriori (B-010) ──────────────────
def test_compteurs_ecrits_et_cloture_a_posteriori(tmp_path):
    import importlib.util
    from bridge.journal import Seance
    s = Seance(tmp_path, "ESP32", "S04", "", {"robot": {"transport": "sim"}}, "sim")
    s.evenement("cmd", type="articulations", origine="manuel", demande=[90], envoye=[90.0], ms=0)
    s.compter("commandes")
    s.evenement("journal", niveau="alerte", msg="ARRÊT D'URGENCE — essai")
    s.compter("arrets_urgence")
    meta = json.loads(s.chemin_meta.read_text(encoding="utf-8"))
    assert meta["compteurs"]["commandes"] == 1 and meta["compteurs"]["arrets_urgence"] == 1   # écrits sans clôture
    s._f.close()                                                # arrêt brutal : aucune clôture
    spec = importlib.util.spec_from_file_location("cloture", RACINE / "outils" / "cloture_seance.py")
    outil = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(outil)
    r = outil.examiner(s.chemin_meta)
    assert not r["problemes"] and r["ecarts"] == {} and r["meta"]["fin"] is None
    brut = s.chemin_evt.read_text(encoding="utf-8")
    assert outil.main([str(s.chemin_meta), "--appliquer", "--operateur", "OP99"]) == 0
    apres = s.chemin_evt.read_text(encoding="utf-8")
    assert apres.startswith(brut) and apres.count("\n") == brut.count("\n") + 1     # journal brut intact, +1 ligne
    fin = json.loads(apres.splitlines()[-1])
    assert fin["action"] == "cloture" and fin["a_posteriori"] and fin["sha256_journal_avant_cloture"]
    meta = json.loads(s.chemin_meta.read_text(encoding="utf-8"))
    assert meta["fin"] == r["derniere"] and meta["cloture"]["operateur"] == "OP99"
    sceau = json.loads(s.chemin_meta.with_suffix(".sceau.json").read_text(encoding="utf-8"))
    assert sceau["fichiers"][s.chemin_evt.name] == outil.sha256(s.chemin_evt)
    assert (s.dossier / "SHA256SUMS").exists() and s.chemin_meta.with_name(s.chemin_meta.name + ".avant_cloture").exists()
    # une seconde clôture ne modifie rien
    outil.main([str(s.chemin_meta), "--appliquer"])
    assert s.chemin_evt.read_text(encoding="utf-8") == apres


def test_nom_de_sequence_accentue_nfd():
    """S04_001 (2026-10-10) : « révérence » saisi en NFD était refusé comme « Séquence inconnue »."""
    import unicodedata
    from bridge.robots.bibliotheque import BibliothequeJSON
    b = BibliothequeJSON(RACINE / "sequences", 4)
    for forme in ("NFC", "NFD"):
        assert b.lire(unicodedata.normalize(forme, "révérence"))["images"]
    assert all(unicodedata.is_normalized("NFC", n) for n in b.lister())


def test_ecritures_concurrentes_du_journal(tmp_path):
    """Plusieurs fils qui comptent en même temps : aucune erreur, aucun .tmp résiduel, compte exact."""
    import threading
    from bridge.journal import Seance
    s = Seance(tmp_path, "ESP32", "S04", "", {"robot": {"transport": "sim"}}, "sim")
    erreurs = []

    def compter():
        try:
            for _ in range(50):
                s.compter("commandes")
        except Exception as exc:          # pragma: no cover - ce qui est vérifié, c'est l'absence d'erreur
            erreurs.append(exc)
    fils = [threading.Thread(target=compter) for _ in range(4)]
    [f.start() for f in fils]
    [f.join() for f in fils]
    s.cloturer()
    assert not erreurs and not list(s.dossier.glob("*.tmp"))
    assert json.loads(s.chemin_meta.read_text(encoding="utf-8"))["compteurs"]["commandes"] == 200


def test_bandeau_pont_propose_la_version_locale():
    """Pages en ligne : lien vers la même page servie par le pont (Chrome 147 : accès au réseau local)."""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js absent")
    script = """
      import fs from "node:fs";
      const essai = (chemin, recherche = "", memo = null) => {
        globalThis.location = { protocol: "https:", hostname: "robo-scene.netlify.app", host: "robo-scene.netlify.app",
                                pathname: chemin, search: recherche };
        globalThis.localStorage = { getItem: () => memo, setItem() {} };
        globalThis.window = globalThis;
        new Function(fs.readFileSync("./web/pont.js", "utf8"))();
        return window.ROBO_PONT.adresseLocale();
      };
      console.log(JSON.stringify([essai("/"), essai("/console"), essai("/partenaire"), essai("/atelier", "?x=1"),
        essai("/public"), essai("/", "?simulation=1"), essai("/avatar", "", "ws://192.168.1.20:8765/ws")]));
    """
    r = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60, cwd=RACINE)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == ["http://127.0.0.1:8765/", "http://127.0.0.1:8765/", "http://127.0.0.1:8765/partenaire",
                                    "http://127.0.0.1:8765/atelier?x=1", "http://127.0.0.1:8765/tableau-public",
                                    "http://127.0.0.1:8765/", "http://192.168.1.20:8765/avatar"]
