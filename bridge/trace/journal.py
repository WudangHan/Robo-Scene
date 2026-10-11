"""Journal unifié des cinq opérations (N-01 à N-03, N-07, N-08).

Un même journal reçoit les traces de l'atelier P1, de la scène robotique P2, de l'interface P3, du
partenaire et de la régie. Chaque ligne est validée par le schéma robo-scene/evenement/v1 avant
d'être écrite (N-02) ; un événement invalide n'est jamais écrit partiellement.

Chaque génération est en outre déposée selon le protocole de métadonnées (§6.2) :
    corpus/[Système]/[Type]/[Date]/[ID].txt   texte brut des propositions
    corpus/[Système]/[Type]/[Date]/[ID].json  métadonnées complètes
puis versionnée par un commit commenté dans le dépôt Git du corpus (N-03).
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA = json.loads((Path(__file__).with_name("schema_evenement_v1.json")).read_text(encoding="utf-8"))
VALIDATEUR = Draft202012Validator(SCHEMA)
OPERATIONS = ("consigne", "generation", "selection", "transformation", "attribution")


class EvenementInvalide(ValueError):
    """L'événement ne respecte pas le schéma v1 : il n'est pas écrit."""


def horodatage() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _segment(s: str, defaut: str) -> str:
    s = re.sub(r"[^A-Za-z0-9.-]", "-", str(s or "")).strip("-")
    return (s or defaut)[:40]


def identifiant_seance(dossier: Path, systeme: str, type_: str, date: str | None = None) -> str:
    """[DATE]_[SYSTÈME]_[TYPE]_[NUMÉRO], le numéro suivant ceux déjà présents pour ce jour."""
    date = date or datetime.now().strftime("%Y%m%d")
    sys_, typ = _segment(systeme, "SYS"), _segment(type_, "X")
    prefixe = f"{date}_{sys_}_{typ}_"
    deja = [int(m.group(1)) for p in Path(dossier).glob(f"{prefixe}*.jsonl")
            if (m := re.search(r"_(\d{3})\.jsonl$", p.name))]
    return f"{prefixe}{max(deja, default=0) + 1:03d}"


def valider(evenement: dict[str, Any]) -> list[str]:
    """Liste des violations du schéma (vide si l'événement est valide)."""
    return [f"{'/'.join(map(str, e.absolute_path)) or '(racine)'} : {e.message}"
            for e in sorted(VALIDATEUR.iter_errors(evenement), key=lambda e: list(e.absolute_path))]


class DepotCorpus:
    """Dépôt Git du corpus (protocole §6.2) : un commit commenté par génération."""

    def __init__(self, racine: Path, actif: bool = True):
        self.racine = Path(racine)
        self.racine.mkdir(parents=True, exist_ok=True)
        self.actif = actif
        self.erreur: str | None = None
        if actif and not (self.racine / ".git").exists():
            self._git("init", "-q")
            self._git("config", "user.name", "Robo-Scène (journal de corpus)")
            self._git("config", "user.email", "corpus@robo-scene.local")

    def _git(self, *args: str) -> str | None:
        try:
            r = subprocess.run(["git", *args], cwd=self.racine, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.erreur = f"git indisponible : {exc}"
            return None
        if r.returncode != 0:
            self.erreur = (r.stderr or r.stdout).strip()[:300]
            return None
        return r.stdout.strip()

    def deposer(self, chemins: list[Path], message: str) -> str | None:
        """Ajoute les fichiers et crée un commit ; renvoie l'empreinte du commit ou None (motif dans self.erreur)."""
        if not self.actif:
            self.erreur = "versionnement désactivé dans la configuration"
            return None
        rel = [str(Path(c).resolve().relative_to(self.racine.resolve())) for c in chemins]
        if self._git("add", "--", *rel) is None:
            return None
        if self._git("commit", "-q", "-m", message) is None:
            return None
        return self._git("rev-parse", "HEAD")


class JournalCocreation:
    """Journal d'une séance de cocréation (un fichier JSON Lines en ajout seul)."""

    def __init__(self, racine_corpus: str | Path, seance: str, *, versionner: bool = True):
        if not re.fullmatch(r"\d{8}_[A-Za-z0-9.-]+_[A-Za-z0-9.-]+_\d{3}", seance):
            raise ValueError(f"Identifiant de séance hors nomenclature [DATE]_[SYSTÈME]_[TYPE]_[NUMÉRO] : {seance}")
        self.racine = Path(racine_corpus)
        self.seance = seance
        self.dossier_traces = self.racine / "traces" / seance[:8]
        self.dossier_traces.mkdir(parents=True, exist_ok=True)
        self.fichier = self.dossier_traces / f"{seance}.jsonl"
        self.depot = DepotCorpus(self.racine, versionner)
        self._verrou = threading.Lock()
        self._n = sum(1 for _ in self.fichier.open(encoding="utf-8")) if self.fichier.exists() else 0
        self._abonnes: list = []

    # ── Écriture ────────────────────────────────────────────
    def emettre(self, module: str, operation: str, agent: tuple[str, str] | dict, donnees: dict[str, Any],
                *, cycle: str | None = None, reconstitue: bool = False,
                categorie_autre: str | None = None) -> dict[str, Any]:
        if isinstance(agent, tuple):
            agent = {"type": agent[0], "id": agent[1]}
        with self._verrou:
            ev = {"schema": "robo-scene/evenement/v1", "id": f"{self.seance}-E{self._n + 1:05d}",
                  "ts": horodatage(), "seance": self.seance, "module": module, "operation": operation,
                  "cycle": cycle, "agent": agent, "reconstitue": bool(reconstitue),
                  "categorie_autre": categorie_autre, "donnees": donnees}
            erreurs = valider(ev)
            if erreurs:
                raise EvenementInvalide("; ".join(erreurs[:5]))
            if operation == "generation":
                ev["donnees"] = {**donnees, **self._deposer_generation(ev)}
            with self.fichier.open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            self._n += 1
        for fn in list(self._abonnes):
            try:
                fn(ev)
            except Exception:
                pass
        return ev

    def abonner(self, fn) -> None:
        self._abonnes.append(fn)

    def _deposer_generation(self, ev: dict[str, Any]) -> dict[str, Any]:
        d = ev["donnees"]
        date = self.seance[:8]
        systeme = _segment(d["version_modele"].upper(), "SYSTEME")
        type_ = _segment(d["type_texte"], "X")
        dossier = self.racine / systeme / type_ / date
        dossier.mkdir(parents=True, exist_ok=True)
        prefixe = f"{date}_{systeme}_{type_}_"
        n = 1 + max((int(m.group(1)) for p in dossier.glob(f"{prefixe}*.json")
                     if (m := re.search(r"_(\d{3})\.json$", p.name))), default=0)
        gid = f"{prefixe}{n:03d}"
        txt = dossier / f"{gid}.txt"
        txt.write_text("\n\n".join(f"[{i}] {p}" for i, p in enumerate(d["propositions"], 1)) + "\n",
                       encoding="utf-8")
        meta = {"identifiant": gid, "evenement": ev["id"], "seance": self.seance, "module": ev["module"],
                "cycle": ev["cycle"], "horodatage": ev["ts"], "systeme": d["systeme"],
                "version_modele": d["version_modele"], "type": d["type_texte"], "consigne_integrale": d["consigne"],
                "contexte_dramaturgique": d.get("contexte"), "parametres_demandes": d["parametres_demandes"],
                "parametres_appliques": d["parametres_appliques"], "ecarts_parametres": d.get("ecarts_parametres", []),
                "longueur_jetons": {"entree": d["jetons_entree"], "sortie": d["jetons_sortie"]},
                "nb_propositions": len(d["propositions"]), "notes": d.get("notes")}
        js = dossier / f"{gid}.json"
        js.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        commit = self.depot.deposer([txt, js], f"Génération {gid} — {d['systeme']} {d['version_modele']}, "
                                               f"type {d['type_texte']}, {len(d['propositions'])} proposition(s) "
                                               f"(séance {self.seance}, cycle {ev['cycle'] or '—'})")
        return {"identifiant_generation": gid, "fichier_texte": str(txt.relative_to(self.racine)),
                "fichier_meta": str(js.relative_to(self.racine)), "commit": commit,
                "commit_motif_absence": None if commit else self.depot.erreur}

    # ── Lecture ─────────────────────────────────────────────
    def lire(self) -> list[dict[str, Any]]:
        return lire_journal(self.fichier)

    def completude(self) -> dict[str, Any]:
        return completude(self.lire())


def lire_journal(chemin: str | Path) -> list[dict[str, Any]]:
    p = Path(chemin)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def completude(evenements: list[dict[str, Any]]) -> dict[str, Any]:
    """Critère d'acceptation de N-01 : chaque génération a ses cinq traces, ou un motif d'absence consigné.

    Pour chaque proposition générée : une sélection (ou une absence motivée) ; pour chaque proposition
    retenue : une transformation (même nulle) et une attribution (ou une absence motivée) ; chaque cycle
    a sa consigne.
    """
    par_cycle: dict[str, dict[str, list]] = {}
    for e in evenements:
        if e["operation"] == "autre" or not e.get("cycle"):
            continue
        par_cycle.setdefault(e["cycle"], {o: [] for o in OPERATIONS})[e["operation"]].append(e)
    manques = []
    n_gen = 0
    for cyc, ops in par_cycle.items():
        if not ops["generation"]:
            continue
        n_gen += len(ops["generation"])
        if not ops["consigne"]:
            manques.append({"cycle": cyc, "manque": "consigne"})
        absences = {o: any(x["donnees"].get("absence") for x in ops[o]) for o in OPERATIONS}
        for gi, g in enumerate(ops["generation"], 1):
            for pi in range(1, len(g["donnees"]["propositions"]) + 1):
                cle = (gi, pi)
                sel = [x for x in ops["selection"] if (x["donnees"].get("generation"), x["donnees"].get("proposition")) == cle
                       or (x["donnees"].get("generation") == gi and x["donnees"].get("decision") == "redemandee")]
                if not sel and not absences["selection"]:
                    manques.append({"cycle": cyc, "manque": "selection", "generation": gi, "proposition": pi})
                    continue
                if any(x["donnees"].get("decision") == "retenue" for x in sel):
                    for op in ("transformation", "attribution"):
                        ok = any((x["donnees"].get("generation"), x["donnees"].get("proposition")) == cle
                                 for x in ops[op]) or absences[op]
                        if not ok:
                            manques.append({"cycle": cyc, "manque": op, "generation": gi, "proposition": pi})
    return {"generations": n_gen, "cycles": len(par_cycle), "manques": manques,
            "conforme": not manques, "taux": 1.0 if not n_gen else round(1 - len({(m["cycle"], m.get("generation"))
                                                                                   for m in manques}) / max(1, n_gen), 3)}
