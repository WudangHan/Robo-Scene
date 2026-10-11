# P3.2 — Interface spectateur, version alpha (système SI-06)

Projet « L'IA au service de la création théâtrale » — Sylvain Gagné, Ph. D. — version 0.1.0-alpha, 5 octobre 2026.

## Principe

Un **serveur local**, lancé sur l'ordinateur de régie et joint par le Wi-Fi de la salle, reçoit les réponses
anonymes du public (grille de huit émotions ou deux curseurs, spécification P3.1) et les **agrège aussitôt** :
aucune réponse individuelle, aucune adresse IP, aucun témoin (cookie), aucun horodatage individuel n'est conservé.
Le seul état par appareil est un jeton éphémère en mémoire vive, effacé à la fin de la séance, qui sert à
appliquer le délai minimal de dix secondes entre deux réponses.

Chaque réponse est comptée dans une **cellule** : fenêtre de temps (30 s par défaut) × repère de la conduite ×
étiquette de provenance de la réplique en cours (humaine, système, mixte). L'étiquette arrive du pont scénique
P2.3 par OSC ; elle n'est montrée au public que si la condition expérimentale « provenance affichée » (H4) est
active. À l'export, les cellules de moins de cinq réponses sont masquées.

## Contenu

| Chemin | Rôle |
|---|---|
| `p3_spectateur/emotions.py` | Les huit émotions (cercle de Russell), conversion des curseurs |
| `p3_spectateur/agregat.py` | Séance : code, jetons éphémères, délai minimal, agrégation, export masqué |
| `p3_spectateur/serveur.py` | Serveur HTTP (pages et API), flux SSE, entrée OSC, ligne de commande |
| `p3_spectateur/static/public.html` | Page du public, issue de la maquette P3.1 (WCAG 2.2 AA visé, FR/EN) |
| `p3_spectateur/static/regie.html` | Page de régie : code de séance, compteurs, cercle, provenance, fin de séance |
| `tests/test_p3_spectateur.py` | 10 tests (agrégat, HTTP sans témoin, SSE, OSC) |
| `tests/test_integration_pont_scenique.py` | La conduite d'exemple de P2.3 étiquette les réponses (1 test) |

## Installation et lancement (macOS)

```bash
cd "05_Prototypes/P3_Interface_spectateur/code"
python3 -m venv ~/venv-p3 && source ~/venv-p3/bin/activate
pip install -r requirements.txt
python -m pytest tests                                   # 11 tests

# séance, condition H4 active, écoute OSC sur 9000 (provenance) et 8000 (/p3/fin du pont)
python -m p3_spectateur.serveur --titre "Essai 1" --provenance-affichee --osc 9000 --osc 8000 \
       --exports ../../../07_Analyse/Quantitative
```

Le serveur affiche le **code de séance** (à projeter en salle), l'adresse du public (`http://<ip>:8080/?code=…`)
et l'adresse de la régie, qui contient une clé secrète à ne pas diffuser.

## Avec le pont scénique (P2.3)

Le pont envoie `/p3/provenance <étiquette> <repère>` vers `--p3` (défaut `127.0.0.1:9000`) et les messages OSC
libres, dont `/p3/fin`, vers `--osc` (défaut `127.0.0.1:8000`) : d'où l'écoute sur les deux ports ci-dessus.

```bash
cd ../../P2_Scenographie_robotique/code
python -m pont_scenique.regie pont_scenique/conduite_exemple.yaml --a-blanc   # à blanc : rien n'est émis
python -m pont_scenique.regie pont_scenique/conduite_exemple.yaml --p3 127.0.0.1:9000 --osc 127.0.0.1:8000 --cible sim
```

Attention : en mode `--a-blanc`, le pont n'émet aucun message, y compris vers P3.

## Limites de l'alpha

- HTTP sans chiffrement, acceptable sur un réseau de salle fermé, sans Internet ; HTTPS à prévoir pour la bêta.
- Le délai minimal repose sur un jeton par onglet : une personne qui recharge la page obtient un nouveau jeton.
- Libellés des émotions non encore validés (rétrotraduction T.1, tests P3.3 avec les personnes concernées).
- Revue d'accessibilité experte et tests I-8 à faire avant tout usage public (P3.3).

## Version 0.1.1-alpha (5 octobre 2026) — audit d'accessibilité (P3.3, préparation)

- Corrections : noms accessibles commençant par le texte visible (critère 2.5.3 : « EN, switch to English »,
  « A−, réduire le texte ») ; attribut ARIA interdit retiré du code de séance (4.1.2) ; couleur des contours portée
  de #4a4337 (1,97:1) à #857b68 (4,62:1) pour le champ du code (1.4.11).
- Audit axe-core (WCAG 2.2 A/AA) sur 14 états : 13 violations avant, 0 après.

| Outil | Rôle |
|---|---|
| `outils/audit_wcag.py` | Audit axe-core de tous les écrans (FR/EN, contraste élevé, texte 200 %, régie) ; rapport JSON |
| `outils/verifs_manuelles.py` | Clavier, focus masqué, taille des cibles, redistribution à 320 px, espacement du texte |

```bash
npm install axe-core@4 && pip install playwright && playwright install chromium
python outils/audit_wcag.py --axe node_modules/axe-core/axe.min.js --sortie rapport_axe.json
python outils/verifs_manuelles.py
```
