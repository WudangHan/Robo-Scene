"""Séance d'atelier : les cinq opérations (cadre R.4) et leur journal (instrument I-5, schéma PROV de P1.2).

1. consigne      → entité attribuée à l'artiste (pseudonyme)
2. génération    → activité associée au système (SI-01, SI-02 ou SIMULE), qui utilise consigne et extraits
3. sélection     → activité associée à l'artiste : retenue, rejetée, redemandée, avec motif
4. transformation→ version transformée dérivée de la proposition retenue ; écart mesuré
5. attribution   → étiquette humaine, système ou mixte, et crédit

Le journal est un fichier JSON Lines en ajout seul : chaque événement est écrit dès qu'il survient.
"""
from __future__ import annotations

import csv
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import __version__
from .ecart import ecart_transformation, etiquette_suggeree
from .modeles import ErreurModele, TYPES
from .routeur import Routeur

ETIQUETTES = ("humaine", "systeme", "mixte")
DECISIONS = ("retenue", "rejetee")
CRITERES_P1_1 = [
    "avis_ethique_favorable_et_consentements_approuves",
    "ententes_de_creation_signees",
    "exigences_EF01_EF07_ENF01_ENF02_ENF06_verifiees",
    "fournisseur_SI01_verifie_et_SI02_documente",
    "grille_de_relecture_des_biais_essayee_sur_50_propositions",
    "assurance_responsabilite_civile_souscrite",
]


class ErreurAtelier(Exception):
    pass


def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def verifier_mise_en_service(chemin: str | Path) -> list[str]:
    """Renvoie la liste des critères non remplis (fiche P1.1, section 7) ; vide si la mise en service est permise."""
    p = Path(chemin)
    if not p.exists():
        return ["fichier de mise en service absent"]
    d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    manquants = [c for c in CRITERES_P1_1 if d.get("criteres", {}).get(c) is not True]
    if not d.get("approuve_par") or not d.get("date"):
        manquants.append("approbation (nom et date) manquante")
    return manquants


@dataclass
class Proposition:
    texte: str
    decision: str | None = None
    motif: str = ""
    version: str | None = None
    ecart: float | None = None
    etiquette: str | None = None
    credit: str = ""


@dataclass
class GenerationCycle:
    systeme: str
    modele: str
    cible: str
    motifs_routage: list[str]
    propositions: list[Proposition]
    jetons: int
    horodatage: str


@dataclass
class Cycle:
    id: str
    pseudonyme: str
    type: str
    consigne: str
    nb: int
    extraits: list[str]
    confidentielle: bool
    generations: list[GenerationCycle] = field(default_factory=list)


class Atelier:
    def __init__(self, *, seance: str, pseudonymes: list[str], corpus: dict, distant, local, simule=None,
                 dossier_journal: str | Path = "journaux", liste_blocage: list[str] | None = None,
                 mode: str = "essai", mise_en_service: str | Path | None = None, plafond_jetons: int = 200_000,
                 nb_max: int = 5, forcer_simule: bool = False):
        if mode not in ("essai", "atelier"):
            raise ErreurAtelier("Mode inconnu.")
        if mode == "atelier":
            manquants = verifier_mise_en_service(mise_en_service or "mise_en_service.yaml")
            if manquants:
                raise ErreurAtelier("Mise en service refusée (fiche P1.1, section 7) : " + " ; ".join(manquants))
        self.mode, self.seance, self.pseudonymes = mode, seance, list(pseudonymes)
        self.corpus, self.distant, self.local, self.simule = corpus, distant, local, simule
        self.routeur = Routeur(liste_blocage)
        # Le générateur simulé n'est permis qu'en mode « essai » (aucune personne participante).
        self.forcer_simule = bool(forcer_simule and simule is not None and mode == "essai")
        self.plafond, self.nb_max = plafond_jetons, nb_max
        self.jetons = {"SI-01": 0, "SI-02": 0, "SIMULE": 0}
        self.cycles: dict[str, Cycle] = {}
        self.segments: list[dict] = []   # texte final ordonné : {texte, etiquette, credit, origine}
        self._verrou = threading.Lock()
        self.dossier = Path(dossier_journal)
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.fichier = self.dossier / f"{seance}_journal_I-5.jsonl"
        self._ecrire("ouverture", mode=mode, version_logiciel=__version__, pseudonymes=self.pseudonymes,
                     corpus=sorted(corpus))

    # ------------------------------------------------------------------ journal
    def _ecrire(self, evenement: str, **donnees):
        ligne = {"t": maintenant(), "seance": self.seance, "evenement": evenement, **donnees}
        with self._verrou, self.fichier.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")

    @property
    def hors_ligne(self) -> bool:
        return self.routeur.hors_ligne

    def regler_hors_ligne(self, actif: bool):
        self.routeur.hors_ligne = bool(actif)
        self._ecrire("mode_hors_ligne", actif=bool(actif))

    # ------------------------------------------------------------------ opérations 1 et 2
    def _modele_pour(self, decision):
        if self.forcer_simule:
            return self.simule
        if decision.cible == "local":
            return self.local
        if self.jetons["SI-01"] >= self.plafond:
            raise ErreurAtelier("Plafond de jetons de la séance atteint pour le modèle distant (ENF-04).")
        return self.distant

    def consigner(self, pseudonyme: str, texte: str, type_: str = "libre", nb: int = 3, extraits=(),
                  confidentielle: bool = False) -> Cycle:
        if pseudonyme not in self.pseudonymes:
            raise ErreurAtelier("Pseudonyme inconnu pour cette séance.")
        if not texte or not texte.strip():
            raise ErreurAtelier("Consigne vide.")
        if type_ not in TYPES:
            raise ErreurAtelier("Type de consigne inconnu.")
        nb = max(1, min(int(nb), self.nb_max))                            # EF-02 : de une à cinq
        inconnus = [c for c in extraits if c not in self.corpus]
        if inconnus:
            raise ErreurAtelier(f"Extraits inconnus : {inconnus}")
        with self._verrou:
            cid = f"{self.seance}-C{len(self.cycles) + 1:02d}"
            c = Cycle(cid, pseudonyme, type_, texte.strip(), nb, list(extraits), bool(confidentielle))
            self.cycles[cid] = c
        self._ecrire("consigne", cycle=cid, pseudonyme=pseudonyme, type=type_, consigne=c.consigne, nb=nb,
                     extraits=c.extraits, confidentielle=c.confidentielle)
        self._generer(c)
        return c

    def _generer(self, c: Cycle) -> GenerationCycle:
        extraits = [self.corpus[k] for k in c.extraits]
        decision = self.routeur.decider(c.consigne, extraits, c.confidentielle)
        modele = self._modele_pour(decision)
        if not modele.disponible:
            self._ecrire("generation_refusee", cycle=c.id, cible=decision.cible, motifs=decision.motifs)
            if decision.cible == "local":
                raise ErreurAtelier("Consigne sensible et modèle local indisponible : génération refusée "
                                    "(aucun repli sur le modèle distant).")
            raise ErreurAtelier("Modèle distant indisponible ; activez le mode hors ligne pour utiliser le modèle local.")
        try:
            g = modele.generer(c.consigne, c.type, c.nb, extraits)
        except ErreurModele as e:
            self._ecrire("generation_erreur", cycle=c.id, systeme=modele.code, erreur=str(e)[:300])
            raise ErreurAtelier(f"Erreur du modèle {modele.code} : {e}") from e
        gc = GenerationCycle(g.systeme, g.modele, decision.cible, decision.motifs,
                             [Proposition(p) for p in g.propositions], g.jetons_entree + g.jetons_sortie, maintenant())
        with self._verrou:
            c.generations.append(gc)
            self.jetons[g.systeme] = self.jetons.get(g.systeme, 0) + gc.jetons
        self._ecrire("generation", cycle=c.id, numero=len(c.generations), systeme=g.systeme, version_modele=g.modele,
                     cible=decision.cible, motifs_routage=decision.motifs, propositions=g.propositions,
                     jetons_entree=g.jetons_entree, jetons_sortie=g.jetons_sortie)
        return gc

    def redemander(self, cycle: str, motif: str = "") -> GenerationCycle:
        c = self._cycle(cycle)
        derniere = c.generations[-1] if c.generations else None
        if derniere:
            for p in derniere.propositions:
                if p.decision is None:
                    p.decision, p.motif = "redemandee", motif
        self._ecrire("selection", cycle=cycle, generation=len(c.generations), decision="redemandee", motif=motif)
        return self._generer(c)

    # ------------------------------------------------------------------ opérations 3 à 5
    def _cycle(self, cycle: str) -> Cycle:
        if cycle not in self.cycles:
            raise ErreurAtelier("Cycle inconnu.")
        return self.cycles[cycle]

    def _prop(self, cycle: str, gen: int, prop: int) -> Proposition:
        c = self._cycle(cycle)
        try:
            return c.generations[gen - 1].propositions[prop - 1]
        except IndexError as e:
            raise ErreurAtelier("Proposition inconnue.") from e

    def decider(self, cycle: str, gen: int, prop: int, decision: str, motif: str = ""):
        if decision not in DECISIONS:
            raise ErreurAtelier("Décision : « retenue » ou « rejetee ».")
        p = self._prop(cycle, gen, prop)
        p.decision, p.motif = decision, motif.strip()[:200]
        if decision == "retenue" and p.version is None:
            p.version = p.texte
            p.ecart = 0.0
        self._ecrire("selection", cycle=cycle, generation=gen, proposition=prop, decision=decision, motif=p.motif)

    def transformer(self, cycle: str, gen: int, prop: int, texte: str) -> float:
        p = self._prop(cycle, gen, prop)
        if p.decision != "retenue":
            raise ErreurAtelier("Seule une proposition retenue peut être transformée (EF-04).")
        p.version = texte.strip()
        p.ecart = ecart_transformation(p.texte, p.version)
        self._ecrire("transformation", cycle=cycle, generation=gen, proposition=prop, version_transformee=p.version,
                     ecart_transformation=p.ecart)
        return p.ecart

    def attribuer(self, cycle: str, gen: int, prop: int, etiquette: str | None = None, credit: str = "") -> dict:
        p = self._prop(cycle, gen, prop)
        if p.decision != "retenue":
            raise ErreurAtelier("Seule une proposition retenue entre dans le texte final.")
        etiquette = etiquette or etiquette_suggeree(p.ecart)
        if etiquette not in ETIQUETTES:
            raise ErreurAtelier("Étiquette : humaine, systeme ou mixte.")
        c = self._cycle(cycle)
        p.etiquette, p.credit = etiquette, (credit or c.pseudonyme).strip()[:120]
        seg = {"texte": p.version, "etiquette": etiquette, "credit": p.credit, "pseudonyme": c.pseudonyme,
               "origine": f"{cycle}/G{gen}/P{prop}",
               "ecart": p.ecart, "systeme": c.generations[gen - 1].systeme}
        self.segments.append(seg)
        self._ecrire("attribution", cycle=cycle, generation=gen, proposition=prop, etiquette=etiquette,
                     credit=p.credit, suggestion=etiquette_suggeree(p.ecart))
        return seg

    def segment_humain(self, pseudonyme: str, texte: str) -> dict:
        if pseudonyme not in self.pseudonymes:
            raise ErreurAtelier("Pseudonyme inconnu pour cette séance.")
        if not texte or not texte.strip():
            raise ErreurAtelier("Segment vide.")
        seg = {"texte": texte.strip(), "etiquette": "humaine", "credit": pseudonyme, "pseudonyme": pseudonyme,
               "origine": "écriture directe",
               "ecart": None, "systeme": None}
        self.segments.append(seg)
        self._ecrire("segment_humain", pseudonyme=pseudonyme, texte=seg["texte"])
        return seg

    def reetiqueter(self, index: int, etiquette: str):
        """EF-05 : l'étiquette d'un segment du texte final reste modifiable par l'artiste."""
        if etiquette not in ETIQUETTES or not (0 <= index < len(self.segments)):
            raise ErreurAtelier("Segment ou étiquette invalide.")
        ancienne = self.segments[index]["etiquette"]
        self.segments[index]["etiquette"] = etiquette
        self._ecrire("reetiquetage", segment=index, avant=ancienne, apres=etiquette)

    # ------------------------------------------------------------------ indicateurs et exports
    def indicateurs(self) -> dict:
        """Indicateurs d'agentivité opératoire par pseudonyme (instrument I-5)."""
        res = {}
        for ps in self.pseudonymes:
            props = [p for c in self.cycles.values() if c.pseudonyme == ps for g in c.generations for p in g.propositions]
            retenues = [p for p in props if p.decision == "retenue"]
            ecarts = [p.ecart for p in retenues if p.ecart is not None]
            segs = [s for s in self.segments if s["pseudonyme"] == ps]
            sys_brut = [s for s in segs if s["etiquette"] == "systeme" and (s["ecart"] or 0) == 0]
            res[ps] = {
                "propositions_generees": len(props), "propositions_retenues": len(retenues),
                "taux_conservation": round(len(retenues) / len(props), 3) if props else None,
                "ecart_moyen_retenues": round(sum(ecarts) / len(ecarts), 3) if ecarts else None,
                "segments_texte_final": len(segs),
                "part_systeme_sans_transformation": round(len(sys_brut) / len(segs), 3) if segs else None,
            }
        return res

    def lignes_registre(self) -> list[dict]:
        """Lignes au format de l'onglet « Provenance » du registre P1-2 (une par proposition décidée)."""
        lignes = []
        for c in self.cycles.values():
            for gi, g in enumerate(c.generations, 1):
                for pi, p in enumerate(g.propositions, 1):
                    if p.decision is None:
                        continue
                    lignes.append({
                        "id_cycle": c.id, "date": g.horodatage[:10], "seance": self.seance,
                        "pseudonyme_artiste": c.pseudonyme, "consigne": c.consigne, "type_consigne": c.type,
                        "extraits_utilises (codes CORP)": ", ".join(c.extraits),
                        "systeme (SI-01/SI-02)": g.systeme, "version_modele": g.modele,
                        "nb_propositions": len(g.propositions), "proposition_retenue": f"G{gi}/P{pi}",
                        "decision": p.decision, "motif": p.motif,
                        "version_transformee (réf.)": f"{c.id}/G{gi}/P{pi}" if p.version else "",
                        "ecart_transformation (0–1)": p.ecart if p.ecart is not None else "",
                        "etiquette (humaine/système/mixte)": p.etiquette or "", "credit": p.credit,
                        "diffusion (oui/non)": "non",
                    })
        return lignes

    def exporter(self) -> dict[str, Path]:
        """EF-06 : export JSON horodaté (pseudonymes seulement) et CSV compatible avec le registre P1-2."""
        horo = datetime.now().strftime("%Y-%m-%d_%H%M")
        pj = self.dossier / f"{self.seance}_{horo}_export_I-5.json"
        doc = {
            "systeme": "SI-04", "version_logiciel": __version__, "seance": self.seance, "mode": self.mode,
            "exporte_le": maintenant(), "jetons": self.jetons,
            "schema": "Cinq opérations (R.4) ; relations PROV-O : wasAttributedTo, used, wasAssociatedWith, "
                      "wasGeneratedBy, wasDerivedFrom (P1.2, section 4)",
            "corpus": {k: e.public() for k, e in self.corpus.items()},
            "cycles": [{
                "id": c.id, "pseudonyme": c.pseudonyme, "type": c.type, "consigne": c.consigne,
                "extraits_utilises": c.extraits, "confidentielle": c.confidentielle,
                "generations": [{
                    "systeme": g.systeme, "version_modele": g.modele, "cible": g.cible, "motifs_routage": g.motifs_routage,
                    "jetons": g.jetons, "horodatage": g.horodatage,
                    "propositions": [p.__dict__ for p in g.propositions],
                } for g in c.generations],
            } for c in self.cycles.values()],
            "texte_final": self.segments,
            "indicateurs": self.indicateurs(),
        }
        pj.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        pc = self.dossier / f"{self.seance}_{horo}_registre_provenance.csv"
        lignes = self.lignes_registre()
        with pc.open("w", encoding="utf-8-sig", newline="") as f:
            champs = list(lignes[0]) if lignes else ["id_cycle"]
            w = csv.DictWriter(f, fieldnames=champs, delimiter=";")
            w.writeheader()
            w.writerows(lignes)
        self._ecrire("export", json=pj.name, csv=pc.name)
        return {"json": pj, "csv": pc}
