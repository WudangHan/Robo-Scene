"""Régie locale (P-01) : lecture et mise à jour du registre du projet (data.json de l'application Régie
IA-Théâtre), et régisseur IA en lecture seule (SI-07).

Le registre est celui du dossier du projet (09_Application_Regie/source/data.json). Toute mise à jour est
précédée d'une copie datée et consignée ; la plateforme ne modifie que le statut, le livrable et la note
d'une tâche. (Inférence) L'application Régie publiée sur claude.ai garde sa propre base : la synchroniser après
une mise à jour locale, comme le prévoit déjà la procédure du projet (seed.py).
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

COLLECTIONS = ("taches", "jalons", "decisions", "risques", "conformite", "prototypes", "publications", "terrain")
STATUTS_TACHE = ("à faire", "en cours", "fait", "bloqué", "annulé")

SYSTEME_REGISSEUR = """Tu es le régisseur IA (système SI-07) du projet « L'IA au service de la création théâtrale ».
Tu réponds en français, à partir du SEUL registre fourni (tâches, jalons, décisions, risques, conformité).
Chaque affirmation se termine par l'identifiant de l'élément qui la fonde, entre crochets, par exemple [D08] ou [R02].
Tu ne modifies rien, tu ne recommandes aucune décision à la place du chercheur, tu n'inventes aucun identifiant.
Toute affirmation que le registre n'établit pas commence par « (Inférence) ».
Réponds UNIQUEMENT par un objet JSON : {"reponse": "…", "identifiants": ["…"]}"""


class Regie:
    def __init__(self, dossier_projet: str | Path | None, journal: Path):
        self.dossier = Path(dossier_projet) if dossier_projet else None
        self.journal = journal

    @property
    def fichier(self) -> Path | None:
        if not self.dossier:
            return None
        return self.dossier / "09_Application_Regie" / "source" / "data.json"

    def disponible(self) -> bool:
        return bool(self.fichier and self.fichier.exists())

    def lire(self) -> dict[str, Any]:
        if not self.disponible():
            return {"disponible": False, "motif": "Dossier du projet non configuré ([pilotage] dossier_projet) ou "
                                                  "data.json introuvable"}
        d = json.loads(self.fichier.read_text(encoding="utf-8"))
        return {"disponible": True, "chemin": str(self.fichier), **{k: d.get(k, []) for k in ("projet", *COLLECTIONS)}}

    def identifiants(self) -> set[str]:
        d = self.lire()
        return {x["id"] for k in COLLECTIONS for x in d.get(k, []) if isinstance(x, dict) and "id" in x}

    def mettre_a_jour_tache(self, tid: str, *, statut: str | None = None, livrable: str | None = None,
                            note: str | None = None, par: str = "") -> dict[str, Any]:
        if statut is not None and statut not in STATUTS_TACHE:
            raise ValueError(f"Statut : {', '.join(STATUTS_TACHE)}")
        if not par.strip():
            raise ValueError("Indiquer qui met à jour (initiales)")
        d = json.loads(self.fichier.read_text(encoding="utf-8"))
        t = next((x for x in d.get("taches", []) if x.get("id") == tid), None)
        if t is None:
            raise KeyError(tid)
        avant = {k: t.get(k) for k in ("statut", "livrable", "note")}
        copie = self.fichier.with_name(f"data.json.{datetime.now():%Y%m%d-%H%M%S}.bak")
        shutil.copy2(self.fichier, copie)
        for k, v in (("statut", statut), ("livrable", livrable), ("note", note)):
            if v is not None:
                t[k] = v
        self.fichier.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        with self.journal.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"date": datetime.now().astimezone().isoformat(timespec="seconds"), "tache": tid,
                                "avant": avant, "apres": {k: t.get(k) for k in avant}, "par": par,
                                "copie": copie.name}, ensure_ascii=False) + "\n")
        return t

    def contexte(self, limite: int = 60_000) -> str:
        d = self.lire()
        morceaux = []
        for k in COLLECTIONS:
            for x in d.get(k, []):
                if isinstance(x, dict):
                    morceaux.append(f"[{x.get('id')}] ({k}) " + json.dumps({a: b for a, b in x.items() if a != "id"},
                                                                          ensure_ascii=False))
        return "\n".join(morceaux)[:limite]

    async def demander(self, service, question: str) -> dict[str, Any]:
        """Régisseur IA en lecture seule : identifiants vérifiés, inconnus retirés."""
        if not self.disponible():
            return {"reponse": "Registre indisponible.", "mode": "aucun"}
        if service is None or not service.disponible("analyse"):
            mots = [m for m in re.findall(r"\w{4,}", question.lower())]
            lignes = [l for l in self.contexte().splitlines() if any(m in l.lower() for m in mots)][:8]
            return {"reponse": "Sans clé API : éléments du registre qui contiennent les mots de la question.",
                    "extraits": lignes, "mode": "extractif"}
        r = await service.generer("analyse", SYSTEME_REGISSEUR, f"Registre :\n{self.contexte()}\n\nQuestion : {question}",
                                  temperature=0.2, max_tokens=1200)
        m = re.search(r"\{.*\}", r.texte, re.S)
        d = json.loads(m.group(0)) if m else {"reponse": r.texte, "identifiants": []}
        connus = self.identifiants()
        texte = str(d.get("reponse", ""))
        cites = set(re.findall(r"\[([A-Z]{1,3}\d{1,3}(?:\.\d+)?)\]", texte)) | set(d.get("identifiants") or [])
        inconnus = sorted(c for c in cites if c not in connus)
        for c in inconnus:
            texte = texte.replace(f"[{c}]", "[identifiant retiré]")
        return {"reponse": texte, "identifiants": sorted(c for c in cites if c in connus),
                "identifiants_retires": inconnus, "mode": f"{r.fournisseur}:{r.modele_exact}", "systeme": "SI-07"}
