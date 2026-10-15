#!/bin/bash
# Lancé toutes les 15 secondes par l'application « Pont ROBO-SCÈNE » (outils/demarrage_automatique.sh) :
# démarre le pont en simulation s'il n'écoute pas déjà sur le port 8765, sinon ne fait rien.
cd "$(dirname "$0")/.." || exit 1
lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1 && exit 0
VERROU="${TMPDIR:-/tmp}/robo-scene-pont.verrou"
# un seul démarrage à la fois (le pont met quelques secondes à ouvrir le port)
if [ -f "$VERROU" ] && [ $(( $(date +%s) - $(stat -f %m "$VERROU") )) -lt 60 ]; then exit 0; fi
touch "$VERROU"
JOURNAL="$HOME/Library/Logs/robo-scene-pont.log"
{ source outils/environnement.sh; } >> "$JOURNAL" 2>&1 || { rm -f "$VERROU"; exit 1; }
echo "── $(date '+%Y-%m-%d %H:%M:%S') démarrage du pont (simulation, service d'arrière-plan)" >> "$JOURNAL"
PYTHONUNBUFFERED=1 nohup ./.venv/bin/python -m bridge.serveur --sim >> "$JOURNAL" 2>&1 &
sleep 20; rm -f "$VERROU"
