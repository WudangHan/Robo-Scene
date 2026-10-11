"""O-03 — Export TEI d'une pièce de la bibliothèque, pour encoder les répertoires franco-canadiens.

Le cahier (§4, O-03) relève que le corpus DraCor est surtout européen et que les répertoires franco-canadiens
devront être encodés. L'export suit les conventions que lit déjà l'importeur du partenaire (texte.lire_tei),
elles-mêmes calquées sur DraCor : <particDesc>/<listPerson>/<person xml:id>, <div type="act">/<div type="scene">,
<sp who="#id"><speaker>, <l> pour le vers et <p> pour la prose, <stage>. L'aller-retour (export puis import)
conserve personnages, scènes, répliques, didascalies et leur ordre ; la position d'une didascalie à l'intérieur
d'une réplique n'est pas conservée (elle est placée en tête de la réplique).

(Inférence) Le fichier produit est un point de départ d'encodage : l'en-tête (sources, licence, dates) doit être
complété et le document validé contre le schéma TEI ou DraCor avant tout dépôt public.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

NS = "http://www.tei-c.org/ns/1.0"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def _sous(parent: ET.Element, tag: str, texte: str | None = None, **attrs: str) -> ET.Element:
    el = ET.SubElement(parent, f"{{{NS}}}{tag}", {k: v for k, v in attrs.items() if v is not None})
    if texte is not None:
        el.text = texte
    return el


def _xml_id(s: str) -> str:
    s = "".join(c if c.isalnum() or c in "-_." else "_" for c in s)
    return s if s[:1].isalpha() or s[:1] == "_" else f"p_{s}"


def exporter(piece: dict[str, Any], *, licence: str | None = None, langue: str = "fr") -> str:
    ET.register_namespace("", NS)
    tei = ET.Element(f"{{{NS}}}TEI", {"{http://www.w3.org/XML/1998/namespace}lang": langue})
    en_tete = _sous(tei, "teiHeader")
    fd = _sous(en_tete, "fileDesc")
    ts = _sous(fd, "titleStmt")
    _sous(ts, "title", piece.get("titre", ""), type="main")
    if piece.get("auteur"):
        aut = _sous(ts, "author")
        _sous(aut, "persName", piece["auteur"])
    ps = _sous(fd, "publicationStmt")
    _sous(ps, "p", "Encodage produit par la plateforme ROBO-SCÈNE (fonction O-03) ; en-tête à compléter avant dépôt.")
    av = _sous(ps, "availability")
    lic = _sous(av, "licence")
    _sous(lic, "ab", licence or (piece.get("source") or {}).get("licence") or "Licence à préciser")
    sd = _sous(fd, "sourceDesc")
    _sous(sd, "p", str((piece.get("source") or {}).get("type", "source à préciser")))
    pr = _sous(en_tete, "profileDesc")
    lp = _sous(_sous(pr, "particDesc"), "listPerson")
    ids = {}
    for p in piece.get("personnages", []):
        ids[p["id"]] = _xml_id(p["id"])
        pers = _sous(lp, "person", **{XML_ID: ids[p["id"]], "sex": {"f": "FEMALE", "m": "MALE"}.get(p.get("genre") or "")})
        _sous(pers, "persName", p.get("nom", p["id"]))
    corps = _sous(_sous(tei, "text"), "body")
    actes: dict[str, ET.Element] = {}
    par_scene: dict[str, list] = {}
    for e in piece.get("elements", []):
        par_scene.setdefault(e["scene"], []).append(e)
    for s in piece.get("scenes", []):
        parent = corps
        if s.get("acte"):
            if s["acte"] not in actes:
                actes[s["acte"]] = _sous(corps, "div", type="act")
                _sous(actes[s["acte"]], "head", s["acte"])
            parent = actes[s["acte"]]
        div = _sous(parent, "div", type="scene")
        _sous(div, "head", s.get("titre") or f"Scène {s['id']}")
        for e in par_scene.get(s["id"], []):
            if e["type"] == "didascalie":
                _sous(div, "stage", e["texte"])
                continue
            sp = _sous(div, "sp", who=f"#{ids.get(e['perso'], _xml_id(e['perso']))}")
            _sous(sp, "speaker", e.get("nom", ""))
            types = list(e.get("didascalies_types") or [])
            for i, d in enumerate(e.get("didascalies", [])):
                _sous(sp, "stage", d, type=types[i] if i < len(types) else None)
            if e.get("vers"):
                for ligne in e["texte"].split("\n"):
                    _sous(sp, "l", ligne)
            else:
                _sous(sp, "p", e["texte"])
    ET.indent(tei, "  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(tei, encoding="unicode")
