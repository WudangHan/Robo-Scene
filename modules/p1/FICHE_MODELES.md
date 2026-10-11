# Fiche descriptive des modèles — SI-04, version alpha 0.1.1 (6 octobre 2026)

Gabarit inspiré des *model cards* (Mitchell et al., 2019), ramené à l'usage du projet (fiche P1.1, §6 ; ENF-06).

| Rubrique | SI-01 — modèle distant | SI-02 — modèle local |
|---|---|---|
| Identifiant | `claude-opus-5-5` (API Messages d'Anthropic, version d'API `2023-06-01`) | À choisir par l'évaluation à l'aveugle (`evaluation_si02.py`) parmi les candidats de `config/candidats_si02.yaml` ; servi par Ollama (`/api/chat`) sur 127.0.0.1, jamais une étiquette `-cloud` |
| Version consignée | Champ `model` de chaque réponse, inscrit au journal I-5 | Champ `model` de chaque réponse |
| Usage prévu | Propositions de répliques, situations, didascalies à partir de consignes **non sensibles** | Consignes sensibles ou confidentielles ; mode hors ligne |
| Hors périmètre | Données personnelles, textes inédits d'artistes (cat. E), évaluation de personnes | Évaluation de personnes ; publication automatique |
| Entraînement par le projet | Aucun (contexte seulement) | Aucun (contexte seulement) |
| Conservation des données chez le fournisseur | Selon la page de confidentialité consultée le 6 oct. 2026 : entrées et sorties de l'API supprimées dans les 30 jours, sauf exceptions (violation des politiques d'usage : jusqu'à 2 ans ; obligation légale) ; pas d'entraînement par défaut sur les données des produits commerciaux, sauf rétroaction volontaire. Fiche fournisseur F-01 (G.5 v1.1) | Sans objet (local), à condition que `verifier_local()` ne relève aucun motif |
| Limites connues | Biais narratifs documentés pour les grands modèles (Lucy et Bamman, 2021) ; reprise possible de formules convenues | Qualité en français à évaluer ; idem pour les biais |
| Mesures | Consigne système anti-stéréotypes ; relecture humaine ; grille de biais (critère 5) | Idem |
| Critères de choix de SI-02 | Licence permettant la recherche et la publication ; exécution sur le matériel du chercheur ; qualité en français ; documentation publique des données d'entraînement (fiche P1.1, §2.2) | |

Consigne système commune : voir `atelier_p1/modeles.py`, constante `SYSTEME`.
