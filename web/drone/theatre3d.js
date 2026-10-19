/* Robo-Scène — théâtre en 3D pour le drone : plateau, cadre de scène, porteuses, salle, balcon, régie, zones de vol,
   interprètes, drone (hélices, protège-hélices, couronne de DEL, nacelle et caméra), trajectoire de la conduite,
   jumeau du drone réel, et caméra embarquée (vue rendue dans un second canevas, au format 16:9).
   Toutes les cotes viennent de salle.json : modifier le relevé suffit à redessiner la salle. */
import * as THREE from "three";
import { OrbitControls } from "three/addons/OrbitControls.js";

const boite = (b) => ({ cx: (b.x[0] + b.x[1]) / 2, cy: (b.y[0] + b.y[1]) / 2, cz: (b.z[0] + b.z[1]) / 2,
  w: b.x[1] - b.x[0], h: b.y[1] - b.y[0], d: b.z[1] - b.z[0] });
const V = (a) => new THREE.Vector3(a[0], a[1], a[2]);

function texturePlancher() {
  const c = document.createElement("canvas"); c.width = 512; c.height = 512;
  const g = c.getContext("2d");
  g.fillStyle = "#231a13"; g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 16; i++) {
    const y = i * 32; g.fillStyle = `hsl(26, 26%, ${13 + ((i * 37) % 7)}%)`; g.fillRect(0, y + 1, 512, 30);
    g.fillStyle = "#120d09"; g.fillRect(0, y, 512, 1.5); g.fillRect((i * 151) % 512, y, 1.5, 32);
  }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(4, 3); t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
function texteSprite(texte, couleur = "#f2b544", taille = 0.5) {
  const c = document.createElement("canvas"); c.width = 512; c.height = 96;
  const g = c.getContext("2d"); g.font = "600 52px system-ui, sans-serif"; g.fillStyle = couleur; g.textAlign = "center"; g.textBaseline = "middle";
  g.shadowColor = "#000"; g.shadowBlur = 8; g.fillText(texte, 256, 48);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, transparent: true, depthWrite: false, depthTest: false }));
  s.scale.set(taille * 5.33, taille, 1); s.renderOrder = 10; return s;
}
function etiquetteSol(texte) {
  const c = document.createElement("canvas"); c.width = 256; c.height = 64;
  const g = c.getContext("2d"); g.font = "600 34px system-ui, sans-serif"; g.fillStyle = "rgba(242,181,68,.6)"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(texte, 128, 32);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const m = new THREE.Mesh(new THREE.PlaneGeometry(1.6, 0.4), new THREE.MeshBasicMaterial({ map: t, transparent: true, depthWrite: false }));
  m.rotation.x = -Math.PI / 2; return m;
}

/* ── Le drone ──────────────────────────────────────────────── */
export function modeleDrone({ fantome = false } = {}) {
  const g = new THREE.Group(); g.name = fantome ? "drone-reel" : "drone";
  const mat = fantome ? new THREE.MeshBasicMaterial({ color: "#6fa8ff", wireframe: true, transparent: true, opacity: 0.7 })
    : new THREE.MeshStandardMaterial({ color: "#2a2e36", roughness: 0.45, metalness: 0.35 });
  const matBras = fantome ? mat : new THREE.MeshStandardMaterial({ color: "#16181d", roughness: 0.6 });
  const corps = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.06, 0.22), mat); corps.castShadow = !fantome; g.add(corps);
  const capot = new THREE.Mesh(new THREE.SphereGeometry(0.075, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2), mat); capot.position.y = 0.03; capot.scale.set(1, 0.6, 1.3); g.add(capot);
  g.userData.helices = [];
  const L = 0.17;
  for (const [sx, sz] of [[1, 1], [-1, 1], [1, -1], [-1, -1]]) {
    const bras = new THREE.Mesh(new THREE.BoxGeometry(0.018, 0.016, L * 1.45), matBras);
    bras.position.set((sx * L) / 2, 0, (sz * L) / 2); bras.rotation.y = Math.atan2(sx, sz); g.add(bras);
    const moteur = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.02, 0.03, 14), matBras); moteur.position.set(sx * L, 0.015, sz * L); g.add(moteur);
    const helice = new THREE.Group(); helice.position.set(sx * L, 0.034, sz * L);
    const pale = new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.003, 0.016), fantome ? mat : new THREE.MeshStandardMaterial({ color: "#c9ced8", roughness: 0.3 }));
    helice.add(pale); const p2 = pale.clone(); p2.rotation.y = Math.PI / 2; helice.add(p2);
    helice.userData.sens = sx * sz; g.add(helice); g.userData.helices.push(helice);
    const disque = new THREE.Mesh(new THREE.CircleGeometry(0.078, 24), new THREE.MeshBasicMaterial({ color: "#d9dde5", transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide }));
    disque.rotation.x = -Math.PI / 2; disque.position.copy(helice.position); g.add(disque); helice.userData.disque = disque;
    const garde = new THREE.Mesh(new THREE.TorusGeometry(0.088, 0.005, 6, 32), fantome ? mat : new THREE.MeshStandardMaterial({ color: "#3a404c", roughness: 0.5 }));
    garde.rotation.x = Math.PI / 2; garde.position.set(sx * L, 0.034, sz * L); g.add(garde);
  }
  // couronne de DEL (couleur réglable par la conduite)
  const del = new THREE.Mesh(new THREE.TorusGeometry(0.1, 0.008, 8, 40), new THREE.MeshStandardMaterial({ color: "#f2b544", emissive: "#f2b544", emissiveIntensity: 2.2 }));
  del.rotation.x = Math.PI / 2; del.position.y = -0.02; g.add(del); g.userData.del = del;
  if (!fantome) { const lum = new THREE.PointLight("#f2b544", 0.6, 3, 2); lum.position.y = -0.05; g.add(lum); g.userData.lumiere = lum; }
  // nacelle (lacet du drone ; tangage de la caméra) à l'avant : l'avant est +z local
  const nacelle = new THREE.Group(); nacelle.position.set(0, -0.05, 0.1); g.add(nacelle);
  const cam = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.04, 0.04), fantome ? mat : new THREE.MeshStandardMaterial({ color: "#0d0f13", roughness: 0.4 }));
  nacelle.add(cam);
  const objectif = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.014, 0.02, 16), new THREE.MeshStandardMaterial({ color: "#223", metalness: 0.8, roughness: 0.2 }));
  objectif.rotation.x = Math.PI / 2; objectif.position.z = 0.026; nacelle.add(objectif);
  g.userData.nacelle = nacelle;
  // halo de repérage (visible de loin, non rendu par la caméra embarquée)
  if (!fantome) {
    const halo = new THREE.Mesh(new THREE.RingGeometry(0.26, 0.29, 40), new THREE.MeshBasicMaterial({ color: "#f2b544", transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthWrite: false }));
    halo.rotation.x = -Math.PI / 2; halo.layers.set(1); g.add(halo); g.userData.halo = halo;
  }
  return g;
}

export class Theatre {
  constructor(conteneur, salle) {
    this.salle = salle; this.conteneur = conteneur;
    const r = (this.rendu = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true }));
    r.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    r.shadowMap.enabled = true; r.shadowMap.type = THREE.PCFSoftShadowMap;
    r.toneMapping = THREE.ACESFilmicToneMapping; r.outputColorSpace = THREE.SRGBColorSpace;
    conteneur.appendChild(r.domElement);
    r.domElement.setAttribute("aria-label", "Théâtre en 3D : plateau, salle et drone ; glisser pour tourner, molette pour s'approcher");
    const s = (this.scene = new THREE.Scene());
    s.background = new THREE.Color("#06070a");
    this.camera = new THREE.PerspectiveCamera(42, 1, 0.05, 120);
    this.camera.layers.enable(1);
    this.controles = new OrbitControls(this.camera, r.domElement);
    this.controles.enableDamping = true; this.controles.dampingFactor = 0.08; this.controles.maxDistance = 45;
    this.vue("regie", 0);
    this.construireSalle();
    this.groupeZones = new THREE.Group(); s.add(this.groupeZones);
    this.groupeInterpretes = new THREE.Group(); s.add(this.groupeInterpretes);
    this.groupeTrajet = new THREE.Group(); s.add(this.groupeTrajet);
    this.drone = modeleDrone(); s.add(this.drone);
    this.jumeau = modeleDrone({ fantome: true }); this.jumeau.visible = false; this.jumeau.traverse((o) => o.layers.set(1)); s.add(this.jumeau);
    this.poursuite = new THREE.SpotLight("#fff3df", 0, 40, 0.07, 0.5, 1.4); this.poursuite.position.set(0, 7, 19); s.add(this.poursuite); s.add(this.poursuite.target);
    // caméra embarquée : 16:9 ; champ horizontal de 82° à ×1 (grand-angle typique d'un drone)
    this.camDrone = new THREE.PerspectiveCamera(50, 16 / 9, 0.05, 80);
    this.champH = 82; this.zoom = 1;
    this.nacelleTangage = -15; this.viser = null;
    this.rayon = new THREE.Raycaster(); this.souris = new THREE.Vector2();
    this.plans = [new THREE.Plane(new THREE.Vector3(0, 1, 0), 0)];
    this.surClic = null; this.outil = null;
    r.domElement.addEventListener("pointerdown", (e) => { this.debutClic = [e.clientX, e.clientY]; });
    r.domElement.addEventListener("pointerup", (e) => {
      if (!this.debutClic || Math.hypot(e.clientX - this.debutClic[0], e.clientY - this.debutClic[1]) > 5) return;
      const p = this.pointSol(e); if (p && this.surClic) this.surClic(p, e);
    });
    new ResizeObserver(() => this.redimensionner()).observe(conteneur);
    this.redimensionner();
  }

  redimensionner() {
    const w = this.conteneur.clientWidth || 640, h = this.conteneur.clientHeight || 480;
    this.rendu.setSize(w, h, false); this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  }

  /* Point cliqué sur le plateau ou sur le sol de la salle. */
  pointSol(e) {
    const b = this.rendu.domElement.getBoundingClientRect();
    this.souris.set(((e.clientX - b.left) / b.width) * 2 - 1, -((e.clientY - b.top) / b.height) * 2 + 1);
    this.rayon.setFromCamera(this.souris, this.camera);
    const out = new THREE.Vector3();
    const hit = this.rayon.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), out);
    if (!hit) return null;
    if (out.z > this.salle.volumes.plateau.z[1]) {
      const y0 = this.salle.volumes.salle.y[0];
      this.rayon.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), -y0), out);
    }
    return [out.x, out.y, out.z];
  }

  construireSalle() {
    const s = this.scene, S = this.salle, P = boite(S.volumes.plateau), SA = boite(S.volumes.salle);
    const sombre = new THREE.MeshStandardMaterial({ color: "#14161b", roughness: 0.95 });
    const bordeaux = new THREE.MeshStandardMaterial({ color: "#2e0a10", roughness: 0.9 });
    // plateau
    const sol = new THREE.Mesh(new THREE.PlaneGeometry(P.w, P.d), new THREE.MeshStandardMaterial({ map: texturePlancher(), roughness: 0.85 }));
    sol.rotation.x = -Math.PI / 2; sol.position.set(P.cx, 0, P.cz); sol.receiveShadow = true; s.add(sol);
    // Boîtes vues de l'intérieur, sans la face qui donne sur l'autre volume (sinon le plateau masquerait la salle) ni le sol
    const invisible = new THREE.MeshBasicMaterial({ visible: false });
    const faces = (couleur, sauf) => [0, 1, 2, 3, 4, 5].map((i) => (sauf.includes(i) ? invisible
      : new THREE.MeshStandardMaterial({ color: couleur, side: THREE.BackSide, roughness: 1 })));   // ordre : +x, −x, +y, −y, +z, −z
    const cage = new THREE.Mesh(new THREE.BoxGeometry(P.w + 0.2, P.h + 1.2, P.d), faces("#0b0c10", [3, 4]));
    cage.position.set(P.cx, (P.h + 1.2) / 2, P.cz); s.add(cage);
    // salle : sol, murs, plafond
    const solSalle = new THREE.Mesh(new THREE.PlaneGeometry(SA.w, SA.d), new THREE.MeshStandardMaterial({ color: "#1d1416", roughness: 1 }));
    solSalle.rotation.x = -Math.PI / 2; solSalle.position.set(SA.cx, S.volumes.salle.y[0], SA.cz); solSalle.receiveShadow = true; s.add(solSalle);
    const murs = new THREE.Mesh(new THREE.BoxGeometry(SA.w + 1, SA.h + 1.6, SA.d), faces("#1a1214", [3, 5]));
    murs.position.set(SA.cx, SA.cy + 0.8, SA.cz); s.add(murs);
    // obstacles (cadre, manteau, porteuses, balcon, régie, nez de scène)
    for (const o of S.obstacles) {
      const b = boite(o);
      const mat = o.id.startsWith("cadre") || o.id === "manteau" ? bordeaux : o.id.startsWith("porteuse") ? new THREE.MeshStandardMaterial({ color: "#2b2f36", metalness: 0.6, roughness: 0.4 }) : sombre;
      const m = new THREE.Mesh(new THREE.BoxGeometry(b.w, b.h, b.d), mat); m.position.set(b.cx, b.cy, b.cz); m.castShadow = m.receiveShadow = true; s.add(m);
      if (o.id.startsWith("porteuse")) {          // projecteurs suspendus
        for (let x = o.x[0] + 0.8; x < o.x[1]; x += 1.6) {
          const pr = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.13, 0.32, 12), new THREE.MeshStandardMaterial({ color: "#111", roughness: 0.5 }));
          pr.position.set(x, o.y[0] - 0.2, b.cz); pr.rotation.x = 0.5; s.add(pr);
        }
      }
    }
    // rideaux à l'allemande ouverts, frise
    const rideau = new THREE.MeshStandardMaterial({ color: "#3c0a12", roughness: 1, side: THREE.DoubleSide });
    for (const sx of [-1, 1]) { const r = new THREE.Mesh(new THREE.PlaneGeometry(1.4, 6.4), rideau); r.position.set(sx * 4.4, 3.2, -0.45); s.add(r); }
    // sièges (instanciés) et public (silhouettes, visibles en mode représentation)
    const geoSiege = new THREE.BoxGeometry(0.46, 0.85, 0.45), geoPers = new THREE.CapsuleGeometry(0.17, 0.42, 4, 8);
    const places = [];
    for (const b of S.public) {
      const rang = 0.9, larg = 0.52;
      const nr = Math.floor((b.z[1] - b.z[0]) / rang), nc = Math.floor((b.x[1] - b.x[0]) / larg);
      for (let i = 0; i < nr; i++) for (let j = 0; j < nc; j++) {
        const z = b.z[0] + rang * (i + 0.5), x = b.x[0] + larg * (j + 0.5);
        const pente = b.id.startsWith("parterre") ? (b.y[1] - b.y[0] - 0.4) * (i / Math.max(1, nr - 1)) : 0;
        places.push([x, b.y[0] + pente, z]);
      }
    }
    const sieges = new THREE.InstancedMesh(geoSiege, new THREE.MeshStandardMaterial({ color: "#5c1520", roughness: 0.9 }), places.length);
    this.publicMesh = new THREE.InstancedMesh(geoPers, new THREE.MeshStandardMaterial({ color: "#3b4252", roughness: 0.9 }), places.length);
    const M = new THREE.Matrix4();
    places.forEach(([x, y, z], i) => {
      M.makeTranslation(x, y + 0.42, z); sieges.setMatrixAt(i, M);
      M.makeTranslation(x, y + 0.95, z - 0.05); this.publicMesh.setMatrixAt(i, M);
    });
    sieges.receiveShadow = true; s.add(sieges); this.publicMesh.visible = false; s.add(this.publicMesh);
    // aire de décollage
    const a = S.aire;
    const aire = new THREE.Mesh(new THREE.RingGeometry(a.rayon * 0.82, a.rayon, 48), new THREE.MeshBasicMaterial({ color: "#f2b544", side: THREE.DoubleSide }));
    aire.rotation.x = -Math.PI / 2; aire.position.set(a.centre[0], 0.004, a.centre[2]); s.add(aire);
    const H = etiquetteSol("H"); H.scale.set(0.5, 1.4, 1); H.position.set(a.centre[0], 0.005, a.centre[2]); s.add(H);
    for (const [t, x, z] of [["COUR", 5, -1.2], ["JARDIN", -5, -1.2], ["LOINTAIN", 0, -8.4], ["AVANT-SCÈNE", 0, 1.0]]) { const e = etiquetteSol(t); e.position.set(x, 0.003, z); s.add(e); }
    // lumières
    s.add(new THREE.HemisphereLight("#b4bfd6", "#2a2022", 0.9));
    const face = new THREE.SpotLight("#fff1dc", 1400, 40, 0.6, 0.6, 1.6); face.position.set(0, 9, 10); face.target.position.set(0, 0, -3);
    face.castShadow = true; face.shadow.mapSize.set(2048, 2048); s.add(face); s.add(face.target);
    const contre = new THREE.SpotLight("#9fc0ff", 500, 25, 0.75, 0.6, 1.6); contre.position.set(-3, 8, -9); contre.target.position.set(0, 0, -2); s.add(contre); s.add(contre.target);
    const service = new THREE.PointLight("#ffd9a8", 50, 40, 1.6); service.position.set(0, 7, 9); s.add(service);
    this.lumieres = { face, contre, service };
  }

  /* Zones : volumes ouverts (arêtes vertes), obstacles (rouge), colonnes du public ou fauteuils (selon le mode). */
  dessinerZones(mode, visible = true) {
    const S = this.salle, R = S.regles, M = S.modes[mode], g = this.groupeZones;
    g.clear(); g.visible = visible;
    const arete = (b, couleur, opacite = 1) => {
      const k = boite(b), e = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(k.w, k.h, k.d)), new THREE.LineBasicMaterial({ color: couleur, transparent: true, opacity: opacite }));
      e.position.set(k.cx, k.cy, k.cz); e.layers.set(1); g.add(e);
    };
    const bloc = (b, couleur, opacite) => {
      const k = boite(b), m = new THREE.Mesh(new THREE.BoxGeometry(k.w, k.h, k.d), new THREE.MeshBasicMaterial({ color: couleur, transparent: true, opacity: opacite, depthWrite: false }));
      m.position.set(k.cx, k.cy, k.cz); m.layers.set(1); g.add(m);
    };
    const m = R.marge_m;
    for (const id of M.volumes) {
      const v = S.volumes[id];
      arete({ x: [v.x[0] + m, v.x[1] - m], y: [v.y[0] + R.hauteur_min_m, v.y[1] - m], z: [v.z[0] + (id === "salle" ? 0 : m), v.z[1] - (id === "plateau" && M.volumes.includes("salle") ? 0 : m)] }, "#4cc38a", 0.75);
    }
    for (const o of S.obstacles) bloc({ x: [o.x[0] - m, o.x[1] + m], y: [o.y[0] - m, o.y[1] + m], z: [o.z[0] - m, o.z[1] + m] }, "#ff5d5d", 0.08);
    this.publicMesh.visible = mode === "representation";
    if (M.volumes.includes("salle")) {
      for (const b of S.public) {
        if (M.public === "colonnes") { const mp = R.marge_public_m; bloc({ x: [b.x[0] - mp, b.x[1] + mp], y: [S.volumes.salle.y[0], S.volumes.salle.y[1]], z: [b.z[0] - mp, b.z[1] + mp] }, "#ff5d5d", 0.1); }
        else bloc({ x: [b.x[0] - m, b.x[1] + m], y: [b.y[0], b.y[0] + R.hauteur_fauteuils_m + m], z: [b.z[0] - m, b.z[1] + m] }, "#e8a33d", 0.12);
      }
    } else {
      // salle fermée : voile rouge sur l'ouverture du cadre
      const voile = new THREE.Mesh(new THREE.PlaneGeometry(10, 6.5), new THREE.MeshBasicMaterial({ color: "#ff5d5d", transparent: true, opacity: 0.07, side: THREE.DoubleSide, depthWrite: false }));
      voile.position.set(0, 3.25, S.volumes.plateau.z[1] - m); voile.layers.set(1); g.add(voile);
    }
  }

  dessinerInterpretes(liste) {
    const g = this.groupeInterpretes, R = this.salle.regles; g.clear();
    liste.forEach((it, i) => {
      const corps = new THREE.Mesh(new THREE.CapsuleGeometry(0.2, 1.2, 4, 10), new THREE.MeshStandardMaterial({ color: "#c58b4a", roughness: 0.7 }));
      corps.position.set(it.x, 0.8, it.z); corps.castShadow = true; g.add(corps);
      const cyl = new THREE.Mesh(new THREE.CylinderGeometry(R.rayon_interpretes_m, R.rayon_interpretes_m, R.hauteur_interpretes_m, 36, 1, true),
        new THREE.MeshBasicMaterial({ color: "#e8a33d", transparent: true, opacity: 0.1, side: THREE.DoubleSide, depthWrite: false }));
      cyl.position.set(it.x, R.hauteur_interpretes_m / 2, it.z); cyl.layers.set(1); g.add(cyl);
      const t = texteSprite(`Interprète ${i + 1}`, "#e8a33d", 0.4); t.position.set(it.x, 2.0, it.z); t.layers.set(1); g.add(t);
    });
  }

  /* Trajectoire de la conduite compilée : segments (vert si valide, rouge sinon) et repères numérotés. */
  dessinerTrajet(comp) {
    const g = this.groupeTrajet; g.clear();
    if (!comp) return;
    for (const s of comp.segments) {
      const geo = new THREE.BufferGeometry().setFromPoints([V(s.p0), V(s.p1)]);
      const l = new THREE.Line(geo, new THREE.LineDashedMaterial({ color: comp.ok ? "#4cc38a" : "#ff5d5d", dashSize: 0.18, gapSize: 0.1 }));
      l.computeLineDistances(); l.layers.set(1); g.add(l);
      if (s.action !== "stationnaire") {
        const b = new THREE.Mesh(new THREE.SphereGeometry(0.07, 12, 8), new THREE.MeshBasicMaterial({ color: "#f2b544" })); b.position.copy(V(s.p1)); b.layers.set(1); g.add(b);
        const t = texteSprite(s.id, "#f2b544", 0.42); t.position.copy(V(s.p1)).add(new THREE.Vector3(0, 0.25, 0)); t.layers.set(1); g.add(t);
      }
    }
  }

  vue(nom, duree = 0.8) {
    const V3 = (a) => new THREE.Vector3(...a);
    const VUES = {
      regie: [[0, 6.2, 13.4], [0, 2.2, -3]], salle: [[2.5, 1.2, 9], [0, 2.5, -2]], plateau: [[-6.5, 2.2, -1], [2, 2.5, 2]],
      dessus: [[0, 30, 5.5], [0, 0, 5.4]], cour: [[12, 5, -2], [0, 2, -2]], lointain: [[0, 4, -8.7], [0, 2.5, 6]],
    };
    if (nom === "poursuite") { this.suivre = true; return; }
    this.suivre = false;
    const [p, c] = VUES[nom] || VUES.regie;
    if (!duree) { this.camera.position.copy(V3(p)); this.controles.target.copy(V3(c)); this.controles.update(); return; }
    this.transition = { p0: this.camera.position.clone(), p1: V3(p), c0: this.controles.target.clone(), c1: V3(c), u: 0, duree };
  }

  poser(etat, temps) {
    const d = this.drone;
    d.position.set(etat.p[0], etat.p[1] + 0.035, etat.p[2]);
    d.rotation.set(0, 0, 0);
    d.rotation.y = etat.lacetRad;
    // inclinaison apparente proportionnelle à l'accélération horizontale (lecture du mouvement)
    const ax = etat.inclinaison || [0, 0];
    d.rotateX(ax[0]); d.rotateZ(ax[1]);
    for (const h of d.userData.helices) { h.rotation.y += h.userData.sens * etat.helices * 60 * (temps || 0.016); h.userData.disque.material.opacity = 0.12 * etat.helices; h.children.forEach((c) => (c.visible = etat.helices < 0.25)); }
    d.userData.nacelle.rotation.x = -THREE.MathUtils.degToRad(this.nacelleTangage);
    if (d.userData.halo) d.userData.halo.visible = true;
  }

  couleurDEL(c) { const d = this.drone.userData; d.del.material.color.set(c); d.del.material.emissive.set(c); d.lumiere?.color.set(c); }

  poursuiteSur(actif) { this.poursuite.intensity = actif ? 2600 : 0; }

  /* Caméra embarquée : position de la nacelle, visée (point ou tangage), champ selon le zoom. */
  majCameraDrone() {
    const n = this.drone.userData.nacelle, c = this.camDrone;
    n.updateWorldMatrix(true, false);
    const pos = new THREE.Vector3(); n.getWorldPosition(pos); pos.add(new THREE.Vector3(0, -0.01, 0));
    c.position.copy(pos);
    if (this.viser) {
      const cible = V(this.viser);
      c.up.set(0, 1, 0); c.lookAt(cible);
      // la nacelle suit la visée (lecture dans la vue de la salle)
      const dir = cible.clone().sub(pos).normalize();
      this.nacelleTangage = THREE.MathUtils.radToDeg(Math.asin(Math.max(-1, Math.min(1, dir.y))));
    } else {
      const lacet = this.drone.rotation.y, t = THREE.MathUtils.degToRad(this.nacelleTangage);
      const dir = new THREE.Vector3(Math.sin(lacet) * Math.cos(t), Math.sin(t), Math.cos(lacet) * Math.cos(t));
      c.up.set(0, 1, 0); c.lookAt(pos.clone().add(dir));
    }
    const h = THREE.MathUtils.degToRad(this.champH) / this.zoom;
    c.fov = THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(h / 2) / c.aspect)); c.updateProjectionMatrix();
  }

  /* Le public est-il dans le champ de la caméra embarquée ? (avertissement de vie privée pour le drone réel) */
  publicDansLeChamp() {
    if (!this.publicMesh.visible) return false;
    const fr = new THREE.Frustum(), m = new THREE.Matrix4();
    this.camDrone.updateMatrixWorld(); m.multiplyMatrices(this.camDrone.projectionMatrix, this.camDrone.matrixWorldInverse); fr.setFromProjectionMatrix(m);
    return this.salle.public.some((b) => fr.intersectsBox(new THREE.Box3(new THREE.Vector3(b.x[0], b.y[0], b.z[0]), new THREE.Vector3(b.x[1], b.y[1] + 1.2, b.z[1]))));
  }

  rendre(dt) {
    if (this.transition) {
      const T = this.transition; T.u = Math.min(1, T.u + dt / T.duree); const e = T.u * T.u * (3 - 2 * T.u);
      this.camera.position.lerpVectors(T.p0, T.p1, e); this.controles.target.lerpVectors(T.c0, T.c1, e);
      if (T.u >= 1) this.transition = null;
    }
    if (this.suivre) {
      const d = this.drone.position, l = this.drone.rotation.y;
      const souhait = new THREE.Vector3(d.x - Math.sin(l) * 2.4, d.y + 0.9, d.z - Math.cos(l) * 2.4);
      this.camera.position.lerp(souhait, Math.min(1, dt * 3)); this.controles.target.lerp(d, Math.min(1, dt * 6));
    }
    this.poursuite.target.position.copy(this.drone.position);
    this.controles.update();
    this.rendu.render(this.scene, this.camera);
  }

  /* Rendu de la caméra embarquée dans un rendu dédié (le halo et les zones, sur la couche 1, n'y figurent pas). */
  rendreCamera(rendu) { this.majCameraDrone(); rendu.render(this.scene, this.camDrone); }
}
