"""Séance et agrégation anonyme des réponses du public (P3.2).

Principes (spécification P3.1, section 2 ; plan de gestion des données G.6, DO-04) :

* aucune réponse individuelle n'est conservée : chaque réponse incrémente aussitôt des compteurs
  par cellule (fenêtre de temps × repère × étiquette de provenance), puis disparaît ;
* aucun horodatage individuel, aucune adresse IP, aucun témoin (cookie) ;
* le seul état par appareil est un jeton éphémère, tiré au hasard, qui sert au délai minimal
  entre deux réponses ; il réside en mémoire vive et il est effacé à la fin de la séance ;
* à l'export, les cellules de moins de `seuil_diffusion` réponses sont masquées.
"""
from __future__ import annotations

import secrets
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .emotions import CLES, curseur_vers_unite, plus_proche

PROVENANCES = ("humaine", "systeme", "mixte")
SANS_ETIQUETTE = "aucune"


class ErreurSeance(Exception):
    code_http = 400


class CodeInvalide(ErreurSeance):
    code_http = 403


class JetonInconnu(ErreurSeance):
    code_http = 403


class TropTot(ErreurSeance):
    code_http = 429


class SeanceClose(ErreurSeance):
    code_http = 410


class ValeurInvalide(ErreurSeance):
    code_http = 400


@dataclass
class Cellule:
    emotions: Counter = field(default_factory=Counter)
    n: int = 0
    n_curseurs: int = 0
    somme_v: float = 0.0  # sommes des réponses par curseurs seulement (moyennes à l'export)
    somme_a: float = 0.0


class Seance:
    def __init__(self, *, titre: str = "Séance d'essai", code: str | None = None, fenetre_s: float = 30.0,
                 delai_min_s: float = 10.0, seuil_diffusion: int = 5, afficher_provenance: bool = False,
                 horloge=time.monotonic):
        self.titre = titre
        self.code = code or f"{secrets.randbelow(10_000):04d}"
        self.cle_regie = secrets.token_urlsafe(18)
        self.fenetre_s, self.delai_min_s, self.seuil = float(fenetre_s), float(delai_min_s), int(seuil_diffusion)
        self.afficher_provenance = bool(afficher_provenance)  # condition expérimentale H4
        self._horloge = horloge
        self._t0 = horloge()
        self.debut_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        self._jetons: dict[str, float] = {}       # jeton -> instant du dernier envoi (mémoire vive seulement)
        self._cellules: dict[tuple[int, str, str], Cellule] = {}
        self.provenance = SANS_ETIQUETTE
        self.repere = "-"
        self.close = False
        self._verrou = threading.Lock()
        self._abonnes: list = []  # fonctions appelées à chaque événement public

    # ------------------------------------------------------------------ public
    def rejoindre(self, code: str) -> str:
        if self.close:
            raise SeanceClose("La séance est terminée.")
        if not secrets.compare_digest(str(code).strip(), self.code):
            raise CodeInvalide("Code de séance incorrect.")
        jeton = secrets.token_urlsafe(16)
        with self._verrou:
            self._jetons[jeton] = float("-inf")
        return jeton

    def repondre(self, jeton: str, *, emotion: str | None = None, v: int | None = None,
                 a: int | None = None) -> str:
        """Enregistre une réponse dans l'agrégat et renvoie la clé d'émotion retenue."""
        maintenant = self._horloge()
        with self._verrou:
            if self.close:
                raise SeanceClose("La séance est terminée.")
            if jeton not in self._jetons:
                raise JetonInconnu("Jeton inconnu.")
            if maintenant - self._jetons[jeton] < self.delai_min_s:
                raise TropTot(f"Une réponse au plus toutes les {self.delai_min_s:g} secondes.")
            if emotion is not None:
                if emotion not in CLES:
                    raise ValeurInvalide("Émotion inconnue.")
                cle, curseurs = emotion, None
            else:
                if not all(isinstance(x, int) and 1 <= x <= 9 for x in (v, a)):
                    raise ValeurInvalide("Curseurs : deux entiers de 1 à 9 attendus.")
                vu, au = curseur_vers_unite(v), curseur_vers_unite(a)
                cle, curseurs = plus_proche(vu, au), (vu, au)
            self._jetons[jeton] = maintenant
            fen = int((maintenant - self._t0) // self.fenetre_s)
            c = self._cellules.setdefault((fen, self.repere, self.provenance), Cellule())
            c.emotions[cle] += 1
            c.n += 1
            if curseurs:
                c.n_curseurs += 1
                c.somme_v += curseurs[0]
                c.somme_a += curseurs[1]
        return cle

    # ------------------------------------------------------------------ régie
    def etiqueter(self, etiquette: str, repere: str | None = None):
        """Change l'étiquette de provenance de la réplique en cours (OSC /p3/provenance ou régie)."""
        if etiquette not in PROVENANCES + (SANS_ETIQUETTE,):
            raise ValeurInvalide(f"Étiquette de provenance invalide : {etiquette!r}")
        with self._verrou:
            self.provenance = etiquette
            if repere is not None:
                self.repere = str(repere)[:20]
        self._diffuser("provenance", self.evenement_provenance())

    def marquer_repere(self, repere: str):
        with self._verrou:
            self.repere = str(repere)[:20]

    def evenement_provenance(self) -> dict:
        # Le public ne reçoit l'étiquette que si la condition « provenance affichée » est active.
        return {"etiquette": self.provenance if self.afficher_provenance else None}

    def terminer(self) -> dict:
        with self._verrou:
            self.close = True
            self._jetons.clear()  # aucun jeton ne survit à la séance
        self._diffuser("fin", {})
        return self.exporter()

    def etat_regie(self) -> dict:
        with self._verrou:
            tot, par_prov = Counter(), {p: Counter() for p in PROVENANCES + (SANS_ETIQUETTE,)}
            fen_courante = int((self._horloge() - self._t0) // self.fenetre_s)
            recent = Counter()
            for (fen, _rep, prov), c in self._cellules.items():
                tot.update(c.emotions)
                par_prov[prov].update(c.emotions)
                if fen == fen_courante:
                    recent.update(c.emotions)
            return {
                "titre": self.titre, "code": self.code, "close": self.close,
                "provenance": self.provenance, "repere": self.repere,
                "condition_provenance_affichee": self.afficher_provenance,
                "appareils": len(self._jetons), "reponses": sum(tot.values()),
                "par_emotion": {k: tot[k] for k in CLES},
                "fenetre_courante": {k: recent[k] for k in CLES},
                "par_provenance": {p: {k: cnt[k] for k in CLES} for p, cnt in par_prov.items() if cnt},
            }

    def exporter(self) -> dict:
        """Agrégat diffusable : cellules sous le seuil masquées ; aucun jeton, aucun horodatage individuel."""
        with self._verrou:
            cellules = []
            for (fen, rep, prov), c in sorted(self._cellules.items()):
                ligne = {"fenetre": fen, "debut_s": fen * self.fenetre_s, "repere": rep, "provenance": prov}
                if c.n < self.seuil:
                    ligne.update({"masquee": True, "n": None})
                else:
                    ligne.update({"masquee": False, "n": c.n, "emotions": {k: c.emotions[k] for k in CLES}})
                    if c.n_curseurs >= self.seuil:
                        ligne["moyennes_curseurs"] = {"agrement": round(c.somme_v / c.n_curseurs, 3),
                                                      "intensite": round(c.somme_a / c.n_curseurs, 3),
                                                      "n": c.n_curseurs}
                cellules.append(ligne)
            par_prov = {}
            for p in PROVENANCES + (SANS_ETIQUETTE,):
                cnt = Counter()
                for (_f, _r, pr), c in self._cellules.items():
                    if pr == p:
                        cnt.update(c.emotions)
                n = sum(cnt.values())
                if n:
                    par_prov[p] = {"n": n, "emotions": {k: cnt[k] for k in CLES}} if n >= self.seuil \
                        else {"n": None, "masquee": True}
        return {
            "systeme": "SI-06", "version_logiciel": "0.1.1-alpha", "titre": self.titre,
            "debut_utc": self.debut_utc, "fenetre_s": self.fenetre_s, "seuil_diffusion": self.seuil,
            "condition_provenance_affichee": self.afficher_provenance,
            "avertissement": "Agrégat anonyme : aucune réponse individuelle n'a été conservée.",
            "par_provenance": par_prov, "cellules": cellules,
        }

    # ------------------------------------------------------------------ diffusion
    def abonner(self, fonction):
        with self._verrou:
            self._abonnes.append(fonction)

    def desabonner(self, fonction):
        with self._verrou:
            if fonction in self._abonnes:
                self._abonnes.remove(fonction)

    def _diffuser(self, nom: str, donnees: dict):
        for f in list(self._abonnes):
            try:
                f(nom, donnees)
            except Exception:  # un client déconnecté ne doit pas bloquer la séance
                self.desabonner(f)
