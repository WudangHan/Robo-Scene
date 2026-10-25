/* Robo-Scène — animation du robot virtuel.
   Chaque degré de liberté suit sa cible par un ressort amorti du second ordre dont la
   fréquence et l'amortissement dépendent des facteurs d'effort de Laban (démarche proche du
   modèle EMOTE de Chi et al.) : temps soudain → ressort rapide ; flux libre → légère
   oscillation ; poids fort → accélération accrue ; espace indirect → dérive lente du regard
   et des extrémités. Couches superposées : pose voulue + posture émotionnelle + vie
   (respiration, transfert de poids, micro-mouvements, clignements, saccades) + parole + marche. */
import { CONTACTS, CONTACTS_POSES, EMOTIONS, GESTES, POSES } from "./emotions.js";
import { REPERES_VISAGE, REPERES_CORPS } from "./humanoide.js";
import { MainVirtuelle, CAPTEURS_POINT, FORCES_TOUCHER } from "./mains.js";

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const attendre = (ms) => new Promise((r) => setTimeout(r, ms));

export class Animateur {
  constructor(humanoide, schema) {
    this.h = humanoide; this.S = schema;
    this.noms = Object.keys(schema.dofs);
    this.val = {}; this.vit = {}; this.base = {};
    for (const n of this.noms) { this.val[n] = 0; this.vit[n] = 0; this.base[n] = 0; }
    this.vitesseDof = {};                                  // facteur propre à la dernière consigne
    this.emotion = { nom: "neutre", intensite: 0 };
    this.vitesse = 1;
    this.vivant = true;
    this.au = {}; this.auTenu = {}; this.auGeste = {}; this.clignement = 0;
    this.regardMode = "public"; this.regardYeux = { yaw: 0, pitch: 0 }; this.teteRegard = { yaw: 0, pitch: 0 };
    this.saccade = { yaw: 0, pitch: 0, prochaine: 0 };
    this.prochainClignement = 1.5;
    this.racine = { x: 0, z: 0, yaw: 0 };
    this.marche = null; this.poidsMarche = 0; this.phase = 0;
    this.battement = 0; this.sourcilBattement = 0;
    this.pointe = { g: false, d: false };
    this.tabouret = false;
    this.geste = null;                                     // {jeton}
    this.jeton = 0;
    this.imitation = null;                                 // {pose:{}, au:{}, tete:{}} imposé par la caméra
    this.toucher = { g: null, d: null };                   // contact main-visage voulu : {point, local}
    this.toucherCourant = { g: null, d: null };            // contact effectivement suivi (cible lissée)
    this.poidsToucher = { g: 0, d: 0 };
    this.camera = null;                                    // fourni par la scène (cible du regard « public »)
    this.ecouteurs = new Set();
    // mains à cinq doigts (25 oct. 2026) : perception, force et mouvement des doigts (mains.js)
    this.mains = { g: new MainVirtuelle("g"), d: new MainVirtuelle("d") };
    this.accMain = { g: 0, d: 0 }; this.histMain = { g: [], d: [] };
    this.maniereToucher = { g: null, d: null };            // « touche ton cœur fermement » : manière du contact
    this.surMain = null;                                   // rappel (événement) fourni par la page : journal
  }
  /* ── cibles ─────────────────────────────────────────── */
  effort() {
    const e = EMOTIONS[this.emotion.nom] || EMOTIONS.neutre;
    const k = this.emotion.intensite / 10;
    return e.effort.map((x) => x * k);
  }
  cible(n) {
    const d = this.S.dofs[n];
    const e = EMOTIONS[this.emotion.nom] || EMOTIONS.neutre;
    const k = this.emotion.intensite / 10;
    const age = this.h.apparence.age || 40;
    let v = this.base[n] + (e.posture[n] || 0) * k;
    if (n === "tronc.flexion") v += Math.max(0, age - 55) * 0.18;           // voussure de l'âge
    if (n === "tete.flexion") v += Math.max(0, age - 60) * 0.12;
    return clamp(v, d.min, d.max);
  }
  definir(n, valeur, { relatif = false, vitesse = null } = {}) {
    if (!(n in this.base)) return;
    const d = this.S.dofs[n];
    this.base[n] = clamp(relatif ? this.base[n] + valeur : valeur, d.min, d.max);
    if (vitesse) this.vitesseDof[n] = vitesse; else delete this.vitesseDof[n];
  }
  instantane() { return { ...this.base }; }
  restaurer(p) { this.toucher = { g: null, d: null }; for (const n of this.noms) this.base[n] = p[n] ?? 0; this.tabouret = (this.base["bassin.abaissement"] > 35 && this.base["genou_g.flexion"] > 60 && this.base["hanche_g.flexion"] > 60 && this.base["genou_g.flexion"] < 110); }
  /* ── émotions et visage ─────────────────────────────── */
  definirEmotion(nom, intensite, relatif = false) {
    if (!EMOTIONS[nom]) return;
    const i = relatif && nom === this.emotion.nom ? this.emotion.intensite + intensite : (relatif ? 5 + intensite : intensite);
    this.emotion = { nom, intensite: clamp(i, 0, 10) };
    if (EMOTIONS[nom].regard && this.regardMode !== "libre") this.regardEmotion = EMOTIONS[nom].regard; else this.regardEmotion = null;
    this.emettre();
  }
  definirVisage(au, tenir = true) {
    // les expressions se cumulent (« souris et lève les sourcils ») ; un visage vide efface tout
    this.auTenu = tenir && Object.keys(au).length ? { ...this.auTenu, ...au } : {};
    this.emettre();
  }
  cibleAU() {
    const e = EMOTIONS[this.emotion.nom] || EMOTIONS.neutre;
    const k = this.emotion.intensite / 10;
    const c = {};
    for (const [a, v] of Object.entries(e.au)) c[a] = v * k;
    for (const [a, v] of Object.entries(this.auTenu)) c[a] = Math.max(c[a] || 0, v);
    for (const [a, v] of Object.entries(this.auGeste)) c[a] = v;
    if (this.sourcilBattement > 0.01) { c.au1 = Math.max(c.au1 || 0, this.sourcilBattement * 0.5); c.au2 = Math.max(c.au2 || 0, this.sourcilBattement * 0.6); }
    if (this.imitation?.au) for (const [a, v] of Object.entries(this.imitation.au)) c[a] = v;
    return c;
  }
  /* ── contacts main-visage ───────────────────────────── */
  /* spec : {X|g|d : [point de la main, repère du visage, décalage]} ; « X » = côté du geste (le repère et le
     décalage sont écrits pour la main droite et reflétés pour la gauche) ; null efface les contacts. */
  definirContacts(spec, cote = "d") {
    this.toucher = { g: null, d: null };
    if (!spec) return;
    for (const [k, [point, rep, dec = [0, 0, 0]]] of Object.entries(spec)) {
      const s = k === "X" ? cote : k;
      const miroir = k === "X" && cote === "g";
      const nom = miroir ? rep.replace(/_d$/, "_g") : rep;
      const r = REPERES_VISAGE[nom] || REPERES_CORPS[nom];
      if (!r) continue;
      this.toucher[s] = { point, groupe: REPERES_CORPS[nom] ? "poitrine" : "visage", local: [r[0] + (miroir ? -dec[0] : dec[0]), r[1] + dec[1], r[2] + dec[2]] };
    }
  }
  majContacts(dt) {
    const out = [];
    const k = 1 - Math.exp(-dt / 0.12);
    for (const s of ["g", "d"]) {
      const t = this.toucher[s];
      this.poidsToucher[s] = clamp(this.poidsToucher[s] + (t ? dt / 0.35 : -dt / 0.3), 0, 1);
      if (t) {
        const c = this.toucherCourant[s];
        if (!c || c.point !== t.point || c.groupe !== t.groupe || this.poidsToucher[s] < 0.02) this.toucherCourant[s] = { point: t.point, groupe: t.groupe, local: t.local.slice() };
        else c.local = c.local.map((v, i) => v + (t.local[i] - v) * k);
      }
      const c = this.toucherCourant[s];
      if (c && this.poidsToucher[s] > 0.01) out.push({ s, point: c.point, groupe: c.groupe, local: c.local, poids: this.poidsToucher[s] });
      else if (!t) this.toucherCourant[s] = null;
    }
    return this.imitation?.pose ? [] : out;
  }
  /* ── gestes et poses ────────────────────────────────── */
  arreter() {
    this.toucher = { g: null, d: null };
    this.jeton++; this.geste = null; this.marche = null; this.auGeste = {};
    for (const n of this.noms) this.vit[n] = 0;
  }
  /* tenir : le geste garde sa dernière position au lieu de revenir à la position d'avant (boutons en bascule :
     le second appui sur le même bouton ramène le robot, voir app.js, basculer). */
  async jouerGeste(nom, { cote = "d", repetitions = 1, intensite = 1, direction = "devant", vitesse = null, tenir = false } = {}) {
    const fabrique = GESTES[nom];
    if (!fabrique) return false;
    const j = ++this.jeton;
    const images = fabrique(Math.max(1, repetitions), direction);
    const autre = cote === "g" ? "d" : "g";
    const touches = new Set();
    const avant = this.instantane();
    const pointeAvant = { ...this.pointe };
    const v = (vitesse || 1) * this.vitesse;
    const t0 = performance.now();
    this.geste = { nom, j };
    const contacts = CONTACTS[nom] || {};
    for (const [i, im] of images.entries()) {
      const att = t0 + (im.t * 1000) / v - performance.now();
      if (att > 0) await attendre(att);
      if (j !== this.jeton) return false;
      if (im.fin) {
        if (tenir) continue;                       // position tenue jusqu'au second appui
        this.definirContacts(null);                // la main quitte le visage avec le retour
        if (im.regard) this.regardMode = im.regard;
        for (const n of touches) this.base[n] = avant[n];
        this.pointe = pointeAvant; this.auGeste = im.au ? { ...im.au } : {};
        if (im.au) setTimeout(() => { if (j === this.jeton) this.auGeste = {}; }, 500 / v);
        continue;
      }
      for (const [cle, val] of Object.entries(im.p || {})) {
        const n = cle.replace("_X", `_${cote}`).replace("_Y", `_${autre}`);
        if (n.startsWith("pointe_")) { this.pointe[n.slice(-1)] = !!val; continue; }
        if (!(n in this.base)) continue;
        touches.add(n);
        const d = this.S.dofs[n];
        const ancre = avant[n] || 0;
        this.base[n] = clamp(ancre + (val - ancre) * intensite, d.min, d.max);
        this.vitesseDof[n] = 1.4 * v;
      }
      if (i in contacts) this.definirContacts(contacts[i], cote);
      if (im.au) this.auGeste = { ...this.auGeste, ...im.au };
      if (im.regard) this.regardMode = im.regard;
    }
    await attendre(450 / v);
    if (j === this.jeton) { this.geste = null; for (const n of touches) delete this.vitesseDof[n]; }
    this.emettre();
    return true;
  }
  prendrePose(nom, vitesse = null) {
    const p = POSES[nom];
    if (!p) return;
    this.arreter();
    for (const n of this.noms) {
      if (nom === "debout" && !/^(hanche|genou|cheville|bassin|tronc)/.test(n)) continue;   // « debout » ne touche pas les bras
      this.base[n] = p[n] ?? 0;
      this.vitesseDof[n] = vitesse || 0.8;
    }
    this.tabouret = nom === "assis" || nom === "penseur";
    this.definirContacts(CONTACTS_POSES[nom] || null);
    if (nom === "repos") { this.auTenu = {}; this.pointe = { g: false, d: false }; }
    this.emettre();
  }
  /* ── déplacements ───────────────────────────────────── */
  async deplacer({ x = null, z = null, avant = null, lateral = null, course = false, vitesse = null }) {
    const P = this.S.plateau;
    let tx = this.racine.x, tz = this.racine.z;
    const fy = this.racine.yaw;
    if (x !== null) tx = x;
    if (z !== null) tz = z;
    if (avant !== null) { tx += Math.sin(fy) * avant; tz += Math.cos(fy) * avant; }
    if (lateral !== null) { tx += Math.cos(fy) * lateral; tz -= Math.sin(fy) * lateral; }
    tx = clamp(tx, P.x[0], P.x[1]); tz = clamp(tz, P.z[0], P.z[1]);
    const dx = tx - this.racine.x, dz = tz - this.racine.z, dist = Math.hypot(dx, dz);
    if (dist < 0.03) return true;
    if (this.tabouret || this.base["bassin.abaissement"] > 10) {           // se lever avant de marcher
      this.prendrePose("debout"); await attendre(900 / this.vitesse);
    }
    const j = ++this.jeton;
    const cap = Math.atan2(dx, dz);
    const recul = avant !== null && avant < 0 && x === null && z === null;
    const deCote = lateral !== null && x === null && z === null;
    const yawInitial = fy;
    if (!recul && !deCote) await this.orienter(cap, false, j);
    if (j !== this.jeton) return false;
    this.marche = { tx, tz, recul, deCote, vitesse: (course ? 2.0 : 1.0) * (vitesse || 1) * this.vitesse, j };
    while (this.marche && this.marche.j === j) await attendre(50);
    if (j !== this.jeton) return false;
    if (!recul && !deCote && Math.abs(yawInitial) < 0.2) await this.orienter(0, false, j);     // revient face au public
    return true;
  }
  async orienter(angle, relatif = false, jeton = null) {
    const j = jeton ?? ++this.jeton;
    const cible = relatif ? this.racine.yaw + angle : angle;
    let ecart = Math.atan2(Math.sin(cible - this.racine.yaw), Math.cos(cible - this.racine.yaw));
    if (relatif && Math.abs(angle) >= Math.PI - 0.01) ecart = angle;                   // demi-tour, tour complet : sens demandé
    const fin = this.racine.yaw + ecart;
    const duree = 250 + Math.abs(ecart) / Math.PI * 900 / this.vitesse;
    const debut = this.racine.yaw, t0 = performance.now();
    this.pietinement = true;
    while (performance.now() - t0 < duree) {
      if (j !== this.jeton) { this.pietinement = false; return false; }
      const u = (performance.now() - t0) / duree;
      this.racine.yaw = debut + ecart * (u * u * (3 - 2 * u));
      await attendre(16);
    }
    this.racine.yaw = fin; this.pietinement = false;
    return true;
  }
  /* ── boucle ─────────────────────────────────────────── */
  maj(dt, t, bouche) {
    dt = Math.min(dt, 0.1);       // ordinateurs lents : temps réel jusqu'à 10 images/s (pas d'intégration adaptatif)
    const [poids, temps, espace, flux] = this.effort();
    const f0 = 1.15 * Math.pow(2, 1.1 * temps) * (1 + 0.15 * Math.max(0, poids)) * this.vitesse;
    const zeta = clamp(0.8 + 0.22 * flux - 0.1 * Math.max(0, -poids), 0.5, 1.05);
    const imit = this.imitation?.pose;
    for (const n of this.noms) {
      const d = this.S.dofs[n];
      const c = imit && n in imit ? imit[n] : this.cible(n);
      // fréquence plafonnée (8 Hz) et pas d'intégration adapté : le ressort reste stable à toute vitesse
      const f = Math.min(8, imit && n in imit ? 4 : f0 * (this.vitesseDof[n] || 1));
      const w = 2 * Math.PI * f;
      const pas = Math.max(1, Math.ceil(dt / (1 / 120)), Math.ceil((w * dt) / 0.25));
      const h = dt / pas;
      let x = this.val[n], v = this.vit[n];
      if (!Number.isFinite(x) || !Number.isFinite(v)) { x = c; v = 0; }
      for (let i = 0; i < pas; i++) {
        const a = w * w * (c - x) - 2 * zeta * w * v; v += a * h; x += v * h;
        // butées articulaires : un léger dépassement (flux libre) est permis, jamais au-delà
        const marge = 0.08 * (d.max - d.min);
        if (x > d.max + marge) { x = d.max + marge; v = Math.min(v, 0); }
        else if (x < d.min - marge) { x = d.min - marge; v = Math.max(v, 0); }
      }
      this.val[n] = x; this.vit[n] = v;
    }
    // couches additionnelles (n'entrent pas dans les ressorts)
    const P = { ...this.val };
    const extra = { pointe: this.pointe, tabouret: this.tabouret };
    if (this.vivant) {
      const souffle = Math.sin(2 * Math.PI * 0.24 * t);
      P["tronc.flexion"] -= 0.7 * souffle;
      P["epaule_g.haussement"] += 0.9 * (souffle + 1) / 2; P["epaule_d.haussement"] += 0.9 * (souffle + 1) / 2;
      const transfert = Math.sin(2 * Math.PI * 0.055 * t);
      if (!this.tabouret && this.val["bassin.abaissement"] < 10) {
        extra.bassinX = 0.009 * transfert;
        P["hanche_g.abduction"] += 1.2 * transfert; P["hanche_d.abduction"] -= 1.2 * transfert;
        P["tronc.inclinaison"] -= 0.9 * transfert;
      }
      const derive = 1 + 1.6 * Math.max(0, -espace);
      P["tete.rotation"] += derive * (1.3 * Math.sin(0.31 * t) + 0.6 * Math.sin(0.83 * t + 1));
      P["tete.flexion"] += derive * 0.8 * Math.sin(0.43 * t + 2);
      P["tete.inclinaison"] += derive * 0.7 * Math.sin(0.27 * t + 4);
      P["poignet_g.flexion"] += derive * 1.5 * Math.sin(0.5 * t); P["poignet_d.flexion"] += derive * 1.5 * Math.sin(0.47 * t + 1);
    }
    // battements de parole (tête) : impulsion amortie
    this.battement *= Math.exp(-dt / 0.18); this.sourcilBattement *= Math.exp(-dt / 0.22);
    P["tete.flexion"] += 4.5 * this.battement * (1 + 0.5 * Math.max(0, poids));
    // marche
    this.majMarche(dt, P, extra);
    // regard
    this.majRegard(dt, t, P, espace);
    // contact main-visage : la main suit la tête où qu'elle aille (passe géométrique dans humanoide.js)
    extra.contacts = this.majContacts(dt);
    // mains : la fermeture des gestes guide les doigts libres ; une main commandée (posture, prise, toucher)
    // impose sa fermeture au degré de liberté « main_x.fermeture » (jumeau à pince du TonyPi Pro)
    extra.mains = {};
    for (const s of ["g", "d"]) {
      const m = this.mains[s];
      m.suivreFermeture(clamp((P[`main_${s}.fermeture`] || 0) / 100, 0, 1), !!this.pointe[s]);
      // toucher du corps propre (visage, cœur…) : les capteurs du point de contact sentent la pression
      const tc = this.toucherCourant[s];
      if (tc && this.poidsToucher[s] > 0.01 && !m.prise && (!m.toucher || m.toucher.auto))
        m.toucher = { auto: true, capteurs: CAPTEURS_POINT[tc.point] || [], force: FORCES_TOUCHER[this.maniereToucher[s]] ?? FORCES_TOUCHER.delicat, poids: this.poidsToucher[s] };
      else if (m.toucher?.auto && !(tc && this.poidsToucher[s] > 0.01)) m.toucher = null;
      const ev = m.pas(dt, { acceleration: this.accMain[s] });
      if (m.prise?.chute) m.lacher("échappé");
      // (le jumeau physique lit les valeurs des ressorts : on y reporte la fermeture des doigts commandés)
      if (!m.libre) { const f = m.fermeture(); P[`main_${s}.fermeture`] = f; this.val[`main_${s}.fermeture`] = f; this.vit[`main_${s}.fermeture`] = 0; }
      for (const e of ev) this.surMain?.(e);
      extra.mains[s] = m;
    }
    this.h.appliquer(P, extra);
    this.h.racine.position.set(this.racine.x, 0, this.racine.z);
    this.h.racine.rotation.y = this.racine.yaw;
    // accélération verticale de chaque main (différence seconde lissée) : la charge à tenir en dépend
    this.h.racine.updateMatrixWorld(true);
    for (const s of ["g", "d"]) {
      const H = this.histMain[s]; H.push(this.h.pointMain(s, "paume").y); if (H.length > 3) H.shift();
      if (H.length === 3 && dt > 0) {
        const a = clamp((H[2] - 2 * H[1] + H[0]) / (dt * dt), -60, 60);
        this.accMain[s] += (a - this.accMain[s]) * (1 - Math.exp(-dt / 0.05));
      }
    }
    this.h.majChutes(dt);
    // visage
    this.majClignement(dt, t);
    const cAU = this.cibleAU();
    const k = 1 - Math.exp(-dt / (0.11 / Math.max(0.5, Math.pow(2, temps))));
    const tous = new Set([...Object.keys(cAU), ...Object.keys(this.au)]);
    for (const a of tous) { this.au[a] = (this.au[a] || 0) + ((cAU[a] || 0) - (this.au[a] || 0)) * k; if (Math.abs(this.au[a]) < 0.002 && !cAU[a]) delete this.au[a]; }
    this.h.visage.maj({ ...this.au, clignement: this.clignement }, this.regardYeux, bouche);
    this.dernierePose = P;
  }
  majMarche(dt, P, extra) {
    const M = this.marche;
    const actif = !!M || this.pietinement;
    this.poidsMarche = clamp(this.poidsMarche + (actif ? dt / 0.25 : -dt / 0.3), 0, 1);
    if (M) {
      const dx = M.tx - this.racine.x, dz = M.tz - this.racine.z, d = Math.hypot(dx, dz);
      const v = 0.95 * M.vitesse * (this.h.apparence.taille / 178) * Math.min(1, this.poidsMarche + 0.2);
      if (d < 0.025) { this.racine.x = M.tx; this.racine.z = M.tz; this.marche = null; }
      else { const s = Math.min(d, v * dt); this.racine.x += dx / d * s; this.racine.z += dz / d * s; }
      this.phase += dt * 2 * Math.PI * 0.85 * M.vitesse * (M.recul ? -1 : 1);
    } else if (this.pietinement) this.phase += dt * 2 * Math.PI * 0.9;
    const w = this.poidsMarche;
    extra.marche = w;                  // l'ancrage plantaire laisse alors le déroulé talon-pointe libre
    if (w < 0.001) return;
    const amp = this.pietinement && !M ? 0.45 : (M?.deCote ? 0.4 : 1);
    const s = Math.sin(this.phase), c = Math.cos(this.phase);
    P["hanche_g.flexion"] += w * amp * 24 * s; P["hanche_d.flexion"] -= w * amp * 24 * s;
    P["genou_g.flexion"] += w * amp * (6 + 48 * Math.max(0, c) ** 2); P["genou_d.flexion"] += w * amp * (6 + 48 * Math.max(0, -c) ** 2);
    P["cheville_g.flexion"] += w * amp * 10 * Math.max(0, -s); P["cheville_d.flexion"] += w * amp * 10 * Math.max(0, s);
    if (M?.deCote) { P["hanche_g.abduction"] += w * 10 * Math.max(0, s); P["hanche_d.abduction"] += w * 10 * Math.max(0, -s); }
    P["epaule_g.flexion"] -= w * amp * 16 * s; P["epaule_d.flexion"] += w * amp * 16 * s;
    P["coude_g.flexion"] += w * 14; P["coude_d.flexion"] += w * 14;
    P["tronc.rotation"] += w * amp * 4 * s;
    extra.bassinY = -w * amp * 0.014 * (1 - Math.abs(s));
    extra.bassinRot = -w * amp * 5 * s;
  }
  majRegard(dt, t, P, espace) {
    const mode = this.imitation?.regard ? null : (this.regardEmotion && this.regardMode === "public" ? this.regardEmotion : this.regardMode);
    let yaw = 0, pitch = 0, teteYaw = 0, tetePitch = 0;
    if (this.imitation?.regard) { yaw = this.imitation.regard.yaw; pitch = this.imitation.regard.pitch; }
    else if (mode === "public" && this.camera) {
      // cible : la caméra (le spectateur), exprimée dans le repère de la tête
      const loc = this.h.os.tete.worldToLocal(this.camera.position.clone());
      const yy = Math.atan2(loc.x, loc.z), pp = Math.atan2(loc.y - 0.1, Math.hypot(loc.x, loc.z));
      if (Math.abs(yy) < 1.9) { yaw = yy; pitch = pp; }
      teteYaw = clamp(yaw * 0.35, -0.5, 0.5) * 57.3; tetePitch = clamp(-pitch * 0.25, -0.3, 0.3) * 57.3;
    } else if (mode === "gauche") { yaw = 0.42; teteYaw = 28; }
    else if (mode === "droite") { yaw = -0.42; teteYaw = -28; }
    else if (mode === "haut") { pitch = 0.32; tetePitch = -18; }
    else if (mode === "bas") { pitch = -0.38; tetePitch = 16; }
    else if (mode === "loin") { pitch = 0.04; yaw = 0.1 * Math.sin(t * 0.1); }
    else if (mode === "libre") { yaw = 0.4 * Math.sin(t * 0.37) * Math.sin(t * 0.11); pitch = 0.12 * Math.sin(t * 0.23); teteYaw = yaw * 40; }
    // saccades (petits sauts du regard), plus amples si l'espace est indirect
    if (t > this.saccade.prochaine) {
      const a = 0.03 + 0.05 * Math.max(0, -espace);
      this.saccade = { yaw: (Math.random() - 0.5) * 2 * a, pitch: (Math.random() - 0.5) * a, prochaine: t + 0.6 + Math.random() * 1.8 };
    }
    yaw = clamp(yaw - teteYaw / 57.3 + this.saccade.yaw, -0.55, 0.55);
    pitch = clamp(pitch + this.saccade.pitch, -0.42, 0.38);
    const k = 1 - Math.exp(-dt / 0.05), kt = 1 - Math.exp(-dt / 0.35);
    this.regardYeux.yaw += (yaw - this.regardYeux.yaw) * k; this.regardYeux.pitch += (pitch - this.regardYeux.pitch) * k;
    this.teteRegard.yaw += (teteYaw - this.teteRegard.yaw) * kt; this.teteRegard.pitch += (tetePitch - this.teteRegard.pitch) * kt;
    if (!this.imitation?.pose || !("tete.rotation" in this.imitation.pose)) { P["tete.rotation"] += this.teteRegard.yaw; P["tete.flexion"] += this.teteRegard.pitch; }
  }
  majClignement(dt, t) {
    // ≈ 17 clignements par minute au repos (Bentivoglio et al.) ; durée ≈ 150 ms
    if (this.cligne) {
      this.cligne.u += dt / 0.15;
      this.clignement = this.cligne.u < 0.45 ? this.cligne.u / 0.45 : Math.max(0, 1 - (this.cligne.u - 0.45) / 0.55);
      if (this.cligne.u >= 1) { this.cligne = null; this.clignement = 0; }
    } else if (t > this.prochainClignement && !this.imitation?.au) {
      this.cligne = { u: 0 };
      const moyenne = 60 / 17;
      this.prochainClignement = t + Math.max(0.6, -Math.log(1 - Math.random()) * moyenne);
    }
  }
  /* ── divers ─────────────────────────────────────────── */
  battre(force = 1) { this.battement = Math.min(1.2, this.battement + 0.6 * force); this.sourcilBattement = Math.min(1, this.sourcilBattement + 0.5 * force); }
  surChangement(f) { this.ecouteurs.add(f); return () => this.ecouteurs.delete(f); }
  emettre() { for (const f of this.ecouteurs) try { f(this); } catch (e) { console.error(e); } }
}
