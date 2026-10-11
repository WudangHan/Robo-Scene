"""O-07 — Justificatifs de contenu C2PA pour les captations et images diffusées.

Le manifeste suit la forme documentée par la Content Authenticity Initiative pour les définitions de manifeste :
assertion « c2pa.actions.v2 », action « c2pa.created » et type de source numérique IPTC (digitalCapture pour une
captation, compositeWithTrainedAlgorithmicMedia pour un contenu comportant des éléments générés,
trainedAlgorithmicMedia pour un contenu entièrement généré) (Content Authenticity Initiative, « Writing assertions
and actions »). La spécification de référence est C2PA 2.2.

Deux modes :
* signé — si l'outil c2patool est installé et qu'un certificat est configuré ([diffusion] c2pa_certificat et
  c2pa_cle), la plateforme appelle `c2patool <entrée> -m <manifeste> -o <sortie>` (syntaxe tirée des connaissances
  d'entraînement, à vérifier dans la documentation de C2PA Tool avant la première diffusion) ;
* non signé — sinon, un fichier compagnon <fichier>.c2pa.json contient la définition du manifeste et
  l'empreinte SHA-256 du fichier : il documente la provenance mais n'a pas la valeur d'un justificatif signé, ce
  que le fichier déclare en toutes lettres.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

IPTC = "http://cv.iptc.org/newscodes/digitalsourcetype/"
SOURCES = {"captation": "digitalCapture", "mixte": "compositeWithTrainedAlgorithmicMedia",
           "genere": "trainedAlgorithmicMedia"}


def definition(fichier: Path, *, nature: str, titre: str, auteurs: list[str], description_ia: str | None,
               logiciel: str = "ROBO-SCÈNE") -> dict[str, Any]:
    if nature not in SOURCES:
        raise ValueError(f"Nature : {', '.join(SOURCES)}")
    if nature != "captation" and not (description_ia or "").strip():
        raise ValueError("Décrire la part générée (divulgation obligatoire, cahier §4 et O-12)")
    d = {
        "claim_generator_info": [{"name": logiciel}],
        "title": titre,
        "assertions": [
            {"label": "c2pa.actions.v2", "data": {"actions": [
                {"action": "c2pa.created", "digitalSourceType": IPTC + SOURCES[nature],
                 "softwareAgent": {"name": logiciel}}]}},
            {"label": "stds.schema-org.CreativeWork", "data": {
                "@context": "https://schema.org", "@type": "CreativeWork", "name": titre,
                "author": [{"@type": "Person", "name": a} for a in auteurs],
                **({"description": description_ia} if description_ia else {})}},
        ],
    }
    return d


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def produire(fichier: str | Path, *, nature: str, titre: str, auteurs: list[str], description_ia: str | None = None,
             certificat: str | None = None, cle: str | None = None, outil: str = "c2patool") -> dict[str, Any]:
    f = Path(fichier)
    if not f.is_file():
        raise FileNotFoundError(f)
    d = definition(f, nature=nature, titre=titre, auteurs=auteurs, description_ia=description_ia)
    exe = shutil.which(outil)
    if exe and certificat and cle and Path(certificat).exists() and Path(cle).exists():
        man = f.with_suffix(f.suffix + ".manifeste.json")
        man.write_text(json.dumps({**d, "alg": "es256", "sign_cert": certificat, "private_key": cle},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        sortie = f.with_name(f"{f.stem}_c2pa{f.suffix}")
        r = subprocess.run([exe, str(f), "-m", str(man), "-o", str(sortie), "-f"], capture_output=True, text=True,
                           timeout=300)
        man.unlink(missing_ok=True)                    # le chemin de la clé ne reste pas sur le disque
        if r.returncode == 0:
            return {"mode": "signe", "fichier": str(sortie), "sha256_source": _sha(f)}
        erreur = r.stderr[-500:]
    else:
        erreur = None
    compagnon = f.with_suffix(f.suffix + ".c2pa.json")
    compagnon.write_text(json.dumps({
        "avertissement": "Manifeste NON SIGNÉ : document de provenance, sans valeur de justificatif C2PA vérifiable.",
        "fichier": f.name, "sha256": _sha(f), "date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "definition": d, **({"erreur_signature": erreur} if erreur else {})}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return {"mode": "non_signe", "fichier": str(compagnon), "sha256_source": _sha(f), "erreur_signature": erreur}
