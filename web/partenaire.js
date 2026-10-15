/* Partenaire de théâtre ROBO-SCÈNE — interface.
   Voix : synthèse vocale du navigateur (ou signal tonal) ; écoute : détection d'activité vocale
   calculée localement ; transcription et caméra facultatives, soumises au consentement. */
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const echapper = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const attendre = (ms) => new Promise((r) => setTimeout(r, ms));
const suite = (t) => (/[….]$/.test(t) ? t : t + "…");

/* ══════════ Connexion au pont ══════════ */
let ws = null;
const enAttente = new Map();          // op -> [resolve, reject][]
let P = null;                          // état du partenaire (p_etat)
let etatRobot = { arret: false, lien: "deconnecte" };
const cachePieces = new Map();

function connecter() {
  ws = new WebSocket(window.ROBO_PONT.url);
  ws.onopen = async () => { window.ROBO_PONT.ouvert(); await chargerEtat(); };
  ws.onclose = () => { window.ROBO_PONT.ferme(); majLien("interface"); setTimeout(connecter, 1500); };
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.type === "etat") return surEtatRobot(m);
    if (m.type === "journal" && (m.niveau === "alerte" || m.niveau === "refus")) return toast(m.msg);
    if (m.type === "p_erreur") {
      const f = enAttente.get(m.op); if (f && f.length) f.shift()[1](new Error(m.msg));
      return toast(m.msg);
    }
    const f = enAttente.get(m.type);
    if (f && f.length) f.shift()[0](m);
  };
}
function envoyer(op, data = {}) { if (ws && ws.readyState === 1) ws.send(JSON.stringify({ op, ...data })); }
function demander(op, data = {}) {
  return new Promise((ok, ko) => {
    if (!enAttente.has(op)) enAttente.set(op, []);
    enAttente.get(op).push([ok, ko]);
    envoyer(op, data);
  });
}
function toast(msg, type = "") {
  let t = $("#toast"); if (!t) { t = document.createElement("div"); t.id = "toast"; document.body.appendChild(t); }
  t.className = type; t.textContent = msg; t.hidden = false;
  clearTimeout(t._h); t._h = setTimeout(() => (t.hidden = true), 5500);
}

function surEtatRobot(m) {
  const avant = etatRobot.arret;
  etatRobot = m;
  majLien(m.lien);
  $("#bandeau-arret").hidden = !m.arret;
  $("#btn-rearmer").disabled = !m.arret;
  if (m.arret && !avant) { Voix.annuler(); Repetition.pause(true); }
}
function majLien(l) {
  const map = { connecte: ["Robot connecté", "ok"], muet: ["Télémétrie muette", "avert"], deconnecte: ["Robot déconnecté", "alerte"], interface: ["Pont injoignable", "alerte"] };
  const [t, c] = map[l] || ["—", "neutre"];
  const p = $("#st-lien"); p.textContent = t; p.className = "pastille " + c;
}

async function chargerEtat() {
  P = await demander("p_etat");
  $("#st-ia").textContent = "IA : " + P.moteur_ia;
  $("#incarnation").checked = P.incarnation;
  $("#r-souffleur").value = P.souffleur_delai_s;
  $("#r-regime").value = P.regime;
  remplirSelect($("#r-style"), P.styles); remplirSelect($("#v-style"), P.styles);
  remplirSelect($("#v-emotion"), P.emotions);
  remplirSelect($("#v-melange"), [""].concat(P.emotions), (e) => e || "—");
  remplirSelect($("#d-corpus"), P.corpus_dracor);
  majActeurs(P.acteurs);
  majPieces(P.pieces);
  $("#t-externes").innerHTML = P.repertoires_externes.map((r) => `<div><a href="${echapper(r.url)}" target="_blank" rel="noopener">${echapper(r.nom)}</a><br>${echapper(r.portee)}<br><span class="petit">${echapper(r.acces)}</span></div>`).join("");
  $("#c-domaines").innerHTML = (P.domaines || []).map((d) => `<label><input type="checkbox" value="${d}">${d.replace("_", " ")}</label>`).join("");
  $("#k-situations").innerHTML = Object.entries(P.situations).map(([k, v]) => `<div class="carte"><h4>${echapper(v.split(":")[0])}</h4><div class="petit">${echapper(v.split(":").slice(1).join(":"))}</div><button data-situation="${k}">Jouer</button></div>`).join("");
  $$("#k-situations [data-situation]").forEach((b) => (b.onclick = () => jouerSituation(b.dataset.situation)));
  grilleAuto(P.grille);
  await Formation.charger();
}
function remplirSelect(sel, valeurs, libelle = (v) => v) {
  sel.innerHTML = valeurs.map((v) => `<option value="${echapper(v)}">${echapper(libelle(v))}</option>`).join("");
}

/* ══════════ Arrêt d'urgence, incarnation, onglets ══════════ */
$("#btn-arret").onclick = () => { Voix.annuler(); Repetition.pause(true); envoyer("estop", { motif: "bouton ARRÊT (partenaire)" }); };
$("#btn-rearmer").onclick = () => envoyer("rearmer");
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.preventDefault(); Voix.annuler(); Repetition.pause(true); envoyer("estop", { motif: "touche Échap (partenaire)" }); return; }
  if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;
  if (Repetition.actif) {
    if (e.key === "Enter" || e.key === "ArrowRight") { e.preventDefault(); Repetition.repliqueDite(); }
    if (e.key.toLowerCase() === "s") { e.preventDefault(); Repetition.souffler(); }
  }
});
$("#incarnation").onchange = async (e) => {
  const r = await demander("p_incarnation", { actif: e.target.checked });
  e.target.checked = r.incarnation;
  toast(r.incarnation ? "Incarnation active : les gestes passent par la couche de sécurité du pont." : "Incarnation désactivée.", "info");
};
$$(".onglets [role=tab]").forEach((b) => (b.onclick = () => {
  $$(".onglets [role=tab]").forEach((x) => x.setAttribute("aria-selected", x === b));
  $$(".onglet").forEach((o) => (o.hidden = o.id !== "o-" + b.dataset.onglet));
}));

/* ══════════ Acteurs et consentements ══════════ */
const acteurCourant = () => $("#acteur-courant").value || null;
function majActeurs(liste) {
  if (P) P.acteurs = liste;
  const sel = $("#acteur-courant"), v = sel.value;
  sel.innerHTML = `<option value="">— aucun —</option>` + liste.map((a) => `<option value="${a.id}">${echapper(a.pseudonyme)}</option>`).join("");
  sel.value = liste.some((a) => a.id === v) ? v : "";
  $("#p-liste").innerHTML = liste.length ? liste.map((a) => `<div class="acteur-ligne"><span>${echapper(a.pseudonyme)} <span class="petit">· année ${a.annee_formation}</span></span><span class="petit">${Object.values(a.consentements).filter(Boolean).length}/4 consentements</span><button data-a="${a.id}">Ouvrir</button></div>`).join("") : `<p class="petit">Aucun acteur. Créez un pseudonyme pour conserver les traces de formation et de répétition.</p>`;
  $$("#p-liste [data-a]").forEach((b) => (b.onclick = () => { $("#acteur-courant").value = b.dataset.a; ouvrirActeur(); }));
}
$("#acteur-courant").onchange = () => ouvrirActeur();
$("#p-form").onsubmit = async (e) => {
  e.preventDefault();
  const p = $("#p-pseudo").value.trim(); if (!p) return;
  const r = await demander("p_acteur_creer", { pseudonyme: p, annee: +$("#p-annee").value });
  majActeurs(r.acteurs); $("#acteur-courant").value = r.acteur.id; $("#p-pseudo").value = ""; ouvrirActeur();
};
async function ouvrirActeur() {
  const id = acteurCourant();
  if (!id) { $("#p-qui").textContent = ""; $("#p-consent").innerHTML = `<p class="petit">Choisissez un acteur.</p>`; $("#p-historique").innerHTML = ""; return; }
  const { acteur } = await demander("p_acteur", { id });
  $("#p-qui").textContent = "— " + acteur.pseudonyme;
  $("#p-consent").innerHTML = Object.entries(P.consentements).map(([k, txt]) => `<label class="consentement"><input type="checkbox" data-c="${k}" ${acteur.consentements[k] ? "checked" : ""}><span>${echapper(txt)}${acteur.consentements[k] ? `<br><span class="date">accordé le ${echapper(acteur.consentements[k])}</span>` : ""}</span></label>`).join("") + `<p class="petit">Chaque consentement est révocable à tout moment ; sa révocation est horodatée.</p>`;
  $$("#p-consent [data-c]").forEach((c) => (c.onchange = async () => { const r = await demander("p_consentir", { acteur: id, cle: c.dataset.c, accorde: c.checked }); majActeurs(r.acteurs); ouvrirActeur(); }));
  const ex = acteur.exercices.slice(-15).reverse().map((x) => `<li>${echapper(x.ts.slice(0, 10))} — ${echapper(x.exercice)}${x.note ? " : " + echapper(x.note) : ""}</li>`).join("");
  const ev = acteur.auto_evaluations.slice(-4).reverse().map((x) => `<li>${echapper(x.ts.slice(0, 10))} — ${Object.entries(x.notes).map(([k, v]) => `${echapper(k)} ${v}`).join(" · ")}</li>`).join("");
  $("#p-historique").innerHTML = `<b>Exercices</b><ul>${ex || "<li>—</li>"}</ul><b>Auto-évaluations</b><ul>${ev || "<li>—</li>"}</ul>`;
}
$("#p-retirer").onclick = async () => {
  const id = acteurCourant(); if (!id) return;
  if (!confirm("Effacer définitivement le profil, les consentements et toutes les traces de cet acteur ?")) return;
  const r = await demander("p_acteur_retirer", { id }); majActeurs(r.acteurs); ouvrirActeur();
};

/* ══════════ Robot virtuel : délégation de la voix et du visage (BroadcastChannel) ══════════ */
const Avatar = {
  canal: "BroadcastChannel" in window ? new BroadcastChannel("robo-scene-avatar") : null,
  vu: 0, jeton: 0, attentes: new Map(),
  init() {
    if (!this.canal) { $("#avatar-voix").disabled = true; return; }
    this.canal.onmessage = (ev) => {
      const m = ev.data || {};
      if (m.t === "pong") { this.vu = Date.now(); this.maj(); }
      if (m.t === "fini" && this.attentes.has(m.jeton)) { this.attentes.get(m.jeton)(); this.attentes.delete(m.jeton); }
    };
    try { $("#avatar-voix").checked = localStorage.getItem("robo-scene-avatar-voix-partenaire") === "1"; } catch (e) {}
    $("#avatar-voix").onchange = (e) => { try { localStorage.setItem("robo-scene-avatar-voix-partenaire", e.target.checked ? "1" : "0"); } catch (x) {} this.maj(); };
    setInterval(() => { this.canal.postMessage({ t: "ping" }); this.maj(); }, 2500);
    this.canal.postMessage({ t: "ping" });
  },
  present() { return Date.now() - this.vu < 6000; },
  actif() { return !!this.canal && $("#avatar-voix").checked && this.present(); },
  maj() {
    const el = $("#st-avatar"); if (!el) return;
    el.className = "pastille bascule " + (this.actif() ? "ok" : $("#avatar-voix").checked ? "avert" : "neutre");
    el.title = this.present() ? "Robot virtuel ouvert dans ce navigateur" : "Ouvrez la page « Robot virtuel » pour qu'il donne sa voix et son visage aux répliques";
  },
  dire(rendu, opts) {
    const jeton = ++this.jeton;
    return new Promise((fin) => {
      const garde = setTimeout(() => { this.attentes.delete(jeton); fin(); }, (rendu.duree_estimee_ms || 3000) * 2 + 4000);
      this.attentes.set(jeton, () => { clearTimeout(garde); fin(); });
      this.canal.postMessage({ t: "dire", jeton, rendu, volume: opts.volume, variation: opts.variation || null, nom: opts.nom || null });
    });
  },
  taire() { if (this.canal) this.canal.postMessage({ t: "taire" }); for (const f of this.attentes.values()) f(); this.attentes.clear(); },
};
Avatar.init();

/* ══════════ Voix : synthèse, voix machinique, signal tonal ══════════ */
const Voix = {
  voix: [], jeton: 0, audio: null,
  charger() {
    const lire = () => { this.voix = (speechSynthesis.getVoices() || []).filter((v) => v.lang && v.lang.toLowerCase().startsWith("fr")); };
    if ("speechSynthesis" in window) { lire(); speechSynthesis.onvoiceschanged = lire; }
  },
  pour(index) {
    if (!this.voix.length) return null;
    const ca = this.voix.filter((v) => /fr-ca/i.test(v.lang));
    const pool = ca.length && index === 0 ? ca : this.voix;
    return pool[index % pool.length];
  },
  annuler() {
    this.jeton++;
    Avatar.taire();
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    if (this.audio) { try { this.audio.close(); } catch (e) {} this.audio = null; }
  },
  /* rendu : {parler, debit, hauteur, volume, segments[{texte, pause_apres_ms}], duree_estimee_ms} */
  async dire(rendu, { indexVoix = 0, tonale = false, volume = null, variation = null, nom = null } = {}) {
    const j = ++this.jeton;
    if (!tonale && Avatar.actif()) { await Avatar.dire(rendu, { volume, variation, nom }); return; }   // le robot virtuel parle
    if (!rendu.parler) { await attendre(rendu.duree_estimee_ms); return; }     // film muet : le texte s'affiche, le corps joue
    if (tonale) return this.tonale(rendu, j);
    const dispo = "speechSynthesis" in window && this.voix.length;
    for (const seg of rendu.segments) {
      if (j !== this.jeton) return;
      if (dispo) {
        await new Promise((fin) => {
          const u = new SpeechSynthesisUtterance(seg.texte);
          u.lang = "fr-CA"; const v = this.pour(indexVoix); if (v) u.voice = v;
          u.rate = rendu.debit; u.pitch = rendu.hauteur; u.volume = volume ?? rendu.volume;
          const garde = setTimeout(fin, 1500 + seg.texte.length * 120 / rendu.debit);
          u.onend = u.onerror = () => { clearTimeout(garde); fin(); };
          speechSynthesis.speak(u);
        });
      } else {
        await attendre(Math.max(300, seg.texte.split(/\s+/).length * 330 / rendu.debit));   // repli : temps estimé
      }
      if (seg.pause_apres_ms) await attendre(seg.pause_apres_ms);
    }
  },
  /* Voie non anthropomorphe : une impulsion sonore par syllabe ; le rythme suit l'effort de temps,
     l'enveloppe suit le flux (contenu = détaché, libre = lié), la hauteur glisse selon l'espace. */
  async tonale(rendu, j) {
    const ctx = new (window.AudioContext || window.webkitAudioContext)(); this.audio = ctx;
    const e = rendu.effort || { poids: 0, temps: 0, espace: 0, flux: 0 };
    const base = 180 + 60 * (e.poids + 1);
    let t = ctx.currentTime + 0.05;
    for (const seg of rendu.segments) {
      const syl = Math.max(1, (seg.texte.match(/[aeiouyàâéèêëîïôûùü]+/gi) || []).length);
      const d = 0.16 / rendu.debit;
      for (let k = 0; k < syl; k++) {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type = e.poids > 0.3 ? "square" : "sine";
        const f = base * (1 + 0.08 * Math.sin(k * (e.espace >= 0 ? 0.3 : 1.7)));
        o.frequency.setValueAtTime(f, t);
        if (e.espace < 0) o.frequency.linearRampToValueAtTime(f * 1.12, t + d);
        const lie = e.flux < 0 ? 0.95 : 0.55;
        g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(0.12 * rendu.volume, t + 0.01);
        g.gain.linearRampToValueAtTime(0, t + d * lie);
        o.connect(g).connect(ctx.destination); o.start(t); o.stop(t + d);
        t += d;
      }
      t += seg.pause_apres_ms / 1000;
    }
    const total = (t - ctx.currentTime) * 1000;
    await attendre(total);
    if (j === this.jeton) { ctx.close(); this.audio = null; }
  },
};
Voix.charger();

/* ══════════ Écoute : détection d'activité vocale locale ══════════ */
const Micro = {
  ctx: null, an: null, buf: null, plancher: -60, muet: false, niveau: -100, actif: false,
  async demarrer() {
    if (this.actif) return true;
    try {
      const flux = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      const src = this.ctx.createMediaStreamSource(flux);
      this.an = this.ctx.createAnalyser(); this.an.fftSize = 1024; src.connect(this.an);
      this.buf = new Float32Array(this.an.fftSize); this.actif = true;
      const echant = [];
      const boucle = () => {
        if (!this.actif) return;
        this.an.getFloatTimeDomainData(this.buf);
        let s = 0; for (const x of this.buf) s += x * x;
        this.niveau = 10 * Math.log10(s / this.buf.length + 1e-12);
        if (echant.length < 40) { echant.push(this.niveau); if (echant.length === 40) this.plancher = [...echant].sort((a, b) => a - b)[20]; }
        $("#r-niveau-micro").style.width = Math.max(0, Math.min(100, (this.niveau + 70) * 1.6)) + "%";
        setTimeout(boucle, 30);
      };
      boucle();
      return true;
    } catch (err) { toast("Micro indisponible : " + err.message + " — passage en mode manuel."); return false; }
  },
  seuil() { return Math.max(this.plancher + 9, -55); },
  /* Écoute d'une réplique : résout {debut, fin, pauses_ms[], rms_db, rms_db_max} ou null (fin manuelle) */
  ecouter(silenceFinMs, surDebut) {
    let annule = false, finManuelle = null;
    const p = new Promise((ok) => {
      const t0 = performance.now();
      let debut = null, dernierSon = null, enSilence = null, pauses = [], somme = 0, n = 0, max = -100;
      const boucle = () => {
        if (annule) return ok(null);
        const now = performance.now();
        if (finManuelle) return ok(debut ? { debut: debut - t0, fin: now - t0, pauses_ms: pauses, rms_db: n ? somme / n : null, rms_db_max: n ? max : null, manuel: true } : null);
        const parle = !this.muet && this.niveau > this.seuil();
        if (parle) {
          if (debut === null) { debut = now; surDebut && surDebut(); }
          if (enSilence !== null && now - enSilence >= 250) pauses.push(Math.round(now - enSilence));
          enSilence = null; dernierSon = now; somme += this.niveau; n++; max = Math.max(max, this.niveau);
        } else if (debut !== null) {
          if (enSilence === null) enSilence = now;
          if (now - enSilence >= silenceFinMs) return ok({ debut: debut - t0, fin: dernierSon - t0, pauses_ms: pauses, rms_db: n ? somme / n : null, rms_db_max: n ? max : null });
        }
        setTimeout(boucle, 30);
      };
      boucle();
    });
    p.annuler = () => (annule = true);
    p.terminer = () => (finManuelle = true);
    return p;
  },
};

/* Transcription facultative (consentement « transcription ») */
const Transcription = {
  rec: null, texte: "",
  disponible() { return !!(window.SpeechRecognition || window.webkitSpeechRecognition); },
  demarrer() {
    const R = window.SpeechRecognition || window.webkitSpeechRecognition; if (!R) return;
    this.texte = ""; this.rec = new R(); this.rec.lang = "fr-CA"; this.rec.continuous = true; this.rec.interimResults = false;
    if ("processLocally" in this.rec) this.rec.processLocally = true;   // traitement local exigé là où le navigateur le permet
    this.rec.onresult = (e) => { for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) this.texte += " " + e.results[i][0].transcript; };
    this.rec.onerror = (e) => { if (e.error === "language-not-supported" && this.rec.processLocally) toast("Transcription locale indisponible pour le français dans ce navigateur."); };
    try { this.rec.start(); } catch (e) {}
  },
  arreter() { if (this.rec) { try { this.rec.stop(); } catch (e) {} } return this.texte.trim(); },
};

/* Caméra facultative : estimation de pose locale (MediaPipe), aucune image conservée */
const Camera = {
  pret: false, video: null, poseur: null, images: [], enregistre: false,
  async demarrer() {
    if (this.pret) return true;
    try {
      const V = await import("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs");
      const fichiers = await V.FilesetResolver.forVisionTasks("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm");
      this.poseur = await V.PoseLandmarker.createFromOptions(fichiers, {
        baseOptions: { modelAssetPath: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task" },
        runningMode: "VIDEO", numPoses: 1 });
      this.video = document.createElement("video"); this.video.muted = true; this.video.playsInline = true;
      this.video.srcObject = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
      await this.video.play(); this.pret = true;
      const boucle = () => {
        if (!this.pret) return;
        if (this.enregistre && this.video.readyState >= 2) {
          const r = this.poseur.detectForVideo(this.video, performance.now());
          const l = r.landmarks && r.landmarks[0];
          if (l) this.images.push({ t: performance.now() / 1000, points: { nez: [l[0].x, l[0].y], poignet_g: [l[15].x, l[15].y], poignet_d: [l[16].x, l[16].y], hanche_g: [l[23].x, l[23].y], hanche_d: [l[24].x, l[24].y] } });
        }
        setTimeout(boucle, 66);
      };
      boucle();
      return true;
    } catch (err) { toast("Caméra ou modèle de pose indisponible : " + err.message); return false; }
  },
  debut() { this.images = []; this.enregistre = true; },
  fin() { this.enregistre = false; const i = this.images; this.images = []; return i; },
};

/* ══════════ Formation ══════════ */
const Formation = {
  sommaire: [], donnees: null, courant: null, guide: null,
  async charger() {
    this.donnees = await demander("p_livret");
    this.sommaire = this.donnees.exercices;
    $("#livret-source").textContent = `— ${this.sommaire.length} exercices`;
    this.lister(); this.calendrier();
  },
  lister() {
    const a = +$("#f-annee").value, q = $("#f-cherche").value.trim().toLowerCase();
    const ex = this.sommaire.filter((e) => e.annee === a && (!q || (e.titre + " " + e.objectif).toLowerCase().includes(q)));
    let chap = null, html = "";
    for (const e of ex) {
      if (e.chapitre !== chap) { chap = e.chapitre; html += `<div class="chap">Chapitre ${e.chapitre} — ${echapper(e.titre_chapitre)}</div>`; }
      html += `<button data-ex="${e.id}">${e.numero} · ${echapper(e.titre)}<span class="duree">${e.duree_min ?? "?"} min</span></button>`;
    }
    $("#f-liste").innerHTML = html || `<p class="petit">Aucun exercice.</p>`;
    $$("#f-liste [data-ex]").forEach((b) => (b.onclick = () => this.ouvrir(b.dataset.ex)));
  },
  calendrier() {
    const a = $("#f-annee").value, cal = (this.donnees.calendriers || {})[a] || [];
    $("#f-calendrier").innerHTML = cal.length ? cal.map((c) => `<p><b>Semaines ${c.semaines[0]}–${c.semaines[1]} · ${echapper(c.theme)}</b><br>${echapper(c.description)}</p>`).join("") : "Le livret ne détaille pas de calendrier pour cette année.";
  },
  async ouvrir(id) {
    const r = await demander("p_exercice", { id });
    const e = r.exercice; this.courant = { ...e, accompagnement: r.accompagnement };
    $$("#f-liste [data-ex]").forEach((b) => b.classList.toggle("actif", b.dataset.ex === id));
    $("#f-fiche").className = "fiche";
    $("#f-fiche").innerHTML = `<div class="petit">Année ${e.annee} · chapitre ${e.chapitre} · exercice ${e.numero}</div><h3>« ${echapper(e.titre)} »</h3>
      <div class="mono petit">${e.duree_min ?? "?"} minutes · accompagnement du robot : ${echapper(r.accompagnement)}</div>
      <div class="objectif">${echapper(e.objectif)}</div>
      ${e.justification.map((p) => `<p class="petit">${echapper(p)}</p>`).join("")}
      <h3 style="font-size:14px">Déroulement</h3>
      ${e.etapes.map((s, i) => `<div class="etape" data-i="${i}"><span class="num">${i + 1}</span><span>${echapper(s.texte)}</span><span class="minuteur">${s.minutes ? s.minutes + ":00" : ""}</span></div>`).join("")}
      ${e.variantes.length ? `<h3 style="font-size:14px">Variantes</h3>` + e.variantes.map((v) => `<p class="petit">${echapper(v)}</p>`).join("") : ""}
      ${e.note ? `<div class="note">Note pédagogique : ${echapper(e.note)}</div>` : ""}
      ${e.citations.map((c) => `<p class="petit">${echapper(c)}</p>`).join("")}
      <div class="ligne"><button id="f-guider" class="primaire">Guider l'exercice</button><button id="f-stop">Arrêter</button><input id="f-note" placeholder="Note après l'exercice"><button id="f-fait">Marquer comme fait</button></div>
      <div class="source">Texte du livret restitué tel quel (${echapper(r.agent_name)}). Les références citées dans le livret n'ont pas été revérifiées par l'outil.</div>`;
    $("#f-guider").onclick = () => this.guider();
    $("#f-stop").onclick = () => this.arreter();
    $("#f-fait").onclick = async () => {
      if (!acteurCourant()) return toast("Choisissez d'abord un acteur.");
      await demander("p_exercice_noter", { acteur: acteurCourant(), id: e.id, note: $("#f-note").value }); toast("Exercice consigné.", "info"); $("#f-note").value = "";
    };
  },
  async guider() {
    const e = this.courant; if (!e) return;
    this.arreter(); const jeton = (this.guide = {});
    if ($("#incarnation").checked) envoyer("p_accompagner", { mode: e.accompagnement, cycles: 8 });
    for (const [i, s] of e.etapes.entries()) {
      if (this.guide !== jeton) return;
      $$("#f-fiche .etape").forEach((x) => x.classList.toggle("active", +x.dataset.i === i));
      await Voix.dire(rendreSimple(s.texte), { indexVoix: 0 });
      const ms = (s.minutes || 0) * 60000, t0 = performance.now(), cell = $(`#f-fiche .etape[data-i="${i}"] .minuteur`);
      while (ms && performance.now() - t0 < ms) {
        if (this.guide !== jeton) return;
        const r = Math.ceil((ms - (performance.now() - t0)) / 1000);
        cell.textContent = `${Math.floor(r / 60)}:${String(r % 60).padStart(2, "0")}`;
        await attendre(250);
      }
    }
    await Voix.dire(rendreSimple("Fin de l'exercice. Prenez un temps pour noter ce que vous avez observé."));
  },
  arreter() { this.guide = null; Voix.annuler(); envoyer("p_accompagner", { mode: "stop" }); },
};
function rendreSimple(texte) {
  const segs = texte.split(/(?<=[.;:!?])\s+/).filter(Boolean).map((t) => ({ texte: t, pause_apres_ms: 350 }));
  return { parler: true, debit: 0.95, hauteur: 1, volume: 0.9, segments: segs, duree_estimee_ms: texte.length * 70 };
}
$("#f-annee").onchange = () => { Formation.lister(); Formation.calendrier(); };
$("#f-cherche").oninput = () => Formation.lister();
$("#f-planifier").onclick = async () => {
  const r = await demander("p_seance", { annee: +$("#f-annee").value, acteur: acteurCourant() });
  $("#f-plan").innerHTML = r.plan.map((p) => `<li><span class="role">${echapper(p.role)} · ${p.duree_min} min</span>${p.exercice ? `<a href="#" data-ex="${p.exercice}">${echapper(p.titre)}</a>` : echapper(p.titre)}</li>`).join("") ;
  if (!$("#f-plan-total")) $("#f-plan").insertAdjacentHTML("afterend", `<p class="petit" id="f-plan-total"></p>`);
  $("#f-plan-total").textContent = `Durée totale : ${r.duree_totale_min} min — ${r.regle}`;
  $$("#f-plan [data-ex]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); Formation.ouvrir(a.dataset.ex); }));
};
function grilleAuto(domaines) {
  $("#f-auto").innerHTML = domaines.map((d, i) => `<div class="ligne-eval"><span>${echapper(d)}</span><span class="notes">${[1, 2, 3, 4, 5].map((n) => `<label><input type="radio" name="g${i}" value="${n}">${n}</label>`).join("")}</span></div>`).join("") + `<textarea id="f-auto-com" rows="2" placeholder="Observations qualitatives"></textarea><button class="primaire">Enregistrer l'auto-évaluation</button>`;
  $("#f-auto").onsubmit = async (e) => {
    e.preventDefault(); if (!acteurCourant()) return toast("Choisissez d'abord un acteur.");
    const notes = {}; domaines.forEach((d, i) => { const r = $(`#f-auto input[name=g${i}]:checked`); if (r) notes[d] = +r.value; });
    await demander("p_auto_eval", { acteur: acteurCourant(), notes, commentaire: $("#f-auto-com").value }); toast("Auto-évaluation enregistrée.", "info");
  };
}

/* ══════════ Pièces : bibliothèque et répertoire ══════════ */
function majPieces(liste) {
  for (const sel of [$("#r-piece"), $("#v-piece"), $("#a-piece")]) {
    const v = sel.value;
    sel.innerHTML = liste.map((p) => `<option value="${p.id}">${echapper(p.titre)}${p.auteur ? " — " + echapper(p.auteur) : ""}</option>`).join("");
    if (liste.some((p) => p.id === v)) sel.value = v;
  }
  $("#t-biblio").innerHTML = liste.length ? `<table class="res"><tr><th>Pièce</th><th>Pers.</th><th>Sc.</th><th>Licence</th><th></th></tr>` + liste.map((p) => `<tr><td>${echapper(p.titre)}<br><span class="petit">${echapper(p.auteur)}</span></td><td>${p.personnages}</td><td>${p.scenes}</td><td class="petit">${echapper(p.licence || "—")}</td><td><button data-sup="${p.id}" class="discret">✕</button></td></tr>`).join("") + `</table>` : `<p class="petit">Aucune pièce.</p>`;
  $$("#t-biblio [data-sup]").forEach((b) => (b.onclick = async () => { if (confirm("Retirer cette pièce de la bibliothèque locale ?")) { const r = await demander("p_piece_supprimer", { id: b.dataset.sup }); cachePieces.delete(b.dataset.sup); majPieces(r.pieces); } }));
  if (liste.length) { chargerPiecePour("r"); chargerPiecePour("v"); remplirPersosAnalyse(); }
}
async function piece(id) {
  if (!cachePieces.has(id)) cachePieces.set(id, (await demander("p_piece", { id })).piece);
  return cachePieces.get(id);
}
async function chargerPiecePour(prefixe) {
  const id = $(`#${prefixe}-piece`).value; if (!id) return;
  const p = await piece(id);
  if (prefixe === "r") {
    remplirSelect($("#r-roles"), p.personnages.map((x) => x.id), (pid) => p.personnages.find((x) => x.id === pid).nom);
    $("#r-roles").selectedIndex = 0;
    remplirSelect($("#r-scenes"), p.scenes.map((s) => s.id), (sid) => { const s = p.scenes.find((x) => x.id === sid); return `${s.acte ? s.acte + " · " : ""}${s.titre}`.slice(0, 90); });
    $("#r-scenes").selectedIndex = 0;
    $("#r-licence").textContent = p.source && p.source.licence ? `Licence de l'édition numérique : ${p.source.licence}` : "";
  } else {
    const reps = p.elements.filter((e) => e.type === "replique");
    remplirSelect($("#v-replique"), reps.map((r) => r.id), (rid) => { const r = reps.find((x) => x.id === rid); return `${r.nom} : ${r.texte}`.slice(0, 80); });
    majTexteVariation();
  }
}
$("#r-piece").onchange = () => chargerPiecePour("r");
$("#v-piece").onchange = () => chargerPiecePour("v");

$("#d-form").onsubmit = async (e) => {
  e.preventDefault();
  const r = await demander("p_repertoire", { corpus: $("#d-corpus").value, texte: $("#d-texte").value, genre: $("#d-genre").value, hommes: $("#d-h").value, femmes: $("#d-f").value, min_perso: $("#d-min").value, max_perso: $("#d-max").value, annee_min: $("#d-a1").value, annee_max: $("#d-a2").value });
  const g = $("#d-genre").value; remplirSelect($("#d-genre"), [""].concat(r.genres), (x) => x || "tous"); $("#d-genre").value = g;
  $("#d-res").innerHTML = `<p class="petit">${r.total} pièce(s)${r.total > r.resultats.length ? ` — ${r.resultats.length} affichées` : ""}.</p><table class="res"><tr><th>Année</th><th>Titre</th><th>Auteur</th><th>Genre</th><th>H/F/total</th><th></th></tr>` +
    r.resultats.map((x) => `<tr><td>${x.yearNormalized ?? ""}</td><td>${echapper(x.title)}</td><td>${echapper(x.firstAuthor)}</td><td>${echapper(x.normalizedGenre || "")}</td><td class="mono">${x.numOfSpeakersMale ?? "?"}/${x.numOfSpeakersFemale ?? "?"}/${x.numOfSpeakers ?? "?"}</td><td><button data-imp="${x.name}">Importer</button></td></tr>`).join("") + `</table>`;
  $$("#d-res [data-imp]").forEach((b) => (b.onclick = async () => {
    b.disabled = true; b.textContent = "…";
    try { const r2 = await demander("p_importer_dracor", { corpus: r.corpus, nom: b.dataset.imp }); majPieces(r2.pieces); b.textContent = "Importée"; toast("Pièce importée dans la bibliothèque.", "info"); }
    catch (err) { b.disabled = false; b.textContent = "Importer"; }
  }));
};
$("#t-fichier").onchange = async (e) => {
  const f = e.target.files[0]; if (!f) return;
  if (!$("#t-titre").value) $("#t-titre").value = f.name.replace(/\.(txt|docx)$/i, "");
  if (/\.txt$/i.test(f.name)) $("#t-texte").value = await f.text();
};
$("#t-importer").onclick = async () => {
  const f = $("#t-fichier").files[0];
  let r;
  if (f && /\.docx$/i.test(f.name)) {
    const octets = new Uint8Array(await f.arrayBuffer());
    let bin = ""; for (let i = 0; i < octets.length; i += 0x8000) bin += String.fromCharCode.apply(null, octets.subarray(i, i + 0x8000));
    const b64 = btoa(bin);
    r = await demander("p_importer_docx", { titre: $("#t-titre").value, auteur: $("#t-auteur").value, contenu: b64 });
  } else {
    r = await demander("p_importer_texte", { titre: $("#t-titre").value, auteur: $("#t-auteur").value, texte: $("#t-texte").value });
  }
  majPieces(r.pieces); toast(`Importé : ${r.repliques} répliques, personnages ${r.personnages.join(", ")}.`, "info");
};

/* ══════════ Analyse de pièce ══════════ */
async function remplirPersosAnalyse() {
  const id = $("#a-piece").value; if (!id) return;
  const p = await piece(id);
  remplirSelect($("#a-perso"), p.personnages.map((x) => x.id), (pid) => p.personnages.find((x) => x.id === pid).nom);
}
$("#a-piece").onchange = remplirPersosAnalyse;
$("#a-analyser").onclick = async () => {
  $("#a-mode").textContent = "analyse…";
  const r = await demander("p_analyser", { id: $("#a-piece").value });
  const s = r.statistiques, v = s.vue;
  $("#a-mode").textContent = `${r.agent_name} · ${r.mode}${r.licence ? " · licence " + r.licence : ""}`;
  $("#a-vue").innerHTML = [["Scènes", v.scenes], ["Actes", v.actes], ["Répliques", v.repliques], ["Mots", v.mots], ["Personnages", v.personnages], ["Part en vers", Math.round(v.en_vers * 100) + " %"], ["Mots / réplique", v.mots_par_replique], ["Didascalies", v.didascalies]].map(([k, x]) => `<div class="tuile"><div class="etiq">${k}</div><div class="val">${x}</div></div>`).join("");
  $("#a-persos").innerHTML = s.personnages.map((p) => `<div class="barre-parole"><span>${echapper(p.nom)}</span><span class="jauge-p"><div style="width:${p.part_parole * 100}%"></div></span><span class="mono">${(p.part_parole * 100).toFixed(1)} %</span></div><div class="petit" style="margin:-2px 0 6px 128px">${p.repliques} réplique${p.repliques > 1 ? "s" : ""} · ${p.scenes} scène${p.scenes > 1 ? "s" : ""} · ${p.mots_par_replique} mots/réplique${p.genre ? " · " + ({ male: "homme", female: "femme", unknown: "genre non indiqué" }[p.genre] || p.genre) : ""}</div>`).join("");
  const ids = s.personnages.map((p) => p.id);
  $("#a-config").innerHTML = `<table class="config"><tr><th></th>${s.personnages.map((p) => `<th>${echapper(p.nom.slice(0, 10))}</th>`).join("")}</tr>` + s.configurations.map((c) => `<tr><th class="sc" title="${echapper(c.titre)}">${echapper(c.titre.slice(0, 40))}</th>${ids.map((id) => `<td class="${c.presents.includes(id) ? "on" : ""}"></td>`).join("")}</tr>`).join("") + `</table><p class="petit">${s.limites.map(echapper).join(" ")}</p>`;
  dessinerReseau(s.reseau);
  $("#a-rythme").innerHTML = `<b>${s.stichomythies.length} stichomythie(s)</b> (au moins 4 répliques brèves alternées)<ul>${s.stichomythies.slice(0, 12).map((x) => `<li>scène ${x.scene} : ${x.longueur} répliques (${x.debut}–${x.fin})</li>`).join("")}</ul><b>Tirades les plus longues</b><ul>${s.tirades.slice(0, 6).map((t) => `<li>${echapper(t.nom)} (${t.mots} mots, scène ${t.scene}) — « ${echapper(t.incipit)}… »</li>`).join("")}</ul>`;
  const it = r.interpretation;
  $("#a-interp").innerHTML = !it ? echapper(r.note || "—") : `<p><b>Fable.</b> ${echapper(it.fable)}</p><p><b>Modèle actantiel.</b> sujet : ${echapper(it.modele_actantiel?.sujet)} · objet : ${echapper(it.modele_actantiel?.objet)} · destinateur : ${echapper(it.modele_actantiel?.destinateur)} · destinataire : ${echapper(it.modele_actantiel?.destinataire)} · adjuvants : ${echapper((it.modele_actantiel?.adjuvants || []).join(", "))} · opposants : ${echapper((it.modele_actantiel?.opposants || []).join(", "))}</p>
    <p><b>Enjeux.</b></p><ul>${(it.enjeux || []).map((x) => `<li>${echapper(x)}</li>`).join("")}</ul><p><b>Pistes de jeu.</b></p><ul>${(it.pistes_de_jeu || []).map((x) => `<li>${echapper(x)}</li>`).join("")}</ul>
    <p><b>Partenaire robotique.</b></p><ul>${(it.partenaire_robotique || []).map((x) => `<li>${echapper(x)}</li>`).join("")}</ul>
    <p><b>Citations vérifiées dans le texte.</b></p><ul>${(it.citations || []).map((c) => `<li>« ${echapper(c.texte)} » (${c.replique}) — ${echapper(c.commentaire)}</li>`).join("")}</ul>${r.citations_retirees?.length ? `<p class="mode">${r.citations_retirees.length} citation(s) introuvable(s) dans la pièce, retirée(s).</p>` : ""}`;
};
function dessinerReseau(res) {
  const cv = $("#a-reseau"), ctx = cv.getContext("2d"), w = cv.width, h = cv.height;
  ctx.clearRect(0, 0, w, h);
  const n = res.noeuds.length, pos = {}, maxm = Math.max(...res.noeuds.map((x) => x.mots), 1), maxw = Math.max(...res.aretes.map((a) => a.scenes), 1);
  res.noeuds.forEach((x, i) => { const a = (2 * Math.PI * i) / n - Math.PI / 2; pos[x.id] = [w / 2 + (w * 0.36) * Math.cos(a), h / 2 + (h * 0.38) * Math.sin(a)]; });
  for (const a of res.aretes) { ctx.strokeStyle = `rgba(111,168,255,${0.25 + 0.6 * a.scenes / maxw})`; ctx.lineWidth = 1 + 5 * a.scenes / maxw; ctx.beginPath(); ctx.moveTo(...pos[a.a]); ctx.lineTo(...pos[a.b]); ctx.stroke(); }
  for (const x of res.noeuds) { const r = 5 + 18 * Math.sqrt(x.mots / maxm); ctx.fillStyle = "#f2b544"; ctx.beginPath(); ctx.arc(...pos[x.id], r, 0, 2 * Math.PI); ctx.fill(); ctx.fillStyle = "#e7e9ee"; ctx.font = "12px sans-serif"; ctx.textAlign = "center"; ctx.fillText(x.nom, pos[x.id][0], pos[x.id][1] + r + 14); }
  ctx.fillStyle = "#9aa3b2"; ctx.textAlign = "left"; ctx.fillText(`densité ${res.densite}`, 8, h - 8);
}
$("#a-fiche").onclick = async () => {
  const r = await demander("p_fiche", { id: $("#a-piece").value, perso: $("#a-perso").value }), f = r.fiche;
  $("#a-fiche-out").innerHTML = `<p><b>Première réplique</b> (${f.premiere_replique.id}) : « ${echapper(f.premiere_replique.texte)} »</p><p><b>Dernière réplique</b> (${f.derniere_replique.id}) : « ${echapper(f.derniere_replique.texte.slice(0, 400))} »</p>
    <p><b>Didascalies qui le concernent</b> : ${f.didascalies.map(echapper).join(" · ") || "—"}</p><p><b>Ce que les autres disent de lui ou d'elle</b></p><ul>${f.ce_que_les_autres_disent.map((x) => `<li>${echapper(x.nom)} : « ${echapper(x.texte.slice(0, 220))} »</li>`).join("") || "<li>—</li>"}</ul>
    <p><b>Questions de Stanislavski</b> : ${f.questions_stanislavski.map(echapper).join(" ")}</p><p><b>Quatre couches</b> : ${f.quatre_couches.map(echapper).join(" · ")}</p><p class="petit">${echapper(f.source_grille)} — les réponses reviennent à l'acteur.</p>`;
};

/* ══════════ Variations ══════════ */
async function majTexteVariation() {
  const p = await piece($("#v-piece").value), r = p.elements.find((e) => e.id === $("#v-replique").value);
  if (r) $("#v-texte").value = r.texte;
}
$("#v-replique").onchange = majTexteVariation;
$("#v-intensite").oninput = (e) => ($("#v-int-txt").textContent = e.target.value + "/10");
function variationComposee() {
  const v = { emotion: $("#v-emotion").value, intensite: +$("#v-intensite").value, melange: $("#v-melange").value || null, style: $("#v-style").value, source: "manuel" };
  if ($("#v-effort-libre").checked) { v.effort = {}; $$("#v-effort input[data-axe]").forEach((i) => (v.effort[i.dataset.axe] = +i.value)); v.etiquette = "qualité d'effort composée"; }
  return v;
}
$("#v-proposer").onclick = async () => {
  const p = $("#v-piece").value, rid = $("#v-replique").value;
  const r = await demander("p_variations", { piece: p, replique: rid });
  const ind = r.indices.candidats.map((c) => `${c.emotion} (${c.score})${c.preuves.length ? " : " + c.preuves.map(echapper).join(", ") : ""}`).join(" · ");
  $("#v-indices").innerHTML = `<b>${echapper(r.personnage)}</b> — indices relevés : ${ind || "aucun"} <span class="mode">${echapper(r.agent_name)} · ${echapper(r.mode)}</span>`;
  $("#v-props").innerHTML = r.propositions.map((v, i) => `<div class="carte"><h4>${echapper(v.etiquette)}</h4><div class="mono petit">${echapper(v.emotion)}${v.melange ? " + " + echapper(v.melange) : ""} · ${v.intensite}/10 · ${echapper(v.style)}${v.source === "claude" ? (v.indice_verifie ? " · indice vérifié" : " · indice non retrouvé") : ""}</div><div class="petit">${echapper(v.justification)}</div><button data-v="${i}">Charger</button></div>`).join("");
  $$("#v-props [data-v]").forEach((b) => (b.onclick = () => { const v = r.propositions[+b.dataset.v]; $("#v-emotion").value = v.emotion; $("#v-melange").value = v.melange || ""; $("#v-intensite").value = v.intensite; $("#v-int-txt").textContent = v.intensite + "/10"; $("#v-style").value = v.style; $("#v-effort-libre").checked = false; apercu(false); }));
};
async function apercu(jouer) {
  const texte = $("#v-texte").value.trim(); if (!texte) return;
  const r = await demander("p_rendu", { texte, variation: variationComposee(), regime: $("#v-regime").value, jouer, graine: $("#v-replique").value });
  $("#v-desc").textContent = `effort ${JSON.stringify(r.description.effort)} · voix débit ${r.voix.debit}, hauteur ${r.voix.hauteur}, volume ${r.voix.volume}${r.joue ? " · geste joué" : jouer ? " · incarnation désactivée" : ""}`;
  dessinerGeste(r.geste);
  return r;
}
$("#v-ecouter").onclick = async () => { const r = await apercu(false); if (r) Voix.dire({ ...r.voix, effort: r.description.effort }, { variation: variationComposee(), tonale: $("#v-regime").value === "machinique" && $("#r-voixmach").value === "tonale" }); };
$("#v-incarner").onclick = async () => { const r = await apercu(true); if (r) Voix.dire({ ...r.voix, effort: r.description.effort }, { variation: variationComposee(), tonale: $("#v-regime").value === "machinique" && $("#r-voixmach").value === "tonale" }); };
function dessinerGeste(images) {
  const cv = $("#v-geste"), ctx = cv.getContext("2d"), w = cv.width, h = cv.height;
  ctx.clearRect(0, 0, w, h);
  const total = images.reduce((s, i) => s + i.ms, 0) || 1, nj = images[0]?.deg.length || 0, coul = ["#f2b544", "#6fa8ff", "#4cc38a", "#ff7eb6"];
  for (let j = 0; j < nj; j++) {
    ctx.strokeStyle = coul[j % 4]; ctx.lineWidth = 2; ctx.beginPath();
    let t = 0; ctx.moveTo(4, h - 8 - (90 / 180) * (h - 16));
    for (const im of images) { t += im.ms; ctx.lineTo(4 + (w - 8) * t / total, h - 8 - (im.deg[j] / 180) * (h - 16)); }
    ctx.stroke();
  }
  ctx.fillStyle = "#9aa3b2"; ctx.font = "11px sans-serif"; ctx.fillText(`geste : ${images.length} images · ${(total / 1000).toFixed(1)} s (angles 0–180°)`, 8, 14);
}

/* ══════════ Répétiteur ══════════ */
const NIVEAUX = ["texte entier", "initiales", "premier mot", "texte masqué (réplique de mémoire)"];
$("#r-niveau").oninput = (e) => ($("#r-niveau-txt").textContent = NIVEAUX[e.target.value]);
const Repetition = {
  actif: false, plan: null, i: 0, enPause: false, ecoute: null, souffles: 0, finCue: 0, options: {},
  async demarrer() {
    const roles = $$("#r-roles option:checked").map((o) => o.value), scenes = $$("#r-scenes option:checked").map((o) => o.value);
    const acteur = acteurCourant();
    const consent = acteur ? (P.acteurs.find((a) => a.id === acteur)?.consentements || {}) : {};
    this.options = { micro: $("#r-micro").checked, stt: $("#r-stt").checked && !!consent.transcription && Transcription.disponible(),
      camera: $("#r-camera").checked && !!consent.camera, didas: $("#r-didas").checked,
      tonale: $("#r-regime").value === "machinique" && $("#r-voixmach").value === "tonale" };
    if ($("#r-stt").checked && !consent.transcription) toast("Transcription désactivée : consentement « transcription » absent pour cet acteur.");
    if ($("#r-camera").checked && !consent.camera) toast("Caméra désactivée : consentement « caméra » absent pour cet acteur.");
    if (acteur && !consent.mesures_vocales) toast("Sans consentement « mesures vocales », ce passage ne sera pas conservé.");
    this.plan = await demander("p_repet_demarrer", { piece: $("#r-piece").value, roles, scenes, niveau: +$("#r-niveau").value, souffleur_delai_s: +$("#r-souffleur").value,
      variation_mode: $("#r-varmode").value, regime: $("#r-regime").value, style: $("#r-style").value, consignes: $("#r-consignes").checked, acteur });
    if (this.options.micro) this.options.micro = await Micro.demarrer();
    if (this.options.camera) this.options.camera = await Camera.demarrer();
    this.actif = true; this.i = 0; this.enPause = false; this.finCue = performance.now();
    $("#r-etat").textContent = `passage n° ${this.plan.passage} · ${this.plan.titre}`;
    ["#r-suivante", "#r-souffle", "#r-pause", "#r-arreter"].forEach((s) => ($(s).disabled = false));
    $("#r-demarrer").disabled = true; $("#r-retour").textContent = "—";
    this.boucle();
  },
  async boucle() {
    const persos = [...new Set(this.plan.items.filter((x) => x.type === "replique" && !x.acteur).map((x) => x.perso))];
    while (this.actif && this.i < this.plan.items.length) {
      if (this.enPause) { await attendre(200); continue; }
      const it = this.plan.items[this.i];
      if (it.type === "didascalie") {
        $("#r-precedent").innerHTML = `<span class="didascalie">(${echapper(it.texte)})</span>`;
        if (this.options.didas) await Voix.dire(rendreSimple(it.texte), { indexVoix: 1, volume: 0.55 }); else await attendre(700);
        this.finCue = performance.now();
      } else if (!it.acteur) {
        $("#r-courant").className = "replique-acteur attente";
        $("#r-precedent").innerHTML = `<span class="nom">${echapper(it.nom)} · ${echapper(it.variation.etiquette)}</span>${echapper(it.texte)}${it.didascalies.length ? ` <span class="didascalie">(${it.didascalies.map(echapper).join(" ; ")})</span>` : ""}`;
        Micro.muet = true;
        envoyer("p_repet_geste", { replique: it.id, variation: it.variation, duree_ms: it.voix.duree_estimee_ms });
        await Voix.dire({ ...it.voix, effort: it.effort }, { indexVoix: 1 + persos.indexOf(it.perso), tonale: this.options.tonale, variation: it.variation, nom: it.nom });
        await attendre(150); Micro.muet = false;
        this.finCue = performance.now();
      } else {
        await this.repliqueActeur(it);
      }
      if (!this.enPause) this.i++;
    }
    if (this.actif) this.terminer(false);
  },
  async repliqueActeur(it) {
    this.souffles = 0; this.souffleEnCours = false;
    $("#r-courant").className = "replique-acteur";
    $("#r-courant").innerHTML = `<span class="nom">${echapper(it.nom)} — à vous</span>${echapper(it.affiche)}`;
    $("#r-consigne").textContent = it.consigne ? `Consigne : ${it.consigne}` : "";
    if (this.options.stt) Transcription.demarrer();
    if (this.options.camera) Camera.debut();
    const t0 = this.finCue;
    let aParle = false;
    const minuteur = setInterval(() => {
      if (!aParle && !this.enPause && performance.now() - t0 > this.plan.souffleur_delai_s * 1000 * (this.souffles + 1)) this.souffler();
    }, 200);
    let res = null;
    if (this.options.micro) {
      this.ecoute = Micro.ecouter(this.plan.fin_replique_silence_ms, () => (aParle = true));
      res = await this.ecoute;
    } else {
      res = await new Promise((ok) => (this.attenteManuelle = ok));
    }
    clearInterval(minuteur); this.ecoute = null;
    if (!this.actif || this.enPause) { if (this.options.stt) Transcription.arreter(); return; }
    const transcription = this.options.stt ? Transcription.arreter() : null;
    const decalage = performance.now() - t0;
    const mesure = res && !res.manuel_simple ? { latence_ms: Math.round(res.debut), duree_ms: Math.round(res.fin - res.debut), pauses_ms: res.pauses_ms, rms_db: res.rms_db, rms_db_max: res.rms_db_max, mode_fin: res.manuel ? "manuel" : "detection" }
      : { latence_ms: null, duree_ms: Math.round(decalage), pauses_ms: [], mode_fin: "manuel" };
    const r = await demander("p_repet_mesure", { repetition: this.plan.repetition, replique: it.id, souffles: this.souffles, transcription, ...mesure });
    if (this.options.camera) { const images = Camera.fin(); if (images.length > 8) envoyer("p_mouvement", { replique: it.id, images }); }
    const m = r.mesure;
    $("#r-mesure").textContent = `${it.id} · reprise ${m.latence_ms != null ? (m.latence_ms / 1000).toFixed(2) + " s" : "—"} · durée ${m.duree_ms ? (m.duree_ms / 1000).toFixed(1) + " s" : "—"} · débit ${m.debit_syl_s ?? "—"} syl/s · pauses ${m.pauses} · souffleur ${m.souffles}${m.texte ? " · fidélité " + Math.round(m.texte.precision * 100) + " %" : ""}`;
    $("#r-courant").innerHTML = `<span class="nom">${echapper(it.nom)}</span>${echapper(suite(it.souffle))}`;
    this.finCue = performance.now();
  },
  repliqueDite() {
    if (this.ecoute) this.ecoute.terminer();
    else if (this.attenteManuelle) { const ok = this.attenteManuelle; this.attenteManuelle = null; ok({ manuel_simple: true }); }
  },
  async souffler() {
    const it = this.plan?.items[this.i]; if (!it || !it.acteur || this.souffleEnCours) return;
    this.souffleEnCours = true; this.souffles++;
    Micro.muet = true;
    if (this.souffles >= 2) $("#r-courant").innerHTML = `<span class="nom">${echapper(it.nom)} — souffleur</span>${echapper(suite(it.souffle))}`;
    await Voix.dire(rendreSimple(it.souffle), { indexVoix: 0, volume: 0.45 });
    await attendre(120); Micro.muet = false; this.souffleEnCours = false;
  },
  pause(forcer = false) {
    if (!this.actif) return;
    this.enPause = forcer ? true : !this.enPause;
    $("#r-pause").textContent = this.enPause ? "Reprendre" : "Pause";
    if (this.enPause) { Voix.annuler(); if (this.ecoute) this.ecoute.annuler(); if (this.attenteManuelle) { const ok = this.attenteManuelle; this.attenteManuelle = null; ok(null); } }
  },
  async terminer(interrompu = true) {
    if (!this.actif) return;
    this.actif = false; Voix.annuler(); if (this.ecoute) this.ecoute.annuler();
    if (this.attenteManuelle) { this.attenteManuelle(null); this.attenteManuelle = null; }
    ["#r-suivante", "#r-souffle", "#r-pause", "#r-arreter"].forEach((s) => ($(s).disabled = true));
    $("#r-demarrer").disabled = false; $("#r-pause").textContent = "Pause";
    const r = await demander("p_repet_terminer", { interrompu });
    const s = r.passage.synthese, ret = r.retour;
    $("#r-etat").textContent = interrompu ? "passage interrompu" : "passage terminé";
    $("#r-retour").innerHTML = `<ul>${ret.observations.map((o) => `<li>${echapper(o)}</li>`).join("")}</ul>${ret.erreurs_texte.length ? `<b>Écarts au texte</b><ul>${ret.erreurs_texte.map(([id, t]) => `<li>${id} : ${t.omissions.length ? "omis « " + t.omissions.map(echapper).join(" / ") + " »" : ""} ${t.substitutions.map((x) => `« ${echapper(x.attendu)} » → « ${echapper(x.dit)} »`).join(" ; ")}</li>`).join("")}</ul>` : ""}<p class="petit">${r.conserve ? "Passage conservé dans les traces de l'acteur." : "Passage non conservé (aucun acteur choisi ou consentement absent)."} ${echapper(ret.avertissement)}</p>`;
    if (r.trajectoire) dessinerTrajectoire(r.trajectoire);
  },
};
$("#r-demarrer").onclick = () => Repetition.demarrer().catch((e) => toast(e.message));
$("#r-suivante").onclick = () => Repetition.repliqueDite();
$("#r-souffle").onclick = () => Repetition.souffler();
$("#r-pause").onclick = () => Repetition.pause();
$("#r-arreter").onclick = () => Repetition.terminer(true);
function dessinerTrajectoire(t) {
  const cv = $("#r-trajectoire"), ctx = cv.getContext("2d"), w = cv.width, h = cv.height, n = t.passages;
  ctx.clearRect(0, 0, w, h);
  const serie = (vals, coul, max, etiq, k) => {
    ctx.strokeStyle = coul; ctx.fillStyle = coul; ctx.lineWidth = 2; ctx.beginPath(); let premier = true;
    vals.forEach((v, i) => { if (v == null) return; const x = 30 + (w - 50) * (n > 1 ? i / (n - 1) : 0.5), y = h - 24 - (h - 44) * Math.min(1, v / max); premier ? ctx.moveTo(x, y) : ctx.lineTo(x, y); premier = false; ctx.fillRect(x - 2, y - 2, 4, 4); });
    ctx.stroke(); ctx.font = "11px sans-serif"; ctx.fillText(etiq, 30 + k * 190, 14);
  };
  const mx = Math.max(500, ...t.latence_mediane.filter((x) => x != null), ...t.dispersion.filter((x) => x != null));
  serie(t.latence_mediane, "#f2b544", mx, "reprise médiane (ms)", 0);
  serie(t.dispersion, "#6fa8ff", mx, "dispersion (ms)", 1);
  serie(t.souffles, "#ff7eb6", Math.max(3, ...t.souffles), "appels au souffleur", 2);
  ctx.fillStyle = "#9aa3b2"; for (let i = 0; i < n; i++) ctx.fillText(String(i + 1), 28 + (w - 50) * (n > 1 ? i / (n - 1) : 0.5), h - 6);
  $("#r-lecture").innerHTML = t.lecture.map((l) => `<p>${echapper(l)}</p>`).join("") + `<p>${echapper(t.avertissement)}</p>`;
}

/* ══════════ Conseiller ══════════ */
$("#c-form").onsubmit = async (e) => {
  e.preventDefault();
  const q = $("#c-question").value.trim(); if (!q) return;
  $("#c-reponse").innerHTML = `<p class="petit">Recherche…</p>`;
  const r = await demander("p_question", { texte: q, domaines: $$("#c-domaines input:checked").map((i) => i.value) });
  const texte = echapper(r.reponse).replace(/\[(K\d{5})\]/g, `<a href="#src-$1">[$1]</a>`);
  $("#c-reponse").innerHTML = `<div class="mode">${echapper(r.agent_name)} · ${echapper(r.mode)}${r.references_retirees?.length ? ` · ${r.references_retirees.length} référence(s) inconnue(s) retirée(s)` : ""}</div><div class="texte">${texte}</div>` +
    r.sources.map((s) => `<details id="src-${s.id}" ${r.mode === "extractif" && r.citations.includes(s.id) ? "open" : ""}><summary>[${s.id}] ${echapper(s.reference)}</summary><p class="petit">${echapper(s.extrait)}…</p></details>`).join("");
};

/* ══════════ Coprésence (régie) ══════════ */
$("#k-type").onclick = async () => { const r = await demander("p_cop_plan_type"); $("#k-plan").value = JSON.stringify(r.plan, null, 2); };
$("#k-sceller").onclick = async () => {
  let plan; try { plan = JSON.parse($("#k-plan").value); } catch (e) { return toast("Plan illisible : JSON invalide."); }
  const r = await demander("p_cop_sceller", { plan });
  $("#k-empreinte").value = r.empreinte; $("#k-plan").value = ""; $("#k-plan").placeholder = "Plan scellé — contenu masqué jusqu'au descellement.";
  toast("Plan scellé ; empreinte inscrite au journal de séance.", "info");
};
$("#k-desceller").onclick = async () => {
  const r = await demander("p_cop_desceller", { empreinte: $("#k-empreinte").value.trim() });
  $("#k-descelle").textContent = `${r.integre ? "✔ empreinte vérifiée" : "✘ EMPREINTE NON CONCORDANTE"} — scellé le ${r.scelle_le}\n` + JSON.stringify(r.plan, null, 2);
};
async function jouerSituation(s) {
  if (!$("#incarnation").checked) toast("Incarnation désactivée : la situation est consignée mais le robot ne bouge pas.");
  const r = await demander("p_cop_jouer", { situation: s, duree_s: +$("#k-duree").value, tempo: +$("#k-tempo").value, empreinte: $("#k-empreinte").value.trim() || null });
  $("#k-etat").textContent = `${r.description} — ${r.duree_s} s ${r.joue ? "(robot)" : "(non incarnée)"}`;
}
$("#k-stop").onclick = () => envoyer("p_accompagner", { mode: "stop" });

connecter();
