# Robo-Scène

*Plateforme intégrée du projet de recherche « L'IA au service de la création théâtrale »* (Sylvain Gagné, Ph. D., chercheur indépendant non affilié et autofinancé) :
console de pilotage multi-robots, partenaire de théâtre, robot virtuel humanoïde, atelier dramaturgique instrumenté, pont scénique, interface
spectateur, analyse et gouvernance, réunis autour d'un seul journal des cinq opérations de la cocréation instrumentée
(consigne, génération, sélection, transformation, attribution).

## Plateforme intégrée

La plateforme réalise les 58 fonctions du *Cahier des fonctions et plan d'action* v1.0 (11 oct. 2026) : les fonctions
« doit » (N, A, R, S, Q, G, P) et les extensions « pourrait » (O-01 à O-12). La table `bridge/pilotage/fonctions.py`,
affichée dans la page Gouvernance et vérifiée par les tests, rattache chaque fonction à son code, à son test et à ce
qui reste à faire.

| Page | Fonctions | Rôle |
|---|---|---|
| `/` Console | R-01 à R-04, R-07, R-08, N-07, N-08, O-12 | Pilotage de la flotte (robot actif, profils), observateur de sécurité, règle de l'IA, arrêt global, saisie « de tête », surtitres et voix divulguée |
| `/partenaire` | O-01 à O-04, O-10 | Formation, répétiteur (consigne graduée), variations (deux régimes), analyse de pièce, DraCor et export TEI, mode pédagogique É.T.T. |
| `/atelier` | A-01 à A-08, O-01 | Atelier P1 : cinq opérations, routeur D03 sans repli, modèles D13, registre de consigne, verrous de mise en service |
| `/scene` | R-05, R-06, O-05, O-06, O-11, O-12 | Conduite du pont scénique sous GO unique, multi-robots, aperçu et GO simulés dans le jumeau, écho tracé, surtitres |
| `/spectateur` | S-01 à S-06 | Tirage scellé X.2, séance P3 (condition de provenance), questionnaires I-7 et I-6 sur serveur public distinct, avis S-06 |
| `/surtitres` | O-06 | Surtitrage et audiodescription proposés, validés par une personne, étiquetés, exportés en WebVTT |
| `/recherche` | Q-01 à Q-05, O-02, O-08, O-09 | Analyse reproductible (dossier daté, script R, manifeste), codage local des entretiens, veille, tableau public |
| `/gouvernance` | G-01 à G-07, R-08 | Verrous (avis éthique, EFVP), incidents, décisions humaines (Loi 25, art. 12.1), conservation, registre des systèmes |
| `/regie` | P-01 à P-04 | Registre du projet, régisseur IA en lecture seule, revue trimestrielle ISO/IEC 42001, inventaire mensuel, dépôts |
| `/tableau-public` | O-09 | Indicateurs agrégés publiés après validation (seuil de cinq) |

Toutes les pages sont bilingues (français par défaut, anglais), sans ressource externe, et utilisables au clavier.

### Principes appliqués par le code

- **Bibliothèque fermée** : l'IA ne propose qu'un nom de geste ; le mode « angles proposés » reste verrouillé hors séance S04.
- **D03** : un contenu sensible ou confidentiel ne part que vers le modèle local ; si celui-ci est indisponible, la génération est refusée, sans repli distant.
- **D13** : à l'ouverture de chaque séance, la version la plus récente de chaque famille (Claude Opus 5.5 et Sonnet 5.5 ; GPT 6.1 Sol et 6 Luna ; GPT Terra dès qu’une version 6 sera publiée) est adoptée et consignée ; jamais en cours de séance.
- **G-02 et G-04** : toute collecte auprès de personnes (atelier, questionnaires publics, séance P3 publique) est refusée tant que l'avis éthique n'est pas consigné dans `gouvernance/etat.yaml` et que l'EFVP ne couvre pas la version de la fonction ; le mode « essai » reste ouvert, ses données rangées à part.
- **Validation humaine avant diffusion** : surtitres, tableau public, décisions concernant des personnes, notices bibliographiques.
- **Anonymat des publics** : aucune adresse IP, aucun témoin, seuil de cinq ; les moins de 18 ans ne sont jamais enregistrés.

### N'importe quel robot

Chaque robot est décrit par un profil TOML (`robots/`) : articulations et limites, pilote, zone d'exclusion, bibliothèque.
Pilotes fournis : ligne JSON (série, TCP, UDP, WebSocket, simulation), bus de servos Hiwonder (AiNex), rosbridge (ROS 1
et 2), MQTT, OSC, HTTP REST, Reachy Mini et processus externe. Trousses pour écrire un pilote dans le langage du robot :
Python, JavaScript (Node), C++ et Arduino (`sdk/`), toutes conformes au langage de commande unifié v2 (`PROTOCOLE.md`).
Un même geste nommé se joue sur chaque robot validé ; un brouillon est refusé sur robot réel, et les statuts
intermédiaires jouent à demi-vitesse.

### Lancer la plateforme

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=…   OPENAI_API_KEY=…    # facultatif ; jamais dans config.toml
python -m bridge.serveur --sim                       # tous les robots en simulation
```

Ouvrir <http://127.0.0.1:8765>. Pour que le pont soit toujours disponible (en simulation, sans fenêtre du Terminal) : `bash outils/demarrage_automatique.sh installer` (`retirer` pour l'annuler, `etat` pour vérifier). Le service « Pont ROBO-SCÈNE », invisible, démarre à l'ouverture de session et relance le pont s'il s'arrête ; macOS demande une seule fois l'accès au dossier Documents (répondre « Autoriser »). L'application `~/Applications/ROBO-SCÈNE.app` ouvre directement la console. `lancer.command` réinstalle les dépendances dès que `requirements.txt` change. Réglages : `config.toml` (sections `[modeles]`, `[flotte]`, `[scene]`, `[spectateur]`,
`[pilotage]`, `[pedagogie]`, `[diffusion]`). Analyse hors interface : `python -m bridge.analyse --exclure X2-03`.
Le script R de l'analyse principale (lme4, pbkrtest, ordinal) est copié dans chaque dossier d'analyse.

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

Prérequis : Python 3.12 ou plus récent (3.11 pour la seule console).

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

L'interface est publiée sur <https://robo-scene.netlify.app> (console), <https://robo-scene.netlify.app/partenaire> et <https://robo-scene.netlify.app/avatar> (robot virtuel, utilisable sans pont). Netlify ne sert que des pages statiques : le pont Python, le robot, vos documents et les données des acteurs restent sur votre ordinateur, et la page en ligne se connecte au pont local, `ws://127.0.0.1:8765/ws`.

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

## Robot virtuel humanoïde

Ouvrir <http://127.0.0.1:8765/avatar> (lien « Robot virtuel » dans l'en-tête), ou <https://robo-scene.netlify.app/avatar> : le robot virtuel fonctionne entièrement dans le navigateur ; le pont n'est requis que pour le journal de séance, l'interprète par modèle (service unique des modèles, rôle « commande ») et le jumeau du robot physique. Guide complet : `docs/Guide_robot_virtuel_ROBO-SCENE.docx`.

Personnage masculin procédural en 3D (three.js 0.169, licence MIT, servi localement depuis `web/vendor/`) : 32 degrés de liberté bornés (tête, tronc, bassin, épaules, coudes, poignets, doigts, hanches, genoux, chevilles), visage animé par unités d'action FACS (sourcils, paupières, regard, lèvres, mâchoire), présence vivante (respiration, transfert de poids, saccades, clignements), marche sur un plateau figuré (cour, jardin, lointain, avant-scène).

| Onglet | Rôle |
|---|---|
| **Directives** | Consignes écrites ou dictées en français (« lève le bras droit lentement puis souris », « va côté cour et salue le public », « deviens triste, puis dis « Je ne reviendrai pas. » »). Interprète de règles hors ligne (188 exemples de référence, tous vérifiés par les tests), qui corrige les fautes de frappe et rapproche les formulations voisines ; s'il ne comprend pas, le robot le dit à voix haute et propose des commandes proches ; « aide » affiche la liste. Ce qu'il ne comprend pas peut être soumis par le pont au service des modèles (routeur de sensibilité compris), puis revalidé et présenté pour validation humaine. *Annule*, *répète*, *stop*, mémoire de poses. |
| **Émotions et parole** | Douze émotions (les onze du partenaire et le dégoût) à intensité réglable : visage, posture, qualité d'effort de Laban et prosodie. Expressions isolées. Parole par synthèse vocale avec synchronisation labiale par visèmes et battements de tête et de sourcils. |
| **Corps** | Clic et glisser sur une partie du corps ; curseurs de tous les degrés de liberté ; 70 gestes (quotidien, scène, combat de théâtre : saluer, bras au ciel, frapper à la porte, boire, téléphoner, sauter, boxer, tituber, dormir…), 11 poses (dont effondré, en garde, le penseur, statue), mouvements de scène (tour de la scène, cent pas, pirouette, sortie, entrée, pas chassé), poses mémorisées, chorégraphie d'images clés, export et import JSON. |
| **Apparence** | Taille, carrure, corpulence, âge, coiffure, barbe, moustache, peau, yeux, vêtements et couleurs (aussi par directive). |
| **Imitation** | Reproduction en direct du visage, de la tête et de la posture d'une personne filmée (MediaPipe, traitement local, accord explicite, mode miroir) ; « figer l'expression » ; lecture émotionnelle indicative. |
| **Liaisons** | Voix et visage pour les répliques de la page Partenaire (case « Robot virtuel » dans son en-tête) ; journalisation dans la séance ; jumeau du robot physique en lecture ou en pilotage, via la couche de sécurité. |

Cadrages (face, trois-quarts, profil, gros plan, plan américain, en pied, plan large, plongée), cinq ambiances lumineuses, *Mode scène* plein écran et *Fenêtre* séparée pour un second écran. Le bouton ARRÊT et la touche Échap figent le personnage, coupent la parole et envoient l'arrêt d'urgence au pont.

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

162 tests réussis et 1 ignoré (classeur de la grille de biais absent du dépôt), tous sans appel réseau ni matériel :
prototypes P1, P2, P3, T.6 et X.2 (60) ; console (7) ; partenaire (22) ; robots et pilotes (16) ; modèles D13 (7) ;
traçabilité (6) ; spectateur (10) ; analyse (11) ; extensions (8) ; plateforme (3) ; certificats HTTPS (3) ; robot virtuel (9, dont 4 en JavaScript exécutés par Node.js s'il est présent). L'intégration continue
(`.github/workflows/tests.yml`) les exécute à chaque dépôt.

## Arborescence

```
robo-scene/
├── config.toml              réglages (serveur, robots, sécurité, IA, modèles, scène, spectateur, pilotage…)
├── PROTOCOLE.md             langage de commande unifié v2 (pont ↔ robot)
├── bridge/                  serveur-pont et plateforme
│   ├── serveur.py           contrôleur, flotte, sécurité, IA supervisée, WebSocket
│   ├── plateforme.py        montage des pages et des routes de la plateforme
│   ├── trace/               journal unifié des cinq opérations, écart, PROV-O, saisies N-07 et N-08
│   ├── modeles/             service des modèles (D13, D03), clients Anthropic, OpenAI, Ollama
│   ├── robots/              descriptions, pilotes, bibliothèques fermées, flotte
│   ├── atelier/             atelier P1 relié au journal unifié
│   ├── scene/               pont scénique P2.3 multi-robots, aperçu et simulation
│   ├── spectateur/          séance P3, tirage X.2, questionnaires, avis S-06
│   ├── analyse/             Q-01 à Q-05, juges O-02, script R A.2
│   ├── accessibilite/       surtitres et audiodescription (O-06)
│   ├── veille/              veille bibliographique (O-08)
│   ├── diffusion/           C2PA (O-07), tableau public (O-09)
│   ├── gouvernance/         verrous, incidents, décisions, conservation, retrait, biométrie
│   ├── pilotage/            régie, dépôts, rapports, table de couverture
│   └── partenaire/          partenaire de théâtre ; avatar.py : validation et interprète Claude du robot virtuel
├── modules/                 prototypes P1, P2, P3, T.6, X.2 et outils de la Régie (importés tels quels)
├── gouvernance/             état, registre des systèmes, EFVP, conservation (YAML)
├── questionnaires/          instruments I-7 et I-6 (YAML)
├── analyse/                 livre de codes A.1
├── robots/                  profils de robots (TOML)
├── sdk/                     trousses de pilote : Python, JavaScript, C++, Arduino
├── web/                     interfaces (HTML, CSS, JS)
│   ├── avatar/              robot virtuel (corps, visage, animation, parole, directives, imitation)
│   └── vendor/              three.js 0.169 (MIT), servi localement
├── firmware/esp32_robot/    micrologiciel Arduino pour ESP32
├── sequences/               chorégraphies (JSON)
├── partenaire/              sources, index, pièces, répertoire, démo
└── tests/
```

Les données (`donnees/`, `corpus/`, `donnees_ett/`, `partenaire/donnees/`) restent sur l'ordinateur et sont exclues de Git.
