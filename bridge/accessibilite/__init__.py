"""O-06 — Surtitrage et audiodescription générés, puis validés par une personne (français et anglais).

Conditions du cahier : « validation humaine et étiquette de provenance obligatoires ». Le flux suit donc les
cinq opérations de R.4, tracées dans le journal unifié (module SCENE) :
1. consigne — demande de surtitres (traduction) ou d'audiodescription pour une liste de repères ;
2. génération — propositions du modèle (service D13 ; contenu confidentiel → modèle local, D03) ;
3. sélection — chaque proposition est validée ou rejetée par une personne (aucune diffusion sans validation) ;
4. transformation — la personne peut corriger ; l'écart est mesuré (N-04) ;
5. attribution — étiquette « systeme » (inchangé), « mixte » (corrigé) ou « humaine » (saisi à la main).

Seuls les éléments validés sont diffusés en salle (événement « surtitre ») ou exportés en WebVTT, avec leur
provenance en commentaire (NOTE) dans le fichier.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from ..trace import EvenementInvalide
from ..trace.ecart import mesurer

TYPES = ("surtitre", "audiodescription")
LANGUES = ("fr", "en")

SYSTEME_SURTITRES = """Tu prépares des surtitres de théâtre. Traduis chaque réplique vers la langue cible en gardant le
registre, le rythme et la brièveté lisible d'un surtitre (deux lignes de 42 caractères au plus quand c'est possible).
Réponds UNIQUEMENT par un objet JSON {"items": [{"id": "...", "texte": "..."}]}."""

SYSTEME_AD = """Tu rédiges une audiodescription de théâtre : une phrase brève, au présent, qui décrit ce qui se voit
(gestes, déplacements, lumière), sans interpréter les intentions ni les émotions des personnages, sans nommer
d'émotion qui ne soit pas visible. Langue demandée : {langue}.
Réponds UNIQUEMENT par un objet JSON {{"items": [{{"id": "...", "texte": "..."}}]}}."""


class Surtitrage:
    def __init__(self, ctl, dossier: Path | None = None):
        self.ctl = ctl
        self.dossier = Path(dossier or (ctl.donnees / "surtitres"))
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.fichier = self.dossier / "elements.json"
        self._verrou = threading.Lock()
        self.elements: dict[str, dict[str, Any]] = (json.loads(self.fichier.read_text(encoding="utf-8"))
                                                   if self.fichier.exists() else {})
        self._n = 0

    def _sauver(self) -> None:
        tmp = self.fichier.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.elements, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.fichier)

    def _trace(self, operation: str, agent: tuple[str, str], donnees: dict[str, Any], cycle: str | None) -> None:
        try:
            self.ctl.trace.emettre("SCENE", operation, agent, donnees, cycle=cycle)
        except (EvenementInvalide, OSError, AttributeError):
            pass

    # ── Sources ─────────────────────────────────────────────
    def importer_conduite(self) -> dict[str, Any]:
        """Crée un élément par réplique (surtitre) et par repère comportant gestes ou didascalies (audiodescription)."""
        c = getattr(getattr(self.ctl, "scene", None), "conduite", None)
        if c is None:
            raise ValueError("Aucune conduite chargée")
        n = 0
        with self._verrou:
            for r in c.reperes:
                for i, a in enumerate(r.actions):
                    if a.type == "replique":
                        d = a.valeur if isinstance(a.valeur, dict) else {"texte": str(a.valeur)}
                        eid = f"{r.numero}-{i}"
                        el = self.elements.setdefault(eid, {"id": eid, "repere": r.numero, "type": "surtitre",
                                                            "source": {"fr": d.get("texte", "")}, "versions": {}})
                        if d.get("en") and "en" not in el["versions"]:
                            el["versions"]["en"] = {"texte": d["en"], "statut": "valide", "etiquette": "humaine",
                                                    "par": "conduite", "date": _maintenant()}
                        n += 1
                visibles = [f"geste « {a.valeur} »" + (f" ({a.robot})" if a.robot else "")
                            for a in r.actions if a.type == "geste"]
                if visibles or r.nom:
                    eid = f"{r.numero}-AD"
                    self.elements.setdefault(eid, {"id": eid, "repere": r.numero, "type": "audiodescription",
                                                   "source": {"fr": f"Repère {r.nom or r.numero} : " + ", ".join(visibles)},
                                                   "versions": {}})
                    n += 1
            self._sauver()
        return {"elements": n, **self.etat()}

    # ── Opérations 1 et 2 ───────────────────────────────────
    async def proposer(self, ids: list[str], langue: str, *, confidentielle: bool = False, par: str = "") -> dict[str, Any]:
        if langue not in LANGUES:
            raise ValueError("Langue : fr ou en")
        els = [self.elements[i] for i in ids if i in self.elements]
        if not els:
            raise ValueError("Aucun élément")
        types = {e["type"] for e in els}
        if len(types) > 1:
            raise ValueError("Une demande ne mélange pas surtitres et audiodescription")
        t = types.pop()
        self._n += 1
        cycle = f"ST-{datetime.now():%H%M%S}-{self._n}"
        personne = par or getattr(self.ctl, "pseudo_operatrice", "OP01")
        consigne = f"{t} vers {langue} pour {len(els)} élément(s)"
        self._trace("consigne", ("personne", personne), {"texte": consigne, "type": t, "langue": langue,
                                                          "elements": [e["id"] for e in els]}, cycle)
        systeme = SYSTEME_SURTITRES if t == "surtitre" else SYSTEME_AD.format(langue=langue)
        contenu = f"Langue cible : {langue}\n" + "\n".join(f"[{e['id']}] {e['source'].get('fr', '')}" for e in els)
        r = await self.ctl.service.generer("rapide", systeme, contenu, temperature=0.3, max_tokens=2000,
                                           confidentielle=confidentielle, json_attendu=True)
        m = re.search(r"\{.*\}", r.texte, re.S)
        items = {str(x.get("id")): str(x.get("texte", "")).strip()
                 for x in (json.loads(m.group(0)).get("items", []) if m else [])}
        props = [items.get(e["id"], "") or "(aucune proposition)" for e in els]
        self._trace("generation", ("systeme", r.systeme),
                    {**r.trace(), "type_texte": t, "consigne": consigne, "propositions": props}, cycle)
        with self._verrou:
            for k, (e, p) in enumerate(zip(els, props), 1):
                e["versions"][langue] = {"proposition": p, "statut": "a_valider", "cycle": cycle, "rang": k,
                                         "modele": r.modele_exact, "date": _maintenant()}
            self._sauver()
        return self.etat()

    # ── Opérations 3, 4 et 5 ────────────────────────────────
    def valider(self, eid: str, langue: str, *, decision: str, par: str, texte: str | None = None) -> dict[str, Any]:
        if not par.strip():
            raise ValueError("Indiquer qui valide (pseudonyme)")
        if decision not in ("valide", "rejete"):
            raise ValueError("Décision : valide ou rejete")
        e = self.elements[eid]
        v = e["versions"].get(langue)
        if not v or "proposition" not in v:
            raise ValueError("Aucune proposition à valider")
        cyc, k = v.get("cycle"), v.get("rang", 1)
        self._trace("selection", ("personne", par), {"generation": 1, "proposition": k,
                                                     "decision": "retenue" if decision == "valide" else "rejetee",
                                                     "motif": "validation humaine du surtitrage (O-06)"}, cyc)
        if decision == "rejete":
            v.update(statut="rejete", par=par, date=_maintenant())
        else:
            final = (texte if texte is not None else v["proposition"]).strip()
            mesure = mesurer(v["proposition"], final)
            etiquette = "systeme" if mesure["ecart"] == 0 else "mixte"
            self._trace("transformation", ("personne", par), {"generation": 1, "proposition": k, "version": final,
                                                              **mesure}, cyc)
            self._trace("attribution", ("personne", par), {"generation": 1, "proposition": k, "etiquette": etiquette,
                                                           "credit": f"{e['type']} validé par {par}"}, cyc)
            v.update(texte=final, statut="valide", etiquette=etiquette, par=par, date=_maintenant(), **mesure)
        with self._verrou:
            self._sauver()
        return e

    def saisir(self, eid: str, langue: str, texte: str, par: str) -> dict[str, Any]:
        """Version écrite par une personne : provenance « humaine », validée d'emblée."""
        if not par.strip() or not texte.strip():
            raise ValueError("Texte et pseudonyme requis")
        e = self.elements[eid]
        e["versions"][langue] = {"texte": texte.strip(), "statut": "valide", "etiquette": "humaine", "par": par,
                                 "date": _maintenant()}
        with self._verrou:
            self._sauver()
        return e

    # ── Diffusion et export ─────────────────────────────────
    def valide(self, repere: str, langue: str, type_: str = "surtitre") -> str | None:
        for e in self.elements.values():
            v = e["versions"].get(langue) or {}
            if e["repere"] == str(repere) and e["type"] == type_ and v.get("statut") == "valide":
                return v["texte"]
        return None

    def webvtt(self, langue: str, type_: str = "surtitre", durees: dict[str, float] | None = None,
               duree_defaut: float = 4.0) -> Path:
        """Fichier WebVTT des seuls éléments validés, dans l'ordre des repères ; la provenance est notée.
        Sans durées réelles (captation), les repères sont espacés de `duree_defaut` secondes (à recaler)."""
        els = [e for e in self.elements.values() if e["type"] == type_
               and (e["versions"].get(langue) or {}).get("statut") == "valide"]
        els.sort(key=lambda e: _cle(e["id"]))
        lignes = ["WEBVTT", "", f"NOTE {type_} {langue} — éléments validés par une personne (O-06) ; "
                  "horodatage provisoire si aucune durée réelle n'est fournie.", ""]
        t = 0.0
        for e in els:
            v = e["versions"][langue]
            d = (durees or {}).get(e["id"], duree_defaut)
            lignes += [f"NOTE {e['id']} provenance={v.get('etiquette')} validé_par={v.get('par')}", "",
                       e["id"], f"{_ts(t)} --> {_ts(t + d)}", v["texte"], ""]
            t += d
        f = self.dossier / f"{type_}_{langue}.vtt"
        f.write_text("\n".join(lignes), encoding="utf-8")
        return f

    def etat(self) -> dict[str, Any]:
        c = {"a_valider": 0, "valide": 0, "rejete": 0}
        for e in self.elements.values():
            for v in e["versions"].values():
                c[v.get("statut", "a_valider")] = c.get(v.get("statut", "a_valider"), 0) + 1
        return {"compte": c, "elements": sorted(self.elements.values(), key=lambda e: _cle(e["id"]))}


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _ts(s: float) -> str:
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{sec:06.3f}"


def _cle(eid: str):
    return [(0, int(x), "") if x.isdigit() else (1, 0, x) for x in re.split(r"[-.]", eid)]
