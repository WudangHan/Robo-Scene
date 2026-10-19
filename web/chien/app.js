/* Robo-Scène — page « Chien » : chien de scène virtuel dans le théâtre, console de marche, postures et allures,
   conduite, caméra de tête, sol praticable, liaison au chien réel par le pont. Même logique que la page « Drone » :
   le chien virtuel fonctionne seul dans le navigateur ; le chien réel n'est commandé qu'à travers le pont, qui
   applique le même sol praticable et ses propres conditions de sécurité. */
import { TheatreChien } from "./theatre3d.js";
import { ALLURES, ChienVirtuel, ETATS, POSTURES, deg, rad } from "./chien.js";
import { CONDUITE_EXEMPLE, cibleRegard, compiler } from "./conduite.js";
import { hauteurSol, pointSol, verifierSol, verifierTrajet } from "./sol.js";
import { CameraVirtuelle, FluxReel, UHD, dessinerCadre } from "../drone/camera4k.js";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const nb = (x, d = 1) => Number(x).toLocaleString("fr-CA", { minimumFractionDigits: d, maximumFractionDigits: d });
const memo = {
  lire(k, defaut) { try { const v = localStorage.getItem(`robo-scene-chien-${k}`); return v ? JSON.parse(v) : defaut; } catch (e) { return defaut; } },
  ecrire(k, v) { try { localStorage.setItem(`robo-scene-chien-${k}`, JSON.stringify(v)); } catch (e) { /* stockage indisponible */ } },
};
const MODES = { plateau: "Plateau seul", salle_vide: "Salle vide (répétition)", representation: "Représentation (public présent)" };
const AIDE_MODES = {
  plateau: "Le chien reste sur le plateau, à distance du nez de scène ; escaliers et salle fermés.",
  salle_vide: "Salle vérifiée vide de toute personne : escaliers, avant-salle et allée centrale ouverts.",
  representation: "Public présent : le chien garde 1 m de distance aux rangées (rayon + marge) et ralentit hors du plateau ; l'allée centrale, trop étroite, se ferme d'elle-même.",
};

const salle = await (await fetch("/static/drone/salle.json")).json();
const theatre = new TheatreChien($("#vue3d"), salle);
const journalEv = [];
const chien = new ChienVirtuel(salle, { surEvenement: (e) => journal(e.niveau, e.msg, "virtuel") });
const cam = new CameraVirtuelle($("#cam-virtuelle"), theatre);
const flux = new FluxReel($("#cam-reelle"));
let cible = "virtuel";
let interpretes = memo.lire("interpretes", []);
let conduite = memo.lire("conduite", null) || structuredClone(CONDUITE_EXEMPLE);
let comp = null, prochain = 0, enCours = null, toutJouer = false;
const pont = { ws: null, ouvert: false, etat: null, tel: null };
const numeroEssai = (memo.lire("numero", 0) || 0) + 1; memo.ecrire("numero", numeroEssai);
const hauteur = (x, z) => hauteurSol(salle, x, z, "salle_vide");

/* ── Journal ─────────────────────────────────────────────── */
function journal(niveau, msg, source = "page") {
  const ts = new Date().toLocaleTimeString("fr-CA", { hour12: false });
  journalEv.push({ ts: new Date().toISOString(), niveau, msg, source });
  const li = document.createElement("li");
  li.className = niveau === "alerte" || niveau === "refus" ? "alerte" : niveau === "avert" ? "avert" : "";
  li.textContent = `${ts} · ${source === "pont" ? "[pont] " : ""}${msg}`;
  const ol = $("#journal"); ol.prepend(li); while (ol.children.length > 300) ol.lastChild.remove();
}

/* ── Onglets ─────────────────────────────────────────────── */
function onglet(nom) {
  $$(".onglets [role=tab]").forEach((b) => b.setAttribute("aria-selected", b.dataset.onglet === nom));
  $$(".panneau-onglet").forEach((p) => (p.hidden = p.id !== `ong-${nom}`));
  memo.ecrire("onglet", nom);
}
$$(".onglets [role=tab]").forEach((b) => (b.onclick = () => onglet(b.dataset.onglet)));
onglet(memo.lire("onglet", "marche"));

/* ── Modes, interprètes, règles ─────────────────────────── */
function majModes() {
  $("#modes").innerHTML = Object.entries(MODES).map(([k, l]) => `<label><input type="radio" name="mode" value="${k}"${k === chien.mode ? " checked" : ""}>
    <b>${esc(l)}</b><small>${esc(AIDE_MODES[k])}</small></label>`).join("");
  $$("#modes input").forEach((r) => (r.onchange = () => changerMode(r.value)));
}
function changerMode(m) {
  if (chien.enMouvement) { journal("refus", "Changement de mode refusé pendant la marche"); majModes(); return; }
  if (m === "salle_vide" && !$("#salle-vide-par").value.trim()) {
    $("#salle-vide-par").focus(); journal("avert", "Mode « salle vide » : saisir les initiales de la personne qui a vérifié la salle, puis choisir à nouveau le mode"); majModes(); return;
  }
  chien.mode = m; memo.ecrire("mode", m);
  theatre.dessinerZones(m, $("#voir-zones").checked); majModes(); recompiler();
  journal("info", `Mode : ${MODES[m]}${m === "salle_vide" ? ` (salle vérifiée vide par ${$("#salle-vide-par").value.trim()})` : ""}`);
  envoyer({ op: "chien_mode", mode: m, par: $("#salle-vide-par").value.trim() });
}
$("#salle-vide-par").value = memo.lire("salle_vide_par", "");
$("#salle-vide-par").onchange = () => memo.ecrire("salle_vide_par", $("#salle-vide-par").value.trim());
function majInterpretes() {
  chien.interpretes = interpretes.map((i) => [i.x, i.z]);
  theatre.dessinerInterpretes(interpretes);
  $("#z-interpretes").innerHTML = interpretes.map((it, i) => `<li><span>Interprète ${i + 1} : x ${nb(it.x)} m, z ${nb(it.z)} m</span><button data-i="${i}" aria-label="Retirer l'interprète ${i + 1}">Retirer</button></li>`).join("")
    || `<li class="petit">Aucun interprète déclaré.</li>`;
  $$("#z-interpretes button").forEach((b) => (b.onclick = () => { interpretes.splice(+b.dataset.i, 1); majInterpretes(); }));
  memo.ecrire("interpretes", interpretes); recompiler();
  envoyer({ op: "chien_interpretes", liste: interpretes });
}
$("#z-ajout").onclick = () => { $("#outil-clic").value = "interprete"; journal("info", "Cliquez sur le plateau pour placer un interprète"); };
$("#z-vider").onclick = () => { interpretes = []; majInterpretes(); };
$("#z-tester").onclick = () => {
  const p = $("#z-point").value.split(/[,;\s]+/).filter(Boolean).map(Number);
  const v = verifierSol(salle, p, chien.ctx), el = $("#z-verdict");
  el.className = `message ${v.ok ? "ok" : "erreur"}`; el.textContent = v.ok ? `Point permis (${v.surface}, sol à ${nb(hauteur(p[0], p[1]), 2)} m)` : v.motif;
};
$("#regles").innerHTML = (() => {
  const R = salle.sol.regles;
  return `<ul>
    <li>Gabarit du robot : carré de ${nb(R.rayon_m)} m de demi-côté, tout entier sur le sol praticable ; obstacles au sol : cadre de scène et décor déclaré</li>
    <li>Distance au public en représentation : ${nb(R.rayon_m + R.marge_public_m)} m du centre du robot aux rangées</li>
    <li>Cercle des interprètes : ${nb(R.rayon_interpretes_m)} m</li>
    <li>Vitesses : ${salle.sol.surfaces.map((s) => `${s.libelle.toLowerCase()} ${nb(s.vitesse_max_m_s)} m/s`).join(" ; ")} ; ${nb(R.vitesse_max_representation_m_s)} m/s hors du plateau en représentation ; accélération ${nb(R.acceleration_max_m_s2)} m/s²</li>
    <li>Batterie : alerte ${R.batterie_alerte_pct} %, retour ${R.batterie_retour_pct} %, couché ${R.batterie_critique_pct} % ; autonomie modélisée ${R.autonomie_min} min</li>
    <li>Perte de liaison : arrêt après ${nb(R.perte_liaison_arret_s)} s, couché après ${nb(R.perte_liaison_coucher_s)} s</li></ul>`;
})();

/* ── Clic dans le théâtre ────────────────────────────────── */
theatre.surClic = (p) => {
  const outil = $("#outil-clic").value, q = [+p[0].toFixed(2), +p[2].toFixed(2)];
  if (outil === "interprete") {
    if (q[1] > salle.volumes.plateau.z[1]) { journal("refus", "Les interprètes se placent sur le plateau"); return; }
    interpretes.push({ x: q[0], z: q[1] }); majInterpretes(); $("#outil-clic").value = "";
  } else if (outil === "aller") allerA(q, {});
  else if (outil === "regarder") regarder([q[0], (hauteur(q[0], q[1]) ?? 0) + 0.3, q[1]]);
};

/* ── Commandes : virtuel ou réel ─────────────────────────── */
function envoyer(m) { if (pont.ouvert) { try { pont.ws.send(JSON.stringify(m)); return true; } catch (e) { /* pont fermé */ } } return false; }
const reelActif = () => cible === "reel" && pont.ouvert && pont.etat?.adaptateur;
function lever() { return reelActif() ? envoyer({ op: "chien_posture", posture: "debout" }) : chien.lever(); }
function coucher() { annulerConduite(); return reelActif() ? envoyer({ op: "chien_posture", posture: "couche" }) : chien.coucher(); }
function arreter() { annulerConduite(); return reelActif() ? envoyer({ op: "chien_arreter" }) : chien.arreter(); }
function posture(nom) { return reelActif() ? envoyer({ op: "chien_posture", posture: nom }) : chien.prendrePosture(nom); }
function allure(nom) { envoyer({ op: "chien_allure", allure: nom }); const r = chien.choisirAllure(nom); majPuces(); return r; }
function regarder(p) { chien.regarder(p); theatre.viser = null; return { ok: true }; }
function retour() {
  annulerConduite();
  if (reelActif()) return envoyer({ op: "chien_aller", p: "depart" });
  return chien.retour();
}
function allerA(p, o = {}) {
  if (reelActif()) return envoyer({ op: "chien_aller", p, duree: o.duree || null, lacet: o.lacet ?? null });
  const s = verifierTrajet(salle, chien.p, p, chien.ctx);
  if (!s.ok) { journal("refus", `Trajet refusé à ${Math.round(s.fraction * 100)} % : ${s.motif}`); return { ok: false }; }
  return chien.allerA(p, { duree: o.duree || undefined, lacet: o.lacet === null || o.lacet === undefined ? undefined : rad(o.lacet) });
}
function arret() { annulerConduite(); chien.arretUrgence("bouton ARRÊT de la page Chien"); envoyer({ op: "estop", motif: "ARRÊT de la page Chien" }); }
function rearmer() {
  const r = chien.rearmer();
  if (pont.ouvert && pont.etat?.urgence && window.confirm("Réarmer toute la plateforme (robots, drone et chien) ? Le réarmement est une action volontaire et distincte.")) envoyer({ op: "rearmer" });
  return r;
}
$("#b-lever").onclick = lever; $("#b-coucher").onclick = coucher; $("#b-arreter").onclick = arreter;
$("#b-retour").onclick = retour; $("#b-rearmer").onclick = rearmer; $("#btn-arret").onclick = arret;
$("#b-batterie").onclick = () => chien.changerBatterie();
$("#yeux").oninput = () => theatre.couleurYeux($("#yeux").value);
$("#postures").innerHTML = Object.entries(POSTURES).map(([k, p]) => `<button data-posture="${k}">${esc(p.libelle)}</button>`).join("");
$("#allures").innerHTML = Object.entries(ALLURES).map(([k, a]) => `<button data-allure="${k}">${esc(a.libelle)}</button>`).join("");
$$("#postures button").forEach((b) => (b.onclick = () => posture(b.dataset.posture)));
$$("#allures button").forEach((b) => (b.onclick = () => allure(b.dataset.allure)));
function majPuces() {
  $$("#postures button").forEach((b) => b.classList.toggle("actif", b.dataset.posture === chien.posture));
  $$("#allures button").forEach((b) => b.classList.toggle("actif", b.dataset.allure === chien.allure));
}
$("#b-aller").onclick = () => { try { allerA(pointSol(salle, $("#aller-repere").value), { duree: Number($("#aller-duree").value) || null }); } catch (e) { journal("refus", e.message); } };
$$("input[name=cible]").forEach((r) => (r.onchange = () => {
  cible = r.value;
  journal("info", cible === "reel" ? "Les commandes vont désormais au chien réel ; le chien virtuel suit sa télémétrie" : "Les commandes vont au chien virtuel");
}));
const dlg = $("#d-coupure");
$("#b-coupure").onclick = () => { $("#d-coupure-texte").value = ""; dlg.showModal(); };
dlg.addEventListener("close", () => {
  if (dlg.returnValue !== "ok") return;
  const c = $("#d-coupure-texte").value.trim(); annulerConduite();
  if (reelActif()) envoyer({ op: "chien_coupure", confirmation: c }); else chien.couperMoteurs(c);
});
for (const id of Object.keys(salle.sol.reperes)) $("#aller-repere").insertAdjacentHTML("beforeend", `<option value="${id}">${esc(id.replace(/_/g, " "))}</option>`);
for (const id of Object.keys(salle.sol.reperes)) $("#viser").insertAdjacentHTML("beforeend", `<option value="${id}">${esc(id.replace(/_/g, " "))}</option>`);
$("#aller-repere").value = "centre";

/* ── Manettes, clavier, manette de jeu ──────────────────── */
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
  if (k === " ") { e.preventDefault(); arreter(); return; }
  if (k === "u") { lever(); return; }
  if (k === "j") { coucher(); return; }
  if (k === "h") { retour(); return; }
  if (k === "enter" && !$("#ong-conduite").hidden) { e.preventDefault(); go(); return; }
  if (["w", "a", "s", "d", "q", "e", "arrowup", "arrowdown", "arrowleft", "arrowright"].includes(k)) { e.preventDefault(); touches.add(k); }
});
window.addEventListener("keyup", (e) => touches.delete(e.key.toLowerCase()));
window.addEventListener("blur", () => touches.clear());
let boutonsPrec = [];
function lireManche() {
  const k = (a, b) => (touches.has(a) ? 1 : 0) - (touches.has(b) ? 1 : 0);
  let droite = k("d", "a") + manettes.d[0], avant = k("w", "s") + k("arrowup", "arrowdown") + manettes.d[1];
  let rotation = k("e", "q") + k("arrowright", "arrowleft") + manettes.g[0];
  const gp = navigator.getGamepads ? [...navigator.getGamepads()].filter(Boolean)[0] : null;
  if (gp) {
    const z = (v) => (Math.abs(v) < 0.12 ? 0 : v);
    rotation += z(gp.axes[0] || 0); droite += z(gp.axes[2] || 0); avant += -z(gp.axes[3] || 0);
    const b = gp.buttons.map((x) => x.pressed), front = (i) => b[i] && !boutonsPrec[i];
    if (front(0)) lever(); if (front(1)) coucher(); if (front(2)) arreter(); if (front(3)) retour();
    boutonsPrec = b;
  }
  const c = (v) => Math.max(-1, Math.min(1, v));
  return { manche: [c(droite), c(avant)], rotation: c(rotation) };
}

/* ── Conduite ────────────────────────────────────────────── */
function detail(s) {
  if (s.action === "aller") return `vers ${s.p1.map((x) => nb(x)).join(" ; ")}`;
  if (s.action === "posture") return POSTURES[s.posture]?.libelle || "";
  if (s.action === "allure") return ALLURES[s.allure]?.libelle || "";
  if (s.action === "tourner") return `lacet ${s.lacet ?? "—"}°`;
  if (s.action === "regarder") return s.regard ? s.regard.map((x) => nb(x)).join(" ; ") : "droit devant";
  return s.note || "";
}
function recompiler() {
  comp = compiler(salle, conduite, salle.sol.aire.centre, { mode: chien.mode, interpretes: chien.interpretes });
  theatre.dessinerTrajet(comp, hauteur);
  const b = $("#c-bilan");
  b.className = `note${comp.ok ? "" : " erreur"}`;
  b.innerHTML = `<b>${esc(conduite.titre || "Conduite")}</b> — ${comp.segments.length} repères, ${nb(comp.duree)} s en mode « ${esc(MODES[chien.mode])} » : `
    + (comp.ok ? "<span>valide</span>" : "<span class=\"erreur\">GO bloqué</span>")
    + (comp.erreurs.length ? `<ul>${comp.erreurs.map((e) => `<li class="erreur">${esc(e)}</li>`).join("")}</ul>` : "")
    + (comp.avertissements.length ? `<ul>${comp.avertissements.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>` : "");
  $("#c-table tbody").innerHTML = comp.segments.map((s, i) => `<tr class="${i === prochain ? "courant" : i < prochain ? "fait" : ""}">
    <td><b>${esc(s.id)}</b> ${esc(s.nom)}</td><td>${esc(s.action)}</td><td>${esc(detail(s))}</td><td>${nb(s.T)} s</td>
    <td><button data-i="${i}" class="discret" title="Jouer ce repère">▶</button></td></tr>`).join("");
  $$("#c-table button").forEach((x) => (x.onclick = () => { prochain = +x.dataset.i; go(); }));
  $("#c-go").disabled = !comp.ok;
  $("#c-prochain").textContent = comp.segments[prochain] ? `Prochain : ${comp.segments[prochain].id} ${comp.segments[prochain].nom}` : "Fin de la conduite";
  $("#c-json").value = JSON.stringify(conduite, null, 2);
  memo.ecrire("conduite", conduite);
}
function annulerConduite() { if (enCours || toutJouer) journal("avert", "Conduite interrompue"); enCours = null; toutJouer = false; $("#etat-conduite").textContent = ""; }
function go() {
  if (!comp?.ok) { journal("refus", "GO bloqué : conduite invalide (voir le bilan)"); return; }
  const s = comp.segments[prochain];
  if (!s) { journal("info", "Fin de la conduite"); return; }
  let r;
  switch (s.action) {
    case "lever": r = lever(); break;
    case "coucher": r = coucher(); break;
    case "posture": r = posture(s.posture); break;
    case "allure": r = allure(s.allure); break;
    case "aller": r = allerA(s.p1, { duree: s.T - 0.6, lacet: s.lacet }); break;
    case "tourner": r = reelActif() ? envoyer({ op: "chien_aller", p: s.p1, lacet: s.lacet }) : chien.tourner(rad(s.lacet ?? 0)); break;
    case "regarder": r = regarder(s.regard); envoyer({ op: "chien_regard", regard: s.regard }); break;
    default: r = { ok: true };
  }
  if (r === false || (r && r.ok === false)) { toutJouer = false; return; }
  enCours = { i: prochain, t0: performance.now(), T: s.T, action: s.action };
  journal("info", `GO ${s.id} — ${s.nom || s.action}${s.note ? ` (${s.note})` : ""}`);
  $("#repere-courant").textContent = `${s.id} ${s.nom}`;
  prochain += 1; recompiler(); majPuces();
}
function suivreConduite() {
  if (!enCours) return;
  const ecoule = (performance.now() - enCours.t0) / 1000;
  $("#etat-conduite").textContent = `${nb(Math.min(ecoule, enCours.T))} / ${nb(enCours.T)} s`;
  const fini = ecoule >= enCours.T + 0.1 && (reelActif() || chien.consigne.type !== "trajectoire");
  if (!fini) return;
  enCours = null; $("#etat-conduite").textContent = "";
  if (toutJouer && prochain < comp.segments.length) setTimeout(() => toutJouer && go(), 250); else toutJouer = false;
}
$("#c-go").onclick = go;
$("#c-tout").onclick = () => { if (!comp?.ok) return go(); toutJouer = true; if (!enCours) go(); };
$("#c-retour").onclick = () => { annulerConduite(); prochain = 0; recompiler(); };
$("#c-exemple").onclick = () => { conduite = structuredClone(CONDUITE_EXEMPLE); prochain = 0; recompiler(); };
$("#c-valider").onclick = () => { recompiler(); journal(comp.ok ? "info" : "refus", comp.ok ? "Conduite valide" : `Conduite invalide : ${comp.erreurs[0]}`); };
$("#c-appliquer").onclick = () => { try { conduite = JSON.parse($("#c-json").value); prochain = 0; recompiler(); journal("info", "Texte de la conduite appliqué"); } catch (e) { journal("refus", `JSON invalide : ${e.message}`); } };
$("#c-fichier").onchange = async (e) => { const f = e.target.files[0]; if (!f) return; try { conduite = JSON.parse(await f.text()); prochain = 0; recompiler(); journal("info", `Conduite « ${f.name} » chargée`); } catch (err) { journal("refus", `Fichier illisible : ${err.message}`); } };
const telecharger = (blob, nom) => { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = nom; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); };
$("#c-exporter").onclick = () => telecharger(new Blob([JSON.stringify(conduite, null, 2)], { type: "application/json" }), `conduite_chien_${new Date().toISOString().slice(0, 10)}.json`);

/* ── Caméra ──────────────────────────────────────────────── */
$("#zoom").oninput = () => { theatre.zoom = Number($("#zoom").value); $("#zoom-val").textContent = `×${nb(theatre.zoom)}`; };
$("#viser").onchange = () => { const v = $("#viser").value; chien.regarder(v ? cibleRegard(salle, v) : null); };
$("#definition").onchange = () => { const [w, h] = $("#definition").value.split("x").map(Number); cam.regler(w, h); };
$("#b-photo").onclick = async () => {
  const blob = await cam.photo4K();
  telecharger(blob, `chien_virtuel_${UHD.largeur}x${UHD.hauteur}_${new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19)}.png`);
  journal("info", `Image virtuelle 4K enregistrée (${UHD.largeur} × ${UHD.hauteur})`);
};
$("#b-rec").onclick = async () => {
  if (cam.enregistre) {
    const blob = await cam.arreterEnregistrement(); $("#b-rec").textContent = "● Enregistrer"; $("#b-rec").setAttribute("aria-pressed", "false");
    if (blob) telecharger(blob, `chien_virtuel_${cam.definition.join("x")}_${new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19)}.webm`);
  } else {
    try { cam.demarrerEnregistrement(30); $("#b-rec").textContent = "■ Arrêter"; $("#b-rec").setAttribute("aria-pressed", "true"); } catch (e) { journal("refus", e.message); }
  }
};
let source = "virtuelle";
function majSource() {
  source = $("input[name=source]:checked").value;
  $("#pip").classList.toggle("superposee", source === "superposee");
  $("#cam-reelle").hidden = source === "virtuelle"; $("#cam-virtuelle").hidden = source === "reelle";
  $("#pip-titre").textContent = { virtuelle: "Caméra de tête (virtuelle)", reelle: "Caméra du chien réel", superposee: "Réelle + virtuelle superposées" }[source];
}
$$("input[name=source]").forEach((r) => (r.onchange = majSource));
$("#pip-taille").onclick = () => $("#pip").classList.toggle("grand");
async function listerCameras() {
  try { const l = await FluxReel.cameras(); $("#cam-liste").innerHTML = `<option value="">Carte de capture HDMI / webcam…</option>` + l.map((d, i) => `<option value="${esc(d.deviceId)}">${esc(d.label || `Source vidéo ${i + 1}`)}</option>`).join(""); } catch (e) { /* aucune source */ }
}
const infoCam = (r) => { $("#cam-info").textContent = r.largeur ? `Flux réel : ${r.largeur} × ${r.hauteur}${r.ips ? ` à ${r.ips} i/s` : ""}${r.nom ? ` · ${r.nom}` : ""}` : "Flux ouvert, en attente d'images…"; };
$("#b-capture").onclick = async () => { try { infoCam(await flux.ouvrirCapture($("#cam-liste").value || undefined)); $("input[name=source][value=reelle]").checked = true; majSource(); listerCameras(); } catch (e) { $("#cam-info").textContent = e.message; } };
$("#b-whep").onclick = async () => {
  const url = $("#whep-url").value.trim(); if (!url) return; memo.ecrire("whep", url);
  try { $("#cam-info").textContent = "Connexion WHEP…"; infoCam(await flux.ouvrirWHEP(url)); $("input[name=source][value=reelle]").checked = true; majSource(); } catch (e) { $("#cam-info").textContent = e.message; }
};
$("#b-cam-fermer").onclick = async () => { await flux.fermer(); $("#cam-info").textContent = "—"; $("input[name=source][value=virtuelle]").checked = true; majSource(); };
$("#whep-url").value = memo.lire("whep", "");
listerCameras();

/* ── Vues ────────────────────────────────────────────────── */
$$("[data-vue]").forEach((b) => (b.onclick = () => theatre.vue(b.dataset.vue)));
$("#voir-zones").onchange = () => (theatre.groupeZones.visible = theatre.groupeTrajet.visible = $("#voir-zones").checked);
$("#voir-poursuite").onchange = () => theatre.poursuiteSur($("#voir-poursuite").checked);
$("#btn-scene").onclick = () => document.body.classList.toggle("mode-scene");

/* ── Liaison avec le pont (chien réel) ──────────────────── */
function majReel() {
  const e = pont.etat;
  $("#r-pont").textContent = pont.ouvert ? `Pont : relié (${window.ROBO_PONT.url})` : "Pont : non relié — le chien virtuel fonctionne sans pont ; la liaison au chien réel en dépend.";
  $("#cible-reel").disabled = !(pont.ouvert && e?.adaptateur);
  if ($("#cible-reel").disabled && cible === "reel") { $("input[name=cible][value=virtuel]").checked = true; cible = "virtuel"; }
  const st = $("#st-reel");
  st.textContent = !pont.ouvert ? "Chien réel : pont absent" : !e?.adaptateur ? "Chien réel : non relié" : `${e.reel ? "Chien réel" : "Pont (simulation)"} : ${e.adaptateur}`;
  st.className = `pastille ${!e?.adaptateur ? "neutre" : e.urgence ? "alerte" : e.reel ? "ok" : "avert"}`;
  if (!e) { $("#r-conditions").innerHTML = ""; return; }
  if (!$("#r-adaptateur").options.length) {
    $("#r-adaptateur").innerHTML = Object.entries(e.adaptateurs).map(([k, d]) => `<option value="${k}" title="${esc(d)}">${k}</option>`).join("");
    $("#r-adaptateur").onchange = () => ($("#r-desc").textContent = e.adaptateurs[$("#r-adaptateur").value]);
    $("#r-adaptateur").onchange();
    if (e.camera?.whep_url && !$("#whep-url").value) $("#whep-url").value = e.camera.whep_url;
  }
  const cond = [
    [e.reel_autorise, "Marche réelle autorisée dans config.toml ([chien] reel_autorise)"],
    [!!e.observateur, `Observateur de sécurité déclaré dans la Console${e.observateur ? ` (${e.observateur.initiales})` : ""}`],
    [e.liste_complete && !!e.liste_par, `Liste de contrôle cochée et signée${e.liste_par ? ` (${e.liste_par})` : ""}`],
    [e.mode !== "representation" || e.marche_en_representation, `Mode « ${MODES[e.mode]} »${e.mode === "salle_vide" ? ` — salle vérifiée vide par ${e.salle_vide_par}` : ""}`],
    [!e.urgence, "Aucun arrêt d'urgence actif"],
    [e.position_mesuree !== false, e.position_mesuree === false ? "Position estimée (marche en boucle ouverte) : trajets approximatifs" : "Position mesurée (odométrie du robot)"],
  ];
  $("#r-conditions").innerHTML = cond.map(([ok, t]) => `<li class="${ok ? "ok" : ""}">${esc(t)}</li>`).join("");
  $$("#r-liste input").forEach((c) => (c.checked = e.liste.includes(c.value)));
  if (e.liste_par) $("#r-liste-par").value = e.liste_par;
}
$("#r-liste").innerHTML = salle.sol.liste_controle.map((c) => `<li><label><input type="checkbox" value="${c.id}"> ${esc(c.texte)}</label></li>`).join("");
$("#r-liste-signer").onclick = () => envoyer({ op: "chien_liste", coches: $$("#r-liste input:checked").map((c) => c.value), par: $("#r-liste-par").value.trim() }) || journal("refus", "Pont non relié");
$("#r-connecter").onclick = () => envoyer({ op: "chien_connecter", adaptateur: $("#r-adaptateur").value }) || journal("refus", "Pont non relié");
$("#r-deconnecter").onclick = () => envoyer({ op: "chien_deconnecter" });

function ouvrirPont() {
  if (!window.ROBO_PONT || window.ROBO_PONT.forcerSimulation) return;
  let ws;
  try { ws = new WebSocket(window.ROBO_PONT.url); } catch (e) { return; }
  pont.ws = ws;
  ws.onopen = () => {
    pont.ouvert = true; window.ROBO_PONT.ouvert(); journal("info", "Pont relié", "pont");
    envoyer({ op: "chien_etat" }); envoyer({ op: "chien_interpretes", liste: interpretes });
    envoyer({ op: "chien_mode", mode: chien.mode, par: chien.mode === "salle_vide" ? $("#salle-vide-par").value.trim() : "" });
    majReel();
  };
  ws.onmessage = (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.type === "etat" || m.type === "drone_tel") return;
    if (m.type === "chien_etat") { pont.etat = m; majReel(); }
    else if (m.type === "chien_tel") pont.tel = m;
    else if (m.type === "chien_refus") journal("refus", m.msg, "pont");
    else if (m.type === "chien_aller") journal("info", `Trajet accepté par le pont (${nb(m.duree)} s)`, "pont");
    else if (m.type === "journal" && (/^Chien|ARRÊT|Observateur/.test(m.msg) || m.niveau === "refus")) journal(m.niveau === "info" ? "info" : m.niveau === "avert" ? "avert" : "alerte", m.msg, "pont");
    else if (m.type === "config") envoyer({ op: "chien_etat" });
  };
  ws.onclose = () => {
    const etait = pont.ouvert; pont.ouvert = false; pont.etat = null; pont.tel = null; window.ROBO_PONT.ferme();
    if (etait) journal("avert", "Pont déconnecté", "pont");
    majReel(); setTimeout(ouvrirPont, 3000);
  };
}
setInterval(() => { if (pont.ouvert && pont.etat?.adaptateur) envoyer({ op: "chien_hb" }); }, 250);
setInterval(() => { if (pont.ouvert) envoyer({ op: "chien_etat" }); }, 3000);

/* ── Boucle principale ───────────────────────────────────── */
let tPrec = performance.now(), tSim = tPrec, image = 0, dernierEnvoiV = 0, mancheActif = false;
function majStatuts() {
  const s = chien.instantane();
  const st = $("#st-etat"); st.textContent = (ETATS[s.etat] || s.etat) + (s.etat === "posture" ? ` · ${POSTURES[s.posture].libelle.toLowerCase()}` : "") + (s.urgence ? " · verrou ARRÊT" : "");
  st.className = `pastille ${s.urgence || s.etat === "affaisse" ? "alerte" : s.etat === "debout" || s.etat === "posture" ? "ok" : "neutre"}`;
  $("#st-mode").textContent = MODES[chien.mode];
  const b = $("#st-batt"); b.textContent = `Batterie ${Math.round(s.batterie)} %`;
  b.className = `pastille ${s.batterie <= salle.sol.regles.batterie_retour_pct ? "alerte" : s.batterie <= salle.sol.regles.batterie_alerte_pct ? "avert" : "neutre"}`;
  $("#st-vit").textContent = `${nb(Math.hypot(...chien.v))} m/s · ${(s.surface || "hors sol").replace(/_/g, " ")}`;
  const v = verifierSol(salle, chien.p, chien.ctx);
  $("#telemetrie").textContent = `x ${nb(s.p[0], 2)}  z ${nb(s.p[2], 2)} m   corps à ${nb(s.p[1], 2)} m   lacet ${nb(s.lacet, 0)}°\n`
    + `v ${s.v.map((x) => nb(x, 2)).join(" ; ")} m/s   ${v.ok ? `sol : ${v.surface}` : `hors zone — ${v.motif}`}\n`
    + `posture : ${POSTURES[s.posture].libelle}   allure : ${ALLURES[s.allure].libelle}   consigne : ${chien.consigne.type}   cible : ${cible}`;
  const t = pont.tel;
  $("#r-tel").textContent = t ? `${t.adaptateur}${t.reel ? " (réel)" : " (simulation du pont)"} · ${t.etat || "?"} · ${t.posture || ""}\n`
    + `p ${(t.p || []).map((x) => nb(x, 2)).join(" ; ")} m · lacet ${t.lacet != null ? nb(t.lacet, 0) : "?"}° · batterie ${t.batterie ?? "?"} %\n`
    + `position ${t.position || "?"}` : "—";
  majPuces();
}
function boucle() {
  const now = performance.now(), dtReel = Math.min(0.5, (now - tPrec) / 1000); tPrec = now; image++;
  const { manche, rotation } = lireManche();
  const actif = manche.some((x) => Math.abs(x) > 0.02) || Math.abs(rotation) > 0.02;
  if (actif && (enCours || toutJouer)) annulerConduite();
  if (reelActif()) {
    if ((actif || mancheActif) && now - dernierEnvoiV > 100) {
      // consignes de vitesse dans le repère du corps du robot : [avant, gauche] m/s, lacet °/s (positif : antihoraire)
      const vmax = 0.8, [d, a] = manche;
      envoyer({ op: "chien_vitesse", v: [a * vmax, -d * vmax], lacet_vitesse: -rotation * salle.sol.regles.vitesse_lacet_max_deg_s });
      dernierEnvoiV = now;
    }
    mancheActif = actif;
    const t = pont.tel;
    if (t?.p) {   // le chien virtuel devient le jumeau du chien réel
      chien.p[0] += (t.p[0] - chien.p[0]) * Math.min(1, dtReel * 10); chien.p[1] += (t.p[2] - chien.p[1]) * Math.min(1, dtReel * 10);
      if (t.lacet != null) chien.lacet = rad(t.lacet); chien.v = (t.v || [0, 0]).slice(0, 2);
      if (t.batterie != null) chien.batterie = t.batterie;
      if (t.posture && t.posture !== chien.posture && POSTURES[t.posture]) chien.changerPosture(t.posture);
      chien.etat = t.etat === "debout" || t.etat === "marche" ? "debout" : t.etat === "couche" ? "couche" : t.etat === "affaisse" ? "affaisse" : chien.etat;
    }
    chien.calculerPose(Math.min(0.05, dtReel));
  } else {
    if (actif || mancheActif) chien.marcher(manche, rotation);
    mancheActif = actif;
    let reste = Math.min(0.5, (now - tSim) / 1000); tSim = now;
    while (reste > 1e-4) { const h = Math.min(0.02, reste); chien.pas(h); reste -= h; }
  }
  const t = pont.tel;
  if (t?.p && cible === "virtuel") theatre.poserJumeau(t, chien); else theatre.jumeau.visible = false;
  theatre.poserChien(chien);
  suivreConduite();
  theatre.rendre(dtReel);
  if (image % 2 === 0 && source !== "reelle") cam.rendre(); else if (source === "reelle") theatre.majCameraDrone();
  if (image % 3 === 0) {
    const c = $("#cam-surimp"), r = c.getBoundingClientRect(), k = Math.min(2, devicePixelRatio || 1);
    if (c.width !== Math.round(r.width * k)) { c.width = Math.round(r.width * k); c.height = Math.round(r.height * k); }
    const reel = source !== "virtuelle" && flux.source, rg = reel ? flux.reglages() : null;
    const enr = cam.enregistre ? `REC ${Math.floor((performance.now() - cam.debutEnr) / 60000)}:${String(Math.floor(((performance.now() - cam.debutEnr) / 1000) % 60)).padStart(2, "0")}` : "";
    dessinerCadre(c.getContext("2d"), c.width, c.height, {
      tiers: $("#tiers").checked, rec: source === "reelle" ? "" : enr,
      texte: reel ? `RÉEL · ${rg.largeur} × ${rg.hauteur}${rg.ips ? ` · ${rg.ips} i/s` : ""} · affichage seul` : `VIRTUEL · tête · aperçu ${cam.definition.join(" × ")} · ×${nb(theatre.zoom)}`,
      alerte: theatre.publicDansLeChamp() ? "Public dans le champ — aucune captation (G-06)" : "",
    });
  }
  if (image % 6 === 0) majStatuts();
}

/* ── Démarrage ───────────────────────────────────────────── */
chien.mode = MODES[memo.lire("mode", "plateau")] ? memo.lire("mode", "plateau") : "plateau";
if (chien.mode === "salle_vide" && !$("#salle-vide-par").value) chien.mode = "plateau";
theatre.dessinerZones(chien.mode, true);
majModes(); majInterpretes(); majSource(); recompiler(); majReel(); majPuces();
$("#j-exporter").onclick = () => {
  const d = new Date(), date = d.toISOString().slice(0, 10).replace(/-/g, "");
  const systeme = pont.etat?.adaptateur ? `CHIEN-${pont.etat.adaptateur.toUpperCase()}` : "CHIEN-VIRTUEL";
  const id = `${date}_${systeme}_MARCHE_${String(numeroEssai).padStart(3, "0")}`;
  telecharger(new Blob([JSON.stringify({ identifiant: id, systeme, type: "MARCHE", date: d.toISOString(), salle: { version: salle.version, titre: salle.titre },
    mode: chien.mode, interpretes, conduite, bilan_conduite: comp && { ok: comp.ok, erreurs: comp.erreurs, avertissements: comp.avertissements, duree_s: comp.duree },
    parametres: salle.sol.regles, evenements: journalEv, note: "Aucune image ni vidéo n'est incluse (G-06)." }, null, 2)], { type: "application/json" }), `${id}.json`);
};
journal("info", `Chien virtuel prêt — salle « ${salle.titre} », mode « ${MODES[chien.mode]} »`);
theatre.rendu.setAnimationLoop(boucle);
ouvrirPont();
window.ROBO_CHIEN = { chien, theatre, salle, compiler: () => comp };
void deg;
