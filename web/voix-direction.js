/* Voix de la direction d'exercices — six profils de voix humaines pour la personne qui guide les exercices
   dans la page Partenaire (onglet Formation).

   Principes :
   - La direction d'exercices est une figure humaine, distincte du partenaire robotique : sa voix n'est jamais
     confiée au robot virtuel ni à la voie tonale, et elle privilégie les voix les plus naturelles que le
     navigateur expose (voix neuronales, « Premium », « Améliorée »), en écartant les voix synthétiques anciennes.
   - Les six profils sont des personnages fictifs ; aucun n'imite la voix d'une personne réelle.
   - Le timbre vient de la voix du système ; le caractère de chaque profil tient surtout au tempo, aux pauses
     et à de faibles variations d'une phrase à l'autre, car un fort décalage de hauteur dégrade le naturel
     d'une voix de synthèse (choix de conception).
   - L'humanisation est déterministe (graine tirée du texte) : un même texte dit par un même profil produit
     toujours le même rendu, ce qui garde les séances comparables et les tests reproductibles.

   Le module ne dépend d'aucune API du navigateur : il reçoit la liste des voix (objets ayant name, lang,
   localService) et rend des « rendus » au format attendu par Voix.dire de partenaire.js. */
"use strict";
(function (racine) {
  const PROFILS = [
    { id: "mathilde", nom: "Mathilde", role: "pédagogue chaleureuse", genre: "f", langue: "fr-CA",
      debit: 0.93, hauteur: 1.02, volume: 0.92, variation: 0.035,
      pauses: { phrase: 520, question: 700, souffle: 900, fin: 900 },
      description: "Voix douce et accueillante, débit posé ; convient aux premières séances et aux échauffements." },
    { id: "etienne", nom: "Étienne", role: "metteur en scène posé", genre: "m", langue: "fr-CA",
      debit: 0.9, hauteur: 0.97, volume: 0.95, variation: 0.03,
      pauses: { phrase: 600, question: 780, souffle: 950, fin: 1000 },
      description: "Voix grave et calme, silences francs entre les consignes ; pour le travail de plateau." },
    { id: "sophie", nom: "Sophie", role: "coach énergique", genre: "f", langue: "fr-FR",
      debit: 1.03, hauteur: 1.03, volume: 1, variation: 0.045,
      pauses: { phrase: 360, question: 480, souffle: 650, fin: 650 },
      description: "Voix vive et engagée, relances rapides ; pour les exercices d'énergie, de rythme et d'improvisation." },
    { id: "gabriel", nom: "Gabriel", role: "guide du souffle et de la détente", genre: "m", langue: "fr-CA",
      debit: 0.82, hauteur: 0.96, volume: 0.82, variation: 0.02,
      pauses: { phrase: 900, question: 1000, souffle: 1800, fin: 1500 },
      description: "Voix lente et enveloppante, longs temps de respiration ; pour la relaxation, le souffle et la concentration." },
    { id: "claire", nom: "Claire", role: "répétitrice précise", genre: "f", langue: "fr-FR",
      debit: 0.97, hauteur: 1, volume: 0.95, variation: 0.025,
      pauses: { phrase: 450, question: 600, souffle: 800, fin: 800 },
      description: "Voix nette et articulée, consignes détachées ; pour la diction, le texte et la mémorisation." },
    { id: "laurent", nom: "Laurent", role: "maître de stage bienveillant", genre: "m", langue: "fr-FR",
      debit: 0.91, hauteur: 0.95, volume: 0.93, variation: 0.035,
      pauses: { phrase: 560, question: 720, souffle: 900, fin: 950 },
      description: "Voix mûre et rassurante, ton de conversation ; pour les retours, les bilans et les exercices d'écoute." },
  ];
  const DEFAUT = "mathilde";

  /* Bornes de sécurité du rendu : au-delà, la synthèse perd en intelligibilité ou en naturel. */
  const BORNES = { debit: [0.75, 1.15], hauteur: [0.9, 1.08], volume: [0.4, 1] };
  const borner = (x, [a, b]) => Math.min(b, Math.max(a, x));

  /* ── Classement des voix du système ─────────────────────────────── */
  // Indices de prénoms (heuristique : les navigateurs n'exposent pas le genre d'une voix).
  const FEMININ = /am[ée]lie|chantal|audrey|aur[ée]lie|\bmarie\b|virginie|sylvie|denise|[ée]lo[iï]se|jos[ée]phine|c[ée]leste|brigitte|jacqueline|yvette|coralie|vivienne|caroline|nathalie|julie|hortense|\bl[ée]a\b|\bclara\b|\bmanon\b|google fran[cç]ais|female|femme|f[ée]minin/i;
  const MASCULIN = /thomas|daniel|nicolas|\bpaul\b|henri|jacques|antoine|f[ée]lix|mathieu|guillaume|\bjean\b|louis|olivier|thierry|alain|lucien|maurice|j[ée]r[ôo]me|\byves\b|r[ée]my|\bclaude\b|\bmale\b|homme|masculin/i;
  // Voix anciennes ou de fantaisie : lisibles mais nettement « robotiques ».
  const SYNTHETIQUE = /\beddy\b|\bflo\b|grandma|grandpa|\breed\b|rocko|\bsandy\b|shelley|compact|espeak|robot|albert|bad news|good news|\bbells\b|boing|bubbles|cellos|jester|\borgan\b|superstar|trinoids|whisper|wobble|zarvox|bahh/i;

  function genre(v) {
    const n = (v && v.name) || "";
    if (FEMININ.test(n)) return "f";
    if (MASCULIN.test(n)) return "m";
    return "x";
  }
  /* Qualité perçue d'après le nom que le navigateur donne à la voix (heuristique documentée). */
  function qualite(v) {
    const n = (v && v.name) || "";
    if (SYNTHETIQUE.test(n)) return { rang: 0, libelle: "synthétique ancienne", points: -60 };
    if (/natural|neural|naturel/i.test(n)) return { rang: 3, libelle: "neuronale (la plus naturelle)", points: 45 };
    if (/premium/i.test(n)) return { rang: 3, libelle: "Premium (très naturelle)", points: 40 };
    if (/enhanced|am[ée]lior[ée]e?|siri/i.test(n)) return { rang: 2, libelle: "améliorée", points: 28 };
    if (/google/i.test(n)) return { rang: 2, libelle: "en ligne (Google)", points: 18 };
    return { rang: 1, libelle: "standard", points: 0 };
  }
  const francaise = (v) => !!(v && v.lang && /^fr/i.test(v.lang));
  const locale = (v) => !(v && v.localService === false);

  function score(profil, v) {
    let s = qualite(v).points;
    const g = genre(v);
    s += g === profil.genre ? 30 : g === "x" ? 4 : -35;
    const lang = String(v.lang || "").toLowerCase().replace("_", "-");
    if (lang === profil.langue.toLowerCase()) s += 12; else if (lang.startsWith("fr")) s += 4;
    if (locale(v)) s += 3;   // latence plus faible, aucun envoi du texte
    return s;
  }

  /* Attribue une voix du système à chacun des six profils, en évitant les doublons tant que possible.
     options : { localesSeulement, imposees: {idProfil: nomVoix} } */
  function attribuer(voix, options = {}) {
    const fr = (voix || []).filter(francaise).filter((v) => !options.localesSeulement || locale(v));
    const imposees = options.imposees || {};
    const res = {}, utilisees = new Map();
    for (const p of PROFILS) {
      const imp = imposees[p.id] && fr.find((v) => v.name === imposees[p.id]);
      if (imp) { res[p.id] = imp; utilisees.set(imp.name, (utilisees.get(imp.name) || 0) + 1); }
    }
    for (const p of PROFILS) {
      if (res[p.id]) continue;
      let meilleure = null, sMax = -Infinity;
      for (const v of fr) {
        const s = score(p, v) - 50 * (utilisees.get(v.name) || 0);
        if (s > sMax) { sMax = s; meilleure = v; }
      }
      res[p.id] = meilleure;
      if (meilleure) utilisees.set(meilleure.name, (utilisees.get(meilleure.name) || 0) + 1);
    }
    return res;
  }
  /* Voix françaises triées pour un profil (pour le menu « voix du système »). */
  function classer(profil, voix, options = {}) {
    return (voix || []).filter(francaise).filter((v) => !options.localesSeulement || locale(v))
      .map((v) => ({ v, s: score(profil, v) })).sort((a, b) => b.s - a.s).map((x) => x.v);
  }

  /* ── Humanisation de la prosodie ───────────────────────────────── */
  function graine(texte) {   // FNV-1a 32 bits
    let h = 0x811c9dc5;
    for (let i = 0; i < texte.length; i++) { h ^= texte.charCodeAt(i); h = Math.imul(h, 0x01000193); }
    return h >>> 0;
  }
  function alea(g) {          // mulberry32
    let a = g >>> 0;
    return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }
  /* Abréviations du livret que la synthèse lit mal, rendues comme les dirait une personne. */
  const ABREVIATIONS = [
    [/\bp\. ?ex\./gi, "par exemple"], [/\benv\./gi, "environ"], [/\bcf\./gi, "voir"], [/\betc\.(?=\s*[,;:)])/gi, "et cetera"], [/\betc\./gi, "et cetera."],
    [/\bN\.?B\.?\s*:/g, "Note :"], [/\bmin\b\.?/g, "minutes"], [/\bsec\b\.?/g, "secondes"],
    [/\b1re\b/g, "première"], [/\b1er\b/g, "premier"], [/\b2e\b/g, "deuxième"], [/\b3e\b/g, "troisième"],
    [/([A-Za-zÀ-ÿ])\s*\/\s*([A-Za-zÀ-ÿ])/g, "$1 ou $2"], [/\s*→\s*/g, ", puis "], [/([A-Za-zÀ-ÿ])\s+\+\s+([A-Za-zÀ-ÿ])/g, "$1 et $2"], [/\s+[–—]\s+/g, ", "],
  ];
  function normaliser(texte) {
    let t = String(texte || "").replace(/\s+/g, " ").trim();
    for (const [re, rep] of ABREVIATIONS) t = t.replace(re, rep);
    t = t.replace(/\(([^)]{1,140})\)/g, ", $1,").replace(/,\s*([.;:!?])/g, "$1").replace(/,\s*,/g, ",").replace(/\s+,/g, ",");
    return t.replace(/\s+/g, " ").trim();
  }
  /* Découpe en phrases (pas aux virgules : la synthèse donne une intonation conclusive à chaque énoncé,
     ce qui morcellerait la phrase). Une phrase très longue est coupée à un point-virgule ou à un deux-points. */
  function phrases(texte) {
    const out = [];
    for (const p of texte.split(/(?<=[.!?…])\s+/).filter(Boolean)) {
      if (p.length <= 220) { out.push(p); continue; }
      out.push(...p.split(/(?<=[;:])\s+/).filter(Boolean));
    }
    return out;
  }
  const SOUFFLE = /\b(inspirez|expirez|respirez|soufflez|relâchez|relachez|fermez les yeux|détendez|detendez|laissez aller|prenez (un|le) temps)\b/i;

  /* Rend un texte de consigne au format de Voix.dire, avec une prosodie humanisée.
     options : { humaniser = true, final = true } — final : la consigne clôt une étape (pause plus longue). */
  function rendre(texte, idProfil, options = {}) {
    const p = PROFILS.find((x) => x.id === idProfil) || PROFILS[0];
    const humain = options.humaniser !== false;
    const t = normaliser(texte);
    const ph = phrases(t);
    const r = alea(graine(p.id + "|" + t));
    const segments = ph.map((s, i) => {
      const dernier = i === ph.length - 1;
      const jit = humain ? (r() - 0.5) * 2 * p.variation : 0;
      const jitH = humain ? (r() - 0.5) * p.variation : 0;
      let debit = p.debit * (1 + jit);
      if (humain && dernier && ph.length > 1) debit *= 0.96;            // léger ralentissement conclusif
      if (humain && s.length < 28) debit *= 0.97;                       // consigne brève : plus détachée
      let pause = /\?$/.test(s) ? p.pauses.question : p.pauses.phrase;
      if (humain) pause *= 0.85 + 0.3 * r() + Math.min(0.35, s.length / 400);   // les phrases longues appellent un temps plus long
      if (SOUFFLE.test(s)) pause = Math.max(pause, p.pauses.souffle);    // laisser le temps de faire ce qui est demandé
      if (dernier) pause = options.final === false ? Math.min(pause, p.pauses.phrase) : p.pauses.fin;
      return { texte: s, debit: +borner(debit, BORNES.debit).toFixed(3),
               hauteur: +borner(p.hauteur * (1 + jitH), BORNES.hauteur).toFixed(3), pause_apres_ms: Math.round(pause) };
    });
    const parole = segments.reduce((d, s) => d + s.texte.split(/\s+/).length * 360 / s.debit + s.pause_apres_ms, 0);
    return { parler: segments.length > 0, debit: p.debit, hauteur: p.hauteur, volume: borner(p.volume, BORNES.volume),
             segments, duree_estimee_ms: Math.round(parole), profil: p.id };
  }

  function echantillon(idProfil) {
    const p = PROFILS.find((x) => x.id === idProfil) || PROFILS[0];
    return `Bonjour, je suis ${p.nom}. Je vais vous guider dans cet exercice. Installez-vous debout, les pieds bien ancrés au sol. Inspirez lentement… puis relâchez les épaules. Quand vous êtes prêts, nous commençons.`;
  }

  const api = { PROFILS, DEFAUT, BORNES, genre, qualite, score, attribuer, classer, normaliser, phrases, rendre, echantillon, locale };
  racine.VoixDirection = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
