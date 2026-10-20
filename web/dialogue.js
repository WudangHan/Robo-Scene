/* Robo-Scène — dialogue parlé avec le robot humanoïde, le chien ou le drone (demande du 20 octobre 2026).

   Une personne parle (micro de la page, reconnaissance sur l'appareil par défaut) ou écrit ; ce qui n'est pas une
   commande comprise par les règles de la page part au pont (op « dialogue »), qui le confie au moteur d'IA choisi
   pour cette machine : Claude, GPT, Grok, Gemini ou un modèle de LM Studio. La machine répond d'une voix humaine
   (profils de voix-direction.js : voix neuronales ou « Premium » du système de préférence, prosodie humanisée) et,
   si elle est reliée et le permet, par son propre haut-parleur.

   Sécurité : les actions que le modèle propose sont revalidées par le pont puis présentées ici ; rien ne bouge sans
   le clic « Valider » d'une personne. « Stop » et « arrêt d'urgence » restent traités par la page, même pendant que
   la machine parle. Demi-duplex : pendant la réponse parlée et 1,2 s après, ce que capte le micro est écarté (écho). */
import { estEcho } from "./avatar/parole.js";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const attendre = (ms) => new Promise((ok) => setTimeout(ok, ms));
const memo = {
  lire(k, d) { try { const v = localStorage.getItem(k); return v ? { ...d, ...JSON.parse(v) } : d; } catch (e) { return d; } },
  ecrire(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* stockage indisponible */ } },
};
const REVERBERATION_MS = 1200;

/* Voix humaine d'une machine : un des six profils de voix-direction.js (timbre du système, tempo, pauses). */
export class Locuteur {
  constructor(profil) { this.profil = profil; this.actif = false; this.jeton = 0; this.fin = 0; this.dits = []; }
  static disponible() { return typeof window !== "undefined" && "speechSynthesis" in window; }
  voix() {
    const toutes = Locuteur.disponible() ? speechSynthesis.getVoices() : [];
    const V = globalThis.VoixDirection;
    if (V) return V.attribuer(toutes)[this.profil] || null;
    return toutes.find((v) => /^fr/i.test(v.lang || "")) || null;
  }
  async dire(texte) {
    if (!Locuteur.disponible() || !String(texte || "").trim()) return;
    this.taire();
    const j = ++this.jeton; this.actif = true;
    this.dits.push({ texte, t: Date.now() }); if (this.dits.length > 6) this.dits.shift();
    const V = globalThis.VoixDirection;
    const rendu = V ? V.rendre(texte, this.profil, { final: false })
      : { volume: 1, segments: [{ texte, debit: 1, hauteur: 1, pause_apres_ms: 300 }] };
    const voix = this.voix();
    for (const s of rendu.segments) {
      if (j !== this.jeton) return;
      await new Promise((ok) => {
        const u = new SpeechSynthesisUtterance(s.texte);
        if (voix) { u.voice = voix; u.lang = voix.lang; } else u.lang = "fr-CA";
        u.rate = s.debit; u.pitch = s.hauteur; u.volume = rendu.volume ?? 1;
        const garde = setTimeout(ok, 5000 + s.texte.length * 120);   // certaines voix n'émettent jamais « end »
        u.onend = u.onerror = () => { clearTimeout(garde); ok(); };
        speechSynthesis.speak(u);
      });
      if (j !== this.jeton) return;
      await attendre(Math.min(s.pause_apres_ms, 900));
    }
    if (j === this.jeton) { this.actif = false; this.fin = Date.now(); }
  }
  taire() { this.jeton++; if (this.actif) this.fin = Date.now(); this.actif = false; try { if (Locuteur.disponible()) speechSynthesis.cancel(); } catch (e) { /* rien à taire */ } }
  get parle() { return this.actif || Date.now() - this.fin < REVERBERATION_MS; }
}

/* Libellé d'un moteur dans le sélecteur. */
function libelleMoteur(m) {
  const v = m.version && m.id !== "auto" && !m.id.startsWith("local:") ? ` — ${m.version}` : "";
  return `${m.libelle}${v}${m.si02 ? " (SI-02)" : ""}${m.disponible ? "" : " — indisponible"}`;
}

/* opts : { conteneur, domaine ("robot"|"chien"|"drone"), nom, envoyer(objet) → booléen, reperes() → [noms],
   contexte() → texte, executerActions(actions, libelle), decrire(action) → texte, journal(niveau, texte),
   parler(texte) (facultatif : voix propre de la page), parle() (facultatif), taire() (facultatif),
   profilDefaut, hautParleur (booléen : proposer « aussi par le haut-parleur du robot relié ») } */
export function installerDialogue(opts) {
  const { conteneur, domaine, nom } = opts;
  const cle = `robo-scene-dialogue-${domaine}`;
  const reglages = memo.lire(cle, { actif: true, profil: opts.profilDefaut || "laurent", hautParleur: false });
  const locuteur = new Locuteur(reglages.profil);
  const attentes = new Map(); let n = 0, pontOk = false;
  const V = globalThis.VoixDirection;

  conteneur.classList.add("dialogue");
  conteneur.innerHTML = `
    <div class="ligne petit"><label><input type="checkbox" data-d="actif"> Conversation : quand une phrase n'est pas une commande, ${esc(nom)} répond à voix haute</label></div>
    <div class="ligne petit"><label>Moteur d'IA <select data-d="moteur" aria-label="Moteur d'IA de ${esc(nom)}"><option value="auto">Automatique</option></select></label>
      <button type="button" class="discret" data-d="rafraichir" title="Relire la liste (modèles chargés dans LM Studio, clés API)">↻</button>
      <span data-d="etat" class="petit"></span></div>
    <div class="ligne petit" data-d="bloc-voix"><label>Voix <select data-d="profil"></select></label>
      <button type="button" data-d="essai">Écouter</button>
      ${opts.hautParleur ? `<label><input type="checkbox" data-d="haut-parleur"> aussi par le haut-parleur du robot relié</label>` : ""}</div>
    <ol class="flux dialogue-fil" data-d="fil" aria-live="polite"></ol>
    <form class="ligne" data-d="form">
      <input data-d="texte" autocomplete="off" maxlength="800" placeholder="Parler à ${esc(nom)} (ou utiliser le micro)" aria-label="Phrase pour ${esc(nom)}">
      <button type="submit" class="primaire">Dire</button>
      <button type="button" data-d="taire">Se taire</button>
      <button type="button" data-d="oublier" title="Effacer la mémoire courte de l'échange (six derniers tours)">Oublier l'échange</button>
    </form>
    <p class="petit note">Les phrases comprises comme des commandes s'exécutent comme d'habitude ; les autres reçoivent une réponse du moteur choisi.
      Un contenu jugé sensible (D03) va toujours au modèle local désigné (SI-02), ou il est refusé. Les gestes et déplacements que
      la machine propose attendent votre validation ; « stop » et « arrêt d'urgence » restent immédiats. Le journal de séance garde le moteur
      et les longueurs des échanges, pas leur texte. LM Studio peut tourner sur ce Mac ou, si <code>reseau_local = true</code> dans
      config.toml, sur un autre ordinateur du réseau Wi-Fi local (adresse privée seulement). Sur une tablette ou un
      téléphone relié au pont par le Wi-Fi, le navigateur ne donne le micro qu'en <code>https</code> : renseigner
      <code>certificat</code> et <code>cle</code> dans la section [serveur] de config.toml ; la voix de la machine, elle, fonctionne partout.</p>`;
  const q = (k) => conteneur.querySelector(`[data-d="${k}"]`);
  const fil = q("fil");

  q("actif").checked = !!reglages.actif;
  q("actif").onchange = (e) => { reglages.actif = e.target.checked; memo.ecrire(cle, reglages); };
  if (opts.parler) { q("bloc-voix").querySelector("label").hidden = true; q("essai").hidden = true; }
  const profils = V ? V.PROFILS : [];
  q("profil").innerHTML = profils.map((p) => `<option value="${p.id}">${esc(p.nom)} — ${esc(p.role)}</option>`).join("") || `<option value="">voix du système</option>`;
  q("profil").value = reglages.profil;
  q("profil").onchange = (e) => { reglages.profil = locuteur.profil = e.target.value; memo.ecrire(cle, reglages); };
  q("essai").onclick = () => locuteur.dire(`Bonjour, je suis ${nom}. Je vous écoute.`);
  if (q("haut-parleur")) {
    q("haut-parleur").checked = !!reglages.hautParleur;
    q("haut-parleur").onchange = (e) => { reglages.hautParleur = e.target.checked; memo.ecrire(cle, reglages); };
  }

  function ligne(qui, html, classe = "") {
    const li = document.createElement("li"); li.className = classe;
    li.innerHTML = `<b>${esc(qui)}</b> ${html}`;
    fil.appendChild(li); fil.scrollTop = fil.scrollHeight;
    while (fil.children.length > 60) fil.firstElementChild.remove();
    return li;
  }
  const parle = () => (opts.parle ? opts.parle() : locuteur.parle);
  function taire() { locuteur.taire(); opts.taire?.(); }
  async function dire(texte) {
    if (reglages.hautParleur && opts.hautParleur) opts.envoyer({ op: "robot_dire", texte, origine: "dialogue" });
    if (opts.parler) await opts.parler(texte); else await locuteur.dire(texte);
  }

  function demander(texte, source = "texte") {
    texte = String(texte || "").trim(); if (!texte) return false;
    const li = ligne("Vous", `${esc(texte)} <small>(${source === "voix" ? "🎙" : "⌨"})</small>`, "humain");
    if (!pontOk) {
      li.insertAdjacentHTML("beforeend", ` <span class="ignore">— pont non relié : pas de conversation possible</span>`);
      opts.journal?.("avert", `Dialogue : pont non relié, « ${texte} » sans réponse`);
      return false;
    }
    const ref = `${domaine}-${++n}`;
    const attente = ligne(nom, "<i>réfléchit…</i>", "machine attente");
    attentes.set(ref, { attente, texte });
    opts.envoyer({ op: "dialogue", ref, domaine, texte, reperes: opts.reperes?.() || [], contexte: opts.contexte?.() || "" });
    setTimeout(() => { if (attentes.has(ref)) { attentes.delete(ref); attente.innerHTML = `<b>${esc(nom)}</b> <span class="ignore">pas de réponse (délai dépassé)</span>`; } }, 60000);
    return true;
  }

  function proposer(li, r) {
    if (!r.actions?.length && !r.rejets?.length) return;
    const bloc = document.createElement("div"); bloc.className = "prop-dialogue";
    const desc = (a) => esc(opts.decrire ? opts.decrire(a) : JSON.stringify(a));
    bloc.innerHTML = `<div class="actions">${r.actions.map((a) => `<code>${desc(a)}</code>`).join(" ") || "<i>aucune action valide</i>"}</div>`
      + (r.rejets?.length ? `<div class="ignore">Écartées par le pont : ${r.rejets.map((x) => esc(x.motif)).join(" ; ")}</div>` : "")
      + (r.actions.length ? `<div class="ligne"><button type="button" class="primaire" data-ok>Valider</button><button type="button" data-non>Rejeter</button></div>` : "");
    li.appendChild(bloc);
    if (!r.actions.length) return;
    const decider = (ok) => {
      bloc.querySelector(".ligne").innerHTML = ok ? "<span class='ok'>Validée</span>" : "<span class='petit'>Rejetée</span>";
      opts.journal?.("info", `Dialogue : proposition ${ok ? "validée" : "rejetée"} (${r.actions.map((a) => (opts.decrire ? opts.decrire(a) : a.type)).join(", ")})`);
      if (ok) opts.executerActions(r.actions, `💬 « ${r.texte} »`);
    };
    bloc.querySelector("[data-ok]").onclick = () => decider(true);
    bloc.querySelector("[data-non]").onclick = () => decider(false);
  }

  function majMoteurs(m) {
    const sel = q("moteur");
    sel.innerHTML = (m.moteurs || []).map((x) => `<option value="${esc(x.id)}" ${x.disponible || x.id === "auto" ? "" : "class='indispo'"} title="${esc(x.motif || "")}">${esc(libelleMoteur(x))}</option>`).join("");
    const choix = m.choix?.[domaine] || "auto";
    if (![...sel.options].some((o) => o.value === choix)) sel.insertAdjacentHTML("beforeend", `<option value="${esc(choix)}">${esc(choix)} (absent)</option>`);
    sel.value = choix;
    const c = (m.moteurs || []).find((x) => x.id === choix);
    q("etat").textContent = c && !c.disponible && c.id !== "auto" ? `indisponible : ${c.motif}` : (m.reseau_local ? "LM Studio : réseau local permis" : "");
  }
  q("moteur").onchange = (e) => opts.envoyer({ op: "ia_choisir", domaine, moteur: e.target.value });
  q("rafraichir").onclick = () => opts.envoyer({ op: "ia_moteurs" });
  q("form").onsubmit = (e) => { e.preventDefault(); const t = q("texte").value; q("texte").value = ""; demander(t, "texte"); };
  q("taire").onclick = taire;
  q("oublier").onclick = () => { opts.envoyer({ op: "dialogue_oublier", domaine }); ligne("—", "<i>échange oublié</i>", "petit"); };

  async function recevoir(m) {
    if (m.type === "ia_moteurs") majMoteurs(m);
    else if (m.type === "ia_choix") { opts.envoyer({ op: "ia_moteurs" }); }
    else if (m.type === "dialogue_refus" && m.op === "ia_choisir") { q("etat").textContent = m.msg; opts.envoyer({ op: "ia_moteurs" }); }
    else if ((m.type === "dialogue" || m.type === "dialogue_refus") && attentes.has(m.ref)) {
      const { attente } = attentes.get(m.ref); attentes.delete(m.ref);
      if (m.type === "dialogue_refus") { attente.innerHTML = `<b>${esc(nom)}</b> <span class="ignore">${esc(m.msg)}</span>`; return; }
      attente.classList.remove("attente");
      attente.innerHTML = `<b>${esc(nom)}</b> ${esc(m.reponse)} <small class="moteur">${esc(m.moteur || "")}</small>`
        + (m.erreur ? `<div class="ignore">${esc(m.erreur)}</div>` : "");
      proposer(attente, m);
      await dire(m.reponse);
    }
  }

  return {
    actif: () => reglages.actif && pontOk,
    parle, taire, demander, recevoir,
    estEcho: (t) => estEcho(t, locuteur.dits.filter((d) => Date.now() - d.t < 15000).map((d) => d.texte)),
    pontOuvert() { pontOk = true; opts.envoyer({ op: "ia_moteurs" }); },
    pontFerme() { pontOk = false; },
  };
}
