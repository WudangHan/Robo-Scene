/* Robo-Scène — modèle du chien de scène virtuel (quadrupède à 12 degrés de liberté).
   Module pur (aucune dépendance au DOM ni à three.js) : testé sous Node, partagé par la page et par la conduite.

   Corps : quatre pattes (AVG, AVD, ARG, ARD : avant/arrière, gauche/droite), chacune avec abduction de hanche,
   flexion de hanche et genou ; segments de 0,21 m ; hauteur debout de 0,30 m ; gabarit voisin d'un quadrupède
   de 15 kg (70 × 31 × 40 cm debout). Locomotion : trot (paires diagonales en opposition de phase), pas posés au
   sol pendant l'appui, arc de levée pendant le transfert, cinématique inverse à deux segments plus abduction.
   Postures : debout, couché, assis, donner la patte, saluer, s'étirer (révérence). Allures expressives (joyeux,
   craintif, menaçant, fatigué, curieux) : paramètres de hauteur, de cadence, de levée, de vitesse et de port de
   tête, choisis par conception — (Inférence) non validés par des juges, à éprouver comme les variations O-02.

   Sécurités reproduites : sol praticable (bridge/chien/sol.py, même règle), freinage devant les bords, plafonds
   de vitesse par surface (escaliers lents ; salle plus lente en représentation), batterie (retour à la marque,
   puis couché), perte de liaison (arrêt, puis couché), ARRÊT (arrêt freiné puis couché, verrouillé jusqu'au
   réarmement), coupure des moteurs confirmée (le robot s'affaisse).

   Repère du théâtre : x vers cour, z vers la salle ; lacet ψ : 0 = museau vers la salle, croissant dans le sens
   antihoraire vu de dessus ; avant = (sin ψ, cos ψ), gauche = (cos ψ, −sin ψ) dans le plan (x, z). */
import { hauteurSol, surfaceDe, verifierSol, vitesseMax } from "./sol.js";

export const L1 = 0.21, L2 = 0.21;
export const HANCHES = { AVG: [0.19, 0.09], AVD: [0.19, -0.09], ARG: [-0.19, 0.09], ARD: [-0.19, -0.09] };   // [avant, gauche]
const PHASES = { AVG: 0, ARD: 0, AVD: 0.5, ARG: 0.5 };   // trot : paires diagonales
export const PATTES = Object.keys(HANCHES);
export const deg = (r) => (r * 180) / Math.PI;
export const rad = (d) => (d * Math.PI) / 180;
const ecartAngle = (a, b) => Math.atan2(Math.sin(b - a), Math.cos(b - a));
const lerp = (a, b, t) => a + (b - a) * t;

export const ALLURES = {
  neutre: { libelle: "Neutre", hauteur: 0.30, cadence: 1.0, levee: 0.07, vitesse: 1.0, tete: -5, roulis: 0, rebond: 0.005, balayage: 0 },
  joyeux: { libelle: "Joyeux", hauteur: 0.31, cadence: 1.25, levee: 0.09, vitesse: 1.0, tete: 10, roulis: 0.03, rebond: 0.015, balayage: 0 },
  craintif: { libelle: "Craintif", hauteur: 0.21, cadence: 0.85, levee: 0.04, vitesse: 0.6, tete: -25, roulis: 0, rebond: 0.002, balayage: 0 },
  menacant: { libelle: "Menaçant", hauteur: 0.25, cadence: 0.8, levee: 0.05, vitesse: 0.7, tete: -15, roulis: 0, rebond: 0, balayage: 0 },
  fatigue: { libelle: "Fatigué", hauteur: 0.26, cadence: 0.7, levee: 0.04, vitesse: 0.5, tete: -20, roulis: 0.02, rebond: 0.003, balayage: 0 },
  curieux: { libelle: "Curieux", hauteur: 0.30, cadence: 1.0, levee: 0.07, vitesse: 0.8, tete: 5, roulis: 0, rebond: 0.006, balayage: 15 },
};

/* Postures : pieds [avant, haut] relatifs à chaque hanche, en mètres (haut négatif = sous la hanche). */
export const POSTURES = {
  debout: { libelle: "Debout", pieds: (h) => ({ AVG: [0, -h], AVD: [0, -h], ARG: [0, -h], ARD: [0, -h] }) },
  couche: { libelle: "Couché", pieds: () => ({ AVG: [0.08, -0.1], AVD: [0.08, -0.1], ARG: [-0.04, -0.1], ARD: [-0.04, -0.1] }) },
  assis: { libelle: "Assis", pieds: () => ({ AVG: [0.03, -0.32], AVD: [0.03, -0.32], ARG: [0.12, -0.11], ARD: [0.12, -0.11] }) },
  patte: { libelle: "Donner la patte", pieds: () => ({ AVG: [0.03, -0.32], AVD: [0.17, -0.17], ARG: [0.12, -0.11], ARD: [0.12, -0.11] }) },
  salut: { libelle: "Saluer", pieds: (h, t) => ({ AVG: [0.03, -0.32], AVD: [0.16, -0.12 + 0.05 * Math.sin(t * 9)], ARG: [0.12, -0.11], ARD: [0.12, -0.11] }) },
  etirement: { libelle: "S'étirer (révérence)", pieds: () => ({ AVG: [0.14, -0.13], AVD: [0.14, -0.13], ARG: [-0.02, -0.33], ARD: [-0.02, -0.33] }) },
};

/* Cinématique inverse d'une patte : pied [avant, gauche, haut] relatif à la hanche → angles (radians).
   abduction (autour de l'axe avant), hanche (cuisse, depuis la verticale, positive vers l'avant), genou (jambe
   relativement à la cuisse, positif vers l'avant : genou « en arrière », comme les quadrupèdes électriques). */
export function ik([a, l, h]) {
  const ab = Math.atan2(l, -h);
  const hs = Math.hypot(l, h);
  let D = Math.hypot(a, hs);
  const Dmax = L1 + L2 - 1e-4, atteint = D <= Dmax;
  D = Math.min(Math.max(D, 0.05), Dmax);
  const phiPied = Math.atan2(a, hs);
  const alpha = Math.acos(Math.max(-1, Math.min(1, (L1 * L1 + D * D - L2 * L2) / (2 * L1 * D))));
  const cosK = Math.max(-1, Math.min(1, (L1 * L1 + L2 * L2 - D * D) / (2 * L1 * L2)));
  return { abduction: ab, hanche: phiPied - alpha, genou: Math.PI - Math.acos(cosK), atteint };
}

/* Cinématique directe (vérification) : angles → position du pied relative à la hanche [avant, gauche, haut]. */
export function fk({ abduction, hanche, genou }) {
  const ka = L1 * Math.sin(hanche), kh = -L1 * Math.cos(hanche);
  const fa = ka + L2 * Math.sin(hanche + genou), fhs = kh - L2 * Math.cos(hanche + genou);
  return [fa, -fhs * Math.sin(abduction), fhs * Math.cos(abduction)];
}

export const ETATS = { couche: "Couché", debout: "Debout", posture: "Posture", urgence: "Arrêt d'urgence", affaisse: "Moteurs coupés — affaissé" };

export class ChienVirtuel {
  constructor(salle, opts = {}) {
    this.salle = salle;
    this.R = salle.sol.regles;
    this.mode = opts.mode || "plateau";
    this.interpretes = [];
    const a = salle.sol.aire;
    this.p = [a.centre[0], a.centre[1]];
    this.lacet = rad(a.lacet ?? 0); this.lacetCible = this.lacet;
    this.v = [0, 0];                       // vitesse dans le plan (x, z) du théâtre
    this.wz = 0;
    this.etat = "couche";
    this.posture = "couche";
    this.postureDe = null; this.postureT = 1;   // transition de posture (0 → 1)
    this.allure = "neutre";
    this.tete = { lacet: 0, tangage: 0 }; this.regard = null;
    this.batterie = 100;
    this.verrouUrgence = false;
    this.consigne = { type: "aucune" };
    this.phase = 0; this.amplitude = 0;
    this.liaison = { exigee: false, dernier: 0, etape: 0 };
    this.t = 0; this.alertes = new Set();
    this.retourEnCours = false;
    this.surEvenement = opts.surEvenement || (() => {});
    this.pieds = POSTURES.couche.pieds(0.1);
    this.angles = {}; this.y = 0; this.tangageCorps = 0; this.roulisCorps = 0;
    this.calculerPose(0);
  }

  get ctx() { return { mode: this.mode, interpretes: this.interpretes }; }
  get A() { return ALLURES[this.allure] || ALLURES.neutre; }
  get debout() { return this.etat === "debout"; }
  get enMouvement() { return Math.hypot(this.v[0], this.v[1]) > 0.02 || Math.abs(this.wz) > 0.05; }

  evenement(niveau, msg, cle) {
    if (cle) { if (this.alertes.has(cle)) return; this.alertes.add(cle); }
    this.surEvenement({ niveau, msg, t: this.t });
  }
  refuser(msg) { this.evenement("refus", msg); return { ok: false, motif: msg }; }

  /* ── Commandes ─────────────────────────────────────────── */
  changerPosture(nom) {
    if (!POSTURES[nom]) return this.refuser(`Posture inconnue : ${nom}`);
    this.postureDe = { ...this.pieds }; this.postureT = 0; this.posture = nom;
    return { ok: true };
  }

  lever() {
    if (this.verrouUrgence) return this.refuser("Arrêt d'urgence actif : réarmer d'abord");
    if (this.etat === "affaisse") return this.refuser("Moteurs coupés : réarmer, puis relever le robot");
    if (this.batterie <= this.R.batterie_critique_pct) return this.refuser("Batterie trop faible pour se lever");
    this.etat = "debout"; this.consigne = { type: "aucune" };
    this.changerPosture("debout");
    this.evenement("info", "Debout");
    return { ok: true };
  }

  coucher(motif = "") {
    if (this.etat === "affaisse") return { ok: true };
    this.v = [0, 0]; this.wz = 0; this.consigne = { type: "aucune" }; this.retourEnCours = false;
    if (this.etat !== "urgence") this.etat = "couche";
    this.changerPosture("couche");
    this.evenement(motif ? "avert" : "info", `Couché${motif ? ` (${motif})` : ""}`);
    return { ok: true };
  }

  prendrePosture(nom) {
    if (!POSTURES[nom]) return this.refuser(`Posture inconnue : ${nom}`);
    if (nom === "couche") return this.coucher();
    if (nom === "debout") return this.lever();
    if (this.verrouUrgence) return this.refuser("Arrêt d'urgence actif : réarmer d'abord");
    if (this.etat === "couche" || this.etat === "affaisse") return this.refuser("Le robot doit d'abord se lever");
    this.v = [0, 0]; this.wz = 0; this.consigne = { type: "aucune" };
    this.etat = "posture"; this.changerPosture(nom);
    this.evenement("info", POSTURES[nom].libelle);
    return { ok: true };
  }

  choisirAllure(nom) {
    if (!ALLURES[nom]) return this.refuser(`Allure inconnue : ${nom}`);
    this.allure = nom; this.evenement("info", `Allure : ${ALLURES[nom].libelle}`);
    return { ok: true };
  }

  regarder(cible) { this.regard = cible ? cible.slice() : null; return { ok: true }; }

  exigerDebout() {
    if (this.verrouUrgence) return this.refuser("Arrêt d'urgence actif : réarmer d'abord");
    if (this.etat === "posture") { this.etat = "debout"; this.changerPosture("debout"); }
    if (this.etat !== "debout") return this.refuser("Le robot doit être debout pour marcher");
    return null;
  }

  /* Marche manuelle : manche [droite, avant] ∈ [−1, 1] et rotation ∈ [−1, 1] (positive vers la droite, sens horaire). */
  marcher(manche, rotation = 0) {
    const [d, a] = manche.map((x) => Math.max(-1, Math.min(1, x || 0)));
    const actif = Math.abs(d) + Math.abs(a) + Math.abs(rotation) > 0.02;
    if (!actif) { if (this.consigne.type === "manuelle") this.consigne = { type: "aucune" }; return { ok: true }; }
    const e = this.exigerDebout(); if (e) return e;
    const ps = this.lacet, f = [Math.sin(ps), Math.cos(ps)], dr = [-Math.cos(ps), Math.sin(ps)];
    const vmax = vitesseMax(this.salle, this.p[0], this.p[1], this.mode) * this.A.vitesse;
    this.retourEnCours = false;
    this.consigne = { type: "manuelle", v: [(f[0] * a + dr[0] * d) * vmax, (f[1] * a + dr[1] * d) * vmax], wz: -rotation * rad(this.R.vitesse_lacet_max_deg_s) };
    return { ok: true };
  }

  /* Aller à un point du sol, en ligne droite, à secousse minimale ; le robot s'oriente dans le sens de la marche. */
  allerA(cible, o = {}) {
    const e = this.exigerDebout(); if (e) return e;
    const v = verifierSol(this.salle, cible, this.ctx);
    if (!v.ok) return this.refuser(`Destination refusée : ${v.motif}`);
    const T = dureeMarche(this.salle, this.p, cible, this.mode, o.duree, this.A.vitesse);
    const dx = cible[0] - this.p[0], dz = cible[1] - this.p[1];
    this.consigne = { type: "trajectoire", p0: this.p.slice(), p1: cible.slice(), T: T.T, t: 0,
      cap: Math.hypot(dx, dz) > 0.3 ? Math.atan2(dx, dz) : null, lacetFinal: o.lacet ?? null };
    if (T.ralenti) this.evenement("avert", `Marche ralentie : ${o.duree?.toFixed?.(1) ?? "?"} → ${T.T.toFixed(1)} s (plafonds de vitesse du sol)`);
    return { ok: true, duree: T.T };
  }

  tourner(lacet) {
    const e = this.exigerDebout(); if (e) return e;
    this.consigne = { type: "aucune" }; this.lacetCible = lacet;
    return { ok: true };
  }

  arreter() { this.consigne = { type: "aucune" }; this.retourEnCours = false; return { ok: true }; }

  retour(motif = "") {
    const a = this.salle.sol.aire.centre;
    const r = this.allerA(a, { lacet: rad(this.salle.sol.aire.lacet ?? 0) });
    if (r.ok) { this.retourEnCours = true; this.evenement("avert", `Retour à la marque de départ${motif ? ` (${motif})` : ""}`); }
    return r;
  }

  arretUrgence(motif = "bouton ARRÊT") {
    this.verrouUrgence = true; this.retourEnCours = false;
    this.consigne = { type: "freinage" };
    if (this.etat !== "affaisse") this.etat = "urgence";
    this.evenement("alerte", `ARRÊT D'URGENCE — ${motif} : arrêt freiné, puis couché`);
    return { ok: true };
  }

  couperMoteurs(confirmation) {
    if (confirmation !== "COUPER") return this.refuser("Coupure des moteurs : confirmation « COUPER » requise");
    this.verrouUrgence = true; this.etat = "affaisse"; this.consigne = { type: "aucune" }; this.v = [0, 0]; this.wz = 0;
    this.evenement("alerte", "COUPURE DES MOTEURS — le robot s'affaisse");
    return { ok: true };
  }

  rearmer() {
    if (this.enMouvement) return this.refuser("Réarmement possible seulement à l'arrêt");
    this.verrouUrgence = false; this.alertes.clear();
    if (this.etat === "urgence" || this.etat === "affaisse") { this.etat = "couche"; this.changerPosture("couche"); }
    this.evenement("info", "Système du chien réarmé");
    return { ok: true };
  }

  signalLiaison(t = this.t) { if (this.liaison.etape) this.evenement("info", "Liaison rétablie"); this.liaison.dernier = t; this.liaison.etape = 0; this.alertes.delete("liaison1"); this.alertes.delete("liaison2"); }
  changerBatterie() { if (this.debout && this.enMouvement) return this.refuser("Changer la batterie à l'arrêt"); this.batterie = 100; this.alertes.clear(); return { ok: true }; }

  /* ── Pas de simulation ────────────────────────────────── */
  pas(dt) {
    dt = Math.min(0.05, Math.max(0, dt)); this.t += dt;
    const R = this.R, A = this.A;
    if (this.etat !== "affaisse") this.batterie = Math.max(0, this.batterie - (100 / (R.autonomie_min * 60)) * dt * (this.etat === "couche" ? 0.2 : this.enMouvement ? 1.2 : 0.7));
    this.securites();
    let vd = [0, 0], wz = null;
    const c = this.consigne;
    if (c.type === "manuelle") { vd = c.v.slice(); wz = c.wz; }
    else if (c.type === "trajectoire") {
      c.t += dt;
      const s = Math.max(0, Math.min(1, c.t / c.T)), f = s ** 3 * (10 - 15 * s + 6 * s * s), df = (30 * s * s * (1 - s) ** 2) / c.T;
      const pr = [lerp(c.p0[0], c.p1[0], f), lerp(c.p0[1], c.p1[1], f)];
      vd = [(c.p1[0] - c.p0[0]) * df + 2.0 * (pr[0] - this.p[0]), (c.p1[1] - c.p0[1]) * df + 2.0 * (pr[1] - this.p[1])];
      if (c.cap !== null && s < 0.97) this.lacetCible = c.cap;
      if (c.t >= c.T) {
        if (c.lacetFinal !== null && c.lacetFinal !== undefined) this.lacetCible = c.lacetFinal;
        this.consigne = { type: "maintien", p: c.p1.slice() };
        if (this.retourEnCours) { this.retourEnCours = false; this.coucher("retour terminé"); }
      }
    } else if (c.type === "maintien") vd = [1.5 * (c.p[0] - this.p[0]), 1.5 * (c.p[1] - this.p[1])];
    if (!this.debout || c.type === "freinage") { vd = [0, 0]; wz = 0; }
    // plafond selon la surface et l'allure
    const vmax = vitesseMax(this.salle, this.p[0], this.p[1], this.mode) * (c.type === "manuelle" ? 1 : Math.max(A.vitesse, 0.5));
    const n = Math.hypot(...vd); if (n > vmax) { vd[0] *= vmax / n; vd[1] *= vmax / n; }
    if (this.debout) vd = this.filtrerSol(vd);
    // dynamique : accélération bornée (freinage d'urgence plus fort)
    const amax = c.type === "freinage" ? 2.0 : R.acceleration_max_m_s2;
    const dv = [vd[0] - this.v[0], vd[1] - this.v[1]], nd = Math.hypot(...dv), lim = amax * dt;
    if (nd > lim) { dv[0] *= lim / nd; dv[1] *= lim / nd; }
    this.v[0] += dv[0]; this.v[1] += dv[1];
    if (c.type === "freinage" && Math.hypot(...this.v) < 0.01) {
      this.v = [0, 0]; this.consigne = { type: "aucune" }; this.changerPosture("couche");
      this.evenement("alerte", "Arrêté et couché après ARRÊT — réarmer pour reprendre");
    }
    // lacet
    const wmax = rad(R.vitesse_lacet_max_deg_s);
    if (wz !== null && this.debout) { this.wz = Math.max(-wmax, Math.min(wmax, wz)); this.lacetCible = this.lacet + this.wz * dt; }
    else if (this.debout) { const e = ecartAngle(this.lacet, this.lacetCible); this.wz = Math.max(-wmax, Math.min(wmax, e * 3)); }
    else this.wz = 0;
    this.lacet += this.wz * dt;
    // intégration, avec garantie finale : aucun pas ne fait sortir du sol praticable
    const avant = this.p.slice(), permis = verifierSol(this.salle, avant, this.ctx).ok;
    this.p[0] += this.v[0] * dt; this.p[1] += this.v[1] * dt;
    if (permis && !verifierSol(this.salle, this.p, this.ctx).ok) {
      for (const i of [0, 1]) { const q = this.p.slice(); q[i] = avant[i]; if (verifierSol(this.salle, q, this.ctx).ok) { this.p = q; this.v[i] = 0; break; } if (i === 1) { this.p = avant; this.v = [0, 0]; } }
    }
    this.calculerPose(dt);
  }

  filtrerSol(vd) {
    const ici = verifierSol(this.salle, this.p, this.ctx);
    if (!ici.ok) { this.evenement("alerte", `Robot hors zone : ${ici.motif}`, `hors:${ici.motif}`); return vd; }
    this.alertes.forEach((k) => k.startsWith("hors:") && this.alertes.delete(k));
    const ok = (v) => { const s = Math.hypot(...v), t = s / (2 * this.R.acceleration_max_m_s2) + 0.2;
      return verifierSol(this.salle, [this.p[0] + this.v[0] * 0.2 + v[0] * t, this.p[1] + this.v[1] * 0.2 + v[1] * t], this.ctx).ok; };
    if (ok(vd)) { this.alertes.delete("frein"); return vd; }
    for (const i of [0, 1]) { const v = vd.slice(); v[i] = 0; if (ok(v)) { this.evenement("avert", "Bord du sol praticable : le robot freine et longe la limite", "frein"); return v; } }
    this.evenement("avert", "Bord du sol praticable : arrêt", "frein");
    return [0, 0];
  }

  securites() {
    const R = this.R;
    if (this.etat === "debout" || this.etat === "posture") {
      if (this.batterie <= R.batterie_critique_pct) { this.evenement("alerte", `Batterie critique (${Math.round(this.batterie)} %)`, "bcrit"); this.coucher("batterie critique"); }
      else if (this.batterie <= R.batterie_retour_pct && !this.retourEnCours && !this.alertes.has("bret")) { this.alertes.add("bret"); if (this.etat === "posture") this.etat = "debout"; this.retour("batterie faible"); }
      else if (this.batterie <= R.batterie_alerte_pct) this.evenement("avert", `Batterie à ${Math.round(this.batterie)} %`, "balerte");
    }
    if (this.liaison.exigee && (this.etat === "debout" || this.etat === "posture")) {
      const muet = this.t - this.liaison.dernier;
      if (muet > R.perte_liaison_coucher_s && this.liaison.etape < 2) { this.liaison.etape = 2; this.evenement("alerte", "Liaison perdue : couché", "liaison2"); this.coucher("perte de liaison"); }
      else if (muet > R.perte_liaison_arret_s && this.liaison.etape < 1) { this.liaison.etape = 1; this.evenement("avert", "Liaison perdue : arrêt", "liaison1"); this.arreter(); }
    }
  }

  /* Pose du corps et des pattes : posture (avec transition) ou trot selon la vitesse. */
  calculerPose(dt) {
    const A = this.A;
    const sol = hauteurSol(this.salle, this.p[0], this.p[1], "salle_vide") ?? 0;
    this.postureT = Math.min(1, this.postureT + dt / 0.7);
    const h = this.etat === "affaisse" ? 0.07 : A.hauteur;
    let cible = this.etat === "affaisse" ? POSTURES.couche.pieds(h) : POSTURES[this.posture].pieds(h, this.t);
    if (this.etat === "affaisse") cible = Object.fromEntries(Object.entries(cible).map(([k, [a]]) => [k, [a * 1.6, -0.05]]));
    const pieds = {};
    const vb = this.versCorps(this.v), vitesse = Math.hypot(...this.v);
    const marche = this.debout && this.posture === "debout" && this.postureT >= 1 && (vitesse > 0.02 || Math.abs(this.wz) > 0.05);
    this.amplitude += ((marche ? 1 : 0) - this.amplitude) * Math.min(1, dt * 6);
    const f = 2.0 * A.cadence * (0.7 + 0.6 * Math.min(1, vitesse / 1.0));
    if (this.amplitude > 0.01) this.phase = (this.phase + f * dt) % 1;
    const beta = 0.6;
    for (const k of PATTES) {
      const base = this.postureDe && this.postureT < 1
        ? [lerp(this.postureDe[k][0], cible[k][0], this.postureT), lerp(this.postureDe[k][1], cible[k][1], this.postureT)]
        : cible[k];
      let [fa, fh] = base, fl = 0;
      if (this.amplitude > 0.01) {
        const [ha, hl] = HANCHES[k];
        const va = vb[0] - this.wz * hl, vl = vb[1] + this.wz * ha;   // vitesse du corps au droit de la hanche
        const Ts = beta / f, phi = (this.phase + PHASES[k]) % 1;
        let u, lev = 0;
        if (phi < beta) u = 0.5 - phi / beta; else { const s = (phi - beta) / (1 - beta); u = -0.5 + s; lev = A.levee * Math.sin(Math.PI * s); }
        fa += u * va * Ts * this.amplitude; fl += u * vl * Ts * this.amplitude; fh += lev * this.amplitude;
      }
      pieds[k] = [fa, fh, fl];
    }
    this.pieds = Object.fromEntries(PATTES.map((k) => [k, [pieds[k][0], pieds[k][1]]]));
    // corps : hauteur moyenne des hanches, tangage selon l'écart avant/arrière, pente du sol, rebond et roulis d'allure
    const hAv = -(pieds.AVG[1] + pieds.AVD[1]) / 2, hAr = -(pieds.ARG[1] + pieds.ARD[1]) / 2;
    const pente = this.pente(), rebond = this.amplitude * A.rebond * Math.sin(this.phase * 4 * Math.PI);
    this.tangageCorps = Math.atan2(hAv - hAr, 0.38) + pente;
    this.roulisCorps = this.amplitude * A.roulis * Math.sin(this.phase * 2 * Math.PI);
    this.y = sol + (hAv + hAr) / 2 + rebond;
    // pieds donnés dans le repère horizontal de chaque hanche → repère du corps incliné par la posture (la pente du sol,
    // elle, incline corps et appuis ensemble et n'entre pas dans la conversion)
    const th = Math.atan2(hAv - hAr, 0.38), ct = Math.cos(th), st = Math.sin(th);
    for (const k of PATTES) { const [fa, fh, fl] = pieds[k]; this.angles[k] = ik([fa * ct + fh * st, fl, -fa * st + fh * ct]); }
    // tête : regard vers un point, ou port de l'allure (balayage pour « curieux »)
    let tl = A.balayage ? rad(A.balayage) * Math.sin(this.t * 1.3) : 0, tt = rad(A.tete);
    if (this.regard) {
      const dx = this.regard[0] - this.p[0], dz = this.regard[2] - this.p[1], dy = this.regard[1] - (this.y + 0.1);
      tl = Math.max(-1.2, Math.min(1.2, ecartAngle(this.lacet, Math.atan2(dx, dz))));
      tt = Math.max(-0.8, Math.min(0.6, Math.atan2(dy, Math.hypot(dx, dz))));
    }
    if (this.etat === "couche" || this.etat === "affaisse") tt = Math.min(tt, rad(-10));
    this.tete.lacet += (tl - this.tete.lacet) * Math.min(1, dt * 4);
    this.tete.tangage += (tt - this.tete.tangage) * Math.min(1, dt * 4);
  }

  pente() {
    const ps = this.lacet, d = 0.19;
    const av = hauteurSol(this.salle, this.p[0] + Math.sin(ps) * d, this.p[1] + Math.cos(ps) * d, "salle_vide");
    const ar = hauteurSol(this.salle, this.p[0] - Math.sin(ps) * d, this.p[1] - Math.cos(ps) * d, "salle_vide");
    return av !== null && ar !== null ? Math.atan2(av - ar, 2 * d) : 0;
  }

  /* Vitesse du plan du théâtre → repère du corps [avant, gauche]. */
  versCorps(v) { const ps = this.lacet; return [v[0] * Math.sin(ps) + v[1] * Math.cos(ps), v[0] * Math.cos(ps) - v[1] * Math.sin(ps)]; }

  instantane() {
    return { p: [+this.p[0].toFixed(3), +this.y.toFixed(3), +this.p[1].toFixed(3)], v: this.v.map((x) => +x.toFixed(3)), lacet: +deg(this.lacet).toFixed(1),
      etat: this.etat, posture: this.posture, allure: this.allure, batterie: +this.batterie.toFixed(1), urgence: this.verrouUrgence, mode: this.mode,
      surface: surfaceDe(this.salle, this.p[0], this.p[1], "salle_vide")?.id || null };
  }
}

/* Durée d'une marche : demandée, ou déduite des plafonds de vitesse rencontrés sur le trajet (le plus lent l'emporte)
   et de l'accélération (pic 5,7735 d/T²) ; allongée au lieu d'être refusée. */
export function dureeMarche(salle, a, b, mode, duree, facteur = 1) {
  const d = Math.hypot(b[0] - a[0], b[1] - a[1]), R = salle.sol.regles;
  let vmin = Infinity;
  const n = Math.max(1, Math.ceil(d / 0.1));
  for (let i = 0; i <= n; i++) { const u = i / n; vmin = Math.min(vmin, vitesseMax(salle, a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, mode)); }
  vmin *= Math.max(facteur, 0.5);
  const Tmin = Math.max(0.6, (1.875 * d) / vmin, Math.sqrt((5.7735 * d) / R.acceleration_max_m_s2));
  const T = duree ?? Tmin;
  return { T: Math.max(T, Tmin), Tmin, ralenti: T < Tmin - 1e-6, distance: d };
}
