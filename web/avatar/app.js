/* Robo-Scène — page « Robot virtuel » : assemblage de la scène, des directives écrites et
   vocales, des émotions, de la parole, de l'apparence, de l'imitation et des liaisons
   (page Partenaire, pont local, robot physique). */
import * as THREE from "three";
import { Humanoide, APPARENCE_DEFAUT, PEAUX, YEUX } from "./humanoide.js";
import { Animateur } from "./animation.js";
import { Scene, LIBELLES_ZONES, DOFS_ZONE } from "./scene.js";
import { Parole } from "./parole.js";
import { Imitation, lireEmotion } from "./imitation.js";
import { EMOTIONS, prosodie } from "./emotions.js";
import { interpreter, valider, EXEMPLES } from "./directives.js";

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
const imitation = new Imitation();
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
  jumeau.maj();
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
    case "apparence": return `apparence ${a.cle} ${a.relatif ? "+" : ""}${a.valeur}`;
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
  journal({ html: `<b>Arrêt</b> — ${echapper(motif)}`, classe: "alerte" });
}
function appliquerApparence(cle, valeur, relatif) {
  const A = humain.apparence;
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
  const ok = await parole.dire(segs, { debit, hauteur, volume, parler: true });
  if (ok) setTimeout(() => { if (!parole.actif) sousTitre(""); }, 900);
  return ok;
}
async function executer(actions, { source = "règles", clauseLog = null } = {}) {
  const jeton = ++enCours;
  memoriserEtat();
  let groupe = false;
  const tenir = async () => { if (groupe) { groupe = false; await attendre(650 / anim.vitesse); } };
  for (const a of actions) {
    if (jeton !== enCours) return;
    if (a.type !== "articulation") await tenir();
    switch (a.type) {
      case "articulation": anim.definir(a.dof, a.valeur, { relatif: !!a.relatif, vitesse: a.vitesse }); groupe = true; break;
      case "emotion": anim.definirEmotion(a.nom, a.intensite, !!a.relatif); await attendre(250); break;
      case "visage": anim.definirVisage(a.au, a.tenir !== false); await attendre(250); break;
      case "geste": await anim.jouerGeste(a.nom, { cote: a.cote || "d", repetitions: a.repetitions || 1, intensite: a.intensite || 1, direction: a.direction || "devant", vitesse: a.vitesse }); break;
      case "pose": anim.prendrePose(a.nom, a.vitesse); await attendre(900 / anim.vitesse); break;
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

/* ══════════ Directives écrites et vocales ══════════ */
async function executerTexte(texte, origine = "écrit") {
  texte = String(texte || "").trim();
  if (!texte) return;
  const r = interpreter(texte, SCHEMA);
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
/* Le robot répond toujours : s'il n'a pas compris, il le dit et le montre (haussement d'épaules, sous-titre). */
function repondreIncompris(ignores, enPartie) {
  if (!$("#repondre-incompris").checked) return;
  const phrase = enPartie ? `Je n'ai pas compris : ${ignores.join(", ")}.` : "Pardon, je n'ai pas compris. Dites « aide » pour connaître mes commandes.";
  setTimeout(async () => {
    if (!enPartie) anim.jouerGeste("hausser_epaules");
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

/* Dictée (reconnaissance vocale du navigateur, fr-CA) */
const Dictee = {
  rec: null, continu: false, actif: false,
  dispo() { return "SpeechRecognition" in window || "webkitSpeechRecognition" in window; },
  demarrer(continu) {
    if (!this.dispo()) { journal({ html: "La reconnaissance vocale n'est pas offerte par ce navigateur (essayez Chrome, Edge ou Safari récent).", classe: "avert" }); return; }
    const R = window.SpeechRecognition || window.webkitSpeechRecognition;
    const r = (this.rec = new R());
    r.lang = "fr-CA"; r.interimResults = true; r.continuous = !!continu; this.continu = !!continu;
    try { if ("processLocally" in r) r.processLocally = true; } catch (e) {}
    r.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const x = e.results[i];
        if (x.isFinal) { const t = x[0].transcript.trim(); $("#dictee-interim").textContent = ""; if (t) executerTexte(t, "vocal"); }
        else interim += x[0].transcript;
      }
      $("#dictee-interim").textContent = interim;
    };
    r.onerror = (e) => { if (e.error !== "no-speech") journal({ html: `Dictée : ${echapper(e.error)}`, classe: "avert" }); };
    r.onend = () => { if (this.actif && this.continu) { try { r.start(); } catch (e) {} } else this.fin(); };
    this.actif = true; r.start();
    $("#btn-micro").classList.add("actif"); $("#btn-micro").setAttribute("aria-pressed", "true");
  },
  arreter() { this.actif = false; try { this.rec?.stop(); } catch (e) {} this.fin(); },
  fin() { this.actif = false; $("#btn-micro").classList.remove("actif"); $("#btn-micro").setAttribute("aria-pressed", "false"); $("#dictee-interim").textContent = ""; },
};
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
  sautiller: "sautiller", serrer_main: "serrer la main", repousser: "repousser", trembler: "trembler", frotter_mains: "se frotter les mains",
  muscles: "montrer ses muscles", accolade: "accolade", lancer: "lancer", ramasser: "ramasser", pousser: "pousser", tirer: "tirer", boxer: "boxer",
  coup_de_pied: "coup de pied", pointes_pieds: "pointes des pieds", tituber: "tituber", regarder_loin: "scruter au loin", eternuer: "éternuer",
  tousser: "tousser", compter: "compter sur ses doigts", menacer: "menacer", hesiter: "hésiter", ecouter: "tendre l'oreille", bercer: "bercer",
  mimer_mur: "mur invisible (mime)", dormir: "dormir" };
$("#gestes").innerHTML = SCHEMA.gestes.map((g) => `<button data-g="${g}">${NOMS_GESTES[g] || g}</button>`).join("");
$$("#gestes [data-g]").forEach((b) => (b.onclick = () => { memoriserEtat(); anim.jouerGeste(b.dataset.g, { cote: $("#cote-geste").value }); }));
const NOMS_POSES = { repos: "repos", debout: "debout", assis: "assis", accroupi: "accroupi", a_genoux: "à genoux", garde_a_vous: "garde-à-vous", recroqueville: "recroquevillé",
  effondre: "effondré", en_garde: "en garde", penseur: "le penseur", statue: "statue" };
$("#poses").innerHTML = SCHEMA.poses.map((p) => `<button data-p="${p}">${NOMS_POSES[p] || p}</button>`).join("");
$$("#poses [data-p]").forEach((b) => (b.onclick = () => { memoriserEtat(); anim.prendrePose(b.dataset.p); setTimeout(majCurseurs, 50); }));
$("#btn-annuler").onclick = () => { if (!annuler()) journal({ html: "Rien à annuler." }); };

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
  for (const k of ["haut", "bas", "chaussures", "couleur_cheveux"]) $(`#ap-${k}`).value = hex(A[k]);
}
$("#ap-cheveux").innerHTML = SCHEMA.apparence.cheveux.map((x) => `<option>${x}</option>`).join("");
$("#ap-barbe").innerHTML = SCHEMA.apparence.barbe.map((x) => `<option>${x}</option>`).join("");
$("#ap-manches").innerHTML = SCHEMA.apparence.manches.map((x) => `<option>${x}</option>`).join("");
$("#ap-peau").innerHTML = Object.keys(PEAUX).map((x) => `<option>${x}</option>`).join("");
$("#ap-yeux").innerHTML = Object.keys(YEUX).map((x) => `<option>${x}</option>`).join("");
for (const k of ["taille", "carrure", "corpulence", "age"]) { const r = SCHEMA.apparence[k]; Object.assign($(`#ap-${k}`), { min: r.min, max: r.max, step: k === "taille" || k === "age" ? 1 : 0.01 }); $(`#ap-${k}`).oninput = (e) => appliquerApparence(k, Number(e.target.value)); }
for (const k of ["cheveux", "barbe", "manches", "peau", "yeux"]) $(`#ap-${k}`).onchange = (e) => appliquerApparence(k, e.target.value);
for (const k of ["haut", "bas", "chaussures", "couleur_cheveux"]) $(`#ap-${k}`).oninput = (e) => appliquerApparence(k, e.target.value);
$("#ap-moustache").onchange = (e) => appliquerApparence("moustache", e.target.checked);
$("#ap-defaut").onclick = () => { humain.appliquerApparence({ ...APPARENCE_DEFAUT }); ecrireLS("robo-scene-avatar-apparence", humain.apparence); majApparence(); };
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
    this.ws.onopen = () => { this.ouvert = true; P.ouvert(); this.envoyer("p_avatar_etat"); majPont(); };
    this.ws.onclose = () => { this.ouvert = false; this.ia = false; P.ferme(); majPont(); setTimeout(() => this.connecter(), 2500); };
    this.ws.onmessage = (ev) => {
      let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
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
function majPont() {
  $("#st-pont").textContent = pont.ouvert ? `Pont : relié${pont.cfg ? ` · ${pont.cfg.robot}` : ""}` : "Pont : non relié";
  $("#st-pont").className = "pastille " + (pont.ouvert ? "ok" : "neutre");
  $("#recours-claude").disabled = !pont.ia;
  $("#etat-claude").textContent = pont.ia ? "disponible" : pont.ouvert ? "pont relié, aucun modèle disponible (règles seulement)" : "pont non relié";
  const compatible = jumeau.compatible();
  $("#jumeau-reflet").disabled = $("#jumeau-pilote").disabled = !pont.ouvert || !compatible;
  $("#jumeau-info").textContent = !pont.cfg ? "—" : `Robot actif : ${pont.cfg.robot || pont.cfg.robot_id || "?"} — articulations : ${pont.cfg.noms.join(", ")}.`
    + (compatible ? "" : " La correspondance proposée ne vaut que pour un robot à quatre servos Base, Épaule, Coude, Tête ; le jumeau est désactivé pour ce robot.");
}
/* Jumeau : correspondance entre les 4 servos du robot (Base, Épaule, Coude, Tête) et le robot virtuel
   (Inférence de conception, modifiable) : écart au repos pour Base → rotation du tronc, Épaule → flexion de
   l'épaule droite, Tête → rotation de la tête ; écart au minimum pour Coude → flexion du coude droit. */
const jumeau = {
  reflet: false, pilote: false, dernierEnvoi: 0, dernier: null,
  compatible() {
    const n = (pont.cfg?.noms || []).map((x) => x.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase());
    return n.length === 4 && ["base", "epaule", "coude", "tete"].every((x, i) => n[i].startsWith(x));
  },
  surEtat(m) {
    if (!this.reflet || !Array.isArray(m.deg) || !this.compatible()) return;
    const { repos, min_deg: mn } = pont.cfg, d = m.deg;
    if (d[0] != null) anim.definir("tronc.rotation", d[0] - repos[0]);
    if (d[1] != null) anim.definir("epaule_d.flexion", d[1] - repos[1]);
    if (d[2] != null) anim.definir("coude_d.flexion", d[2] - mn[2]);
    if (d[3] != null) anim.definir("tete.rotation", d[3] - repos[3]);
  },
  maj() {
    if (!this.pilote || !pont.ouvert || !this.compatible() || pont.estop) return;
    const t = performance.now(); if (t - this.dernierEnvoi < 200) return;
    const { repos, min_deg: mn, max_deg: mx } = pont.cfg, v = anim.val;
    const brut = [repos[0] + v["tronc.rotation"], repos[1] + v["epaule_d.flexion"], mn[2] + v["coude_d.flexion"], repos[3] + v["tete.rotation"]];
    const deg = brut.slice(0, pont.cfg.noms.length).map((x, i) => Math.round(Math.max(mn[i], Math.min(mx[i], x))));
    if (this.dernier && deg.every((x, i) => Math.abs(x - this.dernier[i]) < 1)) return;
    this.dernier = deg; this.dernierEnvoi = t;
    pont.envoyer("articulations", { deg, ms: 250, origine: "avatar", robot: pont.cfg.robot_id });
  },
};
$("#jumeau-reflet").onchange = (e) => { jumeau.reflet = e.target.checked; if (e.target.checked) { jumeau.pilote = false; $("#jumeau-pilote").checked = false; } };
$("#jumeau-pilote").onchange = (e) => {
  if (e.target.checked && !confirm("Le bras droit, le tronc et la tête du robot virtuel vont piloter le robot physique (les commandes passent par la couche de sécurité du pont). Vérifiez que la scène est dégagée. Continuer ?")) { e.target.checked = false; return; }
  jumeau.pilote = e.target.checked; jumeau.dernier = null;
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

/* Aide : premières directives */
journal({ html: "Robot virtuel prêt. Donnez une directive écrite ou vocale, ou faites glisser une partie du corps." });
