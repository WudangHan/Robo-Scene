"""Séquences gestuelles : enchaînements de gestes de la bibliothèque fermée (repère P2.4).

Une séquence ne crée aucun mouvement nouveau : elle ordonne des gestes déjà présents dans la
bibliothèque, insère des pauses et, lorsque l'enchaînement direct dépasserait une limite, une
transition calculée vers la pose neutre. Elle reste donc soumise à la règle de la bibliothèque
fermée (plan de prévention P2.1, § 6.4) : un module d'IA peut en proposer le NOM, jamais la composer.

Règles de composition :
* « liaison: auto » (défaut) — enchaînement direct si le geste suivant reste dans les limites en
  partant de la pose atteinte ; sinon transition vers le neutre, de durée minimale sûre.
* « liaison: directe » — enchaînement direct exigé ; erreur si une limite serait dépassée.
* « liaison: neutre » — transition vers le neutre imposée.
* « etirement » (≥ 1) — ralentit un geste ; aucune accélération n'est permise.
* Statut effectif = le plus bas entre le statut déclaré de la séquence et ceux de ses gestes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .bibliotheque import (COMPOSANTES_TETE, LIMITES_PROJET, POSE_NEUTRE, STATUTS, Geste, ImageCle,
                           charger, valider)

PIC = 1.875          # rapport pic/moyenne du profil à jerk minimal (voir bibliotheque.valider)
PAS = 0.05           # arrondi des durées de transition (s)
MARGE = 1.10         # marge de 10 % sous les vitesses limites pour les transitions calculées


class ErreurSequence(ValueError):
    pass


@dataclass
class Etape:
    type: str            # geste, pause, transition
    nom: str
    debut_s: float
    fin_s: float
    liaison: str = ""


@dataclass
class Sequence(Geste):
    statut_declare: str = "brouillon"
    plan: list[Etape] = field(default_factory=list)


def duree_transition(a: ImageCle, b: ImageCle) -> float:
    """Durée minimale (arrondie au pas supérieur) pour aller de a à b sans dépasser les vitesses limites."""
    dang = max(max(abs(b.tete[x] - a.tete[x]) for x in ("roll", "pitch", "yaw")), abs(b.body_yaw - a.body_yaw))
    dlin = math.dist([b.tete[x] for x in ("x", "y", "z")], [a.tete[x] for x in ("x", "y", "z")])
    dant = max(abs(b.antennes[j] - a.antennes[j]) for j in (0, 1))
    L = LIMITES_PROJET
    d = max(PIC * MARGE * dang / L["vitesse_angulaire_deg_s"], PIC * MARGE * dlin / L["vitesse_lineaire_mm_s"],
            PIC * MARGE * dant / L["vitesse_antenne_deg_s"], L["duree_min_s"])
    return round(math.ceil(d / PAS - 1e-9) * PAS, 2)


def _etirer(g: Geste, facteur: float) -> list[ImageCle]:
    return [ImageCle(round(k.duree * facteur, 3), dict(k.tete), tuple(k.antennes), k.body_yaw) for k in g.images_cles]


def composer(nom: str, brut: dict, biblio: dict[str, Geste]) -> Sequence:
    elements = brut.get("elements") or []
    if not elements:
        raise ErreurSequence(f"{nom} : séquence vide")
    statut_decl = brut.get("statut", "brouillon")
    if statut_decl not in STATUTS:
        raise ErreurSequence(f"{nom} : statut inconnu « {statut_decl} »")
    images: list[ImageCle] = []
    plan: list[Etape] = []
    prec, t = POSE_NEUTRE, 0.0
    statuts = [statut_decl]
    for i, el in enumerate(elements, 1):
        if "pause" in el:
            d = float(el["pause"])
            if d < LIMITES_PROJET["duree_min_s"]:
                raise ErreurSequence(f"{nom}, élément {i} : pause de {d} s trop courte")
            images.append(ImageCle(d, dict(prec.tete), tuple(prec.antennes), prec.body_yaw))
            plan.append(Etape("pause", f"pause {d:g} s", round(t, 2), round(t + d, 2)))
            t += d
            continue
        g_nom = el.get("geste")
        if g_nom not in biblio:
            raise ErreurSequence(f"{nom}, élément {i} : « {g_nom} » n'appartient pas à la bibliothèque fermée")
        facteur = float(el.get("etirement", 1.0))
        if facteur < 1.0:
            raise ErreurSequence(f"{nom}, élément {i} : étirement {facteur} < 1 (aucune accélération permise)")
        g = biblio[g_nom]
        statuts.append(g.statut)
        cles = _etirer(g, facteur)
        g_et = Geste(g.nom, g.description, g.intention, g.laban, g.statut, cles)
        liaison = el.get("liaison", "auto")
        if liaison not in ("auto", "directe", "neutre"):
            raise ErreurSequence(f"{nom}, élément {i} : liaison « {liaison} » inconnue")
        direct_ok = not valider(g_et, depart=prec)
        if liaison == "directe" and not direct_ok:
            raise ErreurSequence(f"{nom}, élément {i} : liaison directe impossible — {valider(g_et, depart=prec)[0]}")
        mode = "directe" if (liaison == "directe" or (liaison == "auto" and direct_ok)) else "neutre"
        hors_neutre = (prec.tete != POSE_NEUTRE.tete or tuple(prec.antennes) != tuple(POSE_NEUTRE.antennes)
                       or prec.body_yaw != POSE_NEUTRE.body_yaw)
        if mode == "neutre" and hors_neutre:
            d = duree_transition(prec, POSE_NEUTRE)
            images.append(ImageCle(d, dict(POSE_NEUTRE.tete), tuple(POSE_NEUTRE.antennes), POSE_NEUTRE.body_yaw))
            plan.append(Etape("transition", "vers le neutre", round(t, 2), round(t + d, 2)))
            t += d
            prec = images[-1]
        dg = sum(k.duree for k in cles)
        images.extend(cles)
        plan.append(Etape("geste", g_nom, round(t, 2), round(t + dg, 2), mode))
        t += dg
        prec = cles[-1]
    statut = min(statuts, key=STATUTS.index)
    seq = Sequence(nom, brut.get("description", {}), brut.get("intention", ""), {}, statut, images,
                   statut_declare=statut_decl, plan=plan)
    violations = valider(seq)
    if violations:
        raise ErreurSequence(f"{nom} : composition hors limites — {violations[0]}")
    return seq


def charger_sequences(chemin: str | Path | None = None, biblio: dict[str, Geste] | None = None) -> dict[str, Sequence]:
    chemin = Path(chemin) if chemin else Path(__file__).with_name("sequences.yaml")
    if not chemin.exists():
        return {}
    biblio = biblio if biblio is not None else charger()
    donnees = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    seqs = {}
    for nom, brut in (donnees.get("sequences") or {}).items():
        if nom in biblio:
            raise ErreurSequence(f"« {nom} » est déjà le nom d'un geste")
        seqs[nom] = composer(nom, brut, biblio)
    return seqs


def decrire(seq: Sequence) -> str:
    lignes = [f"{seq.nom} — {seq.duree_totale:.2f} s — statut effectif « {seq.statut} » (déclaré « {seq.statut_declare} »)"]
    for e in seq.plan:
        lignes.append(f"  {e.debut_s:6.2f}–{e.fin_s:6.2f} s  {e.type:10} {e.nom}" + (f"  [{e.liaison}]" if e.liaison else ""))
    return "\n".join(lignes)
