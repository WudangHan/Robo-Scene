/* Robo-Scène — théâtre en 3D pour le chien de scène : reprend la salle du drone (mêmes cotes, même salle.json)
   et y ajoute les escaliers d'accès à la salle, le sol praticable par mode, le chien (12 articulations, tête
   orientable, caméra frontale, yeux à DEL), son jumeau réel et la caméra de tête. */
import * as THREE from "three";
import { Theatre } from "../drone/theatre3d.js";
import { HANCHES, L1, L2, PATTES } from "./chien.js";

export function modeleChien({ fantome = false } = {}) {
  const racine = new THREE.Group(); racine.name = fantome ? "chien-reel" : "chien";
  const corps = new THREE.Group(); racine.add(corps);
  const mat = fantome ? new THREE.MeshBasicMaterial({ color: "#6fa8ff", wireframe: true, transparent: true, opacity: 0.7 })
    : new THREE.MeshStandardMaterial({ color: "#3a3f49", roughness: 0.5, metalness: 0.3 });
  const sombre = fantome ? mat : new THREE.MeshStandardMaterial({ color: "#1b1e24", roughness: 0.7 });
  const ambre = fantome ? mat : new THREE.MeshStandardMaterial({ color: "#f2b544", roughness: 0.5, emissive: "#3a2400" });
  const tronc = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.11, 0.44), mat); tronc.castShadow = !fantome; corps.add(tronc);
  const dos = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.02, 0.3), ambre); dos.position.y = 0.065; corps.add(dos);
  // tête : lacet puis tangage ; caméra et yeux à l'avant
  const cou = new THREE.Group(); cou.position.set(0, 0.04, 0.23); corps.add(cou);
  const tete = new THREE.Group(); cou.add(tete);
  const crane = new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.09, 0.12), mat); crane.position.z = 0.05; crane.castShadow = !fantome; tete.add(crane);
  const visiere = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.045, 0.01), fantome ? mat : new THREE.MeshStandardMaterial({ color: "#05070a", roughness: 0.15, metalness: 0.6 }));
  visiere.position.set(0, 0.005, 0.112); tete.add(visiere);
  const yeux = [];
  for (const sx of [-1, 1]) {
    const oeil = new THREE.Mesh(new THREE.SphereGeometry(0.009, 10, 8), new THREE.MeshStandardMaterial({ color: "#7fd3ff", emissive: "#7fd3ff", emissiveIntensity: 2.5 }));
    oeil.position.set(sx * 0.035, 0.008, 0.118); tete.add(oeil); yeux.push(oeil);
  }
  const objectif = new THREE.Object3D(); objectif.position.set(0, -0.012, 0.12); tete.add(objectif);
  racine.userData = { corps, cou, tete, yeux, objectif, pattes: {} };
  for (const k of PATTES) {
    const [a, l] = HANCHES[k];
    const abd = new THREE.Group(); abd.position.set(l, 0, a); corps.add(abd);
    const hanche = new THREE.Group(); abd.add(hanche);
    const cuisse = new THREE.Mesh(new THREE.BoxGeometry(0.045, L1, 0.05), mat); cuisse.position.y = -L1 / 2; cuisse.castShadow = !fantome; hanche.add(cuisse);
    const moteur = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 0.05, 16), sombre); moteur.rotation.z = Math.PI / 2; hanche.add(moteur);
    const genou = new THREE.Group(); genou.position.y = -L1; hanche.add(genou);
    const jambe = new THREE.Mesh(new THREE.BoxGeometry(0.028, L2, 0.03), sombre); jambe.position.y = -L2 / 2; jambe.castShadow = !fantome; genou.add(jambe);
    const pied = new THREE.Mesh(new THREE.SphereGeometry(0.022, 12, 8), fantome ? mat : new THREE.MeshStandardMaterial({ color: "#0c0d10", roughness: 0.9 })); pied.position.y = -L2; genou.add(pied);
    racine.userData.pattes[k] = { abd, hanche, genou };
  }
  if (!fantome) {
    const halo = new THREE.Mesh(new THREE.RingGeometry(0.45, 0.48, 48), new THREE.MeshBasicMaterial({ color: "#f2b544", transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthWrite: false }));
    halo.rotation.x = -Math.PI / 2; halo.layers.set(1); racine.add(halo); racine.userData.halo = halo;
  }
  return racine;
}

export class TheatreChien extends Theatre {
  constructor(conteneur, salle) {
    super(conteneur, salle);
    this.scene.remove(this.drone); this.scene.remove(this.jumeau);
    this.chien = this.drone = modeleChien(); this.scene.add(this.chien);
    this.jumeau = modeleChien({ fantome: true }); this.jumeau.visible = false; this.jumeau.traverse((o) => o.layers.set(1)); this.scene.add(this.jumeau);
    this.champH = 90; this.viser = null;
    this.construireEscaliers();
    this.vue("plateau_chien", 0);
  }

  construireEscaliers() {
    const mat = new THREE.MeshStandardMaterial({ color: "#2b211a", roughness: 0.85 });
    const bas = this.salle.volumes.salle.y[0];
    for (const s of this.salle.sol.surfaces.filter((u) => u.id.startsWith("escalier"))) {
      const n = 6, dz = (s.z[1] - s.z[0]) / n, w = s.x[1] - s.x[0];
      for (let i = 0; i < n; i++) {
        const haut = s.y0 + ((s.y1 - s.y0) * (i + 0.5)) / n, h = haut - bas;
        const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, dz), mat);
        m.position.set((s.x[0] + s.x[1]) / 2, bas + h / 2, s.z[0] + dz * (i + 0.5)); m.receiveShadow = m.castShadow = true; this.scene.add(m);
      }
      const rampe = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.04, Math.hypot(s.z[1] - s.z[0], s.y1 - s.y0)), new THREE.MeshStandardMaterial({ color: "#8a6224", metalness: 0.6 }));
      rampe.position.set(s.x[1] + 0.02, (s.y0 + s.y1) / 2 + 0.9, (s.z[0] + s.z[1]) / 2); rampe.rotation.x = Math.atan2(s.y0 - s.y1, s.z[1] - s.z[0]); this.scene.add(rampe);
    }
    // fond de la fosse (zone non praticable entre le plateau et l'avant-salle)
    const fosse = new THREE.Mesh(new THREE.PlaneGeometry(10.4, 1.2), new THREE.MeshStandardMaterial({ color: "#050506", roughness: 1 }));
    fosse.rotation.x = -Math.PI / 2; fosse.position.set(0, bas - 0.5, 2.1); this.scene.add(fosse);
  }

  /* Sol praticable du mode (vert, suivant les pentes), obstacles au sol et marges du public (rouge). */
  dessinerZones(mode, visible = true) {
    const S = this.salle.sol, M = S.modes[mode], g = this.groupeZones;
    g.clear(); g.visible = visible;
    const r = S.regles.rayon_m;
    const dalle = (x0, x1, z0, z1, y0, y1, couleur, opacite) => {
      const geo = new THREE.BufferGeometry(), e = 0.025;
      geo.setAttribute("position", new THREE.Float32BufferAttribute([x0, y0 + e, z0, x1, y0 + e, z0, x1, y1 + e, z1, x0, y1 + e, z1], 3));
      geo.setIndex([0, 2, 1, 0, 3, 2]); geo.computeVertexNormals();
      const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: couleur, transparent: true, opacity: opacite, side: THREE.DoubleSide, depthWrite: false }));
      m.layers.set(1); g.add(m);
    };
    for (const id of M.surfaces) {
      const s = S.surfaces.find((u) => u.id === id); if (!s) continue;
      dalle(s.x[0], s.x[1], s.z[0], s.z[1], s.y0, s.y1, "#4cc38a", 0.1);
      const bord = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.PlaneGeometry(s.x[1] - s.x[0], Math.hypot(s.z[1] - s.z[0], s.y1 - s.y0))), new THREE.LineBasicMaterial({ color: "#4cc38a" }));
      bord.rotation.x = -Math.PI / 2 + Math.atan2(s.y0 - s.y1, s.z[1] - s.z[0]); bord.position.set((s.x[0] + s.x[1]) / 2, (s.y0 + s.y1) / 2 + 0.03, (s.z[0] + s.z[1]) / 2);
      bord.layers.set(1); g.add(bord);
    }
    for (const id of S.obstacles) {
      const o = this.salle.obstacles.find((u) => u.id === id); if (!o) continue;
      dalle(o.x[0] - r, o.x[1] + r, o.z[0] - r, o.z[1] + r, 0, 0, "#ff5d5d", 0.18);
    }
    this.publicMesh.visible = mode === "representation";
    if (M.public === "marge") {
      const mp = r + S.regles.marge_public_m;
      for (const b of this.salle.public.filter((u) => u.y[0] < 0.5)) dalle(b.x[0] - mp, b.x[1] + mp, b.z[0] - mp, b.z[1] + mp, b.y[0], b.y[0], "#ff5d5d", 0.12);
    }
  }

  dessinerInterpretes(liste) {
    const g = this.groupeInterpretes, R = this.salle.sol.regles; g.clear();
    liste.forEach((it) => {
      const corps = new THREE.Mesh(new THREE.CapsuleGeometry(0.2, 1.2, 4, 10), new THREE.MeshStandardMaterial({ color: "#c58b4a", roughness: 0.7 }));
      corps.position.set(it.x, 0.8, it.z); corps.castShadow = true; g.add(corps);
      const disque = new THREE.Mesh(new THREE.RingGeometry(R.rayon_interpretes_m - 0.03, R.rayon_interpretes_m, 48), new THREE.MeshBasicMaterial({ color: "#e8a33d", transparent: true, opacity: 0.6, side: THREE.DoubleSide }));
      disque.rotation.x = -Math.PI / 2; disque.position.set(it.x, 0.02, it.z); disque.layers.set(1); g.add(disque);
    });
  }

  dessinerTrajet(comp, hauteur) {
    const g = this.groupeTrajet; g.clear();
    if (!comp) return;
    for (const s of comp.segments.filter((u) => u.action === "aller")) {
      const pts = [];
      for (let i = 0; i <= 20; i++) { const u = i / 20, x = s.p0[0] + (s.p1[0] - s.p0[0]) * u, z = s.p0[1] + (s.p1[1] - s.p0[1]) * u; pts.push(new THREE.Vector3(x, (hauteur(x, z) ?? 0) + 0.04, z)); }
      const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineDashedMaterial({ color: comp.ok ? "#4cc38a" : "#ff5d5d", dashSize: 0.15, gapSize: 0.08 }));
      l.computeLineDistances(); l.layers.set(1); g.add(l);
      const y = (hauteur(s.p1[0], s.p1[1]) ?? 0) + 0.05;
      const b = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.02, 20), new THREE.MeshBasicMaterial({ color: "#f2b544" })); b.position.set(s.p1[0], y, s.p1[1]); b.layers.set(1); g.add(b);
      const c = document.createElement("canvas"); c.width = 256; c.height = 64; const x = c.getContext("2d");
      x.font = "600 40px system-ui, sans-serif"; x.fillStyle = "#f2b544"; x.textAlign = "center"; x.textBaseline = "middle"; x.shadowColor = "#000"; x.shadowBlur = 6; x.fillText(s.id, 128, 32);
      const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, transparent: true, depthTest: false })); sp.scale.set(1.6, 0.4, 1); sp.position.set(s.p1[0], y + 0.45, s.p1[1]); sp.layers.set(1); sp.renderOrder = 10; g.add(sp);
    }
  }

  vue(nom, duree = 0.8) {
    const V3 = (a) => new THREE.Vector3(...a);
    const VUES = { plateau_chien: [[6.5, 3.2, 3.5], [-0.5, 0.2, -3.5]], ras_du_sol: [[1.6, 0.5, 1.3], [-0.6, 0.3, -5]] };
    if (VUES[nom]) {
      this.suivre = false;
      const [p, c] = VUES[nom];
      if (!duree) { this.camera.position.copy(V3(p)); this.controles.target.copy(V3(c)); this.controles.update(); return; }
      this.transition = { p0: this.camera.position.clone(), p1: V3(p), c0: this.controles.target.clone(), c1: V3(c), u: 0, duree };
      return;
    }
    super.vue(nom, duree);
  }

  poserChien(c, cible = this.chien) {
    const u = cible.userData;
    cible.position.set(c.p[0], c.y, c.p[1]);
    cible.rotation.set(0, c.lacet, 0);
    u.corps.rotation.set(-c.tangageCorps, 0, c.roulisCorps);
    for (const k of PATTES) {
      const a = c.angles[k], j = u.pattes[k]; if (!a) continue;
      j.abd.rotation.z = a.abduction; j.hanche.rotation.x = -a.hanche; j.genou.rotation.x = -a.genou;
    }
    u.cou.rotation.y = c.tete.lacet; u.tete.rotation.x = -c.tete.tangage;
  }

  /* Pose du jumeau à partir de la seule télémétrie (position, lacet, posture) : pattes en posture nominale. */
  poserJumeau(tel, chienModele) {
    this.jumeau.visible = !!tel; if (!tel) return;
    this.jumeau.position.set(tel.p[0], tel.p[1], tel.p[2]); this.jumeau.rotation.set(0, THREE.MathUtils.degToRad(tel.lacet || 0), 0);
    if (chienModele) for (const k of PATTES) { const a = chienModele.angles[k], j = this.jumeau.userData.pattes[k]; j.abd.rotation.z = a.abduction; j.hanche.rotation.x = -a.hanche; j.genou.rotation.x = -a.genou; }
  }

  couleurYeux(c) { for (const o of this.chien.userData.yeux) { o.material.color.set(c); o.material.emissive.set(c); } }

  /* Caméra de tête : à l'objectif, dans l'axe du museau. */
  majCameraDrone() {
    const o = this.chien.userData.objectif, c = this.camDrone;
    this.chien.updateMatrixWorld(true);
    const pos = new THREE.Vector3(), dir = new THREE.Vector3();
    o.getWorldPosition(pos); o.getWorldDirection(dir);
    c.position.copy(pos); c.up.set(0, 1, 0);
    c.lookAt(this.viser ? new THREE.Vector3(...this.viser) : pos.clone().add(dir));
    const h = THREE.MathUtils.degToRad(this.champH) / this.zoom;
    c.fov = THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(h / 2) / c.aspect)); c.updateProjectionMatrix();
  }
}
