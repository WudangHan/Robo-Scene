"""Bibliothèque fermée de gestes pour le Reachy Mini — repère P2.2.

Projet « L'IA au service de la création théâtrale », Sylvain Gagné, Ph. D.
"""
from .bibliotheque import charger, valider, echantillonner, LIMITES_SDK, LIMITES_PROJET, STATUTS
from .executeur import ExecuteurFerme, Proposition, RefusExecution
from .sequenceur import charger_sequences, ErreurSequence, Sequence

__all__ = ["charger", "valider", "echantillonner", "LIMITES_SDK", "LIMITES_PROJET", "STATUTS",
           "ExecuteurFerme", "Proposition", "RefusExecution", "charger_sequences", "ErreurSequence", "Sequence"]
__version__ = "1.1.0"
