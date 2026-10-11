# Langage de commande unifié ROBO-SCÈNE (v2.0)

Un seul langage pour tous les robots, quels que soient leur marque, le langage dans lequel leur pilote est écrit et
le canal qui les relie au pont. La v2 étend la v1 sans la modifier : un micrologiciel v1 reste pleinement compatible.

Un objet JSON **par ligne** (terminée par `\n`), encodé en UTF-8.

## Du pont vers le robot

| `t`      | Champs                          | Effet attendu côté robot |
|----------|---------------------------------|--------------------------|
| `hello`  | —                               | Répondre par un message `info`. |
| `hb`     | —                               | Battement de cœur toutes les 200 ms ; réarme le chien de garde. |
| `servos` | `deg` : liste de N valeurs, `ms` : durée | Rejoindre `deg` en `ms` millisecondes. Valeurs en degrés (ou en mm pour un axe déclaré `unite = "mm"`), déjà bornées par le pont ; le robot les borne à nouveau. |
| `drive`  | `l`, `r` : −1 à 1               | Commande des roues gauche et droite (plafonnée). |
| `estop`  | —                               | Arrêt immédiat : roues à zéro, servos **figés à leur position** (ne jamais couper le couple d'un bipède) ; verrou jusqu'à `reset`. |
| `reset`  | —                               | Lever le verrou (refusé si un bouton d'arrêt local est enfoncé). |
| `geste`  | `nom` *(v2, facultatif)*        | Jouer un geste natif du robot (si le robot en déclare). |
| `dire`   | `texte` *(v2, facultatif)*      | Synthèse vocale embarquée (si le robot en dispose). |

## Du robot vers le pont

| `t`    | Champs | Fréquence |
|--------|--------|-----------|
| `info` | `nom`, `fw`, `servos` (N), `propulsion` (booléen), `articulations` *(v2, noms)* | Au démarrage et sur `hello`. |
| `tel`  | `ms`, `deg` (N valeurs), `drive` [l, r], `vbat` (V), `dist` (cm), `estop` (booléen), `pose` [x, y, cap] *(facultatif)*, `estimee` *(v2 : vrai si `deg` est une cible et non une mesure)* | 20 Hz. |
| `err`  | `msg`, `niveau` *(v2, facultatif : « info »)* | Sur commande refusée ou illisible. |

## Règles de sécurité imposées à tout pilote

1. **Chien de garde** : sans message du pont pendant 500 ms, les roues s'arrêtent.
2. **Bornage local** des angles et de la propulsion, indépendant du pont (défense en profondeur).
3. **Arrêt verrouillé** : `estop` (ou bouton local) fige le robot jusqu'à un `reset` explicite.
4. Les lignes illisibles sont ignorées, jamais interprétées partiellement.

Ces règles logicielles complètent, sans le remplacer, l'arrêt d'urgence matériel qui coupe l'alimentation des
actionneurs (ISO 13850 ; IEC 60204-1 pour sa réalisation électrique).

## Canaux et pilotes (bridge/robots/pilotes)

| Pilote | Canal | Robots visés |
|---|---|---|
| `ligne_json` | série USB, TCP, UDP, WebSocket, simulation | ESP32, Arduino, Pico, Teensy, Raspberry Pi (trousses `sdk/`) |
| `hiwonder_bus` | bus de servomoteurs LewanSoul/LX (trames `55 55 ID LONG CMD … SOMME`) | AiNex, bras xArm, tout robot à servos de bus Hiwonder |
| `rosbridge` | WebSocket rosbridge (ROS 1 ou ROS 2) | bras, humanoïdes et bases mobiles sous ROS |
| `mqtt` | courtier MQTT (`{prefixe}/{id}/cmd`, `{prefixe}/{id}/tel`) | microcontrôleurs Wi-Fi, installations scénographiques |
| `osc` | Open Sound Control (`/robot/servos`, `/robot/tel`…) | Max, Pure Data, TouchDesigner, Isadora, QLab |
| `http` | API REST (gabarits de requêtes, pointeurs JSON) | robots à interface web |
| `reachy_mini` | trousse Python du Reachy Mini | Reachy Mini (pose de tête, corps, antennes) |
| `externe` | programme pilote sur stdin/stdout | pilote écrit en **n'importe quel langage** |

## Trousses de développement (sdk/)

| Langage | Fichier | Usage |
|---|---|---|
| Python | `sdk/python/robo_scene_sdk.py` | `PiloteRobot.executer()` (stdin/stdout) ou `servir_tcp(3333)` (embarqué) |
| JavaScript | `sdk/javascript/robo-scene-pilote.mjs` | Node.js ≥ 18, sans dépendance ; `executer()` ou `servirTcp(3333)` |
| C++17 | `sdk/cpp/robo_scene_pilote.hpp` | un seul en-tête, sans dépendance ; `executer()` |
| Arduino | `sdk/arduino/RoboScenePilote` | bibliothèque (ArduinoJson 7) ; `boucle()` dans `loop()` |

Chaque trousse applique elle-même les quatre règles de sécurité ci-dessus. Un robot se déclare dans `robots/<id>.toml`
(articulations, bornes, repos, pilote, connexion, sécurité) ; voir les profils d'exemple.

## Exemple d'échange

```
→ {"t":"hello"}
← {"t":"info","nom":"ROBO-SCENE-01","fw":"1.0.0","servos":4,"propulsion":true}
→ {"t":"servos","deg":[90,140,60,90],"ms":900}
← {"t":"tel","ms":10432,"deg":[90.0,104.4,82.0,90.0],"drive":[0,0],"vbat":8.11,"dist":143.5,"estop":false}
→ {"t":"estop"}
← {"t":"tel", …, "estop":true}
```
