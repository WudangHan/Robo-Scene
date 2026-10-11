"""Interface entre les modules d'IA (atelier P1, régisseur) et la bibliothèque fermée.

La contrainte est structurelle : l'outil exposé au modèle de langage n'accepte qu'un NOM
pris dans une énumération fermée ; il ne comporte aucun champ d'angle, de vitesse ou de
durée. Le résultat de l'appel est une proposition, que l'opérateur doit confirmer.
"""
from __future__ import annotations

from .bibliotheque import charger
from .executeur import ExecuteurFerme, Proposition


def schema_outil(chemin_bibliotheque=None) -> dict:
    """Définition d'outil (format « tools » de l'API Messages) à fournir au modèle."""
    gestes = charger(chemin_bibliotheque)
    from .sequenceur import charger_sequences
    gestes.update(charger_sequences(None, dict(gestes)))   # séquences P2.4 : noms seulement, liste fermée
    return {
        "name": "proposer_geste",
        "description": ("Propose au régisseur humain un geste du robot, choisi dans la bibliothèque "
                        "fermée du spectacle. N'exécute rien : l'opérateur décide. "
                        + " ; ".join(f"{n} = {g.description.get('fr', '')}" for n, g in gestes.items())),
        "input_schema": {
            "type": "object",
            "properties": {
                "geste": {"type": "string", "enum": sorted(gestes)},
                "motif": {"type": "string", "description": "Raison dramaturgique, en une phrase"},
            },
            "required": ["geste"],
            "additionalProperties": False,
        },
    }


def recevoir_appel(executeur: ExecuteurFerme, entree: dict, source: str = "P1/SI-01") -> Proposition:
    """Transforme l'appel d'outil du modèle en proposition journalisée (ou la refuse)."""
    champs = set(entree) - {"geste", "motif"}
    if champs:  # toute tentative de passer des paramètres moteurs est refusée
        executeur._journaliser("proposition_refusee", source=source, raison=f"champs interdits {sorted(champs)}")
        raise ValueError(f"Champs non autorisés : {sorted(champs)}")
    return executeur.proposer(entree["geste"], source=source, motif=entree.get("motif", ""))
