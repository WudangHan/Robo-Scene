/* Robo-Scène — corps et visage du robot virtuel.
   Humanoïde masculin entièrement procédural (aucun modèle tiers) : squelette hiérarchique de
   groupes three.js dont les pivots sont placés aux articulations, volumes simples (capsules,
   ellipsoïdes) et visage animé par unités d'action. Le parti pris stylisé, plutôt que
   photoréaliste, est volontaire (voir le guide : vallée de l'étrange). */
import * as THREE from "three";

const R = THREE.MathUtils.degToRad;
const lerp = THREE.MathUtils.lerp;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const REPOS_BRAS = 7;          // abduction structurelle : les bras pendent sans traverser le thorax
const REPOS_COUDE = 6;
// Segments de la jambe (repère de l'échelle, en m) : hanche → genou, genou → cheville, cheville → semelle
const CUISSE = 0.43, JAMBE = 0.41, SEMELLE = 0.08;
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

export const PEAUX = { "très claire": "#f0d2bd", claire: "#e2b794", mate: "#c99a78", olive: "#ad875c", brune: "#8a5a3c", "foncée": "#5c3925" };
export const YEUX = { bleu: "#3d6ea8", vert: "#4f7d4a", brun: "#4a3220", noir: "#1e1612", gris: "#7d8790", noisette: "#7a5a2e" };
export const APPARENCE_DEFAUT = {
  taille: 178, carrure: 1, corpulence: 1, age: 40, cheveux: "court", couleur_cheveux: "châtain", barbe: "courte",
  moustache: false, manches: "longues", peau: "mate", yeux: "brun", haut: "bleu marine", bas: "gris", chaussures: "noir",
};

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
      this.construireMain(poignet, s, x);
      const hanche = (O[`hanche_${s}`] = groupe(`hanche_${s}`, bassin, 0.092 * x, -0.06, 0));
      hanche.rotation.order = "ZXY";
      const cuisse = capsule(0.068, 0.3, M.bas, `cuisse_${s}`); cuisse.position.y = -0.2; hanche.add(cuisse); O[`cuisse_${s}`] = cuisse;
      const genou = (O[`genou_${s}`] = groupe(`genou_${s}`, hanche, 0, -0.43, 0));
      const rotule = ellipsoide(0.052, M.bas, `tibia_${s}`); genou.add(rotule);
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
    this.racine.traverse((o) => { if (o.isMesh && o.userData.zone) this.zones.push(o); });
  }
  construireMain(poignet, s, x) {
    const M = this.mat;
    const main = groupe(`main_${s}`, poignet);
    const paume = maille(new THREE.BoxGeometry(0.026, 0.085, 0.074), M.peau, `main_${s}`); paume.position.y = -0.045; main.add(paume);
    const arrondi = ellipsoide(0.037, M.peau, `main_${s}`, [0.38, 1.18, 1.02]); arrondi.position.y = -0.045; main.add(arrondi);
    this.os[`doigts_${s}`] = [0.026, 0.0085, -0.0085, -0.026].map((z, i) => {
      const long = [0.044, 0.05, 0.047, 0.037][i];
      const d1 = groupe("phalange", main, 0, -0.088, z);
      const p1 = capsule(0.0085, long * 0.5, M.peau, `main_${s}`); p1.position.y = -long * 0.3; d1.add(p1);
      const d2 = groupe("phalange", d1, 0, -long * 0.6, 0);
      const p2 = capsule(0.0078, long * 0.4, M.peau, `main_${s}`); p2.position.y = -long * 0.25; d2.add(p2);
      return [d1, d2];
    });
    const pouce = groupe("pouce", main, -0.004 * x, -0.03, 0.036);
    pouce.rotation.set(0.5, 0, 0.45 * x);
    const pp = capsule(0.0105, 0.03, M.peau, `main_${s}`); pp.position.y = -0.024; pouce.add(pp);
    this.os[`pouce_${s}`] = pouce;
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
      O[`poignet_${s}`].rotation.z = -x * R(v(`poignet_${s}.flexion`));
      const ferm = v(`main_${s}.fermeture`) / 100, pointe = !!(extra.pointe && extra.pointe[s]);
      O[`doigts_${s}`].forEach(([a, b], i) => {
        const k = pointe && i === 0 ? 0.05 : ferm;
        a.rotation.z = -x * R(8 + 82 * k); b.rotation.z = -x * R(6 + 95 * k);
      });
      O[`pouce_${s}`].rotation.z = x * R(26 - 40 * ferm);
      const h = O[`hanche_${s}`];
      h.rotation.set(-R(v(`hanche_${s}.flexion`)), x * R(v(`hanche_${s}.rotation`)), x * R(v(`hanche_${s}.abduction`) + 1.5));
      O[`genou_${s}`].rotation.x = R(v(`genou_${s}.flexion`));
      O[`cheville_${s}`].rotation.x = R(v(`cheville_${s}.flexion`));
      O[`cheville_${s}`].rotation.z = -x * R(v(`cheville_${s}.roulis`));   // roulis (inversion +), comme la cheville du TonyPi
    }
    O.tabouret.visible = !!extra.tabouret;
    if (extra.ancrage !== false && !extra.tabouret) this.ancrer(P, extra);
    if (extra.contacts) this.toucherVisage(P, extra.contacts);
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
      case "index": return O[`doigts_${s}`][0][1].localToWorld(v.set(0, -0.02, 0));  // bout de l'index
      case "doigts": return O[`doigts_${s}`][1][1].localToWorld(v.set(0, -0.018, 0)); // bout du majeur
      case "poing": return O[`doigts_${s}`][1][0].localToWorld(v.set(0, -0.012, 0));  // jointures
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
      const cible = f.localToWorld(new THREE.Vector3(...c.local));
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
    M.haut.color.set(couleur(A.haut, "#1f2b4a")); M.bas.color.set(couleur(A.bas, "#7d8086")); M.chaussures.color.set(couleur(A.chaussures, "#1b1b1d"));
    const courtes = A.manches === "courtes";
    for (const s of ["g", "d"]) { O[`avantbras_${s}`].material = courtes ? M.peau : M.haut; O[`articCoude_${s}`].material = courtes ? M.peau : M.haut; O[`manchette_${s}`].visible = !courtes; }
    this.visage.coiffure(A.cheveux, A.barbe, A.moustache);
    return A;
  }
  /* position mondiale approximative du milieu des yeux (cadrage, regard) */
  pointYeux(cible = new THREE.Vector3()) {
    this.visage.g.updateWorldMatrix(true, false);
    return cible.set(0, 0.012, 0.08).applyMatrix4(this.visage.g.matrixWorld);
  }
}
