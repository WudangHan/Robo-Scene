#!/bin/bash
# Démarrage automatique du pont ROBO-SCÈNE à l'ouverture de la session macOS (agent launchd).
#
#   bash outils/demarrage_automatique.sh installer     # active (pont en simulation, relancé s'il s'arrête)
#   bash outils/demarrage_automatique.sh retirer       # désactive
#   bash outils/demarrage_automatique.sh etat          # vérifie
#
# Par prudence, le pont démarré sans surveillance est TOUJOURS en simulation (--sim) : aucun robot
# réel ne peut recevoir de commande sans qu'une personne relance le pont elle-même (lancer.command).
# macOS interdit à un agent launchd de lire le dossier Documents : l'agent se contente donc d'ouvrir
# outils/pont_session.command dans le Terminal (en arrière-plan), qui, lui, y a accès.
# Journal : ~/Library/Logs/robo-scene-pont.log
set -e
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
ETIQ="ca.robo-scene.pont"
PLIST="$HOME/Library/LaunchAgents/$ETIQ.plist"
JOURNAL="$HOME/Library/Logs/robo-scene-pont.log"

case "${1:-etat}" in
  installer)
    cd "$RACINE" && source outils/environnement.sh && chmod +x outils/pont_session.command
    mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
    cat > "$PLIST" <<FIN
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$ETIQ</string>
  <key>WorkingDirectory</key><string>$RACINE</string>
  <key>ProgramArguments</key>
  <array><string>/usr/bin/open</string><string>-g</string><string>-a</string><string>Terminal</string>
    <string>$RACINE/outils/pont_session.command</string></array>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
FIN
    launchctl bootout "gui/$(id -u)/$ETIQ" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    echo "Démarrage automatique activé ($PLIST)." ;;
  retirer)
    launchctl bootout "gui/$(id -u)/$ETIQ" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Démarrage automatique retiré." ;;
  etat)
    launchctl print "gui/$(id -u)/$ETIQ" 2>/dev/null | grep -E "state =|pid =" || echo "Agent non chargé."
    lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1 && echo "Pont à l'écoute sur 127.0.0.1:8765." || echo "Pont non joint." ;;
  *) echo "Usage : $0 installer | retirer | etat" ; exit 1 ;;
esac
