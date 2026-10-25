/* Robo-Scène — mains à cinq doigts du robot virtuel : anatomie, gestes des doigts, prises, force et toucher simulé
   (demande du 25 octobre 2026). Module pur (aucune dépendance au DOM ni à three.js), testé sous Node.

   Perception, force et mouvement sont reliés dans une boucle unique, sur le modèle de la préhension humaine :
   1. Mouvement — chaque doigt suit une trajectoire articulaire (premier ordre, vitesse bornée) dans les amplitudes
      articulaires usuelles ; l'articulation interphalangienne distale suit les deux tiers de la proximale
      (Rijpkema et Girard) ; un doigt entraîne légèrement ses voisins (« asservissement », Zatsiorsky et al.).
   2. Perception — dix capteurs par main (cinq pulpes, quatre phalanges moyennes, paume) mesurent contact, force
      normale, pression et glissement ; les contacts sont calculés par géométrie (capsules des phalanges contre la
      forme de l'objet), non posés à la main.
   3. Force — la force de serrage est réglée sur la charge et le frottement, avec une marge de sécurité qui dépend
      de la manière (délicate, normale, ferme) : force normale ≥ charge / (2 μ), comme dans la régulation humaine
      décrite par Westling et Johansson ; un glissement détecté par les capteurs relève la force après 74 ms, la
      latence mesurée chez l'humain (Johansson et Westling 1987) ; la force est plafonnée sous le seuil de dommage
      de l'objet, sauf intention contraire (« froisse la lettre »).
   Les prises suivent la taxonomie GRASP (Feix et al.) : puissance, intermédiaire, précision ; opposition paume,
   pulpe ou côté.

   (Inférence) Les longueurs des phalanges, les masses, les coefficients de frottement, les seuils de dommage et
   les forces de toucher sont des valeurs de conception, plausibles mais non mesurées : elles se règlent ici.

   Repère canonique de la main (identique pour les deux mains ; humanoide.js le reflète) : u = côté palmaire,
   d = vers le bout des doigts, w = vers le pouce et l'index. Angles en degrés ; flexion positive vers la paume. */

export const DOIGTS = ["pouce", "index", "majeur", "annulaire", "auriculaire"];
export const LIBELLES_DOIGTS = { pouce: "pouce", index: "index", majeur: "majeur", annulaire: "annulaire", auriculaire: "auriculaire" };
export const RAYON_DOIGT = 0.0082;           // m, rayon des capsules des phalanges (contact)
export const PAUME = { epaisseur: 0.028, longueur: 0.088, largeur: 0.074 };   // m (paume de la main)

/* Doigts longs : base de l'articulation métacarpo-phalangienne (MCP) en (u, d, w), longueurs des trois phalanges. */
export const SEGMENTS = {
  index: { base: [0, 0.088, 0.026], longueurs: [0.040, 0.023, 0.019], abduction: 1 },
  majeur: { base: [0, 0.090, 0.0085], longueurs: [0.044, 0.027, 0.020], abduction: 0 },
  annulaire: { base: [0, 0.088, -0.0085], longueurs: [0.041, 0.026, 0.019], abduction: -1 },
  auriculaire: { base: [0, 0.083, -0.026], longueurs: [0.032, 0.019, 0.017], abduction: -1 },
  // pouce : trapézo-métacarpienne (CMC), puis métacarpien, phalange proximale, phalange distale
  pouce: { base: [0.008, 0.022, 0.03], longueurs: [0.046, 0.033, 0.027] },
};

/* Amplitudes articulaires (degrés). Valeurs usuelles des tableaux cliniques consultés (Eaton ; Physiotutors) :
   MCP 0-90 (hyperextension jusqu'à 30-45), IPP 0-100/115, IPD 0-80, abduction 20-30 ; pouce : CMC abduction
   45-60, MCP 0-55, IP 0-80 ; poignet : déviation radiale 15-20, cubitale 30-45 ; pronation et supination 90. */
export const ARTICULATIONS = {
  "pouce.cmc_flexion": { min: -15, max: 50, repos: 8, libelle: "Pouce — opposition (trapézo-métacarpienne)" },
  "pouce.cmc_abduction": { min: 0, max: 60, repos: 22, libelle: "Pouce — abduction palmaire" },
  "pouce.mcp": { min: 0, max: 55, repos: 10, libelle: "Pouce — métacarpo-phalangienne" },
  "pouce.ip": { min: -10, max: 80, repos: 12, libelle: "Pouce — interphalangienne" },
  "poignet.deviation": { min: -20, max: 35, repos: 0, libelle: "Poignet — déviation (+ : cubitale)" },
  "avant_bras.pronation": { min: -90, max: 90, repos: 0, libelle: "Avant-bras — pronation (+) et supination (−)" },
};
const REPOS_DOIGTS = { index: [14, 0, 18], majeur: [18, 0, 22], annulaire: [22, 0, 26], auriculaire: [26, 0, 30] };
for (const d of DOIGTS.slice(1)) {
  const [m, a, p] = REPOS_DOIGTS[d];
  ARTICULATIONS[`${d}.mcp`] = { min: -30, max: 90, repos: m, libelle: `${d} — métacarpo-phalangienne` };
  ARTICULATIONS[`${d}.abduction`] = { min: -15, max: 20, repos: a, libelle: `${d} — écartement` };
  ARTICULATIONS[`${d}.pip`] = { min: 0, max: 105, repos: p, libelle: `${d} — interphalangienne proximale` };
  ARTICULATIONS[`${d}.dip`] = { min: -10, max: 80, repos: Math.round(p * 2 / 3), libelle: `${d} — interphalangienne distale` };
}
export const NOMS_ARTICULATIONS = Object.keys(ARTICULATIONS);
const borne = (n, v) => Math.max(ARTICULATIONS[n].min, Math.min(ARTICULATIONS[n].max, v));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

/* ── Postures des doigts (gestes) ───────────────────────────────────────────────────
   Chaque doigt long : [MCP, écartement, IPP] (l'IPD suit les deux tiers de l'IPP) ; pouce : [opposition,
   abduction, MCP, IP]. « null » : le doigt garde sa posture de repos. */
const F = (mcp, pip, abd = 0) => [mcp, abd, pip];
const OUVERT = F(0, 0), REPLIE = F(85, 100), DEMI = F(45, 55);
const P = (pouce, index, majeur, annulaire, auriculaire, libelle) => ({ pouce, index, majeur, annulaire, auriculaire, libelle });
export const POSTURES = {
  repos: P([8, 22, 10, 12], F(14, 18), F(18, 22), F(22, 26), F(26, 30), "main au repos"),
  ouverte: P([0, 30, 0, 0], F(0, 4, 4), F(0, 4), F(0, 4, 4), F(0, 4, 6), "main ouverte"),
  ecartee: P([-10, 45, 0, 0], F(-5, 0, 18), F(-5, 0), F(-5, 0, 15), F(-5, 0, 20), "doigts écartés"),
  poing: P([42, 8, 45, 55], REPLIE, REPLIE, REPLIE, REPLIE, "poing fermé"),
  pointer: P([40, 10, 40, 40], F(0, 2), REPLIE, REPLIE, REPLIE, "index pointé"),
  pouce_leve: P([-10, 35, 0, -5], REPLIE, REPLIE, REPLIE, REPLIE, "pouce levé"),
  pouce_bas: P([-10, 35, 0, -5], REPLIE, REPLIE, REPLIE, REPLIE, "pouce baissé"),
  ok: P([38, 40, 25, 40], F(55, 70), F(5, 8), F(10, 10, -4), F(15, 12, -8), "signe « OK » (pouce et index en anneau)"),
  victoire: P([40, 10, 40, 45], F(0, 2, 12), F(0, 2, 0), REPLIE, REPLIE, "V de la victoire"),
  pince: P([30, 38, 18, 25], F(42, 45), F(60, 70), F(70, 80), F(75, 85), "pince pouce-index"),
  cle: P([0, 12, 20, 25], F(50, 40), F(80, 95), REPLIE, REPLIE, "prise en clé (index à demi replié)"),
  coupe: P([10, 15, 15, 20], F(25, 30, -2), F(25, 32), F(25, 32, 2), F(25, 32, 4), "main en coupe"),
  griffe: P([20, 30, 25, 35], F(10, 90, 6), F(10, 90), F(10, 90, 6), F(10, 90, 8), "main en griffe"),
  compter_1: P([40, 10, 40, 40], F(0, 2), REPLIE, REPLIE, REPLIE, "un doigt"),
  compter_2: P([40, 10, 40, 45], F(0, 2, 10), F(0, 2), REPLIE, REPLIE, "deux doigts"),
  compter_3: P([40, 10, 40, 45], F(0, 2, 8), F(0, 2), F(0, 2, 6), REPLIE, "trois doigts"),
  compter_4: P([40, 12, 40, 45], F(0, 2, 8), F(0, 2), F(0, 2, 6), F(0, 2, 10), "quatre doigts"),
  compter_5: P([-5, 45, 0, 0], F(0, 2, 10), F(0, 2), F(0, 2, 8), F(0, 2, 12), "cinq doigts"),
};
export const NOMS_POSTURES = Object.keys(POSTURES);

/* ── Accessoires (objets) ───────────────────────────────────────────────────────────
   forme : cylindre (rayon, demi-longueur), sphere (rayon), plaque (demi-épaisseur, demi-longueur, demi-largeur).
   (Inférence) masse, frottement peau-objet μ et seuil de dommage sont des valeurs de conception. */
export const OBJETS = {
  verre: { libelle: "verre", genre: "m", forme: "cylindre", dims: [0.034, 0.06], masse: 0.25, mu: 0.6, dommage: 45, effet: "se fêle", prise: "cylindrique", couleur: "#cfe8ff" },
  coupe: { libelle: "coupe", genre: "f", forme: "cylindre", dims: [0.012, 0.05], masse: 0.2, mu: 0.6, dommage: 40, effet: "se fêle", prise: "cylindrique", couleur: "#d8b04a" },
  epee: { libelle: "épée", genre: "f", forme: "cylindre", dims: [0.016, 0.07], masse: 1.1, mu: 0.9, dommage: 2000, effet: "", prise: "cylindrique", couleur: "#8a8f99" },
  eventail: { libelle: "éventail", genre: "m", forme: "plaque", dims: [0.007, 0.12, 0.016], masse: 0.08, mu: 0.6, dommage: 60, effet: "se brise", prise: "laterale", couleur: "#a8323e" },
  lettre: { libelle: "lettre", genre: "f", forme: "plaque", dims: [0.001, 0.105, 0.075], masse: 0.006, mu: 0.45, dommage: 6, effet: "se froisse", prise: "laterale", couleur: "#f3ead3" },
  rose: { libelle: "rose", genre: "f", forme: "cylindre", dims: [0.003, 0.16], masse: 0.03, mu: 0.55, dommage: 4, effet: "a la tige pliée", prise: "pince_fine", couleur: "#2f6b2f" },
  plume: { libelle: "plume", genre: "f", forme: "cylindre", dims: [0.004, 0.09], masse: 0.01, mu: 0.5, dommage: 8, effet: "se brise", prise: "tripode", couleur: "#f5f5f0" },
  pomme: { libelle: "pomme", genre: "f", forme: "sphere", dims: [0.038], masse: 0.2, mu: 0.6, dommage: 120, effet: "s'écrase", prise: "spherique", couleur: "#b8202a" },
  crane: { libelle: "crâne", genre: "m", forme: "sphere", dims: [0.075], masse: 0.9, mu: 0.7, dommage: 600, effet: "", prise: "spherique", couleur: "#e7dfc8" },
  livre: { libelle: "livre", genre: "m", forme: "plaque", dims: [0.016, 0.11, 0.075], masse: 0.5, mu: 0.6, dommage: 800, effet: "", prise: "plat", couleur: "#5a2a1a" },
  lanterne: { libelle: "lanterne", genre: "f", forme: "cylindre", dims: [0.007, 0.05], masse: 0.6, mu: 0.7, dommage: 400, effet: "", prise: "crochet", couleur: "#3a3a3a" },
  // main tendue d'un partenaire virtuel : tenue par lui (aucune charge), confort plafonné
  main_partenaire: { libelle: "main du partenaire", genre: "f", forme: "plaque", dims: [0.014, 0.05, 0.03], masse: 0, mu: 0.8, dommage: 30, effet: "est serrée trop fort (inconfort)", prise: "poignee", couleur: "#c99a7a", partenaire: true },
};
export const NOMS_OBJETS = Object.keys(OBJETS);

/* ── Prises (taxonomie GRASP, Feix et al.) ─────────────────────────────────────────── */
export const PRISES = {
  cylindrique: { libelle: "enveloppement cylindrique", taxonomie: "Medium wrap — puissance, opposition paume", depart: "ouverte", but: "poing",
                 doigts: ["pouce", "index", "majeur", "annulaire", "auriculaire"], paume: true },
  spherique: { libelle: "prise sphérique", taxonomie: "Power sphere — puissance, opposition paume", depart: "ecartee", but: "poing",
               doigts: ["pouce", "index", "majeur", "annulaire", "auriculaire"], paume: true },
  crochet: { libelle: "crochet", taxonomie: "Hook — puissance, sans pouce", depart: "ouverte", but: "griffe", doigts: ["index", "majeur", "annulaire", "auriculaire"], paume: false },
  pince_fine: { libelle: "pince fine pulpe à pulpe", taxonomie: "Tip pinch — précision, opposition pulpe", depart: "ouverte", but: "pince", doigts: ["pouce", "index"], paume: false },
  tripode: { libelle: "tripode", taxonomie: "Tripod — précision, opposition pulpe", depart: "ouverte", but: "pince", doigts: ["pouce", "index", "majeur"], paume: false },
  laterale: { libelle: "prise latérale (pouce contre le côté de l'index)", taxonomie: "Lateral — intermédiaire, opposition côté", depart: "repos", but: "cle",
              doigts: ["pouce", "index"], paume: false },
  plat: { libelle: "prise palmaire d'un objet plat (pouce sur une face, doigts sur l'autre)", taxonomie: "Medium wrap aplati — puissance, opposition paume (Inférence)",
          depart: "ouverte", but: "poing", doigts: ["pouce", "index", "majeur", "annulaire", "auriculaire"], paume: true },
  poignee: { libelle: "poignée de main", taxonomie: "Medium wrap appliqué à la main d'autrui", depart: "ouverte", but: "poing",
             doigts: ["pouce", "index", "majeur", "annulaire", "auriculaire"], paume: true },
};
export const NOMS_PRISES = Object.keys(PRISES);

/* Manières : marge de sécurité au-dessus de la force minimale, plafond (fraction du seuil de dommage), vitesse.
   (Inférence) valeurs de conception ; un « effleurement » ne serre pas (contact de 0,2 N par doigt). */
export const MANIERES = {
  effleurer: { libelle: "effleurement", marge: 0, plancher: 0.2, plafond: 0.05, vitesse: 0.5 },
  delicat: { libelle: "délicatement", marge: 0.2, plancher: 0.4, plafond: 0.5, vitesse: 0.6 },
  normal: { libelle: "normalement", marge: 0.5, plancher: 1.0, plafond: 0.8, vitesse: 1 },
  ferme: { libelle: "fermement", marge: 1.0, plancher: 3.0, plafond: 0.9, vitesse: 1.2 },
  fort: { libelle: "de toutes ses forces", marge: 3.0, plancher: 30, plafond: Infinity, vitesse: 1.4 },
};
export const FORCE_MAX_MAIN = 300;      // N, force de serrage maximale de la main entière (Inférence : ordre d'un adulte)
export const LATENCE_GLISSEMENT = 0.074; // s, réponse de la force de serrage au glissement (Johansson et Westling 1987)
export const G = 9.81;

function deDoigt(d) { return /^[aeiou]/.test(d) ? `de l'${d}` : `du ${d}`; }
/* Capteurs du toucher : aire de contact (m²) pour convertir la force en pression. (Inférence) */
export const CAPTEURS = [
  ...DOIGTS.map((d) => ({ id: `pulpe_${d}`, doigt: d, segment: 2, libelle: `pulpe ${deDoigt(d)}`, aire: d === "pouce" ? 1.4e-4 : 1.0e-4 })),
  ...DOIGTS.slice(1).map((d) => ({ id: `phalange_${d}`, doigt: d, segment: 1, libelle: `phalange moyenne ${deDoigt(d)}`, aire: 1.5e-4 })),
  { id: "paume", doigt: null, segment: null, libelle: "paume", aire: 20e-4 },
];

/* ── Petite algèbre 3D (matrices 3×3 en tableaux de lignes) ─────────────────────────── */
const mul = (A, B) => A.map((r) => [0, 1, 2].map((j) => r[0] * B[0][j] + r[1] * B[1][j] + r[2] * B[2][j]));
const appl = (A, v) => A.map((r) => r[0] * v[0] + r[1] * v[1] + r[2] * v[2]);
const add = (a, b) => a.map((x, i) => x + b[i]);
const sub = (a, b) => a.map((x, i) => x - b[i]);
const sc = (a, k) => a.map((x) => x * k);
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const norme = (a) => Math.sqrt(dot(a, a));
const unit = (a) => sc(a, 1 / (norme(a) || 1));
const RAD = Math.PI / 180;
export function rot(axe, deg) {
  const [x, y, z] = unit(axe), a = deg * RAD, c = Math.cos(a), s = Math.sin(a), t = 1 - c;
  return [[t * x * x + c, t * x * y - s * z, t * x * z + s * y], [t * x * y + s * z, t * y * y + c, t * y * z - s * x], [t * x * z - s * y, t * y * z + s * x, t * z * z + c]];
}
const I3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
/* Repère du métacarpien du pouce (colonnes u, d, w) : direction donnée par un azimut dans le plan de la paume
   (de l'axe des doigts vers le côté radial) et une élévation palmaire ; la pulpe se tourne vers les doigts à
   mesure de l'opposition (pronation couplée du pouce). (Inférence) correspondances de conception :
   azimut = 55° − 1,1 × opposition ; élévation = 10° + 0,8 × abduction ; rotation de la pulpe = 20° + 0,9 × opposition. */
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
export function reperePouce(opp, abd) {
  const az = (55 - 1.1 * opp) * RAD, el = (10 + 0.8 * abd) * RAD, g = (20 + 0.9 * opp) * RAD;
  const d = unit([Math.sin(el), Math.cos(el) * Math.cos(az), Math.cos(el) * Math.sin(az)]);
  const vise = [Math.cos(g), 0, -Math.sin(g)];                    // côté palmaire, tourné vers le cubitus
  const u = unit(sub(vise, sc(d, dot(vise, d))));
  const w = cross(u, d);
  return [[u[0], d[0], w[0]], [u[1], d[1], w[1]], [u[2], d[2], w[2]]];
}

/* Rotations locales de chaque articulation : axe dans le repère du segment parent, en degrés. Le segment se
   prolonge selon +d local. Flexion : autour de −w (le bout du doigt va vers +u, la paume). */
const AXE_FLEXION = [0, 0, -1], AXE_ECART = [1, 0, 0];
export function chaine(doigt, q) {
  const S = SEGMENTS[doigt], a = (n) => q[`${doigt}.${n}`] ?? 0;
  if (doigt === "pouce") {
    const Rb = reperePouce(a("cmc_flexion"), a("cmc_abduction"));
    return { base: S.base, articulations: [{ R: Rb, L: S.longueurs[0] }, { R: rot(AXE_FLEXION, a("mcp")), L: S.longueurs[1] }, { R: rot(AXE_FLEXION, a("ip")), L: S.longueurs[2] }] };
  }
  const sgn = S.abduction === 0 ? 1 : S.abduction;
  return { base: S.base, articulations: [
    { R: mul(rot(AXE_ECART, sgn * a("abduction")), rot(AXE_FLEXION, a("mcp"))), L: S.longueurs[0] },
    { R: rot(AXE_FLEXION, a("pip")), L: S.longueurs[1] },
    { R: rot(AXE_FLEXION, a("dip")), L: S.longueurs[2] },
  ] };
}
/* Cinématique directe : points des articulations et du bout du doigt, et orientation de chaque segment. */
export function cinematique(doigt, q) {
  const c = chaine(doigt, q);
  let R = I3, p = c.base.slice();
  const points = [p.slice()], reperes = [];
  for (const j of c.articulations) {
    R = mul(R, j.R); reperes.push(R);
    p = add(p, appl(R, [0, j.L, 0])); points.push(p.slice());
  }
  return { points, reperes };
}

/* Distance signée d'un point à la forme d'un objet placé (centre c, axes e1 e2 e3 colonnes de M). */
export function distanceObjet(obj, pose, p) {
  const l = appl(transposee(pose.R), sub(p, pose.centre));      // point dans le repère de l'objet
  const [a, b, c] = obj.dims;
  if (obj.forme === "sphere") return norme(l) - a;
  if (obj.forme === "cylindre") {                                 // axe de l'objet : w local (l[2])
    const dr = Math.hypot(l[0], l[1]) - a, dz = Math.abs(l[2]) - b;
    return Math.min(Math.max(dr, dz), 0) + Math.hypot(Math.max(dr, 0), Math.max(dz, 0));
  }
  const q = [Math.abs(l[0]) - a, Math.abs(l[1]) - b, Math.abs(l[2]) - c];   // plaque : u = épaisseur
  return Math.min(Math.max(...q), 0) + norme(q.map((x) => Math.max(x, 0)));
}
const transposee = (A) => [0, 1, 2].map((i) => [A[0][i], A[1][i], A[2][i]]);

/* Distance minimale entre un doigt (capsules) et l'objet ; segment le plus proche. */
function distanceDoigt(doigt, q, obj, pose, sMin = 0) {
  const { points } = cinematique(doigt, q);
  let best = { d: Infinity, segment: 0 };
  for (let s = sMin; s < 3; s++) {
    const premier = doigt === "pouce" && s === 0 ? 0.5 : 0;     // le métacarpien du pouce est en partie dans la paume
    for (let k = premier; k <= 1.0001; k += 0.125) {
      const pt = add(points[s], sc(sub(points[s + 1], points[s]), k));
      const d = distanceObjet(obj, pose, pt) - RAYON_DOIGT;
      if (d < best.d) best = { d, segment: s };
    }
  }
  return best;
}

/* Angles d'une posture, IPD couplée aux deux tiers de l'IPP (Rijpkema et Girard), bornés. */
export function anglesPosture(nom) {
  const P = POSTURES[nom] || POSTURES.repos, q = {};
  const [o, a, m, i] = P.pouce;
  Object.assign(q, { "pouce.cmc_flexion": o, "pouce.cmc_abduction": a, "pouce.mcp": m, "pouce.ip": i });
  for (const d of DOIGTS.slice(1)) {
    const [mcp, abd, pip] = P[d];
    Object.assign(q, { [`${d}.mcp`]: mcp, [`${d}.abduction`]: abd, [`${d}.pip`]: pip, [`${d}.dip`]: (pip * 2) / 3 });
  }
  for (const n of Object.keys(q)) q[n] = borne(n, q[n]);
  return q;
}
const interp = (qa, qb, s, doigt) => {
  const q = {};
  for (const n of Object.keys(qa)) q[n] = doigt && !n.startsWith(`${doigt}.`) ? qa[n] : qa[n] + (qb[n] - qa[n]) * s;
  return q;
};

/* Pose de l'objet dans la main, selon la prise (repère canonique) : centre, axes (colonnes de R : épaisseur ou
   rayon selon u local, longueur selon d local, axe des cylindres selon w local), et point visé par le pouce. */
const colonnes = (a, b, c) => [[a[0], b[0], c[0]], [a[1], b[1], c[1]], [a[2], b[2], c[2]]];
export function poseObjet(nomPrise, obj) {
  const r = obj.dims[0], ep = PAUME.epaisseur / 2;
  const pulpe = (doigt, posture) => cinematique(doigt, anglesPosture(posture)).points[3];
  switch (nomPrise) {
    case "cylindrique": {
      const c = [ep + r + 0.003, 0.072, 0.004];                 // contre la paume distale, sous les phalanges
      return { centre: c, R: I3, pouce: add(c, [0.55 * r + RAYON_DOIGT, -0.8 * r - RAYON_DOIGT, 0.035]) };
    }
    case "plat": {
      // livre tenu par la tranche : la couverture contre la paume et les doigts, la tranche au ras de l'index,
      // le pouce passe par-dessus la tranche et se pose sur l'autre couverture
      const c = [ep + obj.dims[0] + 0.002, 0.08, 0.03 - obj.dims[1]];
      return { centre: c, R: colonnes([1, 0, 0], [0, 0, 1], [0, 1, 0]), pouce: [c[0] + obj.dims[0] + RAYON_DOIGT, 0.07, 0.02] };
    }
    case "poignee": {
      // main du partenaire tendue « en couteau » : sa paume dans le plan (d, u), épaisseur selon w ; elle
      // traverse la paume du robot, les doigts du robot l'entourent par le dos, le pouce se pose sur le dos
      const c = [ep + obj.dims[0] + 0.002, 0.09, -0.005];
      return { centre: c, R: colonnes([1, 0, 0], [0, 0, 1], [0, 1, 0]), pouce: add(c, [obj.dims[0] + RAYON_DOIGT, -0.025, 0.03]) };
    }
    case "spherique": {
      const c = [ep + r + 0.004, 0.09 + 0.3 * r, 0.0];
      return { centre: c, R: I3, pouce: add(c, sc(unit([0.55, -0.45, 0.7]), r + RAYON_DOIGT)) };
    }
    case "crochet": return { centre: [0.026, 0.118, 0.0], R: I3, pouce: null };
    case "laterale": {
      // plaque fine (lettre, éventail) pincée par son bord entre la pulpe du pouce et le côté radial de la
      // phalange moyenne de l'index à demi replié (prise en clé) ; elle dépasse vers l'avant de la main
      const { points } = cinematique("index", anglesPosture("cle"));
      const m = add(points[1], sc(sub(points[2], points[1]), 0.8));
      const flanc = add(m, [0, 0, RAYON_DOIGT + r - 0.0004]);
      const ex = [0, 0, 1], ey = unit([m[0], m[1] - PAUME.longueur / 2, 0]), ez = cross(ex, ey);
      const c = add(flanc, sc(ey, obj.dims[1] * 0.8));
      return { centre: c, R: colonnes(ex, ey, ez), pouce: add(flanc, [0, 0, 2 * r + RAYON_DOIGT]) };
    }
    case "tripode":
    case "pince_fine":
    default: {
      // objet fin pincé entre les pulpes : posé contre la pulpe de l'index (et du majeur pour le tripode),
      // du côté du pouce ; axe de l'objet selon w (tige, plume)
      const i = pulpe("index", "pince"), m = pulpe("majeur", "pince");
      const appui = i;
      const versPouce = unit(sub(SEGMENTS.pouce.base, appui));
      const c = add(appui, sc(versPouce, RAYON_DOIGT + r - 0.0006));
      const ez = unit(cross(versPouce, [0, 1, 0])), ex = versPouce, ey = cross(ez, ex);
      return { centre: c, R: colonnes(ex, ey, ez), pouce: add(c, sc(versPouce, r + RAYON_DOIGT)) };
    }
  }
}

/* Cinématique inverse du pouce : (opposition, abduction, flexion) qui mène la pulpe au point visé. Recherche en
   grille puis affinage ; l'IP suit la MCP (0,9 × 80/55, Inférence de conception d'après le couplage des doigts). */
/* Pouce posé sur un objet : même recherche, mais le coût pénalise toute pénétration du pouce dans l'objet et
   demande que la pulpe touche sa surface ; le point visé par défaut n'est plus qu'une préférence. (Inférence :
   pondérations de conception.) */
export function anglesPouceObjet(obj, pose, cible) {
  const q = (o, a, f) => ({ "pouce.cmc_flexion": o, "pouce.cmc_abduction": a, "pouce.mcp": 55 * f, "pouce.ip": 72 * f });
  const cout = (o, a, f) => {
    const P = cinematique("pouce", q(o, a, f)).points;
    let pen = 0;
    for (let s = 0; s < 3; s++) for (let k = s === 0 ? 4 : 0; k <= 8; k += 2) {
      const d = distanceObjet(obj, pose, add(P[s], sc(sub(P[s + 1], P[s]), k / 8))) - RAYON_DOIGT;
      if (d < 0) pen += d * d;
    }
    const dp = distanceObjet(obj, pose, P[3]) - RAYON_DOIGT, e = norme(sub(P[3], cible));
    return 1000 * pen + 200 * dp * dp + 0.3 * e * e;
  };
  let best = [8, 22, 0.2], c0 = Infinity;
  for (let o = -15; o <= 50; o += 5) for (let a = 0; a <= 60; a += 5) for (let f = 0; f <= 1.0001; f += 0.1) {
    const c = cout(o, a, f); if (c < c0) { c0 = c; best = [o, a, f]; }
  }
  let pas = [2.5, 2.5, 0.05];
  for (let it = 0; it < 30; it++) {
    let mieux = false;
    for (let k = 0; k < 3; k++) for (const sgn of [-1, 1]) {
      const c = best.slice(); c[k] += sgn * pas[k];
      c[0] = clamp(c[0], -15, 50); c[1] = clamp(c[1], 0, 60); c[2] = clamp(c[2], 0, 1);
      const v = cout(...c); if (v < c0) { c0 = v; best = c; mieux = true; }
    }
    if (!mieux) pas = pas.map((x) => x / 2);
  }
  const Q = q(...best), P = cinematique("pouce", Q).points;
  return { q: Q, pulpe: distanceObjet(obj, pose, P[3]) - RAYON_DOIGT };
}
export function anglesPouce(cible) {
  const q = (o, a, f) => ({ "pouce.cmc_flexion": o, "pouce.cmc_abduction": a, "pouce.mcp": 55 * f, "pouce.ip": 72 * f });
  const err = (o, a, f) => { const t = cinematique("pouce", q(o, a, f)).points[3]; return norme(sub(t, cible)); };
  let best = [8, 22, 0.2], e0 = Infinity;
  for (let o = -15; o <= 50; o += 5) for (let a = 0; a <= 60; a += 5) for (let f = 0; f <= 1.0001; f += 0.1) {
    const e = err(o, a, f); if (e < e0) { e0 = e; best = [o, a, f]; }
  }
  let pas = [2.5, 2.5, 0.05];
  for (let it = 0; it < 30; it++) {
    let mieux = false;
    for (let k = 0; k < 3; k++) for (const sgn of [-1, 1]) {
      const c = best.slice(); c[k] += sgn * pas[k];
      c[0] = clamp(c[0], -15, 50); c[1] = clamp(c[1], 0, 60); c[2] = clamp(c[2], 0, 1);
      const e = err(...c); if (e < e0) { e0 = e; best = c; mieux = true; }
    }
    if (!mieux) pas = pas.map((x) => x / 2);
  }
  return { q: q(...best), erreur: e0 };
}

/* Fermeture de contact, segment par segment (enveloppement) : le doigt se ferme le long du chemin départ → but ;
   quand un segment touche l'objet, les articulations en amont s'arrêtent et les suivantes continuent de se
   fermer jusqu'à ce que la phalange distale touche à son tour, ou que le chemin s'achève — ainsi les doigts
   s'enroulent autour d'un verre ou du bord d'une main. Le but du pouce est calculé par cinématique inverse vers
   le point visé, prolongé de 20 % pour serrer. Sortie par doigt : contact, segments touchés, angles finaux. */
const JOINTS = { pouce: ["cmc_flexion", "cmc_abduction", "mcp", "ip"], doigt: ["abduction", "mcp", "pip", "dip"] };
const ORDRE = { pouce: [["cmc_flexion", "cmc_abduction"], ["mcp"], ["ip"]], doigt: [["abduction", "mcp"], ["pip"], ["dip"]] };
export function contacts(nomPrise, obj, pose = poseObjet(nomPrise, obj)) {
  const pr = PRISES[nomPrise], qa = anglesPosture(pr.depart), qb = anglesPosture(pr.but);
  const out = {};
  // le pouce est posé par cinématique inverse sur la surface de l'objet, sans le traverser (il n'enveloppe pas)
  if (pr.doigts.includes("pouce") && pose.pouce) {
    const { q, pulpe } = anglesPouceObjet(obj, pose, pose.pouce);
    const P = cinematique("pouce", q).points, segs = [];
    for (let s = 0; s < 3; s++) {
      let mn = Infinity;
      for (let k = s === 0 ? 4 : 0; k <= 8; k++) mn = Math.min(mn, distanceObjet(obj, pose, add(P[s], sc(sub(P[s + 1], P[s]), k / 8))) - RAYON_DOIGT);
      if (mn < 0.003) segs.push(s);
    }
    if (pulpe < 0.003 && !segs.includes(2)) segs.push(2);
    out.pouce = { contact: segs.length > 0, segments: segs, segment: segs.length ? segs[segs.length - 1] : null, q };
  }
  for (const d of pr.doigts) {
    if (d === "pouce" && out.pouce) continue;
    const ordre = ORDRE[d === "pouce" ? "pouce" : "doigt"];
    const q = {}; for (const n of JOINTS[d === "pouce" ? "pouce" : "doigt"]) q[`${d}.${n}`] = qa[`${d}.${n}`];
    const touches = new Set();
    let libres = 0;                                       // indice du premier groupe d'articulations encore mobile
    const essai = (t, depart) => {                        // angles quand les groupes ≥ libres avancent de t
      const r = { ...q };
      for (let g = libres; g < 3; g++) for (const n of ordre[g]) { const k = `${d}.${n}`; r[k] = depart[k] + (qb[k] - depart[k]) * t; }
      return r;
    };
    for (let etape = 0; etape < 3 && libres < 3; etape++) {
      const depart = { ...q };
      const f = (t) => distanceDoigt(d, { ...qa, ...essai(t, depart) }, obj, pose, libres);   // segments encore mobiles
      // déjà au contact dès le départ (éminence thénar contre un gros objet) : ce segment s'arrête, la suite continue
      if (f(0).d <= 0) { const sg = f(0).segment; touches.add(sg); if (sg >= 2) break; libres = Math.max(libres + 1, sg + 1); continue; }
      let t0 = 0, t1 = null;
      for (let t = 0.04; t <= 1.0001; t += 0.04) { if (f(t).d <= 0) { t1 = t; break; } t0 = t; }
      if (t1 === null) { Object.assign(q, essai(1, depart)); const fin = f(1); if (fin.d < 0.003) touches.add(fin.segment); break; }
      for (let k = 0; k < 12; k++) { const m = (t0 + t1) / 2; if (f(m).d <= 0) t1 = m; else t0 = m; }
      Object.assign(q, essai(t0, depart));
      const seg = f(t1).segment;
      touches.add(seg);
      libres = Math.max(libres + 1, seg + 1);             // les articulations en amont du segment touché s'arrêtent
    }
    // l'IPD des doigts longs reste couplée aux deux tiers de l'IPP (Rijpkema et Girard), sauf si elle a touché
    if (d !== "pouce" && !touches.has(2)) q[`${d}.dip`] = Math.min(q[`${d}.dip`], (q[`${d}.pip`] * 2) / 3 + 5);
    const segs = [...touches].sort();
    out[d] = { contact: segs.length > 0, segments: segs, segment: segs.length ? segs[segs.length - 1] : null, q };
  }
  return { qa, qb, doigts: out, pose };
}

/* Force minimale de serrage pour tenir une charge (règle de frottement de Coulomb, deux faces opposées) :
   N ≥ m (g + a) / (2 μ). */
export const forceMinimale = (masse, mu, acceleration = 0) => (masse * (G + Math.max(0, acceleration))) / (2 * mu);

/* ── Main virtuelle : état, boucle perception-force-mouvement ──────────────────────── */
export class MainVirtuelle {
  constructor(cote = "d") {
    this.cote = cote;
    this.q = anglesPosture("repos");
    this.cible = { ...this.q };
    this.posture = "repos";
    this.prise = null;               // { nom, objet, obj, contacts, maniere, Ncmd, Napp, glisse, glissement, ... }
    this.toucher = null;             // contact avec le corps ou le partenaire sans prise : { capteurs:[ids], force }
    this.pianoter = 0;
    this.libre = true;               // vrai : la main suit la fermeture des gestes (compatibilité) ; faux : posture, prise ou toucher commandés
    this.t = 0;
    this.capteurs = Object.fromEntries(CAPTEURS.map((c) => [c.id, { contact: false, force: 0, pression: 0, glissement: false }]));
    this.evenements = [];
  }
  // file d'événements : ceux émis entre deux pas (commande prendre, lâcher…) sont rendus par le pas suivant
  evenement(niveau, msg) { (this.file = this.file || []).push({ niveau, msg, cote: this.cote, t: this.t }); }

  /* Posture des doigts (geste). Une prise en cours est conservée sauf pour « ouverte » (qui lâche). */
  prendrePosture(nom) {
    if (!POSTURES[nom]) return { ok: false, motif: `posture inconnue : ${nom}` };
    if (this.prise && nom !== "ouverte") return { ok: false, motif: `la main tient ${article(this.prise.obj)} : la lâcher d'abord` };
    if (this.prise) this.lacher("ouvre la main");
    this.posture = nom; this.pianoter = 0; this.cible = anglesPosture(nom); this.libre = false;
    return { ok: true };
  }
  pianoterDoigts(actif = true) { this.pianoter = actif ? 1 : 0; if (actif) { this.posture = "repos"; this.cible = anglesPosture("coupe"); this.libre = false; } return { ok: true }; }
  /* Rend la main aux gestes : elle suit de nouveau la fermeture (0-100) des gestes et des poses du corps. */
  liberer() { if (this.prise) return { ok: false, motif: `la main tient ${article(this.prise.obj)}` }; this.libre = true; this.pianoter = 0; this.toucher = null; this.posture = "repos"; return { ok: true }; }
  /* Compatibilité : une fermeture globale k (0-1) des gestes existants devient une posture (ouverte → repos →
     poing) ; « pointe » tend l'index (geste pointer). Sans effet si la main est commandée. */
  suivreFermeture(k, pointe = false) {
    if (!this.libre) return;
    const a = anglesPosture("ouverte"), r = anglesPosture("repos"), b = anglesPosture("poing"), q = {};
    for (const n of Object.keys(a)) q[n] = k < 0.15 ? a[n] + (r[n] - a[n]) * (k / 0.15) : r[n] + (b[n] - r[n]) * ((k - 0.15) / 0.85);
    if (pointe) { const p = anglesPosture("pointer"); for (const n of Object.keys(p)) if (n.startsWith("index.") || n.startsWith("pouce.")) q[n] = p[n]; }
    this.cible = q;
  }

  /* Saisir un objet (accessoire tendu dans la main, ou main du partenaire). */
  prendre(nomObjet, { prise = null, maniere = "normal" } = {}) {
    const obj = OBJETS[nomObjet];
    if (!obj) return { ok: false, motif: `objet inconnu : ${nomObjet}` };
    if (!MANIERES[maniere]) maniere = "normal";
    if (this.prise) this.lacher("nouvelle prise", { poser: true });
    const nom = prise && PRISES[prise] ? prise : obj.prise;
    const c = contacts(nom, obj);
    const touches = Object.values(c.doigts).filter((x) => x.contact).length;
    if (touches < 2 && maniere !== "effleurer") return { ok: false, motif: `prise « ${PRISES[nom].libelle} » impossible sur ${article(obj)} (moins de deux contacts)` };
    this.prise = { nom, objet: nomObjet, obj, c, maniere, Ncmd: 0, Napp: 0, glisse: 0, vGlisse: 0, glissement: false, reflexe: null, etablie: false, endommage: false, chute: false, depuis: this.t };
    this.posture = `prise:${nom}`; this.pianoter = 0; this.libre = false; this.toucher = null;
    this.cible = this.anglesPrise();
    this.evenement("info", `${this.cote === "g" ? "Main gauche" : "Main droite"} : ${PRISES[nom].libelle} sur ${article(obj)} (${MANIERES[maniere].libelle})`);
    return { ok: true, prise: nom, contacts: Object.fromEntries(Object.entries(c.doigts).map(([d, x]) => [d, x.contact])) };
  }
  /* Angles de la prise : chaque doigt s'arrête au contact ; la force commandée « enfonce » légèrement la
     cible au-delà du contact (raideur de la pulpe), ce qui ne change presque rien visuellement. */
  anglesPrise() {
    const { c } = this.prise, q = { ...anglesPosture(PRISES[this.prise.nom].depart) };
    for (const x of Object.values(c.doigts)) for (const [n, v] of Object.entries(x.q)) q[n] = borne(n, v);
    // doigts hors de la prise (crochet : le pouce ; pinces : les autres doigts) : repliés sans gêner
    for (const d of DOIGTS) if (!c.doigts[d]) Object.assign(q, Object.fromEntries(Object.entries(anglesPosture(d === "pouce" ? "repos" : "pince")).filter(([n]) => n.startsWith(`${d}.`))));
    return q;
  }
  regler(maniere) {
    if (!this.prise) return { ok: false, motif: "la main ne tient rien" };
    if (!MANIERES[maniere]) return { ok: false, motif: `manière inconnue : ${maniere}` };
    this.prise.maniere = maniere;
    return { ok: true };
  }
  /* Écraser volontairement (« froisse la lettre ») : la force dépasse le seuil de dommage, par intention. */
  ecraser() { if (!this.prise) return { ok: false, motif: "la main ne tient rien" }; this.prise.maniere = "fort"; this.prise.intention = true; return { ok: true }; }
  lacher(motif = "", { poser = false } = {}) {
    if (!this.prise) return { ok: false, motif: "la main ne tient rien" };
    const p = this.prise; this.dernierLacher = { objet: p.objet, poser: poser || !!p.obj.partenaire }; this.prise = null; this.posture = "ouverte"; this.cible = anglesPosture("ouverte"); this.libre = false;
    this.evenement("info", `${capitale(article(p.obj))} ${p.obj.partenaire ? "est relâchée" : poser ? `est posé${p.obj.genre === "f" ? "e" : ""}` : `est lâché${p.obj.genre === "f" ? "e" : ""}`}${motif ? ` (${motif})` : ""}`);
    return { ok: true, objet: p.objet, chute: !p.obj.partenaire };
  }
  /* Toucher sans prise (corps propre, partenaire effleuré) : capteurs et force normale (N). */
  definirToucher(t) { this.toucher = t; if (t && t.posture && !this.prise) { this.cible = anglesPosture(t.posture); this.posture = t.posture; this.libre = false; } }

  /* Un pas de la boucle. acceleration : accélération verticale de la main (m/s², vers le haut positive),
     fournie par la page à partir du mouvement du bras ; elle augmente la charge à tenir et elle est anticipée
     (la force de serrage la suit en parallèle, comme chez l'humain). imprevu : charge (N) non anticipée, par
     exemple un partenaire qui tire sur l'objet ; seul le réflexe de glissement y répond. */
  pas(dt, { acceleration = 0, imprevu = 0 } = {}) {
    this.t += dt;
    const ev = (this.evenements = (this.file || []).splice(0));
    // 1. mouvement : premier ordre vers la cible, vitesse bornée (300 °/s ; plus lent si délicat)
    const vit = 300 * (this.prise ? MANIERES[this.prise.maniere].vitesse : 1) * dt, k = 1 - Math.exp(-dt / 0.08);
    let cible = this.cible;
    if (this.pianoter) {
      cible = { ...cible };
      DOIGTS.slice(1).forEach((d, i) => {
        const ph = Math.max(0, Math.sin(this.t * 9 - i * 1.1)) * 35;
        cible[`${d}.mcp`] += ph; cible[`${d}.pip`] += ph * 0.4; cible[`${d}.dip`] += ph * 0.27;
      });
    }
    for (const n of NOMS_ARTICULATIONS) {
      if (!(n in cible)) continue;
      const e = cible[n] - this.q[n];
      this.q[n] = borne(n, this.q[n] + clamp(e * k, -vit, vit));
    }
    asservir(this.q, cible);
    // 2. perception et 3. force
    for (const c of Object.values(this.capteurs)) { c.contact = false; c.force = 0; c.pression = 0; c.glissement = false; }
    if (this.prise) this.pasPrise(dt, acceleration, imprevu);
    else if (this.toucher && this.toucher.poids > 0.6) {
      const ids = this.toucher.capteurs.filter((id) => this.capteurs[id]);
      for (const id of ids) {
        const f = (this.toucher.force * this.toucher.poids) / Math.max(1, ids.length);
        this.capteurs[id] = { contact: true, force: f, pression: f / CAPTEURS.find((c) => c.id === id).aire, glissement: false };
      }
    }
    ev.push(...(this.file || []).splice(0));
    return ev;
  }
  pasPrise(dt, acceleration, imprevu = 0) {
    const p = this.prise, M = MANIERES[p.maniere], o = p.obj;
    // fermeture atteinte ? (les doigts sont arrivés au contact)
    const cible = this.anglesPrise();
    let ecart = 0;
    for (const n of Object.keys(cible)) ecart = Math.max(ecart, Math.abs(cible[n] - this.q[n]));
    const ferme = ecart < 6;
    // force minimale pour la charge (feedforward : accélération prévue incluse) et force commandée
    const Nmin = forceMinimale(o.masse, o.mu, acceleration);
    const plafondDommage = p.intention ? Infinity : o.dommage * M.plafond;
    let Nvoulu = p.maniere === "effleurer" ? M.plancher : Math.max(M.plancher, Nmin * (1 + M.marge + (p.reflexe?.applique ? p.reflexe.bonus : 0)));
    Nvoulu = Math.min(Nvoulu, plafondDommage, FORCE_MAX_MAIN);
    // la force monte quand les doigts sont au contact (constante de temps 0,1 s)
    p.Ncmd = ferme ? p.Ncmd + (Nvoulu - p.Ncmd) * (1 - Math.exp(-dt / 0.1)) : Math.max(0, p.Ncmd * 0.5);
    p.Napp = p.Ncmd;
    // l'objet est tendu par un accessoiriste (ou tenu par le partenaire) jusqu'à ce que la prise soit établie
    if (!p.etablie && ferme && p.Ncmd >= 0.9 * Nvoulu) { p.etablie = true; if (!p.intention) this.evenement("info", `Prise établie : ${p.Napp.toFixed(1)} N (minimum ${forceMinimale(o.masse, o.mu).toFixed(1)} N)`); }
    // glissement : charge supérieure au frottement disponible (Coulomb, deux faces)
    const charge = o.masse * (G + Math.max(0, acceleration)) + imprevu;
    const tenue = 2 * o.mu * p.Napp;
    const glisse = p.etablie && charge > 0 && charge > tenue;
    if (glisse) {
      // m/s, l'objet glisse dans la main ; la pulpe, souple, freine le glissement (amortissement 30 /s, Inférence)
      const v = p.vGlisse || 0;
      p.vGlisse = v + ((charge - tenue) / Math.max(o.masse, 0.3) - 30 * v) * dt;
      p.glisse += p.vGlisse * dt;
      if (!p.glissement) {
        this.evenement("avert", `${capitale(article(o))} glisse dans la main ${this.cote === "g" ? "gauche" : "droite"}`);
        p.reflexe = { depuis: this.t, bonus: p.reflexe?.bonus || 0, applique: false };
      }
    } else p.vGlisse = 0;
    p.glissement = glisse;
    // réflexe de glissement : la marge est relevée 74 ms après le début du glissement (Johansson et Westling 1987)
    if (p.reflexe && !p.reflexe.applique && !p.chute && this.t - p.reflexe.depuis >= LATENCE_GLISSEMENT) {
      p.reflexe.applique = true; p.reflexe.bonus += 0.6;
      this.evenement("info", `Glissement senti : serrage relevé après ${Math.round(LATENCE_GLISSEMENT * 1000)} ms (marge + 60 %)`);
    }
    if (p.glisse > 0.04 && !p.chute) {
      p.chute = true;
      const cause = imprevu > 0 ? "on la lui arrache" : Nvoulu >= plafondDommage ? "serrage plafonné sous son seuil de dommage" : "serrage trop lent pour la charge";
      this.evenement("alerte", `${capitale(article(o))} échappe à la main (${cause})`);
    }
    // dommage (intention, ou manière « de toutes ses forces »)
    if (!p.endommage && p.Napp > o.dommage) {
      p.endommage = true;
      if (o.effet) this.evenement(p.intention ? "info" : "alerte", `${capitale(article(o))} ${o.effet}`);
    }
    // répartition sur les capteurs : moitié côté pouce (ou paume), moitié côté doigts ; selon les contacts
    const C = Object.entries(p.c.doigts).filter(([, x]) => x.contact);
    const pouce = C.find(([d]) => d === "pouce"), autres = C.filter(([d]) => d !== "pouce");
    const N = ferme ? p.Napp : 0;
    const poser = (id, f) => {
      const cap = CAPTEURS.find((c) => c.id === id);
      const s = this.capteurs[id];
      s.contact = s.contact || f > 0.01 || ferme; s.force += f; s.pression = s.force / cap.aire; s.glissement = p.glissement;
    };
    const capteurDe = (d, seg) => (p.nom === "laterale" && d === "index" ? "phalange_index"
      : d === "pouce" || seg === 2 || seg === null ? `pulpe_${d}` : `phalange_${d}`);
    if (PRISES[p.nom].paume) {
      poser("paume", N * (pouce ? 0.35 : 0.5));
      if (pouce) poser(capteurDe("pouce", pouce[1].segment), N * 0.15);
    } else if (pouce) poser(capteurDe("pouce", pouce[1].segment), N * 0.5);
    const poids = { index: 1, majeur: 1, annulaire: 0.85, auriculaire: 0.6 };
    const tot = autres.reduce((a, [d]) => a + poids[d], 0) || 1;
    for (const [d, x] of autres) {
      const f = (N * 0.5 * poids[d]) / tot, segs = x.segments.filter((g) => g >= 1);
      if (segs.includes(1) && segs.includes(2)) { poser(`phalange_${d}`, f * 0.45); poser(`pulpe_${d}`, f * 0.55); }
      else poser(capteurDe(d, x.segment), f);
    }
  }

  /* Fermeture globale (0-100) : moyenne des flexions, pour le jumeau à pince du TonyPi Pro. */
  fermeture() {
    let s = 0;
    for (const d of DOIGTS.slice(1)) s += (this.q[`${d}.mcp`] / 90 + this.q[`${d}.pip`] / 105) / 2;
    return Math.round(clamp(s / 4, 0, 1) * 100);
  }
  /* Résumé pour l'interface et le journal. */
  etat() {
    const p = this.prise;
    return {
      cote: this.cote, posture: this.posture,
      prise: p ? { nom: p.nom, libelle: PRISES[p.nom].libelle, objet: p.objet, maniere: p.maniere, force: +p.Napp.toFixed(2),
                   minimale: +forceMinimale(p.obj.masse, p.obj.mu).toFixed(2), glissement: p.glissement, endommage: p.endommage, chute: p.chute } : null,
      capteurs: Object.fromEntries(Object.entries(this.capteurs).map(([k, c]) => [k, { contact: c.contact, force: +c.force.toFixed(2), pression_kpa: +(c.pression / 1000).toFixed(1), glissement: c.glissement }])),
      fermeture: this.fermeture(),
    };
  }
}

/* Asservissement des doigts voisins (Zatsiorsky et al.) : un doigt fortement fléchi entraîne ses voisins
   commandés en extension, d'une fraction de l'écart. (Inférence) Coefficients réduits : la posture voulue reste
   lisible (annulaire-majeur 0,12, annulaire-auriculaire 0,12, autres voisins 0,06). */
const VOISINS = [["index", "majeur", 0.06], ["majeur", "annulaire", 0.12], ["annulaire", "auriculaire", 0.12]];
function asservir(q, cible) {
  for (const [a, b, c] of VOISINS) {
    for (const [x, y] of [[a, b], [b, a]]) {
      const e = (cible[`${x}.mcp`] ?? 0) - (cible[`${y}.mcp`] ?? 0);
      if (e > 40) q[`${y}.mcp`] = borne(`${y}.mcp`, Math.max(q[`${y}.mcp`], (cible[`${y}.mcp`] ?? 0) + e * c));
    }
  }
}

export const article = (o) => (/^[aeéèiouyhâ]/i.test(o.libelle) ? `l'${o.libelle}` : `${o.genre === "f" ? "la" : "le"} ${o.libelle}`);
const capitale = (t) => t.charAt(0).toUpperCase() + t.slice(1);

/* Toucher du corps propre ou du partenaire : capteurs sollicités selon le point de la main, et force (N) selon la
   manière. (Inférence) forces de conception : effleurement 0,2 N ; délicat 0,6 N ; normal 1,5 N ; appuyé 5 N. */
export const FORCES_TOUCHER = { effleurer: 0.2, delicat: 0.6, normal: 1.5, ferme: 5, fort: 12 };
export const CAPTEURS_POINT = {
  paume: ["paume"], index: ["pulpe_index"], doigts: ["pulpe_index", "pulpe_majeur", "pulpe_annulaire"],
  poing: [], dos: [], avantbras: [],
};
