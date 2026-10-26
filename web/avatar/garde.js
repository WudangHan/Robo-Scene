/* Robo-Scène — garde-corps du robot virtuel (26 oct. 2026).
   La main et l'avant-bras ne doivent pas entrer dans le corps (tête, cou, tronc, bassin, cuisses). Chaque segment du
   corps est décrit, dans son propre repère, par un nuage de points de sa surface avec leurs normales (sous-échantillonné
   en voxels de 1,5 cm) : pour le corps humain, les sommets MakeHuman au repos ; pour le robot stylisé, les volumes
   visibles rattachés au segment. Un point du bras est « dedans » quand, rapporté au repère courant du segment, il se
   trouve du côté intérieur du point de surface le plus proche (produit scalaire avec la normale négatif) ; la
   profondeur est cette distance signée. La passe d'évitement (eviter) écarte le bras par moindres carrés amortis sur
   l'épaule (flexion, abduction, rotation) et le coude, avec départ à chaud et relâchement progressif d'une image à
   l'autre : pas de saut visible. Les contacts voulus (main sur le cœur, sur la tête…) passent ensuite (toucherVisage). */
import * as THREE from "three";

const SEGMENTS = ["tete", "cou", "poitrine", "lombaires", "bassin", "hanche_g", "hanche_d"];
const REGION_SEGMENT = { 0: "tete", 1: "cou", 2: "poitrine", 3: "lombaires", 4: "bassin" };   // 8 : cuisse (selon x)
const MARGE = 0.012;                     // m : jeu laissé entre la peau du bras et celle du corps
const POINTS_BRAS = ["paume", "doigts", "index", "poing", "pouce", "poignet", "avantbras_milieu", "coude"];

/* nuage → voxels de 1,5 cm (moyenne des positions et des normales), avec boîte englobante */
function voxeliser(pts) {
  const cell = 0.015, M = new Map();
  for (const [x, y, z, nx, ny, nz] of pts) {
    const k = `${Math.floor(x / cell)},${Math.floor(y / cell)},${Math.floor(z / cell)}`;
    const a = M.get(k) || [0, 0, 0, 0, 0, 0, 0];
    a[0] += x; a[1] += y; a[2] += z; a[3] += nx; a[4] += ny; a[5] += nz; a[6]++; M.set(k, a);
  }
  const P = [], min = [9, 9, 9], max = [-9, -9, -9];
  for (const a of M.values()) {
    const n = Math.hypot(a[3], a[4], a[5]) || 1, p = [a[0] / a[6], a[1] / a[6], a[2] / a[6], a[3] / n, a[4] / n, a[5] / n];
    P.push(p); for (let i = 0; i < 3; i++) { min[i] = Math.min(min[i], p[i]); max[i] = Math.max(max[i], p[i]); }
  }
  return { P: Float32Array.from(P.flat()), n: P.length, min, max };
}

export class GardeCorps {
  constructor(humanoide) { this.h = humanoide; this.segments = null; this.delta = { g: null, d: null }; this.cle = null; }

  /* (re)construit les nuages pour le style courant ; cle : invalide le cache quand l'apparence change */
  construire(cle) {
    if (cle && cle === this.cle && this.segments) return;
    this.cle = cle;
    const h = this.h, O = h.os, humain = h.humain?.visible, seg = {};
    for (const s of SEGMENTS) seg[s] = [];
    const v = new THREE.Vector3(), n = new THREE.Vector3(), M = new THREE.Matrix4(), N3 = new THREE.Matrix3();
    if (humain) {
      const H = h.humain, R = H.region, P = H.repos, nrm = H.mesh.geometry.attributes.normal.array, nb = Math.min(R.length, H.nOriginal || R.length);
      const inv = {}; for (const s of SEGMENTS) inv[s] = H.repos0[s].clone().invert();
      for (let i = 0; i < nb; i++) {
        const r = R[i]; let s = REGION_SEGMENT[r];
        if (r === 8) s = P[3 * i] > 0 ? "hanche_g" : "hanche_d";
        if (!s) continue;
        v.set(P[3 * i], P[3 * i + 1], P[3 * i + 2]).applyMatrix4(inv[s]);
        n.set(nrm[3 * i], nrm[3 * i + 1], nrm[3 * i + 2]).applyMatrix3(N3.setFromMatrix4(inv[s])).normalize();
        seg[s].push([v.x, v.y, v.z, n.x, n.y, n.z]);
      }
    } else {
      // volumes visibles du robot stylisé : chaque maillage est rendu au segment dont il dépend directement
      const groupes = new Set(Object.values(O).filter((o) => o?.isObject3D));
      const acc = new Set(); for (const g of Object.values(O.acc || {})) g.traverse((o) => acc.add(o));
      h.racine.updateMatrixWorld(true);
      h.racine.traverse((o) => {
        if (!o.isMesh || acc.has(o) || !o.visible || /^capteur_|^objet_|^corps-humain|^oeil_humain|^sangle/.test(o.name)) return;
        let g = o.parent; while (g && !groupes.has(g)) g = g.parent;
        const s = SEGMENTS.find((k) => O[k] === g);
        if (!s) return;
        const G = O[s];
        M.copy(G.matrixWorld).invert().multiply(o.matrixWorld); N3.getNormalMatrix(M);
        const pos = o.geometry.attributes.position, nor = o.geometry.attributes.normal;
        if (!nor) return;
        for (let i = 0; i < pos.count; i++) {
          v.fromBufferAttribute(pos, i).applyMatrix4(M); n.fromBufferAttribute(nor, i).applyMatrix3(N3).normalize();
          seg[s].push([v.x, v.y, v.z, n.x, n.y, n.z]);
        }
      });
    }
    this.segments = Object.fromEntries(SEGMENTS.filter((s) => seg[s].length).map((s) => [s, voxeliser(seg[s])]));
  }

  /* points du bras surveillés (monde) */
  pointsBras(s) {
    const h = this.h, O = h.os, out = [];
    for (const p of POINTS_BRAS) {
      if (p === "poignet") out.push(O[`poignet_${s}`].getWorldPosition(new THREE.Vector3()));
      else if (p === "coude") out.push(O[`coude_${s}`].getWorldPosition(new THREE.Vector3()));
      else if (p === "avantbras_milieu") out.push(O[`coude_${s}`].getWorldPosition(new THREE.Vector3()).lerp(O[`poignet_${s}`].getWorldPosition(new THREE.Vector3()), 0.5));
      else if (p === "pouce") { const d = h.mainsRendu?.[s]?.doigts?.pouce; out.push(d ? d.arts[d.arts.length - 1].getWorldPosition(new THREE.Vector3()) : h.pointMain(s, "paume").clone()); }
      else out.push(h.pointMain(s, p).clone());
    }
    return out;
  }

  /* pénétration d'un point (monde) : {profondeur (m, > 0 dedans), normale monde, segment} ou null */
  penetration(p, marge = 0) {
    const O = this.h.os, q = new THREE.Vector3(), M = new THREE.Matrix4();
    let pire = null;
    for (const [s, S] of Object.entries(this.segments || {})) {
      const G = O[s];
      q.copy(p).applyMatrix4(M.copy(G.matrixWorld).invert());
      if (q.x < S.min[0] - 0.03 || q.y < S.min[1] - 0.03 || q.z < S.min[2] - 0.03 || q.x > S.max[0] + 0.03 || q.y > S.max[1] + 0.03 || q.z > S.max[2] + 0.03) continue;
      let best = Infinity, b = -1;
      for (let i = 0; i < S.n; i++) {
        const k = 6 * i, dx = q.x - S.P[k], dy = q.y - S.P[k + 1], dz = q.z - S.P[k + 2], d = dx * dx + dy * dy + dz * dz;
        if (d < best) { best = d; b = k; }
      }
      const signe = (q.x - S.P[b]) * S.P[b + 3] + (q.y - S.P[b + 1]) * S.P[b + 4] + (q.z - S.P[b + 2]) * S.P[b + 5];
      const prof = marge - signe;
      if (prof > 0 && (!pire || prof > pire.profondeur)) {
        const nw = new THREE.Vector3(S.P[b + 3], S.P[b + 4], S.P[b + 5]).transformDirection(G.matrixWorld);
        pire = { profondeur: prof, normale: nw, segment: s };
      }
    }
    return pire;
  }

  /* mesure (audit) : pénétration maximale des points des deux bras, en m */
  mesurer() {
    const out = {};
    for (const s of ["g", "d"]) {
      let m = 0, seg = null, point = null;
      this.pointsBras(s).forEach((p, i) => { const r = this.penetration(p); if (r && r.profondeur > m) { m = r.profondeur; seg = r.segment; point = POINTS_BRAS[i]; } });
      out[s] = { profondeur: m, segment: seg, point };
    }
    return out;
  }

  /* Cinématique inverse d'un bras, empilée (moindres carrés amortis) : q = [flexion, abduction, rotation de
     l'épaule, flexion du coude] (+ [flexion, inclinaison, rotation du poignet] pour un contact). Résidus : la
     cible du point de contact, s'il y en a une, et la sortie de chaque autre point du bras qui entre dans le corps. */
  resoudreBras(s, P, q, { cible = null, point = null, iterations = 4, marge = MARGE } = {}) {
    const h = this.h, D = h.schema.dofs;
    const noms = ["flexion", "abduction", "rotation"].map((k) => `epaule_${s}.${k}`).concat([`coude_${s}.flexion`],
      q.length > 4 ? ["flexion", "deviation", "rotation"].map((k) => `poignet_${s}.${k}`) : []);
    const bornes = noms.map((n) => [D[n].min, D[n].max]);
    const ignore = point ? POINTS_BRAS.indexOf(point) : -1;
    const mesurer = (qq) => {
      h.regleBras(s, P, qq);
      const pts = this.pointsBras(s), r = [];
      if (cible) r.push({ k: -1, p: h.pointMain(s, point).clone(), e: cible.clone().sub(h.pointMain(s, point)) });
      pts.forEach((p, k) => {
        if (k === ignore) return;
        const pe = this.segments ? this.penetration(p, marge) : null;
        if (pe) r.push({ k, p, e: pe.normale.clone().multiplyScalar(pe.profondeur) });
      });
      return r;
    };
    for (let it = 0; it <= iterations; it++) {
      const r = mesurer(q);
      this.residu = r.reduce((a, { e }) => a + e.length(), 0);          // m : somme des écarts restants
      if (it === iterations || !r.length || (r.length === 1 && r[0].k === -1 && r[0].e.length() < 0.003)) break;
      const J = q.map((_, i) => {
        const qq = q.slice(); qq[i] += 1;
        h.regleBras(s, P, qq);
        const pts = this.pointsBras(s), pc = cible ? h.pointMain(s, point).clone() : null;
        return r.map(({ k, p }) => (k === -1 ? pc : pts[k]).clone().sub(p));      // m par degré
      });
      // dq = Jᵀ (J Jᵀ + λ²I)⁻¹ e, empilé sur les points (3 lignes par résidu)
      const m3 = r.length * 3, Jm = (i, row) => { const v = J[i][Math.floor(row / 3)]; return [v.x, v.y, v.z][row % 3]; };
      const ev = r.flatMap(({ e }) => [e.x, e.y, e.z]);
      const A = Array.from({ length: m3 }, (_, a) => Array.from({ length: m3 }, (_, b) => { let sum = a === b ? 0.004 * 0.004 : 0; for (let i = 0; i < q.length; i++) sum += Jm(i, a) * Jm(i, b); return sum; }));
      const y = resoudre(A, ev);
      q = q.map((v, i) => { let d = 0; for (let row = 0; row < m3; row++) d += Jm(i, row) * y[row]; return Math.max(bornes[i][0], Math.min(bornes[i][1], v + Math.max(-12, Math.min(12, d)))); });
    }
    return q;
  }

  /* évitement : écarte chaque bras (sauf s'il est en contact voulu) ; P : pose de l'image (degrés) */
  eviter(P, sauf = {}) {
    if (!this.segments) return;
    const h = this.h, D = h.schema.dofs;
    for (const s of ["g", "d"]) {
      const libre = 1 - Math.min(1, sauf[s] || 0);
      if (libre < 0.05) { this.delta[s] = null; continue; }
      const noms = ["flexion", "abduction", "rotation"].map((k) => `epaule_${s}.${k}`).concat([`coude_${s}.flexion`]);
      const q0 = noms.map((n) => P[n] || 0);
      // départ à chaud : correction précédente, relâchée de 12 % (le bras revient de lui-même quand il le peut)
      const d0 = this.delta[s] || [0, 0, 0, 0];
      let q = q0.map((v, i) => Math.max(D[noms[i]].min, Math.min(D[noms[i]].max, v + d0[i] * 0.88)));
      q = this.resoudreBras(s, P, q);
      this.delta[s] = q.map((v, i) => v - q0[i]);
      h.regleBras(s, P, q0.map((v, i) => v + (q[i] - v) * libre));
    }
  }
}

/* résolution d'un petit système linéaire symétrique par élimination de Gauss avec pivot partiel */
function resoudre(A, b) {
  const n = b.length, M = A.map((r, i) => [...r, b[i]]);
  for (let c = 0; c < n; c++) {
    let p = c; for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    const d = M[c][c] || 1e-12;
    for (let r = c + 1; r < n; r++) { const f = M[r][c] / d; for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k]; }
  }
  const x = new Array(n).fill(0);
  for (let r = n - 1; r >= 0; r--) { let s = M[r][n]; for (let k = r + 1; k < n; k++) s -= M[r][k] * x[k]; x[r] = s / (M[r][r] || 1e-12); }
  return x;
}
