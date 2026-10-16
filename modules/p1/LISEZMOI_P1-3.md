# P1.3 — Atelier dramaturgique, version alpha (système SI-04)

Projet « L'IA au service de la création théâtrale » — Sylvain Gagné, Ph. D. — version 0.1.0-alpha, 5 octobre 2026.

## Principe

Application locale (servie sur `127.0.0.1` seulement) qui met en œuvre les **cinq opérations** du cadre R.4 :
l'artiste formule une **consigne** ; le système **génère** de une à cinq propositions ; l'artiste les **retient**,
les **rejette** ou les **redemande** ; il **transforme** la proposition retenue dans un éditeur (l'écart est calculé) ;
il **attribue** chaque segment du texte final (humaine, système, mixte). Tout est consigné dans le journal I-5.

Le **routeur de sensibilité** (D03) n'envoie au modèle distant (SI-01, Claude par l'API d'Anthropic) qu'une
consigne exempte de tout motif de sensibilité ; sinon, la consigne va au modèle local (SI-02, servi par Ollama).
Si le modèle local est indisponible, la génération est **refusée** : aucun repli sur le distant.

## Contenu

| Chemin | Rôle |
|---|---|
| `atelier_p1/atelier.py` | Séance, cinq opérations, journal JSONL, indicateurs I-5, exports JSON et CSV (registre P1-2), mise en service |
| `atelier_p1/routeur.py` | Motifs de sensibilité : liste de blocage, courriel, téléphone, confidentialité, extrait « local seulement », mode hors ligne |
| `atelier_p1/modeles.py` | Clients SI-01 (API Messages), SI-02 (Ollama), générateur simulé ; consigne système anti-stéréotypes |
| `atelier_p1/ecart.py` | Distance de Levenshtein normalisée ; étiquette suggérée |
| `atelier_p1/corpus.py` | Chargement du corpus et contrôle d'admission (catégories P1.2) |
| `atelier_p1/serveur.py` + `static/atelier.html` | Interface d'atelier (FR) et ligne de commande |
| `corpus/` | `corpus.yaml` et deux extraits du domaine public (Molière, *Amphitryon*) |
| `config/mise_en_service.yaml` | Six critères de la fiche P1.1, §7 (tous à `false`) |
| `config/liste_blocage.EXEMPLE.txt` | Exemple fictif ; la vraie liste reste dans le volume chiffré |
| `FICHE_MODELES.md`, `FICHE_CORPUS.md` | Fiches descriptives exigées par ENF-06 |
| `tests/test_atelier_p1.py` | 15 tests |

## Installation (macOS)

```bash
cd "05_Prototypes/P1_Atelier_dramaturgique/code"
python3 -m venv ~/venv-p1 && source ~/venv-p1/bin/activate
pip install -r requirements.txt
python -m pytest tests                                          # 15 tests, sans réseau

# 1) essai sans réseau (générateur simulé)
python -m atelier_p1.serveur --seance ESSAI01 --pseudonymes T1 T2 --simule

# 2) essai avec les vrais modèles, sans personne participante
export ANTHROPIC_API_KEY=…                                      # SI-01
# SI-02 : LM Studio (défaut) — modèle téléchargé dans LM Studio, serveur local démarré (lms server start)
export ATELIER_MODELE_LOCAL=luciole-8b-instruct-1.1            # identifiant affiché par « lms ls »
# variante Ollama : export ATELIER_API_LOCALE=ollama ; ollama pull <étiquette> ; ATELIER_MODELE_LOCAL=<étiquette>
python -m atelier_p1.serveur --seance ESSAI02 --pseudonymes T1

# 3) atelier réel : refusé tant que config/mise_en_service.yaml n'est pas rempli
python -m atelier_p1.serveur --seance S01 --pseudonymes A01 A02 A03 --mode atelier \
  --liste-blocage "/Volumes/<volume chiffré>/liste_blocage.txt" --journal "/Volumes/<volume chiffré>/journaux"
```

## Règles

- **Jamais de nom réel** dans une consigne ni dans le dossier du projet ; pseudonymes seulement (G.6).
- La liste de blocage et le journal I-5 (qui contient les consignes et les textes) vont dans le **volume chiffré**.
- Le générateur simulé est interdit en mode `atelier`.
- Plafond de jetons par séance pour le modèle distant (`--plafond-jetons`, ENF-04).

## Limites de l'alpha

- Clients API vérifiés contre des serveurs factices reproduisant les formats documentés ; **aucun appel réel** n'a
  encore été fait (pas de clé dans l'environnement de développement). Premier essai réel : à consigner.
- Modèle local SI-02 non choisi (critère 4 de mise en service).
- Interface en français seulement (ENF-02 exige FR/EN : version anglaise à l'étape bêta).
- Extraits du corpus à collationner avec la source avant le premier atelier.

## Ajout du 5 octobre 2026 — grille de relecture des biais (critère 5 de mise en service)

| Chemin | Rôle |
|---|---|
| `atelier_p1/grille_biais.py` | Génère le lot d'essai de 50 propositions ; calcule l'alpha de Krippendorff (nominal, ordinal, intervalle) |
| `tests/test_grille_biais.py` | 3 tests (valeurs de référence vérifiées contre le paquet indépendant `krippendorff`) |
| `../specifications/P1-GB_Grille_biais_narratifs_v1.0.xlsx` | Dimensions B1–B8, consignes d'essai, cotation, recotation, synthèse |

```bash
python -m atelier_p1.grille_biais generer ../specifications/P1-GB_Grille_biais_narratifs_v1.0.xlsx essai_grille.xlsx
python -m atelier_p1.grille_biais fiabilite essai_grille.xlsx
```

Le fichier `essai_grille.xlsx` contient des propositions générées : le conserver dans le volume chiffré ou dans
`specifications/` (aucune donnée personnelle), jamais avec des données de personnes participantes.

## Ajout du 6 octobre 2026 — version 0.1.1-alpha : contrôle « traitement local » et choix de SI-02

| Chemin | Rôle |
|---|---|
| `atelier_p1/modeles.py` | `verifier_local()` : SI-02 refuse un serveur de modèles non local (autre que 127.0.0.1, localhost, ::1) et tout modèle exécuté ailleurs (étiquette `cloud` ou `remote`, entrée annoncée comme distante par `/api/tags` d'Ollama ou par le champ `device` de LM Studio) ; `chat_local()` parle à LM Studio (`/v1/chat/completions`, sortie `json_schema`) ou à Ollama (`/api/chat`) |
| `atelier_p1/evaluation_si02.py` | Évaluation à l'aveugle des candidats : 12 consignes fictives × 3 propositions, codes M1…Mn, clé séparée, mesures automatiques, dépouillement |
| `config/candidats_si02.yaml` | Quatre candidats révisés le 2026-10-12 (Apertus-8B-2509, EuroLLM-9B-2512, Luciole-8B 1.1, témoin Mistral-Small-3.2-24B) ; étiquettes Ollama et provenance des GGUF renseignées |
| `tests/test_evaluation_si02.py` | 3 tests (contrôle local, modèle annoncé distant, génération aveugle et dépouillement) |

```bash
# ne PAS se connecter à un compte ollama.com sur l'ordinateur de recherche (les modèles -cloud l'exigent)
ollama pull hf.co/<dépôt GGUF du candidat>:Q4_K_M          # pour chaque candidat de config/candidats_si02.yaml
python -m atelier_p1.evaluation_si02 generer --api lmstudio --modeles <id. A> <id. B> <id. C> <id. T> \
  --sortie eval_si02.xlsx --cle "/Volumes/<volume chiffré>/cle_si02.json"
# coter eval_si02.xlsx sans ouvrir la clé, puis :
python -m atelier_p1.evaluation_si02 depouiller eval_si02.xlsx --cle "/Volumes/<volume chiffré>/cle_si02.json"
```

Règle de choix : fiche SI-02 (02_Gouvernance_ethique_conformite/ISO42001_politique_et_registre_IA). Le choix,
la quantification et l'empreinte du fichier GGUF sont inscrits au registre G.5 et dans `FICHE_MODELES.md`.
Tests : 20 réussis, 1 sauté (dépendance facultative `krippendorff`).
