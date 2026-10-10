# Robo-Scène

*Partenaire de jeu pour acteurs* — console de pilotage et partenaire de théâtre du projet ROBO-SCÈNE 2026.

## Console ROBO-SCÈNE

Application de développement, de suivi et de pilotage d'un robot à microcontrôleur, conçue pour la séance incarnée S04 du protocole ROBO-SCÈNE (mouvement supervisé réel, sous seuil de confiance).

```
 Interface web (navigateur, tablette)        Serveur-pont Python                Robot
 ─────────────────────────────────          ──────────────────────           ──────────────
 suivi · téléopération · séquences   ⇄ WS ⇄  sécurité · séquences · IA   ⇄  série USB ou TCP Wi-Fi
 IA supervisée · journal                     journal de séance (corpus)       ESP32 + servos + roues
```

Le pont est le seul à parler au robot : chaque commande, qu'elle vienne d'un curseur, d'une séquence ou de l'agent IA, traverse la même couche de sécurité (bornage articulaire, limitation de vitesse, plafond de propulsion, verrou d'arrêt d'urgence), puis est archivée.

## Démarrage rapide (sans robot)

Prérequis : Python 3.11 ou plus récent.

```bash
cd robo-scene-console
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m bridge.serveur --sim
```

Ouvrir ensuite <http://127.0.0.1:8765>. Sur macOS, `bash lancer.command` dans le Terminal (ou un double-clic, une fois le fichier autorisé dans Réglages Système › Confidentialité et sécurité) fait tout cela et ouvre le navigateur.

Le robot simulé parle exactement le même protocole que le micrologiciel : tout ce qui fonctionne en simulation fonctionnera sur le robot réel, aux réglages de câblage près.

## Passer au robot réel

1. **Matériel de référence** : ESP32 DevKit, 4 servos (base, épaule, coude, tête), pilote de moteurs TB6612FNG et deux motoréducteurs (facultatif), capteur HC-SR04 (facultatif), batterie LiPo 2S, **interrupteur coup-de-poing coupant l'alimentation des actionneurs**.
2. **Micrologiciel** : ouvrir `firmware/esp32_robot/esp32_robot.ino` dans l'IDE Arduino, installer le paquet de cartes *esp32* d'Espressif, puis les bibliothèques *ESP32Servo* et *ArduinoJson* (7.x). Adapter le bloc « Configuration à adapter » (broches, limites, mot de passe Wi-Fi), téléverser. Le croquis a été compilé sans erreur pour « ESP32 Dev Module » avec le paquet esp32 3.3.12, ESP32Servo 3.2.1 et ArduinoJson 7.4.3 ; il n'a pas encore été essayé sur une carte physique, d'où l'essai sur cales recommandé plus bas.
3. **Configuration** : dans `config.toml`, section `[robot]`, choisir `transport = "serie"` (câble USB ; renseigner `port_serie`, par exemple `/dev/tty.usbserial-0001` sur Mac) ou `transport = "tcp"` (se connecter au réseau Wi-Fi `ROBO-SCENE-01` créé par l'ESP32 ; adresse `192.168.4.1`). Les limites articulaires de `config.toml` doivent être **identiques** à celles du micrologiciel.
4. Lancer `python -m bridge.serveur` (sans `--sim`).

| Fonction | Broche ESP32 | Remarque |
|---|---|---|
| Servos Base, Épaule, Coude, Tête | 13, 14, 27, 26 | alimentation 5–6 V séparée, masses communes |
| TB6612 PWMA / AIN1 / AIN2 | 25 / 33 / 32 | roue gauche |
| TB6612 PWMB / BIN1 / BIN2 | 4 / 16 / 17 | roue droite |
| TB6612 STBY | 18 | |
| Tension batterie | 34 | pont diviseur 10 kΩ / 3,3 kΩ |
| HC-SR04 TRIG / ECHO | 19 / 23 | ECHO en 5 V : diviseur obligatoire |
| Bouton d'arrêt local (NF) | 22 | mettre `BOUTON_ARRET` à 0 si absent |

Le protocole complet figure dans `PROTOCOLE.md` ; il permet d'adapter n'importe quel autre microcontrôleur.

## Utilisation

| Zone | Rôle |
|---|---|
| **ARRÊT** (ou touche Échap, ou barre d'espace hors champ de saisie) | Arrêt d'urgence logiciel verrouillé ; « Réarmer » est une action distincte et volontaire. |
| **Suivi** | Schéma des articulations, plan du plateau 4 × 3 m (jardin, cour, avant-scène, lointain) avec trace et rayon du capteur, tuiles et courbes sur 12 s. |
| **Téléopération** | Un curseur par articulation ; manette tactile ou flèches / ZQSD pour les roues. Relâcher = arrêt (homme mort de 400 ms côté pont, chien de garde de 500 ms côté robot). |
| **Séquences** | Jouer, arrêter, charger dans l'éditeur ; « Capturer la pose » ajoute la position courante ; durées et pauses modifiables ; enregistrement en JSON dans `sequences/`. |
| **Interaction IA** | Consigne en français → proposition (action, confiance, justification). Sous le seuil, la proposition est **bloquée** ; au-dessus, elle attend la **validation** de l'opératrice. |
| **Journal** | Événements en direct, notes observationnelles horodatées, clôture de séance. |

### Confiance de l'agent IA

La confiance retenue vaut `min(confiance déclarée par le modèle, confiance de vérification)`. La vérification est déterministe et indépendante du modèle : angles hors limites, obstacle à moins de 40 cm devant, déplacement de plus de 3 s, séquence inexistante, etc. Une auto-évaluation d'un modèle de langage n'étant pas une probabilité calibrée, elle ne peut jamais, à elle seule, autoriser un mouvement.

Sans clé API, un analyseur de règles hors ligne prend le relais (consignes simples : « salut », « repos », « avance », « tourne à gauche », « lève la tête »…). Pour activer Claude :

```bash
pip install anthropic
export ANTHROPIC_API_KEY=…      # ne jamais l'écrire dans config.toml
python -m bridge.serveur
```

Le modèle et la température se règlent dans `[ia]`. Le profil « commande » utilise une température basse (0,2) ; le profil 0,7 de votre protocole de génération dramaturgique reste réservé aux monologues, dialogues et scènes. L'API Anthropic refuse, pour les modèles récents, que `temperature` et `top_p` soient fixés simultanément : le pont n'envoie donc que la température.

## Corpus de séance

Chaque lancement ouvre une séance identifiée selon la nomenclature `[DATE]_[SYSTÈME]_[TYPE]_[NUMÉRO]` (par défaut `20261008_ESP32_S04_001`), rangée dans `corpus/[Système]/[Type]/[Date]/` :

- `….jsonl` : commandes (origine : manuel, séquence, IA), refus, arrêts, propositions IA **avec le prompt intégral**, décisions, notes, télémétrie à 5 Hz ;
- `….json` : métadonnées (opératrice, transport, paramètres de sécurité et d'IA, compteurs, notes observationnelles, début et fin).

Renseigner `operatrice` et `type` dans `[protocole]` avant la séance. Le dossier `corpus/` se versionne avec Git comme le reste du protocole.

## Sécurité — à lire avant toute séance avec des personnes

- La console est une couche **logicielle**. Un arrêt d'urgence matériel qui coupe l'alimentation des actionneurs reste indispensable ; c'est l'objet de la norme ISO 13850 et, pour sa réalisation électrique, de l'IEC 60204-1.
- La norme ISO 10218-1:2025 vise les robots industriels et exclut les robots de service accessibles au public ; ses principes (conception intrinsèquement sûre, modes à vitesse réduite) restent une bonne référence pour un robot de scène.
- Par défaut, le serveur n'écoute que sur `127.0.0.1`. Passer `hote = "0.0.0.0"` pour piloter depuis une tablette expose la commande **sans authentification** à tout le réseau local : ne le faire que sur un réseau isolé dédié à la scène.
- Répéter d'abord en simulation, puis robot sur cales (roues en l'air), puis au sol sans public.

## Interface en ligne (Netlify)

L'interface est publiée sur <https://robo-scene.netlify.app> (console) et <https://robo-scene.netlify.app/partenaire>. Netlify ne sert que des pages statiques : le pont Python, le robot, vos documents et les données des acteurs restent sur votre ordinateur, et la page en ligne se connecte au pont local, `ws://127.0.0.1:8765/ws`.

1. Lancer le pont sur l'ordinateur (`bash lancer.command`).
2. Ouvrir l'adresse en ligne : la pastille passe à « Robot connecté ». Si le pont n'est pas joint, un bandeau l'indique ; « Modifier l'adresse » permet de viser un autre port ou une autre machine.
3. Le pont n'accepte que les pages qu'il sert lui-même et celles que liste `[serveur] origines_autorisees` dans `config.toml` ; toute autre page est refusée (HTTP 403), ce qui empêche un site tiers ouvert dans le navigateur de commander le robot.

Seul le dossier `web/` est publié (`netlify.toml`), avec des en-têtes qui interdisent l'intégration dans un cadre et l'indexation. Essai réalisé le 10 octobre 2026 avec Chromium : connexion de la page en ligne au pont local réussie. Le comportement de Safari envers `ws://127.0.0.1` depuis une page https n'a pas été vérifié : en cas d'échec, utiliser Chrome, ou l'interface locale <http://127.0.0.1:8765>.

Pour republier après une modification de l'interface : relier le dépôt GitHub au projet Netlify (déploiement continu), ou relancer un déploiement manuel du dossier `web/`.

## Partenaire de théâtre

Ouvrir <http://127.0.0.1:8765/partenaire> (lien « Partenaire » dans l'en-tête de la console). Le bouton ARRÊT et la touche Échap y fonctionnent comme dans la console : ils figent le robot, coupent la voix et suspendent la répétition.

| Onglet | Rôle |
|---|---|
| **Formation** | Les 97 exercices du *Livret d'exercices pour acteurs* (trois années), restitués tels quels : fiche technique, déroulement minuté, variantes, note pédagogique. Le partenaire guide l'exercice à voix haute avec minuteurs ; le robot peut l'accompagner (souffle en quatre temps, immobilité, miroir lent). Séance type composée selon la structure du livret, calendrier de progression, grille d'auto-évaluation hebdomadaire. |
| **Répétition** | Le partenaire donne les répliques des autres rôles (voix de synthèse, une voix par personnage) et écoute l'acteur. Il souffle le début de la réplique après un silence réglable ; il propose une mémorisation progressive (texte, initiales, premier mot, masqué). Mesures : reprise de réplique, durée, pauses, débit, intensité, fidélité au texte. Trajectoire longitudinale des passages. |
| **Variations** | Pour chaque réplique : indices textuels (didascalies, lexique, ponctuation) et trois propositions — lecture du texte, contre-emploi, mélange de deux affects (exercice 5.3 du livret) — avec intensité de 1 à 10 et cinq styles (exercice 6.3). Deux régimes de rendu : **émulation humaine** (prosodie et posture) ou **voie machinique** (facteurs d'effort de Laban — poids, temps, espace, flux — et voix aplatie ou signal tonal sans mots). L'effort peut être composé directement, sans étiquette émotionnelle. |
| **Analyse de pièce** | Distribution de la parole, réseau de coprésence, matrice des configurations, stichomythies, tirades, fiche de personnage (questions de Stanislavski et quatre couches du livret). Lecture interprétative (fable, modèle actantiel, enjeux, pistes de jeu, place du robot) avec une clé API ; les citations non retrouvées mot pour mot dans la pièce sont retirées. |
| **Répertoire** | Recherche croisée dans DraCor (24 corpus, dont 1 940 pièces françaises et Shakespeare) par nombre d'hommes, de femmes, de personnages, genre et époque, puis import du texte intégral avec sa licence. Import de vos propres textes (collage, .txt, .docx). Liens vers les catalogues CEAD, Playwrights Guild of Canada, Le Proscenium, Théâtre-contemporain.net, Doollee et Folger Shakespeare. |
| **Conseiller** | Questions sur le jeu, la voix, le corps, la dramaturgie, la mise en scène, la scénographie, la robotique et l'IA, à partir de vos documents indexés (et de la pièce étudiée). Sans clé API : passages pertinents avec leur référence ; avec clé : synthèse dont chaque référence est contrôlée. |
| **Coprésence (régie)** | Partition du chapitre 7 (attente partagée, marche accordée, adresse au public, silence tenu) et perturbations P1 à P3. Le plan est scellé par empreinte SHA-256 inscrite au journal de séance ; son descellement vérifie l'intégrité. L'onglet est destiné au poste de régie, non à l'écran de l'acteur. |
| **Acteurs et consentements** | Pseudonymes, quatre consentements séparés et révocables (mesures vocales, transcription, caméra, versement au corpus de recherche), historique de formation, droit de retrait qui efface toutes les données de l'acteur. |

### Voix, écoute et vie privée

- La **détection vocale** (latences, pauses, intensité) est calculée dans le navigateur ; aucun son n'est enregistré.
- La **transcription** utilise la reconnaissance vocale du navigateur ; le partenaire exige le traitement local lorsque le navigateur l'offre (`processLocally`). Sinon, selon le navigateur, l'audio peut être traité par un service distant ; c'est pourquoi elle exige un consentement distinct.
- La **caméra** (expérimentale) estime la pose avec MediaPipe dans le navigateur ; le modèle se télécharge depuis Internet au premier usage ; seules des grandeurs cinématiques sont conservées.
- Les voix disponibles dépendent du système (sur macOS : Réglages Système › Accessibilité › Contenu énoncé, pour ajouter des voix françaises du Canada ou de France).

### Incarnation robotique

Désactivée par défaut (`[partenaire] incarnation = false`), elle se bascule dans l'en-tête. Les gestes du partenaire — accompagnements, variations, répliques, situations de coprésence — sont des images clés bornées qui traversent la même couche de sécurité que la téléopération ; l'arrêt d'urgence les interrompt.

### Vos documents

La base de connaissances indexe les fichiers de `partenaire/sources/`. Pour en ajouter : déposer le fichier (.docx, .pdf, .md, .txt, .html), puis lancer `python -m bridge.partenaire.connaissances`. Après une nouvelle édition du livret : `python -m bridge.partenaire.livret`.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Vingt-neuf tests, tous exécutés sur le robot simulé et sans appel réseau, à l'exception de l'import DraCor, qui n'est pas testé automatiquement :
- **console (7)** : couche de sécurité ; scénario complet (bornage, arrêt et réarmement, homme mort, IA validée et bloquée, notes, métadonnées) ; confiance abaissée devant un obstacle ; numérotation des séances ; moteur Claude simulé ;
- **partenaire (22)** : index et livret ; lecteurs de texte brut et de TEI ; analyse dramaturgique ; variations bornées et déterministes ; lisibilité de la voie machinique ; mesures et descripteurs ; consentements et retrait ; plan scellé et falsification détectée ; garde-fous des agents contre les références et citations inventées ; répétition complète par le pont ; refus des gestes après un arrêt d'urgence.

## Arborescence

```
robo-scene-console/
├── config.toml              réglages (robot, sécurité, IA, protocole)
├── lancer.command           lancement par double-clic (macOS)
├── PROTOCOLE.md             contrat JSON pont ↔ robot
├── bridge/                  serveur-pont Python
│   ├── serveur.py           application, contrôleur, boucles de surveillance
│   ├── securite.py          bornage, vitesse, arrêt d'urgence
│   ├── transports.py        simulé, série, TCP
│   ├── ia.py                agent supervisé (Claude ou règles)
│   ├── journal.py           séance et métadonnées ROBO-SCÈNE
│   └── partenaire/          partenaire de théâtre (connaissances, livret, textes, dramaturgie,
│                            variations, analyse du jeu, coprésence, agents, consentements)
├── web/                     interface (HTML, CSS, JS sans dépendance externe)
├── firmware/esp32_robot/    micrologiciel Arduino pour ESP32
├── sequences/               chorégraphies enregistrées (JSON)
├── partenaire/
│   ├── sources/             vos documents (base de connaissances)
│   ├── index/               index de recherche et livret structuré (générés)
│   ├── pieces/              pièces de la bibliothèque (JSON)
│   ├── repertoire/          catalogues DraCor en cache (recherche hors ligne)
│   ├── demo/                scène de démonstration originale « Le Souffleur »
│   └── donnees/             acteurs, passages, plans scellés (exclus de Git)
└── tests/
```
