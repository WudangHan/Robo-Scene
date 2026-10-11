"""Rapports périodiques : inventaire mensuel du dossier (P-02) et revue trimestrielle de la politique d'IA
et audit interne (P-04, ISO/IEC 42001).

* L'inventaire réutilise l'outil du projet (09_Application_Regie/outils/inventaire_projet.py), qui produit
  00_Pilotage/Inventaires_mensuels/AAAA-MM-JJ_Inventaire_projet.docx ; la plateforme le lance le premier jour
  de chaque mois (ou au premier démarrage du mois) si le dossier du projet est configuré.
* La revue trimestrielle produit un rapport Markdown daté qui rassemble les éléments à examiner : versions des
  systèmes, adoptions de modèles, incidents, décisions concernant des personnes, écarts d'EFVP, échéances de
  conservation, verrous de gouvernance.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .. import _modules


def inventaire_du_mois_fait(dossier_projet: Path, aujourd_hui: date | None = None) -> bool:
    aujourd_hui = aujourd_hui or date.today()
    d = Path(dossier_projet) / "00_Pilotage" / "Inventaires_mensuels"
    return any(p.name.startswith(f"{aujourd_hui:%Y-%m}") for p in d.glob("*_Inventaire_projet.docx")) if d.exists() else False


def lancer_inventaire(dossier_projet: Path) -> dict[str, Any]:
    outil = _modules.CHEMINS["regie"] / "inventaire_projet.py"
    r = subprocess.run([sys.executable, str(outil), str(dossier_projet)], capture_output=True, text=True, timeout=600)
    return {"code": r.returncode, "resume": r.stdout[-4000:], "erreur": r.stderr[-1000:]}


def revue_trimestrielle(ctl, aujourd_hui: date | None = None) -> Path:
    aujourd_hui = aujourd_hui or date.today()
    g = ctl.gouv
    g.recharger()
    from ..gouvernance import conservation
    adoptions = ctl.service.catalogue.etat.get("historique", [])
    inc = g.incidents.lister()
    lignes = [
        f"# Revue trimestrielle de la politique d'IA et audit interne — {aujourd_hui:%Y-%m-%d}",
        "", "Référentiel : ISO/IEC 42001:2023 (système de management de l'IA) ; politique G.5 "
        f"v{(g.etat.get('politique_ia') or {}).get('version', '?')}.", "",
        "## 1. Systèmes d'IA et versions en service (G-03)", "",
        "| Système | Nom | Version courante | Risque |", "|---|---|---|---|",
        *[f"| {k} | {v.get('nom', '')} | {v.get('version_courante', '—')} | {v.get('risque', '')} |"
          for k, v in (g.registre.get("systemes") or {}).items()],
        "", "## 2. Adoptions de versions de modèles (D13)", "",
        *([f"- {a['date']} — {a['famille']} : {a['ancienne']} → {a['nouvelle']} (séance {a['seance']})" for a in adoptions]
          or ["- Aucune adoption depuis la mise en service de la veille."]),
        "", "## 3. Incidents (R-08)", "",
        f"- Fiches : {len(inc)} ; ouvertes : {sum(1 for i in inc if i['statut'] == 'ouvert')}.",
        *[f"- {i['id']} ({i['ouverture'][:10]}) — {i['motif']} — {i['statut']}"
          + (f", gravité {i['gravite']}" if i.get("gravite") else "") for i in inc[-20:]],
        "", "## 4. Décisions concernant des personnes en attente de validation humaine (G-05)", "",
        *([f"- {d['id']} — {d['objet']} ({d['date'][:10]})" for d in g.decisions.en_attente()] or ["- Aucune."]),
        "", "## 5. Couverture de l'EFVP (G-04)", "",
        *([f"- {k} : version {v['version']}, couverte {v['couverte'] or 'aucune'}" for k, v in g.efvp_ecarts().items()]
          or ["- Toutes les fonctions sont couvertes."]),
        "", "## 6. Conservation et destruction (G-07)", "",
        *[f"- {c['code']} {c['libelle']} : {c['statut']} ({c['fichiers']} fichier(s))"
          for c in conservation.etat(getattr(ctl, "racine", _modules.RACINE), Path(g.regles) / "conservation.yaml")],
        "", "## 7. Verrous de gouvernance", "",
        f"- Avis éthique : {'obtenu' if g.avis_ethique else 'NON obtenu — collecte auprès de personnes verrouillée'}.",
        f"- Assurance responsabilité civile : {'souscrite' if g.etat.get('assurance_responsabilite_civile') else 'non souscrite'}.",
        f"- Modèle local SI-02 : {'provisoire' if ctl.service.local_provisoire else 'désigné'} ({ctl.service.local.modele}).",
        "", "## 8. Points à décider par le chercheur", "",
        "- [ ] Clore les incidents ouverts (qualification sous 48 h).",
        "- [ ] Valider ou refuser les décisions en attente.",
        "- [ ] Réviser l'EFVP pour les fonctions non couvertes.",
        "- [ ] Fixer les échéances de conservation encore « à fixer ».",
        "- [ ] Dater la prochaine revue dans gouvernance/etat.yaml.", "",
        "*Rapport produit par la plateforme ; les cases à cocher relèvent du chercheur (aucune décision automatisée).*",
    ]
    d = ctl.donnees / "revues"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{aujourd_hui:%Y-%m-%d}_revue_trimestrielle_G5.md"
    f.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return f
