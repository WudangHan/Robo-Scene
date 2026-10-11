"""Accès aux prototypes du projet réunis dans modules/ (P1, P2, P3, T.6, X.2).

Les prototypes restent des paquets autonomes, testés pour eux-mêmes ; la plateforme les importe
tels quels plutôt que de les recopier, pour qu'il n'existe qu'une seule version de chaque règle
(routeur de sensibilité D03, bibliothèque fermée P2.2, agrégation anonyme P3.2…).
"""
from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
MODULES = RACINE / "modules"
CHEMINS = {nom: MODULES / nom for nom in ("p1", "p2", "p3", "t6", "x2", "regie")}

for _p in CHEMINS.values():
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
