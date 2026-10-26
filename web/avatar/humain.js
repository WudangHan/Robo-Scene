/* Robo-Scène — style « humain » du robot virtuel (25 oct. 2026).
   Corps humain issu de MakeHuman (CC0 ; outils/humain/construire_humain.py) : maillage à peau continue, lié par
   habillage (SkinnedMesh) au squelette du robot. Chaque nœud (bassin, tronc, cou, tête, bras, mains, 15 phalanges
   par main, jambes, pieds) suit exactement le groupe three.js correspondant de humanoide.js, ou la phalange
   calculée par mains.js ; la mâchoire, les paupières et les yeux suivent le visage animé. Peau, cheveux,
   sourcils, lèvres et vêtements sont peints par sommet, selon l'apparence (tons Monk, habillages). */
import * as THREE from "three";
import { DOIGTS, cinematique } from "./mains.js";

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const TYPES = { float32: Float32Array, uint8: Uint8Array, uint32: Uint32Array, uint16: Uint16Array };

/* Échelle de tons de peau de Monk (Ellis Monk ; Google, 2022 ; CC BY 4.0) : Monk 01 à Monk 10. */
export const TONS_MONK = ["#f6ede4", "#f3e7db", "#f7ead0", "#eadaba", "#d7bd96", "#a07e56", "#825c43", "#604134", "#3a312a", "#292420"];

export async function chargerCorpsHumain(base = "/static/avatar/humain/") {
  const [meta, bin] = await Promise.all([fetch(`${base}corps.json`).then((r) => r.json()), fetch(`${base}corps.bin`).then((r) => r.arrayBuffer())]);
  const t = {};
  for (const [nom, d] of Object.entries(meta.tableaux)) {
    const C = TYPES[d.type];
    const n = d.forme.reduce((a, b) => a * b, 1);
    t[nom] = new C(bin, d.offset, n);
  }
  return { meta, t };
}

/* Subdivision par milieux d'arêtes des triangles choisis (choisir(region, y) vrai pour leurs trois sommets) ; les
   triangles voisins sont coupés en deux ou en trois pour ne laisser aucune fente. Les influences des deux sommets
   d'une arête sont fusionnées (quatre plus fortes, renormalisées). */
function subdiviser(t, choisir) {
  const P = Array.from(t.position), N = Array.from(t.normale), UV = Array.from(t.uv), J = Array.from(t.noeud), W = Array.from(t.poids), R = Array.from(t.region);
  const I = t.indice, nt = I.length / 3, marque = new Set(), cle = (a, b) => (a < b ? a * 4194304 + b : b * 4194304 + a);
  const choisi = (v) => choisir(R[v], P[3 * v + 1]);
  for (let f = 0; f < nt; f++) {
    const [a, b, c] = [I[3 * f], I[3 * f + 1], I[3 * f + 2]];
    if (choisi(a) && choisi(b) && choisi(c)) { marque.add(cle(a, b)); marque.add(cle(b, c)); marque.add(cle(c, a)); }
  }
  const milieux = new Map();
  const milieu = (a, b) => {
    const k = cle(a, b); if (milieux.has(k)) return milieux.get(k);
    const v = R.length;
    for (let j = 0; j < 3; j++) P.push((P[3 * a + j] + P[3 * b + j]) / 2);
    const n = [0, 1, 2].map((j) => N[3 * a + j] + N[3 * b + j]), l = Math.hypot(...n) || 1; N.push(n[0] / l, n[1] / l, n[2] / l);
    UV.push((UV[2 * a] + UV[2 * b]) / 2, (UV[2 * a + 1] + UV[2 * b + 1]) / 2);
    const inf = new Map();
    for (const s of [a, b]) for (let j = 0; j < 4; j++) if (W[4 * s + j] > 0) inf.set(J[4 * s + j], (inf.get(J[4 * s + j]) || 0) + W[4 * s + j] / 2);
    const top = [...inf].sort((x, y) => y[1] - x[1]).slice(0, 4), somme = top.reduce((x, y) => x + y[1], 0) || 1;
    for (let j = 0; j < 4; j++) { J.push(top[j] ? top[j][0] : 0); W.push(top[j] ? top[j][1] / somme : 0); }
    R.push(R[a]); milieux.set(k, v); return v;
  };
  const out = [];
  for (let f = 0; f < nt; f++) {
    let v = [I[3 * f], I[3 * f + 1], I[3 * f + 2]];
    const m = [0, 1, 2].map((i) => marque.has(cle(v[i], v[(i + 1) % 3])));
    const n = m.filter(Boolean).length;
    if (n === 0) { out.push(...v); continue; }
    if (n === 3) {
      const [a, b, c] = v, ab = milieu(a, b), bc = milieu(b, c), ca = milieu(c, a);
      out.push(a, ab, ca, ab, b, bc, ca, bc, c, ab, bc, ca); continue;
    }
    // rotation : n = 1 → l'arête marquée devient (v0, v1) ; n = 2 → l'arête non marquée devient (v2, v0)
    const r = n === 1 ? m.indexOf(true) : (m.indexOf(false) + 1) % 3;
    v = [v[r], v[(r + 1) % 3], v[(r + 2) % 3]];
    const [a, b, c] = v, ab = milieu(a, b);
    if (n === 1) out.push(a, ab, c, ab, b, c);
    else { const bc = milieu(b, c); out.push(ab, b, bc, a, ab, bc, a, bc, c); }
  }
  return { ...t, position: Float32Array.from(P), normale: Float32Array.from(N), uv: Float32Array.from(UV), noeud: Uint8Array.from(J),
           poids: Float32Array.from(W), region: Uint8Array.from(R), indice: Uint32Array.from(out) };
}

/* Repère d'une phalange : x = direction du segment, y = normale palmaire orthogonalisée, z = x × y. */
function repere(dir, palmaire) {
  const x = dir.clone().normalize();
  const y = palmaire.clone().addScaledVector(x, -palmaire.dot(x)).normalize();
  const z = new THREE.Vector3().crossVectors(x, y);
  return new THREE.Matrix4().makeBasis(x, y, z);
}

export class CorpsHumain {
  constructor(humanoide, donnees) {
    this.h = humanoide;
    const { meta } = donnees;
    // maillage affiné au chargement (25 oct. 2026) : un niveau partout, un second sur les pieds et le bas des jambes,
    // pour que les motifs fins (lacets, bandes, liserés) restent nets ; le fichier téléchargé ne grossit pas
    const cy = Math.max(meta.pivots.cheville_g[1], meta.pivots.cheville_d[1]) + 0.2;
    let t = subdiviser(donnees.t, () => true);
    t = subdiviser(t, (r, y) => r === 10 || (r === 9 && y < cy));
    this.meta = meta;
    this.noeuds = meta.noeuds;
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(t.position, 3));
    g.setAttribute("normal", new THREE.BufferAttribute(t.normale, 3));
    g.setAttribute("uv", new THREE.BufferAttribute(t.uv, 2));
    g.setAttribute("skinIndex", new THREE.Uint16BufferAttribute(Uint16Array.from(t.noeud), 4));
    g.setAttribute("skinWeight", new THREE.BufferAttribute(t.poids, 4));
    this.couleurs = new Float32Array(t.position.length);
    g.setAttribute("color", new THREE.BufferAttribute(this.couleurs, 3));
    g.setIndex(new THREE.BufferAttribute(t.indice, 1));
    this.region = t.region;
    this.repos = t.position;
    // (pas de lustre « sheen » global : il teintait de rose les vêtements et les chaussures sombres)
    this.mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.58, metalness: 0 });
    // coupes du maillot calculées par pixel (encolure, emmanchures, liserés, couture, ourlets) : bords nets quelle que
    // soit la taille des triangles ; les couleurs par sommet portent alors le tissu sans les coupes (peindre, this.gpu)
    // zones (tronc, cou et bras, cuisse) en indicateurs 0/1 : interpolés, ils ne passent jamais par une autre région
    g.setAttribute("aZones", new THREE.BufferAttribute(Float32Array.from(Array.from(t.region, (r) => [r === 2 || r === 3 ? 1 : 0, r === 5 ? 1 : 0, r === 8 ? 1 : 0, r === 1 ? 1 : 0]).flat()), 4));
    this.uniformes = { uSans: { value: 0 }, uSinglet: { value: 0 }, uCuissard: { value: 0 }, uCouture: { value: 0 }, uYs: { value: 1.42 },
      uOurlet: { value: 0.6 }, uPeau: { value: new THREE.Color() }, uLiser: { value: new THREE.Color() }, uOurletC: { value: new THREE.Color() } };
    this.gpu = typeof document !== "undefined";
    this.mat.onBeforeCompile = (sh) => {
      Object.assign(sh.uniforms, this.uniformes);
      sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nattribute vec4 aZones;\nvarying vec3 vRepos;\nvarying vec4 vZones;")
        .replace("#include <begin_vertex>", "#include <begin_vertex>\nvRepos = position; vZones = aZones;");
      sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\n" + GLSL_COUPES)
        .replace("#include <color_fragment>", "#include <color_fragment>\ncouperMaillot(diffuseColor.rgb);");
    };
    this.os = this.noeuds.map(() => { const b = new THREE.Bone(); b.matrixAutoUpdate = false; return b; });
    this.mesh = new THREE.SkinnedMesh(g, this.mat);
    this.mesh.name = "corps-humain"; this.mesh.frustumCulled = false; this.mesh.castShadow = true; this.mesh.receiveShadow = true;
    this.mesh.bindMode = THREE.DetachedBindMode;
    this.mesh.bind(new THREE.Skeleton(this.os, this.os.map(() => new THREE.Matrix4())), new THREE.Matrix4());
    // les os n'ont pas de parent : leur matrice monde est posée directement à chaque image
    for (const b of this.os) b.updateMatrixWorld = () => {};
    this.construireYeux(t);
    this.construireGalbe();
    this.visible = false;
    this.mesh.visible = false;
    humanoide.racine.add(this.mesh);
  }

  /* Silhouette masculine sous le vêtement (25 oct. 2026) : volume ellipsoïdal à l'avant du bassin, toujours de la
     couleur du bas, lié au bassin et aux deux hanches (il suit la marche et les flexions). */
  construireGalbe() {
    const G = this.meta.galbe;
    if (!G?.centre) return;
    const geo = new THREE.SphereGeometry(1, 28, 20);
    // forme en goutte : plus large et plus pleine vers le bas, effilée vers le haut où elle se fond dans le bassin
    const p0 = geo.attributes.position;
    for (let k = 0; k < p0.count; k++) { const y = p0.getY(k); const f = y < 0 ? 1 + 0.18 * -y : 1 - 0.3 * y; p0.setX(k, p0.getX(k) * f); p0.setZ(k, p0.getZ(k) * (y > 0 ? 1 - 0.45 * y : 1)); }
    geo.computeVertexNormals();
    geo.scale(...G.rayons); geo.rotateX(G.inclinaison || 0); geo.translate(...G.centre);
    const n = geo.attributes.position.count, iBassin = this.noeuds.indexOf("bassin"), ig = this.noeuds.indexOf("hanche_g"), id = this.noeuds.indexOf("hanche_d");
    const si = new Uint16Array(n * 4), sw = new Float32Array(n * 4);
    for (let k = 0; k < n; k++) { si.set([iBassin, ig, id, 0], 4 * k); sw.set([0.7, 0.15, 0.15, 0], 4 * k); }
    geo.setAttribute("skinIndex", new THREE.Uint16BufferAttribute(si, 4)); geo.setAttribute("skinWeight", new THREE.BufferAttribute(sw, 4));
    this.matGalbe = new THREE.MeshStandardMaterial({ roughness: 0.58 });
    const m = new THREE.SkinnedMesh(geo, this.matGalbe); m.name = "corps-humain-galbe"; m.frustumCulled = false; m.castShadow = true;
    m.bindMode = THREE.DetachedBindMode; m.bind(this.mesh.skeleton, new THREE.Matrix4()); m.visible = false;
    this.h.racine.add(m); this.galbe = m;
  }

  construireYeux(t) {
    // deux yeux (maillage « high-poly » de MakeHuman), chacun dans un pivot centré sur l'œil, rattaché à la tête
    this.yeux = {};
    this.matIris = new THREE.MeshPhysicalMaterial({ map: textureIris("#4a3220"), roughness: 0.25, clearcoat: 0.9, clearcoatRoughness: 0.05, alphaTest: 0.5 });
    for (const [s, c] of [["g", 0], ["d", 1]]) {
      const idx = [], map = new Map();
      for (let i = 0; i < t.yeux_cote.length; i++) if (t.yeux_cote[i] === c) { map.set(i, idx.length); idx.push(i); }
      const pos = new Float32Array(idx.length * 3), uv = new Float32Array(idx.length * 2);
      const centre = new THREE.Vector3(...this.meta.pivots[`oeil_${s}`]);
      idx.forEach((i, k) => { pos.set([t.yeux_position[3 * i] - centre.x, t.yeux_position[3 * i + 1] - centre.y, t.yeux_position[3 * i + 2] - centre.z], 3 * k); uv.set([t.yeux_uv[2 * i], t.yeux_uv[2 * i + 1]], 2 * k); });
      const ind = [];
      for (let i = 0; i < t.yeux_indice.length; i += 3) {
        const a = map.get(t.yeux_indice[i]), b = map.get(t.yeux_indice[i + 1]), d = map.get(t.yeux_indice[i + 2]);
        if (a !== undefined && b !== undefined && d !== undefined) ind.push(a, b, d);
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
      g.setIndex(ind); g.computeVertexNormals();
      const m = new THREE.Mesh(g, this.matIris); m.name = `oeil_humain_${s}`;
      const pivot = new THREE.Group(); pivot.add(m); pivot.visible = false;
      this.yeux[s] = { pivot, centre };
    }
  }

  /* Active ou désactive le style humain : proportions du squelette, visibilité, rattachement des yeux. */
  activer(oui) {
    const h = this.h, O = h.os;
    this.visible = oui;
    this.mesh.visible = oui;
    for (const nom of ["cheveux", "sourcils", "barbe", "galbe"]) if (this[nom]) this[nom].visible = oui;
    h.proportions(oui ? this.meta : null);
    // repos du squelette (degrés de liberté nuls), mémorisé pour l'habillage
    h.appliquer({}, { ancrage: false, sansHumain: true }); h.racine.position.set(0, 0, 0); h.racine.rotation.set(0, 0, 0);
    h.racine.updateMatrixWorld(true);
    this.repos0 = {};
    for (const n of this.noeuds) { const G = this.groupe(n); if (G) this.repos0[n] = G.matrixWorld.clone(); }
    this.reposMains = { g: this.reperesMain("g", true), d: this.reperesMain("d", true) };
    h.visage.g.updateWorldMatrix(true, false); this.visageRepos = h.visage.g.matrixWorld.clone();   // sangles du protège-oreilles
    for (const s of ["g", "d"]) {
      const y = this.yeux[s];
      if (oui) { O.tete.add(y.pivot); y.pivot.position.copy(O.tete.worldToLocal(y.centre.clone())); y.pivot.visible = true; }
      else y.pivot.removeFromParent();
    }
    this.mainsRepos = null;
    this.peindre();
  }

  groupe(n) {
    const O = this.h.os;
    const m = /^(clav|epaule|coude|main|hanche|genou|cheville)_([gd])$/.exec(n);
    if (m) return m[1] === "main" ? O[`poignet_${m[2]}`] : O[n];
    return { bassin: O.bassin, lombaires: O.lombaires, poitrine: O.poitrine, cou: O.cou, tete: O.tete }[n] || null;
  }

  /* Repères des 15 phalanges d'une main : au repos MakeHuman (liaison) ou selon les angles courants (mains.js). */
  reperesMain(s, liaison) {
    const piv = this.meta.pivots, out = {};
    const V = (k) => new THREE.Vector3(...piv[k]);
    if (liaison) {
      const poignet = V(`main_${s}`), idx = V(`index0_${s}`), auri = V(`auriculaire0_${s}`);
      let n = new THREE.Vector3().crossVectors(idx.clone().sub(poignet), auri.clone().sub(poignet)).normalize();
      if (n.x * (s === "g" ? -1 : 1) < 0) n.negate();                // paume vers le corps au repos
      for (const d of DOIGTS) for (let k = 0; k < 3; k++) {
        const a = V(`${d}${k}_${s}`), b = V(`${d}${k + 1}_${s}`);
        out[`${d}${k}_${s}`] = { p: a, R: repere(b.clone().sub(a), n) };
      }
      return out;
    }
    const R = this.h.mainsRendu[s], x = R.x;
    const M = R.main.matrixWorld, rot = new THREE.Matrix4().extractRotation(M);
    const loc = (p) => new THREE.Vector3(-x * p[0], -p[1], p[2]).applyMatrix4(M);
    const n = new THREE.Vector3(-x, 0, 0).applyMatrix4(rot).normalize();
    const q = this.h.anglesMains?.[s];
    if (!q) return null;
    for (const d of DOIGTS) {
      const pts = cinematique(d, q).points.map(loc);
      for (let k = 0; k < 3; k++) out[`${d}${k}_${s}`] = { p: pts[k], R: repere(pts[k + 1].clone().sub(pts[k]), n) };
    }
    return out;
  }

  /* À chaque image, après humanoide.appliquer : matrices des os = déplacement de chaque nœud depuis le repos. */
  maj() {
    if (!this.visible) return;
    const h = this.h;
    h.racine.updateMatrixWorld(true);
    const inv = new THREE.Matrix4().copy(h.racine.matrixWorld).invert();
    const mains = { g: this.reperesMain("g", false), d: this.reperesMain("d", false) };
    const tmp = new THREE.Matrix4(), tmp2 = new THREE.Matrix4();
    this.noeuds.forEach((n, i) => {
      const b = this.os[i];
      const G = this.groupe(n);
      if (G) { b.matrixWorld.multiplyMatrices(inv, G.matrixWorld).multiply(tmp.copy(this.repos0[n]).invert()); return; }
      const ph = /^(pouce|index|majeur|annulaire|auriculaire)([0-2])_([gd])$/.exec(n);
      if (ph) {
        const s = ph[3], cur = mains[s]?.[n], rep = this.reposMains[s][n];
        if (!cur) { b.matrixWorld.multiplyMatrices(inv, this.groupe(`main_${s}`).matrixWorld).multiply(tmp.copy(this.repos0[`main_${s}`]).invert()); return; }
        // T(p_courant) · R_courant · R_liaison⁻¹ · T(−p_liaison), dans le repère de la racine
        tmp.copy(cur.R).setPosition(cur.p);
        tmp2.copy(rep.R).setPosition(rep.p).invert();
        b.matrixWorld.multiplyMatrices(inv, tmp).multiply(tmp2);
        return;
      }
      if (n === "machoire" || n.startsWith("paupiere_")) {
        const s = n.endsWith("_g") ? "g" : "d";
        const piv = new THREE.Vector3(...(n === "machoire" ? this.meta.pivots.machoire : this.meta.pivots[`oeil_${s}`]));
        const ang = n === "machoire" ? this.machoire || 0 : this.paupieres?.[s] || 0;
        const local = new THREE.Matrix4().makeTranslation(piv.x, piv.y, piv.z).multiply(new THREE.Matrix4().makeRotationX(ang)).multiply(new THREE.Matrix4().makeTranslation(-piv.x, -piv.y, -piv.z));
        b.matrixWorld.multiplyMatrices(inv, h.os.tete.matrixWorld).multiply(tmp.copy(this.repos0.tete).invert()).multiply(local);
      }
    });
  }

  /* Visage : mâchoire (ouverture de la bouche), paupières (clignement), regard (rotation des yeux). */
  majVisage(au, regard, bouche) {
    if (!this.visible) return;
    const A = (k) => au[k] || 0;
    const jaw = clamp(Math.max(A("au26") * 0.75 + A("au25") * 0.12 + A("au27"), bouche?.jaw || 0), 0, 1);
    this.machoire = 0.32 * jaw;                                   // rad, rotation vers le bas autour de l'articulation
    this.paupieres = {};
    for (const s of ["g", "d"]) {
      const f = clamp(Math.max(A("au43"), A("clignement"), A(`au46_${s}`)) + 0.25 * Math.max(A("au7"), A(`au7_${s}`)), 0, 1);
      this.paupieres[s] = 0.42 * f;
      this.yeux[s].pivot.rotation.set(-regard.pitch, regard.yaw, 0);
    }
  }

  /* Coques (cheveux, sourcils, barbe) : triangles de la peau dont les trois sommets sont dans le masque, décalés
     le long de la normale, avec le même habillage que la peau (ils suivent la tête et la mâchoire). */
  coque(nom, masque, epaisseur, materiau) {
    const g0 = this.mesh.geometry, I = g0.index.array, N = g0.attributes.normal.array;
    if (this[nom]) { this[nom].removeFromParent(); this[nom].geometry.dispose(); this[nom] = null; }
    const garde = [];
    for (let i = 0; i < I.length; i += 3) if (masque[I[i]] && masque[I[i + 1]] && masque[I[i + 2]]) garde.push(I[i], I[i + 1], I[i + 2]);
    if (!garde.length) return;
    const map = new Map(), ids = [];
    for (const v of garde) if (!map.has(v)) { map.set(v, ids.length); ids.push(v); }
    const pos = new Float32Array(ids.length * 3), nrm = new Float32Array(ids.length * 3), si = new Uint16Array(ids.length * 4), sw = new Float32Array(ids.length * 4);
    const P = this.repos, SI = g0.attributes.skinIndex.array, SW = g0.attributes.skinWeight.array;
    ids.forEach((v, k) => {
      const e = typeof epaisseur === "function" ? epaisseur(v) : epaisseur;
      for (let j = 0; j < 3; j++) { pos[3 * k + j] = P[3 * v + j] + N[3 * v + j] * e; nrm[3 * k + j] = N[3 * v + j]; }
      for (let j = 0; j < 4; j++) { si[4 * k + j] = SI[4 * v + j]; sw[4 * k + j] = SW[4 * v + j]; }
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.setAttribute("normal", new THREE.BufferAttribute(nrm, 3));
    g.setAttribute("skinIndex", new THREE.Uint16BufferAttribute(si, 4)); g.setAttribute("skinWeight", new THREE.BufferAttribute(sw, 4));
    g.setIndex(garde.map((v) => map.get(v)));
    const m = new THREE.SkinnedMesh(g, materiau); m.name = `corps-humain-${nom}`; m.frustumCulled = false; m.castShadow = true;
    m.bindMode = THREE.DetachedBindMode; m.bind(this.mesh.skeleton, new THREE.Matrix4());
    this.h.racine.add(m); this[nom] = m;
  }

  /* Peinture par sommet : peau (ton Monk ou teinte nommée), cheveux, sourcils, lèvres, barbe, vêtements. */
  peindre() {
    if (!this.visible) return;
    const h = this.h, A = h.apparence, C = h.schema.apparence.couleurs;
    const col = (n, d) => new THREE.Color(/^#/.test(n || "") ? n : C[n] || d);
    const peau = new THREE.Color().copy(h.mat.peau.color);
    const cheveux = new THREE.Color().copy(h.mat.cheveux.color), sourcils = new THREE.Color().copy(h.mat.sourcils.color);
    const levres = peau.clone().lerp(new THREE.Color("#9e4a46"), 0.38);
    const haut = col(A.haut, "#1f2b4a"), bas = col(A.bas, "#7d8086"), chaus = col(A.chaussures, "#1b1b1d"), acc = col(A.accessoire, "#6d1f2a");
    const P = this.meta.pivots, oe = new THREE.Vector3(...P.oeil_g).add(new THREE.Vector3(...P.oeil_d)).multiplyScalar(0.5);
    const ys = (P.epaule_g[1] + P.epaule_d[1]) / 2, genou = (P.genou_g[1] + P.genou_d[1]) / 2, cheville = (P.cheville_g[1] + P.cheville_d[1]) / 2;
    const singlet = A.manches === "sans" && A.coupe_bas === "cuissard";
    // modèle de chaussures de lutte (25 oct. 2026) : couleurs et motif peints sur le pied et la tige
    const modele = h.schema.apparence.modeles_chaussures?.[A.modele_chaussures];
    const chaussure = modele?.couleurs ? peintreChaussure(modele, P, cheville) : null;
    const montantes = A.chaussures_montantes || !!chaussure, hauteurTige = chaussure ? modele.hauteur : 0.1;
    // modèle de maillot de lutte (25 oct. 2026) : tissu, motif et liserés peints sur le tronc, le bassin et les cuisses
    const mm = singlet ? h.schema.apparence.modeles_maillot?.[A.modele_maillot] : null;
    const maillot = mm?.couleurs ? peintreMaillot(mm, P, ys) : null;
    const liser = maillot ? new THREE.Color(mm.couleurs.liseres) : acc, ourl = maillot ? new THREE.Color(mm.couleurs.ourlets || mm.couleurs.liseres) : acc;
    const couture = mm?.motif === "nuages";
    const U = this.uniformes;
    U.uSans.value = A.manches === "sans" ? 1 : 0; U.uSinglet.value = singlet ? 1 : 0; U.uCuissard.value = A.coupe_bas === "cuissard" ? 1 : 0;
    U.uCouture.value = couture ? 1 : 0; U.uYs.value = ys; U.uOurlet.value = genou + 0.12;
    U.uPeau.value.copy(peau); U.uLiser.value.copy(liser); U.uOurletC.value.copy(ourl);
    const c = this.couleurs, r = this.region, p = this.repos;
    const tmp = new THREE.Color();
    const nv = r.length, mCheveux = new Uint8Array(nv), mSourcils = new Uint8Array(nv), mBarbe = new Uint8Array(nv);
    for (let i = 0; i < r.length; i++) {
      const x = p[3 * i], y = p[3 * i + 1], z = p[3 * i + 2], reg = r[i];
      let k = peau;
      const ax = Math.abs(x), dy = y - oe.y, dz = z - oe.z;
      const trapeze = reg === 1 && A.manches === "sans" && ax > 0.048 && y < ys + 0.125;   // bretelles sur les trapèzes
      if (reg === 0 || (reg === 1 && !trapeze)) {
        // cheveux : au-dessus d'une ligne qui descend du front vers la nuque
        const seuil = dz > -0.01 ? 0.05 : dz < -0.11 ? -0.085 : 0.05 - (0.135 * (-0.01 - dz)) / 0.1;
        const calvitie = A.cheveux === "chauve" ? 0 : A.cheveux === "rasé" ? 0.45 : 1;
        if (reg === 0 && dy > seuil && calvitie > 0 && !(ax > 0.072 && dy < 0.02 && dz > -0.09)) { k = tmp.copy(peau).lerp(cheveux, calvitie); mCheveux[i] = 1; }
        else if (reg === 0 && dy > 0.012 && dy < 0.027 && ax > 0.01 && ax < 0.052 && dz > -0.03) { k = sourcils; mSourcils[i] = 1; }   // sourcils
        else if (reg === 0 && Math.abs(dy + 0.071) < 0.0075 && ax < 0.024 && dz > -0.02) k = levres;                       // lèvres
        else if (reg === 0 && A.barbe !== "aucune" && dy < -0.05 && dz > -0.09 && !(Math.abs(dy + 0.071) < 0.009 && ax < 0.026))
          { k = tmp.copy(peau).lerp(cheveux, A.barbe === "pleine" ? 0.9 : 0.45); mBarbe[i] = 1; }
      } else if (reg === 2 || reg === 3 || trapeze) {
        k = haut;
        if (A.manches === "sans") {
          // encolure en U, emmanchures larges, liserés (coupe() ; par pixel dans le navigateur : GLSL_COUPES)
          const cp = this.gpu ? 0 : coupe(ax, y, z, ys, singlet, couture);
          if (cp === 1) k = peau; else if (cp === 2) k = liser;
        }
        if (maillot && k === haut) k = maillot(x, y, z);
      } else if (reg === 5) k = A.manches === "longues" || (A.manches === "courtes" && y > ys - 0.17) ? haut : peau;
      else if (reg === 6) k = A.manches === "longues" ? haut : peau;
      else if (reg === 7) k = A.gants ? acc : peau;
      else if (reg === 4) k = maillot ? maillot(x, y, z) : bas;
      else if (reg === 8) {
        const ourlet = genou + 0.12;
        // (par pixel, seule la frange de l'ourlet garde le tissu : sinon il déteint sur la peau au pli du genou)
        k = A.coupe_bas === "cuissard" && y < ourlet && (!this.gpu || y < ourlet - 0.03) ? peau : bas;
        if (maillot && k === bas) k = maillot(x, y, z);
        if (singlet && y >= ourlet && y < ourlet + 0.025 && !this.gpu) k = ourl;              // bandes au bas des cuisses
      } else if (reg === 9) {
        const dansTige = montantes && y < cheville + hauteurTige;
        k = dansTige ? (chaussure ? chaussure(x, y, z, true) : chaus) : A.coupe_bas === "cuissard" ? peau : bas;
      } else if (reg === 10) k = chaussure ? chaussure(x, y, z, false) : chaus;
      c[3 * i] = k.r; c[3 * i + 1] = k.g; c[3 * i + 2] = k.b;
    }
    this.mesh.geometry.attributes.color.needsUpdate = true;
    if (this.matGalbe) this.matGalbe.color.copy(maillot ? maillot(0, genou + 0.3, 0.09) : bas);
    // coques : cheveux (épaisseur selon la coiffure, plus fine sur les bords), sourcils, barbe
    this.matCheveux = this.matCheveux || new THREE.MeshStandardMaterial({ roughness: 0.92 });
    this.matCheveux.color.copy(cheveux);
    this.matSourcils = this.matSourcils || new THREE.MeshStandardMaterial({ roughness: 0.95 });
    this.matSourcils.color.copy(sourcils);
    const ep = A.cheveux === "mi-long" ? 0.016 : A.cheveux === "rasé" ? 0.0012 : 0.006;
    if (A.cheveux === "chauve") this.coque("cheveux", new Uint8Array(nv), 0, this.matCheveux);
    else this.coque("cheveux", mCheveux, (v) => ep * Math.min(1, Math.max(0.25, (p[3 * v + 1] - oe.y - 0.02) / 0.05)), this.matCheveux);
    this.coque("sourcils", mSourcils, 0.0015, this.matSourcils);
    this.coque("barbe", A.barbe === "pleine" ? mBarbe : new Uint8Array(nv), 0.003, this.matCheveux);
    this.matIris.map = textureIris(h.mat.iris.color.getStyle());
    this.matIris.needsUpdate = true;
  }
}

/* Peintre d'un modèle de chaussure de lutte : renvoie la couleur d'un sommet du pied ou de la tige (repère du corps au
   repos ; pointe du pied vers +z). Motifs : chevrons, dégradé, touches de couleur, bandes, obliques. Aucune marque ni
   aucun logo n'est reproduit : les motifs sont génériques. */
function peintreChaussure(m, P, cheville) {
  const k = Object.fromEntries(Object.entries(m.couleurs).map(([n, v]) => [n, new THREE.Color(v)]));
  const sol = cheville - 0.075, haut = cheville + m.hauteur, tmp = new THREE.Color();
  const axeX = { g: P.cheville_g[0], d: P.cheville_d[0] };
  return (x, y, z, tige) => {
    const ax = x - (x > 0 ? axeX.g : axeX.d), cote = Math.sign(x) * ax;     // cote > 0 : côté extérieur du pied
    const h = y - sol, av = z - 0.02;                                      // hauteur au-dessus du sol, avancée vers la pointe
    if (!tige && h < 0.018) return k.semelle;                              // semelle
    if (k.intermediaire && !tige && h < 0.032) return k.intermediaire;     // semelle intermédiaire
    if (y > haut - 0.012) return k.col;                                   // bord du col
    // laçage : bande centrale sur le dessus, du cou-de-pied au haut de la tige
    if (Math.abs(ax) < 0.014 && z > 0.025 && av < 0.12 && (tige || h > 0.045)) {
      const pas = ((y + z) * 70) % 1;
      if (pas < 0.55 || Math.abs(ax) < 0.004) return k.lacets;
    }
    switch (m.motif) {
      case "chevrons": {                                                   // chevrons pointant vers l'avant
        const t = ((av * 1.0 - Math.abs(h - 0.075) * 0.9) * 28) % 1;
        return Math.abs(ax) > 0.018 && h > 0.03 && (t + 1) % 1 < 0.32 ? (Math.floor((av + h) * 40) % 2 ? k.accent : tmp.copy(k.accent).lerp(k.tige, 0.35)) : k.tige;
      }
      case "degrade": {                                                    // noir à l'avant, orange puis rouge vers le talon
        const u = Math.min(1, Math.max(0, (0.05 - av) / 0.16 + (h - 0.03) * 1.5));
        return u < 0.15 ? k.tige : tmp.copy(k.tige).lerp(u > 0.7 ? k.accent2 : k.accent, Math.min(1, (u - 0.15) * 1.6));
      }
      case "accents": {                                                    // talon, bande latérale et col violets
        if (av < -0.06 && h > 0.03) return k.accent;
        if (Math.abs(h - 0.055) < 0.006 && Math.abs(ax) > 0.02) return k.accent;
        return k.tige;
      }
      case "bandes": {                                                     // contrefort et bandes blanches
        if (av < -0.055 && h > 0.025 && h < 0.09) return k.accent;
        if (Math.abs(ax) > 0.02 && Math.abs(h - (0.035 + 0.25 * Math.max(0, 0.1 - av))) < 0.007) return k.accent;
        if (tige && Math.abs(ax) > 0.02 && ((y * 60) % 1) < 0.18) return k.accent;
        return k.tige;
      }
      case "col_noir": {                                                   // haut de tige et contrefort noirs, diagonale fine
        if (h > m.hauteur + 0.075 - 0.05 || (av < -0.05 && h > 0.02)) return k.accent;
        if (Math.abs(ax) > 0.02 && h > 0.03 && Math.abs(h - 0.03 - (0.1 - av) * 0.35) < 0.004) return k.accent;
        return k.tige;
      }
      case "liseres": {                                                    // deux liserés dorés qui remontent vers le talon
        if (Math.abs(ax) > 0.02 && h > 0.025 && av < 0.08) {
          const base = 0.04 + Math.max(0, 0.08 - av) * 0.32;
          if (Math.abs(h - base) < 0.0045 || Math.abs(h - base - 0.016) < 0.0045) return k.accent;
        }
        return k.tige;
      }
      case "bicolore": {                                                   // avant-pied blanc, arrière et tige bleus, bandes argent
        const bleu = h > 0.07 - Math.max(0, 0.06 - av) * 0.5 || av < -0.04;
        if (!bleu) return k.tige;
        if (Math.abs(ax) > 0.02 && h > 0.04) { const t = ((h * 0.8 - av * 0.7) * 30) % 1; if ((t + 1) % 1 < 0.14) return k.accent2; }
        return k.accent;
      }
      case "obliques": {                                                   // bandes obliques argentées sur les côtés
        if (Math.abs(ax) > 0.02 && h > 0.03) {
          const t = ((h * 0.9 + av * 0.6) * 22) % 1;
          if (cote > 0 ? t < 0.22 : t < 0.18) return k.accent;
        }
        return k.tige;
      }
    }
    return k.tige;
  };
}

/* Coupes du haut sans manches, au repos (ax = |x|) : 0 tissu, 1 peau (encolure en U arrondie, plus profonde devant ;
   emmanchures), 2 liseré (bande de 12 mm autour des ouvertures du maillot de lutte ; couture sous la poitrine).
   GLSL_COUPES reprend exactement ces formules pour le rendu par pixel. */
function coupe(ax, y, z, ys, singlet, couture) {
  const prof = z > 0.02 ? 0.1 : 0.06, wN = 0.068, e = 0.012;
  const fond = (w) => ys - prof + prof * 0.55 * (Math.min(ax, w) / w) ** 2, bras = ys - 0.19 + 0.6 * Math.max(0, 0.15 - ax);
  if (y > ys + 0.125) return 1;                                            // cou au-dessus des trapèzes
  if (ax < wN && y > fond(wN)) return 1;
  if (ax > 0.125 && y > bras) return 1;
  if (!singlet) return 0;
  if (ax < wN + e && y > fond(wN + e) - e) return 2;
  if (ax > 0.125 - e && y > bras - e) return 2;
  if (couture && Math.abs(y - (ys - 0.2 + 2.6 * Math.min(ax, 0.12) ** 2)) < 0.005) return 2;
  return 0;
}
const GLSL_COUPES = `
uniform float uSans, uSinglet, uCuissard, uCouture, uYs, uOurlet; uniform vec3 uPeau, uLiser, uOurletC;
varying vec3 vRepos; varying vec4 vZones;
float coupe(float ax, float y, float z) {
  float prof = z > 0.02 ? 0.1 : 0.06, wN = 0.068, e = 0.012;
  float f0 = uYs - prof + prof * 0.55 * pow(min(ax, wN) / wN, 2.0), f1 = uYs - prof + prof * 0.55 * pow(min(ax, wN + e) / (wN + e), 2.0);
  float bras = uYs - 0.19 + 0.6 * max(0.0, 0.15 - ax);
  if (y > uYs + 0.125) return 1.0;
  if (ax < wN && y > f0) return 1.0;
  if (ax > 0.125 && y > bras) return 1.0;
  if (uSinglet < 0.5) return 0.0;
  if (ax < wN + e && y > f1 - e) return 2.0;
  if (ax > 0.125 - e && y > bras - e) return 2.0;
  if (uCouture > 0.5 && abs(y - (uYs - 0.2 + 2.6 * pow(min(ax, 0.12), 2.0))) < 0.005) return 2.0;
  return 0.0;
}
void couperMaillot(inout vec3 c) {
  float ax = abs(vRepos.x), y = vRepos.y;
  // tronc et base du cou (trapèzes) : les bretelles passent par-dessus l'épaule, de la poitrine jusqu'au dos
  if (uSans > 0.5 && (vZones.x > 0.5 || vZones.w > 0.5)) { float k = coupe(ax, y, vRepos.z); if (k == 1.0) c = uPeau; else if (k == 2.0) c = uLiser; }
  else if (uSans > 0.5 && vZones.y > 0.5) c = uPeau;          // bras nus (triangles à cheval sur le tronc)
  if (uCuissard > 0.5 && vZones.z > 0.5) { if (y < uOurlet) c = uPeau; else if (uSinglet > 0.5 && y < uOurlet + 0.025) c = uOurletC; }
}`;

/* Peintre d'un modèle de maillot de lutte : couleur d'un sommet du tronc, du bassin ou des cuisses (repère du corps
   au repos). Motifs : uni, chiné, ton sur ton, nuages avec couture sous la poitrine, flancs en maille. Aucun logo,
   drapeau ni inscription des photographies de référence n'est reproduit : seuls les couleurs et le type de motif. */
function peintreMaillot(m, P, ys) {
  const k = Object.fromEntries(Object.entries(m.couleurs).map(([n, v]) => [n, new THREE.Color(v)]));
  const hanche = Math.abs(P.hanche_g[0]), tmp = new THREE.Color();
  const bruit = (x, y, z) => { const s = Math.sin(x * 12.9898 + y * 78.233 + z * 37.719) * 43758.5453; return s - Math.floor(s); };
  return (x, y, z) => {
    const ax = Math.abs(x);
    switch (m.motif) {
      case "chine": {                                                      // fils clairs et sombres mêlés
        const b = bruit(x * 900, y * 900, z * 900);
        return tmp.copy(k.corps).multiplyScalar(0.86 + 0.28 * b);
      }
      case "ton_sur_ton": {                                                // grandes formes sublimées plus sombres
        const v = Math.sin(x * 24 + y * 15) + Math.sin(y * 21 - z * 17 + x * 9) + 0.6 * Math.sin((x + z) * 41 - y * 8);
        return v > 1.05 ? k.accent : v > 0.8 ? tmp.copy(k.corps).lerp(k.accent, 0.5) : k.corps;
      }
      case "nuages": {                                                     // nuages pâles sous la couture de poitrine (coupe())
        const couture = ys - 0.2 + 2.6 * Math.min(ax, 0.12) ** 2;
        if (y < couture) { const v = Math.sin(x * 33 + y * 11) + Math.sin(y * 27 - x * 19 + z * 23); if (v > 0.9) return k.accent; }
        return k.corps;
      }
      case "flancs": {                                                     // flancs du tronc et côtés des cuisses en maille
        const cuisse = y < P.hanche_g[1] - 0.06;
        const flanc = cuisse ? ax - hanche > 0.045 : ax > 0.105 && z > -0.075 && z < 0.06 && y > ys - 0.5;
        return flanc ? (bruit(x * 400, y * 400, z * 400) > 0.5 ? k.accent : tmp.copy(k.accent).multiplyScalar(0.8)) : k.corps;
      }
    }
    return k.corps;
  };
}

/* Texture de l'œil : image de MakeHuman (CC0), iris recoloré à la teinte choisie (luminance conservée). */
let IMAGE_OEIL = null;
function textureIris(couleur, base = "/static/avatar/humain/") {
  if (typeof document === "undefined") return null;
  const cv = document.createElement("canvas"); cv.width = cv.height = 512;
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace;
  const dessiner = () => {
    const g = cv.getContext("2d"); g.drawImage(IMAGE_OEIL, 0, 0, 512, 512);
    const d = g.getImageData(0, 0, 512, 512), px = d.data, cible = new THREE.Color(couleur), hsl = {};
    cible.getHSL(hsl);
    const c = new THREE.Color(), h2 = {};
    for (let i = 0; i < px.length; i += 4) {
      c.setRGB(px[i] / 255, px[i + 1] / 255, px[i + 2] / 255); c.getHSL(h2);
      if (h2.s > 0.28 && h2.l < 0.6 && (h2.h < 0.12 || h2.h > 0.92)) {          // iris brun de l'image d'origine
        c.setHSL(hsl.h, Math.min(1, hsl.s * 1.1), clamp(h2.l * (0.6 + hsl.l * 1.2), 0, 0.85));
        px[i] = c.r * 255; px[i + 1] = c.g * 255; px[i + 2] = c.b * 255;
      }
    }
    g.putImageData(d, 0, 0); t.needsUpdate = true;
  };
  if (IMAGE_OEIL?.complete) dessiner();
  else { if (!IMAGE_OEIL) { IMAGE_OEIL = new Image(); IMAGE_OEIL.src = `${base}oeil.png`; } IMAGE_OEIL.addEventListener("load", dessiner, { once: true }); }
  return t;
}
