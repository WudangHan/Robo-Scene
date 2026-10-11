"""Tests de l'alpha P1.3 (SI-04) — exigences EF-01 à EF-07 et ENF-01 de la fiche P1.1, sans réseau externe."""
import csv
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from atelier_p1.atelier import Atelier, ErreurAtelier, verifier_mise_en_service
from atelier_p1.corpus import ErreurCorpus, charger_corpus
from atelier_p1.ecart import ecart_transformation, etiquette_suggeree, levenshtein
from atelier_p1.modeles import ModeleDistant, ModeleLocal, ModeleSimule, extraire_propositions
from atelier_p1.routeur import Routeur, charger_liste_blocage

RACINE = Path(__file__).resolve().parents[1]


class Faux:
    """Modèle factice qui enregistre les consignes reçues."""

    def __init__(self, code, disponible=True):
        self.code, self.modele, self.disponible, self.recues = code, f"faux-{code}", disponible, []

    def generer(self, texte, type_, nb, extraits=()):
        from atelier_p1.modeles import Generation, construire_consigne
        self.recues.append(construire_consigne(texte, type_, nb, extraits))
        return Generation([f"{self.code} proposition {i + 1}" for i in range(nb)], self.code, self.modele, 10, 20)


@pytest.fixture
def corpus():
    return charger_corpus(RACINE / "corpus")


def atelier(tmp_path, corpus, **kw):
    d, l = Faux("SI-01"), Faux("SI-02")
    a = Atelier(seance="T01", pseudonymes=["A01", "A02"], corpus=corpus, distant=d, local=l,
                dossier_journal=tmp_path, liste_blocage=["eloise tremblay"], **kw)
    return a, d, l


# ------------------------------------------------------------------ écart (I-5, opération 4)
def test_levenshtein_et_ecart():
    assert levenshtein("chat", "chats") == 1 and levenshtein("", "abc") == 3
    assert ecart_transformation("Bonjour.", "Bonjour.") == 0.0
    assert ecart_transformation("abc", "xyz") == 1.0
    assert 0 < ecart_transformation("Elle se tait.", "Elle se tait enfin.") < 0.5
    assert etiquette_suggeree(None) == "humaine" and etiquette_suggeree(0.0) == "systeme"
    assert etiquette_suggeree(0.3) == "mixte"


# ------------------------------------------------------------------ corpus (P1.2)
def test_corpus_exemple_admis(corpus):
    assert set(corpus) == {"CORP-001", "CORP-002"}
    assert all(e.categorie == "A" and not e.local_seulement for e in corpus.values())


def test_corpus_refuse_categories_D_et_F_et_force_E_local(tmp_path):
    (tmp_path / "x.txt").write_text("texte", encoding="utf-8")
    base = {"code": "C1", "titre": "t", "auteur": "a", "fichier": "x.txt", "admis": True}
    (tmp_path / "corpus.yaml").write_text(json.dumps({"extraits": [{**base, "categorie": "D"}]}), encoding="utf-8")
    with pytest.raises(ErreurCorpus):
        charger_corpus(tmp_path)
    (tmp_path / "corpus.yaml").write_text(json.dumps({"extraits": [{**base, "categorie": "E", "local_seulement": False}]}),
                                          encoding="utf-8")
    assert charger_corpus(tmp_path)["C1"].local_seulement is True
    (tmp_path / "corpus.yaml").write_text(json.dumps({"extraits": [{**base, "categorie": "F", "admis": False}]}),
                                          encoding="utf-8")
    assert charger_corpus(tmp_path) == {}            # ligne refusée au registre : jamais chargée


# ------------------------------------------------------------------ routeur (D03, ENF-01, EF-07)
def test_routeur_motifs(corpus, tmp_path):
    f = tmp_path / "bl.txt"
    f.write_text("# commentaire\nÉloïse Tremblay\n", encoding="utf-8")
    r = Routeur(charger_liste_blocage(f))
    assert r.decider("Une scène dans un hangar").cible == "distant"
    d = r.decider("Une réplique pour ELOISE   tremblay, qui entre")
    assert d.cible == "local" and "liste de blocage" in d.motifs[0] and "loïse" not in " ".join(d.motifs)
    assert r.decider("écrire à quelqu'un@exemple.org").cible == "local"
    assert r.decider("appeler le 819 555-0199").cible == "local"
    assert r.decider("texte", confidentielle=True).cible == "local"
    r.hors_ligne = True
    assert r.decider("Une scène dans un hangar").cible == "local"


def test_consigne_sensible_jamais_envoyee_au_distant(tmp_path, corpus):
    a, d, l = atelier(tmp_path, corpus)
    a.consigner("A01", "Une scène où Éloïse Tremblay hésite", "situation", 2)
    assert d.recues == [] and len(l.recues) == 1
    a.consigner("A01", "Une scène dans un hangar", "situation", 2)
    assert len(d.recues) == 1


def test_aucun_repli_sur_le_distant_si_local_indisponible(tmp_path, corpus):
    d, l = Faux("SI-01"), Faux("SI-02", disponible=False)
    a = Atelier(seance="T02", pseudonymes=["A01"], corpus=corpus, distant=d, local=l, dossier_journal=tmp_path)
    a.regler_hors_ligne(True)
    with pytest.raises(ErreurAtelier, match="aucun repli"):
        a.consigner("A01", "Une scène", "libre", 1)
    assert d.recues == []


# ------------------------------------------------------------------ cinq opérations, journal et exports
def test_parcours_cinq_operations_et_exports(tmp_path, corpus):
    a, d, _ = atelier(tmp_path, corpus)
    c = a.consigner("A01", "Réplique d'ouverture : le décor a disparu", "amorce", 3, ["CORP-001"])
    assert "CORP-001" in d.recues[0] and "Tout beau" in d.recues[0]        # extrait fourni en contexte
    a.decider(c.id, 1, 1, "rejetee", "trop explicatif")
    a.decider(c.id, 1, 2, "retenue")
    e = a.transformer(c.id, 1, 2, "SI-01 proposition 2, mais murmurée")
    assert e > 0
    seg = a.attribuer(c.id, 1, 2)                                          # suggestion : mixte
    assert seg["etiquette"] == "mixte" and seg["credit"] == "A01"
    a.redemander(c.id, "autre piste")
    assert len(c.generations) == 2 and c.generations[0].propositions[2].decision == "redemandee"
    a.decider(c.id, 2, 1, "retenue")
    a.attribuer(c.id, 2, 1)                                                # inchangée : système
    a.segment_humain("A01", "Noir.")
    a.reetiqueter(1, "mixte")                                              # EF-05 : modifiable
    ind = a.indicateurs()["A01"]
    assert ind["propositions_generees"] == 6 and ind["propositions_retenues"] == 2
    assert ind["taux_conservation"] == round(2 / 6, 3)
    sorties = a.exporter()
    doc = json.loads(sorties["json"].read_text(encoding="utf-8"))
    assert doc["systeme"] == "SI-04" and len(doc["texte_final"]) == 3
    assert "tremblay" not in sorties["json"].read_text(encoding="utf-8").lower()   # liste de blocage absente
    with sorties["csv"].open(encoding="utf-8-sig") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))
    assert lignes[0]["id_cycle"] == c.id and "ecart_transformation (0–1)" in lignes[0]
    evenements = [json.loads(l)["evenement"] for l in a.fichier.read_text(encoding="utf-8").splitlines()]
    for ev in ("ouverture", "consigne", "generation", "selection", "transformation", "attribution", "export"):
        assert ev in evenements


def test_regles_de_saisie(tmp_path, corpus):
    a, _, _ = atelier(tmp_path, corpus)
    with pytest.raises(ErreurAtelier):
        a.consigner("Inconnu", "x")
    with pytest.raises(ErreurAtelier):
        a.consigner("A01", "   ")
    c = a.consigner("A01", "x", nb=12)
    assert len(c.generations[0].propositions) == 5                         # EF-02 : au plus cinq
    with pytest.raises(ErreurAtelier):
        a.transformer(c.id, 1, 1, "y")                                     # non retenue


def test_plafond_de_jetons(tmp_path, corpus):
    a, _, _ = atelier(tmp_path, corpus, plafond_jetons=30)
    a.consigner("A01", "x", nb=1)                                          # 30 jetons consommés
    with pytest.raises(ErreurAtelier, match="Plafond"):
        a.consigner("A01", "y", nb=1)


def test_mise_en_service_bloque_le_mode_atelier(tmp_path, corpus):
    assert verifier_mise_en_service(RACINE / "config" / "mise_en_service.yaml")   # critères non remplis
    with pytest.raises(ErreurAtelier, match="Mise en service refusée"):
        atelier(tmp_path, corpus, mode="atelier", mise_en_service=RACINE / "config" / "mise_en_service.yaml")


def test_simule_interdit_en_mode_atelier(tmp_path, corpus):
    ok = tmp_path / "ms.yaml"
    from atelier_p1.atelier import CRITERES_P1_1
    ok.write_text(json.dumps({"criteres": {c: True for c in CRITERES_P1_1}, "approuve_par": "S. G.", "date": "2027-02-01"}),
                  encoding="utf-8")
    d, l = Faux("SI-01"), Faux("SI-02")
    a = Atelier(seance="T03", pseudonymes=["A01"], corpus=corpus, distant=d, local=l, simule=ModeleSimule(),
                dossier_journal=tmp_path, mode="atelier", mise_en_service=ok, forcer_simule=True)
    assert a.forcer_simule is False


# ------------------------------------------------------------------ clients des API (serveurs factices locaux)
class FauxAPI(BaseHTTPRequestHandler):
    recu = {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        corps = json.dumps({"models": [{"name": "modele-test:latest"}]}).encode()
        self.send_response(200); self.end_headers(); self.wfile.write(corps)

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        FauxAPI.recu = {"chemin": self.path, "entetes": {k.lower(): v for k, v in self.headers.items()}, "corps": json.loads(self.rfile.read(n))}
        if self.path == "/v1/messages":
            rep = {"model": "claude-opus-5-5", "content": [{"type": "text", "text": '{"propositions": ["Un", "Deux"]}'}],
                   "usage": {"input_tokens": 50, "output_tokens": 12}}
        else:
            rep = {"model": "modele-test", "message": {"content": "1. Premier\n2. Second"},
                   "prompt_eval_count": 40, "eval_count": 9}
        corps = json.dumps(rep).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(corps))); self.end_headers()
        self.wfile.write(corps)


@pytest.fixture
def faux_serveur():
    h = ThreadingHTTPServer(("127.0.0.1", 0), FauxAPI)
    threading.Thread(target=h.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{h.server_address[1]}"
    h.shutdown()


def test_client_distant_format_api_messages(faux_serveur):
    m = ModeleDistant(cle="cle-test")
    m.URL = faux_serveur + "/v1/messages"
    g = m.generer("Une scène", "libre", 2)
    r = FauxAPI.recu
    assert r["entetes"]["x-api-key"] == "cle-test" and r["entetes"]["anthropic-version"] == "2023-06-01"
    assert r["corps"]["model"] == "claude-opus-5-5" and r["corps"]["max_tokens"] > 0 and r["corps"]["system"]
    assert g.propositions == ["Un", "Deux"] and g.jetons_entree == 50 and g.systeme == "SI-01"


def test_client_local_ollama(faux_serveur):
    m = ModeleLocal("modele-test", url=faux_serveur)
    assert m.disponible
    g = m.generer("Une scène", "libre", 2)
    assert FauxAPI.recu["chemin"] == "/api/chat" and FauxAPI.recu["corps"]["stream"] is False and FauxAPI.recu["corps"]["format"] == "json"
    assert g.propositions == ["Premier", "Second"] and g.jetons_sortie == 9 and g.systeme == "SI-02"


def test_extraction_robuste():
    assert extraire_propositions('Voici : {"propositions": ["a", "b", "c"]}', 2) == ["a", "b"]
    assert extraire_propositions("- un\n- deux", 5) == ["un", "deux"]


# ------------------------------------------------------------------ interface locale
def test_serveur_local(tmp_path, corpus):
    from atelier_p1.serveur import fabriquer_gestionnaire
    a = Atelier(seance="T04", pseudonymes=["A01"], corpus=corpus, distant=Faux("SI-01"), local=Faux("SI-02"),
                simule=ModeleSimule(), dossier_journal=tmp_path, forcer_simule=True)
    h = ThreadingHTTPServer(("127.0.0.1", 0), fabriquer_gestionnaire(a))
    threading.Thread(target=h.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{h.server_address[1]}"
    try:
        def post(chemin, corps, entete=True):
            req = urllib.request.Request(base + chemin, data=json.dumps(corps).encode(),
                                         headers={"Content-Type": "application/json", **({"X-Atelier": "1"} if entete else {})})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        assert post("/api/consigne", {"pseudonyme": "A01", "texte": "x"}, entete=False)[0] == 403
        st, e = post("/api/consigne", {"pseudonyme": "A01", "texte": "Une entrée", "nb": 2})
        assert st == 200 and e["cycles"][0]["generations"][0]["systeme"] == "SIMULE"
        with urllib.request.urlopen(base + "/") as r:
            assert b"Atelier dramaturgique" in r.read()
    finally:
        h.shutdown()
