"""Clôture a posteriori d'une séance de la console restée ouverte (« fin » vide), avec vérification et scellement.

    python outils/cloture_seance.py corpus/ESP32/S04/20261010/20261010_ESP32_S04_001.json [...]            # examen
    python outils/cloture_seance.py <fichiers .json> --appliquer --operateur OP01 [--motif "..."]            # clôture

Cas visé : le pont a été arrêté sans que Journal.cloturer() s'exécute (registre d'actions, B-010 ; ISO/IEC 42001,
A.6.2.8, journaux d'événements). La clôture reprend le format de Journal.cloturer() (bridge/journal.py) :
« fin » renseignée et événement {"cat": "seance", "action": "cloture"} ajouté au .jsonl, avec trois différences
déclarées : la fin retenue est l'horodatage de la DERNIÈRE ENTRÉE (fin effective de l'enregistrement), l'événement
porte « a_posteriori » et l'empreinte du journal brut avant ajout, et rien d'autre n'est réécrit.

Vérifications : identifiant [DATE]_[SYSTÈME]_[TYPE]_[NUMÉRO] cohérent avec le nom de fichier, clés requises, chaque
ligne du .jsonl en JSON valide avec « ts » et « cat », horodatages croissants, événement d'ouverture conforme,
absence de clôture antérieure. Les compteurs du .json sont recalculés depuis le .jsonl ; les écarts sont consignés,
jamais corrigés en silence (les valeurs d'origine restent en place). Les notes observationnelles ne sont jamais
complétées par l'outil : elles relèvent du chercheur (procès-verbal de clôture).

Produits : <id>.json mis à jour, <id>.jsonl prolongé d'une ligne, <id>.json.avant_cloture (copie intacte),
<id>.sceau.json (empreintes SHA-256 finales) et SHA256SUMS du dossier.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

RE_ID = re.compile(r"^(\d{8})_([A-Za-z0-9-]+)_([A-Za-z0-9-]+)_(\d{3})$")
CLES = ("identifiant", "systeme", "type", "debut", "fin", "parametres", "compteurs", "notes_observationnelles")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def recompter(evenements: list[dict]) -> dict[str, int]:
    """Compteurs de la console reconstitués depuis le journal brut (mêmes clés que Journal.meta["compteurs"])."""
    c = dict.fromkeys(("commandes", "commandes_refusees", "arrets_urgence", "propositions_ia", "ia_validees",
                       "ia_rejetees", "ia_bloquees_seuil", "sequences_jouees"), 0)
    for e in evenements:
        cat, act = e.get("cat"), e.get("action") or e.get("statut")
        if cat == "cmd":
            c["commandes"] += 1
        elif cat == "refus":
            c["commandes_refusees"] += 1
        elif cat == "journal" and "ARRÊT D'URGENCE" in str(e.get("msg", "")):
            c["arrets_urgence"] += 1
        elif cat == "sequence" and act == "debut":
            c["sequences_jouees"] += 1
        elif cat == "ia":
            if act in ("proposition", None):
                c["propositions_ia"] += 1
            for k, cle in (("validee", "ia_validees"), ("rejetee", "ia_rejetees"), ("bloquee", "ia_bloquees_seuil")):
                if act == k:
                    c[cle] += 1
    return c


def examiner(chemin_meta: Path) -> dict:
    meta = json.loads(chemin_meta.read_text(encoding="utf-8"))
    jsonl = chemin_meta.with_suffix(".jsonl")
    pb, av = [], []
    manquantes = [k for k in CLES if k not in meta]
    if manquantes:
        pb.append(f"clés absentes : {', '.join(manquantes)}")
    sid = meta.get("identifiant", "")
    m = RE_ID.match(sid)
    if not m:
        pb.append(f"identifiant non conforme : {sid!r}")
    elif sid != chemin_meta.stem or m.group(2) != meta.get("systeme") or m.group(3) != meta.get("type"):
        pb.append("identifiant, nom de fichier, système ou type incohérents")
    if not jsonl.exists():
        return {"meta": meta, "problemes": pb + ["journal .jsonl absent"], "avertissements": av}
    evts, invalides = [], 0
    for n, ligne in enumerate(jsonl.read_text(encoding="utf-8").splitlines(), 1):
        try:
            e = json.loads(ligne)
            assert "ts" in e and "cat" in e
            evts.append(e)
        except Exception:
            invalides += 1
    if invalides:
        pb.append(f"{invalides} ligne(s) illisible(s) dans le .jsonl")
    ts = [e["ts"] for e in evts]
    if ts != sorted(ts):
        pb.append("horodatages non croissants")
    if not evts or evts[0].get("cat") != "seance" or evts[0].get("action") != "ouverture" \
            or evts[0].get("identifiant") != sid:
        pb.append("événement d'ouverture absent ou non conforme")
    if any(e.get("cat") == "seance" and e.get("action") == "cloture" for e in evts) or meta.get("fin"):
        av.append("séance déjà close : aucune modification")
    if ts and meta.get("debut") and ts[0] < meta["debut"][:23]:
        av.append("première entrée antérieure au début déclaré")
    recalc = recompter(evts)
    ecarts = {k: {"declare": meta.get("compteurs", {}).get(k, 0), "journal": v}
              for k, v in recalc.items() if meta.get("compteurs", {}).get(k, 0) != v}
    if ecarts:
        av.append("compteurs du .json non à jour (écarts consignés, valeurs d'origine conservées)")
    return {"meta": meta, "jsonl": jsonl, "evenements": len(evts), "premiere": ts[0] if ts else None,
            "derniere": ts[-1] if ts else None, "recalcules": recalc, "ecarts": ecarts,
            "notes": len(meta.get("notes_observationnelles") or []), "problemes": pb, "avertissements": av}


def clore(chemin_meta: Path, r: dict, operateur: str, motif: str) -> dict:
    meta, jsonl = r["meta"], r["jsonl"]
    quand = maintenant()
    avant_jsonl, avant_meta = sha256(jsonl), sha256(chemin_meta)
    shutil.copy2(chemin_meta, chemin_meta.with_name(chemin_meta.name + ".avant_cloture"))
    evt = {"ts": quand, "cat": "seance", "action": "cloture", "a_posteriori": True, "fin_effective": r["derniere"],
           "sha256_journal_avant_cloture": avant_jsonl, "operateur": operateur}
    with open(jsonl, "a", encoding="utf-8") as f:
        f.write(json.dumps(evt, ensure_ascii=False) + "\n")
    meta["fin"] = r["derniere"]
    meta["cloture"] = {
        "mode": "a_posteriori", "date": quand, "operateur": operateur, "motif": motif,
        "fin_retenue": "horodatage de la dernière entrée du journal (fin effective de l'enregistrement)",
        "lignes_journal_avant_cloture": r["evenements"], "sha256_journal_avant_cloture": avant_jsonl,
        "sha256_meta_avant_cloture": avant_meta, "compteurs_recalcules_depuis_journal": r["recalcules"],
        "ecarts_compteurs": r["ecarts"],
        "notes_observationnelles": "aucune note consignée pendant la séance ; compléments éventuels au procès-verbal",
        "outil": "outils/cloture_seance.py", "reference": "registre des actions B-010 ; ISO/IEC 42001, A.6.2.8",
        "validation_chercheur": "en attente (procès-verbal de clôture à signer)",
    }
    chemin_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sceau = {"identifiant": meta["identifiant"], "date": quand, "algorithme": "SHA-256",
             "fichiers": {jsonl.name: sha256(jsonl), chemin_meta.name: sha256(chemin_meta),
                          chemin_meta.name + ".avant_cloture": avant_meta},
             "journal_avant_cloture": avant_jsonl}
    chemin_meta.with_suffix(".sceau.json").write_text(json.dumps(sceau, ensure_ascii=False, indent=2) + "\n",
                                                      encoding="utf-8")
    return sceau


def sommes(dossier: Path) -> None:
    lignes = [f"{sha256(p)}  {p.name}" for p in sorted(dossier.iterdir())
              if p.is_file() and p.name != "SHA256SUMS" and not p.name.startswith(".")]
    (dossier / "SHA256SUMS").write_text("\n".join(lignes) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Clôture a posteriori et scellement d'une séance de la console")
    ap.add_argument("meta", nargs="+", type=Path, help="fichiers <identifiant>.json de séance")
    ap.add_argument("--appliquer", action="store_true", help="clore et sceller (sinon : examen seulement)")
    ap.add_argument("--operateur", default="OP01", help="pseudonyme de la personne qui clôt (jamais un nom)")
    ap.add_argument("--motif", default="séance non close par le pont (processus arrêté avant Journal.cloturer())")
    a = ap.parse_args(argv)
    code, rapport = 0, []
    for p in a.meta:
        r = examiner(p)
        ligne = {k: r.get(k) for k in ("evenements", "premiere", "derniere", "recalcules", "ecarts", "notes",
                                       "problemes", "avertissements")}
        ligne["identifiant"] = r["meta"].get("identifiant")
        if r["problemes"]:
            code = 1
        elif a.appliquer and not any("déjà close" in x for x in r["avertissements"]):
            ligne["sceau"] = clore(p, r, a.operateur, a.motif)
            sommes(p.parent)
        rapport.append(ligne)
    print(json.dumps(rapport, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
