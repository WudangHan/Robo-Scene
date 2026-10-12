#!/bin/bash
# Double-cliquer sur ce fichier (macOS) pour démarrer la plateforme ROBO-SCÈNE.
# Options transmises au pont : par exemple « bash lancer.command --sim » (tous les robots en simulation).
cd "$(dirname "$0")" || exit 1
source outils/environnement.sh || exit 1
if lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Le pont tourne déjà sur le port 8765 (démarrage automatique ou autre fenêtre) : ouverture de la console."
  open "http://127.0.0.1:8765"
  exit 0
fi
( sleep 2 && open "http://127.0.0.1:8765" ) &
exec ./.venv/bin/python -m bridge.serveur "$@"
