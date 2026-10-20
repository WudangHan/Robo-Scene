# Langage de commande unifié ROBO-SCÈNE (v2.1)

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
| `geste_arret` | — *(v2.1)*                 | Interrompre le geste natif en cours, sans verrou d'arrêt. |
| `lumiere` | `rgb` : [r, g, b] 0–255, `ou` *(v2.1, facultatif)* | Lumières du robot (« yeux », DEL de la carte). |
| `afficher` | `texte` ou `motif` *(v2.1, facultatif)* | Afficheur du robot (matrice de points). |

## Du robot vers le pont

| `t`    | Champs | Fréquence |
|--------|--------|-----------|
| `info` | `nom`, `fw`, `servos` (N), `propulsion` (booléen), `articulations` *(v2, noms)* | Au démarrage et sur `hello`. |
| `tel`  | `ms`, `deg` (N valeurs), `drive` [l, r], `vbat` (V), `dist` (cm), `estop` (booléen), `pose` [x, y, cap] *(facultatif)*, `estimee` *(v2 : vrai si `deg` est une cible et non une mesure)* | 20 Hz. |
| `err`  | `msg`, `niveau` *(v2, facultatif : « info »)* | Sur commande refusée ou illisible. |
| `evt`  | `type` : `geste` (`nom`, `etat` : debut, fin, interrompu), `marche` (`mode`), `chute` (`sens`, `releve`), `toucher`, `bouton`, `manette` *(v2.1)* | Ponctuel. Une `chute` arrête toute la flotte ; le relevé reste une décision humaine. |

Champs facultatifs v2.1 : `info.gestes` (gestes natifs), `tel.imu` {`tangage`, `roulis`} (degrés), `tel.chute`
(`avant`, `arriere` ou absent). Un robot v2.0 ignore les messages v2.1 qu'il ne connaît pas.

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
| `tonypi_rpc` | JSON-RPC 2.0 en HTTP vers le serveur de Hiwonder (port 9030) | Hiwonder TonyPi Pro sans installation (servos 1–16, tête, gestes natifs, marche) |
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

## Drone de scène (O-13)

Repère commun : le **repère du théâtre** (`web/drone/salle.json`) — origine au centre de la ligne du cadre de scène, au
niveau du plateau ; `x` vers cour, `y` vers le haut, `z` vers la salle, en mètres. Lacet en degrés : 0 = nez vers la
salle, 90 = nez vers cour, croissant dans le sens antihoraire vu de dessus ; `lacet_vitesse` dans le même sens.

### Page « Drone » → pont (WebSocket `/ws`)

| `op` | Champs | Effet |
|---|---|---|
| `drone_etat` | — | Renvoie `drone_etat` (adaptateur, mode, conditions, liste de contrôle) |
| `drone_connecter` / `drone_deconnecter` | `adaptateur` : `simulation`, `mavlink`, `tello`, `ligne_json` | Adaptateur réel ouvert seulement si `[drone] reel_autorise = true` |
| `drone_mode` | `mode` : `plateau`, `salle_vide`, `representation` ; `par` | `salle_vide` exige des initiales ; `representation` réel exige `vol_en_representation = true` |
| `drone_interpretes` | `liste` : `[{x, z}]` | Cylindres d'exclusion autour des interprètes |
| `drone_liste` | `coches` : identifiants ; `par` | Liste de contrôle avant vol (complète + initiales requises pour le vol réel) |
| `drone_decoller` | `hauteur` (0,6 à 3 m) | Après vérification des conditions et de la zone |
| `drone_aller` | `p` (repère ou `[x, y, z]`), `duree`, `vitesse`, `lacet` | Destination et segment vérifiés ; trajet à secousse minimale, consignes à 10 Hz ; réponse `drone_aller` (durée retenue) |
| `drone_vitesse` | `v` `[vx, vy, vz]` m/s, `lacet_vitesse` °/s | Valable 0,5 s ; plafonnée ; composantes qui franchiraient une limite retirées |
| `drone_stationnaire`, `drone_atterrir` | — | — |
| `drone_coupure` | `confirmation` : `"COUPER"` | Coupure des moteurs (le drone tombe) puis ARRÊT global |
| `drone_hb` | — | Battement de la page (4 Hz) ; silence > 1 s : stationnaire ; > 4 s : atterrissage |

Pont → page : `drone_tel` (10 Hz : `p`, `v`, `lacet`, `batterie`, `arme`, `etat`, `adaptateur`, `reel`, `urgence`,
`position` « mesurée » ou « estimée »), `drone_etat`, `drone_refus` (`msg`). L'`estop` global pose le drone ;
`rearmer` lève son verrou.

### Pont → ordinateur compagnon (adaptateur `ligne_json`, UDP, une ligne JSON par message)

Du pont : `{"t": "drone", "cmd": "hello" | "armer" | "decoller" (hauteur) | "position" (p, lacet) | "vitesse" (v,
lacet_vitesse) | "stationnaire" | "atterrir" | "urgence" | "couper"}`, coordonnées dans le repère du théâtre.
Du compagnon : `{"t": "tel", "p": [x, y, z], "v": […], "lacet": …, "batterie": …, "arme": …, "etat": "au_sol" |
"decollage" | "vol" | "atterrissage" | "coupe"}`. Le compagnon applique ses propres sécurités (perte de liaison,
géorepérage de l'autopilote) ; celles du pont s'y ajoutent sans les remplacer.

## Chien de scène (O-14)

Repère du théâtre (comme le drone) ; positions au sol en `[x, z]`, lacet en degrés (0 = museau vers la salle,
croissant dans le sens antihoraire vu de dessus).

### Page « Chien » → pont

| `op` | Champs | Effet |
|---|---|---|
| `chien_etat`, `chien_connecter` (`adaptateur` : `simulation`, `rosbridge`, `petoi`, `ligne_json`), `chien_deconnecter` | | Comme le drone ; adaptateur réel seulement si `[chien] reel_autorise = true` |
| `chien_mode`, `chien_interpretes`, `chien_liste` | comme le drone | Sol praticable du mode, cercles des interprètes, liste de contrôle |
| `chien_posture` | `posture` : `debout`, `couche`, `assis`, `patte`, `salut`, `etirement` | « couche » toujours permis (position sûre) ; les autres exigent les conditions du réel |
| `chien_aller` | `p` (repère ou `[x, z]`), `duree`, `lacet` | Destination et trajet vérifiés ; poursuite à 10 Hz ; réponse `chien_aller` |
| `chien_vitesse` | `v` : `[avant, gauche]` m/s (repère du corps), `lacet_vitesse` °/s | Valable 0,5 s ; plafonnée selon la surface ; filtrée par le point d'arrêt prévu |
| `chien_arreter`, `chien_coupure` (`"COUPER"`), `chien_hb`, `chien_allure`, `chien_regard` | | Arrêt ; coupure puis ARRÊT global ; battement ; consignation |

Pont → page : `chien_tel` (10 Hz : `p` `[x, y, z]`, `v`, `lacet`, `batterie`, `etat` — `couche`, `debout`, `affaisse` —,
`posture`, `position`, `adaptateur`, `reel`, `urgence`), `chien_etat`, `chien_refus`.

### Pont → robot

- **rosbridge** : `advertise` puis `publish` de `geometry_msgs/Twist` sur `/cmd_vel` (avant, gauche, lacet en rad/s),
  `std_msgs/String` sur `/robo_scene/posture`, `std_msgs/Bool` sur `/robo_scene/arret_urgence` ; `subscribe` à
  `nav_msgs/Odometry` sur `/odom` (sujets réglables dans `[chien.rosbridge]`).
- **petoi** : jetons série OpenCat terminés par un saut de ligne (`kbalance`, `krest`, `ksit`, `khi`, `kstr`, `kwkF`,
  `kwkL`, `kwkR`, `kbk`, `d`).
- **ligne_json** (UDP) : `{"t": "chien", "cmd": "vitesse" (avant, gauche, lacet_vitesse) | "posture" (nom) | "couper"}` ;
  retour `{"t": "tel", "p": [x, y, z], "lacet": …, "etat": …, "posture": …, "batterie": …}`.

## Hiwonder TonyPi Pro

Profil `robots/tonypi_pro.toml` : 20 axes nommés comme les degrés de liberté du robot virtuel (`epaule_d.flexion`,
`genou_g.flexion`, `cheville_g.roulis`, `main_d.fermeture`, `tete.rotation`…), en **degrés relatifs à la position debout
officielle** (groupe « stand » ; 0 partout = debout), mains en % de fermeture. Conversion (`bridge/robots/tonypi.py`) :
position native = `zero + sens × valeur × pas_par_unite` ; servos de bus 1–18 : 1000 pas pour 240° ; servos PWM de la
tête (`pwm:1` tangage, `pwm:2` lacet) : 500–2500 µs pour 180°.

| Liaison | Côté robot | Ce qui passe |
|---|---|---|
| `ligne_json` TCP 3333 | `sdk/python/tonypi_embarque.py` (SDK Hiwonder, carte contrôleur `/dev/ttyAMA0` à 1 Mbit/s ; arrêter d'abord `tonypi.service`) | 20 axes, `geste` (groupes d'actions de la liste fermée), `drive` → marche native, `estop` (arrêt du bus : servos figés), `dire`, `lumiere`, télémétrie (batterie, `imu`, `dist`, `chute`), `evt` (chute, toucher, bouton, manette), flux MJPEG `--camera 8080` |
| `tonypi_rpc` | serveur JSON-RPC de Hiwonder, déjà lancé au démarrage | servos 1–16 (`SetBusServoPulse`), tête (`set_pwm_servo`), `RunAction`, `StopActionGroup` ; positions 1–15 relues (`GetBusServosPulse`) |

Marche : `drive` (l, r) → `go_forward` (l ≈ r > 0,15), `back` (l ≈ r < −0,15), `turn_right` (l > r), `turn_left`, en
boucle jusqu'à l'arrêt ou au chien de garde de 500 ms. Chute : angle de la centrale autour de l'axe y de la carte
(critère du relevé automatique de Hiwonder) proche de 0° (avant) ou de 180° (arrière) pendant 1 s.
