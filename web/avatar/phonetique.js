/* Robo-Scène — phonétisation orthographique française pour la synchronisation labiale (audit du 2026-10-16).

   La graphie est convertie en segments {i, n, v, muet?} : i = position dans le texte, n = nombre de caractères,
   v = visème (clé de VIS dans parole.js). Une lettre muette ne déclenche aucun mouvement : elle prolonge le
   visème précédent (muet: true). Règles :
   - digrammes et trigrammes : eau/au → o ; ou → ou ; oi → ou + a (/wa/) ; eu, œu → eu ; ai, ei → e ;
     ch → ch ; ph → fv ; gn → dent ; qu, gu(e/i) → k (u muet) ; c, g devant e/i/y → dent, ch ;
   - voyelles nasales an/en/am/em, on/om, in/im/ain/ein/un/um quand elles ne précèdent ni voyelle ni n/m ;
   - lettres finales muettes : -e, -es (polysyllabes), d p s t x z, -er des infinitifs, -ent verbal après
     « ils » ou « elles », h toujours muet ; listes d'exceptions (« mer », « fils », « sept »…) ;
   - liaisons usuelles (les amis, nous avons, très heureux) : la consonne finale devient alvéolaire (dent).
   Limites : pas d'analyse grammaticale (« les enfants chantent » garde -ent), pas de h aspiré. */

const VOY = "aàâäeéèêëiîïoôöuùûüyÿœæ";
const voy = (c) => !!c && VOY.includes(c);
const MONO_E = new Set(["le", "je", "de", "ce", "me", "te", "se", "ne", "que"]);
const ER_PRONONCE = new Set(["mer", "fer", "hier", "cher", "fier", "hiver", "amer", "enfer", "ver", "super", "laser",
  "cancer", "éther", "revolver", "hamster", "cuiller", "tiers"]);
const FINALE_PRONONCEE = new Set(["os", "bus", "fils", "sens", "ours", "hélas", "as", "atlas", "maïs", "lys", "tennis",
  "jadis", "vis", "mars", "sud", "sept", "huit", "net", "but", "chut", "ouest", "zut", "stop", "top", "cap", "gaz",
  "index", "silex", "lynx", "sphinx", "six", "dix", "cassis", "oasis", "iris", "virus", "cactus", "bonus", "campus",
  "août", "dot", "brut"]);
const LIAISON = new Set(["les", "des", "ces", "mes", "tes", "ses", "nos", "vos", "leurs", "aux", "nous", "vous", "ils",
  "elles", "eux", "très", "plus", "moins", "tout", "quand", "dans", "chez", "sans", "sous", "deux", "trois", "est",
  "sont", "ont", "fait", "petit", "petits", "petites", "grand", "grands", "grandes", "mauvais", "quels", "quelles",
  "dont", "trop", "pas", "bons", "beaux", "vieux", "gros", "premiers", "dernier", "dernières", "cent", "vingt"]);
const PRONOMS_PLURIELS = new Set(["ils", "elles"]);
const CLITIQUES = new Set(["ne", "n", "se", "s", "le", "la", "les", "l", "lui", "leur", "y", "en", "me", "m", "te",
  "t", "nous", "vous", "qu", "qui"]);

function verbePluriel(prec) {
  for (let k = prec.length - 1; k >= Math.max(0, prec.length - 4); k--) {
    if (PRONOMS_PLURIELS.has(prec[k])) return true;
    if (!CLITIQUES.has(prec[k])) return false;
  }
  return false;
}

/* Lettres finales muettes du mot w (indices dans w), avant toute liaison. */
function finalesMuettes(w, prec) {
  const L = w.length, m = new Set();
  if (L < 2 || FINALE_PRONONCEE.has(w)) return m;
  let fin = L;                                            // fin de la partie encore prononçable
  if (w.endsWith("ent") && L > 3 && !voy(w[L - 4]) && verbePluriel(prec)) {
    m.add(L - 1); m.add(L - 2); m.add(L - 3); return m;   // « ils parlent »
  }
  if (w === "est") { m.add(1); m.add(2); return m; }                                       // verbe être
  if (w.endsWith("es") && L > 3) { m.add(L - 1); m.add(L - 2); return m; }                 // « portes », « aimées »
  if (w.endsWith("e") && !MONO_E.has(w) && L > 2) { m.add(L - 1); return m; }                // « porte », « vie »
  if (w.endsWith("er") && L > 2 && !ER_PRONONCE.has(w)) { m.add(L - 1); return m; }           // « chanter »
  // consonnes finales muettes : s/x/z de pluriel, puis d p t x z, puis p ou g devant elles (temps, doigt, vingt)
  if ("sxz".includes(w[fin - 1])) { m.add(fin - 1); fin--; }
  let dentale = false;
  if (fin > 1 && "dptxz".includes(w[fin - 1])) { m.add(fin - 1); fin--; dentale = true; }
  if (dentale && fin > 1 && "pg".includes(w[fin - 1])) { m.add(fin - 1); fin--; }
  if (fin > 1 && (w[fin - 1] === "c" || w[fin - 1] === "g") && w[fin - 2] === "n") m.add(fin - 1);   // blanc, long
  return m;
}

const nasale = (w, k) => !voy(w[k]) && w[k] !== "n" && w[k] !== "m";   // k : lettre qui suit le digramme

/* Segments d'un mot : [{k, n, v}] ; v === null : muet. */
function analyserMot(w, muettes) {
  const out = [];
  let k = 0;
  const pousse = (n, v) => { out.push({ k, n, v }); k += n; };
  while (k < w.length) {
    const s = w.slice(k), c = w[k], suiv = w[k + 1];
    if (muettes.has(k) || c === "h") { pousse(1, null); continue; }
    if (s.startsWith("eau")) { pousse(3, "o"); continue; }
    if (/^(ain|aim|ein|eim)/.test(s) && nasale(w, k + 3)) { pousse(3, "in"); continue; }
    if (s.startsWith("oin") && nasale(w, k + 3)) { pousse(1, "ou"); pousse(2, "in"); continue; }
    if (s.startsWith("ien") && nasale(w, k + 3)) { pousse(1, "i"); pousse(2, "in"); continue; }      // bien, viendrai
    if (/^(ou|où|oû)/.test(s)) { pousse(2, "ou"); continue; }
    if (/^(oi|oî|oy)/.test(s)) { pousse(1, "ou"); pousse(1, "a"); continue; }
    if (s.startsWith("œu")) { pousse(2, "eu"); continue; }
    if (/^(au|eu)/.test(s)) { pousse(2, s.startsWith("au") ? "o" : "eu"); continue; }
    if (/^(ai|aî|ei)/.test(s)) { pousse(2, "e"); continue; }
    if (/^(an|am|en|em)/.test(s) && nasale(w, k + 2)) { pousse(2, "an"); continue; }
    if (/^(on|om)/.test(s) && nasale(w, k + 2)) { pousse(2, "on"); continue; }
    if (/^(in|im|yn|ym|un|um)/.test(s) && nasale(w, k + 2)) { pousse(2, "in"); continue; }
    if (s.startsWith("ch")) { pousse(2, "ch"); continue; }
    if (s.startsWith("ph")) { pousse(2, "fv"); continue; }
    if (s.startsWith("gn")) { pousse(2, "dent"); continue; }
    if (s.startsWith("qu") || (s.startsWith("gu") && "eéèêiîy".includes(w[k + 2] || "x"))) {
      pousse(1, "k"); pousse(1, null); continue;                     // u muet
    }
    if ("aàâä".includes(c)) { pousse(1, "a"); continue; }
    if ("éèêë".includes(c)) { pousse(1, "e"); continue; }
    if (c === "e") {
      // e fermé ou ouvert devant consonne finale muette ou deux consonnes (« les », « chanter », « merci »),
      // sinon e caduc (/ə/, arrondi léger) : « le », « petit »
      const ferme = !MONO_E.has(w) && (muettes.has(k + 1)
        || (!!suiv && !voy(suiv) && (k + 2 === w.length || (!!w[k + 2] && !voy(w[k + 2])))));
      pousse(1, ferme ? "e" : "eu"); continue;
    }
    if ("iîïyÿ".includes(c)) { pousse(1, "i"); continue; }
    if ("oôö".includes(c)) { pousse(1, "o"); continue; }
    if ("uùûü".includes(c)) { pousse(1, "u"); continue; }
    if (c === "œ") { pousse(1, "eu"); continue; }
    if ("pbm".includes(c)) { pousse(1, "pbm"); continue; }
    if ("fvw".includes(c)) { pousse(1, "fv"); continue; }
    if (c === "j") { pousse(1, "ch"); continue; }
    if (c === "g") { pousse(1, "eiy".includes(suiv || "x") ? "ch" : "k"); continue; }
    if (c === "c") { pousse(1, "eéèêiîy".includes(suiv || "x") ? "dent" : "k"); continue; }
    if ("çsztdnlx".includes(c)) { pousse(1, "dent"); continue; }
    if (c === "r") { pousse(1, "r"); continue; }
    if ("kq".includes(c)) { pousse(1, "k"); continue; }
    pousse(1, "repos");
  }
  return out;
}

const RE_MOT = /[a-zàâäéèêëîïôöùûüÿœæç]+/g;

/* Segments de visèmes pour tout un texte (mêmes conventions que l'ancienne fonction visemes de parole.js). */
export function phonetiser(texte) {
  const t = String(texte || "").toLowerCase();
  const mots = [...t.matchAll(RE_MOT)].map((m) => ({ i: m.index, w: m[0] }));
  const parMot = new Map();
  const prec = [];
  mots.forEach((m, j) => {
    const muettes = finalesMuettes(m.w, prec);
    const suivant = mots[j + 1];
    const contigu = suivant && /^[\s'’-]*$/.test(t.slice(m.i + m.w.length, suivant.i));   // « est-il »
    if (contigu && LIAISON.has(m.w) && /^[aàâäeéèêëiîïoôöuùûüyh]/.test(suivant.w)) {
      const der = m.w.length - 1;
      if (muettes.has(der) && "sxztd".includes(m.w[der])) muettes.delete(der);   // les‿amis, petit‿ami
    }
    parMot.set(m.i, analyserMot(m.w, muettes));
    prec.push(m.w);
  });
  const out = [];
  let i = 0, dernier = "repos";
  while (i < t.length) {
    const segs = parMot.get(i);
    if (segs) {
      for (const s of segs) {
        if (s.v === null) out.push({ i: i + s.k, n: s.n, v: dernier, muet: true });
        else { out.push({ i: i + s.k, n: s.n, v: s.v }); dernier = s.v; }
      }
      i += segs.reduce((a, s) => a + s.n, 0);
      continue;
    }
    const c = t[i];
    out.push({ i, n: 1, v: /[,.;:!?]/.test(c) ? "pause" : "repos" });
    dernier = "repos";
    i++;
  }
  return out;
}
