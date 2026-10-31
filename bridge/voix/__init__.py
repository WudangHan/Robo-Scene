"""Voix humaine du partenaire, du robot virtuel, de la direction d'exercices et du robot physique :
partition prosodique (partition.py), moteurs neuronaux dirigeables (moteurs.py), service hybride avec cache
et repli local (service.py)."""
from .partition import construire, consigne_jeu, vers_navigateur  # noqa: F401
from .service import ServiceVoix  # noqa: F401
