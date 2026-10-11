"""Tests de l'alpha P3.2 (interface spectateur, SI-06) — sans réseau externe."""
import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

from p3_spectateur import (CodeInvalide, JetonInconnu, Seance, SeanceClose, TropTot, ValeurInvalide,
                           plus_proche)
from p3_spectateur.serveur import creer_serveur, demarrer_osc


class Horloge:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def seance_test(**kw):
    h = Horloge()
    return Seance(code="1234", horloge=h, **kw), h


# ------------------------------------------------------------------ agrégat
def test_code_et_jeton():
    s, _ = seance_test()
    with pytest.raises(CodeInvalide):
        s.rejoindre("0000")
    j = s.rejoindre("1234")
    assert len(j) >= 20
    with pytest.raises(JetonInconnu):
        s.repondre("faux", emotion="ravi")


def test_delai_minimal_entre_deux_reponses():
    s, h = seance_test(delai_min_s=10)
    j = s.rejoindre("1234")
    s.repondre(j, emotion="ravi")
    h.t = 5
    with pytest.raises(TropTot):
        s.repondre(j, emotion="ravi")
    h.t = 10.1
    assert s.repondre(j, emotion="apai") == "apai"


def test_curseurs_et_plus_proche():
    s, _ = seance_test()
    j = s.rejoindre("1234")
    assert s.repondre(j, v=9, a=5) == "ravi"          # agrément maximal, intensité neutre
    assert plus_proche(-0.7, 0.7) == "inq"
    j2 = s.rejoindre("1234")
    with pytest.raises(ValeurInvalide):
        s.repondre(j2, v=0, a=5)
    with pytest.raises(ValeurInvalide):
        s.repondre(j2, emotion="colere")


def test_agregation_par_provenance_et_seuil_de_diffusion():
    s, h = seance_test(seuil_diffusion=3, fenetre_s=30)
    jetons = [s.rejoindre("1234") for _ in range(4)]
    s.etiqueter("systeme", "3")
    for j in jetons:
        s.repondre(j, emotion="saisi")
    h.t = 40
    s.etiqueter("humaine", "5")
    s.repondre(jetons[0], emotion="ravi")             # cellule de 1 réponse : masquée à l'export
    e = s.etat_regie()
    assert e["reponses"] == 5 and e["par_provenance"]["systeme"]["saisi"] == 4
    x = s.terminer()
    texte = json.dumps(x)
    assert all(j not in texte for j in jetons)        # aucun jeton dans l'export
    cel = {(c["fenetre"], c["provenance"]): c for c in x["cellules"]}
    assert cel[(0, "systeme")]["n"] == 4 and cel[(0, "systeme")]["emotions"]["saisi"] == 4
    assert cel[(1, "humaine")]["masquee"] is True and cel[(1, "humaine")]["n"] is None
    assert x["par_provenance"]["humaine"]["masquee"] is True


def test_fin_efface_les_jetons_et_ferme_la_saisie():
    s, _ = seance_test()
    j = s.rejoindre("1234")
    s.terminer()
    assert s.etat_regie()["appareils"] == 0
    with pytest.raises(SeanceClose):
        s.repondre(j, emotion="ravi")
    with pytest.raises(SeanceClose):
        s.rejoindre("1234")


def test_provenance_masquee_au_public_hors_condition_H4():
    s, _ = seance_test(afficher_provenance=False)
    s.etiqueter("mixte")
    assert s.evenement_provenance() == {"etiquette": None}
    s2, _ = seance_test(afficher_provenance=True)
    s2.etiqueter("mixte")
    assert s2.evenement_provenance() == {"etiquette": "mixte"}


# ------------------------------------------------------------------ HTTP
def port_libre():
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


@pytest.fixture
def serveur(tmp_path):
    s = Seance(code="4729", delai_min_s=0, seuil_diffusion=1, afficher_provenance=True)
    port = port_libre()
    httpd = creer_serveur(s, "127.0.0.1", port, tmp_path, journal=lambda *_: None)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield s, f"http://127.0.0.1:{port}", tmp_path
    httpd.arret_demande = True
    httpd.shutdown()
    httpd.server_close()


def requete(url, corps=None, entetes=None):
    data = None if corps is None else json.dumps(corps).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(entetes or {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_http_parcours_complet_sans_temoin(serveur):
    s, base, dossier = serveur
    st, h, corps = requete(base + "/")
    assert st == 200 and b"Comment vous sentez-vous" in corps
    assert "Set-Cookie" not in h and h["Cache-Control"] == "no-store"
    assert "camera=()" in h["Permissions-Policy"]
    st, _, c = requete(base + "/api/rejoindre", {"code": "0000"})
    assert st == 403
    st, _, c = requete(base + "/api/rejoindre", {"code": "4729"})
    jeton = json.loads(c)["jeton"]
    st, _, c = requete(base + "/api/reponse", {"jeton": jeton, "emotion": "enth"})
    assert st == 200 and json.loads(c)["emotion"] == "enth"
    st, _, _ = requete(base + "/api/regie/etat")
    assert st == 403                                     # clé de régie exigée
    st, _, c = requete(base + "/api/regie/etat", entetes={"X-Cle-Regie": s.cle_regie})
    assert json.loads(c)["par_emotion"]["enth"] == 1
    st, _, c = requete(base + "/api/regie/fin", {}, {"X-Cle-Regie": s.cle_regie})
    fichiers = list(dossier.glob("*_P3-2_agregat_seance.json"))
    assert st == 200 and len(fichiers) == 1
    assert jeton not in fichiers[0].read_text(encoding="utf-8")


def test_http_requete_trop_volumineuse(serveur):
    _, base, _ = serveur
    st, _, _ = requete(base + "/api/rejoindre", {"code": "x" * 5000})
    assert st == 400


def test_flux_sse_recoit_la_provenance(serveur):
    s, base, _ = serveur
    recu = []

    def lire():
        with urllib.request.urlopen(base + "/api/flux", timeout=5) as r:
            for ligne in r:
                recu.append(ligne.decode())
                if len([x for x in recu if x.startswith("data:")]) >= 2:
                    break

    t = threading.Thread(target=lire, daemon=True)
    t.start()
    time.sleep(0.3)
    s.etiqueter("systeme", "3")
    t.join(timeout=5)
    assert any('"etiquette": "systeme"' in x for x in recu)


# ------------------------------------------------------------------ OSC (pont scénique P2.3)
def test_osc_provenance_et_fin(tmp_path):
    from pythonosc.udp_client import SimpleUDPClient
    s = Seance(code="1111", seuil_diffusion=1)
    port = port_libre()
    serveur_osc = demarrer_osc(s, port, tmp_path, journal=lambda *_: None, hote="127.0.0.1")
    try:
        c = SimpleUDPClient("127.0.0.1", port)
        c.send_message("/p3/provenance", ["mixte", "3"])      # format émis par pont_scenique.moteur
        for _ in range(50):
            if s.provenance == "mixte":
                break
            time.sleep(0.02)
        assert s.provenance == "mixte" and s.repere == "3"
        c.send_message("/p3/provenance", ["inconnue"])       # ignoré, sans plantage
        c.send_message("/p3/fin", [])
        for _ in range(50):
            if s.close:
                break
            time.sleep(0.02)
        assert s.close and list(tmp_path.glob("*.json"))
    finally:
        serveur_osc.shutdown()
