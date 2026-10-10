#!/bin/bash
# Double-cliquer sur ce fichier (macOS) pour démarrer la console ROBO-SCÈNE.
cd "$(dirname "$0")" || exit 1
if [ ! -d .venv ]; then
  echo "Première exécution : création de l'environnement Python…"
  python3 -m venv .venv && ./.venv/bin/pip install -q -r requirements.txt || exit 1
fi
( sleep 2 && open "http://127.0.0.1:8765" ) &
exec ./.venv/bin/python -m bridge.serveur "$@"
