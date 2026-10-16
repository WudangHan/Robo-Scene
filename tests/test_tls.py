"""Certificats HTTPS du pont (python -m pytest -q tests/test_tls.py)."""
import ssl

import bridge  # noqa: F401  (installe le contexte par défaut)
from bridge import tls


def test_contexte_verifie_avec_un_magasin_non_vide(monkeypatch):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    c = tls.contexte()
    assert c.verify_mode == ssl.CERT_REQUIRED and c.check_hostname
    assert c.cert_store_stats()["x509_ca"] > 100        # magasin certifi chargé, même si celui du système est vide


def test_magasin_impose_par_l_environnement_respecte(monkeypatch, tmp_path):
    vide = tmp_path / "vide.pem"
    vide.write_text("")
    monkeypatch.setenv("SSL_CERT_FILE", str(vide))
    c = tls.contexte()
    assert c.verify_mode == ssl.CERT_REQUIRED            # jamais de désactivation de la vérification


def test_contexte_par_defaut_installe():
    assert ssl._create_default_https_context is tls.contexte
