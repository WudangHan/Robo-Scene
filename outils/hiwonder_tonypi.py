"""Groupes d'actions Hiwonder (.d6a) ↔ séquences ROBO-SCÈNE pour le TonyPi Pro.

    # importer les gestes du robot (copie de /home/pi/TonyPi/ActionGroups) dans la bibliothèque fermée, statut brouillon
    python outils/hiwonder_tonypi.py importer --source ~/TonyPi/ActionGroups [--noms wave bow ...] [--remplacer]
    # exporter une séquence ROBO-SCÈNE vers le logiciel PC de Hiwonder (ou le dossier ActionGroups du robot)
    python outils/hiwonder_tonypi.py exporter "révérence" --vers ~/Bureau/reverence.d6a
    # enveloppe des positions employées par un dossier de groupes d'actions (bornes du profil)
    python outils/hiwonder_tonypi.py enveloppe --source ~/TonyPi/ActionGroups

Les séquences importées vont dans sequences/tonypi-pro/hw_<nom>.json — fichiers exclus du dépôt public par .gitignore,
car Hiwonder ne déclare aucune licence pour ses fichiers. Elles arrivent au statut « brouillon » : la règle de la
bibliothèque fermée s'applique (validation en simulation, puis sur le robot à vitesse réduite, par décision signée).
Les gestes de marche et d'équilibre restent à jouer en natif (page Console, « Gestes natifs ») : leur minutage exact
compte pour l'équilibre, et le pont ralentirait leurs images au-delà de sa vitesse plafond.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from bridge.robots import tonypi as T  # noqa: E402
from bridge.robots.description import charger  # noqa: E402

PROFIL = RACINE / "robots" / "tonypi_pro.toml"
SEQUENCES = RACINE / "sequences" / "tonypi-pro"


def importer(source: Path, noms: list[str] | None, remplacer: bool, profil: Path = PROFIL, dest: Path = SEQUENCES) -> list[str]:
    d = charger(profil)
    cible = dest
    cible.mkdir(parents=True, exist_ok=True)
    faits = []
    fichiers = [source / f"{n}.d6a" for n in noms] if noms else sorted(source.glob("*.d6a"))
    for f in fichiers:
        if not f.exists():
            print(f"absent : {f.name}", file=sys.stderr)
            continue
        nom = f"hw_{f.stem}"
        sortie = cible / f"{nom}.json"
        if sortie.exists() and not remplacer:
            continue
        seq = T.d6a_vers_sequence(T.lire_d6a(f), d.articulations, nom, source=f.name)
        libelle = d.libelles_gestes.get(f.stem)
        if libelle:
            seq["libelle"] = f"{libelle} (Hiwonder)"
        if f.stem in d.gestes_dynamiques:
            seq["origine"]["avertissement"] = "geste d'équilibre ou de marche : le jouer en natif sur le robot réel"
        sortie.write_text(json.dumps(seq, ensure_ascii=False, indent=1), encoding="utf-8")
        faits.append(nom)
    return faits


def exporter(nom: str, vers: Path, profil: Path = PROFIL, dest: Path = SEQUENCES) -> Path:
    d = charger(profil)
    candidats = [dest / f"{nom}.json"]
    f = next((c for c in candidats if c.exists()), None)
    if f is None:
        raise SystemExit(f"Séquence introuvable : {nom}")
    seq = json.loads(f.read_text(encoding="utf-8"))
    T.ecrire_d6a(vers, T.sequence_vers_d6a(seq, d.articulations))
    return vers


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("importer"); a.add_argument("--source", type=Path, required=True)
    a.add_argument("--noms", nargs="*"); a.add_argument("--remplacer", action="store_true")
    b = sp.add_parser("exporter"); b.add_argument("nom"); b.add_argument("--vers", type=Path, required=True)
    c = sp.add_parser("enveloppe"); c.add_argument("--source", type=Path, required=True)
    x = ap.parse_args(argv)
    if x.cmd == "importer":
        faits = importer(x.source.expanduser(), x.noms, x.remplacer)
        print(f"{len(faits)} séquence(s) importée(s) dans {SEQUENCES} (préfixe hw_, statut brouillon)")
    elif x.cmd == "exporter":
        print(f"Groupe d'actions écrit : {exporter(x.nom, x.vers.expanduser())}")
    else:
        for i, (lo, hi) in T.enveloppe(x.source.expanduser()).items():
            print(f"servo {i:2d} : {lo:4d} – {hi:4d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
