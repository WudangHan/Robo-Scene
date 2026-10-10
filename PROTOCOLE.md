# Protocole pont ↔ robot (v1.0)

Un objet JSON **par ligne** (terminée par `\n`), encodé en UTF-8, identique sur le port série (115 200 bauds) et sur la connexion TCP (port 3333). Tout microcontrôleur qui respecte ce contrat peut être piloté par la console : ESP32, Arduino, Raspberry Pi Pico, Teensy, etc.

## Du pont vers le robot

| `t`      | Champs                          | Effet attendu côté robot |
|----------|---------------------------------|--------------------------|
| `hello`  | —                               | Répondre par un message `info`. |
| `hb`     | —                               | Battement de cœur toutes les 200 ms ; réarme le chien de garde. |
| `servos` | `deg` : liste de N angles, `ms` : durée | Interpoler linéairement de la position actuelle vers `deg` en `ms` millisecondes. Les angles sont déjà bornés par le pont ; le robot les borne à nouveau. |
| `drive`  | `l`, `r` : −1 à 1               | Commande des roues gauche et droite (plafonnée). |
| `estop`  | —                               | Arrêt immédiat : roues à zéro, servos figés ; verrou jusqu'à `reset`. |
| `reset`  | —                               | Lever le verrou (refusé si un bouton d'arrêt local est enfoncé). |

## Du robot vers le pont

| `t`    | Champs | Fréquence |
|--------|--------|-----------|
| `info` | `nom`, `fw`, `servos` (N), `propulsion` (booléen) | Au démarrage et sur `hello`. |
| `tel`  | `ms`, `deg` (N angles), `drive` [l, r], `vbat` (V), `dist` (cm), `estop` (booléen), `pose` [x, y, cap] *(facultatif, si odométrie)* | 20 Hz. |
| `err`  | `msg` | Sur commande refusée ou illisible. |

## Règles de sécurité imposées au micrologiciel

1. **Chien de garde** : sans message du pont pendant 500 ms, les roues s'arrêtent.
2. **Bornage local** des angles et de la propulsion, indépendant du pont (défense en profondeur).
3. **Arrêt verrouillé** : `estop` (ou bouton local) fige le robot jusqu'à un `reset` explicite.
4. Les lignes illisibles sont ignorées, jamais interprétées partiellement.

Ces règles logicielles complètent, sans le remplacer, l'arrêt d'urgence matériel qui coupe l'alimentation des actionneurs.

## Exemple d'échange

```
→ {"t":"hello"}
← {"t":"info","nom":"ROBO-SCENE-01","fw":"1.0.0","servos":4,"propulsion":true}
→ {"t":"servos","deg":[90,140,60,90],"ms":900}
← {"t":"tel","ms":10432,"deg":[90.0,104.4,82.0,90.0],"drive":[0,0],"vbat":8.11,"dist":143.5,"estop":false}
→ {"t":"estop"}
← {"t":"tel", …, "estop":true}
```
