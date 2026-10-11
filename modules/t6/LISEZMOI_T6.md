# T.6 — Outils de transcription et de pseudonymisation (v1.0, 5 octobre 2026)

| Fichier | Rôle |
|---|---|
| `pseudonymiser.py` | Masque courriels, téléphones et codes postaux ; remplace les formes de la table par `[pseudonyme]` ; rapport d'alertes |
| `test_pseudonymiser.py` | 4 tests, données fictives |
| `MODELE_transcription.txt` | En-tête et conventions de transcription |
| `table_pseudonymes.EXEMPLE.csv` | Format de la table, **fictif** ; la vraie table (DO-09) reste dans le volume chiffré |

```bash
python3 pseudonymiser.py "/Volumes/<chiffré>/brut/E-A07-01.txt" \
  --table "/Volumes/<chiffré>/DO-09_table_pseudonymes.csv" \
  --sortie "../Entretiens_pseudonymises/E-A07-01.txt" \
  --rapport "/Volumes/<chiffré>/controles/E-A07-01_controle.txt"
python3 -m pytest test_pseudonymiser.py
```

Règles : la transcription brute, la table et le rapport de contrôle (qui cite des passages bruts) restent dans le
volume chiffré ; seule la sortie, après examen de chaque alerte, entre dans `Entretiens_pseudonymises`.

## Ajout du 6 octobre 2026 — choix du modèle Whisper (SI-03)

| Fichier | Rôle |
|---|---|
| `comparer_transcriptions.py` | Taux d'erreur sur les mots (WER) de chaque transcription par rapport à une référence établie à l'écoute |
| `test_comparer_transcriptions.py` | 2 tests |

Sur deux ou trois enregistrements **fictifs** lus par le chercheur (jamais de personne participante) :
`python3 comparer_transcriptions.py reference.txt large-v3.txt large-v3-turbo.txt`. Règle : large-v3-turbo si son
WER ne dépasse pas celui de large-v3 de plus de 2 points ; sinon large-v3. Vérifier l'empreinte SHA du modèle
téléchargé (fiche SI-03, G.5) et inscrire modèle et version de whisper.cpp au registre G.5.
