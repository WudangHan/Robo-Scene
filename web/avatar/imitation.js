/* Robo-Scène — imitation : le robot virtuel reproduit le visage et le corps d'une personne
   filmée par la caméra de l'ordinateur. Tout le traitement est local (MediaPipe Tasks Vision,
   exécuté dans le navigateur) ; aucune image n'est enregistrée ni transmise.
   • Visage : 52 coefficients de forme (« blendshapes ») convertis en unités d'action FACS.
   • Tête : matrice de transformation faciale → rotation, flexion, inclinaison.
   • Corps : repères 3D en mètres → angles d'épaule, de coude, de hanche, de genou et de tronc.
   Mode miroir (par défaut) : le personnage agit comme un reflet (la main droite de la personne
   devient sa main gauche, du même côté de l'écran). */

const VISION = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
const MODELE_VISAGE = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
const MODELE_POSE = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task";
const deg = (r) => (r * 180) / Math.PI;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

/* Correspondance coefficients ARKit/MediaPipe → unités d'action (Inférence de conception) */
function versAU(b, miroir) {
  const g = (n) => b[n] || 0;
  const L = miroir ? "Right" : "Left", Rr = miroir ? "Left" : "Right";      // côté du personnage
  return {
    au1: g("browInnerUp"),
    au2_g: g(`browOuterUp${L}`), au2_d: g(`browOuterUp${Rr}`),
    au4: (g("browDownLeft") + g("browDownRight")) / 2,
    au5: (g("eyeWideLeft") + g("eyeWideRight")) / 2,
    au6: (g("cheekSquintLeft") + g("cheekSquintRight")) / 2,
    au7: (g("eyeSquintLeft") + g("eyeSquintRight")) / 2,
    au9: (g("noseSneerLeft") + g("noseSneerRight")) / 2,
    au10: (g("mouthUpperUpLeft") + g("mouthUpperUpRight")) / 2,
    au12_g: g(`mouthSmile${L}`), au12_d: g(`mouthSmile${Rr}`),
    au14_g: g(`mouthDimple${L}`), au14_d: g(`mouthDimple${Rr}`),
    au15_g: g(`mouthFrown${L}`), au15_d: g(`mouthFrown${Rr}`),
    au16: (g("mouthLowerDownLeft") + g("mouthLowerDownRight")) / 2,
    au17: g("mouthShrugLower"),
    au18: g("mouthPucker"),
    au20: (g("mouthStretchLeft") + g("mouthStretchRight")) / 2,
    au24: (g("mouthPressLeft") + g("mouthPressRight")) / 2,
    au25: clamp(g("jawOpen") * 1.6, 0, 1),
    au26: g("jawOpen"),
    au46_g: g(`eyeBlink${L}`), au46_d: g(`eyeBlink${Rr}`),
  };
}

/* Lecture émotionnelle indicative : proximité (cosinus) entre les unités d'action observées et
   les prototypes du répertoire. Ce n'est pas une mesure de l'état intérieur de la personne. */
export function lireEmotion(au, EMOTIONS) {
  const cles = ["au1", "au2", "au4", "au5", "au6", "au7", "au9", "au10", "au12", "au14", "au15", "au17", "au20", "au23", "au24", "au26"];
  const vec = (a) => cles.map((k) => Math.max(a[k] || 0, a[`${k}_g`] || 0, a[`${k}_d`] || 0));
  const v = vec(au), nv = Math.hypot(...v);
  if (nv < 0.15) return [{ nom: "neutre", score: 1 }];
  const res = [];
  for (const [nom, e] of Object.entries(EMOTIONS)) {
    if (nom === "neutre") continue;
    const p = vec(e.au), np = Math.hypot(...p);
    if (!np) continue;
    res.push({ nom, score: v.reduce((s, x, i) => s + x * p[i], 0) / (nv * np) });
  }
  return res.sort((a, b) => b.score - a.score).slice(0, 3);
}

/* Angles d'un membre dans le repère du tronc (même convention que humanoide.js) */
function anglesMembre(dir, X, Y, Z, exterieur) {
  const lx = dir[0] * X[0] + dir[1] * X[1] + dir[2] * X[2];
  const ly = dir[0] * Y[0] + dir[1] * Y[1] + dir[2] * Y[2];
  const lz = dir[0] * Z[0] + dir[1] * Z[1] + dir[2] * Z[2];
  const flex = deg(Math.asin(clamp(lz, -1, 1)));
  const abd = deg(Math.atan2(lx * exterieur, -ly));
  return { flex, abd };
}
const sub = (a, b) => [a.x - b.x, a.y - b.y, a.z - b.z];
const mil = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, z: (a.z + b.z) / 2 });
const norm = (v) => { const n = Math.hypot(...v) || 1; return v.map((x) => x / n); };
const croix = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const scal = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const angle = (a, b) => deg(Math.acos(clamp(scal(norm(a), norm(b)), -1, 1)));

function versPose(w, miroir) {
  const vis = (i) => (w[i].visibility ?? 1) > 0.5;
  const LS = w[11], RS = w[12], LH = w[23], RH = w[24];
  const X = norm(sub(LS, RS));                                    // vers la gauche de la personne
  const Y = norm(sub(mil(LS, RS), mil(LH, RH)));                  // vers le haut du tronc
  let Z = norm(croix(X, Y));                                       // vers l'avant
  if (scal(sub(w[0], mil(LS, RS)), Z) < 0) Z = Z.map((x) => -x);  // le nez est devant les épaules
  const pose = {};
  const S = (personne) => (miroir ? (personne === "g" ? "d" : "g") : personne);
  for (const [p, epaule, coude, poignet, hanche, genou, cheville] of [["g", 11, 13, 15, 23, 25, 27], ["d", 12, 14, 16, 24, 26, 28]]) {
    const ext = p === "g" ? 1 : -1, s = S(p);
    if (vis(coude) && vis(epaule)) {
      const bras = norm(sub(w[coude], w[epaule]));
      const a = anglesMembre(bras, X, Y, Z, ext);
      pose[`epaule_${s}.flexion`] = clamp(a.flex, -50, 180);
      pose[`epaule_${s}.abduction`] = clamp(a.abd, -10, 175);
      if (vis(poignet)) pose[`coude_${s}.flexion`] = clamp(angle(bras, sub(w[poignet], w[coude])), 0, 150);
    }
    if (vis(genou) && vis(hanche)) {
      const cuisse = norm(sub(w[genou], w[hanche]));
      const a = anglesMembre(cuisse, X, Y, Z, ext);
      pose[`hanche_${s}.flexion`] = clamp(a.flex, -30, 125);
      pose[`hanche_${s}.abduction`] = clamp(a.abd, -20, 50);
      if (vis(cheville)) pose[`genou_${s}.flexion`] = clamp(angle(cuisse, sub(w[cheville], w[genou])), 0, 140);
    }
  }
  // tronc : inclinaison du segment bassin-épaules par rapport à la verticale (y vers le bas dans MediaPipe)
  const vert = [0, -1, 0];
  const hx = norm(sub(LH, RH));
  const avant = norm(croix(hx, vert).map((x) => -x));
  const tronc = Y;
  let fl = deg(Math.atan2(scal(tronc, avant), scal(tronc, vert)));
  if (scal(sub(w[0], mil(LS, RS)), avant) < 0) fl = -fl;
  pose["tronc.flexion"] = clamp(fl, -25, 80);
  pose["tronc.inclinaison"] = clamp(deg(Math.atan2(scal(tronc, hx), scal(tronc, vert))) * (miroir ? -1 : 1), -35, 35);
  return pose;
}

export class Imitation {
  constructor() {
    this.actif = false; this.visage = true; this.corps = true; this.miroir = true;
    this.video = null; this.flux = null; this.fv = null; this.fp = null; this.dernier = -1;
    this.sortie = null; this.lisse = {}; this.lecture = [];
  }
  async demarrer(video) {
    this.video = video;
    this.flux = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: "user" }, audio: false });
    video.srcObject = this.flux; await video.play();
    const V = await import(`${VISION}/vision_bundle.mjs`);
    const fichiers = await V.FilesetResolver.forVisionTasks(`${VISION}/wasm`);
    this.fv = await V.FaceLandmarker.createFromOptions(fichiers, {
      baseOptions: { modelAssetPath: MODELE_VISAGE, delegate: "GPU" }, runningMode: "VIDEO", numFaces: 1,
      outputFaceBlendshapes: true, outputFacialTransformationMatrixes: true,
    });
    this.fp = await V.PoseLandmarker.createFromOptions(fichiers, {
      baseOptions: { modelAssetPath: MODELE_POSE, delegate: "GPU" }, runningMode: "VIDEO", numPoses: 1,
    });
    this.actif = true;
  }
  arreter() {
    this.actif = false;
    if (this.flux) for (const p of this.flux.getTracks()) p.stop();
    this.flux = null; this.sortie = null; this.lisse = {};
    try { this.fv?.close(); this.fp?.close(); } catch (e) {}
    this.fv = this.fp = null;
    if (this.video) this.video.srcObject = null;
  }
  /* à appeler à chaque image ; renvoie {pose, au, regard} ou null */
  lire() {
    if (!this.actif || !this.video || this.video.readyState < 2) return this.sortie;
    if (this.video.currentTime === this.dernier) return this.sortie;
    this.dernier = this.video.currentTime;
    const ts = performance.now();
    const out = { pose: {}, au: null, regard: null };
    try {
      if (this.visage && this.fv) {
        const r = this.fv.detectForVideo(this.video, ts);
        const bs = r.faceBlendshapes?.[0]?.categories;
        if (bs) {
          const b = {}; for (const c of bs) b[c.categoryName] = c.score;
          out.au = versAU(b, this.miroir);
          const lx = (b.eyeLookOutLeft || 0) - (b.eyeLookInLeft || 0), ly = (b.eyeLookUpLeft || 0) - (b.eyeLookDownLeft || 0);
          out.regard = { yaw: clamp(lx * 0.6 * (this.miroir ? 1 : -1), -0.5, 0.5), pitch: clamp(ly * 0.4, -0.4, 0.35) };
        }
        const m = r.facialTransformationMatrixes?.[0]?.data;
        if (m) {
          // matrice colonne-majeure 4×4 : axes de la tête dans le repère caméra
          const yaw = deg(Math.atan2(m[8], m[10])), pitch = deg(Math.asin(clamp(-m[9], -1, 1))), roll = deg(Math.atan2(m[1], m[5]));
          const s = this.miroir ? 1 : -1;
          out.pose["tete.rotation"] = clamp(yaw * s, -80, 80);
          out.pose["tete.flexion"] = clamp(pitch, -45, 50);
          out.pose["tete.inclinaison"] = clamp(-roll * s, -40, 40);
        }
      }
      if (this.corps && this.fp) {
        const r = this.fp.detectForVideo(this.video, ts);
        const w = r.worldLandmarks?.[0];
        if (w && w.length >= 29) Object.assign(out.pose, versPose(w, this.miroir));
      }
    } catch (e) { console.warn("imitation", e); }
    // lissage exponentiel (réduit la gigue des détecteurs)
    for (const [k, v] of Object.entries(out.pose)) this.lisse[k] = k in this.lisse ? this.lisse[k] + (v - this.lisse[k]) * 0.35 : v;
    out.pose = Object.fromEntries(Object.keys(out.pose).map((k) => [k, this.lisse[k]]));
    this.sortie = out;
    return out;
  }
}
