/* Robo-Scène — parole du robot virtuel : synthèse vocale du navigateur (Web Speech API),
   synchronisation labiale par visèmes approximés à partir de la graphie française, et
   « battements » (petits mouvements de tête et de sourcils sur les mots longs et en fin de
   groupe rythmique). Les événements « boundary » de la synthèse, quand la voix en fournit,
   recalent l'horloge des visèmes ; sinon un débit estimé sert de repli. */

/* Visèmes : {jaw : ouverture, pucker : arrondi, stretch : étirement, press : lèvres closes} */
const VIS = {
  a: { jaw: 0.75, stretch: 0.25 }, e: { jaw: 0.42, stretch: 0.35 }, i: { jaw: 0.18, stretch: 0.6 },
  o: { jaw: 0.5, pucker: 0.6 }, ou: { jaw: 0.2, pucker: 0.95 }, u: { jaw: 0.18, pucker: 0.9 }, eu: { jaw: 0.32, pucker: 0.5 },
  an: { jaw: 0.6, pucker: 0.15 }, on: { jaw: 0.38, pucker: 0.65 }, in: { jaw: 0.35, stretch: 0.3 },
  pbm: { jaw: 0, press: 1 }, fv: { jaw: 0.08, press: 0.45 }, ch: { jaw: 0.2, pucker: 0.7 },
  dent: { jaw: 0.14, stretch: 0.3 }, r: { jaw: 0.28 }, k: { jaw: 0.3 }, repos: { jaw: 0 },
};
const REGLES = [
  [/^(eau|au|o|ô)/, "o"], [/^(ou|où|oû)/, "ou"], [/^(eu|œu|oeu)/, "eu"], [/^(an|am|en|em)(?![aeiouyéèênm])/, "an"],
  [/^(on|om)(?![aeiouyéèênm])/, "on"], [/^(ain|ein|in|im|un|um)(?![aeiouyéèênm])/, "in"], [/^(ai|ei|é|è|ê|ë|e)/, "e"],
  [/^(a|à|â)/, "a"], [/^(i|î|ï|y)/, "i"], [/^(u|û|ü)/, "u"], [/^(oi|oy)/, "a"],
  [/^(p|b|m)/, "pbm"], [/^(f|v|ph)/, "fv"], [/^(ch|j|ge|gi|sh)/, "ch"], [/^(s|z|c|ç|t|d|n|l|x)/, "dent"], [/^r/, "r"], [/^(k|q|g|gu)/, "k"],
];

export function visemes(texte) {
  const t = String(texte || "").toLowerCase();
  const out = [];
  let i = 0;
  while (i < t.length) {
    const reste = t.slice(i);
    if (/^[\s,.;:!?«»"()—–-]/.test(reste)) { out.push({ i, n: 1, v: /^[,.;:!?]/.test(reste) ? "pause" : "repos" }); i++; continue; }
    const r = REGLES.find(([re]) => re.test(reste));
    if (r) { const n = reste.match(r[0])[0].length; out.push({ i, n, v: r[1] }); i += n; }
    else { out.push({ i, n: 1, v: "repos" }); i++; }
  }
  return out;
}

function voixMasculine(v) {
  return /thomas|daniel|nicolas|paul|henri|jacques|antoine|f[ée]lix|mathieu|guillaume|jean|louis|olivier|eddy|reed|rocko|grandpa|male|homme|masculin/i.test(v.name);
}

export class Parole {
  constructor() {
    this.voix = []; this.jeton = 0; this.actif = false;
    this.bouche = { jaw: 0, pucker: 0, stretch: 0, press: 0 };
    this.ligne = null;            // {vis, debut, cps, ancre:{c,t}, mots:[...]}
    this.surBattement = null;     // rappel(forme) : battement sur un mot accentué
    this.surMot = null;
    this.choix = null;            // nom de voix imposé par l'utilisateur
    this.charger();
  }
  charger() {
    const lire = () => { try { this.voix = (speechSynthesis.getVoices() || []).filter((v) => /^fr/i.test(v.lang || "")); } catch (e) { this.voix = []; } };
    if ("speechSynthesis" in window) { lire(); speechSynthesis.addEventListener?.("voiceschanged", lire); }
  }
  voixChoisie() {
    if (!this.voix.length) return null;
    if (this.choix) { const v = this.voix.find((x) => x.name === this.choix); if (v) return v; }
    const masc = this.voix.filter(voixMasculine);
    const ca = (l) => l.find((v) => /fr-ca/i.test(v.lang));
    return ca(masc) || masc[0] || ca(this.voix) || this.voix[0];
  }
  annuler() {
    this.jeton++; this.actif = false; this.ligne = null;
    try { if ("speechSynthesis" in window) speechSynthesis.cancel(); } catch (e) {}
  }
  /* segments : [{texte, pause_apres_ms}] ; prosodie : {debit, hauteur, volume} */
  async dire(segments, { debit = 1, hauteur = 0.92, volume = 0.9, parler = true } = {}) {
    if (typeof segments === "string") segments = [{ texte: segments, pause_apres_ms: 0 }];
    const j = ++this.jeton; this.actif = true;
    try { if ("speechSynthesis" in window) speechSynthesis.cancel(); } catch (e) {}
    for (const seg of segments) {
      if (j !== this.jeton) return false;
      await this.segment(seg.texte, { debit, hauteur, volume, parler }, j);
      if (seg.pause_apres_ms && j === this.jeton) { this.ligne = null; await new Promise((r) => setTimeout(r, seg.pause_apres_ms)); }
    }
    if (j === this.jeton) { this.actif = false; this.ligne = null; }
    return j === this.jeton;
  }
  segment(texte, p, j) {
    const cps = 13.5 * p.debit;                                   // caractères par seconde (≈ 5,2 syllabes/s)
    const mots = [...texte.matchAll(/[\p{L}\p{N}'’-]+/gu)].map((m) => ({ c: m.index, n: m[0].length, mot: m[0], fait: false }));
    mots.forEach((m, k) => { const apres = texte.slice(m.c + m.n, m.c + m.n + 2); m.accent = m.n >= 7 || /[,;:!?]/.test(apres) || k === mots.length - 1; });
    const ligne = (this.ligne = { texte, vis: visemes(texte), cps, ancre: { c: 0, t: performance.now() }, mots, son: false });
    const voix = this.voixChoisie();
    const synthese = p.parler && "speechSynthesis" in window && voix;
    if (!synthese) {
      const duree = Math.max(400, texte.length / cps * 1000);
      return new Promise((fin) => setTimeout(fin, duree));
    }
    return new Promise((fin) => {
      const u = new SpeechSynthesisUtterance(texte);
      u.voice = voix; u.lang = voix.lang || "fr-CA";
      u.rate = p.debit; u.pitch = p.hauteur; u.volume = p.volume;
      const garde = setTimeout(fin, 2500 + texte.length * 130 / p.debit);
      u.onstart = () => { ligne.ancre = { c: 0, t: performance.now() }; ligne.son = true; };
      u.onboundary = (e) => { if (e.name === "word" || e.name === undefined) ligne.ancre = { c: e.charIndex, t: performance.now() }; };
      u.onend = u.onerror = () => { clearTimeout(garde); fin(); };
      if (j === this.jeton) speechSynthesis.speak(u); else { clearTimeout(garde); fin(); }
    });
  }
  /* appelé à chaque image : renvoie la contribution de la bouche */
  maj(dt) {
    const cible = { jaw: 0, pucker: 0, stretch: 0, press: 0 };
    const L = this.ligne;
    if (L) {
      const c = L.ancre.c + (performance.now() - L.ancre.t) / 1000 * L.cps;
      const v = L.vis.find((x) => c >= x.i && c < x.i + x.n);
      if (v && VIS[v.v]) Object.assign(cible, VIS[v.v]);
      for (const m of L.mots) if (!m.fait && c >= m.c) { m.fait = true; this.surMot?.(m); if (m.accent) this.surBattement?.(m); }
    }
    const k = 1 - Math.exp(-dt / 0.045);                         // lissage (coarticulation sommaire)
    for (const x in this.bouche) this.bouche[x] += ((cible[x] || 0) - this.bouche[x]) * k;
    return this.bouche;
  }
}
