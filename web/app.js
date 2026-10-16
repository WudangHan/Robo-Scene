/* Console ROBO-SCÈNE — interface de suivi et de pilotage.
   Aucune dépendance externe : fonctionne hors ligne, servie par le pont Python. */
"use strict";

const $ = (s) => document.querySelector(s);
const COULEURS = ["#f2b544", "#6fa8ff", "#4cc38a", "#ff7eb6", "#b18cff", "#4fd1d9", "#ff9f5a", "#c9d36a"];
const HIST = 240; // 12 s à 20 Hz

let ws = null;
let cfg = null;
let etat = { deg: [], drive: [0, 0], arret: false, lien: "deconnecte" };
let historique = { deg: [], dist: [], vbat: [] };
let trace = [];
let brouillon = [];
let curseurActif = null;
let derniereEnvoi = {};
const propositions = new Map();

/* ── WebSocket ─────────────────────────────────────── */
/* Servie en ligne (Netlify), la Console bascule en simulation dans le navigateur si le pont local ne répond
   pas dans les 1,5 s (simulateur.js) ; servie par le pont, elle ne simule jamais. Un pont déjà joint puis perdu
   (veille, redémarrage) est rappelé toutes les 1,5 s, sans bascule. */
let simulation = false, pontJoint = false;
function connecter() {
  if (simulation) return;
  if (window.ROBO_PONT.forcerSimulation && window.ROBO_SIMULATEUR) { basculerSimulation(); return; }
  ws = new WebSocket(window.ROBO_PONT.url);
  const delai = setTimeout(() => { if (ws.readyState !== 1 && !pontJoint) basculerSimulation(); }, 1500);
  ws.onopen = () => {
    clearTimeout(delai); pontJoint = true;
    window.ROBO_PONT.ouvert(); journal({ niveau: "info", msg: "Interface reliée au pont", ts: heure() });
  };
  ws.onclose = () => {
    clearTimeout(delai);
    if (simulation) return;
    window.ROBO_PONT.ferme();
    majLien("interface");
    if (!pontJoint && !window.ROBO_PONT.local && window.ROBO_SIMULATEUR) { basculerSimulation(); return; }
    setTimeout(connecter, 1500);
  };
  ws.onmessage = recevoir;
}
function basculerSimulation() {
  if (simulation || !window.ROBO_SIMULATEUR || (window.ROBO_PONT.local && !window.ROBO_PONT.forcerSimulation)) return;
  simulation = true;
  try { if (ws) { ws.onclose = null; ws.close(); } } catch (e) { /* déjà fermée */ }
  window.ROBO_PONT.simulation();
  ws = new window.ROBO_SIMULATEUR.PontSimule();
  ws.onmessage = recevoir;
}
function recevoir(e) {
  const m = JSON.parse(e.data);
  switch (m.type) {
    case "config": appliquerConfig(m); break;
    case "etat": surEtat(m); break;
    case "journal": journal(m); break;
    case "sequences": listerSequences(m.liste); break;
    case "sequence": chargerBrouillon(m.sequence); break;
    case "ia_proposition": propositions.set(m.id, m); rendrePropositions(); break;
    case "ia_statut": if (propositions.has(m.id)) { propositions.get(m.id).statut = m.statut; rendrePropositions(); } break;
  }
  if (window.surMessagePlateforme) window.surMessagePlateforme(m);   // flotte, règles, surtitres, voix (console-plateforme.js)
}
function envoyer(op, data = {}) {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify({ op, ...data }));
}
const heure = () => new Date().toTimeString().slice(0, 8);

/* ── Configuration reçue du pont ───────────────────── */
function appliquerConfig(c) {
  const premiere = !cfg || cfg.robot_id !== c.robot_id;   // changement de robot actif : curseurs reconstruits
  cfg = c;
  $("#st-transport").textContent = `${c.robot} · ${c.transport}`;
  $("#st-seance").textContent = c.seance;
  $("#ia-moteur").textContent = `— moteur : ${c.moteur_ia}`;
  $("#ia-seuil").value = c.seuil;
  $("#ia-seuil-val").textContent = Number(c.seuil).toFixed(2);
  $("#ia-auto").textContent = c.execution_auto ? "exécution auto au-dessus du seuil" : "validation humaine requise";
  $("#ia-auto").className = "pastille " + (c.execution_auto ? "avert" : "ok");
  $("#bloc-propulsion").hidden = !c.propulsion;
  if (!premiere) return;
  // Curseurs
  const zone = $("#curseurs");
  zone.innerHTML = "";
  c.noms.forEach((nom, i) => {
    const d = document.createElement("div");
    d.className = "curseur";
    d.innerHTML = `<label for="c${i}">${nom}</label>
      <input type="range" id="c${i}" min="${c.min_deg[i]}" max="${c.max_deg[i]}" step="1" value="${c.repos[i]}">
      <output id="o${i}">${c.repos[i]}°</output>`;
    zone.appendChild(d);
    const r = d.querySelector("input");
    r.addEventListener("pointerdown", () => (curseurActif = i));
    r.addEventListener("focus", () => (curseurActif = i));
    r.addEventListener("blur", () => (curseurActif = null));
    window.addEventListener("pointerup", () => { if (curseurActif === i) setTimeout(() => (curseurActif = null), 400); });
    r.addEventListener("input", () => {
      $(`#o${i}`).textContent = `${r.value}°`;
      limiter(`a${i}`, 90, () => envoyer("articulation", { i, deg: Number(r.value), ms: 0 }));
    });
    r.addEventListener("change", () => envoyer("articulation", { i, deg: Number(r.value), ms: 0 }));
  });
  // Tuiles
  const t = $("#tuiles");
  t.innerHTML = c.noms.map((n, i) => `<div class="tuile"><div class="etiq">${n}</div><div class="val" id="t${i}">—</div></div>`).join("")
    + `<div class="tuile"><div class="etiq">Distance avant</div><div class="val" id="t-dist">—</div></div>
       <div class="tuile"><div class="etiq">Batterie</div><div class="val" id="t-vbat">—</div></div>
       <div class="tuile"><div class="etiq">Roues G / D</div><div class="val" id="t-roues">—</div></div>`;
  $("#legende").innerHTML = c.noms.map((n, i) => `<span><i style="background:${COULEURS[i % 8]}"></i>${n}</span>`).join("")
    + `<span><i style="background:#e7e9ee"></i>Distance (cm)</span>`;
  // En-tête de l'éditeur
  $("#table-images thead").innerHTML = `<tr><th>#</th>${c.noms.map((n) => `<th>${n}</th>`).join("")}<th>Durée ms</th><th>Pause ms</th><th></th></tr>`;
  rendreBrouillon();
}

function limiter(cle, ms, fn) {
  const now = performance.now();
  if (!derniereEnvoi[cle] || now - derniereEnvoi[cle] > ms) { derniereEnvoi[cle] = now; fn(); }
}

/* ── État et télémétrie ────────────────────────────── */
function surEtat(m) {
  etat = m;
  if (Array.isArray(m.deg)) {
    historique.deg.push(m.deg.slice());
    historique.dist.push(m.dist ?? null);
    historique.vbat.push(m.vbat ?? null);
    for (const k in historique) if (historique[k].length > HIST) historique[k].shift();
  }
  if (m.pose) {
    const der = trace[trace.length - 1];
    if (!der || Math.hypot(der[0] - m.pose[0], der[1] - m.pose[1]) > 0.02) trace.push([m.pose[0], m.pose[1]]);
    if (trace.length > 600) trace.shift();
  }
  if (!cfg) return;
  majLien(m.lien);
  (m.deg || []).forEach((d, i) => {
    const t = $(`#t${i}`); if (t) t.textContent = `${Number(d).toFixed(0)}°`;
    if (curseurActif !== i) { const r = $(`#c${i}`); if (r) { r.value = d; $(`#o${i}`).textContent = `${Number(d).toFixed(0)}°`; } }
  });
  $("#t-dist").textContent = m.dist != null ? `${Number(m.dist).toFixed(0)} cm` : "—";
  $("#t-vbat").textContent = m.vbat != null ? `${Number(m.vbat).toFixed(2)} V` : "—";
  $("#t-roues").textContent = m.drive ? `${(+m.drive[0]).toFixed(2)} / ${(+m.drive[1]).toFixed(2)}` : "—";
  const b = $("#st-batt");
  b.textContent = m.vbat != null ? `${Number(m.vbat).toFixed(2)} V` : "— V";
  b.className = "pastille " + (m.vbat == null ? "neutre" : m.vbat < cfg.batterie_min_v ? "alerte" : "ok");
  // Arrêt d'urgence
  $("#bandeau-arret").hidden = !m.arret;
  $("#btn-rearmer").disabled = !m.arret;
  document.querySelectorAll(".pilotage input, .pilotage button, .liste-seq button, #btn-seq-tester")
    .forEach((el) => (el.disabled = !!m.arret));
  // Séquence
  $("#seq-en-cours").textContent = m.sequence ? `En cours : « ${m.sequence} »` : "";
  document.querySelectorAll(".liste-seq .seq").forEach((el) => el.classList.toggle("active", el.dataset.nom === m.sequence));
  if (m.seance && $("#st-seance").textContent !== m.seance) $("#st-seance").textContent = m.seance;
}

function majLien(l) {
  const p = $("#st-lien");
  const map = {
    connecte: ["Robot connecté", "ok"], muet: ["Télémétrie muette", "avert"],
    deconnecte: ["Robot déconnecté", "alerte"], interface: ["Pont injoignable", "alerte"],
  };
  const [txt, cls] = map[l] || ["—", "neutre"];
  p.textContent = txt;
  p.className = "pastille " + cls;
}

/* ── Dessins ───────────────────────────────────────── */
function preparer(cv) {
  if (!cv._ratio) cv._ratio = cv.height / cv.width;
  const r = window.devicePixelRatio || 1;
  const w = cv.clientWidth || 400, h = Math.round(w * cv._ratio);
  if (cv._w !== w || cv._r !== r) {
    cv.width = w * r; cv.height = h * r; cv._w = w; cv._r = r;
  }
  const ctx = cv.getContext("2d");
  ctx.setTransform(r, 0, 0, r, 0, 0);
  return [ctx, w, h];
}

function dessinerRobot() {
  const [ctx, w, h] = preparer($("#cv-robot"));
  ctx.clearRect(0, 0, w, h);
  if (!cfg || !etat.deg?.length) return;
  const deg = etat.deg, n = deg.length;
  // Base vue de dessus (articulation 0)
  const bx = 52, by = 52, br = 34;
  ctx.strokeStyle = "#2a3040"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.arc(bx, by, br, Math.PI, 2 * Math.PI); ctx.stroke();
  const zoneMin = Math.PI + cfg.min_deg[0] * Math.PI / 180, zoneMax = Math.PI + cfg.max_deg[0] * Math.PI / 180;
  ctx.strokeStyle = "#2f3a50"; ctx.lineWidth = 6;
  ctx.beginPath(); ctx.arc(bx, by, br, zoneMin, zoneMax); ctx.stroke();
  const a0 = Math.PI + deg[0] * Math.PI / 180;
  ctx.strokeStyle = COULEURS[0]; ctx.lineWidth = 3;
  ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(bx + br * Math.cos(a0), by + br * Math.sin(a0)); ctx.stroke();
  ctx.fillStyle = "#9aa3b2"; ctx.font = "11px sans-serif"; ctx.textAlign = "center";
  ctx.fillText(`${cfg.noms[0]} ${deg[0].toFixed(0)}°`, bx, by + 18);
  // Chaîne latérale (articulations 1..n-1)
  const ox = w * 0.55, oy = h - 34;
  ctx.fillStyle = "#232937"; ctx.fillRect(ox - 40, oy, 80, 14);
  ctx.strokeStyle = "#2a3040"; ctx.beginPath(); ctx.moveTo(12, oy + 14); ctx.lineTo(w - 12, oy + 14); ctx.stroke();
  let x = ox, y = oy, ang = 0;
  const L = Math.min(h * 0.32, 90);
  for (let i = 1; i < n; i++) {
    const tete = i === n - 1 && n > 2;
    ang = i === 1 ? deg[i] : ang + (deg[i] - 90);
    const rad = (-ang * Math.PI) / 180;
    ctx.fillStyle = "#0f1218"; ctx.strokeStyle = COULEURS[i % 8]; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(x, y, 7, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
    if (tete) {
      const hx = x + 22 * Math.cos(rad), hy = y + 22 * Math.sin(rad);
      ctx.beginPath(); ctx.arc(hx, hy, 15, 0, 2 * Math.PI); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(hx, hy); ctx.lineTo(hx + 48 * Math.cos(rad), hy + 48 * Math.sin(rad));
      ctx.setLineDash([4, 4]); ctx.stroke(); ctx.setLineDash([]);
    } else {
      const nx = x + L * Math.cos(rad), ny = y + L * Math.sin(rad);
      ctx.lineWidth = 9; ctx.lineCap = "round"; ctx.strokeStyle = COULEURS[i % 8] + "cc";
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(nx, ny); ctx.stroke();
      x = nx; y = ny;
    }
    ctx.fillStyle = "#e7e9ee"; ctx.font = "11px sans-serif"; ctx.textAlign = "left";
    ctx.fillText(`${cfg.noms[i]} ${deg[i].toFixed(0)}°`, 10, 100 + (i - 1) * 16);
  }
  if (etat.arret) { ctx.fillStyle = "#d7263155"; ctx.fillRect(0, 0, w, h); }
}

function dessinerPlateau() {
  const [ctx, w, h] = preparer($("#cv-plateau"));
  ctx.clearRect(0, 0, w, h);
  const m = 24, sx = (w - 2 * m) / 4, sy = (h - 2 * m) / 3, s = Math.min(sx, sy);
  const W = 4 * s, H = 3 * s, x0 = (w - W) / 2, y0 = (h - H) / 2;
  const px = (x) => x0 + (x + 2) * s, py = (y) => y0 + (1.5 - y) * s;
  ctx.strokeStyle = "#20252f"; ctx.lineWidth = 1;
  for (let gx = -2; gx <= 2.001; gx += 0.5) { ctx.beginPath(); ctx.moveTo(px(gx), y0); ctx.lineTo(px(gx), y0 + H); ctx.stroke(); }
  for (let gy = -1.5; gy <= 1.501; gy += 0.5) { ctx.beginPath(); ctx.moveTo(x0, py(gy)); ctx.lineTo(x0 + W, py(gy)); ctx.stroke(); }
  ctx.strokeStyle = "#3a4256"; ctx.strokeRect(x0, y0, W, H);
  ctx.fillStyle = "#6b7487"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
  ctx.fillText("LOINTAIN", w / 2, y0 - 8); ctx.fillText("AVANT-SCÈNE · public", w / 2, y0 + H + 16);
  ctx.save(); ctx.translate(x0 - 10, h / 2); ctx.rotate(-Math.PI / 2); ctx.fillText("JARDIN", 0, 0); ctx.restore();
  ctx.save(); ctx.translate(x0 + W + 10, h / 2); ctx.rotate(Math.PI / 2); ctx.fillText("COUR", 0, 0); ctx.restore();
  if (!etat.pose) {
    ctx.fillStyle = "#9aa3b2"; ctx.fillText("Pas de pose transmise par ce robot", w / 2, h / 2);
    return;
  }
  ctx.strokeStyle = "#f2b54455"; ctx.lineWidth = 2; ctx.beginPath();
  trace.forEach(([x, y], k) => (k ? ctx.lineTo(px(x), py(y)) : ctx.moveTo(px(x), py(y)))); ctx.stroke();
  const [x, y, th] = etat.pose;
  if (etat.dist != null) {
    const d = etat.dist / 100;
    ctx.strokeStyle = etat.dist < 40 ? "#ff5d5d" : "#6fa8ff88"; ctx.setLineDash([3, 3]); ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(px(x), py(y)); ctx.lineTo(px(x + d * Math.cos(th)), py(y + d * Math.sin(th))); ctx.stroke();
    ctx.setLineDash([]);
  }
  ctx.save(); ctx.translate(px(x), py(y)); ctx.rotate(-th);
  ctx.fillStyle = etat.arret ? "#d72631" : "#f2b544";
  ctx.beginPath(); ctx.moveTo(14, 0); ctx.lineTo(-9, 9); ctx.lineTo(-5, 0); ctx.lineTo(-9, -9); ctx.closePath(); ctx.fill();
  ctx.restore();
  ctx.fillStyle = "#9aa3b2"; ctx.textAlign = "left";
  ctx.fillText(`x ${x.toFixed(2)} m · y ${y.toFixed(2)} m · cap ${(th * 180 / Math.PI % 360).toFixed(0)}°`, x0 + 4, y0 + 12);
}

function dessinerCourbes() {
  const [ctx, w, h] = preparer($("#cv-courbes"));
  ctx.clearRect(0, 0, w, h);
  const pad = 26, wa = w * 0.64;
  const panneau = (x, larg, titre, yMin, yMax, series, couleurs, unite) => {
    ctx.strokeStyle = "#20252f"; ctx.fillStyle = "#6b7487"; ctx.font = "10px sans-serif"; ctx.textAlign = "right";
    for (let k = 0; k <= 4; k++) {
      const yy = pad / 2 + (h - pad) * k / 4;
      ctx.beginPath(); ctx.moveTo(x + 34, yy); ctx.lineTo(x + larg - 6, yy); ctx.stroke();
      ctx.fillText(`${Math.round(yMax - (yMax - yMin) * k / 4)}${unite}`, x + 30, yy + 3);
    }
    ctx.textAlign = "left"; ctx.fillText(titre, x + 38, h - 4);
    series.forEach((serie, si) => {
      ctx.strokeStyle = couleurs[si]; ctx.lineWidth = 1.6; ctx.beginPath();
      let premier = true;
      serie.forEach((v, k) => {
        if (v == null) return;
        const xx = x + 34 + (larg - 40) * (HIST - serie.length + k) / (HIST - 1);
        const yy = pad / 2 + (h - pad) * (1 - (v - yMin) / (yMax - yMin));
        premier ? ctx.moveTo(xx, yy) : ctx.lineTo(xx, yy); premier = false;
      });
      ctx.stroke();
    });
  };
  const n = cfg ? cfg.noms.length : 0;
  const series = Array.from({ length: n }, (_, i) => historique.deg.map((d) => d[i]));
  panneau(0, wa, "Angles articulaires — 12 dernières secondes", 0, 180, series, COULEURS, "°");
  const maxD = Math.max(100, ...historique.dist.filter((v) => v != null));
  panneau(wa, w - wa, "Distance avant", 0, Math.ceil(maxD / 50) * 50, [historique.dist], ["#e7e9ee"], "");
}

function boucleDessin() {
  dessinerRobot(); dessinerPlateau(); dessinerCourbes();
  requestAnimationFrame(boucleDessin);
}

/* ── Propulsion : manette tactile et clavier ───────── */
let manette = { x: 0, y: 0, actif: false };
const touches = new Set();
function initManette() {
  const zone = $("#manette"), bouton = $("#bouton-manette");
  const placer = (x, y) => {
    const R = zone.clientWidth / 2 - 29;
    bouton.style.left = `${zone.clientWidth / 2 - 29 + x * R}px`;
    bouton.style.top = `${zone.clientHeight / 2 - 29 - y * R}px`;
  };
  const lire = (e) => {
    const r = zone.getBoundingClientRect();
    let x = (e.clientX - r.left - r.width / 2) / (r.width / 2 - 29);
    let y = -(e.clientY - r.top - r.height / 2) / (r.height / 2 - 29);
    const n = Math.hypot(x, y); if (n > 1) { x /= n; y /= n; }
    manette = { x, y, actif: true }; placer(x, y);
  };
  zone.addEventListener("pointerdown", (e) => { if (etat.arret) return; zone.setPointerCapture(e.pointerId); lire(e); });
  zone.addEventListener("pointermove", (e) => { if (manette.actif) lire(e); });
  const relacher = () => { manette = { x: 0, y: 0, actif: false }; placer(0, 0); envoyer("propulsion", { g: 0, d: 0 }); };
  zone.addEventListener("pointerup", relacher);
  zone.addEventListener("pointercancel", relacher);
  window.addEventListener("blur", () => { touches.clear(); if (manette.actif) relacher(); });
  setInterval(() => {
    let x = manette.x, y = manette.y, actif = manette.actif;
    if (!actif && touches.size) {
      y = (touches.has("up") ? 1 : 0) - (touches.has("down") ? 1 : 0);
      x = (touches.has("right") ? 1 : 0) - (touches.has("left") ? 1 : 0);
      actif = true;
    }
    if (!actif || !cfg) return;
    const p = cfg.propulsion_max;
    const g = Math.max(-1, Math.min(1, y + x)) * p, d = Math.max(-1, Math.min(1, y - x)) * p;
    $("#val-propulsion").textContent = `G ${g.toFixed(2)} · D ${d.toFixed(2)}`;
    envoyer("propulsion", { g, d });
  }, 120);
}
const CLAVIER = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right",
  z: "up", w: "up", s: "down", q: "left", a: "left", d: "right" };
function dansChamp(e) { return ["INPUT", "TEXTAREA"].includes(e.target.tagName) && e.target.type !== "range"; }
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.preventDefault(); envoyer("estop", { motif: "touche Échap" }); return; }
  if (e.code === "Space" && !dansChamp(e) && e.target.tagName !== "BUTTON") { e.preventDefault(); envoyer("estop", { motif: "barre d'espace" }); return; }
  if (dansChamp(e) || e.target.type === "range") return;
  const k = CLAVIER[e.key.length === 1 ? e.key.toLowerCase() : e.key];
  if (k && cfg?.propulsion && !etat.arret) { e.preventDefault(); touches.add(k); }
});
window.addEventListener("keyup", (e) => {
  const k = CLAVIER[e.key.length === 1 ? e.key.toLowerCase() : e.key];
  if (k && touches.delete(k) && !touches.size) { envoyer("propulsion", { g: 0, d: 0 }); $("#val-propulsion").textContent = "G 0.00 · D 0.00"; }
});

/* ── Séquences ─────────────────────────────────────── */
function listerSequences(liste) {
  const z = $("#liste-seq");
  z.innerHTML = liste.length ? "" : `<span class="petit">Aucune séquence enregistrée.</span>`;
  liste.forEach((nom) => {
    const s = document.createElement("span");
    s.className = "seq"; s.dataset.nom = nom;
    s.innerHTML = `<button class="jouer" title="Jouer">▶ ${echapper(nom)}</button><button class="editer" title="Charger dans l'éditeur">✎</button>`;
    s.querySelector(".jouer").onclick = () => envoyer("seq_jouer", { nom });
    s.querySelector(".editer").onclick = () => envoyer("seq_lire", { nom });
    z.appendChild(s);
  });
}
function chargerBrouillon(seq) {
  $("#seq-nom").value = seq.nom;
  brouillon = seq.images.map((im) => ({ deg: im.deg.slice(), ms: im.ms ?? 800, pause_ms: im.pause_ms ?? 0 }));
  rendreBrouillon();
}
function rendreBrouillon() {
  const tb = $("#table-images tbody");
  if (!cfg) return;
  if (!brouillon.length) {
    tb.innerHTML = `<tr><td class="vide" colspan="${cfg.noms.length + 4}">Brouillon vide — utilisez « Capturer la pose ».</td></tr>`;
    return;
  }
  tb.innerHTML = "";
  brouillon.forEach((im, k) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${k + 1}</td>` +
      im.deg.map((d, i) => `<td><input type="number" data-i="${i}" min="${cfg.min_deg[i]}" max="${cfg.max_deg[i]}" value="${Math.round(d)}"></td>`).join("") +
      `<td><input type="number" data-c="ms" min="0" step="50" value="${im.ms}"></td>
       <td><input type="number" data-c="pause_ms" min="0" step="50" value="${im.pause_ms}"></td>
       <td><button data-a="aller" title="Amener le robot à cette pose">↦</button><button data-a="haut" title="Monter">↑</button><button data-a="suppr" class="danger" title="Supprimer">✕</button></td>`;
    tr.querySelectorAll("input").forEach((inp) => inp.addEventListener("change", () => {
      const v = Number(inp.value);
      if (inp.dataset.i != null) im.deg[+inp.dataset.i] = v; else im[inp.dataset.c] = v;
    }));
    tr.querySelector('[data-a="aller"]').onclick = () => envoyer("articulations", { deg: im.deg, ms: 1000 });
    tr.querySelector('[data-a="haut"]').onclick = () => { if (k) { [brouillon[k - 1], brouillon[k]] = [brouillon[k], brouillon[k - 1]]; rendreBrouillon(); } };
    tr.querySelector('[data-a="suppr"]').onclick = () => { brouillon.splice(k, 1); rendreBrouillon(); };
    tb.appendChild(tr);
  });
}
$("#btn-capturer").onclick = () => {
  if (!etat.deg?.length) return;
  brouillon.push({ deg: etat.deg.map((d) => Math.round(d)), ms: 800, pause_ms: 0 });
  rendreBrouillon();
};
$("#btn-seq-vider").onclick = () => { brouillon = []; rendreBrouillon(); };
$("#btn-seq-enreg").onclick = () => {
  const nom = $("#seq-nom").value.trim();
  if (!nom) { journal({ niveau: "refus", msg: "Donnez un nom à la séquence", ts: heure() }); return; }
  envoyer("seq_enregistrer", { sequence: { nom, images: brouillon } });
};
$("#btn-seq-tester").onclick = () => {
  const nom = "_brouillon";
  envoyer("seq_enregistrer", { sequence: { nom, images: brouillon } });
  setTimeout(() => envoyer("seq_jouer", { nom }), 150);
};
$("#btn-seq-stop").onclick = () => envoyer("seq_arreter");

/* ── IA supervisée ─────────────────────────────────── */
$("#form-ia").onsubmit = (e) => {
  e.preventDefault();
  const t = $("#ia-texte").value.trim();
  if (t) { envoyer("ia_demander", { texte: t }); $("#ia-texte").value = ""; }
};
$("#ia-seuil").oninput = (e) => ($("#ia-seuil-val").textContent = Number(e.target.value).toFixed(2));
$("#ia-seuil").onchange = (e) => envoyer("seuil", { valeur: Number(e.target.value) });

const STATUTS = { a_valider: "En attente de validation", bloquee: "Bloquée (sous le seuil)", validee: "Validée et exécutée",
  executee_auto: "Exécutée automatiquement", rejetee: "Rejetée" };
function decrireAction(p) {
  const a = p.action, q = p.parametres || {};
  if (a === "articulations") return "articulations → " + (q.deg || []).map((d, i) => d == null ? null : `${cfg.noms[i]} ${Math.round(d)}°`).filter(Boolean).join(", ") + ` (${q.ms ?? "?"} ms)`;
  if (a === "propulsion") return `propulsion → G ${(+q.g).toFixed(2)} · D ${(+q.d).toFixed(2)} pendant ${q.ms ?? "?"} ms`;
  if (a === "sequence") return `séquence → « ${q.nom} »`;
  if (a === "repos") return "retour à la position de repos";
  return "aucune action";
}
function rendrePropositions() {
  const z = $("#propositions");
  z.innerHTML = "";
  [...propositions.values()].reverse().slice(0, 8).forEach((p) => {
    const d = document.createElement("div");
    d.className = `prop ${p.statut}`;
    const coul = p.confiance >= p.seuil ? "var(--ok)" : "var(--alerte)";
    d.innerHTML = `<div class="entete"><span class="mono">${p.id} · ${echapper(p.moteur || "")}</span><span>${STATUTS[p.statut] || p.statut}</span></div>
      <div class="consigne">« ${echapper(p.consigne)} »</div>
      <div class="action">${echapper(decrireAction(p))}</div>
      <div class="jauge" title="Confiance retenue / seuil"><div class="rempli" style="width:${p.confiance * 100}%;background:${coul}"></div><div class="seuil" style="left:${p.seuil * 100}%"></div></div>
      <div class="petit mono">confiance ${p.confiance.toFixed(2)} = min(déclarée ${(+p.confiance_declaree).toFixed(2)}, vérification ${(+p.confiance_verification).toFixed(2)}) · seuil ${(+p.seuil).toFixed(2)}</div>
      <div class="justif">${echapper(p.justification || "")}</div>
      <div class="petit">Vérification : ${echapper(p.motif_verification || "")}</div>`;
    if (p.statut === "a_valider") {
      const l = document.createElement("div"); l.className = "ligne";
      l.innerHTML = `<button class="primaire">Valider et exécuter</button><button class="danger">Rejeter</button>`;
      l.children[0].onclick = () => envoyer("ia_valider", { id: p.id });
      l.children[1].onclick = () => envoyer("ia_rejeter", { id: p.id });
      d.appendChild(l);
    }
    z.appendChild(d);
  });
}

/* ── Journal ───────────────────────────────────────── */
function journal(m) {
  const li = document.createElement("li");
  li.innerHTML = `<span class="ts">${m.ts || heure()}</span><span class="${m.niveau}">${echapper(m.msg)}</span>`;
  const ol = $("#journal");
  ol.prepend(li);
  while (ol.children.length > 300) ol.lastChild.remove();
}
$("#form-note").onsubmit = (e) => {
  e.preventDefault();
  const t = $("#note-texte").value.trim();
  if (t) { envoyer("note", { texte: t }); $("#note-texte").value = ""; }
};
$("#btn-cloturer").onclick = () => {
  if (confirm("Clôturer la séance en cours et en ouvrir une nouvelle ?")) envoyer("cloturer");
};

/* ── Boutons généraux ──────────────────────────────── */
$("#btn-arret").onclick = () => envoyer("estop", { motif: "bouton ARRÊT" });
$("#btn-rearmer").onclick = () => envoyer("rearmer");
$("#btn-repos").onclick = () => envoyer("repos");

function echapper(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

initManette();
connecter();
requestAnimationFrame(boucleDessin);
