#!/bin/bash
# Pont ROBO-SCÈNE toujours disponible (macOS) : service d'arrière-plan sans fenêtre du Terminal.
#
#   bash outils/demarrage_automatique.sh installer     # active le service et crée l'application « ROBO-SCÈNE »
#   bash outils/demarrage_automatique.sh retirer       # désactive tout
#   bash outils/demarrage_automatique.sh etat          # vérifie
#
# Fonctionnement
# • ~/Applications/Pont ROBO-SCÈNE.app : petite application invisible (pas d'icône dans le Dock) qui,
#   toutes les 15 secondes, vérifie que le pont écoute sur 127.0.0.1:8765 et le relance au besoin
#   (outils/pont_service.sh). macOS lui demande UNE fois l'accès au dossier Documents : répondre « Autoriser ».
#   (Un agent launchd n'a pas cet accès ; une application, si.)
# • Agent launchd ca.robo-scene.pont : ouvre cette application à l'ouverture de session, puis vérifie
#   chaque minute qu'elle tourne toujours (relance si elle a été quittée).
# • ~/Applications/ROBO-SCÈNE.app : raccourci qui garantit que le pont tourne, puis ouvre la console.
#
# Par prudence, le pont démarré sans surveillance est TOUJOURS en simulation (--sim) : aucun robot réel
# ne reçoit de commande sans qu'une personne relance elle-même le pont (bash lancer.command).
# Journal : ~/Library/Logs/robo-scene-pont.log
set -e
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
ETIQ="ca.robo-scene.pont"
PLIST="$HOME/Library/LaunchAgents/$ETIQ.plist"
APPS="$HOME/Applications"
SERVICE="$APPS/Pont ROBO-SCÈNE.app"
RACCOURCI="$APPS/ROBO-SCÈNE.app"

echapper() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

case "${1:-etat}" in
  installer)
    cd "$RACINE" && source outils/environnement.sh && chmod +x outils/pont_service.sh
    mkdir -p "$APPS" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
    launchctl bootout "gui/$(id -u)/$ETIQ" 2>/dev/null || true
    osascript -e 'tell application "Pont ROBO-SCÈNE" to quit' >/dev/null 2>&1 || true
    R="$(echapper "$RACINE")"
    # Service : application « stay-open » qui veille sur le pont
    cat > /tmp/robo-scene-service.applescript <<FIN
property racine : "$R"
on run
	veiller()
end run
on idle
	veiller()
	return 15
end idle
on veiller()
	try
		do shell script "/bin/bash " & quoted form of (racine & "/outils/pont_service.sh") & " > /dev/null 2>&1 &"
	end try
end veiller
FIN
    rm -rf "$SERVICE"
    osacompile -s -o "$SERVICE" /tmp/robo-scene-service.applescript
    /usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$SERVICE/Contents/Info.plist" 2>/dev/null \
      || /usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$SERVICE/Contents/Info.plist"
    /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier ca.robo-scene.pont-service" "$SERVICE/Contents/Info.plist" 2>/dev/null \
      || /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string ca.robo-scene.pont-service" "$SERVICE/Contents/Info.plist"
    /usr/libexec/PlistBuddy -c "Add :NSAppleEventsUsageDescription string 'Pont ROBO-SCÈNE'" "$SERVICE/Contents/Info.plist" 2>/dev/null || true
    codesign --force --deep -s - "$SERVICE" >/dev/null 2>&1 || true
    # Raccourci : s'assure que le service tourne, attend le pont, ouvre la console
    cat > /tmp/robo-scene-raccourci.applescript <<FIN
do shell script "/usr/bin/open -g -j -a " & quoted form of "$(echapper "$SERVICE")"
repeat 40 times
	try
		do shell script "/usr/sbin/lsof -nP -iTCP:8765 -sTCP:LISTEN"
		exit repeat
	end try
	delay 0.5
end repeat
open location "http://127.0.0.1:8765"
FIN
    rm -rf "$RACCOURCI"
    osacompile -o "$RACCOURCI" /tmp/robo-scene-raccourci.applescript
    codesign --force --deep -s - "$RACCOURCI" >/dev/null 2>&1 || true
    rm -f /tmp/robo-scene-service.applescript /tmp/robo-scene-raccourci.applescript
    # Agent launchd : ouvre le service à la connexion et le relance chaque minute s'il a été quitté
    cat > "$PLIST" <<FIN
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$ETIQ</string>
  <key>ProgramArguments</key>
  <array><string>/usr/bin/open</string><string>-g</string><string>-j</string><string>-a</string><string>$SERVICE</string></array>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>60</integer>
</dict>
</plist>
FIN
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    echo "Service activé. Si macOS demande l'accès au dossier Documents pour « Pont ROBO-SCÈNE », répondre « Autoriser »."
    echo "Raccourci : $RACCOURCI (à glisser dans le Dock au besoin)." ;;
  retirer)
    launchctl bootout "gui/$(id -u)/$ETIQ" 2>/dev/null || true
    osascript -e 'tell application "Pont ROBO-SCÈNE" to quit' >/dev/null 2>&1 || true
    rm -f "$PLIST"; rm -rf "$SERVICE" "$RACCOURCI"
    echo "Démarrage automatique retiré (un pont déjà lancé reste actif jusqu'à la fermeture de session)." ;;
  etat)
    launchctl print "gui/$(id -u)/$ETIQ" >/dev/null 2>&1 && echo "Agent launchd chargé." || echo "Agent launchd non chargé."
    pgrep -f "Pont ROBO-SCÈNE.app" >/dev/null && echo "Service « Pont ROBO-SCÈNE » actif." || echo "Service inactif."
    lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1 && echo "Pont à l'écoute sur 127.0.0.1:8765." || echo "Pont non joint." ;;
  *) echo "Usage : $0 installer | retirer | etat" ; exit 1 ;;
esac
