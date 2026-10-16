"""Certificats TLS des requêtes HTTPS du pont (DraCor, API des modèles, catalogue, veille).

Le Python distribué par python.org sur macOS n'utilise pas le trousseau du système : tant que le script
« Install Certificates.command » n'a pas été exécuté, son magasin de certificats est vide et toute requête
HTTPS échoue (« CERTIFICATE_VERIFY_FAILED : unable to get local issuer certificate »). Le pont s'appuie donc
sur le paquet certifi (magasin de Mozilla), sauf si SSL_CERT_FILE ou SSL_CERT_DIR désignent un autre magasin,
par exemple celui d'un mandataire d'établissement. La vérification des certificats n'est JAMAIS désactivée."""
from __future__ import annotations

import os
import ssl


def contexte() -> ssl.SSLContext:
    """Contexte TLS vérifiant les certificats avec le meilleur magasin disponible."""
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
        return ssl.create_default_context()
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def installer() -> None:
    """Fait de ce contexte celui par défaut de urllib et http.client (modules importés tels quels compris)."""
    ssl._create_default_https_context = contexte  # noqa: SLF001 — point d'accroche prévu par la bibliothèque standard
