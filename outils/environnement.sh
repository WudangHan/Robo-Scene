# Prépare l'environnement Python du pont (à « sourcer » depuis la racine du dépôt).
# Crée .venv au besoin et réinstalle les dépendances chaque fois que requirements.txt change
# (empreinte SHA-1 mémorisée dans .venv/.requirements.sha), pour qu'une mise à jour du code
# n'échoue jamais faute d'une bibliothèque nouvelle.
if [ ! -x .venv/bin/python ]; then
  echo "Première exécution : création de l'environnement Python…"
  python3 -m venv .venv || return 1
fi
EMPREINTE=$(shasum requirements.txt | cut -d' ' -f1)
if [ "$(cat .venv/.requirements.sha 2>/dev/null)" != "$EMPREINTE" ]; then
  echo "Installation ou mise à jour des dépendances…"
  ./.venv/bin/pip install -q --upgrade pip && ./.venv/bin/pip install -q -r requirements.txt || return 1
  echo "$EMPREINTE" > .venv/.requirements.sha
fi
