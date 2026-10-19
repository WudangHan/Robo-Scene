"""Table de couverture du cahier des fonctions v1.0 (11 oct. 2026) par la plateforme.

Chaque fonction du cahier y est rattachée au code qui la réalise, au test qui la vérifie et à ce qui reste à faire.
États : « réalisé » (critère d'acceptation vérifié par un test automatisé), « réalisé, à éprouver » (code et tests
présents, critère qui exige une séance réelle, du matériel ou des personnes), « conditionné » (fonction livrée mais
verrouillée par une condition de gouvernance), « hors logiciel » (relève d'un document ou d'une décision).
"""
from __future__ import annotations

from typing import Any

R, E, C, H = "réalisé", "réalisé, à éprouver", "conditionné", "hors logiciel"

FONCTIONS: list[dict[str, Any]] = [
    # 3.1 Noyau de traçabilité
    {"id": "N-01", "etat": R, "code": "bridge/trace/journal.py", "test": "tests/test_trace.py", "reste": ""},
    {"id": "N-02", "etat": R, "code": "bridge/trace/schema_evenement_v1.json", "test": "tests/test_trace.py", "reste": ""},
    {"id": "N-03", "etat": R, "code": "bridge/trace/journal.py (DepotCorpus)", "test": "tests/test_trace.py", "reste": ""},
    {"id": "N-04", "etat": R, "code": "bridge/trace/ecart.py", "test": "tests/test_trace.py", "reste": ""},
    {"id": "N-05", "etat": R, "code": "bridge/scene, modules/p2/pont_scenique/conduite.py", "test": "tests/test_plateforme.py",
     "reste": ""},
    {"id": "N-06", "etat": R, "code": "bridge/trace/provenance.py", "test": "tests/test_trace.py", "reste": ""},
    {"id": "N-07", "etat": E, "code": "bridge/trace/saisies.py ; console « de tête »", "test": "tests/test_trace.py",
     "reste": "Chronométrer la saisie (< 30 s) en répétition réelle"},
    {"id": "N-08", "etat": E, "code": "bridge/trace/saisies.py (revue_autres, consigner_revue)", "test": "tests/test_trace.py",
     "reste": "Revue après le premier atelier (P1.4)"},
    # 3.2 Atelier
    {"id": "A-01", "etat": E, "code": "bridge/atelier, bridge/modeles", "test": "tests/test_plateforme.py",
     "reste": "Premier appel réel après l'avis éthique (clés API)"},
    {"id": "A-02", "etat": R, "code": "modules/p1/atelier_p1/routeur.py ; bridge/modeles", "test": "tests/test_modeles.py", "reste": ""},
    {"id": "A-03", "etat": R, "code": "modules/p1/atelier_p1/atelier.py", "test": "modules/p1/tests", "reste": ""},
    {"id": "A-04", "etat": R, "code": "modules/p1 (éditeur) ; bridge/trace/ecart.py", "test": "modules/p1/tests", "reste": ""},
    {"id": "A-05", "etat": C, "code": "bridge/atelier (G-02, G-04, SI-02 désigné)", "test": "tests/test_plateforme.py",
     "reste": "Cocher les six critères de mise en service"},
    {"id": "A-06", "etat": H, "code": "modules/p1/corpus", "test": "", "reste": "Vérification mot à mot des extraits d'Amphitryon"},
    {"id": "A-07", "etat": R, "code": "modules/p1/atelier_p1/grille_biais.py", "test": "modules/p1/tests", "reste": ""},
    {"id": "A-08", "etat": R, "code": "bridge/modeles/clients.py", "test": "tests/test_modeles.py", "reste": ""},
    # 3.3 Scène
    {"id": "R-01", "etat": R, "code": "bridge/robots/bibliotheque.py ; bridge/ia.py", "test": "tests/test_robots.py", "reste": ""},
    {"id": "R-02", "etat": E, "code": "bridge/robots/bibliotheque.py (statuts) ; jumeau MuJoCo", "test": "tests/test_robots.py",
     "reste": "Modèle de simulation de l'AiNex"},
    {"id": "R-03", "etat": E, "code": "bridge/securite.py", "test": "tests/test_console.py", "reste": "Essais matériels consignés"},
    {"id": "R-04", "etat": E, "code": "bridge/serveur.py (observateur, zone 1,2 m)", "test": "tests/test_robots.py",
     "reste": "Observateur rémunéré présent"},
    {"id": "R-05", "etat": E, "code": "bridge/scene", "test": "tests/test_plateforme.py", "reste": "Conduite d'essai en salle"},
    {"id": "R-06", "etat": R, "code": "bridge/plateforme.py (écho)", "test": "tests/test_plateforme.py", "reste": ""},
    {"id": "R-07", "etat": E, "code": "bridge/robots/pilotes ; robots/*.toml ; sdk/", "test": "tests/test_robots.py",
     "reste": "Validation sur chaque plateforme matérielle"},
    {"id": "R-08", "etat": R, "code": "bridge/gouvernance/incidents.py", "test": "tests/test_robots.py", "reste": ""},
    # 3.4 Spectateur
    {"id": "S-01", "etat": R, "code": "modules/p3/p3_spectateur", "test": "modules/p3/tests", "reste": ""},
    {"id": "S-02", "etat": R, "code": "modules/p3/p3_spectateur/agregat.py", "test": "modules/p3/tests", "reste": ""},
    {"id": "S-03", "etat": E, "code": "modules/p3/outils/audit_wcag.py", "test": "modules/p3/tests", "reste": "Tests P3.3 avec des usagers"},
    {"id": "S-04", "etat": R, "code": "bridge/spectateur (tirage scellé, condition)", "test": "tests/test_spectateur.py", "reste": ""},
    {"id": "S-05", "etat": C, "code": "bridge/spectateur/questionnaire.py ; questionnaires/*.yaml", "test": "tests/test_spectateur.py",
     "reste": "Saisir NE, Godspeed, CSI et le feuillet ; avis éthique ; EFVP"},
    {"id": "S-06", "etat": R, "code": "bridge/spectateur (avis_transparence)", "test": "tests/test_spectateur.py", "reste": ""},
    # 3.5 Analyse
    {"id": "Q-01", "etat": R, "code": "bridge/analyse/operatoire.py", "test": "tests/test_analyse.py", "reste": ""},
    {"id": "Q-02", "etat": R, "code": "bridge/analyse/triangulation.py", "test": "tests/test_analyse.py", "reste": ""},
    {"id": "Q-03", "etat": E, "code": "bridge/analyse/statistiques.py ; A2_analyse_principale.R", "test": "tests/test_analyse.py",
     "reste": "Exécuter le script R (lme4, pbkrtest, ordinal) sur les données X.2"},
    {"id": "Q-04", "etat": R, "code": "bridge/analyse/__init__.py (manifeste)", "test": "tests/test_analyse.py", "reste": ""},
    {"id": "Q-05", "etat": R, "code": "bridge/analyse/entretiens.py", "test": "tests/test_analyse.py", "reste": ""},
    # 3.6 Gouvernance
    {"id": "G-01", "etat": R, "code": "bridge/gouvernance/retrait.py ; partenaire/stockage.py", "test": "tests/test_trace.py", "reste": ""},
    {"id": "G-02", "etat": R, "code": "bridge/gouvernance (exiger_avis_ethique)", "test": "tests/test_spectateur.py", "reste": ""},
    {"id": "G-03", "etat": R, "code": "gouvernance/registre_systemes.yaml ; synchroniser_registre", "test": "tests/test_trace.py",
     "reste": ""},
    {"id": "G-04", "etat": C, "code": "gouvernance/efvp.yaml ; exiger_efvp", "test": "tests/test_spectateur.py",
     "reste": "Réviser l'EFVP : P1_atelier 1.1, P3_questionnaires, entretiens, surtitres"},
    {"id": "G-05", "etat": R, "code": "bridge/gouvernance/decisions.py", "test": "tests/test_trace.py", "reste": ""},
    {"id": "G-06", "etat": R, "code": "bridge/gouvernance/biometrie.py ; op_mouvement", "test": "tests/test_plateforme.py", "reste": ""},
    {"id": "G-07", "etat": C, "code": "bridge/gouvernance/conservation.py", "test": "tests/test_trace.py",
     "reste": "Fixer les échéances (gouvernance/conservation.yaml)"},
    # 3.7 Pilotage
    {"id": "P-01", "etat": R, "code": "bridge/pilotage/regie.py", "test": "tests/test_plateforme.py", "reste": ""},
    {"id": "P-02", "etat": E, "code": "bridge/pilotage/rapports.py (inventaire mensuel)", "test": "tests/test_plateforme.py",
     "reste": "Configurer [pilotage] dossier_projet"},
    {"id": "P-03", "etat": R, "code": "bridge/pilotage/depots.py", "test": "tests/test_spectateur.py", "reste": ""},
    {"id": "P-04", "etat": R, "code": "bridge/pilotage/rapports.py (revue trimestrielle)", "test": "tests/test_plateforme.py", "reste": ""},
    # 4. Extensions
    {"id": "O-01", "etat": E, "code": "bridge/partenaire (répétiteur) ; consigne_graduee.py", "test": "tests/test_extensions.py",
     "reste": "Consentement à la captation vocale ; traitement local"},
    {"id": "O-02", "etat": C, "code": "bridge/partenaire/variations.py ; bridge/analyse/juges.py", "test": "tests/test_analyse.py",
     "reste": "Étude de juges avant tout usage analytique"},
    {"id": "O-03", "etat": R, "code": "bridge/partenaire (DraCor, TEI, dramaturgie) ; tei_export.py", "test": "tests/test_extensions.py",
     "reste": "Encoder des pièces franco-canadiennes"},
    {"id": "O-04", "etat": C, "code": "bridge/partenaire/analyse_jeu.py ; gouvernance/biometrie.py", "test": "tests/test_extensions.py",
     "reste": "EFVP, consentement exprès, revue de conception"},
    {"id": "O-05", "etat": R, "code": "bridge/scene (apercu, simuler)", "test": "tests/test_plateforme.py",
     "reste": "Installer le SDK Reachy Mini pour le jumeau complet"},
    {"id": "O-06", "etat": R, "code": "bridge/accessibilite", "test": "tests/test_extensions.py", "reste": ""},
    {"id": "O-07", "etat": E, "code": "bridge/diffusion/c2pa.py", "test": "tests/test_extensions.py",
     "reste": "Certificat de signature et c2patool"},
    {"id": "O-08", "etat": R, "code": "bridge/veille", "test": "tests/test_extensions.py", "reste": ""},
    {"id": "O-09", "etat": R, "code": "bridge/diffusion/tableau_public.py ; web/tableau-public.html", "test": "tests/test_extensions.py",
     "reste": ""},
    {"id": "O-10", "etat": R, "code": "bridge/partenaire (mode pédagogique, livret)", "test": "tests/test_extensions.py", "reste": ""},
    {"id": "O-11", "etat": E, "code": "conduite multi-robots (champ robot)", "test": "tests/test_plateforme.py",
     "reste": "Nouvelle analyse de risques avant usage"},
    {"id": "O-12", "etat": R, "code": "conduite (divulgation voix_synthese) ; web", "test": "tests/test_plateforme.py", "reste": ""},
    # Extension ajoutée le 19 oct. 2026 (hors cahier v1.0) : drone de scène, virtuel puis réel
    {"id": "O-13", "etat": E, "code": "web/drone ; bridge/drone ; web/drone/salle.json", "test": "tests/test_drone.py",
     "reste": "Relevé de la salle (salle.json), autorisation du lieu et assurance, analyse de risques ; premier vol réel "
              "consigné avec observateur ; signes du Tello et cap MAVLink vérifiés au banc"},
]


def table() -> dict[str, Any]:
    from collections import Counter
    return {"fonctions": FONCTIONS, "bilan": dict(Counter(f["etat"] for f in FONCTIONS)), "total": len(FONCTIONS)}
