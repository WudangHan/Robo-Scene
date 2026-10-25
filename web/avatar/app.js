/* Robo-Scène — page « Robot virtuel » : assemblage de la scène, des directives écrites et
   vocales, des émotions, de la parole, de l'apparence, de l'imitation et des liaisons
   (page Partenaire, pont local, robot physique). */
import * as THREE from "three";
import { Humanoide, APPARENCE_DEFAUT, CHAMPS_HABILLAGE, PEAUX, YEUX } from "./humanoide.js";
import { Animateur } from "./animation.js";
import { Scene, LIBELLES_ZONES, DOFS_ZONE } from "./scene.js";
import { Parole, estEcho } from "./parole.js";
import { Imitation, lireEmotion } from "./imitation.js";
import { EMOTIONS, prosodie } from "./emotions.js";
import { interpreter, valider, EXEMPLES } from "./directives.js";
import { OBJETS, POSTURES, MANIERES, CAPTEURS, NOMS_OBJETS, article } from "./mains.js";
import { CameraVirtuelle, FluxReel, dessinerCadre } from "../drone/camera4k.js";
import { installerDialogue } from "../dialogue.js";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const echapper = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const attendre = (ms) => new Promise((r) => setTimeout(r, ms));
const lireLS = (k, d) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } };
const ecrireLS = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };

const SCHEMA = await (await fetch(new URL("./schema.json", import.meta.url))).json();
const humain = new Humanoide(SCHEMA);
const anim = new Animateur(humain, SCHEMA);
const scene = new Scene($("#vue3d"), humain, anim);
const parole = new Parole();
const ditsRecemment = [];          // {texte, t} : phrases dites par le robot depuis 15 s (anti-écho de la dictée)
let dicteeRef = null;              // renseigné plus bas (Dictee), avant toute parole
const imitation = new Imitation();
let vueRobot = null;               // ce que voit le robot (caméra des yeux et caméra réelle), défini plus bas
humain.appliquerApparence(lireLS("robo-scene-avatar-apparence", {}));

/* ══════════ Exposition minimale (tests et console de développement) ══════════ */
window.ROBOT_VIRTUEL = { humain, anim, scene, parole, executer: (t) => executerTexte(t, "test"), SCHEMA };

/* hauteur réelle de l'en-tête (la navigation de la plateforme peut passer sur deux lignes) */
const majBarre = () => document.documentElement.style.setProperty("--barre", `${(document.querySelector("header.barre")?.offsetHeight || 60) + 14}px`);
new ResizeObserver(majBarre).observe(document.querySelector("header.barre")); majBarre();

/* ══════════ Boucle ══════════ */
parole.surBattement = (m) => anim.battre(m.n >= 9 ? 1 : 0.7);
scene.avantImage = (dt, t) => {
  const bouche = parole.maj(dt);
  if (imitation.actif) {
    const o = imitation.lire();
    anim.imitation = o ? { pose: o.pose, au: imitation.visage ? o.au : null, regard: o.regard } : null;
    if (o?.au && ++compteurLecture % 15 === 0) afficherLecture(o.au);
  } else anim.imitation = null;
  anim.maj(dt, t, bouche);
  majMains();
  jumeau.maj();
  vueRobot?.rendre();
};
let compteurLecture = 0;
scene.demarrer();
anim.prendrePose("repos");
scene.vue("face", 0.01);

/* ══════════ Sous-titres et journal ══════════ */
function sousTitre(texte) {
  const st = $("#sous-titre");
  st.textContent = texte || ""; st.hidden = !texte;
}
function etiquetteEmotion() {
  const e = anim.emotion;
  $("#etat-emotion").textContent = e.nom === "neutre" || !e.intensite ? "neutre" : `${e.nom} · ${Math.round(e.intensite * 10) / 10}/10`;
  const eff = anim.effort(), ax = ["Poids", "Temps", "Espace", "Flux"], bornes = [["léger", "fort"], ["soutenu", "soudain"], ["indirect", "direct"], ["libre", "contenu"]];
  $("#effort").innerHTML = eff.map((v, i) => `<div class="effort"><span>${ax[i]}</span><i style="--v:${(v + 1) / 2}"></i><small>${v < -0.15 ? bornes[i][0] : v > 0.15 ? bornes[i][1] : "—"}</small></div>`).join("");
}
anim.surChangement(etiquetteEmotion); etiquetteEmotion();

function journal(entree) {
  const li = document.createElement("li");
  li.className = entree.classe || "";
  const d = new Date(), h = (n) => String(n).padStart(2, "0");
  li.innerHTML = `<span class="ts">${h(d.getHours())}:${h(d.getMinutes())}:${h(d.getSeconds())}</span>${entree.html}`;
  const ol = $("#journal-directives"); ol.prepend(li);
  while (ol.children.length > 80) ol.lastChild.remove();
  return li;
}
const resume = (a) => {
  switch (a.type) {
    case "articulation": return `${a.dof} ${a.relatif ? (a.valeur >= 0 ? "+" : "") : "→ "}${Math.round(a.valeur)}${a.dof.includes("abaissement") ? " cm" : a.dof.includes("fermeture") ? " %" : "°"}`;
    case "emotion": return `émotion ${a.nom} ${a.relatif ? (a.intensite > 0 ? "+" : "") : ""}${a.intensite}`;
    case "visage": return `visage : ${a.nom || Object.keys(a.au).join("+")}`;
    case "geste": return `geste ${a.nom}${a.cote ? ` (${a.cote})` : ""}${a.direction ? ` → ${a.direction}` : ""}`;
    case "pose": return `pose ${a.nom}`;
    case "dire": return `dire « ${a.texte.slice(0, 60)}${a.texte.length > 60 ? "…" : ""} »${a.maniere ? ` (${a.maniere})` : ""}`;
    case "deplacer": return "x" in a || "z" in a ? `aller à (${a.x ?? "·"}, ${a.z ?? "·"})` : a.lateral ? `pas de côté ${a.lateral} m` : `${a.avant >= 0 ? "avancer" : "reculer"} ${Math.abs(a.avant)} m`;
    case "orienter": return `orientation ${a.relatif ? "+" : ""}${a.angle}°`;
    case "apparence": return a.cle === "habillage" ? `habillage « ${SCHEMA.apparence.habillages?.[a.valeur]?.libelle || a.valeur} »` : `apparence ${a.cle} ${a.relatif ? "+" : ""}${a.valeur}`;
    default: return Object.entries(a).filter(([k]) => k !== "clause").map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(" ");
  }
};

/* ══════════ Exécution des actions ══════════ */
const pile = [];
let derniere = [];
let enCours = 0;
function memoriserEtat() {
  pile.push({ base: anim.instantane(), emotion: { ...anim.emotion }, auTenu: { ...anim.auTenu }, tabouret: anim.tabouret, racine: { ...anim.racine }, regard: anim.regardMode });
  if (pile.length > 40) pile.shift();
}
function annuler() {
  const s = pile.pop(); if (!s) return false;
  anim.arreter(); anim.restaurer(s.base); anim.emotion = s.emotion; anim.auTenu = s.auTenu; anim.tabouret = s.tabouret; anim.regardMode = s.regard;
  anim.deplacer({ x: s.racine.x, z: s.racine.z }).then(() => anim.orienter(s.racine.yaw));
  anim.emettre(); majCurseurs(); return true;
}
function toutArreter(motif) {
  enCours++; anim.arreter(); parole.annuler(); sousTitre("");
  if (typeof viderBascules === "function") viderBascules();
  journal({ html: `<b>Arrêt</b> — ${echapper(motif)}`, classe: "alerte" });
}
function appliquerApparence(cle, valeur, relatif) {
  const A = humain.apparence;
  if (cle === "habillage") {
    const h = (SCHEMA.apparence.habillages || {})[valeur]; if (!h) return;
    humain.appliquerApparence({ ...h.valeurs, habillage: valeur });
    ecrireLS("robo-scene-avatar-apparence", humain.apparence); majApparence(); return;
  }
  if (CHAMPS_HABILLAGE.includes(cle)) humain.apparence.habillage = "";        // tenue retouchée : personnalisée
  const v = relatif ? Number(A[cle]) + Number(valeur) : valeur;
  const r = SCHEMA.apparence[cle];
  humain.appliquerApparence({ [cle]: r && typeof r === "object" && "min" in r ? Math.max(r.min, Math.min(r.max, v)) : v });
  ecrireLS("robo-scene-avatar-apparence", humain.apparence);
  majApparence();
}
async function parler(texte, { maniere = null, emotion = null, prosodieImposee = null, segments = null } = {}) {
  const e = emotion || anim.emotion;
  const p = prosodieImposee || prosodie(e.nom, e.intensite);
  let { debit, hauteur, volume } = p;
  hauteur *= Number($("#voix-hauteur").value || 0.92);
  if (maniere === "chuchote") { volume = 0.35; debit *= 0.92; }
  if (maniere === "crie") { volume = 1; debit *= 1.08; hauteur *= 1.12; anim.battre(1.2); }
  const segs = segments || texte.split(/(?<=[.!?…;:,])\s+/).filter(Boolean).map((s) => ({
    texte: s, pause_apres_ms: /[.!?…]$/.test(s) ? Math.max(120, 320 * (1 + (p.pause || 0))) : /[,;:]$/.test(s) ? Math.max(60, 140 * (1 + (p.pause || 0))) : 0,
  }));
  sousTitre(segs.map((s) => s.texte).join(" "));
  // Anti-écho : la dictée ne doit pas entendre le robot (voir Dictee) ; on mémorise ce qu'il dit
  ditsRecemment.push({ texte, t: Date.now() }); if (ditsRecemment.length > 6) ditsRecemment.shift();
  dicteeRef?.suspendre();
  let ok;
  try { ok = await parole.dire(segs, { debit, hauteur, volume, parler: true }); }
  finally { dicteeRef?.reprendre(); }
  if (ok) setTimeout(() => { if (!parole.actif) sousTitre(""); }, 900);
  return ok;
}
async function executer(actions, { source = "règles", clauseLog = null } = {}) {
  const jeton = ++enCours;
  memoriserEtat();
  // une main commandée dans la même directive garde sa posture pendant les gestes qui suivent
  const mainsCommandees = new Set(actions.filter((a) => a.type === "main").map((a) => a.cote || "d"));
  const libererMains = (cotes = ["g", "d"]) => { for (const s of cotes) if (!mainsCommandees.has(s)) anim.mains[s].liberer(); };
  let groupe = false;
  const tenir = async () => { if (groupe) { groupe = false; await attendre(650 / anim.vitesse); } };
  for (const a of actions) {
    if (jeton !== enCours) return;
    if (a.type !== "articulation") await tenir();
    switch (a.type) {
      case "articulation": if (/^main_[gd]\.fermeture$/.test(a.dof)) libererMains([a.dof[5]]); anim.definir(a.dof, a.valeur, { relatif: !!a.relatif, vitesse: a.vitesse }); groupe = true; break;
      case "emotion": anim.definirEmotion(a.nom, a.intensite, !!a.relatif); await attendre(250); break;
      case "visage": anim.definirVisage(a.au, a.tenir !== false); await attendre(250); break;
      case "main": await executerMain(a); break;
      case "geste": libererMains(); await anim.jouerGeste(a.nom, { cote: a.cote || "d", repetitions: a.repetitions || 1, intensite: a.intensite || 1, direction: a.direction || "devant", vitesse: a.vitesse }); break;
      case "pose": libererMains(); anim.prendrePose(a.nom, a.vitesse); await attendre(900 / anim.vitesse); break;
      case "deplacer": await anim.deplacer({ ...a }); break;
      case "orienter": await anim.orienter((a.angle * Math.PI) / 180, !!a.relatif); break;
      case "regard": anim.regardMode = a.cible; anim.regardEmotion = null; break;
      case "dire": await parler(a.texte, { maniere: a.maniere }); break;
      case "apparence": appliquerApparence(a.cle, a.valeur, a.relatif); break;
      case "camera": scene.vue(a.vue); break;
      case "lumiere": scene.lumiere(a.mode); $("#lumiere").value = a.mode; break;
      case "vitesse": anim.vitesse = a.facteur; $("#vitesse").value = a.facteur; $("#vitesse-val").textContent = `×${a.facteur}`; break;
      case "memoriser": memoriserPose(a.nom); break;
      case "rappeler": if (!rappelerPose(a.nom)) journal({ html: `Pose « ${echapper(a.nom)} » inconnue.`, classe: "avert" }); break;
      case "arret": toutArreter("directive"); return;
      case "annuler": pile.pop(); annuler(); return;
      case "repeter": if (derniere.length) { await executer(derniere, { source }); } return;
      case "aide": montrerAide(); break;
      default: break;
    }
  }
  await tenir();
  if (!actions.some((a) => ["repeter", "annuler"].includes(a.type))) derniere = actions;
  majCurseurs();
}

/* ══════════ Mains à cinq doigts (25 oct. 2026) ══════════
   Postures des doigts, prises d'accessoires, force de serrage, toucher : web/avatar/mains.js. Le bras présente
   l'objet saisi (coude fléchi) ou se tend vers la main du partenaire ; il revient quand la main lâche. */
function presenter(s, objet) {
  if (objet === "main_partenaire") { anim.definir(`epaule_${s}.flexion`, 48); anim.definir(`coude_${s}.flexion`, 38); anim.definir(`epaule_${s}.rotation`, 8); }
  else if (OBJETS[objet]?.prise === "crochet") { anim.definir(`epaule_${s}.flexion`, 8); anim.definir(`coude_${s}.flexion`, 12); }
  else { anim.definir(`epaule_${s}.flexion`, 22); anim.definir(`coude_${s}.flexion`, 82); anim.definir(`epaule_${s}.rotation`, 18); }
}
function ramenerBras(s) { for (const n of ["epaule", "coude"]) anim.definir(`${n}_${s}.flexion`, 0); anim.definir(`epaule_${s}.rotation`, 0); }
async function executerMain(a) {
  let s = a.cote === "g" ? "g" : "d";
  // « lâche le verre », « serre plus fort » : la main qui tient l'objet, même si la phrase ne la nomme pas
  const tient = (c) => !!anim.mains[c].prise && (!a.valeur || anim.mains[c].prise.objet === a.valeur);
  if (["poser", "lacher", "force"].includes(a.action) && !tient(s) && tient(s === "g" ? "d" : "g")) s = s === "g" ? "d" : "g";
  const m = anim.mains[s], cote = s === "g" ? "gauche" : "droite";
  let r = { ok: true };
  switch (a.action) {
    case "posture": r = m.prendrePosture(a.valeur); break;
    case "prendre": r = m.prendre(a.valeur, { maniere: a.maniere || "normal" }); if (r.ok) { presenter(s, a.valeur); await attendre(600 / anim.vitesse); } break;
    case "poser": case "lacher":
      if (a.valeur && m.prise && m.prise.objet !== a.valeur) { r = { ok: false, motif: `elle tient ${article(m.prise.obj)}, pas ${article(OBJETS[a.valeur])}` }; break; }
      r = m.lacher("", { poser: a.action === "poser" }); if (r.ok) ramenerBras(s); break;
    case "force": r = m.regler(a.maniere); if (r.ok) journal({ html: `Main ${cote} : serrage ${echapper(MANIERES[a.maniere].libelle)}` }); break;
    case "ecraser":
      if (!m.prise || m.prise.objet !== a.valeur) { r = m.prendre(a.valeur, { maniere: "normal" }); if (!r.ok) break; presenter(s, a.valeur); await attendre(900 / anim.vitesse); }
      r = m.ecraser(); break;
    case "toucher": anim.maniereToucher[s] = a.maniere || "delicat"; await anim.jouerGeste("main_coeur", { cote: s }); break;
    case "pianoter": r = m.pianoterDoigts(true); break;
    case "relacher": r = m.liberer(); break;
  }
  if (!r.ok) journal({ html: `Main ${cote} : ${echapper(r.motif)}`, classe: "avert" });
  majMains(true);
}
anim.surMain = (e) => journal({ html: `<small>✋ ${e.cote === "g" ? "gauche" : "droite"}</small> ${echapper(e.msg)}`, classe: e.niveau === "alerte" ? "alerte" : e.niveau === "avert" ? "avert" : "" });
/* Panneau « Mains » : commandes et relevé (prise, force, pressions des capteurs). */
function remplirMains() {
  const opt = (o) => Object.entries(o).map(([k, v]) => `<option value="${k}">${echapper(typeof v === "string" ? v : v.libelle)}</option>`).join("");
  for (const s of ["g", "d"]) {
    $(`#mn-objet-${s}`).innerHTML = opt(Object.fromEntries(NOMS_OBJETS.map((k) => [k, OBJETS[k].libelle])));
    $(`#mn-maniere-${s}`).innerHTML = opt(Object.fromEntries(Object.entries(MANIERES).map(([k, v]) => [k, v.libelle])));
    $(`#mn-maniere-${s}`).value = "normal";
    $(`#mn-posture-${s}`).innerHTML = `<option value="">— posture des doigts —</option>${opt(POSTURES)}`;
    $(`#mn-posture-${s}`).onchange = (e) => { if (e.target.value) executer([{ type: "main", cote: s, action: "posture", valeur: e.target.value }]); e.target.value = ""; };
    $(`#mn-prendre-${s}`).onclick = () => executer([{ type: "main", cote: s, action: "prendre", valeur: $(`#mn-objet-${s}`).value, maniere: $(`#mn-maniere-${s}`).value }]);
    $(`#mn-poser-${s}`).onclick = () => executer([{ type: "main", cote: s, action: "poser" }]);
    $(`#mn-lacher-${s}`).onclick = () => executer([{ type: "main", cote: s, action: "lacher" }]);
    $(`#mn-ecraser-${s}`).onclick = () => executer([{ type: "main", cote: s, action: "ecraser", valeur: anim.mains[s].prise?.objet || $(`#mn-objet-${s}`).value }]);
    $(`#mn-maniere-${s}`).onchange = (e) => { if (anim.mains[s].prise) executer([{ type: "main", cote: s, action: "force", maniere: e.target.value }]); };
    $(`#mn-relacher-${s}`).onclick = () => executer([{ type: "main", cote: s, action: "relacher" }]);
  }
  $("#mn-carte").onchange = (e) => humain.carteTactile(e.target.checked);
}
let dernierReleve = 0;
function majMains(force = false) {
  const t = performance.now();
  if (!force && (t - dernierReleve < 200 || $("#ong-mains")?.hidden)) return;
  dernierReleve = t;
  for (const s of ["g", "d"]) {
    const e = anim.mains[s].etat(), p = e.prise;
    $(`#mn-etat-${s}`).innerHTML = p
      ? `<b>${echapper(p.libelle)}</b> — ${echapper(article(OBJETS[p.objet]))} (${echapper(MANIERES[p.maniere].libelle)})<br>force <b>${p.force.toFixed(1)} N</b> · minimum ${p.minimale.toFixed(1)} N${p.glissement ? " · <span class=\"alerte\">glisse</span>" : ""}${p.endommage ? " · <span class=\"avert\">endommagé</span>" : ""}`
      : `${echapper(anim.mains[s].libre ? "suit les gestes" : (POSTURES[e.posture]?.libelle || e.posture))}`;
    $(`#mn-fermeture-${s}`).textContent = `${e.fermeture} %`;
    $(`#mn-capteurs-${s}`).innerHTML = CAPTEURS.map((c) => {
      const k = e.capteurs[c.id];
      return `<tr${k.contact && k.force > 0.005 ? ' class="actif"' : ""}><td>${echapper(c.libelle)}</td><td>${k.force.toFixed(2)} N</td><td>${k.pression_kpa.toFixed(1)} kPa</td></tr>`;
    }).join("");
  }
}
remplirMains();

/* ══════════ Directives écrites et vocales ══════════ */
async function executerTexte(texte, origine = "écrit") {
  texte = String(texte || "").trim();
  if (!texte) return;
  const r = interpreter(texte, SCHEMA);
  // rien de compris comme directive et dialogue actif : la phrase s'adresse au robot, qui répond
  if (!r.actions.length && r.ignores.length && pont.dialogue?.actif()) { pont.dialogue.demander(texte, origine === "vocal" ? "voix" : "texte"); return; }
  const notes = [...new Set(r.actions.filter((a) => a.corrige || a.approx).map((a) => (a.corrige ? `lu « ${a.corrige} »` : `compris comme « ${a.approx} »`)))];
  const sugg = (c) => (r.suggestions?.[c]?.length ? r.suggestions[c] : EXEMPLES.slice(0, 0)).slice(0, 3);
  const li = journal({ html: `<b>${echapper(texte)}</b> <small>(${origine})</small><div class="actions">${r.actions.map((a) => `<code>${echapper(resume(a))}</code>`).join(" ")}</div>`
    + (notes.length ? `<div class="petit">${notes.map(echapper).join(" · ")}</div>` : "")
    + (r.ignores.length ? `<div class="ignore">Non compris : ${r.ignores.map((c) => `« ${echapper(c)} »${sugg(c).length ? ` — essayez : ${sugg(c).map((x) => `<button type="button" class="lien-essai">${echapper(x)}</button>`).join(" ")}` : ""}`).join(" · ")}</div>` : "") });
  li.querySelectorAll(".lien-essai").forEach((b) => (b.onclick = () => executerTexte(b.textContent, "suggestion")));
  pont.journaliser({ texte, origine, source: "règles", actions: r.actions, ignores: r.ignores });
  const promesse = r.actions.length ? executer(r.actions) : Promise.resolve();
  if (r.ignores.length && $("#recours-claude").checked && pont.ia) {
    li.querySelector(".ignore")?.insertAdjacentHTML("beforeend", " — <i>interprétation demandée au pont…</i>");
    const rep = await pont.demander("p_avatar_interpreter", { texte: r.ignores.join(". "), etat: etatPourIA() });
    proposerClaude(rep, li);
    if (rep && rep.actions?.length) return promesse;
  }
  if (r.ignores.length) repondreIncompris(r.ignores, r.actions.length > 0);
  return promesse;
}
/* Le robot répond toujours : s'il n'a pas compris, il le dit et le montre (haussement d'épaules, sous-titre).
   Garde-fou : la même réponse parlée n'est jamais redite à moins de 10 s ; entre-temps, il se contente du
   geste et du sous-titre (plus de boucle « Pardon, je n'ai pas compris » si le micro capte sa propre voix). */
let dernierIncompris = { phrase: "", t: 0 };
function repondreIncompris(ignores, enPartie) {
  if (!$("#repondre-incompris").checked) return;
  const phrase = enPartie ? `Je n'ai pas compris : ${ignores.join(", ")}.` : "Pardon, je n'ai pas compris. Dites « aide » pour connaître mes commandes.";
  const maintenant = Date.now();
  const deja = phrase === dernierIncompris.phrase && maintenant - dernierIncompris.t < 10000;
  dernierIncompris = { phrase, t: maintenant };
  setTimeout(async () => {
    if (!enPartie) anim.jouerGeste("hausser_epaules");
    if (deja) { sousTitre(phrase); setTimeout(() => { if (!parole.actif) sousTitre(""); }, 2500); return; }
    await parler(phrase, { emotion: { nom: "neutre", intensite: 0 } });
  }, enPartie ? 400 : 0);
}
function montrerAide() {
  ouvrirOnglet("directives");
  const d = document.querySelector(".aide-directives"); if (d) d.open = true;
  journal({ html: `<b>Commandes</b> (${EXEMPLES.length} exemples ; cliquez pour essayer) :<div class="actions">${EXEMPLES.map((e) => `<button type="button" class="lien-essai">${echapper(e)}</button>`).join(" ")}</div>` })
    .querySelectorAll(".lien-essai").forEach((b) => (b.onclick = () => executerTexte(b.textContent, "aide")));
  parler("Voici ce que je sais faire. Cliquez sur un exemple, ou donnez-moi une directive.", { emotion: { nom: "neutre", intensite: 0 } });
}
function etatPourIA() {
  const v = {}; for (const [k, x] of Object.entries(anim.base)) if (Math.abs(x) > 0.5) v[k] = Math.round(x);
  return { pose: v, emotion: anim.emotion, apparence: humain.apparence, position: { x: +anim.racine.x.toFixed(2), z: +anim.racine.z.toFixed(2) } };
}
function proposerClaude(rep, li) {
  if (!rep || rep.type === "p_erreur") { li.insertAdjacentHTML("beforeend", `<div class="ignore">Pont : ${echapper(rep?.msg || "pas de réponse")}</div>`); return; }
  const { actions, rejets } = valider(rep.actions || [], SCHEMA);
  const seuil = Number($("#seuil").value);
  const bloc = document.createElement("div"); bloc.className = "prop-claude";
  bloc.innerHTML = `<div><b>${echapper(rep.moteur || "modèle")}</b> · confiance ${Number(rep.confiance || 0).toFixed(2)} ${rep.confiance >= seuil ? "" : "<span class='alerte'>(sous le seuil)</span>"}</div>
    <div class="petit">${echapper(rep.justification || "")}</div>
    <div class="actions">${actions.map((a) => `<code>${echapper(resume(a))}</code>`).join(" ") || "<i>aucune action valide</i>"}</div>
    ${rejets.length ? `<div class="ignore">Écartées par la validation : ${rejets.map((x) => echapper(x.motif)).join(" ; ")}</div>` : ""}
    <div class="ligne"><button class="primaire" data-ok ${actions.length ? "" : "disabled"}>Valider</button><button data-non>Rejeter</button></div>`;
  li.appendChild(bloc);
  const decider = (ok) => {
    bloc.querySelector(".ligne").innerHTML = ok ? "<span class='ok'>Validée par l'utilisateur</span>" : "<span class='petit'>Rejetée</span>";
    pont.journaliser({ texte: rep.texte, origine: "claude", source: rep.moteur, actions, decision: ok ? "validee" : "rejetee", confiance: rep.confiance });
    if (ok) executer(actions, { source: "claude" });
  };
  bloc.querySelector("[data-ok]").onclick = () => decider(true);
  bloc.querySelector("[data-non]").onclick = () => decider(false);
  if ($("#auto-claude").checked && rep.confiance >= seuil && actions.length) decider(true);
}
$("#form-directive").onsubmit = (e) => { e.preventDefault(); const t = $("#directive").value; $("#directive").value = ""; executerTexte(t); };
$$("#exemples button").forEach((b) => (b.onclick = () => executerTexte(b.textContent, "exemple")));

/* Dictée (reconnaissance vocale du navigateur, fr-CA).
   Anti-écho, trois verrous : (1) la reconnaissance est suspendue pendant que le robot parle, puis 1,2 s après ;
   (2) un résultat qui reprend une phrase dite récemment par le robot est écarté (estEcho) ; (3) la réponse
   « je n'ai pas compris » n'est pas redite à moins de 10 s (repondreIncompris). */
const Dictee = {
  rec: null, continu: false, actif: false, suspendu: false, sourdineJusque: 0, reprise: null,
  suspendre() {
    if (!this.actif) return;
    this.suspendu = true; clearTimeout(this.reprise);
    try { this.rec?.abort(); } catch (e) { /* déjà arrêtée */ }
  },
  reprendre() {
    if (!this.actif || !this.suspendu) return;
    this.sourdineJusque = Date.now() + 1200;            // queue de réverbération des haut-parleurs
    clearTimeout(this.reprise);
    const relancer = () => {
      if (!this.actif) return;
      if (parole.actif) { this.reprise = setTimeout(relancer, 400); return; }   // le robot parle encore
      this.suspendu = false;
      try { this.rec?.start(); } catch (e) { /* déjà démarrée */ }
    };
    this.reprise = setTimeout(relancer, 1200);
  },
  dispo() { return "SpeechRecognition" in window || "webkitSpeechRecognition" in window; },
  demarrer(continu) {
    if (!this.dispo()) { journal({ html: "La reconnaissance vocale n'est pas offerte par ce navigateur (essayez Chrome, Edge ou Safari récent).", classe: "avert" }); return; }
    const R = window.SpeechRecognition || window.webkitSpeechRecognition;
    const r = (this.rec = new R());
    r.lang = "fr-CA"; r.interimResults = true; r.continuous = !!continu; this.continu = !!continu;
    try { if ("processLocally" in r) r.processLocally = true; } catch (e) {}
    r.onresult = (e) => {
      if (this.suspendu || parole.actif || Date.now() < this.sourdineJusque) { $("#dictee-interim").textContent = ""; return; }
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const x = e.results[i];
        if (x.isFinal) {
          const t = x[0].transcript.trim(); $("#dictee-interim").textContent = "";
          if (t && estEcho(t, ditsRecemment.filter((d) => Date.now() - d.t < 15000).map((d) => d.texte))) { journal({ html: `<small>Écho de la voix du robot ignoré : « ${echapper(t)} »</small>` }); continue; }
          if (t) executerTexte(t, "vocal");
        } else interim += x[0].transcript;
      }
      $("#dictee-interim").textContent = interim;
    };
    r.onerror = (e) => { if (!["no-speech", "aborted"].includes(e.error)) journal({ html: `Dictée : ${echapper(e.error)}`, classe: "avert" }); };
    r.onend = () => {
      if (this.suspendu) return;                              // reprise gérée par reprendre()
      if (this.actif && this.continu) { try { r.start(); } catch (e) {} } else this.fin();
    };
    this.actif = true; r.start();
    $("#btn-micro").classList.add("actif"); $("#btn-micro").setAttribute("aria-pressed", "true");
  },
  arreter() { this.actif = false; this.suspendu = false; clearTimeout(this.reprise); try { this.rec?.stop(); } catch (e) {} this.fin(); },
  fin() { this.actif = false; $("#btn-micro").classList.remove("actif"); $("#btn-micro").setAttribute("aria-pressed", "false"); $("#dictee-interim").textContent = ""; },
};
dicteeRef = Dictee;
$("#btn-micro").onclick = () => (Dictee.actif ? Dictee.arreter() : Dictee.demarrer($("#ecoute-continue").checked));
if (!Dictee.dispo()) { $("#btn-micro").disabled = true; $("#btn-micro").title = "Reconnaissance vocale indisponible dans ce navigateur"; }

/* ══════════ Émotions, visage, parole ══════════ */
$("#emotions").innerHTML = SCHEMA.emotions.map((n) => `<button data-e="${n}">${n}</button>`).join("");
$$("#emotions [data-e]").forEach((b) => (b.onclick = () => { memoriserEtat(); anim.definirEmotion(b.dataset.e, b.dataset.e === "neutre" ? 0 : Number($("#intensite").value)); majEmotionBoutons(); }));
$("#intensite").oninput = (e) => { $("#intensite-val").textContent = e.target.value; if (anim.emotion.nom !== "neutre") anim.definirEmotion(anim.emotion.nom, Number(e.target.value)); };
function majEmotionBoutons() { $$("#emotions [data-e]").forEach((b) => b.classList.toggle("actif", b.dataset.e === anim.emotion.nom)); }
anim.surChangement(majEmotionBoutons);
const EXPRESSIONS = {
  sourire: { au6: 0.5, au12: 0.8 }, "sourire en coin": { au12_g: 0.7, au14_g: 0.3 }, froncement: { au4: 0.9 }, "sourcils levés": { au1: 0.9, au2: 0.9 },
  "yeux plissés": { au7: 0.9 }, "yeux fermés": { au43: 1 }, moue: { au15: 0.6, au17: 0.7, au18: 0.3 }, "lèvres pincées": { au23: 0.6, au24: 0.8 },
  "bouche bée": { au25: 1, au26: 0.9, au1: 0.4, au2: 0.4 }, grimace: { au4: 0.6, au7: 0.6, au9: 0.6, au20: 0.7 }, "visage neutre": {},
};
$("#expressions").innerHTML = Object.keys(EXPRESSIONS).map((n) => `<button data-x="${n}">${n}</button>`).join("");
$$("#expressions [data-x]").forEach((b) => (b.onclick = () => anim.definirVisage(EXPRESSIONS[b.dataset.x], b.dataset.x !== "visage neutre")));
$("#replique-emotion").innerHTML = `<option value="">émotion courante</option>` + SCHEMA.emotions.map((n) => `<option>${n}</option>`).join("");
$("#btn-dire").onclick = async () => {
  const t = $("#replique").value.trim(); if (!t) return;
  const nom = $("#replique-emotion").value;
  if (nom) anim.definirEmotion(nom, nom === "neutre" ? 0 : Number($("#intensite").value));
  await parler(t);
};
$("#btn-taire").onclick = () => { parole.annuler(); sousTitre(""); };
$("#vivant").onchange = (e) => (anim.vivant = e.target.checked);
$("#vitesse").oninput = (e) => { anim.vitesse = Number(e.target.value); $("#vitesse-val").textContent = `×${e.target.value}`; };
function majVoix() {
  const sel = $("#voix");
  const v = parole.voix;
  sel.innerHTML = v.length ? `<option value="">automatique (voix masculine si disponible)</option>` + v.map((x) => `<option value="${echapper(x.name)}">${echapper(x.name)} — ${echapper(x.lang)}</option>`).join("") : `<option value="">aucune voix française détectée</option>`;
  sel.value = parole.choix || "";
  const c = parole.voixChoisie();
  $("#st-voix").textContent = c ? `Voix : ${c.name}` : "Voix : —";
  $("#st-voix").className = "pastille " + (c ? "ok" : "neutre");
}
parole.choix = lireLS("robo-scene-avatar-voix", null);
$("#voix").onchange = (e) => { parole.choix = e.target.value || null; ecrireLS("robo-scene-avatar-voix", parole.choix); majVoix(); };
if ("speechSynthesis" in window) speechSynthesis.addEventListener?.("voiceschanged", () => setTimeout(majVoix, 50));
setTimeout(majVoix, 300);

/* ══════════ Corps : sélection, curseurs, gestes, poses ══════════ */
function curseurDof(n) {
  const d = SCHEMA.dofs[n];
  return `<label class="curseur-dof"><span>${echapper(d.libelle)}</span><input type="range" min="${d.min}" max="${d.max}" step="1" value="${Math.round(anim.base[n])}" data-dof="${n}"><output>${Math.round(anim.base[n])}</output></label>`;
}
function brancherCurseurs(racine) {
  $$("input[data-dof]", racine).forEach((r) => {
    r.oninput = () => { anim.definir(r.dataset.dof, Number(r.value), { vitesse: 2.5 }); r.nextElementSibling.textContent = r.value; };
    r.onpointerdown = () => memoriserEtat();
  });
}
function majCurseurs() {
  $$("input[data-dof]").forEach((r) => { if (document.activeElement !== r) { r.value = Math.round(anim.base[r.dataset.dof]); r.nextElementSibling.textContent = r.value; } });
}
scene.surSelection = (zone) => {
  $("#selection-titre").textContent = zone ? LIBELLES_ZONES[zone] : "Aucune partie sélectionnée";
  const dofs = zone ? [...new Set([...DOFS_ZONE(zone), ...Object.keys(SCHEMA.dofs).filter((n) => SCHEMA.dofs[n].groupe === groupeDeZone(zone))])] : [];
  $("#selection-curseurs").innerHTML = dofs.map(curseurDof).join("");
  brancherCurseurs($("#selection-curseurs"));
  if (zone) ouvrirOnglet("corps");
};
function groupeDeZone(z) {
  if (/^(bras|avantbras)_/.test(z)) return `epaule_${z.slice(-1)}`;
  if (/^(cuisse|tibia|pied)_/.test(z)) return `jambe_${z.slice(-1)}`;
  return z;
}
let manipulationMemorisee = false;
scene.surManipulation = (dof, delta) => {
  if (!manipulationMemorisee) { memoriserEtat(); manipulationMemorisee = true; }
  const fm = /^main_([gd])\.fermeture$/.exec(dof); if (fm && !anim.mains[fm[1]].prise) anim.mains[fm[1]].liberer();
  anim.definir(dof, delta, { relatif: true, vitesse: 3 }); majCurseurs();
};
scene.surFinManipulation = () => { manipulationMemorisee = false; };
$("#tous-curseurs").innerHTML = Object.entries(SCHEMA.groupes).map(([g, nom]) => `<details><summary>${echapper(nom)}</summary>${Object.keys(SCHEMA.dofs).filter((n) => SCHEMA.dofs[n].groupe === g).map(curseurDof).join("")}</details>`).join("");
brancherCurseurs($("#tous-curseurs"));
const NOMS_GESTES = { saluer: "saluer (main)", reverence: "révérence", hocher: "oui de la tête", non: "non de la tête", hausser_epaules: "hausser les épaules", croiser_bras: "croiser les bras",
  mains_hanches: "mains sur les hanches", reflechir: "réfléchir", applaudir: "applaudir", bras_ouverts: "bras ouverts", pointer: "pointer", poing_leve: "poing levé", main_coeur: "main sur le cœur",
  gratter_tete: "se gratter la tête", rire: "rire", pleurer: "pleurer", soupirer: "soupirer", clin_oeil: "clin d'œil", danser: "danser", taper_pied: "taper du pied",
  cacher_visage: "se cacher le visage", etirer: "s'étirer", respirer: "respirer", marcher_sur_place: "marcher sur place",
  salut_militaire: "salut militaire", bras_au_ciel: "bras au ciel", mains_jointes: "mains jointes", signe_venir: "signe de venir", chasser: "chasser",
  chut: "chut", mains_dos: "mains dans le dos", mains_poches: "mains dans les poches", pouce_leve: "pouce levé", se_designer: "se désigner",
  tete_mains: "tête dans les mains", frapper_porte: "frapper à la porte", boire: "boire", telephoner: "téléphoner", ecrire: "écrire", lire: "lire",
  montre: "regarder sa montre", essuyer_front: "s'essuyer le front", bailler: "bâiller", frotter_yeux: "se frotter les yeux", sauter: "sauter",
  sautiller: "sautiller", serrer_main: "serrer la main", repousser: "repousser", trembler: "trembler", frotter_mains: "se frotter les mains", rouler_poignets: "rouler les poignets",
  muscles: "montrer ses muscles", accolade: "accolade", lancer: "lancer", ramasser: "ramasser", pousser: "pousser", tirer: "tirer", boxer: "boxer",
  coup_de_pied: "coup de pied", pointes_pieds: "pointes des pieds", tituber: "tituber", regarder_loin: "scruter au loin", eternuer: "éternuer",
  tousser: "tousser", compter: "compter sur ses doigts", menacer: "menacer", hesiter: "hésiter", ecouter: "tendre l'oreille", bercer: "bercer",
  mimer_mur: "mur invisible (mime)", dormir: "dormir" };
/* Boutons en bascule (gestes et poses) : premier appui, le robot exécute et TIENT la position ; second appui sur
   le même bouton, il revient à la position d'avant cet appui, ou à la position de départ selon le réglage
   « Second appui ». Les bascules s'empilent : défaire l'une défait aussi celles activées après elle. */
const DEPART = { base: anim.instantane(), emotion: { ...anim.emotion }, auTenu: {}, tabouret: false, regard: anim.regardMode,
  pointe: { g: false, d: false } };
const bascules = [];
function etatComplet() {
  return { base: anim.instantane(), emotion: { ...anim.emotion }, auTenu: { ...anim.auTenu }, tabouret: anim.tabouret,
    regard: anim.regardMode, pointe: { ...anim.pointe } };
}
function majBascules() {
  $$("#gestes [data-g], #poses [data-p]").forEach((b) => {
    const on = bascules.some((x) => x.bouton === b);
    b.classList.toggle("actif", on); b.setAttribute("aria-pressed", String(on));
    b.title = on ? "Appuyer de nouveau pour revenir" : "";
  });
}
function revenirA(etat) {
  enCours++; anim.arreter();
  anim.restaurer(etat.base); anim.emotion = { ...etat.emotion }; anim.auTenu = { ...etat.auTenu };
  anim.tabouret = etat.tabouret; anim.regardMode = etat.regard; anim.pointe = { ...etat.pointe }; anim.auGeste = {};
  for (const n of anim.noms) anim.vitesseDof[n] = 0.9;                // retour posé, sans à-coup
  setTimeout(() => { for (const n of anim.noms) delete anim.vitesseDof[n]; }, 1800);
  anim.emettre(); setTimeout(majCurseurs, 60); majEmotionBoutons();
}
function viderBascules() { bascules.length = 0; majBascules(); }
async function basculer(bouton, lancer) {
  const i = bascules.findIndex((x) => x.bouton === bouton);
  if (i >= 0) {                                                       // second appui : retour
    const depart = $("#retour-bascule").value === "depart";
    const etat = depart ? DEPART : bascules[i].etat;
    bascules.splice(depart ? 0 : i);
    memoriserEtat(); revenirA(etat); majBascules();
    journal({ html: `Retour ${depart ? "à la position de départ" : "à la position d'avant"} (« ${echapper(bouton.textContent)} »)` });
    return;
  }
  memoriserEtat();
  bascules.push({ bouton, etat: etatComplet() }); majBascules();
  await lancer();
}
$("#gestes").innerHTML = SCHEMA.gestes.map((g) => `<button data-g="${g}" aria-pressed="false">${NOMS_GESTES[g] || g}</button>`).join("");
$$("#gestes [data-g]").forEach((b) => (b.onclick = () => basculer(b, () => anim.jouerGeste(b.dataset.g, { cote: $("#cote-geste").value, tenir: true }))));
const NOMS_POSES = { repos: "repos", debout: "debout", assis: "assis", accroupi: "accroupi", a_genoux: "à genoux", garde_a_vous: "garde-à-vous", recroqueville: "recroquevillé",
  effondre: "effondré", en_garde: "en garde", penseur: "le penseur", statue: "statue" };
$("#poses").innerHTML = SCHEMA.poses.map((p) => `<button data-p="${p}" aria-pressed="false">${NOMS_POSES[p] || p}</button>`).join("");
$$("#poses [data-p]").forEach((b) => (b.onclick = () => basculer(b, async () => { anim.prendrePose(b.dataset.p); setTimeout(majCurseurs, 50); })));
$("#btn-annuler").onclick = () => { viderBascules(); if (!annuler()) journal({ html: "Rien à annuler." }); };

/* Poses mémorisées (navigateur) et chorégraphie */
let poses = lireLS("robo-scene-avatar-poses", {});
function memoriserPose(nom) {
  nom = String(nom || "").trim().slice(0, 40) || `pose ${Object.keys(poses).length + 1}`;
  poses[nom] = { base: anim.instantane(), emotion: { ...anim.emotion }, au: { ...anim.auTenu }, tabouret: anim.tabouret };
  ecrireLS("robo-scene-avatar-poses", poses); majPoses();
  journal({ html: `Pose mémorisée : « ${echapper(nom)} »` });
}
function rappelerPose(nom) {
  const cle = Object.keys(poses).find((k) => k.toLowerCase() === String(nom).toLowerCase());
  if (!cle) return false;
  const p = poses[cle];
  anim.arreter(); anim.restaurer(p.base); for (const n of anim.noms) anim.vitesseDof[n] = 0.9;
  anim.tabouret = !!p.tabouret; anim.auTenu = p.au || {}; if (p.emotion) anim.definirEmotion(p.emotion.nom, p.emotion.intensite);
  majCurseurs(); return true;
}
function majPoses() {
  const noms = Object.keys(poses);
  $("#liste-poses").innerHTML = noms.length ? noms.map((n) => `<li><span>${echapper(n)}</span><button data-r="${echapper(n)}">Reprendre</button><button class="discret" data-s="${echapper(n)}" title="Supprimer">×</button></li>`).join("") : "<li class='petit'>Aucune pose mémorisée.</li>";
  $$("#liste-poses [data-r]").forEach((b) => (b.onclick = () => { memoriserEtat(); rappelerPose(b.dataset.r); }));
  $$("#liste-poses [data-s]").forEach((b) => (b.onclick = () => { delete poses[b.dataset.s]; ecrireLS("robo-scene-avatar-poses", poses); majPoses(); }));
}
majPoses();
$("#form-pose").onsubmit = (e) => { e.preventDefault(); memoriserPose($("#nom-pose").value); $("#nom-pose").value = ""; };
let choreo = lireLS("robo-scene-avatar-choregraphie", []);
function majChoreo() {
  $("#choreo").innerHTML = choreo.length ? choreo.map((im, i) => `<li>Image ${i + 1} <input type="number" min="200" max="10000" step="100" value="${im.ms}" data-i="${i}" aria-label="durée en ms"> ms <button class="discret" data-x="${i}">×</button></li>`).join("") : "<li class='petit'>Capturez des poses pour composer une chorégraphie.</li>";
  $$("#choreo input[data-i]").forEach((x) => (x.onchange = () => { choreo[+x.dataset.i].ms = Math.max(200, Number(x.value)); ecrireLS("robo-scene-avatar-choregraphie", choreo); }));
  $$("#choreo [data-x]").forEach((b) => (b.onclick = () => { choreo.splice(+b.dataset.x, 1); ecrireLS("robo-scene-avatar-choregraphie", choreo); majChoreo(); }));
}
majChoreo();
$("#btn-capturer").onclick = () => { choreo.push({ base: anim.instantane(), emotion: { ...anim.emotion }, ms: 1200 }); ecrireLS("robo-scene-avatar-choregraphie", choreo); majChoreo(); };
$("#btn-jouer-choreo").onclick = async () => {
  const j = ++enCours; memoriserEtat();
  for (const im of choreo) {
    if (j !== enCours) return;
    anim.restaurer(im.base); for (const n of anim.noms) anim.vitesseDof[n] = Math.max(0.3, 1200 / im.ms);
    if (im.emotion) anim.definirEmotion(im.emotion.nom, im.emotion.intensite);
    await attendre(im.ms / anim.vitesse);
  }
};
$("#btn-vider-choreo").onclick = () => { choreo = []; ecrireLS("robo-scene-avatar-choregraphie", choreo); majChoreo(); };
function telecharger(nom, objet) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(objet, null, 2)], { type: "application/json" }));
  a.download = nom; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
$("#btn-exporter").onclick = () => telecharger("robot-virtuel.json", { format: "robo-scene-avatar/1", apparence: humain.apparence, poses, choregraphie: choreo });
$("#fichier-import").onchange = async (e) => {
  const f = e.target.files[0]; if (!f) return;
  try {
    const d = JSON.parse(await f.text());
    if (d.format !== "robo-scene-avatar/1") throw new Error("format inattendu");
    if (d.apparence) { humain.appliquerApparence(d.apparence); ecrireLS("robo-scene-avatar-apparence", humain.apparence); majApparence(); }
    if (d.poses) { poses = { ...poses, ...d.poses }; ecrireLS("robo-scene-avatar-poses", poses); majPoses(); }
    if (Array.isArray(d.choregraphie)) { choreo = d.choregraphie; ecrireLS("robo-scene-avatar-choregraphie", choreo); majChoreo(); }
    journal({ html: `Fichier importé : ${echapper(f.name)}` });
  } catch (err) { journal({ html: `Import impossible : ${echapper(err.message)}`, classe: "alerte" }); }
  e.target.value = "";
};

/* ══════════ Apparence ══════════ */
function majApparence() {
  const A = humain.apparence;
  for (const k of ["taille", "carrure", "corpulence", "age"]) { $(`#ap-${k}`).value = A[k]; $(`#ap-${k}-val`).textContent = k === "taille" ? `${A[k]} cm` : k === "age" ? `${A[k]} ans` : Number(A[k]).toFixed(2); }
  for (const k of ["cheveux", "barbe", "manches", "peau", "yeux"]) $(`#ap-${k}`).value = A[k];
  $("#ap-moustache").checked = !!A.moustache;
  const hex = (n) => (/^#/.test(n) ? n : SCHEMA.apparence.couleurs[n] || "#888888");
  for (const k of ["haut", "bas", "chaussures", "couleur_cheveux", "couleur_chapeau", "accessoire"]) $(`#ap-${k}`).value = hex(A[k]);
  for (const k of ["matiere", "chapeau", "cou", "cape", "jupe", "coupe_bas"]) $(`#ap-${k}`).value = A[k];
  $("#ap-gants").checked = !!A.gants; $("#ap-chaussures_montantes").checked = !!A.chaussures_montantes;
  const h = A.habillage || "";
  for (const id of ["#habillage", "#ap-habillage"]) $(id).value = h;
  $("#ap-habillage-desc").textContent = h ? SCHEMA.apparence.habillages[h]?.description || "" : "Tenue personnalisée : choisissez un habillage pour la remplacer.";
}
const HABILLAGES = SCHEMA.apparence.habillages || {};
for (const id of ["#habillage", "#ap-habillage"]) {
  $(id).innerHTML = `<option value="" disabled>${id === "#habillage" ? "Habillage…" : "personnalisé"}</option>`
    + Object.entries(HABILLAGES).map(([k, h]) => `<option value="${k}" title="${echapper(h.description)}">${echapper(h.libelle)}</option>`).join("");
  $(id).onchange = (e) => { if (e.target.value) { appliquerApparence("habillage", e.target.value); journal({ html: `Habillage : <b>${echapper(HABILLAGES[e.target.value].libelle)}</b>` }); } e.target.blur(); };
}
for (const k of ["matiere", "chapeau", "cou", "cape", "jupe", "coupe_bas"]) {
  $(`#ap-${k}`).innerHTML = SCHEMA.apparence[k].map((x) => `<option>${x}</option>`).join("");
  $(`#ap-${k}`).onchange = (e) => appliquerApparence(k, e.target.value);
}
for (const k of ["couleur_chapeau", "accessoire"]) $(`#ap-${k}`).oninput = (e) => appliquerApparence(k, e.target.value);
$("#ap-gants").onchange = (e) => appliquerApparence("gants", e.target.checked);
$("#ap-chaussures_montantes").onchange = (e) => appliquerApparence("chaussures_montantes", e.target.checked);
$("#ap-cheveux").innerHTML = SCHEMA.apparence.cheveux.map((x) => `<option>${x}</option>`).join("");
$("#ap-barbe").innerHTML = SCHEMA.apparence.barbe.map((x) => `<option>${x}</option>`).join("");
$("#ap-manches").innerHTML = SCHEMA.apparence.manches.map((x) => `<option>${x}</option>`).join("");
$("#ap-peau").innerHTML = Object.keys(PEAUX).map((x) => `<option>${x}</option>`).join("");
$("#ap-yeux").innerHTML = Object.keys(YEUX).map((x) => `<option>${x}</option>`).join("");
for (const k of ["taille", "carrure", "corpulence", "age"]) { const r = SCHEMA.apparence[k]; Object.assign($(`#ap-${k}`), { min: r.min, max: r.max, step: k === "taille" || k === "age" ? 1 : 0.01 }); $(`#ap-${k}`).oninput = (e) => appliquerApparence(k, Number(e.target.value)); }
for (const k of ["cheveux", "barbe", "manches", "peau", "yeux"]) $(`#ap-${k}`).onchange = (e) => appliquerApparence(k, e.target.value);
for (const k of ["haut", "bas", "chaussures", "couleur_cheveux"]) $(`#ap-${k}`).oninput = (e) => appliquerApparence(k, e.target.value);
$("#ap-moustache").onchange = (e) => appliquerApparence("moustache", e.target.checked);
$("#ap-defaut").onclick = () => { humain.appliquerApparence({ ...APPARENCE_DEFAUT, habillage: "repetition" }); ecrireLS("robo-scene-avatar-apparence", humain.apparence); majApparence(); };
majApparence();

/* ══════════ Imitation (caméra, traitement local) ══════════ */
function afficherLecture(au) {
  const l = lireEmotion(au, EMOTIONS);
  $("#lecture-emotion").innerHTML = l.map((x) => `<span class="pastille ${x === l[0] ? "ok" : "neutre"}">${echapper(x.nom)} ${(x.score * 100).toFixed(0)} %</span>`).join(" ");
}
$("#btn-imiter").onclick = async () => {
  if (imitation.actif) { imitation.arreter(); majImitation(); return; }
  if (!$("#consent-camera").checked) { $("#imit-etat").textContent = "Cochez d'abord l'accord d'utilisation de la caméra."; return; }
  $("#imit-etat").textContent = "Chargement des modèles de vision…";
  try { await imitation.demarrer($("#video")); $("#imit-etat").textContent = "Imitation active (traitement local, rien n'est enregistré)."; }
  catch (e) { imitation.arreter(); $("#imit-etat").textContent = `Caméra ou modèles indisponibles : ${e.message || e}`; }
  majImitation();
};
function majImitation() {
  $("#btn-imiter").textContent = imitation.actif ? "Arrêter l'imitation" : "Démarrer l'imitation";
  $("#st-imitation").textContent = imitation.actif ? "Imitation : active" : "Imitation : —";
  $("#st-imitation").className = "pastille " + (imitation.actif ? "avert" : "neutre");
  $("#video").hidden = !imitation.actif;
  if (!imitation.actif) $("#lecture-emotion").textContent = "—";
}
$("#imit-visage").onchange = (e) => (imitation.visage = e.target.checked);
$("#imit-corps").onchange = (e) => (imitation.corps = e.target.checked);
$("#imit-miroir").onchange = (e) => { imitation.miroir = e.target.checked; imitation.lisse = {}; };
$("#btn-figer").onclick = () => {
  const o = imitation.sortie; if (!o) return;
  memoriserEtat();
  for (const [k, v] of Object.entries(o.pose || {})) anim.definir(k, v);
  if (o.au) anim.definirVisage(Object.fromEntries(Object.entries(o.au).filter(([, v]) => v > 0.08 && true).filter(([k]) => !/^au46/.test(k))), true);
  journal({ html: "Expression et posture de la personne figées sur le robot virtuel." });
};

/* ══════════ Vues, lumière, mode scène, fenêtre séparée ══════════ */
$$("[data-vue]").forEach((b) => (b.onclick = () => scene.vue(b.dataset.vue)));
$("#lumiere").onchange = (e) => scene.lumiere(e.target.value);
$("#btn-scene").onclick = () => basculerScene();
function basculerScene(force) {
  const actif = force ?? !document.body.classList.contains("mode-scene");
  document.body.classList.toggle("mode-scene", actif);
  if (actif) document.documentElement.requestFullscreen?.().catch(() => {});
  else if (document.fullscreenElement) document.exitFullscreen?.();
  setTimeout(() => scene.redimensionner(), 60);
}
document.addEventListener("fullscreenchange", () => { if (!document.fullscreenElement && document.body.classList.contains("mode-scene")) basculerScene(false); });
$("#btn-fenetre").onclick = () => window.open(`${location.pathname}?scene=1`, "robo-scene-avatar", "popup,width=1100,height=800");
$("#btn-photo").onclick = () => { const a = document.createElement("a"); a.href = scene.capture(); a.download = "robot-virtuel.png"; a.click(); };
if (new URLSearchParams(location.search).get("scene") === "1") document.body.classList.add("mode-scene", "fenetre-scene");

/* ══════════ Onglets ══════════ */
function ouvrirOnglet(nom) {
  $$(".onglets [role=tab]").forEach((t) => t.setAttribute("aria-selected", String(t.dataset.onglet === nom)));
  $$(".panneau-onglet").forEach((p) => (p.hidden = p.id !== `ong-${nom}`));
  try { localStorage.setItem("robo-scene-avatar-onglet", nom); } catch (e) {}
}
$$(".onglets [role=tab]").forEach((t) => (t.onclick = () => ouvrirOnglet(t.dataset.onglet)));
ouvrirOnglet((() => { try { return localStorage.getItem("robo-scene-avatar-onglet") || "directives"; } catch (e) { return "directives"; } })());

/* ══════════ Arrêt ══════════ */
function arretGeneral(motif) { toutArreter(motif); if (jumeau.pilote) { jumeau.pilote = false; $("#jumeau-pilote").checked = false; } pont.envoyer("estop", { motif: `${motif} (robot virtuel)` }); }
$("#btn-arret").onclick = () => arretGeneral("bouton ARRÊT");
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.preventDefault(); if (document.body.classList.contains("mode-scene") && !document.body.classList.contains("fenetre-scene")) basculerScene(false); arretGeneral("touche Échap"); }
  if (e.key === "Enter" && e.ctrlKey && document.activeElement === $("#directive")) $("#form-directive").requestSubmit();
});

/* ══════════ Pont local (facultatif) : journal, interprète Claude, jumeau du robot ══════════ */
const pont = {
  ws: null, ouvert: false, ia: false, cfg: null, attentes: new Map(), n: 0, estop: false,
  connecter() {
    const P = window.ROBO_PONT; if (!P) return;
    try { this.ws = new WebSocket(P.url); } catch (e) { return; }
    this.ws.onopen = () => { this.ouvert = true; P.ouvert(); this.envoyer("p_avatar_etat"); this.dialogue?.pontOuvert(); majPont(); };
    this.ws.onclose = () => { this.ouvert = false; this.ia = false; P.ferme(); this.dialogue?.pontFerme(); majPont(); setTimeout(() => this.connecter(), 2500); };
    this.ws.onmessage = (ev) => {
      let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (/^(ia_moteurs|ia_choix|dialogue|dialogue_refus|dialogue_oublier)$/.test(m.type)) { this.dialogue?.recevoir(m); return; }
      if (m.type === "config") { this.cfg = m; majPont(); }
      else if (m.type === "etat") { this.estop = !!(m.arret ?? m.estop); jumeau.surEtat(m); }
      else if (m.type === "p_avatar_etat") { this.ia = !!m.moteur && m.moteur !== "déterministe"; $("#moteur-ia").textContent = m.moteur; majPont(); }
      const f = this.attentes.get(m.type);
      if (f && (m.type === "p_avatar_interpreter" || m.type === "p_erreur")) { this.attentes.delete("p_avatar_interpreter"); this.attentes.delete("p_erreur"); f(m); }
    };
  },
  envoyer(op, data = {}) { if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify({ op, ...data })); },
  demander(op, data) {
    return new Promise((ok) => {
      if (!this.ouvert) return ok(null);
      this.attentes.set(op, ok); this.attentes.set("p_erreur", ok);
      this.envoyer(op, data);
      setTimeout(() => { if (this.attentes.get(op) === ok) { this.attentes.delete(op); ok({ type: "p_erreur", msg: "délai dépassé" }); } }, 30000);
    });
  },
  journaliser(ev) { if ($("#journaliser").checked) this.envoyer("p_avatar_journal", { evenement: ev }); },
};
/* Dialogue parlé : le robot répond avec sa propre voix (lèvres synchronisées) ; ses propositions de gestes,
   de poses ou de déplacements sont revalidées ici (schema.json) et attendent la validation d'une personne. */
pont.dialogue = installerDialogue({
  conteneur: $("#dialogue"), domaine: "robot", nom: "le robot", hautParleur: true,
  envoyer: ({ op, ...d }) => { pont.envoyer(op, d); return pont.ouvert; },
  decrire: (a) => resume(a),
  journal: (niveau, texte) => journal({ html: echapper(texte), classe: niveau === "avert" ? "avert" : "" }),
  contexte: () => `émotion ${anim.emotion.nom}, position sur le plateau x ${anim.racine.x.toFixed(1)} m, z ${anim.racine.z.toFixed(1)} m`,
  parler: (t) => parler(t), parle: () => parole.actif, taire: () => { parole.annuler(); sousTitre(""); },
  executerActions: (actions) => { const { actions: ok } = valider(actions, SCHEMA); if (ok.length) executer(ok, { source: "dialogue" }); },
});
if (pont.ouvert) pont.dialogue.pontOuvert();
function majPont() {
  $("#st-pont").textContent = pont.ouvert ? `Pont : relié${pont.cfg ? ` · ${pont.cfg.robot}` : ""}` : "Pont : non relié";
  $("#st-pont").className = "pastille " + (pont.ouvert ? "ok" : "neutre");
  $("#recours-claude").disabled = !pont.ia;
  $("#etat-claude").textContent = pont.ia ? "disponible" : pont.ouvert ? "pont relié, aucun modèle disponible (règles seulement)" : "pont non relié";
  const mode = jumeau.mode();
  $("#jumeau-reflet").disabled = $("#jumeau-pilote").disabled = !pont.ouvert || !mode;
  const c = pont.cfg;
  $("#jumeau-info").textContent = !c ? "—" : `Robot actif : ${c.robot || c.robot_id || "?"} — ${c.noms.length} articulations.`
    + (mode === "noms" ? ` Correspondance par nom d'axe : ${jumeau.indices().length} axes reflétés, ${jumeau.pilotes().length} pilotables`
        + ` (${(c.jumeau?.piloter || []).length ? "liste du profil" : "tous"}).`
        + ((c.a_verifier || []).length ? ` Sens et bornes à confirmer par relevé pour ${c.a_verifier.length} axe(s).` : "")
      : mode === "bras4" ? " Correspondance : tronc → Base, bras droit → Épaule et Coude, tête → Tête."
      : " Aucun axe du robot ne correspond à un degré de liberté du robot virtuel ; le jumeau est désactivé.");
  if (c?.camera?.mjpeg && !$("#mjpeg-url").value) $("#mjpeg-url").value = c.camera.mjpeg;
}
/* Jumeau du robot physique. Deux correspondances :
   - « noms » : chaque axe du robot qui porte le nom d'un degré de liberté du robot virtuel (ex. TonyPi Pro :
     epaule_d.flexion, genou_g.flexion…) lui correspond directement, en degrés relatifs à la position debout
     (0 = debout pour les deux) ; tous ces axes sont reflétés, et seuls ceux de `jumeau.piloter` (profil) sont pilotés —
     pour un bipède, la tête, les bras et les mains, l'équilibre restant aux gestes natifs ;
   - « bras4 » : robot historique à 4 servos (Base, Épaule, Coude, Tête), correspondance de conception (Inférence). */
const jumeau = {
  reflet: false, pilote: false, dernierEnvoi: 0, dernier: null, couleur: null,
  mode() {
    const c = pont.cfg; if (!c) return null;
    if (c.noms.some((n) => SCHEMA.dofs[n])) return "noms";
    const n = c.noms.map((x) => x.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase());
    return n.length === 4 && ["base", "epaule", "coude", "tete"].every((x, i) => n[i].startsWith(x)) ? "bras4" : null;
  },
  compatible() { return !!this.mode(); },
  indices() { return (pont.cfg?.noms || []).map((n, i) => (SCHEMA.dofs[n] ? i : -1)).filter((i) => i >= 0); },
  pilotes() {
    const liste = pont.cfg?.jumeau?.piloter;
    return this.indices().filter((i) => !liste || !liste.length || liste.includes(pont.cfg.noms[i]));
  },
  surEtat(m) {
    if (!this.reflet || !Array.isArray(m.deg)) return;
    const mode = this.mode(), c = pont.cfg, d = m.deg;
    if (mode === "noms") { for (const i of this.indices()) if (d[i] != null) anim.definir(c.noms[i], d[i]); return; }
    if (mode !== "bras4") return;
    const { repos, min_deg: mn } = c;
    if (d[0] != null) anim.definir("tronc.rotation", d[0] - repos[0]);
    if (d[1] != null) anim.definir("epaule_d.flexion", d[1] - repos[1]);
    if (d[2] != null) anim.definir("coude_d.flexion", d[2] - mn[2]);
    if (d[3] != null) anim.definir("tete.rotation", d[3] - repos[3]);
  },
  maj() {
    const mode = this.mode();
    if (!this.pilote || !pont.ouvert || !mode || pont.estop) return;
    const t = performance.now(); if (t - this.dernierEnvoi < 200) return;
    const c = pont.cfg, { min_deg: mn, max_deg: mx } = c, v = anim.val;
    let deg;
    if (mode === "noms") {
      const pil = new Set(this.pilotes());
      deg = c.noms.map((n, i) => (pil.has(i) ? Math.round(Math.max(mn[i], Math.min(mx[i], v[n] ?? 0))) : null));
    } else {
      const { repos } = c;
      const brut = [repos[0] + v["tronc.rotation"], repos[1] + v["epaule_d.flexion"], mn[2] + v["coude_d.flexion"], repos[3] + v["tete.rotation"]];
      deg = brut.map((x, i) => Math.round(Math.max(mn[i], Math.min(mx[i], x))));
    }
    if (this.dernier && deg.every((x, i) => x === this.dernier[i] || (x != null && this.dernier[i] != null && Math.abs(x - this.dernier[i]) < 1))) return;
    this.dernier = deg; this.dernierEnvoi = t;
    pont.envoyer("articulations", { deg, ms: 250, origine: "avatar", robot: c.robot_id });
  },
  /* Couleur des « yeux » du robot (DEL) selon l'émotion du robot virtuel : choix de conception (Inférence),
     inspiré des associations couleur–émotion courantes au théâtre ; l'intensité dose la luminosité. */
  COULEURS: { neutre: [200, 200, 200], "colère": [255, 30, 20], joie: [255, 190, 40], tristesse: [40, 90, 255],
    peur: [150, 60, 255], tendresse: [255, 120, 170], "mépris": [140, 200, 40], surprise: [40, 230, 255],
    ironie: [255, 140, 0], lassitude: [90, 110, 140], assurance: [255, 255, 255], "dégoût": [60, 170, 60] },
  emotion() {
    if (!this.pilote || !pont.ouvert || !(pont.cfg?.capacites || []).includes("lumiere") || pont.estop) return;
    const e = anim.emotion, base = this.COULEURS[e.nom] || this.COULEURS.neutre;
    const k = e.nom === "neutre" ? 0.6 : 0.35 + 0.065 * Math.min(10, e.intensite || 0);
    const rgb = base.map((x) => Math.round(x * k));
    if (this.couleur && rgb.every((x, i) => Math.abs(x - this.couleur[i]) < 8)) return;
    this.couleur = rgb;
    pont.envoyer("robot_lumiere", { rgb, origine: "avatar", robot: pont.cfg.robot_id });
  },
};
anim.surChangement(() => jumeau.emotion());
$("#jumeau-reflet").onchange = (e) => { jumeau.reflet = e.target.checked; if (e.target.checked) { jumeau.pilote = false; $("#jumeau-pilote").checked = false; } };
$("#jumeau-pilote").onchange = (e) => {
  const quoi = jumeau.mode() === "noms" ? `${jumeau.pilotes().length} axes (${pont.cfg.noms.filter((_, i) => jumeau.pilotes().includes(i)).join(", ")})`
    : "le bras droit, le tronc et la tête";
  if (e.target.checked && !confirm(`Le robot virtuel va piloter le robot physique : ${quoi}. Les commandes passent par la couche de sécurité du pont. Vérifiez que la scène est dégagée. Continuer ?`)) { e.target.checked = false; return; }
  jumeau.pilote = e.target.checked; jumeau.dernier = null; jumeau.couleur = null;
  if (jumeau.pilote) jumeau.emotion();
  if (e.target.checked) { jumeau.reflet = false; $("#jumeau-reflet").checked = false; }
  journal({ html: `Pilotage du robot physique par le robot virtuel ${jumeau.pilote ? "activé" : "désactivé"}.`, classe: jumeau.pilote ? "avert" : "" });
};
pont.connecter(); majPont();

/* ══════════ Liaison avec la page Partenaire (BroadcastChannel, même navigateur) ══════════ */
const canal = "BroadcastChannel" in window ? new BroadcastChannel("robo-scene-avatar") : null;
let liaison = { derniere: 0 };
if (canal) {
  canal.onmessage = async (ev) => {
    const m = ev.data || {};
    if (!$("#liaison-partenaire").checked) return;
    liaison.derniere = Date.now(); majLiaison();
    if (m.t === "ping") canal.postMessage({ t: "pong" });
    else if (m.t === "taire") { parole.annuler(); sousTitre(""); }
    else if (m.t === "emotion" && EMOTIONS[m.nom]) anim.definirEmotion(m.nom, m.intensite ?? 7);
    else if (m.t === "geste") anim.jouerGeste(m.nom, m);
    else if (m.t === "dire") {
      const r = m.rendu || {};
      if (m.variation?.emotion && EMOTIONS[m.variation.emotion]) anim.definirEmotion(m.variation.emotion, m.variation.intensite ?? 6);
      if (m.nom) $("#replique-perso").textContent = m.nom;
      let ok = true;
      if (r.parler === false) { sousTitre((r.segments || []).map((s) => s.texte).join(" ")); await attendre(r.duree_estimee_ms || 1500); }
      else ok = await parler("", { segments: r.segments, prosodieImposee: { debit: r.debit || 1, hauteur: r.hauteur || 1, volume: m.volume ?? r.volume ?? 0.9, pause: 0 } });
      canal.postMessage({ t: "fini", jeton: m.jeton, ok });
    }
  };
  canal.postMessage({ t: "pong" });
}
function majLiaison() {
  const actif = Date.now() - liaison.derniere < 6000;
  $("#st-liaison").textContent = actif ? "Partenaire : relié" : "Partenaire : —";
  $("#st-liaison").className = "pastille " + (actif ? "ok" : "neutre");
}
setInterval(majLiaison, 3000);

/* ══════════ Ce que voit le robot : caméra des yeux (virtuelle) et caméra du robot réel ══════════
   Même fonctionnement que la caméra embarquée du drone et la caméra de tête du chien (web/drone/camera4k.js).
   Garde-fou G-06 : le flux réel est affiché seulement, jamais enregistré ; seule la vue virtuelle peut l'être. */
vueRobot = (() => {
  const cam = new CameraVirtuelle($("#cam-virtuelle"), scene);
  const flux = new FluxReel($("#cam-reelle"), $("#cam-mjpeg"));
  const nb = (x) => x.toLocaleString("fr-CA", { maximumFractionDigits: 1 });
  const fichier = (blob, nom) => { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = nom; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); };
  const horodatage = () => new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  let source = "virtuelle", image = 0;
  const R = lireLS("robo-scene-avatar-camera", {});
  const sauver = () => ecrireLS("robo-scene-avatar-camera", { visible: $("#pip-visible").checked, regard: $("#suivre-regard").checked, tiers: $("#tiers").checked, whep: $("#whep-url").value.trim() });

  const visible = (v) => { $("#pip").hidden = !v; $("#pip-visible").checked = v; sauver(); };
  $("#pip-visible").checked = R.visible !== false; $("#pip").hidden = R.visible === false;
  $("#pip-visible").onchange = (e) => visible(e.target.checked);
  $("#pip-masquer").onclick = () => visible(false);
  $("#pip-taille").onclick = () => $("#pip").classList.toggle("grand");
  $("#suivre-regard").checked = !!R.regard; scene.suivreRegard = !!R.regard;
  $("#suivre-regard").onchange = (e) => { scene.suivreRegard = e.target.checked; sauver(); };
  $("#tiers").checked = R.tiers !== false; $("#tiers").onchange = sauver;
  $("#whep-url").value = R.whep || "";
  $("#zoom").oninput = (e) => { scene.zoom = +e.target.value; $("#zoom-val").textContent = `×${nb(scene.zoom)}`; };
  $("#definition").onchange = () => { const [w, h] = $("#definition").value.split("x").map(Number); cam.regler(w, h); };

  function majSource() {
    source = $("input[name=source]:checked").value;
    $("#pip").classList.toggle("superposee", source === "superposee");
    const mj = flux.source === "mjpeg";
    $("#cam-reelle").hidden = source === "virtuelle" || mj; $("#cam-mjpeg").hidden = source === "virtuelle" || !mj;
    $("#cam-virtuelle").hidden = source === "reelle";
    $("#pip-titre").textContent = { virtuelle: "Caméra des yeux (virtuelle)", reelle: "Caméra du robot réel", superposee: "Réelle + virtuelle superposées" }[source];
  }
  $$("input[name=source]").forEach((r) => (r.onchange = majSource));
  const choisir = (v) => { $(`input[name=source][value=${v}]`).checked = true; majSource(); };

  $("#b-photo").onclick = async () => { const b = await cam.photo4K(); if (b) fichier(b, `vue_robot_virtuel_3840x2160_${horodatage()}.png`); };
  $("#b-rec").onclick = async () => {
    if (cam.enregistre) {
      const b = await cam.arreterEnregistrement(); $("#b-rec").textContent = "● Enregistrer"; $("#b-rec").setAttribute("aria-pressed", "false");
      if (b) fichier(b, `vue_robot_virtuel_${cam.definition.join("x")}_${horodatage()}.webm`);
    } else {
      try { cam.demarrerEnregistrement(30); $("#b-rec").textContent = "■ Arrêter"; $("#b-rec").setAttribute("aria-pressed", "true"); }
      catch (e) { $("#cam-info").textContent = e.message; }
    }
  };
  async function listerCameras() {
    try {
      const l = await FluxReel.cameras();
      $("#cam-liste").innerHTML = `<option value="">Caméra USB du robot / carte de capture…</option>` + l.map((d, i) => `<option value="${echapper(d.deviceId)}">${echapper(d.label || `Source vidéo ${i + 1}`)}</option>`).join("");
    } catch (e) { /* aucune source */ }
  }
  const info = (r) => { $("#cam-info").textContent = r.largeur ? `Flux réel : ${r.largeur} × ${r.hauteur}${r.ips ? ` à ${r.ips} i/s` : ""}${r.nom ? ` · ${r.nom}` : ""}` : "Flux ouvert, en attente d'images…"; };
  $("#b-capture").onclick = async () => { try { info(await flux.ouvrirCapture($("#cam-liste").value || undefined)); choisir("reelle"); visible(true); listerCameras(); } catch (e) { $("#cam-info").textContent = e.message; } };
  $("#b-whep").onclick = async () => {
    const url = $("#whep-url").value.trim(); if (!url) return; sauver();
    try { $("#cam-info").textContent = "Connexion WHEP…"; info(await flux.ouvrirWHEP(url)); choisir("reelle"); visible(true); } catch (e) { $("#cam-info").textContent = e.message; }
  };
  $("#b-mjpeg").onclick = async () => {
    const url = $("#mjpeg-url").value.trim(); if (!url) return;
    try { $("#cam-info").textContent = "Connexion au flux MJPEG…"; info(await flux.ouvrirMJPEG(url)); choisir("reelle"); visible(true); } catch (e) { $("#cam-info").textContent = e.message; }
  };
  $("#b-cam-fermer").onclick = async () => { await flux.fermer(); $("#cam-info").textContent = "—"; choisir("virtuelle"); };
  listerCameras(); majSource();

  return {
    cam, flux,
    rendre() {
      if ($("#pip").hidden || document.body.classList.contains("mode-scene")) { if (!cam.enregistre) return; }
      image++;
      if (source !== "reelle" && (image % 2 === 0 || cam.enregistre)) cam.rendre(); else if (source === "reelle") scene.majCameraYeux();
      if (image % 6) return;
      const c = $("#cam-surimp"), r = c.getBoundingClientRect(), k = Math.min(2, devicePixelRatio || 1);
      if (!r.width) return;
      if (c.width !== Math.round(r.width * k)) { c.width = Math.round(r.width * k); c.height = Math.round(r.height * k); }
      const reel = source !== "virtuelle" && flux.source, rg = reel ? flux.reglages() : null;
      const enr = cam.enregistre ? `REC ${Math.floor((performance.now() - cam.debutEnr) / 60000)}:${String(Math.floor(((performance.now() - cam.debutEnr) / 1000) % 60)).padStart(2, "0")}` : "";
      dessinerCadre(c.getContext("2d"), c.width, c.height, {
        tiers: $("#tiers").checked, rec: source === "reelle" ? "" : enr,
        texte: reel ? `RÉEL · ${rg.largeur} × ${rg.hauteur}${rg.ips ? ` · ${rg.ips} i/s` : ""} · affichage seul`
          : `VIRTUEL · ${scene.suivreRegard ? "regard" : "tête"} · aperçu ${cam.definition.join(" × ")} · ×${nb(scene.zoom)}`,
        alerte: reel && scene.salleDansLeChamp() ? "Salle dans le champ — aucune captation (G-06)" : "",
      });
    },
  };
})();
window.ROBOT_VIRTUEL.vue = vueRobot;

/* Aide : premières directives */
journal({ html: "Robot virtuel prêt. Donnez une directive écrite ou vocale, ou faites glisser une partie du corps." });
