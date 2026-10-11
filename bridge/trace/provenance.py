"""Export du journal unifié selon le modèle de provenance du W3C (N-06).

Correspondance (P1.2, section 4 ; PROV-O, recommandation W3C du 30 avril 2013) :
* consigne                → prov:Entity attribuée à la personne (prov:wasAttributedTo)
* génération              → prov:Activity associée au système SI (prov:wasAssociatedWith) qui utilise la consigne
* proposition             → prov:Entity générée par la génération (prov:wasGeneratedBy)
* sélection               → prov:Activity associée à la personne, qui utilise la proposition
* transformation          → prov:Activity ; version transformée dérivée de la proposition (prov:wasDerivedFrom)
* attribution             → étiquette et crédit (rs:etiquette, rs:credit) sur la version finale
"""
from __future__ import annotations

from typing import Any

from rdflib import RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef

PROV = Namespace("http://www.w3.org/ns/prov#")
RS = Namespace("https://robo-scene.local/ns#")


def exporter(evenements: list[dict[str, Any]], base: str = "https://robo-scene.local/trace/") -> Graph:
    g = Graph()
    g.bind("prov", PROV)
    g.bind("rs", RS)
    B = Namespace(base)

    def agent(a: dict[str, str]) -> URIRef:
        u = B[f"agent/{a['id']}"]
        g.add((u, RDF.type, PROV.Agent))
        g.add((u, RDF.type, PROV.Person if a["type"] == "personne" else PROV.SoftwareAgent))
        g.add((u, RDFS.label, Literal(a["id"])))
        return u

    for e in evenements:
        if e["operation"] == "autre" or not e.get("cycle"):
            continue
        cyc, d, op = e["cycle"], e["donnees"], e["operation"]
        ag = agent(e["agent"])
        t = Literal(e["ts"], datatype=XSD.dateTime)
        consigne = B[f"{cyc}/consigne"]
        if op == "consigne":
            g.add((consigne, RDF.type, PROV.Entity))
            g.add((consigne, RS.texte, Literal(d.get("texte", ""))))
            g.add((consigne, PROV.wasAttributedTo, ag))
            g.add((consigne, PROV.generatedAtTime, t))
        elif op == "generation":
            act = B[f"{cyc}/generation/{e['id']}"]
            g.add((act, RDF.type, PROV.Activity))
            g.add((act, RS.operation, Literal("generation")))
            g.add((act, PROV.wasAssociatedWith, ag))
            g.add((act, PROV.used, consigne))
            g.add((act, PROV.startedAtTime, t))
            g.add((act, RS.versionModele, Literal(d["version_modele"])))
            gi = d.get("numero", 1)
            for i, texte in enumerate(d["propositions"], 1):
                p = B[f"{cyc}/G{gi}/P{i}"]
                g.add((p, RDF.type, PROV.Entity))
                g.add((p, RS.texte, Literal(texte)))
                g.add((p, PROV.wasGeneratedBy, act))
                g.add((p, PROV.wasAttributedTo, ag))
        elif op in ("selection", "transformation", "attribution") and not d.get("absence"):
            gi, pi = d.get("generation"), d.get("proposition")
            if gi is None or pi is None:
                continue
            p = B[f"{cyc}/G{gi}/P{pi}"]
            act = B[f"{cyc}/{op}/{e['id']}"]
            g.add((act, RDF.type, PROV.Activity))
            g.add((act, RS.operation, Literal(op)))
            g.add((act, PROV.wasAssociatedWith, ag))
            g.add((act, PROV.used, p))
            g.add((act, PROV.startedAtTime, t))
            if op == "selection":
                g.add((act, RS.decision, Literal(d.get("decision", ""))))
                if d.get("motif"):
                    g.add((act, RS.motif, Literal(d["motif"])))
            elif op == "transformation":
                v = B[f"{cyc}/G{gi}/P{pi}/version"]
                g.add((v, RDF.type, PROV.Entity))
                g.add((v, RS.texte, Literal(d.get("version", ""))))
                g.add((v, PROV.wasDerivedFrom, p))
                g.add((v, PROV.wasGeneratedBy, act))
                if d.get("ecart") is not None:
                    g.add((v, RS.ecart, Literal(float(d["ecart"]), datatype=XSD.decimal)))
                if e.get("reconstitue"):
                    g.add((v, RS.reconstitue, Literal(True)))
            else:
                v = B[f"{cyc}/G{gi}/P{pi}/version"]
                g.add((v, RDF.type, PROV.Entity))
                g.add((v, RS.etiquette, Literal(d["etiquette"])))
                g.add((v, RS.credit, Literal(d["credit"])))
                g.add((v, PROV.wasAttributedTo, ag))
    return g


def en_turtle(evenements: list[dict[str, Any]]) -> str:
    return exporter(evenements).serialize(format="turtle")
