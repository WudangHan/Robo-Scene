#!/bin/bash
# Lancé par le démarrage automatique (outils/demarrage_automatique.sh) dans une fenêtre du Terminal :
# le Terminal dispose de l'accès au dossier Documents, ce que macOS refuse à un agent launchd.
# Le pont est TOUJOURS en simulation ici ; fermer la fenêtre (ou Ctrl+C) l'arrête.
cd "$(dirname "$0")/.." || exit 1
source outils/environnement.sh || exit 1
if lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Le pont tourne déjà sur le port 8765."
  exit 0
fi
echo "Pont ROBO-SCÈNE (simulation) — journal : ~/Library/Logs/robo-scene-pont.log"
exec ./.venv/bin/python -m bridge.serveur --sim 2>&1 | tee -a "$HOME/Library/Logs/robo-scene-pont.log"
