"""Pont ROBO-SCÈNE."""
from .tls import installer as _installer_tls

_installer_tls()   # certificats HTTPS fiables, même avec le Python de python.org sur macOS
