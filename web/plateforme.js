/* Outils communs aux pages de la plateforme : appels JSON (en-tête X-Plateforme), échappement, messages. */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const t = (s) => (window.I18N ? window.I18N.t(s) : s);

async function api(chemin, corps, entete = { "X-Plateforme": "1" }) {
  const opts = corps === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json", ...entete }, body: JSON.stringify(corps) };
  const r = await fetch(chemin, opts);
  let d = {};
  try { d = await r.json(); } catch (e) { d = { erreur: `HTTP ${r.status}` }; }
  if (!r.ok) { const err = new Error(d.erreur || `HTTP ${r.status}`); err.verrou = !!d.verrou || r.status === 409; err.donnees = d; throw err; }
  return d;
}

function message(cible, texte, type = "ok") {
  const el = typeof cible === "string" ? $(cible) : cible;
  if (!el) return;
  el.className = `message ${type}`;
  el.setAttribute("role", type === "erreur" ? "alert" : "status");
  el.textContent = texte;
}

async function agir(cible, fn) {
  try { const r = await fn(); message(cible, "✓"); return r; } catch (e) { message(cible, (e.verrou ? `${t("Verrou de gouvernance")} — ` : "") + e.message, "erreur"); return null; }
}

function etiquette(texte, type = "info") { return `<span class="etiquette ${type}">${esc(texte)}</span>`; }

function tableau(lignes, colonnes) {
  if (!lignes || !lignes.length) return `<p class="petit">${t("Aucune donnée.")}</p>`;
  return `<div class="defile"><table class="donnees"><thead><tr>${colonnes.map(([, l]) => `<th scope="col">${esc(l)}</th>`).join("")}</tr></thead><tbody>`
    + lignes.map((l) => `<tr>${colonnes.map(([k, , f]) => `<td>${f ? f(l[k], l) : esc(l[k] ?? "—")}</td>`).join("")}</tr>`).join("")
    + "</tbody></table></div>";
}
