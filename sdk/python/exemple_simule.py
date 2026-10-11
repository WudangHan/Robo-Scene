"""Exemple de pilote Python : robot simulé à deux servos et deux roues (profil robots/exemple_externe_python.toml).

Pour un vrai robot, remplacer les corps de appliquer_servos, appliquer_propulsion et figer par les appels au
matériel (bibliothèque du fabricant, bus série, GPIO…).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from robo_scene_sdk import PiloteRobot  # noqa: E402


class RobotSimule(PiloteRobot):
    nom = "SIM-PYTHON"
    articulations = [("base", 10, 170, 90), ("tete", 30, 150, 90)]
    propulsion = True

    def appliquer_servos(self, deg, ms):
        pass          # le simulateur adopte la cible immédiatement (self.deg est déjà à jour)

    def lire_etat(self):
        return {"vbat": 7.9}


if __name__ == "__main__":
    RobotSimule().executer()
