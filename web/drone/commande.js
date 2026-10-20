/* Robo-Scène — commandes communes au drone et au chien : parole (ou texte tapé), flèches du clavier.
   Interprète pur (testé sous Node) : une phrase française → une suite d'actions ; la page exécute ces actions par les
   mêmes fonctions que ses boutons, de sorte qu'une commande vocale traverse exactement les mêmes contrôles (zones,
   sol praticable, pont et ses conditions) qu'un clic. La coupure des moteurs n'est jamais accessible à la voix.

   Conventions : « gauche » et « droite » sont celles du robot (comme pour un acteur) ; « cour », « jardin »,
   « lointain », « avant-scène » désignent les repères de la scène ; distances en mètres par défaut (« cm » accepté,
   « pas » = 0,3 m), angles en degrés (« quart de tour » = 90, « demi-tour » = 180) ; « puis » enchaîne les actions. */

/* Frontière de mot qui tient compte des lettres accentuées (\b de JavaScript ne connaît que [A-Za-z0-9_]). */
const FRONTIERE = String.raw`(?:(?<![\p{L}\d])(?=[\p{L}\d])|(?<=[\p{L}\d])(?![\p{L}\d]))`;
export const W = (src) => new RegExp(src.replace(/\\b/g, FRONTIERE), "u");

const UNITES = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize"];
const DIZAINES = { vingt: 20, trente: 30, quarante: 40, cinquante: 50, soixante: 60, "soixante-dix": 70, "quatre-vingt": 80, "quatre-vingts": 80, "quatre-vingt-dix": 90, cent: 100 };

export function normaliser(t) {
  return String(t || "").toLowerCase().replace(/[’`]/g, "'").replace(/\s+/g, " ").replace(/[.!?;:«»"]/g, " ").replace(/\s+/g, " ").trim();
}

/* Premier nombre de la phrase (chiffres, « 1,5 », mots français simples, « et demi ») ; null s'il n'y en a pas. */
export function nombre(t) {
  const m = t.match(/(-?\d+(?:[.,]\d+)?)/);
  if (m) {
    let v = parseFloat(m[1].replace(",", "."));
    if (/\bet demie?\b|½/.test(t)) v += 0.5;
    return v;
  }
  if (W(String.raw`\bdemi[- ]?(mètre|metre|tour)?\b`).test(t) && !/\bet demi\b/.test(t) && !/demi-tour/.test(t)) return 0.5;
  const mots = t.split(/[\s']+/);
  for (let i = 0; i < mots.length; i++) {
    let w = mots[i], v = null;
    if (w === "une") w = "un";
    if (DIZAINES[w] !== undefined) {
      v = DIZAINES[w];
      const suiv = (mots[i + 1] || "").replace(/^et-?/, "");
      const u = UNITES.indexOf(suiv === "une" ? "un" : suiv);
      if (mots[i + 1] === "et" && UNITES.indexOf(mots[i + 2]) > 0) v += UNITES.indexOf(mots[i + 2]);
      else if (u > 0) v += u;
    } else if (/^(vingt|trente|quarante|cinquante|soixante)-(et-)?(un|deux|trois|quatre|cinq|six|sept|huit|neuf)$/.test(w)) {
      const [d, , u] = w.split("-").length === 3 ? w.split("-") : [w.split("-")[0], null, w.split("-")[1]];
      v = DIZAINES[d] + UNITES.indexOf(u);
    } else if (UNITES.indexOf(w) >= 0 && !(w === "un" && /^(peu|instant|moment)$/.test(mots[i + 1] || ""))) v = UNITES.indexOf(w);
    if (v !== null) { if (/\bet demie?\b/.test(t)) v += 0.5; return v; }
  }
  return null;
}

function distance(t, defaut) {
  const n = nombre(t), arrondi = (x) => Math.round(x * 100) / 100;
  if (W(String.raw`\bun peu\b`).test(t) && n === null) return defaut / 2;
  if (n === null) return defaut;
  if (W(String.raw`\b(cm|centimètres?|centimetres?)\b`).test(t)) return arrondi(n / 100);
  if (W(String.raw`\bpas\b`).test(t) && !/\bne\b/.test(t)) return arrondi(n * 0.3);
  return n;
}

function angle(t, defaut = 90) {
  if (/demi-tour|demi tour/.test(t)) return 180;
  if (/quart de tour/.test(t)) return 90;
  if (W(String.raw`\b(tour complet|un tour)\b`).test(t)) return 360;
  const n = nombre(t);
  return n === null ? defaut : n;
}

/* Repère nommé reconnu dans la phrase (« centre », « cour », « avant-scène », « salle centre »…). */
/* Périphrases usuelles → repères (seulement si le repère existe pour ce robot). */
const ALIAS = [
  [String.raw`\b(centre|milieu) de la salle\b`, "salle_centre"], [String.raw`\bfond de la salle\b`, "salle_fond"],
  [String.raw`\bsalle (côté )?cour\b`, "salle_cour"], [String.raw`\bsalle (côté )?jardin\b`, "salle_jardin"],
  [String.raw`\b(haut|sommet) de l'?escalier (côté )?cour\b`, "haut_escalier_cour"], [String.raw`\bbas de l'?escalier (côté )?cour\b`, "bas_escalier_cour"],
  [String.raw`\b(haut|sommet) de l'?escalier (côté )?jardin\b`, "haut_escalier_jardin"], [String.raw`\bbas de l'?escalier (côté )?jardin\b`, "bas_escalier_jardin"],
  [String.raw`\b(milieu|centre) de l'?allée\b`, "allee_milieu"], [String.raw`\bfond de l'?allée\b`, "allee_fond"],
  [String.raw`\b(devant le premier rang|avant-salle|avant salle)\b`, "avant_salle_centre"], [String.raw`\b(ta marque|la marque|départ|point de départ)\b`, "depart"],
  [String.raw`\b(passage du cadre|sous le cadre|le cadre)\b`, "cadre_passage"], [String.raw`\b(entrée de la salle|entrée en salle)\b`, "salle_entree"],
  [String.raw`\bcentre en haut\b|\bau-dessus du centre\b`, "centre_haut"],
];

export function repereDans(t, reperes) {
  for (const [src, k] of ALIAS) if (reperes[k] && W(src).test(t)) return k;
  const cles = Object.keys(reperes).sort((a, b) => b.length - a.length);
  const forme = (k) => k.replace(/_/g, "[ -]?").replace(/avant\[ -\]\?scene/, "avant[ -]?sc[eè]ne").replace(/escalier/, "l?'?escalier");
  for (const k of cles) if (W(`\\b${forme(k)}\\b`).test(t)) return k;
  if (W(String.raw`\bavant[ -]?sc[eè]ne\b`).test(t) && reperes.avant_scene) return "avant_scene";
  return null;
}

const DIRECTIONS = [
  [W(String.raw`\b(avance|avancez|avancer|en avant|tout droit|devant)\b`), [0, 1, 0]],
  [W(String.raw`\b(recule|reculez|reculer|en arrière|arrière)\b`), [0, -1, 0]],
  [W(String.raw`\b(à gauche|a gauche|vers la gauche|sur la gauche|glisse à gauche|pas de côté à gauche)\b`), [-1, 0, 0]],
  [W(String.raw`\b(à droite|a droite|vers la droite|sur la droite|glisse à droite|pas de côté à droite)\b`), [1, 0, 0]],
  [W(String.raw`\b(monte|montez|monter|plus haut|en haut|élève-toi|eleve-toi)\b`), [0, 0, 1]],
  [W(String.raw`\b(descends|descendez|descendre|plus bas|en bas)\b`), [0, 0, -1]],
];

/* Interprète une phrase : robot = "drone" | "chien" ; rend { actions, inconnu }.
   actions : { type: "deplacer", droite, avant, haut } (mètres, repère du robot) ; { type: "tourner", angle } (degrés,
   positif = vers la gauche, sens antihoraire vu de dessus) ; { type: "aller", repere } ; { type: "arreter" } ;
   { type: "urgence" } ; { type: "go" } ; drone : decoller, atterrir, retour, regarder ; chien : lever, coucher,
   posture (nom), allure (nom), retour, regarder. */
export function interpreter(texte, robot, reperes = {}) {
  const t0 = normaliser(texte);
  const actions = [], inconnu = [];
  for (const t of t0.split(W(String.raw`\s*(?:,\s*)?\bpuis\b\s*|\s*,\s*et ensuite\s*|\s*;\s*`)).filter(Boolean)) {
    const a = phrase(t, robot, reperes);
    if (a) actions.push(...(Array.isArray(a) ? a : [a])); else inconnu.push(t);
  }
  return { actions, inconnu };
}

function phrase(t, robot, reperes) {
  if (W(String.raw`arr[eê]t d'urgence|\burgence\b|\barr[eê]t total\b`).test(t)) return { type: "urgence" };
  if (W(String.raw`^(stop|halte|arr[eê]te|arr[eê]tez|arr[eê]te-toi|on arr[eê]te|ne bouge plus|ne bougez plus|reste là|stationnaire|sur place|pause)\b`).test(t)) return { type: "arreter" };
  if (W(String.raw`^(go|top|suivant|repère suivant|envoie|envoyez)\b`).test(t)) return { type: "go" };
  if (robot === "drone") {
    if (W(String.raw`\b(décolle|décollez|décoller|decolle|envole-toi|envol|décollage)\b`).test(t)) return { type: "decoller", hauteur: nombre(t) ?? null };
    if (W(String.raw`\b(atterris|atterrissez|atterrir|atterrissage|pose-toi|posez-vous|pose toi)\b`).test(t)) return { type: "atterrir" };
    if (W(String.raw`\b(retour|reviens|rentre|à la base|a la base|aire de décollage)\b`).test(t) && !repereDans(t, reperes)) return { type: "retour" };
  } else {
    if (W(String.raw`\b(lève-toi|leve-toi|lève toi|debout|relève-toi|releve-toi|lève-toi)\b`).test(t)) return { type: "lever" };
    if (W(String.raw`\b(couché|couche|couche-toi|allonge-toi|dodo|repos)\b`).test(t)) return { type: "coucher" };
    if (W(String.raw`\b(assis|assieds-toi|assois-toi|assieds toi)\b`).test(t)) return { type: "posture", nom: "assis" };
    if (W(String.raw`\b(donne la patte|la patte|patte)\b`).test(t)) return { type: "posture", nom: "patte" };
    if (W(String.raw`\b(salue|salut|dis bonjour|bonjour)\b`).test(t)) return { type: "posture", nom: "salut" };
    if (W(String.raw`\b(étire-toi|etire-toi|étire|révérence|reverence|incline-toi)\b`).test(t)) return { type: "posture", nom: "etirement" };
    const allures = { joyeux: W(String.raw`\b(joyeux|joyeuse|content|heureux|joie)\b`), craintif: W(String.raw`\b(craintif|craintive|peur|peureux|apeuré)\b`),
      menacant: W(String.raw`\b(menaçant|menacant|menace|agressif|méchant)\b`), fatigue: W(String.raw`\b(fatigué|fatigue|las|épuisé)\b`),
      curieux: W(String.raw`\b(curieux|curieuse|curiosité)\b`), neutre: W(String.raw`\b(neutre|normal|normalement|calme)\b`) };
    for (const [nom, re] of Object.entries(allures)) if (re.test(t) && !/\b(va|avance|recule|tourne)\b/.test(t)) return { type: "allure", nom };
    if (W(String.raw`\b(retour|reviens|à ta place|a ta place|à ta marque|niche|rentre)\b`).test(t) && !repereDans(t, reperes)) return { type: "retour" };
  }
  if (W(String.raw`\b(regarde|vise|filme|tourne la tête vers|tourne la caméra vers)\b`).test(t)) {
    if (W(String.raw`\b(la salle|le public|les spectateurs)\b`).test(t)) return { type: "regarder", cible: "salle" };
    if (W(String.raw`\b(devant|droit devant|tout droit)\b`).test(t)) return { type: "regarder", cible: null };
    const r = repereDans(t, reperes); if (r) return { type: "regarder", cible: r };
  }
  if (W(String.raw`\b(demi-tour|demi tour|retourne-toi|fais volte-face)\b`).test(t)) return { type: "tourner", angle: 180 };
  if (W(String.raw`\b(tourne|pivote|tournez|pivotez|virage|rotation)\b`).test(t)) {
    const a = angle(t), droite = W(String.raw`\bdroite\b`).test(t);
    return { type: "tourner", angle: droite ? -a : a };
  }
  if (W(String.raw`\b(va|allez|aller|rends-toi|rends toi|déplace-toi|vole|marche|cours|file|direction|vers)\b`).test(t) || W(String.raw`^(à|au|aux|a)\b`).test(t)) {
    const r = repereDans(t, reperes); if (r) return { type: "aller", repere: r };
  }
  for (const [re, [dx, dy, dz]] of DIRECTIONS) {
    if (re.test(t)) {
      if (robot === "chien" && dz) return null;
      const d = distance(t, robot === "drone" && dz ? 0.5 : 1);
      return { type: "deplacer", droite: dx * d, avant: dy * d, haut: dz * d };
    }
  }
  const r = repereDans(t, reperes); if (r) return { type: "aller", repere: r };
  return null;
}

/* Flèches du clavier → manche [droite, avant] (repère du robot), selon le repère choisi :
   « robot » : ↑ avant, ↓ arrière, ← gauche, → droite (du robot) ;
   « scene » : ↑ vers le lointain, ↓ vers la salle, ← jardin, → cour (vu de la salle), converti selon le lacet. */
export function flechesVersManche(haut, bas, gauche, droite, repere, lacet) {
  const av = (haut ? 1 : 0) - (bas ? 1 : 0), dr = (droite ? 1 : 0) - (gauche ? 1 : 0);
  if (repere !== "scene") return [dr, av];
  const vx = dr, vz = -av;                         // monde : x vers cour, z vers la salle
  const n = Math.hypot(vx, vz); if (!n) return [0, 0];
  const f = [Math.sin(lacet), Math.cos(lacet)], r = [-Math.cos(lacet), Math.sin(lacet)];
  return [(vx * r[0] + vz * r[1]) / n, (vx * f[0] + vz * f[1]) / n];
}

/* Déplacement relatif (repère du robot) → point du théâtre. */
export function pointRelatif(p, lacet, droite, avant) {
  const f = [Math.sin(lacet), Math.cos(lacet)], r = [-Math.cos(lacet), Math.sin(lacet)];
  return [p[0] + f[0] * avant + r[0] * droite, p[1] + f[1] * avant + r[1] * droite];
}

/* Écoute vocale (Web Speech API). Traitement sur l'appareil exigé par défaut (processLocally) : sans lui, certains
   navigateurs, dont Chrome, envoient l'audio à un service distant ; la page le dit avant toute écoute. */
export class EcouteVocale {
  constructor({ surTexte, surInterim, surEtat }) { this.surTexte = surTexte; this.surInterim = surInterim || (() => {}); this.surEtat = surEtat || (() => {}); this.r = null; this.active = false; }
  static disponible() { return typeof window !== "undefined" && ("SpeechRecognition" in window || "webkitSpeechRecognition" in window); }
  async demarrer({ continu = false, local = true, langue = "fr-CA" } = {}) {
    if (!EcouteVocale.disponible()) { this.surEtat("indisponible", "Reconnaissance vocale non prise en charge par ce navigateur (essayer Chrome ou Edge)"); return false; }
    const R = window.SpeechRecognition || window.webkitSpeechRecognition;
    const r = (this.r = new R());
    r.interimResults = true; r.continuous = !!continu; r.maxAlternatives = 1;
    if (local) {
      if (!("processLocally" in r)) { this.surEtat("erreur", "Traitement sur l'appareil non proposé par ce navigateur : décocher « reconnaissance sur l'appareil » pour accepter un service distant"); return false; }
      // modèle de langue sur l'appareil : français du Canada, sinon de France ; téléchargé une fois au besoin
      if (typeof R.available === "function") {
        let choisie = null;
        for (const l of [langue, "fr-FR"]) {
          let d; try { d = await R.available({ langs: [l], processLocally: true }); } catch (e) { d = null; }
          if (d === "available") { choisie = l; break; }
          if ((d === "downloadable" || d === "downloading") && typeof R.install === "function") {
            this.surEtat("info", `Téléchargement du modèle de reconnaissance ${l} sur l'appareil…`);
            let ok = false; try { ok = await R.install({ langs: [l] }); } catch (e) { ok = false; }
            if (ok) { choisie = l; break; }
          }
        }
        if (!choisie) { this.surEtat("erreur", "Aucun modèle de reconnaissance du français sur l'appareil : décocher « reconnaissance sur l'appareil » pour accepter un service distant"); return false; }
        langue = choisie;
      }
      try { r.processLocally = true; } catch (e) { /* propriété en lecture seule */ }
    }
    r.lang = langue;
    this.continu = !!continu; this.active = true;
    r.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) this.surTexte(res[0].transcript.trim(), res[0].confidence); else interim += res[0].transcript;
      }
      this.surInterim(interim);
    };
    r.onerror = (e) => {
      const m = { "not-allowed": "Microphone refusé par le navigateur", "service-not-allowed": "Service de reconnaissance refusé", "language-not-supported": "Le français n'est pas installé pour la reconnaissance sur l'appareil",
        network: "Réseau requis par le service de reconnaissance", "no-speech": "Aucune parole entendue", "audio-capture": "Aucun microphone" }[e.error] || e.error;
      if (e.error !== "no-speech" && e.error !== "aborted") { this.active = false; this.surEtat("erreur", m); }
    };
    r.onend = () => { if (this.active && this.continu) { try { r.start(); } catch (e) { /* déjà relancée */ } } else { this.active = false; this.surEtat("arret"); } };
    try { r.start(); this.surEtat("ecoute"); } catch (e) { this.surEtat("erreur", e.message); return false; }
    return true;
  }
  arreter() { this.active = false; try { this.r?.stop(); } catch (e) { /* déjà arrêtée */ } this.surEtat("arret"); }
}

export const AIDE_VOIX = {
  drone: ["décolle", "atterris", "stop / reste là", "avance de 2 mètres", "recule de 50 centimètres", "à gauche d'un mètre", "monte d'un mètre", "descends", "tourne à droite de 45 degrés", "demi-tour", "va au centre", "va côté cour", "va à l'avant-scène", "reviens à la base", "regarde la salle", "décolle puis va au centre", "GO", "arrêt d'urgence"],
  chien: ["lève-toi", "couché", "assis", "donne la patte", "salue", "étire-toi", "stop", "avance de 3 pas", "recule d'un mètre", "à droite", "tourne à gauche", "demi-tour", "va au centre", "va à l'avant-scène", "reviens à ta place", "joyeux", "craintif", "regarde la salle", "lève-toi puis va au centre", "GO", "arrêt d'urgence"],
};
