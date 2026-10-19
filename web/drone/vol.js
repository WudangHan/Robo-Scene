/* Robo-Scène — modèle de vol du drone virtuel (multirotor d'intérieur).
   Module pur (aucune dépendance au DOM ni à three.js) : testé sous Node, partagé par la page et par la conduite.

   Modèle volontairement simple et prudent : la vitesse suit la consigne avec un retard du premier ordre et une
   accélération bornée ; la consigne elle-même est plafonnée (vitesses horizontale, verticale et de lacet), puis
   filtrée par le géorepérage avant d'être appliquée, de sorte que le drone freine devant une limite au lieu de la
   franchir. Les sécurités d'un autopilote réel sont reproduites : seuils de batterie (alerte, retour, atterrissage),
   perte de liaison (stationnaire puis atterrissage), arrêt d'urgence (descente contrôlée) et coupure des moteurs,
   distincte et confirmée, qui fait tomber l'appareil comme dans la réalité.

   Repère : x vers cour, y vers le haut, z vers la salle. Lacet ψ en radians : 0 = nez vers la salle,
   +π/2 = nez vers cour ; avant = (sin ψ, 0, cos ψ), droite (du drone) = (−cos ψ, 0, sin ψ). */
import { verifier } from "./geofence.js";

const G = 9.81;
const norme = (v) => Math.hypot(v[0], v[1], v[2]);
const ecartAngle = (a, b) => Math.atan2(Math.sin(b - a), Math.cos(b - a));
export const deg = (r) => (r * 180) / Math.PI;
export const rad = (d) => (d * Math.PI) / 180;

/* Trajectoire à secousse minimale (Flash et Hogan, 1985) : position et vitesse à l'instant t ∈ [0, T]. */
export function secousseMin(p0, p1, T, t) {
  const s = Math.max(0, Math.min(1, t / T));
  const f = s ** 3 * (10 - 15 * s + 6 * s * s), df = (30 * s * s * (1 - s) ** 2) / T;
  return { p: p0.map((a, i) => a + (p1[i] - a) * f), v: p0.map((a, i) => (p1[i] - a) * df), s };
}

export const ETATS = {
  au_sol: "Au sol", decollage: "Décollage", vol: "En vol", atterrissage: "Atterrissage", urgence: "Descente d'urgence",
  chute: "Moteurs coupés — chute", coupe: "Moteurs coupés",
};

export class DroneVirtuel {
  constructor(salle, opts = {}) {
    this.salle = salle;
    this.R = salle.regles;
    this.mode = opts.mode || "plateau";
    this.interpretes = [];
    this.p = salle.aire.centre.slice();
    this.v = [0, 0, 0];
    this.lacet = opts.lacet ?? Math.PI;        // au départ, nez vers le lointain (vu de la salle, le drone « regarde » la scène)
    this.lacetCible = this.lacet;
    this.etat = "au_sol";
    this.arme = false;
    this.verrouUrgence = false;
    this.batterie = 100;
    this.helices = 0;                         // régime des hélices, 0 à 1 (animation, consommation)
    this.consigne = { type: "aucune" };
    this.turbulence = opts.turbulence ?? 0.05;
    this.liaison = { exigee: false, dernier: 0, etape: 0 };
    this.t = 0;
    this.alertes = new Set();
    this.surEvenement = opts.surEvenement || (() => {});
    this.retourEnCours = false;
    this.alea = opts.alea || Math.random;
  }

  get ctx() { return { mode: this.mode, interpretes: this.interpretes }; }
  get sol() { const z = this.salle.volumes; return (this.p[2] > z.plateau.z[1] ? z.salle.y[0] : 0); }
  get altitude() { return this.p[1] - this.sol; }
  get enVol() { return ["decollage", "vol", "atterrissage", "urgence"].includes(this.etat); }

  evenement(niveau, msg, cle) {
    if (cle) { if (this.alertes.has(cle)) return; this.alertes.add(cle); }
    this.surEvenement({ niveau, msg, t: this.t });
  }

  /* ── Commandes ─────────────────────────────────────────── */
  refuser(msg) { this.evenement("refus", msg); return { ok: false, motif: msg }; }

  armer() {
    if (this.verrouUrgence) return this.refuser("Arrêt d'urgence actif : réarmer d'abord");
    if (this.etat !== "au_sol" && this.etat !== "coupe") return this.refuser("Armement possible seulement au sol");
    if (this.batterie <= this.R.batterie_critique_pct) return this.refuser("Batterie trop faible pour armer");
    this.arme = true; this.etat = "au_sol"; this.helices = 0.12;
    this.evenement("info", "Moteurs armés (ralenti)");
    return { ok: true };
  }

  desarmer() {
    if (this.enVol && this.altitude > 0.08) return this.refuser("Désarmement refusé en vol : atterrir d'abord (ou coupure des moteurs)");
    this.arme = false; this.helices = 0; this.consigne = { type: "aucune" };
    if (this.etat !== "coupe") this.etat = "au_sol";
    this.evenement("info", "Moteurs désarmés");
    return { ok: true };
  }

  decoller(hauteur = 1.5) {
    if (this.verrouUrgence) return this.refuser("Arrêt d'urgence actif : réarmer d'abord");
    if (this.etat !== "au_sol") return this.refuser("Décollage possible seulement depuis le sol");
    if (!this.arme) { const a = this.armer(); if (!a.ok) return a; }
    const cible = [this.p[0], this.sol + Math.max(0.6, hauteur), this.p[2]];
    const v = verifier(this.salle, cible, this.ctx);
    if (!v.ok) { this.arme = false; this.helices = 0; return this.refuser(`Décollage refusé : ${v.motif}`); }
    this.etat = "decollage"; this.retourEnCours = false;
    this.consigne = { type: "point", p: cible, vitesse: Math.min(0.6, this.R.vitesse_max_v_m_s) };
    this.evenement("info", `Décollage vers ${cible[1].toFixed(1)} m`);
    return { ok: true };
  }

  atterrir(motif = "") {
    if (!this.enVol) return this.refuser("Le drone n'est pas en vol");
    if (this.etat === "urgence") return { ok: true };
    this.etat = "atterrissage";
    this.consigne = { type: "atterrissage", x: this.p[0], z: this.p[2] };
    this.evenement(motif ? "avert" : "info", `Atterrissage${motif ? ` (${motif})` : ""}`);
    return { ok: true };
  }

  stationnaire() {
    if (!this.enVol || this.etat === "urgence" || this.etat === "atterrissage") return this.refuser("Stationnaire impossible dans cet état");
    this.etat = "vol"; this.consigne = { type: "stationnaire", p: this.p.slice() }; this.retourEnCours = false;
    return { ok: true };
  }

  /* Aller à un point, en ligne droite, selon une loi à secousse minimale ; durée allongée si elle dépasse les plafonds. */
  allerA(cible, o = {}) {
    if (this.etat === "decollage") return this.refuser("Attendre la fin du décollage (vol stationnaire)");
    if (!this.enVol || this.etat === "urgence" || this.etat === "atterrissage") return this.refuser("Le drone doit être en vol");
    const v = verifier(this.salle, cible, this.ctx);
    if (!v.ok) return this.refuser(`Destination refusée : ${v.motif}`);
    const T = dureeMin(this.R, this.p, cible, o.duree, o.vitesse);
    this.etat = "vol";
    this.consigne = { type: "trajectoire", p0: this.p.slice(), p1: cible.slice(), T: T.T, t: 0 };
    if (o.lacet !== undefined && o.lacet !== null) this.lacetCible = o.lacet;
    if (T.ralenti) this.evenement("avert", `Mouvement ralenti : ${o.duree?.toFixed?.(1) ?? "?"} → ${T.T.toFixed(1)} s (plafonds de vitesse)`);
    return { ok: true, duree: T.T };
  }

  /* Pilotage manuel : manche normalisé [droite, avant, haut] ∈ [−1, 1] et lacet ∈ [−1, 1] (repère du drone ;
     lacet positif = rotation vers la droite du drone, sens horaire vu de dessus, donc lacet du théâtre décroissant). */
  manuel(manche, lacet = 0) {
    if (!this.enVol || this.etat === "urgence" || this.etat === "atterrissage") return { ok: false };
    const [d, a, h] = manche.map((x) => Math.max(-1, Math.min(1, x || 0)));
    const ps = this.lacet, R = this.R;
    const f = [Math.sin(ps), 0, Math.cos(ps)], r = [-Math.cos(ps), 0, Math.sin(ps)];
    const vh = R.vitesse_max_h_m_s;
    const vd = [(f[0] * a + r[0] * d) * vh, h * R.vitesse_max_v_m_s, (f[2] * a + r[2] * d) * vh];
    const actif = Math.abs(d) + Math.abs(a) + Math.abs(h) + Math.abs(lacet) > 0.02;
    if (actif) {
      this.etat = "vol"; this.retourEnCours = false;
      this.consigne = { type: "manuelle", v: vd, wz: -lacet * rad(R.vitesse_lacet_max_deg_s) };
    } else if (this.consigne.type === "manuelle") {
      this.consigne = { type: "stationnaire", p: this.p.slice() };
    }
    return { ok: true };
  }

  retour(motif = "") {
    if (!this.enVol || this.etat === "urgence") return this.refuser("Retour impossible dans cet état");
    const haut = [this.salle.aire.centre[0], Math.max(1.5, Math.min(this.p[1], 4)), this.salle.aire.centre[2]];
    const r = this.allerA(haut, { vitesse: this.R.vitesse_max_h_m_s * 0.7 });
    if (r.ok) { this.retourEnCours = true; this.evenement("avert", `Retour à l'aire de décollage${motif ? ` (${motif})` : ""}`); }
    return r;
  }

  /* ARRÊT : descente contrôlée à la verticale, verrouillée jusqu'au réarmement (ISO 13850 : réarmement distinct). */
  arretUrgence(motif = "bouton ARRÊT") {
    this.verrouUrgence = true;
    if (this.enVol) { this.etat = "urgence"; this.consigne = { type: "urgence" }; }
    else { this.arme = false; this.helices = 0; }
    this.evenement("alerte", `ARRÊT D'URGENCE — ${motif} : descente contrôlée à ${this.R.descente_urgence_m_s} m/s`);
    return { ok: true };
  }

  /* Coupure des moteurs : dernier recours (drone hors de contrôle) ; l'appareil tombe. */
  couperMoteurs(confirmation) {
    if (confirmation !== "COUPER") return this.refuser("Coupure des moteurs : confirmation « COUPER » requise");
    this.verrouUrgence = true; this.arme = false;
    this.etat = this.altitude > 0.05 ? "chute" : "coupe"; this.consigne = { type: "aucune" };
    this.evenement("alerte", "COUPURE DES MOTEURS — le drone tombe");
    return { ok: true };
  }

  rearmer() {
    if (this.enVol) return this.refuser("Réarmement possible seulement une fois le drone posé");
    this.verrouUrgence = false; this.alertes.clear();
    if (this.etat === "coupe") this.etat = "au_sol";
    this.evenement("info", "Système du drone réarmé");
    return { ok: true };
  }

  signalLiaison(t = this.t) { this.liaison.dernier = t; if (this.liaison.etape) this.evenement("info", "Liaison rétablie"); this.liaison.etape = 0; this.alertes.delete("liaison1"); this.alertes.delete("liaison2"); }

  /* Recharge (changement de batterie au sol). */
  changerBatterie() { if (this.enVol) return this.refuser("Changer la batterie au sol seulement"); this.batterie = 100; this.alertes.clear(); return { ok: true }; }

  /* ── Pas de simulation ────────────────────────────────── */
  pas(dt) {
    dt = Math.min(0.05, Math.max(0, dt));
    this.t += dt;
    const R = this.R;
    // batterie
    if (this.helices > 0) {
      const effort = 1 + 0.35 * Math.min(1, norme(this.v) / R.vitesse_max_h_m_s);
      this.batterie = Math.max(0, this.batterie - (100 / (R.autonomie_min * 60)) * dt * (this.enVol ? effort : 0.15));
    }
    this.securites();
    let vd = [0, 0, 0], wz = null;
    const c = this.consigne;
    if (this.etat === "chute") {
      this.v[1] -= G * dt; this.v[0] *= 0.99; this.v[2] *= 0.99;
      this.integrer(dt);
      if (this.p[1] <= this.sol) { this.p[1] = this.sol; this.v = [0, 0, 0]; this.etat = "coupe"; this.helices = 0; this.evenement("alerte", "Drone au sol (impact)"); }
      this.helices = Math.max(0, this.helices - dt * 2);
      return;
    }
    if (!this.enVol) { this.v = [0, 0, 0]; this.helices = this.arme ? 0.12 : 0; return; }
    if (c.type === "manuelle") { vd = c.v.slice(); wz = c.wz; }
    else if (c.type === "point" || c.type === "stationnaire") vd = this.versPoint(c.p, c.vitesse);
    else if (c.type === "trajectoire") {
      c.t += dt;
      const r = secousseMin(c.p0, c.p1, c.T, c.t);
      vd = r.v.map((v, i) => v + 2.2 * (r.p[i] - this.p[i]));
      if (c.t >= c.T) {
        this.consigne = { type: "stationnaire", p: c.p1.slice() };
        if (this.retourEnCours) { this.retourEnCours = false; this.atterrir("retour"); }
      }
    } else if (c.type === "atterrissage") {
      vd = [2 * (c.x - this.p[0]), -Math.min(0.45, 0.15 + 0.4 * this.altitude), 2 * (c.z - this.p[2])];
    } else if (c.type === "urgence") vd = [0, -R.descente_urgence_m_s, 0];
    // plafonds
    const h = Math.hypot(vd[0], vd[2]);
    if (h > R.vitesse_max_h_m_s) { vd[0] *= R.vitesse_max_h_m_s / h; vd[2] *= R.vitesse_max_h_m_s / h; }
    vd[1] = Math.max(-R.vitesse_max_v_m_s, Math.min(R.vitesse_max_v_m_s, vd[1]));
    // géorepérage (sauf descente d'atterrissage ou d'urgence, qui est l'action sûre)
    if (!["atterrissage", "urgence"].includes(this.etat)) vd = this.filtrerZone(vd);
    // dynamique : premier ordre, accélération bornée, légère turbulence (ventilation de salle)
    const tau = 0.35, amax = R.acceleration_max_m_s2;
    const dv = vd.map((x, i) => (x - this.v[i]) * Math.min(1, dt / tau));
    const n = norme(dv), lim = amax * dt;
    for (let i = 0; i < 3; i++) this.v[i] += n > lim ? (dv[i] * lim) / n : dv[i];
    if (this.turbulence) for (const i of [0, 2]) this.v[i] += (this.alea() - 0.5) * this.turbulence * dt * 4;
    // lacet
    const wmax = rad(R.vitesse_lacet_max_deg_s);
    if (wz !== null && wz !== undefined) { this.lacet += Math.max(-wmax, Math.min(wmax, wz)) * dt; this.lacetCible = this.lacet; }
    else { const e = ecartAngle(this.lacet, this.lacetCible); this.lacet += Math.max(-wmax * dt, Math.min(wmax * dt, e * 2.5 * dt)); }
    const avant = this.p.slice(), etaitPermis = verifier(this.salle, avant, this.ctx).ok;
    this.integrer(dt);
    // garantie finale : un pas qui ferait entrer dans une zone interdite est annulé, axe par axe
    if (etaitPermis && !["atterrissage", "urgence"].includes(this.etat) && !verifier(this.salle, this.p, this.ctx).ok) {
      for (let i = 0; i < 3; i++) {
        const essai = this.p.slice(); essai[i] = avant[i];
        if (verifier(this.salle, essai, this.ctx).ok) { this.p = essai; this.v[i] = 0; break; }
        if (i === 2) { this.p = avant; this.v = [0, 0, 0]; }
      }
    }
    // décollage terminé, atterrissage terminé
    if (this.etat === "decollage" && Math.abs(this.p[1] - c.p[1]) < 0.06) { this.etat = "vol"; this.consigne = { type: "stationnaire", p: c.p.slice() }; this.evenement("info", "En vol stationnaire"); }
    if ((this.etat === "atterrissage" || this.etat === "urgence") && this.altitude <= 0.02) {
      this.p[1] = this.sol; this.v = [0, 0, 0]; this.etat = "au_sol"; this.arme = false; this.consigne = { type: "aucune" };
      this.evenement(this.verrouUrgence ? "alerte" : "info", this.verrouUrgence ? "Posé après arrêt d'urgence — réarmer pour reprendre" : "Posé, moteurs désarmés");
    }
    // régime des hélices (animation) : sustentation + effort vertical et horizontal
    this.helices = Math.max(0.3, Math.min(1, 0.55 + 0.25 * (this.v[1] / R.vitesse_max_v_m_s) + 0.1 * Math.hypot(this.v[0], this.v[2]) / R.vitesse_max_h_m_s));
  }

  integrer(dt) {
    for (let i = 0; i < 3; i++) this.p[i] += this.v[i] * dt;
    if (this.p[1] < this.sol) { this.p[1] = this.sol; if (this.v[1] < 0) this.v[1] = 0; }
  }

  versPoint(p, vmax = this.R.vitesse_max_h_m_s) {
    const e = p.map((x, i) => x - this.p[i]), d = norme(e);
    if (d < 1e-4) return [0, 0, 0];
    const v = Math.min(vmax, 1.4 * d, Math.sqrt(2 * this.R.acceleration_max_m_s2 * d) * 0.8);
    return e.map((x) => (x / d) * v);
  }

  /* Freinage devant les limites : on prévoit le point d'arrêt ; s'il est interdit, on retire les composantes fautives. */
  filtrerZone(vd) {
    const ici = verifier(this.salle, this.p, this.ctx);
    // point d'arrêt prévu : élan de la vitesse actuelle (retard du premier ordre) + freinage depuis la consigne essayée
    const ok = (v) => {
      const s = norme(v), t = s / (2 * this.R.acceleration_max_m_s2) + 0.25;
      return verifier(this.salle, this.p.map((x, i) => x + this.v[i] * 0.35 + v[i] * t), this.ctx).ok;
    };
    if (!ici.ok) {
      // déjà hors zone (interprète entré dans le cylindre, mode changé…) : seuls les mouvements qui en sortent sont permis
      this.evenement("alerte", `Drone hors zone : ${ici.motif}`, `hors:${ici.motif}`);
      return vd;
    }
    this.alertes.forEach((k) => k.startsWith("hors:") && this.alertes.delete(k));
    if (ok(vd)) { this.alertes.delete("frein"); return vd; }
    const essais = [[0], [1], [2], [0, 2], [0, 1], [1, 2]];
    for (const axes of essais) {
      const v = vd.slice(); for (const a of axes) v[a] = 0;
      if (ok(v)) { this.evenement("avert", "Limite de zone : le drone freine et glisse le long du mur virtuel", "frein"); return v; }
    }
    this.evenement("avert", "Limite de zone : arrêt devant le mur virtuel", "frein");
    return [0, 0, 0];
  }

  securites() {
    const R = this.R;
    if (this.enVol && this.etat !== "urgence") {
      if (this.batterie <= R.batterie_critique_pct && this.etat !== "atterrissage") { this.evenement("alerte", `Batterie critique (${Math.round(this.batterie)} %)`, "bcrit"); this.atterrir("batterie critique"); }
      else if (this.batterie <= R.batterie_retour_pct && !this.retourEnCours && this.etat !== "atterrissage" && !this.alertes.has("bret")) { this.alertes.add("bret"); this.retour("batterie faible"); }
      else if (this.batterie <= R.batterie_alerte_pct) this.evenement("avert", `Batterie à ${Math.round(this.batterie)} %`, "balerte");
    }
    if (this.liaison.exigee && this.enVol && this.etat !== "urgence") {
      const muet = this.t - this.liaison.dernier;
      if (muet > R.perte_liaison_atterrir_s && this.liaison.etape < 2) { this.liaison.etape = 2; this.evenement("alerte", "Liaison perdue : atterrissage", "liaison2"); this.atterrir("perte de liaison"); }
      else if (muet > R.perte_liaison_stationnaire_s && this.liaison.etape < 1) { this.liaison.etape = 1; this.evenement("avert", "Liaison perdue : vol stationnaire", "liaison1"); this.stationnaire(); }
    }
  }

  instantane() {
    return { p: this.p.map((x) => +x.toFixed(3)), v: this.v.map((x) => +x.toFixed(3)), lacet: +deg(this.lacet).toFixed(1),
      etat: this.etat, arme: this.arme, batterie: +this.batterie.toFixed(1), urgence: this.verrouUrgence, mode: this.mode };
  }
}

/* Durée d'un déplacement : demandée, ou déduite d'une vitesse, puis allongée pour respecter les plafonds de vitesse
   (pic de vitesse de la loi à secousse minimale : 1,875 d/T) et d'accélération (pic : 5,7735 d/T²). */
export function dureeMin(R, a, b, duree, vitesse) {
  const dh = Math.hypot(b[0] - a[0], b[2] - a[2]), dv = Math.abs(b[1] - a[1]), d = Math.hypot(dh, dv);
  const Tmin = Math.max(0.5, (1.875 * dh) / R.vitesse_max_h_m_s, (1.875 * dv) / R.vitesse_max_v_m_s, Math.sqrt((5.7735 * d) / R.acceleration_max_m_s2));
  let T = duree ?? (vitesse ? (1.875 * d) / vitesse : Tmin);
  const ralenti = T < Tmin - 1e-6;
  return { T: Math.max(T, Tmin), Tmin, ralenti, distance: d };
}
