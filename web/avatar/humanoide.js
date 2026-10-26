/* Robo-Scène — corps et visage du robot virtuel.
   Humanoïde masculin entièrement procédural (aucun modèle tiers) : squelette hiérarchique de
   groupes three.js dont les pivots sont placés aux articulations, volumes simples (capsules,
   ellipsoïdes) et visage animé par unités d'action. Le parti pris stylisé, plutôt que
   photoréaliste, est volontaire (voir le guide : vallée de l'étrange). */
import * as THREE from "three";
import { DOIGTS, CAPTEURS, PAUME, OBJETS, cinematique, anglesPosture, poseObjet } from "./mains.js";

const R = THREE.MathUtils.degToRad;
const lerp = THREE.MathUtils.lerp;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const REPOS_BRAS = 7;          // abduction structurelle : les bras pendent sans traverser le thorax
const REPOS_COUDE = 6;
// Segments de la jambe (repère de l'échelle, en m) : hanche → genou, genou → cheville, cheville → semelle
const CUISSE = 0.43, JAMBE = 0.41, SEMELLE = 0.08;
const CUISSE_STYLISE = CUISSE, JAMBE_STYLISE = JAMBE, SEMELLE_STYLISE = SEMELLE;
const TOLERANCE_SOL = 0.002;
/* Repères du visage (m), dans le repère du groupe « visage » (origine au centre de la tête ; x vers la gauche du
   personnage, y vers le haut, z vers l'avant), relevés sur la géométrie ci-dessous (crâne, yeux, nez, menton,
   oreilles). Un contact vise un repère plus un décalage, qui laisse l'épaisseur de la main hors de la peau. */
export const REPERES_VISAGE = {
  bouche: [0, -0.048, 0.093], levres: [0, -0.045, 0.1], menton: [0, -0.08, 0.085], menton_dessous: [0, -0.1, 0.06],
  nez: [0, -0.024, 0.113], front: [0, 0.055, 0.092], sourcil_g: [0.045, 0.035, 0.088], sourcil_d: [-0.045, 0.035, 0.088],
  oeil_g: [0.032, 0.012, 0.1], oeil_d: [-0.032, 0.012, 0.1], tempe_g: [0.078, 0.035, 0.045], tempe_d: [-0.078, 0.035, 0.045],
  oreille_g: [0.1, 0, -0.006], oreille_d: [-0.1, 0, -0.006], joue_g: [0.06, -0.03, 0.075], joue_d: [-0.06, -0.03, 0.075],
  crane_g: [0.05, 0.1, 0], crane_d: [-0.05, 0.1, 0],
};
/* Repères du corps propre (25 oct. 2026), dans le repère du groupe « poitrine » (mêmes axes), relevés sur
   l'ellipsoïde du thorax et la carrure : la main s'y pose comme au visage (cœur, sternum, épaules). */
export const REPERES_CORPS = {
  coeur: [0.065, 0.125, 0.106], sternum: [0, 0.12, 0.113], epaule_g: [0.15, 0.24, 0.048], epaule_d: [-0.15, 0.24, 0.048],
};

export const PEAUX = { "très claire": "#f0d2bd", claire: "#e2b794", mate: "#c99a78", olive: "#ad875c", brune: "#8a5a3c", "foncée": "#5c3925" };
/* Échelle de tons de peau de Monk (Ellis Monk ; Google, 2022 ; CC BY 4.0), Monk 01 à Monk 10. */
PEAUX["Monk 01"] = "#f6ede4";
PEAUX["Monk 02"] = "#f3e7db";
PEAUX["Monk 03"] = "#f7ead0";
PEAUX["Monk 04"] = "#eadaba";
PEAUX["Monk 05"] = "#d7bd96";
PEAUX["Monk 06"] = "#a07e56";
PEAUX["Monk 07"] = "#825c43";
PEAUX["Monk 08"] = "#604134";
PEAUX["Monk 09"] = "#3a312a";
PEAUX["Monk 10"] = "#292420";
export const YEUX = { bleu: "#3d6ea8", vert: "#4f7d4a", brun: "#4a3220", noir: "#1e1612", gris: "#7d8790", noisette: "#7a5a2e" };
export const APPARENCE_DEFAUT = {
  taille: 178, carrure: 1, corpulence: 1, age: 40, cheveux: "court", couleur_cheveux: "châtain", barbe: "courte",
  moustache: false, manches: "longues", peau: "mate", yeux: "brun", haut: "bleu marine", bas: "gris", chaussures: "noir",
  // habillage (21 oct. 2026) : matière des vêtements, chapeau, cou, cape, jupe ou robe, gants
  matiere: "tissu", chapeau: "aucun", couleur_chapeau: "noir", cou: "aucun", cape: "aucune", jupe: "aucune", gants: false,
  accessoire: "bordeaux", habillage: "repetition",
  // lutteur (25 oct. 2026) : longueur du bas (pantalon ou cuissard) et chaussures montant au-dessus de la cheville
  coupe_bas: "pantalon", chaussures_montantes: false, modele_chaussures: "uni", modele_maillot: "uni",
  style: "stylisé",                                   // « humain » : corps humain issu de MakeHuman (humain.js)
};
/* Rendu des matières (MeshStandardMaterial : rugosité, métallicité ; la scène n'a pas de carte d'environnement,
   d'où une métallicité modérée pour que le métal reste lisible sous les projecteurs). */
export const MATIERES = {
  tissu: { haut: [0.86, 0], bas: [0.9, 0] }, satin: { haut: [0.36, 0.06], bas: [0.4, 0.06] },
  cuir: { haut: [0.5, 0.02], bas: [0.55, 0.02] }, "métal": { haut: [0.3, 0.6], bas: [0.32, 0.6] },
};
/* Champs qu'un habillage remplace ; le corps (taille, âge, peau, cheveux, barbe, yeux) n'est jamais touché. */
export const CHAMPS_HABILLAGE = ["haut", "bas", "chaussures", "manches", "matiere", "chapeau", "couleur_chapeau", "cou", "cape",
  "jupe", "gants", "accessoire", "coupe_bas", "chaussures_montantes", "modele_chaussures", "modele_maillot"];

function std(color, roughness = 0.75, extra = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness, metalness: 0, ...extra });
}
function maille(geo, mat, zone, ombre = true) {
  const m = new THREE.Mesh(geo, mat);
  m.castShadow = ombre; m.receiveShadow = true;
  if (zone) m.userData.zone = zone;
  return m;
}
const capsule = (r, l, mat, zone) => maille(new THREE.CapsuleGeometry(r, l, 6, 14), mat, zone);
const ellipsoide = (r, mat, zone, s = [1, 1, 1], seg = 28) => {
  const m = maille(new THREE.SphereGeometry(r, seg, Math.round(seg * 0.7)), mat, zone);
  m.scale.set(...s); return m;
};
function groupe(nom, parent, x = 0, y = 0, z = 0) {
  const g = new THREE.Group(); g.name = nom; g.position.set(x, y, z); parent.add(g); return g;
}

/* ══════════════════════ Visage ══════════════════════ */
class Visage {
  constructor(tete, mat) {
    this.mat = mat;
    const f = (this.g = groupe("visage", tete, 0, 0.085, 0));       // origine : centre de la tête
    this.crane = ellipsoide(0.1, mat.peau, "tete", [0.9, 1.12, 1.0], 40); f.add(this.crane);
    // mâchoire (pivot près de l'articulation temporo-mandibulaire)
    this.machoire = groupe("machoire", f, 0, -0.012, -0.02);
    this.menton = ellipsoide(0.07, mat.peau, "tete", [1.04, 0.8, 1.0]); this.menton.position.set(0, -0.048, 0.038); this.machoire.add(this.menton);
    // nez
    const arete = capsule(0.0072, 0.026, mat.peau, "tete"); arete.position.set(0, -0.004, 0.097); arete.rotation.x = -0.3; f.add(arete);
    this.nez = ellipsoide(0.0098, mat.peau, "tete", [1, 0.92, 1]); this.nez.position.set(0, -0.024, 0.103); f.add(this.nez);
    this.ailes = [-1, 1].map((s) => { const a = ellipsoide(0.0066, mat.peau, "tete"); a.position.set(0.0098 * s, -0.028, 0.096); f.add(a); return a; });
    // oreilles et pommettes
    for (const s of [-1, 1]) { const o = ellipsoide(0.028, mat.peau, "tete", [0.35, 1, 0.7]); o.position.set(0.089 * s, 0.0, -0.006); f.add(o); }
    this.pommettes = [-1, 1].map((s) => { const p = ellipsoide(0.019, mat.peau, "tete", [1.15, 0.75, 0.5]); p.position.set(0.046 * s, -0.02, 0.07); f.add(p); return p; });
    // yeux : globe, iris, pupille ; paupières hémisphériques
    this.yeux = [1, -1].map((s) => {                                  // indice 0 = œil gauche (x > 0)
      const pivot = groupe("oeil", f, 0.032 * s, 0.012, 0.0855);
      const globe = ellipsoide(0.0125, mat.blanc, "tete", [1, 1, 1], 20); pivot.add(globe);
      const iris = new THREE.Mesh(new THREE.CircleGeometry(0.0058, 24), mat.iris); iris.position.z = 0.0122; pivot.add(iris);
      const pupille = new THREE.Mesh(new THREE.CircleGeometry(0.0027, 18), mat.pupille); pupille.position.z = 0.0124; pivot.add(pupille);
      const reflet = new THREE.Mesh(new THREE.CircleGeometry(0.0011, 10), mat.reflet); reflet.position.set(0.0022, 0.0022, 0.0126); pivot.add(reflet);
      const haut = new THREE.Mesh(new THREE.SphereGeometry(0.0137, 24, 10, 0, Math.PI * 2, 0, Math.PI / 2), mat.paupiere);
      const bas = new THREE.Mesh(new THREE.SphereGeometry(0.0134, 24, 10, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2), mat.paupiere);
      const socle = groupe("paupieres", f, 0.032 * s, 0.012, 0.0855); socle.add(haut); socle.add(bas);
      const cils = new THREE.Mesh(new THREE.TorusGeometry(0.0137, 0.0009, 4, 24, Math.PI), mat.cils); cils.rotation.x = Math.PI / 2; haut.add(cils);
      return { pivot, haut, bas, cils, s };
    });
    // sourcils, lèvres, moustache : tubes recalculés quand les paramètres changent
    this.sourcils = [null, null];
    this.levres = { haut: null, bas: null };
    this.moustache = null;
    this.interieur = new THREE.Mesh(new THREE.CircleGeometry(1, 28), mat.bouche); f.add(this.interieur);
    this.dents = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), mat.dents); f.add(this.dents);
    this.dentsBas = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), mat.dents); f.add(this.dentsBas);
    // cheveux et barbe (géométries remplacées selon l'apparence)
    this.cheveux = null; this.barbe = null;
    this.avecMoustache = false;
    this.empreinte = "";
    this.maj({}, { yaw: 0, pitch: 0 });
  }
  tube(points, rayon, mat, ancien) {
    if (ancien) { ancien.geometry.dispose(); ancien.geometry = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), 18, rayon, 6, false); return ancien; }
    const m = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), 18, rayon, 6, false), mat);
    m.castShadow = false; this.g.add(m); return m;
  }
  coiffure(style, barbe, moustache) {
    const f = this.g, M = this.mat;
    if (this.cheveux) { f.remove(this.cheveux); this.cheveux.geometry.dispose(); this.cheveux = null; }
    if (style !== "chauve") {
      const long = style === "mi-long";
      const geo = new THREE.SphereGeometry(1, 40, 24, 0, Math.PI * 2, 0, long ? 1.95 : 1.28);
      const m = maille(geo, style === "rasé" ? M.crane : M.cheveux, "tete");
      const e = style === "rasé" ? 1.012 : 1.06;
      m.scale.set(0.09 * e, 0.112 * e, 0.1 * e);
      m.rotation.x = long ? -0.75 : -0.42; m.position.set(0, style === "rasé" ? 0.002 : 0.006, -0.006);
      f.add(m); this.cheveux = m;
    }
    if (this.barbe) { this.machoire.remove(this.barbe); this.barbe.geometry.dispose(); this.barbe = null; }
    if (barbe !== "aucune") {
      const plein = barbe === "pleine";
      const geo = new THREE.SphereGeometry(1, 32, 18, 0, Math.PI * 2, Math.PI * (plein ? 0.545 : 0.56), Math.PI * (plein ? 0.455 : 0.44));
      const m = maille(geo, M.barbe, "tete");
      m.scale.set(0.074 * (plein ? 1.08 : 1.03), 0.058 * (plein ? 1.3 : 1.04), 0.072 * (plein ? 1.08 : 1.04));
      m.position.set(0, -0.048, 0.038);
      this.machoire.add(m); this.barbe = m;
    }
    this.avecMoustache = !!moustache;
    if (this.moustache) this.moustache.visible = this.avecMoustache;
    this.empreinte = "";
  }
  /* au : unités d'action lissées (0 à 1) ; bouche : contribution de la parole ; regard : angles des yeux */
  maj(au, regard, bouche = { jaw: 0, pucker: 0, stretch: 0, press: 0 }) {
    const A = (k) => au[k] || 0;
    const cote = (k, s) => Math.max(A(k), A(`${k}_${s}`));
    const yeux = this.yeux;
    // regard et paupières
    for (const o of yeux) {
      const s = o.s > 0 ? "g" : "d";
      o.pivot.rotation.set(-regard.pitch, regard.yaw, 0);
      const fermeture = clamp(Math.max(A("au43"), A("clignement"), A(`au46_${s}`)) + 0.28 * cote("au7", s) + 0.18 * cote("au6", s) - 0.05 * A("au5"), 0, 1);
      const suivi = clamp(regard.pitch * 0.6, -0.25, 0.3);           // la paupière suit le regard vertical
      o.haut.rotation.x = lerp(-0.42 - 0.38 * A("au5") - suivi, 1.25, fermeture);
      o.bas.rotation.x = clamp(0.42 - 0.28 * cote("au7", s) - 0.22 * cote("au6", s) - 0.18 * fermeture - suivi * 0.4, 0.02, 0.6);
      o.haut.rotation.y = o.bas.rotation.y = regard.yaw * 0.25;
    }
    // pommettes et nez
    this.pommettes.forEach((p, i) => { const s = i === 0 ? "d" : "g"; p.position.y = -0.02 + 0.0045 * cote("au6", s) + 0.003 * cote("au12", s); });
    this.nez.position.y = -0.026 + 0.0025 * A("au9");
    this.ailes.forEach((a) => { a.position.y = -0.03 + 0.003 * A("au9") + 0.0015 * A("au10"); a.scale.setScalar(1 + 0.18 * A("au9")); });
    // empreinte : on ne recalcule les tubes que si un paramètre a bougé
    const cle = ["au1", "au2", "au4", "au9", "au10", "au12", "au14", "au15", "au16", "au17", "au18", "au20", "au23", "au24", "au25", "au26",
      "au1_g", "au1_d", "au2_g", "au2_d", "au12_g", "au12_d", "au14_g", "au14_d", "au15_g", "au15_d"]
      .map((k) => Math.round(A(k) * 60)).join(",") + `|${Math.round(bouche.jaw * 60)},${Math.round(bouche.pucker * 60)},${Math.round(bouche.stretch * 60)},${Math.round(bouche.press * 60)}`;
    if (cle === this.empreinte) return;
    this.empreinte = cle;
    // sourcils
    [1, -1].forEach((s, i) => {
      const c = s > 0 ? "g" : "d";
      const au1 = cote("au1", c), au2 = cote("au2", c), au4 = A("au4"), au9 = A("au9");
      const yi = 0.036 + 0.008 * au1 - 0.0065 * au4 - 0.003 * au9;
      const ym = 0.040 + 0.004 * au1 + 0.004 * au2 - 0.004 * au4 - 0.002 * au9;
      const yo = 0.036 + 0.009 * au2 - 0.002 * au4;
      const xi = (0.012 - 0.0035 * au4) * s;
      const pts = [new THREE.Vector3(xi, yi, 0.097), new THREE.Vector3(0.032 * s, ym, 0.0925), new THREE.Vector3(0.052 * s, yo, 0.082)];
      this.sourcils[i] = this.tube(pts, 0.0034, this.mat.sourcils, this.sourcils[i]);
    });
    // lèvres
    const jaw = clamp(Math.max(A("au26") * 0.75 + A("au25") * 0.12, bouche.jaw) * (1 - 0.7 * Math.max(A("au24"), bouche.press)), 0, 1);
    const pucker = clamp(A("au18") + bouche.pucker, 0, 1);
    const stretch = clamp(A("au20") + bouche.stretch, 0, 1);
    const press = clamp(Math.max(A("au23"), A("au24"), bouche.press), 0, 1);
    const y0 = -0.053, z0 = 0.093, w0 = 0.0235 * (1 - 0.32 * pucker);
    const coin = (s) => {
      const c = s > 0 ? "g" : "d";
      const sm = cote("au12", c), fr = cote("au15", c), dim = cote("au14", c);
      return new THREE.Vector3((w0 + 0.006 * sm + 0.006 * stretch + 0.002 * dim) * s,
        y0 + 0.0085 * sm - 0.007 * fr - 0.002 * stretch - 0.004 * jaw + 0.0015 * dim,
        z0 - 0.006 - 0.004 * sm - 0.003 * dim + 0.003 * pucker);
    };
    const cg = coin(1), cd = coin(-1);
    const hu = 0.0046 + 0.004 * A("au10") + 0.002 * pucker + 0.003 * jaw;
    const hb = 0.0042 + 0.016 * jaw + 0.004 * A("au16") - 0.003 * A("au17") + 0.002 * pucker;
    const zf = z0 + 0.006 * pucker - 0.002 * press;
    const haut = [cd, new THREE.Vector3(-w0 * 0.5, y0 + hu * 0.95, zf - 0.0015), new THREE.Vector3(0, y0 + hu, zf), new THREE.Vector3(w0 * 0.5, y0 + hu * 0.95, zf - 0.0015), cg];
    const bas = [cd, new THREE.Vector3(-w0 * 0.5, y0 - hb * 0.9, zf - 0.002 - 0.004 * jaw), new THREE.Vector3(0, y0 - hb, zf - 0.001 - 0.005 * jaw), new THREE.Vector3(w0 * 0.5, y0 - hb * 0.9, zf - 0.002 - 0.004 * jaw), cg];
    const epais = 1 - 0.45 * press;
    this.levres.haut = this.tube(haut, 0.0034 * epais, this.mat.levres, this.levres.haut);
    this.levres.bas = this.tube(bas, 0.0044 * epais, this.mat.levres, this.levres.bas);
    const ouvert = Math.max(0, (hu + hb) - 0.0085);
    this.interieur.visible = ouvert > 0.0015;
    this.interieur.position.set(0, y0 + (hu - hb) / 2, zf - 0.0065);
    this.interieur.scale.set((cg.x - cd.x) * 0.46, Math.max(0.001, ouvert * 0.55), 1);
    this.dents.visible = this.dentsBas.visible = ouvert > 0.003;
    this.dents.position.set(0, y0 + hu - 0.0035, zf - 0.0045); this.dents.scale.set((cg.x - cd.x) * 0.62, 0.0045, 1);
    this.dentsBas.position.set(0, y0 - hb + 0.0035, zf - 0.006); this.dentsBas.scale.set((cg.x - cd.x) * 0.5, 0.0035, 1);
    this.machoire.rotation.x = jaw * 0.24;
    // moustache : suit la lèvre supérieure
    const mpts = haut.map((p) => new THREE.Vector3(p.x * 1.08, p.y + 0.0072, p.z + 0.0008));
    this.moustache = this.tube(mpts, 0.0042, this.mat.barbe, this.moustache);
    this.moustache.visible = this.avecMoustache;
  }
}

/* ══════════════════════ Corps ══════════════════════ */
export class Humanoide {
  constructor(schema) {
    this.schema = schema;
    this.mat = {
      peau: std("#c99a78", 0.62), crane: std("#9d7a62", 0.8), haut: std("#1f2b4a", 0.86), bas: std("#7d8086", 0.9),
      chaussures: std("#1b1b1d", 0.45), cheveux: std("#6b4a2f", 0.92), barbe: std("#5a3f28", 0.95), sourcils: std("#3a2a1c", 0.95),
      levres: std("#a2655a", 0.5), blanc: std("#f2efe8", 0.25), iris: std("#4a3220", 0.35), pupille: std("#070707", 0.2),
      reflet: new THREE.MeshBasicMaterial({ color: "#ffffff" }), paupiere: std("#c09072", 0.65), cils: std("#1a1410", 0.9),
      bouche: std("#3b1515", 0.9), dents: std("#efeadf", 0.3), ceinture: std("#3b2618", 0.5), bois: std("#6b4a2e", 0.7),
      mains: std("#c99a78", 0.62), chapeau: std("#1b1b1d", 0.6), accessoire: std("#6d1f2a", 0.7, { side: THREE.DoubleSide }),
      jupe: std("#7d8086", 0.9, { side: THREE.DoubleSide }), or: std("#c9a227", 0.3, { metalness: 0.7 }),
    };
    this.os = {};
    this.zones = [];
    this.racine = new THREE.Group(); this.racine.name = "robot-virtuel";
    this.construire();
    this.apparence = { ...APPARENCE_DEFAUT };
    this.appliquerApparence(this.apparence);
  }
  construire() {
    const M = this.mat, O = this.os;
    const echelle = (O.echelle = groupe("echelle", this.racine));
    const bassin = (O.bassin = groupe("bassin", echelle, 0, 0.98, 0));
    O.pelvis = ellipsoide(0.1, M.bas, "bassin", [1.62, 1.05, 1.08]); bassin.add(O.pelvis);
    O.ceinture = maille(new THREE.TorusGeometry(0.152, 0.012, 8, 40), M.ceinture, "bassin"); O.ceinture.rotation.x = Math.PI / 2; O.ceinture.scale.set(1.05, 0.7, 1); O.ceinture.position.y = 0.072; bassin.add(O.ceinture);
    const lomb = (O.lombaires = groupe("lombaires", bassin, 0, 0.07, 0));
    O.abdomen = capsule(0.118, 0.1, M.haut, "tronc"); O.abdomen.position.y = 0.065; O.abdomen.scale.set(1.24, 1, 0.86); lomb.add(O.abdomen);
    const poitrine = (O.poitrine = groupe("poitrine", lomb, 0, 0.17, 0));
    O.thorax = ellipsoide(0.1, M.haut, "tronc", [1.85, 1.72, 1.13]); O.thorax.position.y = 0.115; poitrine.add(O.thorax);
    O.carrure = capsule(0.056, 0.25, M.haut, "tronc"); O.carrure.rotation.z = Math.PI / 2; O.carrure.position.y = 0.225; O.carrure.scale.set(1, 1, 0.85); poitrine.add(O.carrure);
    O.col = maille(new THREE.TorusGeometry(0.052, 0.011, 8, 24), M.haut, "tronc"); O.col.rotation.x = Math.PI / 2; O.col.position.y = 0.285; poitrine.add(O.col);
    const cou = (O.cou = groupe("cou", poitrine, 0, 0.285, 0));
    const neck = maille(new THREE.CylinderGeometry(0.046, 0.05, 0.11, 18), M.peau, "tete"); neck.position.y = 0.045; cou.add(neck);
    O.tete = groupe("tete", cou, 0, 0.085, 0.004);
    this.visage = new Visage(O.tete, M);
    for (const [s, x] of [["g", 1], ["d", -1]]) {
      const clav = (O[`clav_${s}`] = groupe(`clav_${s}`, poitrine, 0.04 * x, 0.22, 0));
      const ep = (O[`epaule_${s}`] = groupe(`epaule_${s}`, clav, 0.165 * x, 0, 0));
      ep.rotation.order = "ZXY";
      const deltoide = ellipsoide(0.05, M.haut, `bras_${s}`, [1, 1.1, 1]); ep.add(deltoide); O[`deltoide_${s}`] = deltoide;
      const bras = capsule(0.047, 0.2, M.haut, `bras_${s}`); bras.position.y = -0.14; ep.add(bras); O[`bras_${s}`] = bras;
      const coude = (O[`coude_${s}`] = groupe(`coude_${s}`, ep, 0, -0.29, 0));
      const articCoude = ellipsoide(0.043, M.haut, `avantbras_${s}`); coude.add(articCoude); O[`articCoude_${s}`] = articCoude;
      const avb = capsule(0.039, 0.19, M.haut, `avantbras_${s}`); avb.position.y = -0.12; coude.add(avb); O[`avantbras_${s}`] = avb;
      const manchette = maille(new THREE.CylinderGeometry(0.041, 0.041, 0.02, 16), M.haut, `avantbras_${s}`); manchette.position.y = -0.225; coude.add(manchette); O[`manchette_${s}`] = manchette;
      const poignet = (O[`poignet_${s}`] = groupe(`poignet_${s}`, coude, 0, -0.255, 0));
      // rotation de l'avant-bras d'abord (axe du bras), puis flexion, puis inclinaison, dans le repère de la main
      poignet.rotation.order = "YZX";
      this.construireMain(poignet, s, x);
      const hanche = (O[`hanche_${s}`] = groupe(`hanche_${s}`, bassin, 0.092 * x, -0.06, 0));
      hanche.rotation.order = "ZXY";
      const cuisse = capsule(0.068, 0.3, M.bas, `cuisse_${s}`); cuisse.position.y = -0.2; hanche.add(cuisse); O[`cuisse_${s}`] = cuisse;
      const genou = (O[`genou_${s}`] = groupe(`genou_${s}`, hanche, 0, -0.43, 0));
      const rotule = ellipsoide(0.052, M.bas, `tibia_${s}`); genou.add(rotule); O[`rotule_${s}`] = rotule;
      const tibia = capsule(0.05, 0.31, M.bas, `tibia_${s}`); tibia.position.y = -0.2; genou.add(tibia); O[`tibia_${s}`] = tibia;
      const cheville = (O[`cheville_${s}`] = groupe(`cheville_${s}`, genou, 0, -0.41, 0));
      const pied = capsule(0.046, 0.16, M.chaussures, `pied_${s}`); pied.rotation.x = Math.PI / 2; pied.position.set(0, -0.036, 0.055); pied.scale.set(1.05, 1, 0.82); cheville.add(pied);
      const talon = ellipsoide(0.045, M.chaussures, `pied_${s}`, [1, 0.8, 1]); talon.position.set(0, -0.035, -0.02); cheville.add(talon);
      // points de contact de la semelle (talon, pointe), pour l'ancrage au sol
      O[`contact_talon_${s}`] = groupe(`contact_talon_${s}`, cheville, 0, -SEMELLE, -0.03);
      O[`contact_pointe_${s}`] = groupe(`contact_pointe_${s}`, cheville, 0, -SEMELLE, 0.15);
    }
    // tabouret (visible quand le personnage s'assied)
    const tab = (O.tabouret = new THREE.Group());
    const assise = maille(new THREE.CylinderGeometry(0.2, 0.2, 0.04, 28), M.bois); assise.position.y = 0.40; tab.add(assise);
    for (let i = 0; i < 3; i++) { const p = maille(new THREE.CylinderGeometry(0.016, 0.02, 0.4, 8), M.bois); const a = i * Math.PI * 2 / 3; p.position.set(Math.cos(a) * 0.14, 0.2, Math.sin(a) * 0.14); p.rotation.set(Math.sin(a) * 0.12, 0, -Math.cos(a) * 0.12); tab.add(p); }
    tab.position.set(0, 0, -0.06); tab.visible = false; this.racine.add(tab);
    this.construireAccessoires();
    this.racine.traverse((o) => { if (o.isMesh && o.userData.zone) this.zones.push(o); });
  }
  /* Mains à cinq doigts (25 oct. 2026) : 15 phalanges (pouce : métacarpien, phalanges proximale et distale)
     dont la position vient, à chaque image, de la cinématique directe de mains.js — la même que celle des
     contacts et des forces. Repère canonique (u palmaire, d distal, w radial) → repère de la main :
     (−x·u, −d, w), x = 1 à gauche et −1 à droite (main droite : image miroir). */
  construireMain(poignet, s, x) {
    const M = this.mat;
    const main = groupe(`main_${s}`, poignet);
    const paume = maille(new THREE.BoxGeometry(0.026, 0.085, 0.074), M.mains, `main_${s}`); paume.position.y = -0.045; main.add(paume);
    const arrondi = ellipsoide(0.037, M.mains, `main_${s}`, [0.38, 1.18, 1.02]); arrondi.position.y = -0.045; main.add(arrondi);
    GEO_MAIN.cyl = GEO_MAIN.cyl || new THREE.CylinderGeometry(1, 1, 1, 12, 1, true);
    GEO_MAIN.sph = GEO_MAIN.sph || new THREE.SphereGeometry(1, 12, 10);
    const R = { main, x, doigts: {}, coussins: {}, objet: null, cleObjet: null, carte: true };
    for (const d of DOIGTS) {
      const segs = [0, 1, 2].map(() => { const m = maille(GEO_MAIN.cyl, M.mains, `main_${s}`); main.add(m); return m; });
      const arts = [0, 1, 2, 3].map(() => { const m = maille(GEO_MAIN.sph, M.mains, `main_${s}`); main.add(m); return m; });
      R.doigts[d] = { segs, arts };
    }
    // coussinets tactiles : visibles au contact, couleur selon la pression (carte de chaleur)
    for (const c of CAPTEURS) {
      const m = new THREE.Mesh(GEO_MAIN.sph, new THREE.MeshBasicMaterial({ color: "#3fbf6f", transparent: true, opacity: 0.9, depthWrite: false }));
      m.visible = false; m.renderOrder = 2; m.name = `capteur_${c.id}_${s}`; main.add(m); R.coussins[c.id] = m;
    }
    (this.mainsRendu = this.mainsRendu || {})[s] = R;
    this.poserMain(s, anglesPosture("repos"), null);
  }

  /* Angles des doigts (degrés, noms de mains.js) → phalanges ; état de la main (prise, capteurs) → objet tenu
     et carte tactile. */
  poserMain(s, q, etat) {
    (this.anglesMains = this.anglesMains || {})[s] = q;                 // repris par le corps humain (phalanges)
    const R = this.mainsRendu[s], x = R.x, Y = new THREE.Vector3(0, 1, 0);
    const loc = (p) => new THREE.Vector3(-x * p[0], -p[1], p[2]);
    const geo = {};
    for (const d of DOIGTS) {
      const { points, reperes } = cinematique(d, q);
      const P = points.map(loc), r0 = d === "pouce" ? 0.0098 : d === "auriculaire" ? 0.0074 : 0.0082;
      const F = R.doigts[d];
      for (let i = 0; i < 3; i++) {
        const a = P[i], b = P[i + 1], dir = b.clone().sub(a), L = dir.length() || 1e-6;
        const r = d === "pouce" && i === 0 ? 0.0125 : r0 * (1 - 0.08 * i);
        const seg = F.segs[i];
        seg.position.copy(a).add(b).multiplyScalar(0.5);
        seg.quaternion.setFromUnitVectors(Y, dir.multiplyScalar(1 / L));
        seg.scale.set(r, L, r);
        F.arts[i].position.copy(a); F.arts[i].scale.setScalar(r * 1.04);
      }
      F.arts[3].position.copy(P[3]); F.arts[3].scale.setScalar(r0 * 0.84);
      geo[d] = { points, reperes };
    }
    // carte tactile
    for (const c of CAPTEURS) {
      const m = R.coussins[c.id], cap = etat?.capteurs?.[c.id];
      const actif = R.carte && cap && cap.contact && cap.force > 0.005;
      m.visible = !!actif;
      if (!actif) continue;
      let p, n, taille;
      const colonne = (Rm, j) => [Rm[0][j], Rm[1][j], Rm[2][j]];
      if (c.id === "paume") { p = [PAUME.epaisseur / 2 + 0.0008, 0.05, 0]; n = [1, 0, 0]; taille = [0.02, 0.0016, 0.024]; }
      else {
        const g = geo[c.doigt], seg = c.segment, u = colonne(g.reperes[seg], 0), dd = colonne(g.reperes[seg], 1);
        const base = seg === 2 ? g.points[3].map((v, i) => v - dd[i] * 0.008) : g.points[1].map((v, i) => (v + g.points[2][i]) / 2);
        const rr = c.doigt === "pouce" ? 0.0085 : 0.0072;
        p = base.map((v, i) => v + u[i] * rr); n = u; taille = [0.0062, 0.0014, 0.0068];
      }
      m.position.copy(loc(p));
      m.quaternion.setFromUnitVectors(Y, loc(n).normalize());
      m.scale.set(...taille);
      m.material.color.copy(couleurPression(cap.pression / 1000));
    }
    // objet tenu
    const prise = etat?.prise;
    const cle = prise && !prise.chute ? `${prise.objet}/${prise.nom}` : null;
    if (cle !== R.cleObjet) {
      if (R.objet) {
        const tombe = R.objet.userData.tombe && !(etat?.dernierLacher?.poser && etat.dernierLacher.objet === R.objet.userData.nom);
        if (tombe && this.racine.parent) { this.racine.parent.attach(R.objet); this.chutes = (this.chutes || []).filter((c) => c.nom !== R.objet.userData.nom); this.chutes.push({ g: R.objet, v: 0, nom: R.objet.userData.nom }); }
        else R.objet.removeFromParent();
        R.objet = null;
      }
      if (cle) {
        // l'objet retombé au sol est ramassé
        for (const c of this.chutes || []) if (c.nom === prise.objet) c.g.removeFromParent();
        this.chutes = (this.chutes || []).filter((c) => c.nom !== prise.objet);
        const obj = OBJETS[prise.objet], pose = poseObjet(prise.nom, obj);
        const g = construireObjet(prise.objet, obj, this.mat);
        const col = (j) => loc([pose.R[0][j], pose.R[1][j], pose.R[2][j]]);
        const e1 = col(0), e2 = col(1), e3 = col(2);
        if (new THREE.Matrix3().setFromMatrix4(new THREE.Matrix4().makeBasis(e1, e2, e3)).determinant() < 0) e1.negate();
        g.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(e1, e2, e3));
        g.position.copy(loc(pose.centre));
        g.userData = { nom: prise.objet, tombe: !obj.partenaire, base: g.position.clone(), axe: e2.clone() };
        R.main.add(g); R.objet = g;
      }
      R.cleObjet = cle;
    }
    // dommage visible : la lettre froissée devient une boule, la tige de la rose plie, le reste s'assombrit
    if (R.objet && prise?.endommage && !R.objet.userData.abime) {
      R.objet.userData.abime = true;
      if (prise.objet === "lettre") {
        R.objet.clear();
        const geo = new THREE.IcosahedronGeometry(0.03, 1), pos = geo.attributes.position;
        for (let i = 0; i < pos.count; i++) { const k = 0.75 + 0.5 * Math.abs(Math.sin(i * 12.9898) * 43758.5453 % 1); pos.setXYZ(i, pos.getX(i) * k, pos.getY(i) * k, pos.getZ(i) * k); }
        geo.computeVertexNormals();
        const boule = new THREE.Mesh(geo, std(OBJETS.lettre.couleur, 0.95, { flatShading: true })); boule.castShadow = true;
        boule.position.set(0, -0.8 * OBJETS.lettre.dims[1] + 0.022, 0);      // au point de pince (bord tenu de la feuille)
        R.objet.add(boule);
      } else if (prise.objet === "rose") R.objet.rotation.x += 0.5;
      else R.objet.traverse((o) => { if (o.material?.color) { o.material = o.material.clone(); o.material.color.multiplyScalar(0.6); } });
    }
    // glissement visible : l'objet descend le long de sa longueur (au plus 4 cm)
    if (R.objet && prise) R.objet.position.copy(R.objet.userData.base).addScaledVector(R.objet.userData.axe, -Math.min(0.04, prise.glisse || 0));
  }
  /* Objets échappés : chute libre jusqu'au plateau, où ils restent jusqu'à ce qu'on les reprenne. */
  majChutes(dt) {
    for (const c of this.chutes || []) {
      if (c.pose) continue;
      c.v += 9.81 * dt; c.g.position.y -= c.v * dt;
      if (c.g.position.y <= 0.03) { c.g.position.y = 0.03; c.pose = true; c.g.rotation.set(Math.PI / 2, c.g.rotation.y, 0); }
    }
  }
  /* Montre ou cache la carte tactile (coussinets colorés par la pression). */
  carteTactile(visible) { for (const s of ["g", "d"]) this.mainsRendu[s].carte = !!visible; }

  /* Accessoires de l'habillage : chapeaux (sur la tête, qui les entraîne), ornements du cou, cape (dos du tronc),
     jupe ou robe (bassin). Ils n'appartiennent à aucune zone cliquable et sont masqués par défaut. */
  construireAccessoires() {
    const M = this.mat, O = this.os, f = this.visage.g, A = (O.acc = {});
    const ajoute = (parent, nom, ...meshes) => { const g = groupe(nom, parent); meshes.forEach((m) => g.add(m)); g.visible = false; return g; };
    const cyl = (rt, rb, h, mat, seg = 36, ouvert = false) => maille(new THREE.CylinderGeometry(rt, rb, h, seg, 1, ouvert), mat);
    const pos = (m, x, y, z) => { m.position.set(x, y, z); return m; };
    const bord = (r, y) => pos(cyl(r, r, 0.008, M.chapeau, 48), 0, y, 0);
    // chapeaux (origine : centre de la tête ; sommet du crâne vers y = 0,112)
    const calotte = (r, sy, y) => { const m = maille(new THREE.SphereGeometry(r, 36, 18, 0, Math.PI * 2, 0, Math.PI / 2), M.chapeau); m.scale.set(0.95, sy, 1.05); return pos(m, 0, y, -0.004); };
    A.melon = ajoute(f, "chapeau_melon", calotte(0.104, 0.95, 0.05), bord(0.135, 0.058));
    A["haut-de-forme"] = ajoute(f, "chapeau_haut_de_forme", pos(cyl(0.092, 0.086, 0.17, M.chapeau), 0, 0.15, -0.004), pos(cyl(0.093, 0.093, 0.012, M.accessoire), 0, 0.075, -0.004), bord(0.14, 0.064));
    const beret = maille(new THREE.SphereGeometry(0.118, 36, 14), M.chapeau); beret.scale.set(1, 0.32, 1); pos(beret, 0.012, 0.098, -0.01); beret.rotation.z = -0.22;
    A["béret"] = ajoute(f, "chapeau_beret", beret);
    const visiere = maille(new THREE.CylinderGeometry(0.075, 0.075, 0.006, 32, 1, false, -Math.PI / 2, Math.PI), M.chapeau); pos(visiere, 0, 0.05, 0.075); visiere.rotation.x = 0.12;
    A.casquette = ajoute(f, "chapeau_casquette", calotte(0.103, 0.85, 0.03), visiere);
    const pointes = Array.from({ length: 8 }, (_, i) => { const a = (i / 8) * Math.PI * 2, c = maille(new THREE.ConeGeometry(0.014, 0.045, 10), M.or); return pos(c, Math.sin(a) * 0.083, 0.15, Math.cos(a) * 0.083 - 0.004); });
    A.couronne = ajoute(f, "chapeau_couronne", pos(cyl(0.086, 0.086, 0.05, M.or, 40, true), 0, 0.105, -0.004), ...pointes);
    A.calot = ajoute(f, "chapeau_calot", calotte(0.1, 0.92, 0.012));
    // protège-oreilles de lutte : coquilles rigides sur les oreilles, sangles du sommet et de la nuque, mentonnière
    // à boucle (NCAA, règle 1.5.4 : protège-oreilles à dispositif de verrouillage réglable)
    const coquille = (x) => {
      const c = maille(new THREE.CylinderGeometry(0.043, 0.047, 0.026, 28), M.chapeau); c.rotation.z = Math.PI / 2; pos(c, x * 0.111, -0.004, -0.006);
      const event = maille(new THREE.TorusGeometry(0.024, 0.006, 8, 20), M.accessoire); event.rotation.y = Math.PI / 2; pos(event, x * 0.125, -0.004, -0.006);
      return [c, event];
    };
    const sangle = (r, rotX, y, z) => { const m = maille(new THREE.TorusGeometry(r, 0.009, 8, 40, Math.PI), M.chapeau); m.scale.set(1, 1.02, 1.6); m.rotation.x = rotX; return pos(m, 0, y, z); };
    const menton = maille(new THREE.TorusGeometry(0.112, 0.007, 8, 40, Math.PI), M.chapeau); menton.rotation.set(0.55, 0, Math.PI); pos(menton, 0, -0.012, 0.012);
    A["protège-oreilles"] = ajoute(f, "chapeau_protege_oreilles", ...coquille(1), ...coquille(-1), sangle(0.116, 0, -0.004, -0.012), sangle(0.114, -0.75, -0.002, -0.014), menton);
    // chaussures de lutte : tige montant au-dessus de la cheville
    for (const s of ["g", "d"]) {
      const tige = maille(new THREE.CylinderGeometry(0.056, 0.05, 0.12, 24), M.chaussures, `pied_${s}`); pos(tige, 0, 0.02, 0.005);
      A[`tige_${s}`] = ajoute(O[`cheville_${s}`], `chaussure_montante_${s}`, tige);
    }
    // cou (origine : poitrine ; le col est à y = 0,285)
    const P = O.poitrine;
    const cravate = maille(new THREE.BoxGeometry(0.036, 0.21, 0.006), M.accessoire); pos(cravate, 0, 0.16, 0.108); cravate.rotation.x = -0.1;
    const noeud = maille(new THREE.BoxGeometry(0.024, 0.022, 0.016), M.accessoire); pos(noeud, 0, 0.262, 0.07);
    A.cravate = ajoute(P, "cou_cravate", cravate, noeud);
    const aile = (x) => { const c = maille(new THREE.ConeGeometry(0.018, 0.04, 12), M.accessoire); c.rotation.z = x * Math.PI / 2; return pos(c, x * 0.022, 0.265, 0.064); };
    A["nœud papillon"] = ajoute(P, "cou_noeud", aile(1), aile(-1), pos(maille(new THREE.SphereGeometry(0.009, 12, 8), M.accessoire), 0, 0.265, 0.068));
    const collerette = maille(new THREE.TorusGeometry(0.085, 0.03, 10, 28), M.accessoire); collerette.rotation.x = Math.PI / 2; collerette.scale.set(1, 1, 0.45); pos(collerette, 0, 0.29, 0.004);
    A.collerette = ajoute(P, "cou_collerette", collerette);
    const tour = maille(new THREE.TorusGeometry(0.058, 0.017, 10, 24), M.accessoire); tour.rotation.x = Math.PI / 2; pos(tour, 0, 0.278, 0.004);
    const pan = maille(new THREE.ConeGeometry(0.03, 0.09, 3), M.accessoire); pan.rotation.x = Math.PI; pos(pan, 0.012, 0.225, 0.075);
    A.foulard = ajoute(P, "cou_foulard", tour, pan);
    // cape (dos du tronc) et jupe ou robe (bassin)
    const cape = (h, rb) => { const m = maille(new THREE.CylinderGeometry(0.17, rb, h, 36, 1, true, Math.PI / 2 + 0.25, Math.PI - 0.5), M.accessoire); return pos(m, 0, 0.27 - h / 2, -0.01); };
    A.cape_courte = ajoute(P, "cape_courte", cape(0.55, 0.25));
    A.cape_longue = ajoute(P, "cape_longue", cape(1.12, 0.36));
    const jupe = (h, rb) => pos(maille(new THREE.CylinderGeometry(0.165, rb, h, 40, 1, true), M.jupe), 0, 0.075 - h / 2, 0);
    A.jupe_courte = ajoute(O.bassin, "jupe_courte", jupe(0.42, 0.25));
    A.jupe_longue = ajoute(O.bassin, "jupe_longue", jupe(0.93, 0.34));
  }

  /* Pose : {dof: degrés}, plus déplacement de la racine. Les angles sont ceux de schema.json. */
  appliquer(P, extra = {}) {
    const O = this.os, v = (k) => P[k] || 0;
    O.bassin.position.y = 0.98 - v("bassin.abaissement") / 100 + v("bassin.elevation") / 100 + (extra.bassinY || 0);
    O.bassin.position.x = extra.bassinX || 0;
    O.bassin.rotation.set(0, R(extra.bassinRot || 0), 0);
    const tf = v("tronc.flexion") + (extra.voussure || 0), tr = v("tronc.rotation"), ti = v("tronc.inclinaison");
    O.lombaires.rotation.set(R(tf * 0.45), R(tr * 0.4), -R(ti * 0.45));
    O.poitrine.rotation.set(R(tf * 0.55), R(tr * 0.6), -R(ti * 0.55));
    const hf = v("tete.flexion"), hr = v("tete.rotation"), hi = v("tete.inclinaison");
    O.cou.rotation.set(R(hf * 0.4), R(hr * 0.35), -R(hi * 0.4));
    O.tete.rotation.set(R(hf * 0.6), R(hr * 0.65), -R(hi * 0.6));
    for (const [s, x] of [["g", 1], ["d", -1]]) {
      O[`clav_${s}`].rotation.z = x * R(v(`epaule_${s}.haussement`) + Math.max(0, v(`epaule_${s}.abduction`) - 90) * 0.25);
      const ep = O[`epaule_${s}`];
      ep.rotation.set(-R(v(`epaule_${s}.flexion`)), -x * R(v(`epaule_${s}.rotation`)), x * R(v(`epaule_${s}.abduction`) + REPOS_BRAS));
      O[`coude_${s}`].rotation.x = -R(v(`coude_${s}.flexion`) + REPOS_COUDE);
      // poignet humain (25 oct. 2026) : pronation-supination de l'avant-bras (y), flexion-extension (z, vers la
      // paume), inclinaison radiale-cubitale (x) ; au repos, le pouce est devant et la paume tournée vers la cuisse
      O[`poignet_${s}`].rotation.set(R(v(`poignet_${s}.deviation`)), -x * R(v(`poignet_${s}.rotation`)), -x * R(v(`poignet_${s}.flexion`)));
      // mains : angles fournis par l'animateur (MainVirtuelle) ; à défaut, posture tirée de la fermeture
      const mv = extra.mains?.[s];
      if (mv) this.poserMain(s, mv.q, mv);
      else {
        const k = v(`main_${s}.fermeture`) / 100, a = anglesPosture("ouverte"), b = anglesPosture("poing"), q = {};
        for (const n of Object.keys(a)) q[n] = a[n] + (b[n] - a[n]) * k;
        if (extra.pointe?.[s]) Object.assign(q, Object.fromEntries(Object.entries(anglesPosture("pointer")).filter(([n]) => n.startsWith("index."))));
        this.poserMain(s, q, null);
      }
      const h = O[`hanche_${s}`];
      h.rotation.set(-R(v(`hanche_${s}.flexion`)), x * R(v(`hanche_${s}.rotation`)), x * R(v(`hanche_${s}.abduction`) + 1.5));
      O[`genou_${s}`].rotation.x = R(v(`genou_${s}.flexion`));
      O[`cheville_${s}`].rotation.x = R(v(`cheville_${s}.flexion`));
      O[`cheville_${s}`].rotation.z = -x * R(v(`cheville_${s}.roulis`));   // roulis (inversion +), comme la cheville du TonyPi
    }
    O.tabouret.visible = !!extra.tabouret;
    if (extra.ancrage !== false && !extra.tabouret) this.ancrer(P, extra);
    if (extra.contacts) this.toucherVisage(P, extra.contacts);
    if (this.humain?.visible && !extra.sansHumain) this.humain.maj();
  }

  /* ── Style humain (25 oct. 2026) ─────────────────────────────────────────────────────
     Proportions du squelette : pivots du corps humain (MakeHuman) ou du personnage stylisé (meta = null). Le visage
     stylisé (repères des contacts main-visage, chapeaux) est recalé sur les yeux du corps humain. */
  proportions(meta) {
    const O = this.os, noms = ["cou", "tete"];
    for (const s of ["g", "d"]) noms.push(`clav_${s}`, `epaule_${s}`, `coude_${s}`, `poignet_${s}`, `hanche_${s}`, `genou_${s}`, `cheville_${s}`, `contact_talon_${s}`, `contact_pointe_${s}`);
    if (!this.propOrig) {
      this.propOrig = Object.fromEntries(noms.map((n) => [n, O[n].position.clone()]));
      this.propOrig.visage = { p: this.visage.g.position.clone(), s: this.visage.g.scale.clone() };
    }
    for (const n of noms) O[n].position.copy(this.propOrig[n]);
    this.visage.g.position.copy(this.propOrig.visage.p); this.visage.g.scale.copy(this.propOrig.visage.s);
    this.cuisse = this.jambe = this.semelle = undefined;
    this.masquerStylise(!!meta);
    if (!meta) return;
    const pos = this.racine.position.clone(), rot = this.racine.rotation.clone();
    this.racine.position.set(0, 0, 0); this.racine.rotation.set(0, 0, 0);
    this.appliquer({}, { ancrage: false, sansHumain: true });
    const P = meta.pivots, V = (k) => new THREE.Vector3(...P[k]);
    const placer = (g, cible) => { g.parent.updateMatrixWorld(true); g.position.copy(g.parent.worldToLocal(cible)); g.updateMatrixWorld(true); };
    placer(O.cou, V("cou")); placer(O.tete, V("tete"));
    for (const s of ["g", "d"]) {
      placer(O[`clav_${s}`], V(`clav_${s}`)); placer(O[`epaule_${s}`], V(`epaule_${s}`)); placer(O[`coude_${s}`], V(`coude_${s}`));
      placer(O[`poignet_${s}`], V(`main_${s}`));
      placer(O[`hanche_${s}`], V(`hanche_${s}`)); placer(O[`genou_${s}`], V(`genou_${s}`)); placer(O[`cheville_${s}`], V(`cheville_${s}`));
      O[`contact_talon_${s}`].position.set(...meta.pieds[s].talon); O[`contact_pointe_${s}`].position.set(...meta.pieds[s].pointe);
    }
    this.cuisse = V("hanche_g").distanceTo(V("genou_g")); this.jambe = V("genou_g").distanceTo(V("cheville_g")); this.semelle = -meta.pieds.g.talon[1];
    // visage stylisé (invisible) recalé : le milieu des yeux sur celui du corps humain, à l'échelle de l'écart des yeux
    const og = V("oeil_g"), od = V("oeil_d"), k = og.distanceTo(od) / 0.064;
    const cible = og.clone().add(od).multiplyScalar(0.5).add(new THREE.Vector3(0, 0, 0.012));
    O.tete.updateMatrixWorld(true);
    const local = O.tete.worldToLocal(cible);
    // largeur : oreilles du visage stylisé (x = 0,1) sur la demi-largeur de la tête humaine (chapeaux, protège-oreilles)
    const kx = meta.tete?.demi_largeur ? meta.tete.demi_largeur / 0.1 : k;
    this.visage.g.scale.set(kx, k, k);
    this.visage.g.position.set(local.x, local.y - 0.012 * k, local.z - 0.1 * k);
    this.racine.position.copy(pos); this.racine.rotation.copy(rot);
  }
  /* Masque (ou montre) les volumes du personnage stylisé ; les accessoires d'habillage, les coussinets tactiles et
     les objets tenus restent visibles. Les volumes masqués restent cliquables (sélection des parties du corps). */
  masquerStylise(oui) {
    this.stylise = this.stylise || [];
    if (!oui) { for (const m of this.stylise) m.visible = true; this.stylise = []; return; }
    const accessoires = new Set();
    for (const g of Object.values(this.os.acc || {})) g.traverse((o) => accessoires.add(o));
    this.racine.traverse((o) => {
      if (!o.isMesh || accessoires.has(o) || /^corps-humain|^oeil_humain|^capteur_|^objet_/.test(o.name) || o.parent?.name?.startsWith("objet_")) return;
      let dansObjet = false; for (let p = o.parent; p; p = p.parent) if (p.name?.startsWith("objet_") || p.name === "tabouret") dansObjet = true;
      if (dansObjet || o.parent === this.os.tabouret) return;
      if (o.visible) { o.visible = false; this.stylise.push(o); }
    });
  }

  /* ── Contact main-visage (2026-10-16) ───────────────────────────────────────────────
     Les angles des gestes « au visage » (bouche, menton, yeux, front, tempe, oreille, crâne) ne suffisaient
     pas : la tête bouge (regard vers le public, respiration, saccades, inclinaisons du geste), et la main
     arrivait à hauteur du bas du cou. Passe géométrique appliquée après les ressorts, comme l'ancrage
     plantaire : pour chaque main en contact, les moindres carrés amortis (Jacobien numérique) ajustent
     flexion, abduction et rotation de l'épaule et flexion du coude, depuis la pose voulue, jusqu'à poser le
     point choisi de la main sur le repère du visage ; le résultat est dosé par le poids du contact (0 à 1),
     que l'animateur fait monter et descendre en douceur. */
  pointMain(s, type) {
    const x = s === "g" ? 1 : -1, O = this.os, v = new THREE.Vector3();
    const main = O[`poignet_${s}`].children.find((c) => c.name === `main_${s}`);
    switch (type) {
      case "paume": return main.localToWorld(v.set(-x * 0.016, -0.06, 0));          // face palmaire
      case "dos": return main.localToWorld(v.set(x * 0.016, -0.06, 0));             // dos de la main
      case "index": return this.mainsRendu[s].doigts.index.arts[3].getWorldPosition(v);   // bout de l'index
      case "doigts": return this.mainsRendu[s].doigts.majeur.arts[3].getWorldPosition(v); // bout du majeur
      case "poing": return this.mainsRendu[s].doigts.majeur.arts[1].getWorldPosition(v);  // jointures (IPP du majeur replié)
      case "avantbras": return O[`coude_${s}`].localToWorld(v.set(0, -0.06, 0.035)); // pli du coude
      default: return main.localToWorld(v.set(0, -0.06, 0));
    }
  }
  regleBras(s, P, q) {
    const O = this.os, x = s === "g" ? 1 : -1;
    O[`clav_${s}`].rotation.z = x * R((P[`epaule_${s}.haussement`] || 0) + Math.max(0, q[1] - 90) * 0.25);
    O[`epaule_${s}`].rotation.set(-R(q[0]), -x * R(q[2]), x * R(q[1] + REPOS_BRAS));
    O[`coude_${s}`].rotation.x = -R(q[3] + REPOS_COUDE);
    O[`clav_${s}`].updateMatrixWorld(true);
  }
  toucherVisage(P, contacts) {
    const D = this.schema.dofs, f = this.visage.g;
    // départ à chaud : la correction de l'image précédente sert de point de départ (convergence sur quelques
    // images pour les contacts difficiles, comme le pli du coude devant le nez) ; effacée quand le contact cesse
    this.ikDelta = this.ikDelta || { g: null, d: null };
    for (const s of ["g", "d"]) if (!contacts.some((c) => c.s === s)) this.ikDelta[s] = null;
    if (!contacts.length) return;
    this.racine.updateMatrixWorld(true);
    for (const c of contacts) {
      const s = c.s, w = clamp(c.poids ?? 1, 0, 1);
      if (w < 0.01) continue;
      const noms = ["flexion", "abduction", "rotation"].map((k) => `epaule_${s}.${k}`).concat([`coude_${s}.flexion`]);
      const bornes = noms.map((n) => [D[n].min, D[n].max]);
      const q0 = noms.map((n) => P[n] || 0);
      const cible = (c.groupe === "poitrine" ? this.os.poitrine : f).localToWorld(new THREE.Vector3(...c.local));
      const ecart = (q) => { this.regleBras(s, P, q); return cible.clone().sub(this.pointMain(s, c.point)); };
      const delta = this.ikDelta[s] || [0, 0, 0, 0];
      let q = q0.map((v, i) => clamp(v + delta[i], bornes[i][0], bornes[i][1]));
      for (let it = 0; it < 8; it++) {
        const e = ecart(q);
        if (e.length() < 0.004) break;
        // Jacobien numérique (m par degré), puis pas des moindres carrés amortis : dq = Jᵀ (J Jᵀ + λ² I)⁻¹ e
        const J = q.map((_, i) => {
          const qq = q.slice(); qq[i] += 1;
          return e.clone().sub(ecart(qq));                       // dérivée du point de la main (m/°)
        });
        const A = new THREE.Matrix3(), l2 = 0.006 * 0.006;
        const m = [0, 0, 0, 0, 0, 0, 0, 0, 0];
        for (const j of J) { const a = [j.x, j.y, j.z]; for (let r = 0; r < 3; r++) for (let k = 0; k < 3; k++) m[r * 3 + k] += a[r] * a[k]; }
        m[0] += l2; m[4] += l2; m[8] += l2;
        A.set(m[0], m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8]).invert();
        const y = e.clone().applyMatrix3(A);
        q = q.map((v, i) => {
          const d = clamp(J[i].dot(y), -20, 20);
          return clamp(v + d, bornes[i][0], bornes[i][1]);
        });
      }
      this.ikDelta[s] = q.map((v, i) => v - q0[i]);
      // dosage : de la pose voulue (poids 0) à la pose de contact (poids 1)
      this.regleBras(s, P, q0.map((v, i) => v + (q[i] - v) * w));
    }
  }

  /* Ancrage plantaire (audit du 2026-10-16) : passe géométrique appliquée après les ressorts.
     1. jambe enfoncée dans le plateau → flexion résiduelle du genou et de la hanche, par cinématique inverse
        à deux segments (loi des cosinus), la cheville restant sous la hanche ;
     2. le bassin descend (pieds qui flottent) ou remonte (enfoncement résiduel) jusqu'au contact du pied le plus bas ;
     3. hors marche, la semelle du ou des pieds d'appui est mise à plat.
     Pendant un saut ou sur demi-pointes (bassin.elevation > 0), seul l'enfoncement est corrigé : le corps
     peut quitter le sol. Assis (tabouret), aucune correction. */
  hauteurSemelle(s) {
    const O = this.os, p = new THREE.Vector3();
    const y = (o) => O.echelle.worldToLocal(o.getWorldPosition(p)).y;
    return Math.min(y(O[`contact_talon_${s}`]), y(O[`contact_pointe_${s}`]));
  }
  plierJambe(s, P, enfoncement) {
    const O = this.os, p = new THREE.Vector3();
    const hanche = O.echelle.worldToLocal(O[`hanche_${s}`].getWorldPosition(p)).y;
    // longueurs du segment : celles du style courant (stylisé, ou proportions du corps humain)
    const CUISSE = this.cuisse ?? CUISSE_STYLISE, JAMBE = this.jambe ?? JAMBE_STYLISE, SEMELLE = this.semelle ?? SEMELLE_STYLISE;
    const D = clamp(hanche - (this.hauteurSemelle(s) + enfoncement) - SEMELLE, Math.abs(CUISSE - JAMBE) + 0.01, CUISSE + JAMBE);
    const k = Math.acos(clamp((D * D - CUISSE * CUISSE - JAMBE * JAMBE) / (2 * CUISSE * JAMBE), -1, 1));
    const hf = Math.atan2(JAMBE * Math.sin(k), CUISSE + JAMBE * Math.cos(k));
    const genou = Math.min(140, Math.max(P[`genou_${s}.flexion`] || 0, THREE.MathUtils.radToDeg(k)));
    const flex = Math.min(125, Math.max(P[`hanche_${s}.flexion`] || 0, THREE.MathUtils.radToDeg(hf)));
    O[`genou_${s}`].rotation.x = R(genou);
    O[`hanche_${s}`].rotation.x = -R(flex);
  }
  aplatirPied(s) {
    const O = this.os, p = new THREE.Vector3(), q = new THREE.Vector3();
    for (let n = 0; n < 2; n++) {
      this.racine.updateMatrixWorld(true);
      const t = O.echelle.worldToLocal(O[`contact_talon_${s}`].getWorldPosition(p));
      const pt = O.echelle.worldToLocal(O[`contact_pointe_${s}`].getWorldPosition(q));
      const d = Math.atan2(pt.y - t.y, Math.hypot(pt.x - t.x, pt.z - t.z));   // < 0 : pointe plus basse que le talon
      O[`cheville_${s}`].rotation.x = clamp(O[`cheville_${s}`].rotation.x + d, R(-40), R(45));
    }
  }
  ancrer(P, extra) {
    const O = this.os;
    const saut = (P["bassin.elevation"] || 0) > 0.5;
    const hauteurs = () => { this.racine.updateMatrixWorld(true); return { g: this.hauteurSemelle("g"), d: this.hauteurSemelle("d") }; };
    // appui le plus bas de chaque jambe : la semelle, ou la rotule quand le personnage est à genoux
    const p = new THREE.Vector3();
    const rotule = (s) => O.echelle.worldToLocal(O[`genou_${s}`].getWorldPosition(p)).y - 0.052;
    let h = hauteurs();
    // flexion résiduelle seulement pour une jambe d'appui peu fléchie : une pose composée (à genoux, accroupi,
    // effondré) garde ses angles et n'est que recalée verticalement
    if (!saut) for (const s of ["g", "d"]) {
      if (h[s] < -TOLERANCE_SOL && h[s] <= rotule(s) && (P[`genou_${s}.flexion`] || 0) < 75) this.plierJambe(s, P, -h[s]);
    }
    const caler = () => {
      h = hauteurs();
      const min = Math.min(h.g, h.d, rotule("g"), rotule("d"));
      if (min < -TOLERANCE_SOL || (!saut && min > TOLERANCE_SOL)) O.bassin.position.y -= min;
    };
    caler();
    if (!saut && !(extra.marche > 0.05)) {
      h = hauteurs();
      // tibia proche de la verticale seulement (debout, fléchi, accroupi) ; à genoux, le cou-de-pied reste au sol
      const tibia = (s) => Math.abs(-O[`hanche_${s}`].rotation.x - O[`genou_${s}`].rotation.x);
      for (const s of ["g", "d"]) if (h[s] < 0.02 && tibia(s) < R(45)) this.aplatirPied(s);
      caler();
    }
    this.racine.updateMatrixWorld(true);
    this.contact = { g: this.hauteurSemelle("g"), d: this.hauteurSemelle("d") };
  }

  appliquerApparence(a) {
    const A = (this.apparence = { ...this.apparence, ...a });
    const C = this.schema.apparence.couleurs;
    const couleur = (n, defaut) => (/^#/.test(n || "") ? n : C[n] || defaut);
    const M = this.mat, O = this.os;
    const k = clamp(A.taille, 150, 205) / 178;
    O.echelle.scale.setScalar(k);
    const car = clamp(A.carrure, 0.8, 1.3), corp = clamp(A.corpulence, 0.8, 1.5);
    O.thorax.scale.set(1.85 * car, 1.72, 1.13 * (0.92 + 0.08 * corp));
    O.carrure.scale.set(1, car, 0.85); O.carrure.position.y = 0.225;
    O.abdomen.scale.set(1.24 * (0.85 + 0.15 * corp) * (0.9 + 0.1 * car), 1, 0.86 * corp);
    O.pelvis.scale.set(1.62 * (0.92 + 0.08 * corp), 1.05, 1.08 * (0.9 + 0.1 * corp));
    O.ceinture.scale.set(1.05 * (0.9 + 0.12 * corp), 0.7 * corp * 0.98, 1);
    for (const s of ["g", "d"]) {
      const x = s === "g" ? 1 : -1;
      O[`epaule_${s}`].position.x = (0.165 * car) * x;
      O[`bras_${s}`].scale.set(0.9 + 0.1 * car, 1, 0.9 + 0.1 * car);
      O[`deltoide_${s}`].scale.set(car, 1.05, car);
      O[`cuisse_${s}`].scale.set(0.92 + 0.08 * corp, 1, 0.92 + 0.08 * corp);
    }
    M.peau.color.set(PEAUX[A.peau] || PEAUX.mate);
    M.paupiere.color.copy(M.peau.color).multiplyScalar(0.93);
    M.levres.color.copy(M.peau.color).lerp(new THREE.Color("#9e4a46"), 0.45);
    M.crane.color.copy(M.peau.color).lerp(new THREE.Color(couleur(A.couleur_cheveux, "#6b4a2f")), 0.4);
    // l'âge grisonne la chevelure et la barbe (au-delà de 35 ans)
    const gris = clamp((A.age - 35) / 40, 0, 0.85);
    const ch = new THREE.Color(couleur(A.couleur_cheveux, "#6b4a2f")).lerp(new THREE.Color("#a7a7a4"), gris);
    M.cheveux.color.copy(ch); M.barbe.color.copy(ch).multiplyScalar(0.9); M.sourcils.color.copy(ch).multiplyScalar(0.62);
    M.iris.color.set(YEUX[A.yeux] || YEUX.brun);
    // modèle de maillot de lutte (25 oct. 2026) : la couleur du corps du maillot habille le haut et le bas
    const maillot = A.manches === "sans" && A.coupe_bas === "cuissard" ? this.schema.apparence.modeles_maillot?.[A.modele_maillot]?.couleurs : null;
    M.haut.color.set(maillot?.corps || couleur(A.haut, "#1f2b4a")); M.bas.color.set(maillot?.corps || couleur(A.bas, "#7d8086")); M.chaussures.color.set(this.schema.apparence.modeles_chaussures?.[A.modele_chaussures]?.couleurs?.tige || couleur(A.chaussures, "#1b1b1d"));
    const [rh, mh] = (MATIERES[A.matiere] || MATIERES.tissu).haut, [rb, mb] = (MATIERES[A.matiere] || MATIERES.tissu).bas;
    Object.assign(M.haut, { roughness: rh, metalness: mh }); Object.assign(M.bas, { roughness: rb, metalness: mb });
    M.jupe.color.copy(M.bas.color); Object.assign(M.jupe, { roughness: rb, metalness: mb });
    M.chapeau.color.set(couleur(A.couleur_chapeau, "#1b1b1d")); M.accessoire.color.set(couleur(A.accessoire, "#6d1f2a"));
    M.mains.color.copy(A.gants ? new THREE.Color(couleur(A.accessoire, "#ececec")) : M.peau.color);
    M.mains.roughness = A.gants ? 0.5 : 0.62;
    const acc = O.acc;
    for (const k of ["melon", "haut-de-forme", "béret", "casquette", "couronne", "calot", "protège-oreilles"]) acc[k].visible = A.chapeau === k;
    for (const s of ["g", "d"]) acc[`tige_${s}`].visible = !!A.chaussures_montantes && A.style !== "humain";   // le corps humain peint sa tige
    O.ceinture.visible = !(A.manches === "sans" && A.coupe_bas === "cuissard");   // maillot d'une pièce : pas de ceinture
    for (const k of ["cravate", "nœud papillon", "collerette", "foulard"]) acc[k].visible = A.cou === k;
    acc.cape_courte.visible = A.cape === "courte"; acc.cape_longue.visible = A.cape === "longue";
    acc.jupe_courte.visible = A.jupe === "courte"; acc.jupe_longue.visible = A.jupe === "longue";
    const courtes = A.manches === "courtes" || A.manches === "sans", sans = A.manches === "sans", cuissard = A.coupe_bas === "cuissard";
    for (const s of ["g", "d"]) {
      O[`avantbras_${s}`].material = courtes ? M.peau : M.haut; O[`articCoude_${s}`].material = courtes ? M.peau : M.haut; O[`manchette_${s}`].visible = !courtes;
      // sans manches (maillot de lutte) : bras et épaules nus ; cuissard : jambes nues sous le genou
      O[`bras_${s}`].material = sans ? M.peau : M.haut; O[`deltoide_${s}`].material = sans ? M.peau : M.haut;
      O[`tibia_${s}`].material = cuissard ? M.peau : M.bas; O[`rotule_${s}`].material = cuissard ? M.peau : M.bas;
    }
    this.visage.coiffure(A.cheveux, A.barbe, A.moustache);
    // style humain : corps chargé à la demande (chargerHumain, fourni par la page), puis activé ou peint
    if (A.style === "humain" && !this.humain && this.chargerHumain && !this.chargement) {
      this.chargement = this.chargerHumain().then(() => { this.chargement = null; this.appliquerApparence({}); });
    }
    if (this.humain) {
      const veut = A.style === "humain";
      if (veut !== this.humain.visible) { this.humain.activer(veut); if (!veut) return this.appliquerApparence({}); }
      else if (veut) { this.masquerStylise(true); this.humain.peindre(); }
    }
    return A;
  }
  /* position mondiale approximative du milieu des yeux (cadrage, regard) */
  pointYeux(cible = new THREE.Vector3()) {
    this.visage.g.updateWorldMatrix(true, false);
    return cible.set(0, 0.012, 0.08).applyMatrix4(this.visage.g.matrixWorld);
  }
}

/* ── Mains : géométries partagées, carte de pression, accessoires ───────────────── */
const GEO_MAIN = {};
/* Pression (kPa) → couleur : vert (effleurement) → jaune → rouge (≥ 300 kPa), échelle logarithmique. */
function couleurPression(kpa) {
  const t = clamp(Math.log10(1 + Math.max(0, kpa)) / Math.log10(301), 0, 1);
  return new THREE.Color().setHSL(0.36 * (1 - t), 0.85, 0.5);
}
/* Accessoire dans son repère propre (x : épaisseur ou rayon, y : longueur, z : axe des cylindres), aux
   dimensions du modèle de contact (mains.js) ; quelques détails de décor seulement. */
function construireObjet(nom, o, M) {
  const g = new THREE.Group(); g.name = `objet_${nom}`;
  const [a, b, c] = o.dims;
  const mat = std(o.couleur, 0.5, nom === "verre" ? { transparent: true, opacity: 0.45, roughness: 0.08 } : {});
  const ajoute = (m, x = 0, y = 0, z = 0) => { m.position.set(x, y, z); m.castShadow = true; g.add(m); return m; };
  const cylZ = (r1, r2, h, m) => { const geo = new THREE.CylinderGeometry(r1, r2, h, 20); geo.rotateX(Math.PI / 2); return new THREE.Mesh(geo, m); };
  if (o.forme === "cylindre") ajoute(cylZ(a, a, 2 * b, mat));
  else if (o.forme === "sphere") ajoute(new THREE.Mesh(new THREE.SphereGeometry(a, 24, 18), mat));
  else ajoute(new THREE.Mesh(new THREE.BoxGeometry(2 * a, 2 * b, 2 * c), mat));
  switch (nom) {
    case "epee": {
      const acier = std("#c9ccd2", 0.25, { metalness: 0.8 });
      ajoute(new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.022, 0.012), M.or), 0, 0, b + 0.006).scale.set(1, 5, 1);
      ajoute(new THREE.Mesh(new THREE.BoxGeometry(0.006, 0.032, 0.72), acier), 0, 0, b + 0.37);
      ajoute(new THREE.Mesh(new THREE.SphereGeometry(0.02, 14, 10), M.or), 0, 0, -b - 0.012);
      break;
    }
    case "coupe": ajoute(cylZ(0.04, 0.015, 0.06, mat), 0, 0, b + 0.03); ajoute(cylZ(0.035, 0.035, 0.006, mat), 0, 0, -b); break;
    case "rose": ajoute(new THREE.Mesh(new THREE.SphereGeometry(0.024, 16, 12), std("#b0182c", 0.6)), 0, 0, b + 0.016).scale.set(1, 1, 0.8); break;
    case "plume": ajoute(new THREE.Mesh(new THREE.BoxGeometry(0.002, 0.03, 0.13), std("#f5f5f0", 0.8, { side: THREE.DoubleSide })), 0, 0.013, b + 0.02); break;
    case "pomme": ajoute(cylZ(0.002, 0.002, 0.018, M.bois), 0, a, 0).rotation.x = Math.PI / 2; break;
    case "crane": { const noir = std("#151210", 0.9); ajoute(new THREE.Mesh(new THREE.SphereGeometry(0.018, 10, 8), noir), 0.06, -0.012, 0.022); ajoute(new THREE.Mesh(new THREE.SphereGeometry(0.018, 10, 8), noir), 0.06, -0.012, -0.022); break; }
    case "livre": ajoute(new THREE.Mesh(new THREE.BoxGeometry(2 * a * 0.85, 2 * b * 0.97, 2 * c + 0.002), std("#efe6cf", 0.9)), 0.001, 0.002, 0); break;
    case "lanterne": {
      ajoute(new THREE.Mesh(new THREE.BoxGeometry(0.002, 0.11, 0.002), M.chaussures), 0, 0.055, 0);
      ajoute(new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.14, 0.09), std("#ffcf6a", 0.4, { emissive: "#ff9a2a", emissiveIntensity: 0.6 })), 0, 0.18, 0);
      break;
    }
    case "main_partenaire": {
      // main tendue du partenaire virtuel et sa manche, qui vient du côté du pouce du robot
      // l'avant-bras du partenaire part de son poignet (côté pouce du robot) et s'éloigne vers l'avant
      const dir = new THREE.Vector3(0, 0.35, 0.94).normalize();
      const manche = ajoute(new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.034, 0.26, 20), std("#5d6a7a", 0.85)));
      manche.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
      manche.position.set(0, b, 0).addScaledVector(dir, 0.13);
      ajoute(new THREE.Mesh(new THREE.SphereGeometry(0.012, 10, 8), mat), 0.018, -b * 0.3, c * 0.9);
      break;
    }
  }
  return g;
}
