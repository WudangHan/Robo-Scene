/* Robo-Scène — pont simulé dans le navigateur (audit du 2026-10-16, chantier 3).
   Quand la Console est servie en ligne (Netlify) et que le pont local (ws://127.0.0.1:8765) ne répond pas,
   app.js remplace la connexion WebSocket par cet objet de même interface (readyState, send, close,
   onopen, onmessage, onclose). Il reproduit le robot simulé du pont Python (bridge/transports.py,
   TransportSimule) : interpolation linéaire des servos, vitesse angulaire plafonnée, cinématique
   différentielle sur le plateau de 4 × 3 m, décharge de la batterie, chien de garde des roues, arrêt
   d'urgence. Aucune commande ne quitte le navigateur ; rien n'est journalisé ni versionné (pas de corpus). */
"use strict";
window.ROBO_SIMULATEUR = (() => {
  const LIM = { noms: ["Base", "Épaule", "Coude", "Tête"], min_deg: [10, 20, 15, 30], max_deg: [170, 160, 165, 150],
    repos: [90, 90, 90, 90] };                          // valeurs par défaut de config.toml [robot.articulations]
  const SECU = { vitesse_max: 90, propulsion_max: 0.6, cdg_ms: 500, batterie_min_v: 6.4 };
  const SEQUENCES_DEMO = {
    salut: [{ deg: [90, 140, 60, 90], ms: 900, pause_ms: 150 }, { deg: [70, 140, 40, 90], ms: 450 },
      { deg: [110, 140, 40, 90], ms: 450 }, { deg: [70, 140, 40, 90], ms: 450 }, { deg: [110, 140, 40, 90], ms: 450 },
      { deg: [90, 90, 90, 90], ms: 1000 }],
    regard: [{ deg: [60, 90, 90, 60], ms: 1200, pause_ms: 400 }, { deg: [120, 90, 90, 120], ms: 1800, pause_ms: 400 },
      { deg: [90, 90, 90, 90], ms: 1000 }],
    "révérence": [{ deg: [90, 90, 90, 60], ms: 800, pause_ms: 200 }, { deg: [90, 50, 120, 40], ms: 1400, pause_ms: 800 },
      { deg: [90, 90, 90, 90], ms: 1400 }],
  };
  const borne = (v, a, b) => Math.max(a, Math.min(b, v));
  const heure = () => new Date().toTimeString().slice(0, 8);
  const idSeance = (n) => `${new Date().toISOString().slice(0, 10).replace(/-/g, "")}_SIM_DEMO_${String(n).padStart(3, "0")}`;

  function distanceMur(x, y, th) {                      // même calcul que TransportSimule._distance_mur
    const c = Math.cos(th), s = Math.sin(th), ds = [];
    if (c > 1e-6) ds.push((2 - x) / c);
    if (c < -1e-6) ds.push((-2 - x) / c);
    if (s > 1e-6) ds.push((1.5 - y) / s);
    if (s < -1e-6) ds.push((-1.5 - y) / s);
    return Math.min(ds.length ? Math.min(...ds) : 4, 4);
  }

  class PontSimule {
    constructor() {
      this.readyState = 0;
      this.onopen = this.onmessage = this.onclose = null;
      this.deg = LIM.repos.slice(); this.depart = this.deg.slice(); this.cible = this.deg.slice();
      this.t0 = 0; this.duree = 0;
      this.roues = [0, 0]; this.dernierDrive = 0;
      this.pose = [0, 0, 0]; this.vbat = 8.2; this.arret = false;
      this.seuil = 0.75; this.observateur = null; this.regle = "bibliotheque_fermee";
      this.nSeance = 1; this.seance = idSeance(1);
      this.sequences = Object.fromEntries(Object.entries(SEQUENCES_DEMO).map(([k, v]) => [k, v.map((im) => ({ ...im }))]));
      this.lecture = null;                               // {nom, k, jeton}
      this.minuterie = null;
      setTimeout(() => this._ouvrir(), 0);
    }
    _emettre(m) { if (this.readyState === 1 && this.onmessage) this.onmessage({ data: JSON.stringify(m) }); }
    _journal(msg, niveau = "info") { this._emettre({ type: "journal", niveau, msg, ts: heure() }); }
    _config() {
      return { type: "config", robot_id: "sim-navigateur", ...LIM, unites: LIM.noms.map(() => "deg"), propulsion: true,
        propulsion_max: SECU.propulsion_max, vitesse_max: SECU.vitesse_max, batterie_min_v: SECU.batterie_min_v,
        seuil: this.seuil, execution_auto: false, regle_ia: this.regle, type_seance: "S04",
        moteur_ia: "aucun (simulation dans le navigateur)", seance: this.seance, transport: "simulation · navigateur",
        robot: "ROBO-SCENE-01 (simulé)", simulation: true, rayon_exclusion_m: 0, observateur: this.observateur,
        flotte: [{ id: "sim-navigateur", nom: "ROBO-SCENE-01 (simulé)", simulation: true, pilote: "navigateur", lien: "connecte" }],
        profils: [], statuts_sequences: {} };
    }
    _ouvrir() {
      this.readyState = 1;
      this.onopen?.({});
      this._emettre(this._config());
      this._emettre({ type: "sequences", liste: Object.keys(this.sequences) });
      this._journal("Mode simulation autonome dans le navigateur : aucune commande matérielle, rien n'est consigné ni versionné.", "avert");
      let dernier = performance.now();
      this.minuterie = setInterval(() => { const t = performance.now(); this._pas((t - dernier) / 1000, t); dernier = t; }, 50);
    }
    close() {
      clearInterval(this.minuterie); this.readyState = 3;
      this.onclose?.({ code: 1000, reason: "simulation fermée" });
    }
    _viser(deg, ms) {
      const cible = deg.map((d, i) => (d == null ? this.deg[i] : borne(Number(d), LIM.min_deg[i], LIM.max_deg[i])));
      const ecart = Math.max(...cible.map((c, i) => Math.abs(c - this.deg[i])));
      this.depart = this.deg.slice(); this.cible = cible; this.t0 = performance.now();
      this.duree = Math.max(Number(ms) || 0, (ecart / SECU.vitesse_max) * 1000);   // vitesse angulaire plafonnée
    }
    _pas(dt, maintenant) {
      if (maintenant - this.dernierDrive > SECU.cdg_ms) this.roues = [0, 0];          // chien de garde
      const a = this.duree <= 0 ? 1 : Math.min(1, (maintenant - this.t0) / this.duree);
      if (!this.arret) this.deg = this.depart.map((d, i) => d + (this.cible[i] - d) * a);
      const vmax = 0.5, voie = 0.18, vl = this.roues[0] * vmax, vr = this.roues[1] * vmax;
      const v = (vl + vr) / 2, w = (vr - vl) / voie;
      let [x, y, th] = this.pose;
      th += w * dt; x = borne(x + v * Math.cos(th) * dt, -2, 2); y = borne(y + v * Math.sin(th) * dt, -1.5, 1.5);
      this.pose = [x, y, th];
      this.vbat = Math.max(6, this.vbat - (0.00002 + 0.0004 * (Math.abs(vl) + Math.abs(vr))) * dt * 20);
      this._emettre({ type: "etat", deg: this.deg.map((d) => Math.round(d * 10) / 10), drive: this.roues.map((r) => Math.round(r * 100) / 100),
        vbat: Math.round((this.vbat + (Math.random() - 0.5) * 0.02) * 100) / 100,
        dist: Math.round((distanceMur(x, y, th) * 100 + (Math.random() - 0.5) * 2) * 10) / 10,
        pose: [x, y, th].map((q) => Math.round(q * 1000) / 1000), robot_id: "sim-navigateur", lien: "connecte",
        arret: this.arret, sequence: this.lecture?.nom || null, seance: this.seance });
    }
    async _jouer(nom) {
      const images = this.sequences[nom];
      if (!images) { this._journal(`Séquence inconnue : ${nom}`, "refus"); return; }
      const jeton = Symbol(nom);
      this.lecture = { nom, jeton };
      this._journal(`Séquence « ${nom} » lancée (simulation)`);
      for (const im of images) {
        if (this.lecture?.jeton !== jeton || this.arret) return;
        this._viser(im.deg, im.ms ?? 800);
        await new Promise((r) => setTimeout(r, this.duree + (im.pause_ms || 0)));
      }
      if (this.lecture?.jeton === jeton) { this.lecture = null; this._journal(`Séquence « ${nom} » terminée`); }
    }
    send(texte) {
      let m;
      try { m = JSON.parse(texte); } catch (e) { return; }
      const bloque = this.arret && ["articulation", "articulations", "propulsion", "seq_jouer", "repos"].includes(m.op);
      if (bloque) { this._journal("Commande refusée : arrêt d'urgence actif (réarmer d'abord)", "refus"); return; }
      switch (m.op) {
        case "articulation": { const d = this.cible.slice(); d[m.i] = m.deg; this._viser(d, m.ms); break; }
        case "articulations": this._viser(m.deg, m.ms); break;
        case "repos": this.lecture = null; this._viser(LIM.repos, 1000); this._journal("Retour à la position de repos"); break;
        case "propulsion":
          this.roues = [borne(+m.g || 0, -SECU.propulsion_max, SECU.propulsion_max), borne(+m.d || 0, -SECU.propulsion_max, SECU.propulsion_max)];
          this.dernierDrive = performance.now(); break;
        case "estop":
          this.arret = true; this.roues = [0, 0]; this.lecture = null;
          this.depart = this.deg.slice(); this.cible = this.deg.slice(); this.duree = 0;
          this._journal(`ARRÊT D'URGENCE (${m.motif || "commande"})`, "alerte"); break;
        case "rearmer": this.arret = false; this._journal("Réarmé : commandes de nouveau acceptées"); break;
        case "seq_jouer": this._jouer(m.nom); break;
        case "seq_arreter": this.lecture = null; this.depart = this.deg.slice(); this.cible = this.deg.slice(); this.duree = 0;
          this._journal("Séquence arrêtée"); break;
        case "seq_lire": if (this.sequences[m.nom]) this._emettre({ type: "sequence", sequence: { nom: m.nom, images: this.sequences[m.nom] } }); break;
        case "seq_enregistrer": {
          const s = m.sequence || {};
          if (!s.nom || !Array.isArray(s.images) || !s.images.length) { this._journal("Séquence vide ou sans nom", "refus"); break; }
          this.sequences[s.nom] = s.images.map((im) => ({ deg: im.deg.slice(), ms: im.ms ?? 800, pause_ms: im.pause_ms ?? 0 }));
          this._emettre({ type: "sequences", liste: Object.keys(this.sequences).filter((n) => !n.startsWith("_")) });
          if (!s.nom.startsWith("_")) this._journal(`Séquence « ${s.nom} » gardée pour cette page seulement (simulation)`);
          break;
        }
        case "seuil": this.seuil = borne(+m.valeur || 0, 0, 1); this._emettre(this._config()); break;
        case "regle_ia": this.regle = m.valeur === "angles_s04" ? "angles_s04" : "bibliotheque_fermee"; this._emettre(this._config()); break;
        case "observateur":
          this.observateur = m.present ? { initiales: String(m.initiales || "").slice(0, 12), depuis: heure() } : null;
          this._emettre(this._config()); break;
        case "ia_demander":
          this._journal("IA supervisée indisponible en simulation dans le navigateur : lancer le pont local (aucune requête n'est envoyée).", "refus"); break;
        case "cloturer": this.nSeance += 1; this.seance = idSeance(this.nSeance); this._emettre(this._config());
          this._journal(`Nouvelle séance de démonstration : ${this.seance}`); break;
        case "note": case "transformation_de_tete": case "operation_autre":
          this._journal("Saisie reçue mais non consignée : la traçabilité exige le pont local (simulation).", "avert"); break;
        default: this._journal(`Opération « ${m.op} » non simulée dans le navigateur`, "avert");
      }
    }
  }
  return { PontSimule, distanceMur };
})();
