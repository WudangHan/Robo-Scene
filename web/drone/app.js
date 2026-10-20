/* Robo-Scène — page « Drone » : drone virtuel dans le théâtre, console de vol, conduite, caméra 4K, zones, liaison au
   drone réel par le pont. Le drone virtuel fonctionne seul dans le navigateur (aucun pont requis) ; le drone réel
   n'est commandé qu'à travers le pont, qui applique les mêmes zones et ses propres conditions de sécurité. */
import { Theatre } from "./theatre3d.js";
import { DroneVirtuel, ETATS, deg, rad } from "./vol.js";
import { compiler, CONDUITE_EXEMPLE } from "./conduite.js";
import { point, verifier, verifierSegment } from "./geofence.js";
import { CameraVirtuelle, FluxReel, UHD, dessinerCadre } from "./camera4k.js";
import { flechesVersManche, pointRelatif } from "./commande.js";
import { installerCommandes, decrire } from "./commandes_page.js";
import { installerDialogue } from "../dialogue.js";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const nb = (x, d = 1) => Number(x).toLocaleString("fr-CA", { minimumFractionDigits: d, maximumFractionDigits: d });
const memo = {
  lire(k, defaut) { try { const v = localStorage.getItem(`robo-scene-drone-${k}`); return v ? JSON.parse(v) : defaut; } catch (e) { return defaut; } },
  ecrire(k, v) { try { localStorage.setItem(`robo-scene-drone-${k}`, JSON.stringify(v)); } catch (e) { /* stockage indisponible */ } },
};

const salle = await (await fetch("/static/drone/salle.json")).json();
const theatre = new Theatre($("#vue3d"), salle);
const journalEv = [];
const drone = new DroneVirtuel(salle, { surEvenement: (e) => journal(e.niveau, e.msg, "virtuel") });
const cam = new CameraVirtuelle($("#cam-virtuelle"), theatre);
const flux = new FluxReel($("#cam-reelle"));
let cible = "virtuel";
let interpretes = memo.lire("interpretes", []);
let conduite = memo.lire("conduite", null) || structuredClone(CONDUITE_EXEMPLE);
let comp = null, prochain = 0, enCours = null, toutJouer = false;
const pont = { ws: null, ouvert: false, etat: null, tel: null, telT: 0 };
const numeroEssai = (memo.lire("numero", 0) || 0) + 1; memo.ecrire("numero", numeroEssai);

/* ── Journal ─────────────────────────────────────────────── */
function journal(niveau, msg, source = "page") {
  const ts = new Date().toLocaleTimeString("fr-CA", { hour12: false });
  journalEv.push({ ts: new Date().toISOString(), niveau, msg, source });
  const li = document.createElement("li");
  li.className = niveau === "alerte" || niveau === "refus" ? "alerte" : niveau === "avert" ? "avert" : "";
  li.textContent = `${ts} · ${source === "pont" ? "[pont] " : ""}${msg}`;
  const ol = $("#journal"); ol.prepend(li); while (ol.children.length > 300) ol.lastChild.remove();
  if (niveau === "refus" || niveau === "alerte") $("#c-bilan").dataset.dernier = msg;
}

/* ── Onglets ─────────────────────────────────────────────── */
function onglet(nom) {
  $$(".onglets [role=tab]").forEach((b) => b.setAttribute("aria-selected", b.dataset.onglet === nom));
  $$(".panneau-onglet").forEach((p) => (p.hidden = p.id !== `ong-${nom}`));
  memo.ecrire("onglet", nom);
}
$$(".onglets [role=tab]").forEach((b) => (b.onclick = () => onglet(b.dataset.onglet)));
onglet(memo.lire("onglet", "vol"));

/* ── Zones, mode de vol, interprètes ─────────────────────── */
function majModes() {
  $("#modes").innerHTML = Object.entries(salle.modes).map(([k, m]) => `<label><input type="radio" name="mode" value="${k}"${k === drone.mode ? " checked" : ""}>
    <b>${esc(m.libelle)}</b><small>${esc(m.aide)}</small></label>`).join("");
  $$("#modes input").forEach((r) => (r.onchange = () => changerMode(r.value)));
}
function changerMode(m) {
  if (drone.enVol) { journal("refus", "Changement de mode refusé en vol"); majModes(); return; }
  if (m === "salle_vide" && !$("#salle-vide-par").value.trim()) {
    $("#salle-vide-par").focus();
    journal("avert", "Mode « salle vide » : saisir les initiales de la personne qui a vérifié la salle, puis choisir à nouveau le mode");
    majModes(); return;
  }
  drone.mode = m; memo.ecrire("mode", m);
  theatre.dessinerZones(m, $("#voir-zones").checked);
  majModes(); recompiler();
  journal("info", `Mode de vol : ${salle.modes[m].libelle}${m === "salle_vide" ? ` (salle vérifiée vide par ${$("#salle-vide-par").value.trim()})` : ""}`);
  envoyer({ op: "drone_mode", mode: m, par: $("#salle-vide-par").value.trim() });
}
$("#salle-vide-par").value = memo.lire("salle_vide_par", "");
$("#salle-vide-par").onchange = () => memo.ecrire("salle_vide_par", $("#salle-vide-par").value.trim());
function majInterpretes() {
  drone.interpretes = interpretes.map((i) => [i.x, i.z]);
  theatre.dessinerInterpretes(interpretes);
  $("#z-interpretes").innerHTML = interpretes.map((it, i) => `<li><span>Interprète ${i + 1} : x ${nb(it.x)} m, z ${nb(it.z)} m</span><button data-i="${i}" aria-label="Retirer l'interprète ${i + 1}">Retirer</button></li>`).join("")
    || `<li class="petit">Aucun interprète déclaré.</li>`;
  $$("#z-interpretes button").forEach((b) => (b.onclick = () => { interpretes.splice(+b.dataset.i, 1); majInterpretes(); }));
  memo.ecrire("interpretes", interpretes); recompiler();
  envoyer({ op: "drone_interpretes", liste: interpretes });
}
$("#z-ajout").onclick = () => { $("#outil-clic").value = "interprete"; journal("info", "Cliquez sur le plateau pour placer un interprète"); };
$("#z-vider").onclick = () => { interpretes = []; majInterpretes(); };
$("#z-tester").onclick = () => {
  const p = $("#z-point").value.split(/[,;\s]+/).filter(Boolean).map(Number);
  const v = verifier(salle, p, drone.ctx);
  const el = $("#z-verdict"); el.className = `message ${v.ok ? "ok" : "erreur"}`;
  el.textContent = v.ok ? `Point permis (${v.zone})` : v.motif;
};
$("#regles").innerHTML = (() => {
  const R = salle.regles;
  return `<ul>
    <li>Marge aux limites et aux obstacles : ${nb(R.marge_m)} m ; hauteur minimale hors de l'aire : ${nb(R.hauteur_min_m)} m</li>
    <li>Marge autour du public (représentation) : ${nb(R.marge_public_m)} m, sur toute la hauteur ; fauteuils (salle vide) : ${nb(R.hauteur_fauteuils_m)} m</li>
    <li>Cylindre des interprètes : rayon ${nb(R.rayon_interpretes_m)} m, hauteur ${nb(R.hauteur_interpretes_m)} m</li>
    <li>Vitesses maximales : ${nb(R.vitesse_max_h_m_s)} m/s à l'horizontale, ${nb(R.vitesse_max_v_m_s)} m/s à la verticale, ${R.vitesse_lacet_max_deg_s} °/s en lacet ; accélération ${nb(R.acceleration_max_m_s2)} m/s²</li>
    <li>Batterie : alerte ${R.batterie_alerte_pct} %, retour ${R.batterie_retour_pct} %, atterrissage ${R.batterie_critique_pct} % ; autonomie modélisée ${R.autonomie_min} min</li>
    <li>Perte de liaison : stationnaire après ${nb(R.perte_liaison_stationnaire_s)} s, atterrissage après ${nb(R.perte_liaison_atterrir_s)} s</li></ul>`;
})();

/* ── Clic dans le théâtre ────────────────────────────────── */
theatre.surClic = (p) => {
  const outil = $("#outil-clic").value;
  if (outil === "interprete") {
    if (p[2] > salle.volumes.plateau.z[1]) { journal("refus", "Les interprètes se placent sur le plateau"); return; }
    interpretes.push({ x: +p[0].toFixed(2), z: +p[2].toFixed(2) }); majInterpretes(); $("#outil-clic").value = "";
  } else if (outil === "aller") {
    const sol = p[2] > salle.volumes.plateau.z[1] ? salle.volumes.salle.y[0] : 0;
    allerA([+p[0].toFixed(2), +(sol + Number($("#alt-clic").value)).toFixed(2), +p[2].toFixed(2)], { duree: null, lacet: null });
  }
};

/* ── Souris : glisser le drone, double-clic « aller ici » ── */
const solSous = (z) => (z > salle.volumes.plateau.z[1] ? salle.volumes.salle.y[0] : 0);
function cibleSouris(p) {
  // au sol : la destination prend l'altitude du curseur « aller ici » ; en vol : l'altitude du glissement
  const q = [+p[0].toFixed(2), +p[1].toFixed(2), +p[2].toFixed(2)];
  if (!drone.enVol || drone.p[1] - solSous(drone.p[2]) < 0.3) q[1] = +(solSous(q[2]) + Number($("#alt-clic").value)).toFixed(2);
  return q;
}
function verifierSouris(q) {
  const v = drone.enVol ? verifierSegment(salle, drone.p, q, drone.ctx) : verifier(salle, q, drone.ctx);
  return { ok: v.ok, motif: v.motif };
}
function allerSouris(q, libelle) {
  const v = verifierSouris(q);
  if (!v.ok) { journal("refus", `${libelle} : destination refusée (${v.motif})`); return; }
  annulerConduite();
  cmds.executerActions([{ type: "point", p: q }], `🖱 ${libelle}`);
}
theatre.surGlisser = (p, phase) => {
  const q = cibleSouris(p);
  if (phase === "fin") return allerSouris(q, "glisser-déposer");
  return verifierSouris(q);
};
theatre.surDoubleClic = (p) => {
  const q = cibleSouris(p);
  if (drone.enVol && drone.p[1] - solSous(drone.p[2]) > 0.3) q[1] = +(solSous(q[2]) + Math.max(0.6, drone.p[1] - solSous(drone.p[2]))).toFixed(2);
  allerSouris(q, "double-clic");
};

/* ── Commandes : virtuel ou réel ─────────────────────────── */
function envoyer(m) { if (pont.ouvert) { try { pont.ws.send(JSON.stringify(m)); return true; } catch (e) { /* pont fermé */ } } return false; }
const reelActif = () => cible === "reel" && pont.ouvert && pont.etat?.adaptateur;

function decoller(hauteur) {
  const h = Number(hauteur || $("#h-decollage").value);
  if (reelActif()) return envoyer({ op: "drone_decoller", hauteur: h });
  return drone.decoller(h);
}
function atterrir() { annulerConduite(); return reelActif() ? envoyer({ op: "drone_atterrir" }) : drone.atterrir(); }
function stationnaire() { annulerConduite(); return reelActif() ? envoyer({ op: "drone_stationnaire" }) : drone.stationnaire(); }
function retour() {
  annulerConduite();
  if (reelActif()) { const a = salle.aire.centre; return envoyer({ op: "drone_aller", p: [a[0], 1.5, a[2]], vitesse: 1.0 }); }
  return drone.retour();
}
function allerA(p, o = {}) {
  if (reelActif()) return envoyer({ op: "drone_aller", p, duree: o.duree || null, lacet: o.lacet ?? null });
  const s = verifierSegment(salle, drone.p, p, drone.ctx);
  if (!s.ok) { journal("refus", `Trajet refusé à ${Math.round(s.fraction * 100)} % : ${s.motif}`); return { ok: false }; }
  return drone.allerA(p, { duree: o.duree || undefined, lacet: o.lacet === null || o.lacet === undefined ? undefined : rad(o.lacet) });
}
function arret() {
  annulerConduite(); cmds?.vider();
  drone.arretUrgence("bouton ARRÊT de la page Drone");
  envoyer({ op: "estop", motif: "ARRÊT de la page Drone" });
}
function rearmer() {
  const r = drone.rearmer();
  if (pont.ouvert && (pont.etat?.urgence) && window.confirm("Réarmer toute la plateforme (robots et drone) ? Le réarmement est une action volontaire et distincte.")) envoyer({ op: "rearmer" });
  return r;
}

$("#b-decoller").onclick = () => decoller(); $("#b-atterrir").onclick = atterrir; $("#b-station").onclick = stationnaire;
$("#b-retour").onclick = retour; $("#b-rearmer").onclick = rearmer; $("#btn-arret").onclick = arret;
$("#b-batterie").onclick = () => drone.changerBatterie();
$("#b-aller").onclick = () => {
  try { allerA(point(salle, $("#aller-repere").value), { duree: Number($("#aller-duree").value) || null, lacet: Number($("#aller-lacet").value) }); }
  catch (e) { journal("refus", e.message); }
};
$("#h-decollage").oninput = () => ($("#h-decollage-val").textContent = `${nb($("#h-decollage").value)} m`);
$("#alt-clic").oninput = () => ($("#alt-clic-val").textContent = `${nb($("#alt-clic").value)} m`);
$("#del").oninput = () => theatre.couleurDEL($("#del").value);
$("#turbulence").onchange = () => (drone.turbulence = $("#turbulence").checked ? 0.05 : 0);
$$("input[name=cible]").forEach((r) => (r.onchange = () => {
  cible = r.value; drone.liaison.exigee = false;
  journal("info", cible === "reel" ? "Les commandes vont désormais au drone réel ; le drone virtuel suit sa télémétrie" : "Les commandes vont au drone virtuel");
}));
const dlg = $("#d-coupure");
$("#b-coupure").onclick = () => { $("#d-coupure-texte").value = ""; dlg.showModal(); };
dlg.addEventListener("close", () => {
  if (dlg.returnValue !== "ok") return;
  const c = $("#d-coupure-texte").value.trim();
  annulerConduite();
  if (reelActif()) envoyer({ op: "drone_coupure", confirmation: c }); else drone.couperMoteurs(c);
});
for (const [id, nom] of Object.entries(salle.reperes)) {
  $("#aller-repere").insertAdjacentHTML("beforeend", `<option value="${id}">${esc(id.replace(/_/g, " "))}</option>`);
  $("#viser").insertAdjacentHTML("beforeend", `<option value="${id}">${esc(id.replace(/_/g, " "))}</option>`);
  void nom;
}
$("#aller-repere").value = "centre";

/* ── Manettes à l'écran, clavier, manette de jeu ─────────── */
const manettes = { g: [0, 0], d: [0, 0] };
for (const [cote, el] of [["g", $("#manette-g")], ["d", $("#manette-d")]]) {
  el.tabIndex = 0;
  const bouger = (e) => {
    const b = el.getBoundingClientRect(), r = b.width / 2 - 10;
    let x = (e.clientX - b.left - b.width / 2) / r, y = (e.clientY - b.top - b.height / 2) / r;
    const n = Math.hypot(x, y); if (n > 1) { x /= n; y /= n; }
    manettes[cote] = [x, -y]; el.style.setProperty("--dx", `${x * r}px`); el.style.setProperty("--dy", `${y * r}px`);
  };
  el.addEventListener("pointerdown", (e) => { el.setPointerCapture(e.pointerId); bouger(e); });
  el.addEventListener("pointermove", (e) => { if (el.hasPointerCapture(e.pointerId)) bouger(e); });
  const lacher = () => { manettes[cote] = [0, 0]; el.style.setProperty("--dx", "0px"); el.style.setProperty("--dy", "0px"); };
  el.addEventListener("pointerup", lacher); el.addEventListener("pointercancel", lacher);
}
const touches = new Set();
const saisie = (e) => /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable;
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { arret(); document.body.classList.remove("mode-scene"); return; }
  if (saisie(e) || dlg.open) return;
  const k = e.key.toLowerCase();
  if (k === " ") { e.preventDefault(); stationnaire(); return; }
  if (k === "t") { decoller(); return; }
  if (k === "l") { atterrir(); return; }
  if (k === "h") { retour(); return; }
  if (k === "enter" && !$("#ong-conduite").hidden) { e.preventDefault(); go(); return; }
  maj = e.shiftKey;
  if (["w", "a", "s", "d", "r", "f", "q", "e", "arrowup", "arrowdown", "arrowleft", "arrowright", "pageup", "pagedown"].includes(k)) { e.preventDefault(); touches.add(k); }
});
window.addEventListener("keyup", (e) => { touches.delete(e.key.toLowerCase()); maj = e.shiftKey; });
window.addEventListener("blur", () => { touches.clear(); maj = false; });
let maj = false;
$("#repere-fleches").value = memo.lire("repere-fleches", "robot");
$("#repere-fleches").onchange = (e) => { memo.ecrire("repere-fleches", e.target.value); e.target.blur(); };
let boutonsPrec = [];
function lireManche() {
  const k = (a, b) => (touches.has(a) ? 1 : 0) - (touches.has(b) ? 1 : 0);
  // flèches : déplacement (repère du drone ou de la scène) ; Maj + ↑ ↓ : altitude ; Maj + ← → : lacet
  const f = maj ? [0, 0] : flechesVersManche(touches.has("arrowup"), touches.has("arrowdown"), touches.has("arrowleft"), touches.has("arrowright"), $("#repere-fleches").value, drone.lacet);
  let droite = k("d", "a") + f[0] + manettes.d[0], avant = k("w", "s") + f[1] + manettes.d[1];
  let haut = k("r", "f") + k("pageup", "pagedown") + (maj ? k("arrowup", "arrowdown") : 0) + manettes.g[1];
  let lacet = k("e", "q") + (maj ? k("arrowright", "arrowleft") : 0) + manettes.g[0];
  const pads = navigator.getGamepads ? [...navigator.getGamepads()].filter(Boolean) : [];
  const gp = pads[0];
  if (gp) {
    const z = (v) => (Math.abs(v) < 0.12 ? 0 : v);
    lacet += z(gp.axes[0] || 0); haut += -z(gp.axes[1] || 0); droite += z(gp.axes[2] || 0); avant += -z(gp.axes[3] || 0);
    const b = gp.buttons.map((x) => x.pressed);
    const front = (i) => b[i] && !boutonsPrec[i];
    if (front(0)) decoller(); if (front(1)) atterrir(); if (front(2)) stationnaire(); if (front(3)) retour();
    boutonsPrec = b;
  }
  const c = (v) => Math.max(-1, Math.min(1, v));
  return { manche: [c(droite), c(avant), c(haut)], lacet: c(lacet) };
}

/* ── Conduite ────────────────────────────────────────────── */
function recompiler() {
  const depart = drone.enVol ? null : salle.aire.centre;
  comp = compiler(salle, conduite, depart, { mode: drone.mode, interpretes: drone.interpretes });
  theatre.dessinerTrajet(comp);
  const b = $("#c-bilan");
  b.className = `note${comp.ok ? "" : " erreur"}`;
  b.innerHTML = `<b>${esc(conduite.titre || "Conduite")}</b> — ${comp.segments.length} repères, ${nb(comp.duree)} s en mode « ${esc(salle.modes[drone.mode].libelle)} » : `
    + (comp.ok ? "<span>valide</span>" : "<span class=\"erreur\">GO bloqué</span>")
    + (comp.erreurs.length ? `<ul>${comp.erreurs.map((e) => `<li class="erreur">${esc(e)}</li>`).join("")}</ul>` : "")
    + (comp.avertissements.length ? `<ul>${comp.avertissements.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>` : "");
  if (conduite.mode && conduite.mode !== drone.mode) b.insertAdjacentHTML("beforeend", `<p class="petit">La conduite a été écrite pour le mode « ${esc(salle.modes[conduite.mode]?.libelle || conduite.mode)} ».</p>`);
  $("#c-table tbody").innerHTML = comp.segments.map((s, i) => `<tr class="${i === prochain ? "courant" : i < prochain ? "fait" : ""}">
    <td><b>${esc(s.id)}</b> ${esc(s.nom)}</td><td>${esc(s.action)}</td><td class="mono">${s.p1.map((x) => nb(x)).join(" ; ")}</td>
    <td>${nb(s.T)} s</td><td>${s.camera?.viser ? `vise ${esc(Array.isArray(s.camera.viser) ? s.camera.viser.join(",") : s.camera.viser)}` : "—"}</td>
    <td><button data-i="${i}" class="discret" title="Jouer ce repère">▶</button></td></tr>`).join("");
  $$("#c-table button").forEach((x) => (x.onclick = () => { prochain = +x.dataset.i; go(); }));
  $("#c-go").disabled = !comp.ok;
  $("#c-prochain").textContent = comp.segments[prochain] ? `Prochain : ${comp.segments[prochain].id} ${comp.segments[prochain].nom}` : "Fin de la conduite";
  $("#c-json").value = JSON.stringify(conduite, null, 2);
  memo.ecrire("conduite", conduite);
}
function annulerConduite() { if (enCours || toutJouer) journal("avert", "Conduite interrompue"); enCours = null; toutJouer = false; $("#etat-conduite").textContent = ""; }
function appliquerCamera(c) {
  if (!c) return;
  if ("viser" in c) { theatre.viser = c.viser ? point(salle, c.viser) : null; $("#viser").value = typeof c.viser === "string" ? c.viser : ""; }
  if (typeof c.inclinaison === "number" && !c.viser) { theatre.nacelleTangage = c.inclinaison; $("#tangage").value = c.inclinaison; }
  if (typeof c.zoom === "number") { theatre.zoom = c.zoom; $("#zoom").value = c.zoom; }
  majCameraLibelles();
}
function go() {
  if (!comp?.ok) { journal("refus", "GO bloqué : conduite invalide (voir le bilan)"); return; }
  const s = comp.segments[prochain];
  if (!s) { journal("info", "Fin de la conduite"); return; }
  let r;
  if (s.action === "decoller") r = reelActif() ? envoyer({ op: "drone_decoller", hauteur: s.p1[1] - s.p0[1] }) : drone.decoller(s.p1[1] - s.p0[1]);
  else if (s.action === "atterrir") r = reelActif() ? envoyer({ op: "drone_atterrir" }) : drone.atterrir();
  else if (s.action === "stationnaire") r = reelActif() ? envoyer({ op: "drone_stationnaire" }) : drone.stationnaire();
  else r = allerA(s.p1, { duree: s.T, lacet: s.lacet });
  if (r === false || (r && r.ok === false)) { toutJouer = false; return; }
  appliquerCamera(s.camera);
  if (s.led) { theatre.couleurDEL(s.led); $("#del").value = s.led; }
  enCours = { i: prochain, t0: performance.now(), T: s.T, action: s.action };
  journal("info", `GO ${s.id} — ${s.nom || s.action}${s.note ? ` (${s.note})` : ""}`);
  $("#repere-courant").textContent = `${s.id} ${s.nom}`;
  prochain += 1; recompiler();
}
function suivreConduite() {
  if (!enCours) return;
  const ecoule = (performance.now() - enCours.t0) / 1000;
  $("#etat-conduite").textContent = `${nb(Math.min(ecoule, enCours.T))} / ${nb(enCours.T)} s`;
  // drone virtuel : repère terminé quand la trajectoire est achevée (et non au seul chronomètre, si l'affichage a ralenti)
  const fini = ecoule >= enCours.T + 0.2 && (reelActif() || (["vol", "au_sol"].includes(drone.etat) && drone.consigne.type !== "trajectoire"));
  if (!fini) return;
  enCours = null; $("#etat-conduite").textContent = "";
  if (toutJouer && prochain < comp.segments.length) setTimeout(() => toutJouer && go(), 300);
  else toutJouer = false;
}
$("#c-go").onclick = go;
$("#c-tout").onclick = () => { if (!comp?.ok) return go(); toutJouer = true; if (!enCours) go(); };
$("#c-retour").onclick = () => { annulerConduite(); prochain = 0; recompiler(); };
$("#c-exemple").onclick = () => { conduite = structuredClone(CONDUITE_EXEMPLE); prochain = 0; recompiler(); };
$("#c-valider").onclick = () => { recompiler(); journal(comp.ok ? "info" : "refus", comp.ok ? "Conduite valide" : `Conduite invalide : ${comp.erreurs[0]}`); };
$("#c-appliquer").onclick = () => {
  try { conduite = JSON.parse($("#c-json").value); prochain = 0; recompiler(); journal("info", "Texte de la conduite appliqué"); }
  catch (e) { journal("refus", `JSON invalide : ${e.message}`); }
};
$("#c-fichier").onchange = async (e) => {
  const f = e.target.files[0]; if (!f) return;
  try { conduite = JSON.parse(await f.text()); prochain = 0; recompiler(); journal("info", `Conduite « ${f.name} » chargée`); }
  catch (err) { journal("refus", `Fichier illisible : ${err.message}`); }
};
const telecharger = (blob, nom) => { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = nom; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); };
$("#c-exporter").onclick = () => telecharger(new Blob([JSON.stringify(conduite, null, 2)], { type: "application/json" }), `conduite_drone_${new Date().toISOString().slice(0, 10)}.json`);

/* ── Caméra ──────────────────────────────────────────────── */
function majCameraLibelles() {
  $("#tangage-val").textContent = `${theatre.nacelleTangage < 0 ? "−" : ""}${Math.abs(Math.round(theatre.nacelleTangage))}°`;
  $("#zoom-val").textContent = `×${nb(theatre.zoom)}`;
}
$("#tangage").oninput = () => { theatre.viser = null; $("#viser").value = ""; theatre.nacelleTangage = Number($("#tangage").value); majCameraLibelles(); };
$("#zoom").oninput = () => { theatre.zoom = Number($("#zoom").value); majCameraLibelles(); };
$("#viser").onchange = () => { theatre.viser = $("#viser").value ? point(salle, $("#viser").value) : null; };
$("#definition").onchange = () => { const [w, h] = $("#definition").value.split("x").map(Number); cam.regler(w, h); };
$("#b-photo").onclick = async () => {
  const blob = await cam.photo4K();
  telecharger(blob, `drone_virtuel_${UHD.largeur}x${UHD.hauteur}_${new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19)}.png`);
  journal("info", `Image virtuelle 4K enregistrée (${UHD.largeur} × ${UHD.hauteur})`);
};
$("#b-rec").onclick = async () => {
  if (cam.enregistre) {
    const blob = await cam.arreterEnregistrement();
    $("#b-rec").textContent = "● Enregistrer"; $("#b-rec").setAttribute("aria-pressed", "false");
    if (blob) telecharger(blob, `drone_virtuel_${cam.definition.join("x")}_${new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19)}.webm`);
    journal("info", "Enregistrement de la caméra virtuelle terminé");
  } else {
    try { cam.demarrerEnregistrement(30); $("#b-rec").textContent = "■ Arrêter"; $("#b-rec").setAttribute("aria-pressed", "true"); journal("info", `Enregistrement de la caméra virtuelle (${cam.definition.join(" × ")})`); }
    catch (e) { journal("refus", e.message); }
  }
};
let source = "virtuelle";
function majSource() {
  source = $("input[name=source]:checked").value;
  const pip = $("#pip");
  pip.classList.toggle("superposee", source === "superposee");
  $("#cam-reelle").hidden = source === "virtuelle";
  $("#cam-virtuelle").hidden = source === "reelle";
  $("#pip-titre").textContent = { virtuelle: "Caméra embarquée (virtuelle)", reelle: "Caméra du drone réel", superposee: "Réelle + virtuelle superposées" }[source];
}
$$("input[name=source]").forEach((r) => (r.onchange = majSource));
$("#pip-taille").onclick = () => $("#pip").classList.toggle("grand");
async function listerCameras() {
  try {
    const l = await FluxReel.cameras();
    $("#cam-liste").innerHTML = `<option value="">Carte de capture HDMI / webcam…</option>` + l.map((d, i) => `<option value="${esc(d.deviceId)}">${esc(d.label || `Source vidéo ${i + 1}`)}</option>`).join("");
  } catch (e) { /* aucune source */ }
}
const infoCam = (r) => { $("#cam-info").textContent = r.largeur ? `Flux réel : ${r.largeur} × ${r.hauteur}${r.ips ? ` à ${r.ips} i/s` : ""}${r.largeur >= 3840 ? " (UHD 4K)" : " — inférieur à 4K : vérifier la carte de capture et la sortie HDMI"}${r.nom ? ` · ${r.nom}` : ""}` : "Flux ouvert, en attente d'images…"; };
$("#b-capture").onclick = async () => {
  try { const r = await flux.ouvrirCapture($("#cam-liste").value || undefined); infoCam(r); $("input[name=source][value=reelle]").checked = true; majSource(); listerCameras(); journal("info", "Capture vidéo réelle ouverte (affichage seul)"); }
  catch (e) { $("#cam-info").textContent = e.message; journal("refus", `Capture : ${e.message}`); }
};
$("#b-whep").onclick = async () => {
  const url = $("#whep-url").value.trim(); if (!url) return;
  memo.ecrire("whep", url);
  try { $("#cam-info").textContent = "Connexion WHEP…"; const r = await flux.ouvrirWHEP(url); infoCam(r); $("input[name=source][value=reelle]").checked = true; majSource(); journal("info", "Flux WHEP ouvert (affichage seul)"); }
  catch (e) { $("#cam-info").textContent = e.message; journal("refus", `WHEP : ${e.message}`); }
};
$("#b-cam-fermer").onclick = async () => { await flux.fermer(); $("#cam-info").textContent = "—"; $("input[name=source][value=virtuelle]").checked = true; majSource(); };
$("#whep-url").value = memo.lire("whep", "");
listerCameras();

/* ── Vues ────────────────────────────────────────────────── */
$$("[data-vue]").forEach((b) => (b.onclick = () => theatre.vue(b.dataset.vue)));
$("#voir-zones").onchange = () => (theatre.groupeZones.visible = theatre.groupeTrajet.visible = $("#voir-zones").checked);
$("#voir-poursuite").onchange = () => theatre.poursuiteSur($("#voir-poursuite").checked);
$("#btn-scene").onclick = () => document.body.classList.toggle("mode-scene");

/* ── Liaison avec le pont (drone réel) ───────────────────── */
function majReel() {
  const e = pont.etat;
  $("#r-pont").textContent = pont.ouvert ? `Pont : relié (${window.ROBO_PONT.url})` : "Pont : non relié — le drone virtuel fonctionne sans pont ; la liaison au drone réel en dépend.";
  $("#cible-reel").disabled = !(pont.ouvert && e?.adaptateur);
  if ($("#cible-reel").disabled && cible === "reel") { $("input[name=cible][value=virtuel]").checked = true; cible = "virtuel"; }
  const st = $("#st-reel");
  st.textContent = !pont.ouvert ? "Drone réel : pont absent" : !e?.adaptateur ? "Drone réel : non relié" : `${e.reel ? "Drone réel" : "Pont (simulation)"} : ${e.adaptateur}`;
  st.className = `pastille ${!e?.adaptateur ? "neutre" : e.urgence ? "alerte" : e.reel ? "ok" : "avert"}`;
  if (!e) { $("#r-conditions").innerHTML = ""; return; }
  if (!$("#r-adaptateur").options.length) {
    $("#r-adaptateur").innerHTML = Object.entries(e.adaptateurs).map(([k, d]) => `<option value="${k}" title="${esc(d)}">${k}</option>`).join("");
    $("#r-adaptateur").onchange = () => ($("#r-desc").textContent = e.adaptateurs[$("#r-adaptateur").value]);
    $("#r-adaptateur").onchange();
    if (e.camera?.whep_url && !$("#whep-url").value) $("#whep-url").value = e.camera.whep_url;
  }
  const cond = [
    [e.reel_autorise, "Vol réel autorisé dans config.toml ([drone] reel_autorise)"],
    [!!e.observateur, `Observateur de sécurité déclaré dans la Console${e.observateur ? ` (${e.observateur.initiales})` : ""}`],
    [e.liste_complete && !!e.liste_par, `Liste de contrôle cochée et signée${e.liste_par ? ` (${e.liste_par})` : ""}`],
    [e.mode !== "representation" || e.vol_en_representation, `Mode « ${salle.modes[e.mode]?.libelle} »${e.mode === "salle_vide" ? ` — salle vérifiée vide par ${e.salle_vide_par}` : ""}`],
    [!e.urgence, "Aucun arrêt d'urgence actif"],
    [e.position_mesuree !== false, e.position_mesuree === false ? "Position estimée (Tello) : trajectoires approximatives" : "Position mesurée par l'autopilote"],
  ];
  $("#r-conditions").innerHTML = cond.map(([ok, t]) => `<li class="${ok ? "ok" : ""}">${esc(t)}</li>`).join("");
  $$("#r-liste input").forEach((c) => (c.checked = e.liste.includes(c.value)));
  if (e.liste_par) $("#r-liste-par").value = e.liste_par;
}
$("#r-liste").innerHTML = salle.liste_controle.map((c) => `<li><label><input type="checkbox" value="${c.id}"> ${esc(c.texte)}</label></li>`).join("");
$("#r-liste-signer").onclick = () => envoyer({ op: "drone_liste", coches: $$("#r-liste input:checked").map((c) => c.value), par: $("#r-liste-par").value.trim() }) || journal("refus", "Pont non relié");
$("#r-connecter").onclick = () => envoyer({ op: "drone_connecter", adaptateur: $("#r-adaptateur").value }) || journal("refus", "Pont non relié");
$("#r-deconnecter").onclick = () => envoyer({ op: "drone_deconnecter" });

function ouvrirPont() {
  if (!window.ROBO_PONT || window.ROBO_PONT.forcerSimulation) return;
  let ws;
  try { ws = new WebSocket(window.ROBO_PONT.url); } catch (e) { return; }
  pont.ws = ws;
  ws.onopen = () => {
    pont.ouvert = true; window.ROBO_PONT.ouvert(); journal("info", "Pont relié", "pont");
    pont.dialogue?.pontOuvert();
    envoyer({ op: "drone_etat" }); envoyer({ op: "drone_interpretes", liste: interpretes });
    if (drone.mode !== "salle_vide") envoyer({ op: "drone_mode", mode: drone.mode, par: "" });
    else envoyer({ op: "drone_mode", mode: drone.mode, par: $("#salle-vide-par").value.trim() });
    majReel();
  };
  ws.onmessage = (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (/^(ia_moteurs|ia_choix|dialogue|dialogue_refus|dialogue_oublier)$/.test(m.type)) { pont.dialogue?.recevoir(m); return; }
    if (m.type === "etat") return;           // télémétrie des robots (Console), sans objet ici
    if (m.type === "drone_etat") { pont.etat = m; majReel(); }
    else if (m.type === "drone_tel") { pont.tel = m; pont.telT = performance.now(); }
    else if (m.type === "drone_refus") journal("refus", m.msg, "pont");
    else if (m.type === "drone_aller") journal("info", `Trajet accepté par le pont (${nb(m.duree)} s)`, "pont");
    else if (m.type === "journal" && (/^Drone|ARRÊT|Observateur/.test(m.msg) || m.niveau === "refus")) journal(m.niveau === "info" ? "info" : m.niveau === "avert" ? "avert" : "alerte", m.msg, "pont");
    else if (m.type === "config") { if (pont.etat) { pont.etat.observateur = m.observateur; majReel(); } envoyer({ op: "drone_etat" }); }
  };
  ws.onclose = () => {
    const etait = pont.ouvert; pont.ouvert = false; pont.etat = null; pont.tel = null; window.ROBO_PONT.ferme(); pont.dialogue?.pontFerme();
    if (etait) journal("avert", "Pont déconnecté", "pont");
    majReel(); setTimeout(ouvrirPont, 3000);
  };
}
setInterval(() => { if (pont.ouvert && pont.etat?.adaptateur) envoyer({ op: "drone_hb" }); }, 250);
setInterval(() => { if (pont.ouvert) envoyer({ op: "drone_etat" }); }, 3000);

/* ── Boucle principale ───────────────────────────────────── */
let tPrec = performance.now(), tSim = performance.now(), image = 0, vPrec = [0, 0, 0], incl = [0, 0], dernierEnvoiV = 0, mancheActif = false;
function majStatuts() {
  const s = drone.instantane(), etatTxt = ETATS[s.etat] + (s.urgence ? " · verrou ARRÊT" : "");
  const st = $("#st-etat"); st.textContent = etatTxt;
  st.className = `pastille ${s.urgence || s.etat === "chute" || s.etat === "coupe" ? "alerte" : drone.enVol ? "ok" : "neutre"}`;
  $("#st-mode").textContent = salle.modes[drone.mode].libelle;
  const b = $("#st-batt"); b.textContent = `Batterie ${Math.round(s.batterie)} %`;
  b.className = `pastille ${s.batterie <= salle.regles.batterie_retour_pct ? "alerte" : s.batterie <= salle.regles.batterie_alerte_pct ? "avert" : "neutre"}`;
  $("#st-alt").textContent = `Alt. ${nb(drone.altitude)} m · ${nb(Math.hypot(...drone.v))} m/s`;
  const v = verifier(salle, drone.p, drone.ctx);
  $("#telemetrie").textContent = `x ${nb(s.p[0], 2)}  y ${nb(s.p[1], 2)}  z ${nb(s.p[2], 2)} m   lacet ${nb(s.lacet, 0)}°\n`
    + `v ${s.v.map((x) => nb(x, 2)).join(" ; ")} m/s   zone : ${v.zone || "—"}${v.ok ? "" : ` — ${v.motif}`}\n`
    + `consigne : ${drone.consigne.type}   armé : ${s.arme ? "oui" : "non"}   cible : ${cible}`;
  const t = pont.tel;
  $("#r-tel").textContent = t ? `${t.adaptateur}${t.reel ? " (réel)" : " (simulation du pont)"} · ${t.etat || "?"} · ${t.mode_autopilote || ""}\n`
    + `p ${(t.p || []).map((x) => nb(x, 2)).join(" ; ")} m · lacet ${t.lacet != null ? nb(t.lacet, 0) : "?"}° · batterie ${t.batterie ?? "?"} % · armé ${t.arme ? "oui" : "non"}\n`
    + `position ${t.position || "?"}${t.texte ? ` · ${t.texte}` : ""}` : "—";
}
function boucle() {
  const now = performance.now(), dtReel = Math.min(0.5, (now - tPrec) / 1000), dt = Math.min(0.05, dtReel); tPrec = now; image++;
  const { manche, lacet } = lireManche();
  const actif = manche.some((x) => Math.abs(x) > 0.02) || Math.abs(lacet) > 0.02;
  if (actif && (enCours || toutJouer)) annulerConduite();
  if (actif && cmds.occupe) { cmds.vider(); journal("info", "Commande interrompue par le pilotage manuel"); }
  cmds.pas();
  if (reelActif()) {
    // pilotage du drone réel : consignes de vitesse dans le repère du théâtre, renvoyées à 10 Hz tant que la manette est tenue
    if ((actif || mancheActif) && now - dernierEnvoiV > 100) {
      const ps = drone.lacet, R = salle.regles, [d, a, h] = manche;
      const v = [(Math.sin(ps) * a - Math.cos(ps) * d) * R.vitesse_max_h_m_s, h * R.vitesse_max_v_m_s, (Math.cos(ps) * a + Math.sin(ps) * d) * R.vitesse_max_h_m_s];
      // lacet_vitesse dans la convention du théâtre (positif = antihoraire vu de dessus) : manche à droite → négatif
      envoyer({ op: "drone_vitesse", v, lacet_vitesse: -lacet * R.vitesse_lacet_max_deg_s }); dernierEnvoiV = now;
    }
    mancheActif = actif;
    const t = pont.tel;
    if (t?.p) {          // le drone virtuel devient le jumeau du drone réel
      for (let i = 0; i < 3; i++) drone.p[i] += (t.p[i] - drone.p[i]) * Math.min(1, dt * 10);
      drone.v = (t.v || [0, 0, 0]).slice(); if (t.lacet != null) drone.lacet = rad(t.lacet);
      if (t.batterie != null) drone.batterie = t.batterie;
      drone.etat = ["au_sol", "decollage", "vol", "atterrissage", "chute", "coupe"].includes(t.etat) ? t.etat : drone.etat;
      drone.helices = drone.enVol ? 0.6 : t.arme ? 0.12 : 0;
    }
  } else {
    if (actif || mancheActif) drone.manuel(manche, lacet);
    mancheActif = actif;
    // pas fixes de 20 ms : le temps simulé suit le temps réel même quand l'affichage ralentit
    let reste = Math.min(0.5, (now - tSim) / 1000); tSim = now;
    while (reste > 1e-4) { const h = Math.min(0.02, reste); drone.pas(h); reste -= h; }
  }
  // jumeau : visible quand un drone est relié par le pont et que les commandes vont au virtuel
  const t = pont.tel;
  theatre.jumeau.visible = !!(t?.p && cible === "virtuel");
  if (theatre.jumeau.visible) { theatre.jumeau.position.set(t.p[0], t.p[1] + 0.035, t.p[2]); theatre.jumeau.rotation.y = rad(t.lacet || 0); }
  // inclinaison apparente : accélération dans le repère du drone
  const a = drone.v.map((x, i) => (x - vPrec[i]) / Math.max(dt, 1e-3)); vPrec = drone.v.slice();
  const ps = drone.lacet, af = a[0] * Math.sin(ps) + a[2] * Math.cos(ps), ad = -a[0] * Math.cos(ps) + a[2] * Math.sin(ps);
  incl = [incl[0] + (Math.max(-0.35, Math.min(0.35, af * 0.12)) - incl[0]) * Math.min(1, dt * 8), incl[1] + (Math.max(-0.35, Math.min(0.35, -ad * 0.12)) - incl[1]) * Math.min(1, dt * 8)];
  theatre.poser({ p: drone.p, lacetRad: drone.lacet, helices: drone.helices, inclinaison: drone.enVol ? incl : [0, 0] }, dt);
  suivreConduite();
  theatre.rendre(dtReel);
  if (image % 2 === 0 && source !== "reelle") cam.rendre();
  else if (source === "reelle") theatre.majCameraDrone();
  if (image % 3 === 0) {
    const c = $("#cam-surimp"), r = c.getBoundingClientRect(), k = Math.min(2, devicePixelRatio || 1);
    if (c.width !== Math.round(r.width * k)) { c.width = Math.round(r.width * k); c.height = Math.round(r.height * k); }
    const reel = source !== "virtuelle" && flux.source, rg = reel ? flux.reglages() : null;
    const enr = cam.enregistre ? `REC ${Math.floor((performance.now() - cam.debutEnr) / 60000)}:${String(Math.floor(((performance.now() - cam.debutEnr) / 1000) % 60)).padStart(2, "0")}` : "";
    dessinerCadre(c.getContext("2d"), c.width, c.height, {
      tiers: $("#tiers").checked, horizon: theatre.nacelleTangage, rec: source === "reelle" ? "" : enr,
      texte: reel ? `RÉEL · ${rg.largeur} × ${rg.hauteur}${rg.ips ? ` · ${rg.ips} i/s` : ""} · affichage seul` : `VIRTUEL · aperçu ${cam.definition.join(" × ")} · photo ${UHD.largeur} × ${UHD.hauteur} · ×${nb(theatre.zoom)}`,
      alerte: theatre.publicDansLeChamp() ? "Public dans le champ — aucune captation (G-06)" : "",
    });
  }
  if (image % 6 === 0) majStatuts();
}

/* ── Commandes en langage naturel (voix ou texte) ─────────── */
const ecartAngle = (a, b) => Math.atan2(Math.sin(b - a), Math.cos(b - a));
const attendre = (s) => { const t = performance.now() + s * 1000; return () => performance.now() > t; };
const finTrajet = () => drone.consigne.type !== "trajectoire" && Math.abs(ecartAngle(drone.lacet, drone.lacetCible ?? drone.lacet)) < 0.05;
function cibleRegard(c) { if (c === "salle") return [0, 1.2, 9]; return salle.reperes[c] || null; }
function lancerAction(a) {
  const reel = reelActif();
  const allerPoint = (q, lacetDeg) => {
    const r = allerA(q, { duree: null, lacet: lacetDeg ?? null });
    if (r === false || r?.ok === false) return false;
    return { fin: reel ? attendre(Math.hypot(q[0] - drone.p[0], q[1] - drone.p[1], q[2] - drone.p[2]) / (salle.regles.vitesse_max_h_m_s * 0.5) + 1.5) : finTrajet };
  };
  switch (a.type) {
    case "decoller": { const r = decoller(a.hauteur); if (r === false || r?.ok === false) return false; return { fin: reel ? attendre(4) : () => drone.etat !== "decollage" }; }
    case "atterrir": { const r = atterrir(); if (r === false || r?.ok === false) return false; return { fin: reel ? attendre(4) : () => !drone.enVol }; }
    case "retour": { const r = retour(); if (r === false || r?.ok === false) return false; return { fin: reel ? attendre(8) : () => !drone.retourEnCours || !drone.enVol }; }
    case "arreter": return stationnaire();
    case "go": return go();
    case "point": return allerPoint(a.p);
    case "aller": { const r = salle.reperes[a.repere]; if (!r) { journal("refus", `Repère inconnu : ${a.repere}`); return false; } return allerPoint(r.slice()); }
    case "deplacer": {
      const [x, z] = pointRelatif([drone.p[0], drone.p[2]], drone.lacet, a.droite, a.avant);
      return allerPoint([+x.toFixed(2), +(drone.p[1] + a.haut).toFixed(2), +z.toFixed(2)]);
    }
    case "tourner": return allerPoint(drone.p.map((x) => +x.toFixed(2)), deg(drone.lacet + rad(a.angle)));
    case "regarder": {
      const c = a.cible && cibleRegard(a.cible); if (!c) return true;
      return allerPoint(drone.p.map((x) => +x.toFixed(2)), deg(Math.atan2(c[0] - drone.p[0], c[2] - drone.p[2])));
    }
    default: journal("refus", `Action non prise en charge par le drone : ${a.type}`); return false;
  }
}
const cmds = installerCommandes({
  robot: "drone", reperes: salle.reperes, lancer: lancerAction, journal,
  arreterTout: () => { annulerConduite(); stationnaire(); }, urgence: () => arret(),
  // au sol, un déplacement commence par un décollage (ajouté et annoncé dans le journal)
  preparer: (actions) => {
    const bouge = actions.findIndex((a) => ["point", "aller", "deplacer", "tourner", "regarder"].includes(a.type));
    const dec = actions.findIndex((a) => a.type === "decoller");
    if (bouge >= 0 && !drone.enVol && (dec < 0 || dec > bouge)) actions.splice(bouge, 0, { type: "decoller" });
    return actions;
  },
});

/* ── Dialogue parlé avec une personne (moteur d'IA au choix, voix humaine) ── */
pont.dialogue = installerDialogue({
  conteneur: $("#dialogue"), domaine: "drone", nom: "le drone", profilDefaut: "claire",
  envoyer: (m) => envoyer(m), reperes: () => Object.keys(salle.reperes), decrire, journal,
  contexte: () => `${ETATS[drone.instantane().etat] || drone.instantane().etat}, altitude ${nb(drone.p[1])} m, mode « ${salle.modes[drone.mode].libelle} »${reelActif() ? ", drone réel relié" : ", drone virtuel"}`,
  executerActions: (actions, libelle) => cmds.executerActions(actions, libelle),
});
cmds.dialogue = pont.dialogue;
if (pont.ouvert) pont.dialogue.pontOuvert();

/* ── Démarrage ───────────────────────────────────────────── */
drone.mode = salle.modes[memo.lire("mode", "plateau")] ? memo.lire("mode", "plateau") : "plateau";
if (drone.mode === "salle_vide" && !$("#salle-vide-par").value) drone.mode = "plateau";
theatre.dessinerZones(drone.mode, true);
majModes(); majInterpretes(); majSource(); majCameraLibelles(); recompiler(); majReel();
$("#j-exporter").onclick = () => {
  const d = new Date(), date = d.toISOString().slice(0, 10).replace(/-/g, "");
  const systeme = pont.etat?.adaptateur ? `DRONE-${pont.etat.adaptateur.toUpperCase()}` : "DRONE-VIRTUEL";
  const id = `${date}_${systeme}_VOL_${String(numeroEssai).padStart(3, "0")}`;
  telecharger(new Blob([JSON.stringify({ identifiant: id, systeme, type: "VOL", date: d.toISOString(), salle: { version: salle.version, titre: salle.titre },
    mode: drone.mode, interpretes, conduite, bilan_conduite: comp && { ok: comp.ok, erreurs: comp.erreurs, avertissements: comp.avertissements, duree_s: comp.duree },
    parametres: salle.regles, evenements: journalEv, note: "Aucune image ni vidéo n'est incluse (G-06)." }, null, 2)], { type: "application/json" }), `${id}.json`);
};
journal("info", `Drone virtuel prêt — salle « ${salle.titre} », mode « ${salle.modes[drone.mode].libelle} »`);
theatre.rendu.setAnimationLoop(boucle);
ouvrirPont();
window.ROBO_DRONE = { drone, theatre, salle, compiler: () => comp };   // inspection et essais
