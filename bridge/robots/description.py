"""Description unifiée d'un robot : la même pour tous les robots, quels que soient la marque, le langage
du pilote ou le protocole de communication.

Un robot est vu par la plateforme comme :
* une suite d'ARTICULATIONS nommées (en degrés, ou en mm pour les translations), chacune avec ses bornes
  et sa position de repos ;
* éventuellement une PROPULSION différentielle (gauche, droite, de −1 à 1) ;
* des capacités facultatives : gestes natifs nommés, voix, capteur de distance, batterie ;
* un PILOTE (adaptateur) qui traduit le langage de commande unifié (PROTOCOLE.md) dans le protocole du
  robot : ligne JSON (série, TCP, UDP, WebSocket), bus de servomoteurs Hiwonder, ROS 1 ou ROS 2 par
  rosbridge, MQTT, OSC, HTTP, SDK Reachy Mini, ou programme externe écrit dans n'importe quel langage.

Les profils se rangent dans robots/*.toml (un fichier par robot).
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Articulation:
    nom: str
    min: float
    max: float
    repos: float
    unite: str = "deg"
    id: Any = None                 # identifiant natif (n° de servo, nom de joint ROS, axe SDK…)
    zero: float | None = None      # position native correspondant à 0 (ex. 500 pas pour un servo Hiwonder)
    sens: int = 1                  # +1 ou −1 selon le montage
    pas_par_unite: float | None = None   # pas natifs par unité (défaut : selon le type de servo du pilote)
    a_verifier: bool = False       # sens ou bornes déduits, à confirmer par relevé sur le robot


@dataclass
class DescriptionRobot:
    id: str
    nom: str
    pilote: str                                    # type d'adaptateur (voir registre.TYPES)
    articulations: list[Articulation]
    connexion: dict[str, Any] = field(default_factory=dict)
    langage: str = "python"                        # langage du pilote (information ; voir sdk/)
    propulsion: bool = False
    propulsion_max: float = 0.6
    vitesse_max_deg_s: float = 90.0
    chien_de_garde_ms: int = 500
    batterie_min_v: float | None = None
    rayon_exclusion_m: float | None = None         # plan de prévention P2.1 (AiNex : 1,2 m)
    capacites: list[str] = field(default_factory=list)
    gestes_natifs: list[str] = field(default_factory=list)
    simulation: bool = False                       # True : robot simulé (aucun matériel)
    actif: bool = True                             # False : profil d'exemple, non connecté au démarrage
    bibliotheque: str = "json"                     # json (sequences/) ou p2 (YAML du Reachy Mini)
    gestes_dynamiques: list[str] = field(default_factory=list)   # gestes natifs qui déplacent le robot (marche…)
    jumeau: dict[str, Any] = field(default_factory=dict)          # correspondance avec le robot virtuel humanoïde
    camera: dict[str, Any] = field(default_factory=dict)          # flux vidéo du robot (mjpeg, whep)
    libelles_gestes: dict[str, str] = field(default_factory=dict) # libellés français des gestes natifs
    sequences: str | None = None                   # dossier de séquences partagé (sinon : l'identifiant du robot)
    notes: str = ""
    source: str = ""

    @property
    def noms(self) -> list[str]:
        return [a.nom for a in self.articulations]

    @property
    def min_deg(self) -> list[float]:
        return [a.min for a in self.articulations]

    @property
    def max_deg(self) -> list[float]:
        return [a.max for a in self.articulations]

    @property
    def repos(self) -> list[float]:
        return [a.repos for a in self.articulations]

    def resume(self) -> dict[str, Any]:
        return {"id": self.id, "nom": self.nom, "pilote": self.pilote, "langage": self.langage,
                "articulations": len(self.articulations), "propulsion": self.propulsion,
                "simulation": self.simulation, "actif": self.actif, "capacites": self.capacites, "gestes_natifs": self.gestes_natifs,
                "rayon_exclusion_m": self.rayon_exclusion_m, "notes": self.notes,
                "gestes_dynamiques": self.gestes_dynamiques}


def depuis_dict(d: dict[str, Any], source: str = "") -> DescriptionRobot:
    r = d["robot"]
    arts = [Articulation(**{k: v for k, v in a.items() if k in Articulation.__dataclass_fields__})
            for a in d.get("articulations", [])]
    if not arts:
        raise ValueError(f"{source or r.get('id')} : aucune articulation décrite")
    for a in arts:
        if not a.min <= a.repos <= a.max:
            raise ValueError(f"{r['id']} : repos de « {a.nom} » hors de ses bornes")
    sec = d.get("securite", {})
    return DescriptionRobot(
        id=r["id"], nom=r.get("nom", r["id"]), pilote=r["pilote"], articulations=arts,
        connexion=dict(d.get("connexion", {})), langage=r.get("langage", "python"),
        propulsion=bool(d.get("propulsion", {}).get("active", False)),
        propulsion_max=float(sec.get("propulsion_max", 0.6)),
        vitesse_max_deg_s=float(sec.get("vitesse_max_deg_s", 90.0)),
        chien_de_garde_ms=int(sec.get("chien_de_garde_ms", 500)),
        batterie_min_v=sec.get("batterie_min_v"), rayon_exclusion_m=sec.get("rayon_exclusion_m"),
        capacites=list(r.get("capacites", [])), gestes_natifs=list(r.get("gestes_natifs", [])),
        simulation=bool(r.get("simulation", False)), actif=bool(r.get("actif", True)),
        bibliotheque=r.get("bibliotheque", "json"), notes=r.get("notes", ""), source=source,
        gestes_dynamiques=list(r.get("gestes_dynamiques", [])), jumeau=dict(d.get("jumeau", {})),
        camera=dict(d.get("camera", {})), libelles_gestes=dict(d.get("libelles_gestes", {})),
        sequences=r.get("sequences"))


def charger(chemin: str | Path) -> DescriptionRobot:
    p = Path(chemin)
    with open(p, "rb") as f:
        return depuis_dict(tomllib.load(f), str(p))


def depuis_config_console(cfg: dict[str, Any]) -> DescriptionRobot:
    """Robot historique de la console (section [robot] de config.toml) — ESP32 à ligne JSON."""
    r, art, sec = cfg["robot"], cfg["robot"]["articulations"], cfg["securite"]
    arts = [Articulation(n, float(lo), float(hi), float(rp))
            for n, lo, hi, rp in zip(art["noms"], art["min_deg"], art["max_deg"], art["repos"])]
    t = r.get("transport", "sim")
    connexion = {"mode": t, "port_serie": r.get("port_serie"), "debit": r.get("debit", 115200),
                 "hote": r.get("hote_tcp"), "port": r.get("port_tcp")}
    return DescriptionRobot(
        id=r.get("id", "robo-scene-01"), nom=r.get("nom", "ROBO-SCENE-01"), pilote="ligne_json", articulations=arts,
        connexion=connexion, langage="arduino", propulsion=bool(r["propulsion"]["active"]),
        propulsion_max=float(sec["propulsion_max"]), vitesse_max_deg_s=float(sec["vitesse_max_deg_s"]),
        chien_de_garde_ms=int(sec["chien_de_garde_ms"]), batterie_min_v=sec.get("batterie_min_v"),
        capacites=["distance", "batterie"], simulation=(t == "sim"), source="config.toml [robot]",
        notes="Robot maison à microcontrôleur ESP32 (micrologiciel firmware/esp32_robot).")


def charger_profils(dossier: str | Path) -> list[DescriptionRobot]:
    return [charger(p) for p in sorted(Path(dossier).glob("*.toml"))]
