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
    const { meta, t } = donnees;
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
    this.os = this.noeuds.map(() => { const b = new THREE.Bone(); b.matrixAutoUpdate = false; return b; });
    this.mesh = new THREE.SkinnedMesh(g, this.mat);
    this.mesh.name = "corps-humain"; this.mesh.frustumCulled = false; this.mesh.castShadow = true; this.mesh.receiveShadow = true;
    this.mesh.bindMode = THREE.DetachedBindMode;
    this.mesh.bind(new THREE.Skeleton(this.os, this.os.map(() => new THREE.Matrix4())), new THREE.Matrix4());
    // les os n'ont pas de parent : leur matrice monde est posée directement à chaque image
    for (const b of this.os) b.updateMatrixWorld = () => {};
    this.construireYeux(t);
    this.visible = false;
    this.mesh.visible = false;
    humanoide.racine.add(this.mesh);
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
    for (const nom of ["cheveux", "sourcils", "barbe"]) if (this[nom]) this[nom].visible = oui;
    h.proportions(oui ? this.meta : null);
    // repos du squelette (degrés de liberté nuls), mémorisé pour l'habillage
    h.appliquer({}, { ancrage: false, sansHumain: true }); h.racine.position.set(0, 0, 0); h.racine.rotation.set(0, 0, 0);
    h.racine.updateMatrixWorld(true);
    this.repos0 = {};
    for (const n of this.noeuds) { const G = this.groupe(n); if (G) this.repos0[n] = G.matrixWorld.clone(); }
    this.reposMains = { g: this.reperesMain("g", true), d: this.reperesMain("d", true) };
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
    const c = this.couleurs, r = this.region, p = this.repos;
    const tmp = new THREE.Color();
    const nv = r.length, mCheveux = new Uint8Array(nv), mSourcils = new Uint8Array(nv), mBarbe = new Uint8Array(nv);
    for (let i = 0; i < r.length; i++) {
      const x = p[3 * i], y = p[3 * i + 1], z = p[3 * i + 2], reg = r[i];
      let k = peau;
      const ax = Math.abs(x), dy = y - oe.y, dz = z - oe.z;
      if (reg === 0 || reg === 1) {
        // cheveux : au-dessus d'une ligne qui descend du front vers la nuque
        const seuil = dz > -0.01 ? 0.05 : dz < -0.11 ? -0.085 : 0.05 - (0.135 * (-0.01 - dz)) / 0.1;
        const calvitie = A.cheveux === "chauve" ? 0 : A.cheveux === "rasé" ? 0.45 : 1;
        if (reg === 0 && dy > seuil && calvitie > 0 && !(ax > 0.072 && dy < 0.02 && dz > -0.09)) { k = tmp.copy(peau).lerp(cheveux, calvitie); mCheveux[i] = 1; }
        else if (reg === 0 && dy > 0.012 && dy < 0.027 && ax > 0.01 && ax < 0.052 && dz > -0.03) { k = sourcils; mSourcils[i] = 1; }   // sourcils
        else if (reg === 0 && Math.abs(dy + 0.071) < 0.0075 && ax < 0.024 && dz > -0.02) k = levres;                       // lèvres
        else if (reg === 0 && A.barbe !== "aucune" && dy < -0.05 && dz > -0.09 && !(Math.abs(dy + 0.071) < 0.009 && ax < 0.026))
          { k = tmp.copy(peau).lerp(cheveux, A.barbe === "pleine" ? 0.9 : 0.45); mBarbe[i] = 1; }
      } else if (reg === 2 || reg === 3) {
        k = haut;
        if (A.manches === "sans") {
          // encolure en U, plus profonde devant que dans le dos ; emmanchures larges (maillot de lutte)
          const prof = z > 0.02 ? 0.1 : 0.06;
          if (y > ys - prof && ax < 0.07 - 0.25 * Math.max(0, ys - y - 0.02)) k = peau;
          if (ax > 0.125 && y > ys - 0.19) k = peau;
          if (singlet && k === haut && ((y > ys - prof - 0.018 && ax < 0.082) || (ax > 0.113 && y > ys - 0.2))) k = acc;   // liserés
        }
      } else if (reg === 5) k = A.manches === "longues" || (A.manches === "courtes" && y > ys - 0.17) ? haut : peau;
      else if (reg === 6) k = A.manches === "longues" ? haut : peau;
      else if (reg === 7) k = A.gants ? acc : peau;
      else if (reg === 4) k = bas;
      else if (reg === 8) {
        const ourlet = genou + 0.12;
        k = A.coupe_bas === "cuissard" && y < ourlet ? peau : bas;
        if (singlet && y >= ourlet && y < ourlet + 0.025) k = acc;                            // bandes au bas des cuisses
      } else if (reg === 9) k = A.coupe_bas === "cuissard" ? (A.chaussures_montantes && y < cheville + 0.1 ? chaus : peau) : (A.chaussures_montantes && y < cheville + 0.1 ? chaus : bas);
      else if (reg === 10) k = chaus;
      c[3 * i] = k.r; c[3 * i + 1] = k.g; c[3 * i + 2] = k.b;
    }
    this.mesh.geometry.attributes.color.needsUpdate = true;
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
