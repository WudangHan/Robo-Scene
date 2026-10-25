/* Robo-Scène — plateau, éclairage, caméra et manipulation directe du robot virtuel.
   Caméra des yeux : ce que voit le robot, rendue depuis le visage (entre les yeux, devant le nez), dans l'axe de la tête
   ou du regard ; même interface que la caméra embarquée du drone et la caméra de tête du chien (rendreCamera), pour
   réutiliser web/drone/camera4k.js (aperçu, image 4K, enregistrement de la vue virtuelle). */
import * as THREE from "three";
import { OrbitControls } from "three/addons/OrbitControls.js";

/* Zones cliquables → [dof vertical (glisser vers le haut = +), dof horizontal (glisser vers l'extérieur = +)] */
const ZONES = {
  tete: ["-tete.flexion", "tete.rotation"], tronc: ["-tronc.flexion", "tronc.rotation"], bassin: ["-bassin.abaissement", "tronc.inclinaison"],
  bras_g: ["epaule_g.flexion", "epaule_g.abduction"], bras_d: ["epaule_d.flexion", "epaule_d.abduction"],
  avantbras_g: ["coude_g.flexion", "-epaule_g.rotation"], avantbras_d: ["coude_d.flexion", "-epaule_d.rotation"],
  main_g: ["-poignet_g.flexion", "poignet_g.deviation"], main_d: ["-poignet_d.flexion", "poignet_d.deviation"],
  cuisse_g: ["hanche_g.flexion", "hanche_g.abduction"], cuisse_d: ["hanche_d.flexion", "hanche_d.abduction"],
  tibia_g: ["genou_g.flexion", "hanche_g.rotation"], tibia_d: ["genou_d.flexion", "hanche_d.rotation"],
  pied_g: ["-cheville_g.flexion", "hanche_g.rotation"], pied_d: ["-cheville_d.flexion", "hanche_d.rotation"],
};
export const LIBELLES_ZONES = {
  tete: "Tête", tronc: "Tronc", bassin: "Bassin", bras_g: "Bras gauche", bras_d: "Bras droit", avantbras_g: "Avant-bras gauche",
  avantbras_d: "Avant-bras droit", main_g: "Main gauche", main_d: "Main droite", cuisse_g: "Cuisse gauche", cuisse_d: "Cuisse droite",
  tibia_g: "Jambe gauche", tibia_d: "Jambe droite", pied_g: "Pied gauche", pied_d: "Pied droit",
};
export const DOFS_ZONE = (z) => (ZONES[z] || []).map((d) => d.replace(/^-/, ""));

function texturePlancher() {
  const c = document.createElement("canvas"); c.width = 512; c.height = 512;
  const g = c.getContext("2d");
  g.fillStyle = "#2b2119"; g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 16; i++) {
    const y = i * 32, teinte = 34 + ((i * 37) % 11);
    g.fillStyle = `hsl(26, 28%, ${teinte * 0.42}%)`; g.fillRect(0, y + 1, 512, 30);
    g.fillStyle = "#15100c"; g.fillRect(0, y, 512, 1.5);
    const coupe = (i * 151) % 512; g.fillRect(coupe, y, 1.5, 32);
    g.globalAlpha = 0.08; for (let k = 0; k < 30; k++) { g.fillStyle = k % 2 ? "#000" : "#fff"; g.fillRect((k * 97 + i * 13) % 512, y + 4 + (k % 5) * 5, 60 + (k % 7) * 9, 1); } g.globalAlpha = 1;
  }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(3, 2.2); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  return t;
}
function textureRideau() {
  const c = document.createElement("canvas"); c.width = 1024; c.height = 64;
  const g = c.getContext("2d");
  for (let x = 0; x < 1024; x++) { const v = 0.55 + 0.45 * Math.sin(x / 1024 * Math.PI * 36) ** 2; g.fillStyle = `rgb(${Math.round(70 * v)},${Math.round(14 * v)},${Math.round(20 * v)})`; g.fillRect(x, 0, 1, 64); }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
function etiquette(texte) {
  const c = document.createElement("canvas"); c.width = 256; c.height = 64;
  const g = c.getContext("2d"); g.font = "600 34px system-ui, sans-serif"; g.fillStyle = "rgba(242,181,68,.55)"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(texte, 128, 32);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const m = new THREE.Mesh(new THREE.PlaneGeometry(0.8, 0.2), new THREE.MeshBasicMaterial({ map: t, transparent: true, depthWrite: false }));
  m.rotation.x = -Math.PI / 2; return m;
}

/* Salle devant la scène : gradins en pente, allée centrale, sorties, fenêtre de régie. Peu coûteuse (instances, aucune
   ombre) ; elle commence à 5,2 m du centre du plateau pour rester hors des cadrages prédéfinis, et donne à la caméra des
   yeux ce que verrait un robot tourné vers le public. Les places sont vides : aucune personne n'est représentée. */
function salle(s) {
  const g = new THREE.Group(); g.name = "salle";
  const rangs = 12, z0 = 5.2, pas = 0.9, pente = 0.2, largeur = 0.55;
  const xs = []; for (let x = -5.5; x <= 5.51; x += largeur) if (Math.abs(x) > 0.65) xs.push(x);
  const matSiege = new THREE.MeshStandardMaterial({ color: "#5a1420", roughness: 0.95 });
  const matGradin = new THREE.MeshStandardMaterial({ color: "#1a1512", roughness: 1 });
  const assise = new THREE.InstancedMesh(new THREE.BoxGeometry(0.48, 0.12, 0.46), matSiege, rangs * xs.length);
  const dossier = new THREE.InstancedMesh(new THREE.BoxGeometry(0.48, 0.55, 0.08), matSiege, rangs * xs.length);
  const m = new THREE.Matrix4(); let i = 0;
  for (let r = 0; r < rangs; r++) {
    const z = z0 + r * pas, y = r * pente;
    const marche = new THREE.Mesh(new THREE.BoxGeometry(12.5, y + 0.02 || 0.02, pas), matGradin);
    marche.position.set(0, (y + 0.02) / 2 - 0.25, z); g.add(marche);
    for (const x of xs) {
      m.makeTranslation(x, y - 0.25 + 0.45, z - 0.05); assise.setMatrixAt(i, m);
      m.makeTranslation(x, y - 0.25 + 0.75, z + 0.24); dossier.setMatrixAt(i, m); i++;
    }
  }
  g.add(assise, dossier);
  const sol = new THREE.Mesh(new THREE.PlaneGeometry(14, 3), matGradin); sol.rotation.x = -Math.PI / 2; sol.position.set(0, -0.5, 3.9); g.add(sol);
  const fond = z0 + rangs * pas + 0.4;
  const mur = new THREE.Mesh(new THREE.PlaneGeometry(14, 6), new THREE.MeshStandardMaterial({ color: "#14100e", roughness: 1 }));
  mur.position.set(0, 2.2, fond); mur.rotation.y = Math.PI; g.add(mur);
  for (const sx of [-1, 1]) {
    const lat = new THREE.Mesh(new THREE.PlaneGeometry(fond - 2.6, 6), mur.material);
    lat.position.set(sx * 6.4, 2.2, (fond + 2.6) / 2); lat.rotation.y = -sx * Math.PI / 2; g.add(lat);
  }
  const lumineux = (w, h, c) => new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: c, toneMapped: false }));
  const regie = lumineux(2.4, 0.6, "#3a4a66"); regie.position.set(0, rangs * pente + 1.7, fond - 0.01); regie.rotation.y = Math.PI; g.add(regie);
  for (const [x, z] of [[-6.38, 4.6], [6.38, 4.6], [-3.5, fond - 0.02], [3.5, fond - 0.02]]) {
    const e = lumineux(0.42, 0.16, "#2fd36b");
    e.position.set(x, z === 4.6 ? 2.3 : rangs * pente + 2.1, z);
    e.rotation.y = z === 4.6 ? -Math.sign(x) * Math.PI / 2 : Math.PI; g.add(e);
  }
  for (const z of [z0 + 2, z0 + 7.5]) { const l = new THREE.PointLight("#ffd9a8", 14, 12, 1.4); l.position.set(0, 4.4, z); g.add(l); }   // éclairage de service
  s.add(g);
  return g;
}

export class Scene {
  constructor(conteneur, humanoide, animateur) {
    this.h = humanoide; this.anim = animateur; this.conteneur = conteneur;
    const r = (this.rendu = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true }));
    r.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    r.shadowMap.enabled = true; r.shadowMap.type = THREE.PCFSoftShadowMap;
    r.toneMapping = THREE.ACESFilmicToneMapping; r.toneMappingExposure = 1.05;
    r.outputColorSpace = THREE.SRGBColorSpace;
    conteneur.appendChild(r.domElement);
    r.domElement.setAttribute("aria-label", "Robot virtuel en 3D : faites glisser une partie du corps pour la bouger, le fond pour tourner autour");
    const s = (this.scene = new THREE.Scene());
    s.background = new THREE.Color("#07080b");
    s.fog = new THREE.Fog("#07080b", 9, 18);
    this.camera = new THREE.PerspectiveCamera(32, 1, 0.05, 60);
    this.camera.position.set(0, 1.45, 4.2);
    this.camera.layers.enable(1);                          // couche 1 : repères d'édition (halos), absents de la caméra des yeux
    this.camYeux = new THREE.PerspectiveCamera(50, 16 / 9, 0.03, 60);
    this.champH = 78; this.zoom = 1; this.suivreRegard = false;
    this.controles = new OrbitControls(this.camera, r.domElement);
    this.controles.target.set(0, 1.05, 0); this.controles.enableDamping = true; this.controles.dampingFactor = 0.08;
    this.controles.minDistance = 0.5; this.controles.maxDistance = 12; this.controles.maxPolarAngle = Math.PI * 0.52;
    // plateau
    const sol = new THREE.Mesh(new THREE.PlaneGeometry(8, 5.6), new THREE.MeshStandardMaterial({ map: texturePlancher(), roughness: 0.82 }));
    sol.rotation.x = -Math.PI / 2; sol.position.z = -0.2; sol.receiveShadow = true; s.add(sol);
    const nez = new THREE.Mesh(new THREE.BoxGeometry(8, 0.5, 0.06), new THREE.MeshStandardMaterial({ color: "#111", roughness: 0.9 }));
    nez.position.set(0, -0.25, 2.6); s.add(nez);
    const rideau = new THREE.Mesh(new THREE.PlaneGeometry(9, 5), new THREE.MeshStandardMaterial({ map: textureRideau(), roughness: 1 }));
    rideau.position.set(0, 2.5, -3); rideau.receiveShadow = true; s.add(rideau);
    for (const [t, x, z] of [["COUR", 2.4, 1.7], ["JARDIN", -2.4, 1.7], ["LOINTAIN", 0, -2.4]]) { const e = etiquette(t); e.position.set(x, 0.003, z); s.add(e); }
    this.salle = salle(s);
    // éclairage
    this.hemi = new THREE.HemisphereLight("#b9c3d6", "#2a2018", 0.42); s.add(this.hemi);
    this.face = new THREE.SpotLight("#fff1dc", 26, 14, 0.5, 0.55, 1.2); this.face.position.set(1.2, 4.8, 4.2); this.face.castShadow = true;
    this.face.shadow.mapSize.set(2048, 2048); this.face.shadow.bias = -0.0004; this.face.shadow.normalBias = 0.02; s.add(this.face); s.add(this.face.target);
    this.douche = new THREE.SpotLight("#ffe7c4", 0, 9, 0.32, 0.5, 1.1); this.douche.position.set(0, 5.2, 0.2); this.douche.castShadow = true; this.douche.shadow.mapSize.set(1024, 1024); s.add(this.douche); s.add(this.douche.target);
    this.contre = new THREE.SpotLight("#9fc0ff", 14, 12, 0.6, 0.6, 1.2); this.contre.position.set(-2.2, 4.2, -2.8); s.add(this.contre); s.add(this.contre.target);
    this.remplissage = new THREE.DirectionalLight("#cfe0ff", 0.55); this.remplissage.position.set(-3, 2.5, 3); s.add(this.remplissage);
    s.add(this.h.racine);
    this.anim.camera = this.camera;
    // cadrage animé
    this.transition = null;
    // manipulation directe
    this.rayon = new THREE.Raycaster(); this.souris = new THREE.Vector2();
    this.selection = null; this.glisse = null; this.surSelection = null; this.surManipulation = null;
    this.matHalo = new THREE.MeshBasicMaterial({ color: "#f2b544", transparent: true, opacity: 0.22, depthWrite: false, side: THREE.BackSide });
    r.domElement.addEventListener("pointerdown", (e) => this.appui(e));
    r.domElement.addEventListener("pointermove", (e) => this.glisser(e));
    window.addEventListener("pointerup", () => this.relache());
    new ResizeObserver(() => this.redimensionner()).observe(conteneur);
    this.redimensionner();
    this.horloge = new THREE.Clock();
    this.boucle = this.boucle.bind(this);
    this.avantImage = null;
    this.suivi = true;
  }
  redimensionner() {
    const w = this.conteneur.clientWidth || 640, h = this.conteneur.clientHeight || 480;
    this.rendu.setSize(w, h, false); this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  }
  demarrer() { this.rendu.setAnimationLoop(this.boucle); }
  boucle() {
    const dt = this.horloge.getDelta(), t = this.horloge.elapsedTime;
    this.avantImage?.(dt, t);
    if (this.transition) {
      const T = this.transition; T.u = Math.min(1, T.u + dt / T.duree);
      const e = T.u * T.u * (3 - 2 * T.u);
      this.camera.position.lerpVectors(T.p0, T.p1, e); this.controles.target.lerpVectors(T.c0, T.c1, e);
      if (T.u >= 1) this.transition = null;
    }
    const cible = this.h.racine.position;
    // suivi : la caméra accompagne les déplacements du personnage sur le plateau
    if (this.dernierePos && this.suivi && !this.transition) {
      const dx = cible.x - this.dernierePos.x, dz = cible.z - this.dernierePos.z;
      if (dx || dz) { this.camera.position.x += dx; this.camera.position.z += dz; this.controles.target.x += dx; this.controles.target.z += dz; }
    }
    this.dernierePos = cible.clone();
    this.douche.target.position.set(cible.x, 0, cible.z); this.douche.position.set(cible.x, 5.2, cible.z + 0.2);
    this.face.target.position.set(cible.x, 1, cible.z); this.contre.target.position.set(cible.x, 1.2, cible.z);
    this.controles.update();
    this.rendu.render(this.scene, this.camera);
  }
  /* vues de cadrage, relatives à la position et à la taille du personnage */
  vue(nom, duree = 0.9) {
    const k = this.h.apparence.taille / 178, R = this.h.racine.position, yaw = this.h.racine.rotation.y;
    const tete = this.h.pointYeux(new THREE.Vector3());
    const V = {
      face: [[0, 1.45 * k, 4.2], [0, 1.05 * k, 0]], plein_pied: [[0, 1.3 * k, 4.6], [0, 0.95 * k, 0]], plan_large: [[0, 2.6, 8.5], [0, 1.0, -0.4]],
      plan_americain: [[0, 1.45 * k, 2.6], [0, 1.25 * k, 0]], profil: [[3.6, 1.4 * k, 0.3], [0, 1.05 * k, 0]], trois_quarts: [[2.5, 1.55 * k, 3.1], [0, 1.1 * k, 0]],
      dos: [[0, 1.6 * k, -3.8], [0, 1.1 * k, 0]], plongee: [[0, 4.6, 2.6], [0, 0.8 * k, 0]], contre_plongee: [[0, 0.45, 2.6], [0, 1.35 * k, 0]],
    };
    let p, c;
    if (nom === "gros_plan") {
      const avant = new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw));
      p = tete.clone().addScaledVector(avant, 0.95).add(new THREE.Vector3(0, 0.03, 0)); c = tete.clone().add(new THREE.Vector3(0, -0.02, 0));
    } else {
      const [pp, cc] = V[nom] || V.face;
      const rot = (v) => new THREE.Vector3(...v).applyAxisAngle(new THREE.Vector3(0, 1, 0), nom === "plan_large" ? 0 : yaw);
      p = rot(pp).add(new THREE.Vector3(R.x, 0, R.z)); c = new THREE.Vector3(cc[0] + R.x, cc[1], cc[2] + R.z);
    }
    this.transition = { p0: this.camera.position.clone(), p1: p, c0: this.controles.target.clone(), c1: c, u: 0, duree };
  }
  lumiere(mode) {
    const M = {
      plein_feux: { hemi: 0.42, face: 26, douche: 0, contre: 14, rempl: 0.55, couleur: "#fff1dc" },
      douche: { hemi: 0.06, face: 2, douche: 60, contre: 6, rempl: 0.05, couleur: "#fff1dc" },
      contre_jour: { hemi: 0.08, face: 3, douche: 0, contre: 70, rempl: 0.08, couleur: "#fff1dc" },
      chaude: { hemi: 0.3, face: 28, douche: 8, contre: 8, rempl: 0.25, couleur: "#ffc98a" },
      froide: { hemi: 0.35, face: 22, douche: 0, contre: 20, rempl: 0.6, couleur: "#bcd3ff" },
    }[mode];
    if (!M) return;
    this.hemi.intensity = M.hemi; this.face.intensity = M.face; this.douche.intensity = M.douche; this.contre.intensity = M.contre; this.remplissage.intensity = M.rempl;
    this.face.color.set(M.couleur);
  }
  /* ── manipulation ────────────────────────────────────── */
  viser(e) {
    const r = this.rendu.domElement.getBoundingClientRect();
    this.souris.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    this.rayon.setFromCamera(this.souris, this.camera);
    const t = this.rayon.intersectObjects(this.h.zones, false)[0];
    return t ? t.object.userData.zone : null;
  }
  selectionner(zone) {
    for (const h of this.halos || []) h.parent?.remove(h);
    this.halos = [];
    this.selection = zone;
    if (zone) for (const m of this.h.zones) if (m.userData.zone === zone) {
      const h = new THREE.Mesh(m.geometry, this.matHalo); h.scale.setScalar(1.07); h.renderOrder = 2; h.raycast = () => {}; h.layers.set(1);
      m.add(h); this.halos.push(h);
    }
    this.surSelection?.(zone);
  }
  appui(e) {
    if (e.button !== 0) return;
    const zone = this.viser(e);
    if (!zone) { if (!e.shiftKey) this.selectionner(null); return; }
    this.selectionner(zone);
    this.controles.enabled = false;
    this.glisse = { x: e.clientX, y: e.clientY, zone };
    this.rendu.domElement.setPointerCapture?.(e.pointerId);
  }
  glisser(e) {
    if (!this.glisse) return;
    const dx = e.clientX - this.glisse.x, dy = e.clientY - this.glisse.y;
    this.glisse.x = e.clientX; this.glisse.y = e.clientY;
    let [vert, horiz] = ZONES[this.glisse.zone] || [];
    // main + Maj : fermeture des doigts (vertical) et rotation de l'avant-bras, pronation-supination (horizontal)
    const m = /^main_([gd])$/.exec(this.glisse.zone);
    if (m && e.shiftKey) { vert = `main_${m[1]}.fermeture`; horiz = `poignet_${m[1]}.rotation`; }
    // le sens latéral dépend du côté et de l'orientation du personnage par rapport à la caméra
    const versCam = new THREE.Vector3().subVectors(this.camera.position, this.h.racine.position);
    const face = Math.sign(versCam.x * Math.sin(this.h.racine.rotation.y) + versCam.z * Math.cos(this.h.racine.rotation.y)) || 1;
    const cote = /_d$/.test(this.glisse.zone) ? -1 : 1;
    const appliquer = (spec, delta) => {
      if (!spec) return;
      const neg = spec.startsWith("-"), dof = spec.replace(/^-/, "");
      this.surManipulation?.(dof, (neg ? -1 : 1) * delta);
    };
    appliquer(vert, -dy * 0.45);
    const lat = /\.(abduction)$/.test(horiz || "") ? dx * 0.45 * cote * face : dx * 0.45 * face;
    appliquer(horiz, lat);
  }
  relache() { if (this.glisse) { this.glisse = null; this.controles.enabled = true; this.surFinManipulation?.(); } }
  capture() { return this.rendu.domElement.toDataURL("image/png"); }

  /* ── Caméra des yeux ─────────────────────────────────── */
  /* Position entre les yeux, juste devant le nez (le visage n'apparaît pas dans l'image) ; orientation de la tête,
     roulis compris (l'horizon penche quand la tête s'incline), ou du regard si suivreRegard ; champ selon le zoom. */
  majCameraYeux() {
    const g = this.h.visage.g, c = this.camYeux;
    g.updateWorldMatrix(true, false);
    const pos = new THREE.Vector3(0, 0.012, 0.118).applyMatrix4(g.matrixWorld);
    const q = new THREE.Quaternion(); g.getWorldQuaternion(q);
    const dir = new THREE.Vector3(0, 0, 1);
    if (this.suivreRegard) {
      const r = this.h.visage.yeux[0].pivot.rotation;          // rotation.x = -tangage du regard, rotation.y = lacet
      dir.applyEuler(new THREE.Euler(r.x, r.y, 0, "YXZ"));
    }
    dir.applyQuaternion(q);
    c.position.copy(pos); c.up.set(0, 1, 0).applyQuaternion(q);
    c.lookAt(pos.clone().add(dir));
    const h = THREE.MathUtils.degToRad(this.champH) / this.zoom;
    c.fov = THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(h / 2) / c.aspect)); c.updateProjectionMatrix();
    c.updateMatrixWorld();
  }
  rendreCamera(rendu) {
    this.majCameraYeux();
    const f = this.scene.fog, avant = [f.near, f.far];
    f.near = 16; f.far = 34;                               // le brouillard du cadrage de scène masquerait le fond de la salle
    rendu.render(this.scene, this.camYeux);
    [f.near, f.far] = avant;
  }
  /* La salle (au-delà du nez de scène, z > 2,6 m) est-elle dans le champ ? Avertissement pour la caméra réelle (G-06). */
  salleDansLeChamp() {
    const fr = new THREE.Frustum(), m = new THREE.Matrix4();
    m.multiplyMatrices(this.camYeux.projectionMatrix, this.camYeux.matrixWorldInverse); fr.setFromProjectionMatrix(m);
    return fr.intersectsBox(new THREE.Box3(new THREE.Vector3(-7, 0, 2.7), new THREE.Vector3(7, 2.2, 16)));
  }
}
