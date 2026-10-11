# P2.2 — Bibliothèque fermée de gestes et jumeau numérique (Reachy Mini)

Projet « L'IA au service de la création théâtrale » — Sylvain Gagné, Ph. D. — version 1.0, 5 octobre 2026.

## Principe

Aucun module d'IA ne commande les moteurs. Un modèle de langage peut seulement **proposer le nom** d'un geste
pris dans `gestes_scene/bibliotheque_gestes.yaml` ; l'opérateur humain le **confirme** et le déclenche
(plan de prévention P2.1, §6.4). Chaque geste progresse par statuts :
`brouillon → valide_sim → valide_robot_lent → valide` ; seul un humain modifie un statut.

| Cible / vitesse | Statut minimal exigé |
|---|---|
| simulateur, lente ou pleine | brouillon |
| robot, lente (×0,5) | valide_sim |
| robot, pleine | valide |

## Contenu

| Chemin | Rôle |
|---|---|
| `code/gestes_scene/bibliotheque_gestes.yaml` | 11 gestes (images clés, intention, qualités d'effort de Laban, statut) |
| `code/gestes_scene/bibliotheque.py` | Chargement, validation des limites (SDK et projet), interpolation à jerk minimal |
| `code/gestes_scene/executeur.py` | Exécuteur fermé : proposition, autorisation selon le statut, confirmation, journal JSONL |
| `code/gestes_scene/interface_ia.py` | Outil « proposer_geste » pour l'API (énumération fermée, aucun paramètre moteur) |
| `code/gestes_scene/cli.py` | Ligne de commande de l'opérateur |
| `code/tests/` | 8 tests (bibliothèque conforme, refus hors bibliothèque, confirmation obligatoire, etc.) |
| `simulation_MuJoCo/jumeau.py` | Jumeau numérique sans affichage : rapport de validation et planches d'images |
| `simulation_MuJoCo/rapports/` | Rapport du 5 oct. 2026 et planches par geste |

## Installation (macOS)

```bash
python3 -m venv ~/venv-reachy && source ~/venv-reachy/bin/activate
pip install "reachy-mini[mujoco]" pyyaml pillow pytest
```

## Utilisation

```bash
# depuis 05_Prototypes/P2_Scenographie_robotique
python -m pytest code/tests                     # tests, sans robot
cd code && python -m gestes_scene.cli valider   # limites
python -m gestes_scene.cli lister

# jumeau numérique sans affichage (rapport + images)
cd ../simulation_MuJoCo && python jumeau.py

# simulateur graphique du SDK, puis jeu d'un geste avec confirmation
mjpython -m reachy_mini.daemon.app.main --sim   # macOS ; ailleurs : reachy-mini-daemon --sim
cd ../code && python -m gestes_scene.cli jouer acquiescer --cible sim --vitesse lente
```

## Limites appliquées

- **SDK** (documentation « Core Concepts ») : tangage et roulis de la tête ±40°, lacet de la tête ±180°,
  rotation du corps ±160°, écart tête/corps ≤ 65°.
- **Projet** (inférence prudente, à recalibrer) : translations x, y ±20 mm, z de −20 à +25 mm,
  antennes ±90°, vitesses de pointe estimées ≤ 120°/s (tête, corps), ≤ 360°/s (antennes),
  ≤ 80 mm/s (translation), segment ≥ 0,25 s.

## Convention de scène

Robot face au public : « cour » = droite vue de la salle = gauche du robot = lacet positif.
Antennes : 0° = dressées à la verticale.

## Licence

Code du projet : à préciser (proposition : Apache 2.0, comme le SDK, plan G.6).
Le modèle MuJoCo et la cinématique proviennent du SDK Reachy Mini (Apache 2.0) et ne sont pas copiés ici.

---

# P2.3 — Pont scénique (ajout du 5 octobre 2026)

Le paquet `pont_scenique` joue une **conduite** (liste de repères) : à chaque GO de la régie, il déclenche
la lumière (sACN / E1.31), le son (QLab par OSC, port 53000), des messages OSC libres, l'étiquette de
provenance affichée par l'interface spectateur (P3, hypothèse H4) et des gestes du robot — ces derniers
**uniquement** par l'exécuteur à bibliothèque fermée de `gestes_scene`.

| Chemin | Rôle |
|---|---|
| `pont_scenique/conduite_exemple.yaml` | Conduite d'essai en 7 repères, avec plan de feu minimal |
| `pont_scenique/conduite.py` | Chargement et validation (projecteurs, niveaux, gestes connus, provenance) |
| `pont_scenique/sorties.py` | Sorties QLab/OSC, DMX sACN avec transferts à 30 Hz, gestes ; mode « à blanc » |
| `pont_scenique/moteur.py` | GO, retour, ARRÊT logiciel, actions différées |
| `pont_scenique/regie.py` | Poste de régie au clavier (Entrée = GO, a = ARRÊT) |
| `tests/test_pont_scenique.py` | 7 tests, dont l'émission réelle d'OSC et d'un paquet sACN en boucle locale |

```bash
cd code
python -m pont_scenique.regie pont_scenique/conduite_exemple.yaml --a-blanc          # répétition à blanc
python -m pont_scenique.regie ma_conduite.yaml --qlab 192.168.1.10 --sacn-unicast 192.168.1.50 --cible sim
```

**Règles.** Le GO vaut confirmation de l'opérateur pour un geste seulement si son statut autorise la cible
(robot : `valide_sim` au minimum, à vitesse réduite). L'ARRÊT logiciel annule les actions différées, envoie
`/panic` à QLab, fige la lumière sans noir brutal et suspend les gestes ; il ne remplace pas l'arrêt
d'urgence matériel du robot (plan P2.1, §6.2).

---

# P2.4 — Séquences gestuelles (ajout du 6 octobre 2026, gestes_scene 1.1.0)

Une **séquence** enchaîne des gestes de la bibliothèque fermée, avec des pauses ; elle ne crée aucun mouvement.
Quand l'enchaînement direct dépasserait une limite (par exemple regarder côté cour puis côté jardin : environ
150°/s), le séquenceur insère une **transition vers le neutre** de durée minimale sûre (vitesses limites − 10 %).
Le statut effectif d'une séquence est le plus bas de ceux de ses gestes : tant qu'un geste est en `brouillon`,
la séquence est refusée sur le robot.

| Chemin | Rôle |
|---|---|
| `gestes_scene/sequenceur.py` | Composition, liaisons (auto, directe, neutre), étirement ≥ 1, statut effectif |
| `gestes_scene/sequences.yaml` | 4 séquences : eveil, cour_jardin, surprise_joie, fin_de_scene |
| `tests/test_sequences.py` | 6 tests (transitions, refus, statut, exécuteur, outil IA) |
| `simulation_MuJoCo/jumeau.py --sequences` | Validation dans le jumeau ; `rapports/rapport_validation_sequences.json`, planches `seq_*.png` |

```bash
cd code && python -m gestes_scene.cli sequences            # plan minuté
python -m pytest tests                                     # 21 tests
cd ../simulation_MuJoCo && python jumeau.py --sequences    # validation en simulation
```

Les séquences s'emploient dans une conduite du pont scénique comme un geste : `{geste: fin_de_scene}`.
