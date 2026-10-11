"""Droit de retrait global (G-01) : effacement de toutes les données d'une personne participante, dans
toute la plateforme, attesté sans conserver son pseudonyme.

Périmètre :
1. profil, consentements, passages de répétition et formation (partenaire) ;
2. journaux unifiés de cocréation : événements dont la personne est l'agent, et cycles qu'elle a ouverts ;
3. journaux I-5 de l'atelier P1 : mêmes règles ;
4. fichiers de génération des cycles concernés (corpus/[Système]/[Type]/[Date]) ;
5. historique Git du corpus : les fichiers retirés sont purgés de tout l'historique (git filter-branch,
   expiration du reflog, compactage), faute de quoi le texte resterait récupérable dans les commits.

Critère du cahier : retrait exécuté et attesté en moins de trente jours — ici, immédiatement.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def _reecrire_jsonl(p: Path, garder) -> int:
    lignes = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    gardees = [l for l in lignes if garder(json.loads(l))]
    if len(gardees) != len(lignes):
        p.write_text("".join(l + "\n" for l in gardees), encoding="utf-8")
    return len(lignes) - len(gardees)


def _git(racine: Path, *args: str) -> subprocess.CompletedProcess:
    import os
    return subprocess.run(["git", *args], cwd=racine, capture_output=True, text=True, timeout=300,
                          env={**os.environ, "FILTER_BRANCH_SQUELCH_WARNING": "1"})


def retirer(pseudonyme: str, *, racine_corpus: Path, dossiers_p1: list[Path], stockage=None,
            dossier_attestations: Path) -> dict[str, Any]:
    pseudonyme = pseudonyme.strip()
    if not pseudonyme:
        raise ValueError("Pseudonyme requis")
    bilan: dict[str, Any] = {"profil_partenaire": False, "evenements_traces": 0, "evenements_p1": 0,
                             "fichiers_generation": 0, "historique_git_purge": None}
    # 1. Partenaire
    if stockage is not None:
        try:
            aid = stockage.profil(pseudonyme)["id"]
        except KeyError:
            aid = None
        if aid:
            stockage.retirer(aid)
            bilan["profil_partenaire"] = True
    # 2 et 4. Journaux unifiés et fichiers de génération des cycles ouverts par la personne
    fichiers_a_purger: list[Path] = []
    for j in Path(racine_corpus).glob("traces/*/*.jsonl"):
        evs = [json.loads(l) for l in j.read_text(encoding="utf-8").splitlines() if l.strip()]
        cycles = {e["cycle"] for e in evs if e["operation"] == "consigne" and e["agent"]["id"] == pseudonyme and e.get("cycle")}
        for e in evs:
            if e["operation"] == "generation" and e.get("cycle") in cycles:
                for k in ("fichier_texte", "fichier_meta"):
                    if e["donnees"].get(k):
                        fichiers_a_purger.append(Path(racine_corpus) / e["donnees"][k])
        bilan["evenements_traces"] += _reecrire_jsonl(
            j, lambda e: e["agent"]["id"] != pseudonyme and e.get("cycle") not in cycles)
    # 3. Journaux I-5 du prototype P1
    for d in dossiers_p1:
        for j in Path(d).glob("*_journal_I-5.jsonl"):
            evs = [json.loads(l) for l in j.read_text(encoding="utf-8").splitlines() if l.strip()]
            cycles = {e.get("cycle") for e in evs if e.get("evenement") == "consigne" and e.get("pseudonyme") == pseudonyme}
            bilan["evenements_p1"] += _reecrire_jsonl(
                j, lambda e: e.get("pseudonyme") != pseudonyme and e.get("cycle") not in cycles)
    for f in fichiers_a_purger:
        if f.exists():
            f.unlink()
            bilan["fichiers_generation"] += 1
    # 5. Historique Git du corpus
    racine = Path(racine_corpus)
    if fichiers_a_purger and (racine / ".git").exists():
        rel = [str(f.resolve().relative_to(racine.resolve())) for f in fichiers_a_purger]
        _git(racine, "add", "-A")
        _git(racine, "commit", "-q", "-m", "Retrait d'une personne participante (G-01) : fichiers supprimés")
        r = _git(racine, "filter-branch", "-f", "--index-filter",
                 "git rm --cached --ignore-unmatch -q -- " + " ".join(f"'{x}'" for x in rel), "--", "--all")
        ok = r.returncode == 0
        if ok:
            for ref in _git(racine, "for-each-ref", "--format=%(refname)", "refs/original/").stdout.split():
                _git(racine, "update-ref", "-d", ref)
            _git(racine, "reflog", "expire", "--expire=now", "--all")
            _git(racine, "gc", "-q", "--prune=now")
            restants = _git(racine, "log", "--all", "--format=%H", "--", *rel).stdout.strip()
            ok = not restants
        bilan["historique_git_purge"] = ok
    # Attestation, sans le pseudonyme
    Path(dossier_attestations).mkdir(parents=True, exist_ok=True)
    empreinte = hashlib.sha256(pseudonyme.encode("utf-8")).hexdigest()[:12]
    now = datetime.now().astimezone()
    att = {"date_execution": now.isoformat(timespec="seconds"), "empreinte_participant": empreinte,
           "bilan": bilan, "delai": "immédiat (critère : moins de 30 jours)",
           "note": "Le pseudonyme n'est pas conservé ; l'empreinte permet seulement de confirmer, à la "
                   "demande de la personne, que son retrait a été exécuté."}
    f = Path(dossier_attestations) / f"RET-{now:%Y%m%d-%H%M%S}-{empreinte}.json"
    f.write_text(json.dumps(att, ensure_ascii=False, indent=2), encoding="utf-8")
    att["fichier"] = str(f)
    return att
