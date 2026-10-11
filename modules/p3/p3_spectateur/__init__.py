"""Interface spectateur, version alpha (repère P3.2, système SI-06).

Projet « L'IA au service de la création théâtrale » — Sylvain Gagné, Ph. D., chercheur indépendant.
Serveur local d'agrégation anonyme : aucune réponse individuelle n'est conservée.
"""
from .emotions import EMOTIONS, plus_proche
from .agregat import Seance, ErreurSeance, CodeInvalide, JetonInconnu, TropTot, SeanceClose, ValeurInvalide

__all__ = ["EMOTIONS", "plus_proche", "Seance", "ErreurSeance", "CodeInvalide", "JetonInconnu",
           "TropTot", "SeanceClose", "ValeurInvalide"]
__version__ = "0.1.1-alpha"
