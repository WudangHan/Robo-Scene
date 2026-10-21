/* Robo-Scène — interprète de directives en français pour le robot virtuel.
   Module pur (aucun accès au DOM ni à three.js) : il transforme une consigne écrite ou dictée
   en une liste d'actions typées, conformes à schema.json. Il fonctionne hors ligne ; ce qu'il
   ne comprend pas est renvoyé dans « ignores » pour que l'interface puisse, si l'utilisateur
   l'a permis, solliciter l'interprète du pont (Claude), dont la proposition est revalidée.

   Conventions scéniques : « gauche » et « droite » désignent les côtés du personnage
   (comme pour un acteur) ; « ma gauche » désigne la gauche de la personne qui le regarde ;
   « cour » et « jardin » suivent l'usage du théâtre français (vu de la salle, jardin à gauche,
   cour à droite ; pour l'acteur face au public, cour est donc à sa gauche). */

const NOMBRES = [
  ["cent quatre-vingts", 180], ["cent quatre vingts", 180], ["quatre-vingt-dix", 90], ["quatre vingt dix", 90],
  ["quatre-vingts", 80], ["soixante-dix", 70], ["soixante", 60], ["cinquante", 50], ["quarante-cinq", 45],
  ["quarante", 40], ["trente", 30], ["vingt", 20], ["quinze", 15], ["douze", 12], ["dix", 10], ["neuf", 9],
  ["huit", 8], ["sept", 7], ["six", 6], ["cinq", 5], ["quatre", 4], ["trois", 3], ["deux", 2], ["cent", 100],
];

export function normaliser(s) {
  return String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[’`]/g, "'").replace(/œ/g, "oe").replace(/\s+/g, " ").trim();
}
function chiffres(c) {
  let r = " " + c + " ";
  for (const [mot, n] of NOMBRES) r = r.replace(new RegExp(`([\\s'-])${mot}(?=[\\s.,;!?])`, "g"), `$1${n}`);
  r = r.replace(/\b(un|une) (pas|metre|degre|demi)/g, "1 $2").replace(/\bdemi[- ]tour\b/g, "demitour");
  return r.trim();
}

const EMO = [
  ["colère", /\b(colere|fache|furieu|enrag|irrite|en rogne|rage)/],
  ["tristesse", /\b(triste|tristesse|chagrin|melancol|abattu|malheureu|desespere)/],
  ["joie", /\b(joie|joyeu|content|heureu|ravi|gai\b|gaie|enjoue|rejoui)/],
  ["peur", /\b(peur|effraye|apeure|terrifie|terreur|angoiss|craintif|inquiet|panique)/],
  ["tendresse", /\b(tendre|tendresse|doux\b|douce\b|douceur|affectueu|bienveillan)/],
  ["mépris", /\b(mepris|dedaign|hautain|arrogan)/],
  ["surprise", /\b(surpris|surprise|etonne|stupefai|ebahi|sidere)/],
  ["ironie", /\b(ironi|sarcasti|moqueu|narquois|goguenard)/],
  ["lassitude", /\b(las\b|lasse\b|lassitude|fatigue|epuise|ennuye|blase|ennui)/],
  ["assurance", /\b(assure|assurance|confian|fier\b|fiere|fierte|sur de (toi|lui|soi)|determine|autoritaire|triomphan)/],
  ["dégoût", /\b(degout|ecoeur|repugn|beurk)/],
  ["neutre", /\b(neutre|impassible|sans emotion|inexpressif|calme|serein|apaise)/],
];

const GESTES = [
  ["hausser_epaules", /\b(hausse|haussement)s? (les |des |d'|de l')?epaule/],
  ["reverence", /\b(reverence|courbette|incline[- ]toi|salue (le |la |les )?(public|salle|spectateurs)|saluer le public)/],
  ["saluer", /\b(salue|saluer|salut\b|fais (un )?coucou|coucou|signe de (la )?main|agite la main|dis au revoir de la main)/],
  ["hocher", /\b(hoche|acquiesce|fais oui|dis oui de la tete|signe de tete)/],
  ["non", /\b(secoue la tete|fais non|dis non de la tete|refuse de la tete|non de la tete)/],
  ["croiser_bras", /\bcroise(r|s|z)? (les |tes )?bras/],
  ["mains_hanches", /\b(mains?|poings?) sur (les |tes )?hanches/],
  ["reflechir", /\b(reflechi|pense\b|penses|medite|songeur|main (au|sous le) menton)/],
  ["applaudir", /\b(applaudi|applaudissement|bravo|tape des mains)/],
  ["bras_ouverts", /\b(ouvre (grand )?(les |tes )?bras|bras ouverts|accueill)/],
  ["pointer", /\b(pointe\b(?! (le |les |des |du |ton |tes |sur )?(pied|pieds|orteils?|pointes))|pointe du doigt|montre du doigt|designe|indique)/],
  ["poing_leve", /\b(leve (le |ton )?poing|poing leve|brandi)/],
  ["main_coeur", /\bmains? sur (le |ton )?coeur/],
  ["gratter_tete", /\b(gratte[- ]toi la tete|gratte la tete|se gratter)/],
  ["rire", /\b(ris\b|rire|rigole|eclate de rire|esclaffe)/],
  ["pleurer", /\b(pleure|pleurer|sanglot)/],
  ["soupirer", /\b(soupir)/],
  ["clin_oeil", /\b(clin d'oeil|cligne de l'oeil|fais un clin)/],
  ["danser", /\b(danse|balance[- ]toi|ondule|balance les hanches)/],
  ["taper_pied", /\btape du pied/],
  ["cacher_visage", /\bcache[- ]?(toi )?(le |ton |son )?visage/],
  ["etirer", /\b(etire[- ]toi|etirement|etire les bras)/],
  ["respirer", /\b(respire|inspire|expire)/],
  ["marcher_sur_place", /\bmarche(r)? sur place/],
];

const POSES = [
  ["assis", /\b(assieds?[- ]toi|assoi[s-]|assis\b|asseoir|prends? (un )?siege)/],
  ["accroupi", /\b(accroupi|accroupis|accroupir)/],
  ["a_genoux", /\b(a genoux|a genou\b|agenouille|genou a terre)/],
  ["garde_a_vous", /\b(garde[- ]a[- ]vous|tiens[- ]toi droit)/],
  ["recroqueville", /\b(recroqueville|replie[- ]toi|voute[- ]toi)/],
  ["debout", /\b(leve[- ]toi|releve[- ]toi|debout|redresse[- ]toi)\b/],
  ["repos", /\b(repos|position (neutre|initiale|de depart)|detends[- ]toi|relache[- ]toi|relache tout|decontracte)/],
];

const PARTIES = [
  ["sourcils", /\bsourcils?\b/], ["yeux", /\b(yeux|paupieres?|oeil)\b/], ["bouche", /\b(bouche|levres?)\b/],
  ["poignet", /\bpoignets?\b/], ["coude", /\b(coudes?|avant-bras)\b/], ["epaule", /\bepaules?\b/],
  ["main", /\b(mains?|poings?|doigts?)\b/], ["bras", /\bbras\b/],
  ["genou", /\bgenoux?\b/], ["pied", /\b(pieds?|chevilles?|orteils?|pointes? de pied)\b/], ["jambe", /\b(jambes?|cuisses?)\b/],
  ["tete", /\b(tete|visage|menton|nez|cou|nuque|front)\b/], ["tronc", /\b(tronc|buste|torse|dos|haut du corps|corps|poitrine)\b/],
  ["bassin", /\b(bassin|hanches?|fesses)\b/],
];

const V = {
  lever: /\b(leve|levez|lever|monte|montez|eleve|hisse|souleve|redresse|releve)\b/,
  baisser: /\b(baisse|baissez|baisser|descends|descend|abaisse|pose|laisse tomber|rabaisse)\b/,
  tourner: /\b(tourne|tournez|pivote|oriente)\b/,
  pencher: /\b(penche|penchez|incline|inclinez|bascule)\b/,
  plier: /\b(plie|pliez|flechis|replie|ramene)\b/,
  tendre: /\b(tends|tendez|etends|allonge|deplie|tend)\b/,
  ouvrir: /\b(ouvre|ouvrez|ecarte|ecartez|deploie)\b/,
  fermer: /\b(ferme|fermez|serre|serrez|rapproche|joins)\b/,
  froncer: /\b(fronce|froncez)\b/,
};

function intensiteDe(c, defaut = 7) {
  const n = c.match(/\b(\d{1,2})\s*(\/\s*10|sur 10)\b/) || c.match(/\bintensite (de )?(\d{1,2})\b/);
  if (n) return Math.max(0, Math.min(10, Number(n[2] && !n[2].startsWith("/") && !n[2].startsWith("sur") ? n[2] : n[1])));
  if (/\b(a peine|tres peu|imperceptible)/.test(c)) return 2;
  if (/\b(un peu|legerement|un brin|un soupcon|plutot)\b/.test(c)) return 4;
  if (/\b(tres|vraiment|extremement|terriblement|furieu|terrifie|desespere|eclate|completement|au maximum|intensement)\b/.test(c)) return 9.5;
  return defaut;
}
function facteur(c) {
  if (/\b(a peine|tres peu|imperceptible)/.test(c)) return 0.25;
  if (/\b(un peu|legerement|un brin|doucement un peu)\b/.test(c)) return 0.45;
  if (/\b(a moitie|a mi-hauteur|mi-chemin)\b/.test(c)) return 0.55;
  if (/\b(completement|au maximum|tout en haut|tout en bas|beaucoup|bien haut|tres haut|tres bas|a fond)\b/.test(c)) return 1.25;
  return 1;
}
function vitesseDe(c) {
  if (/\b(tres lentement|au ralenti|tres doucement)\b/.test(c)) return 0.35;
  if (/\b(lentement|doucement|calmement|progressivement|tranquillement)\b/.test(c)) return 0.6;
  if (/\b(brusquement|soudain|d'un coup|sec\b|tres vite|vivement)\b/.test(c)) return 2.2;
  if (/\b(vite|rapidement|prestement)\b/.test(c)) return 1.6;
  return null;
}
function degres(c) {
  const m = c.match(/(-?\d+(?:[.,]\d+)?)\s*(?:°|degres?\b|deg\b)/);
  return m ? Number(m[1].replace(",", ".")) : null;
}
function cotes(c) {
  if (/\b(les (deux|2)|(deux|2) (bras|mains|jambes|pieds|epaules|coudes|genoux|poignets))\b/.test(c)) return ["g", "d"];
  if (/\b(les|tes|des|ses) (bras|mains|jambes|genoux|pieds|epaules|coudes|poignets|poings|chevilles)\b/.test(c)) return ["g", "d"];
  if (/\bgauche\b/.test(c)) return ["g"];
  if (/\bdroite?\b/.test(c)) return ["d"];
  return ["d"];
}
/* +1 = vers la gauche du personnage ; -1 = vers sa droite ; 0 = non précisé */
function sens(c) {
  if (/\b(ma|mon) gauche\b/.test(c)) return -1;
  if (/\b(ma|mon) droite\b/.test(c)) return 1;
  if (/\bcour\b/.test(c)) return 1;
  if (/\bjardin\b/.test(c)) return -1;
  if (/\bgauche\b/.test(c)) return 1;
  if (/\bdroite?\b/.test(c)) return -1;
  return 0;
}
const art = (dof, valeur, extra = {}) => ({ type: "articulation", dof, valeur, ...extra });

/* ── Apparence ─────────────────────────────────────────── */
function couleurDans(c, schema) {
  const noms = Object.keys(schema.apparence.couleurs).sort((a, b) => b.length - a.length);
  for (const n of noms) if (new RegExp(`\\b${normaliser(n)}s?\\b`).test(c)) return n;
  const hex = c.match(/#[0-9a-f]{6}\b/);
  return hex ? hex[0] : null;
}
/* Habillages (21 oct. 2026) : mots qui désignent chacun des habillages de schema.json, après un verbe d'habillage. */
const MOTS_HABILLAGE = {
  repetition: /\b(tenue de repetition|repetition|tenue neutre|tenue de travail)\b/, soiree: /\b(habit de soiree|habit|smoking|frac|queue-de-pie|tenue de soiree)\b/,
  pierrot: /\bpierrot\b/, monarque: /\b(monarque|roi|reine|souverain|souveraine)\b/, clown: /\bclown\b/,
  automate: /\b(automate|robot de metal|homme de fer|metallique)\b/, magicien: /\b(magicien|magicienne|illusionniste)\b/,
  professeur: /\b(professeur|professeure|prof)\b/, artiste: /\b(artiste|peintre)\b/, ouvrier: /\b(ouvrier|ouvriere|travailleur)\b/,
  voyageur: /\b(voyageur|voyageuse|aventurier|aventuriere)\b/, danseur: /\b(danseur|danseuse)\b/,
  robe_soiree: /\brobe de soiree\b/, tunique: /\b(tunique|antique|toge)\b/, sport: /\b(survetement|sport|sportif|sportive|jogging)\b/,
};
const VERBE_HABILLAGE = /\b(habille-toi|habille toi|habilles?|habillez|habillage|tenue|costume|deguise-toi|deguise|deguisement|change de tenue|mets ton|mets ta|en tenue)\b/;
export function habillageDans(c, schema) {
  const H = schema.apparence.habillages || {};
  if (!VERBE_HABILLAGE.test(c)) return null;
  for (const [id, re] of Object.entries(MOTS_HABILLAGE)) if (H[id] && re.test(c)) return id;
  for (const id of Object.keys(H)) if (new RegExp(`\\b${normaliser(H[id].libelle)}\\b`).test(c)) return id;
  return null;
}
const RETRAIT = /\b(sans|enleve|enlever|retire|retirer|ote|oter|plus de|supprime|quitte)\b/;

function apparence(c, schema) {
  const out = [];
  const A = (cle, valeur, relatif = false) => out.push({ type: "apparence", cle, valeur, ...(relatif ? { relatif: true } : {}) });
  const hab = habillageDans(c, schema);
  if (hab) { A("habillage", hab); return out; }
  // chapeaux, ornements du cou, cape, jupe ou robe, gants, matière
  const chap = c.match(/\b(chapeau melon|melon|haut-de-forme|haut de forme|beret|casquette|couronne|calot|chapeau)\b/);
  if (chap) {
    if (RETRAIT.test(c)) A("chapeau", "aucun");
    else {
      A("chapeau", { "chapeau melon": "melon", melon: "melon", "haut-de-forme": "haut-de-forme", "haut de forme": "haut-de-forme", beret: "béret",
        casquette: "casquette", couronne: "couronne", calot: "calot", chapeau: "melon" }[chap[1]]);
      const col = couleurDans(c.slice(chap.index), schema);
      if (col) A("couleur_chapeau", col);
    }
  }
  const cou = c.match(/\b(noeud papillon|papillon|cravate|collerette|foulard|echarpe)\b/);
  if (cou) {
    if (RETRAIT.test(c)) A("cou", "aucun");
    else {
      A("cou", { "noeud papillon": "nœud papillon", papillon: "nœud papillon", cravate: "cravate", collerette: "collerette", foulard: "foulard", echarpe: "foulard" }[cou[1]]);
      const col = couleurDans(c.slice(cou.index), schema);
      if (col) A("accessoire", col);
    }
  }
  const cape = c.match(/\b(cape|manteau de scene)\b/);
  if (cape) {
    if (RETRAIT.test(c)) A("cape", "aucune");
    else {
      A("cape", /\bcourte\b/.test(c) ? "courte" : "longue");
      const col = couleurDans(c.slice(cape.index), schema);
      if (col && !cou) A("accessoire", col);
    }
  }
  const jupe = c.match(/\b(jupe|robe|kilt)\b/);
  if (jupe) {
    if (RETRAIT.test(c)) A("jupe", "aucune");
    else {
      A("jupe", /\bcourte\b/.test(c) || jupe[1] === "kilt" ? "courte" : /\blongue\b/.test(c) || jupe[1] === "robe" ? "longue" : "courte");
      const col = couleurDans(c.slice(jupe.index), schema);
      if (col) A("bas", col);
    }
  }
  if (/\bgants?\b/.test(c)) {
    A("gants", !RETRAIT.test(c));
    const col = !RETRAIT.test(c) && couleurDans(c.slice(c.search(/\bgants?\b/)), schema);
    if (col && !cou && !cape) A("accessoire", col);
  }
  const mat = c.match(/\b(?:en|de) (satin|cuir|metal|tissu|soie|velours)\b|\b(metallique|satine|satinee)\b/);
  if (mat) A("matiere", { satin: "satin", soie: "satin", velours: "satin", satine: "satin", satinee: "satin", cuir: "cuir", metal: "métal", metallique: "métal", tissu: "tissu" }[mat[1] || mat[2]]);
  const t = c.match(/\b(?:mesure|taille( de)?|fais) (\d)[ m,.]?(\d{2})\b/) || c.match(/\b(\d{3}) ?cm\b/);
  if (t) A("taille", t[3] ? Number(t[2]) * 100 + Number(t[3]) : Number(t[1]));
  else if (/\b(plus grand|grandis|agrandis)/.test(c)) A("taille", 8, true);
  else if (/\b(plus petit|rapetisse|moins grand)/.test(c)) A("taille", -8, true);
  if (/\b(plus )?(costaud|muscle|baraque|large d'epaules|athletique|carre)\b/.test(c)) A("carrure", 0.1, true);
  if (/\b(plus )?(mince|maigre|svelte|frele|elance)\b/.test(c)) { A("carrure", -0.08, true); A("corpulence", -0.15, true); }
  if (/\b(gros|corpulent|bedaine|ventru|enrobe|du ventre|embonpoint)\b/.test(c)) A("corpulence", 0.2, true);
  const age = c.match(/\b(\d{2}) ans\b/);
  if (age) A("age", Number(age[1]));
  else if (/\b(vieilli|plus vieux|plus age|vieux\b|ag[ee] )/.test(c)) A("age", 15, true);
  else if (/\b(rajeuni|plus jeune|jeune\b)/.test(c)) A("age", -15, true);
  if (/\bcheveux|coiffure|crane|chauve|rase[- ]?toi la tete|tondu/.test(c)) {
    if (/\bchauve\b/.test(c)) A("cheveux", "chauve");
    else if (/\b(rases?|tondus?|crane rase|boule a zero)\b/.test(c)) A("cheveux", "rasé");
    else if (/\b(mi-longs?|longs?|mi longs?)\b/.test(c)) A("cheveux", "mi-long");
    else if (/\bcourts?\b/.test(c)) A("cheveux", "court");
    const col = couleurDans(c, schema);
    if (col) A("couleur_cheveux", col);
  }
  if (/\bbarbe\b/.test(c)) {
    if (/\b(sans|enleve|retire|rase|plus de|supprime)\b/.test(c)) A("barbe", "aucune");
    else if (/\b(pleine|longue|fournie|epaisse|grande)\b/.test(c)) A("barbe", "pleine");
    else A("barbe", "courte");
  } else if (/\brase[- ]toi\b/.test(c)) { A("barbe", "aucune"); A("moustache", false); }
  if (/\bmoustache\b/.test(c)) A("moustache", !/\b(sans|enleve|retire|rase|plus de|supprime)\b/.test(c));
  const vet = [["haut", /\b(chemise|haut|t-shirt|tee-shirt|tshirt|chandail|veste|pull|gilet|tunique|costume|polo)\b/],
               ["bas", /\b(pantalon|jean|jeans|culotte|bas)\b/], ["chaussures", /\b(chaussures?|souliers?|bottes?|bottines?)\b/]];
  for (const [cle, re] of vet) {
    const m = (cle === "haut" ? c.replace(/haut[- ]de[- ]forme/g, "chapeau-forme") : c).match(re);
    if (m) {
      const suite = c.slice(m.index);
      const col = couleurDans(suite, schema) || couleurDans(c, schema);
      if (col) A(cle, col);
    }
  }
  if (/\bmanches? courtes?\b/.test(c)) A("manches", "courtes");
  else if (/\bmanches? longues?\b/.test(c)) A("manches", "longues");
  const p = c.match(/\bpeau (tres claire|claire|mate|olive|brune|foncee|noire|sombre)\b/);
  if (p) A("peau", { "tres claire": "très claire", claire: "claire", mate: "mate", olive: "olive", brune: "brune", foncee: "foncée", noire: "foncée", sombre: "foncée" }[p[1]]);
  const y = c.match(/\byeux (bleus|verts|bruns|marron|noirs|gris|noisette)\b/);
  if (y) A("yeux", { bleus: "bleu", verts: "vert", bruns: "brun", marron: "brun", noirs: "noir", gris: "gris", noisette: "noisette" }[y[1]]);
  return out;
}

/* ── Visage (unités d'action FACS, 0 à 1) ──────────────── */
function visage(c, f) {
  if (/\b(souris|sourire|souriant|fais un sourire)\b/.test(c)) return { type: "visage", nom: "sourire", au: { au6: 0.5 * f, au12: 0.8 * f }, tenir: true };
  if (/\bfronce/.test(c)) return { type: "visage", nom: "froncement", au: { au4: 0.9 * f }, tenir: true };
  if (/\bsourcils?\b/.test(c) && V.lever.test(c)) return { type: "visage", nom: "sourcils levés", au: { au1: 0.9 * f, au2: 0.9 * f }, tenir: true };
  if (/\bsourcils?\b/.test(c) && V.baisser.test(c)) return { type: "visage", nom: "sourcils baissés", au: { au4: 0.8 * f }, tenir: true };
  if (/\b(yeux|paupieres)\b/.test(c) && V.fermer.test(c)) return { type: "visage", nom: "yeux fermés", au: { au43: 1 }, tenir: true };
  if (/\b(yeux|paupieres)\b/.test(c) && (V.ouvrir.test(c) || /\bgrand(s)? ouverts?\b/.test(c))) return { type: "visage", nom: "yeux ouverts", au: { au43: 0, au5: /\bgrand/.test(c) ? 0.8 : 0 }, tenir: true };
  if (/\bplisse les yeux\b/.test(c)) return { type: "visage", nom: "yeux plissés", au: { au7: 0.9 * f }, tenir: true };
  if (/\b(bouche|levres)\b/.test(c) && V.ouvrir.test(c)) return { type: "visage", nom: "bouche ouverte", au: { au25: 1, au26: 0.8 * f }, tenir: true };
  if (/\b(bouche|levres)\b/.test(c) && (V.fermer.test(c) || /\bpince/.test(c))) return { type: "visage", nom: "lèvres pincées", au: { au23: 0.6, au24: 0.7 * f, au26: 0 }, tenir: true };
  if (/\b(moue|boude|bouder)\b/.test(c)) return { type: "visage", nom: "moue", au: { au15: 0.6 * f, au17: 0.7 * f, au18: 0.3 }, tenir: true };
  if (/\bgrimace\b/.test(c)) return { type: "visage", nom: "grimace", au: { au4: 0.6, au7: 0.6, au9: 0.6 * f, au20: 0.7 * f }, tenir: true };
  if (/\b(visage neutre|efface l'expression|detends le visage)\b/.test(c)) return { type: "visage", nom: "neutre", au: {}, tenir: false };
  return null;
}

/* ── Articulations nommées ─────────────────────────────── */
function articulations(c, partie, f) {
  const out = [];
  const d = degres(c);
  const S = cotes(c);
  const dir = sens(c);
  const relatif = /\b(encore|davantage|plus haut|plus bas|un peu plus|plus loin)\b/.test(c);
  const moins = /\bmoins\b/.test(c);
  const R = (dof, v, opts = {}) => out.push(art(dof, v, opts));
  const lever = V.lever.test(c) || /\b(en haut|vers le haut|au ciel)\b/.test(c);
  const baisser = V.baisser.test(c) || /\b(en bas|vers le bas|le long du corps)\b/.test(c);
  switch (partie) {
    case "tete": {
      if (V.tourner.test(c) || (dir && !V.pencher.test(c))) R("tete.rotation", (d ?? 55 * f) * (dir || 1));
      else if (V.pencher.test(c) && dir) R("tete.inclinaison", (d ?? 25 * f) * dir);
      else if (V.pencher.test(c) && /\barriere\b/.test(c)) R("tete.flexion", -(d ?? 30 * f));
      else if (lever && !/\b(redresse|droite)\b/.test(c)) R("tete.flexion", relatif ? -15 : -(d ?? 28 * f), relatif ? { relatif: true } : {});
      else if (baisser || (V.pencher.test(c) && /\b(avant|devant)\b/.test(c)) || V.pencher.test(c)) R("tete.flexion", relatif ? 15 : (d ?? 32 * f), relatif ? { relatif: true } : {});
      else if (/\b(redresse|droite|centre|droit devant)\b/.test(c)) { R("tete.flexion", 0); R("tete.rotation", 0); R("tete.inclinaison", 0); }
      break;
    }
    case "tronc": {
      if (V.tourner.test(c) && dir) R("tronc.rotation", (d ?? 35 * f) * dir);
      else if (V.pencher.test(c) && dir) R("tronc.inclinaison", (d ?? 22 * f) * dir);
      else if ((V.pencher.test(c) || baisser) && /\barriere\b/.test(c)) R("tronc.flexion", -(d ?? 18 * f));
      else if (V.pencher.test(c) || baisser || /\b(avant|courbe)\b/.test(c)) R("tronc.flexion", d ?? 40 * f);
      else if (lever || /\b(redresse|droit)\b/.test(c)) { R("tronc.flexion", 0); R("tronc.inclinaison", 0); R("tronc.rotation", 0); }
      break;
    }
    case "bras": {
      for (const s of S) {
        const cote = /\b(cote|sur le cote|lateral|horizontale sur le cote|en croix|ecarte)\b/.test(c) || V.ouvrir.test(c);
        if (/\b(derriere|en arriere|dans le dos)\b/.test(c)) { R(`epaule_${s}.flexion`, -(d ?? 40)); R(`epaule_${s}.abduction`, 0); R(`coude_${s}.flexion`, 10); }
        else if (V.plier.test(c)) R(`coude_${s}.flexion`, d ?? 100 * f);
        else if (V.tendre.test(c) && !cote) { R(`epaule_${s}.flexion`, d ?? 90); R(`epaule_${s}.abduction`, 0); R(`coude_${s}.flexion`, 0); }
        else if (lever && cote) { R(`epaule_${s}.abduction`, relatif ? 20 : (d ?? 90 * f), relatif ? { relatif: true } : {}); R(`epaule_${s}.flexion`, 0); R(`coude_${s}.flexion`, 5); }
        else if (lever) {
          const v = d ?? (/\bhorizontal/.test(c) ? 90 : 160 * f);
          R(`epaule_${s}.flexion`, relatif ? (moins ? -20 : 20) : v, relatif ? { relatif: true } : {}); R(`coude_${s}.flexion`, 8);
          if (!relatif) R(`epaule_${s}.abduction`, 8);
        } else if (cote) { R(`epaule_${s}.abduction`, d ?? 90 * f); R(`epaule_${s}.flexion`, 0); }
        else if (baisser) { R(`epaule_${s}.flexion`, 0); R(`epaule_${s}.abduction`, 0); R(`coude_${s}.flexion`, 5); }
        else if (V.tourner.test(c)) R(`epaule_${s}.rotation`, (d ?? 45) * (/\b(exterieur|dehors)\b/.test(c) ? -1 : 1));
      }
      break;
    }
    case "epaule": {
      for (const s of S) {
        if (lever) R(`epaule_${s}.haussement`, d ?? 20 * f);
        else if (baisser) R(`epaule_${s}.haussement`, 0);
        else if (/\b(rentre|ferme)\b/.test(c)) { R(`epaule_${s}.haussement`, 12); R(`epaule_${s}.rotation`, 20); }
        else if (V.ouvrir.test(c)) R(`epaule_${s}.rotation`, -20);
      }
      break;
    }
    case "coude": {
      for (const s of S) {
        if (V.tendre.test(c)) R(`coude_${s}.flexion`, 0);
        else R(`coude_${s}.flexion`, d ?? (V.plier.test(c) || lever ? 110 * f : 60));
      }
      break;
    }
    case "poignet": {
      for (const s of S) R(`poignet_${s}.flexion`, d ?? (baisser || V.plier.test(c) ? 50 * f : (lever ? -45 * f : 0)));
      break;
    }
    case "main": {
      for (const s of S) {
        if (/\bpoings?\b/.test(c) && !lever || V.fermer.test(c)) R(`main_${s}.fermeture`, 100);
        else if (V.ouvrir.test(c) || /\bdoigts? (ecartes?|tendus?)\b/.test(c)) R(`main_${s}.fermeture`, 0);
        else if (lever) { R(`epaule_${s}.flexion`, d ?? 170 * f); R(`epaule_${s}.abduction`, 12); R(`coude_${s}.flexion`, 15); R(`main_${s}.fermeture`, 10); }
        else if (baisser) { R(`epaule_${s}.flexion`, 0); R(`epaule_${s}.abduction`, 0); R(`coude_${s}.flexion`, 5); }
        else if (V.tendre.test(c)) { R(`epaule_${s}.flexion`, 80); R(`coude_${s}.flexion`, 10); R(`main_${s}.fermeture`, 0); R(`poignet_${s}.flexion`, -20); }
      }
      break;
    }
    case "jambe": {
      const s = S.length === 2 ? "d" : S[0];
      if (/\b(ecarte|sur le cote)\b/.test(c)) for (const x of S) R(`hanche_${x}.abduction`, d ?? 30 * f);
      else if (/\b(rapproche|serre|joins)\b/.test(c)) for (const x of S) R(`hanche_${x}.abduction`, 0);
      else if (V.plier.test(c)) { R(`hanche_${s}.flexion`, 45 * f); R(`genou_${s}.flexion`, d ?? 90 * f); }
      else if (V.tendre.test(c)) { R(`hanche_${s}.flexion`, d ?? 45 * f); R(`genou_${s}.flexion`, 0); R(`cheville_${s}.flexion`, 20); }
      else if (/\b(arriere|derriere)\b/.test(c)) { R(`hanche_${s}.flexion`, -(d ?? 25)); R(`genou_${s}.flexion`, 30); }
      else if (lever) { R(`hanche_${s}.flexion`, d ?? 75 * f); R(`genou_${s}.flexion`, 70 * f); }
      else if (baisser) { R(`hanche_${s}.flexion`, 0); R(`genou_${s}.flexion`, 0); R(`hanche_${s}.abduction`, 0); R(`cheville_${s}.flexion`, 0); }
      break;
    }
    case "genou": {
      if (S.length === 2 && (V.plier.test(c) || baisser)) {
        const k = f;
        out.push(art("bassin.abaissement", 14 * k)); for (const s of S) { R(`hanche_${s}.flexion`, 35 * k); R(`genou_${s}.flexion`, d ?? 65 * k); R(`cheville_${s}.flexion`, -20 * k); }
        R("tronc.flexion", 12 * k);
      } else {
        const s = S[0];
        if (V.tendre.test(c)) R(`genou_${s}.flexion`, 0);
        else { R(`hanche_${s}.flexion`, lever ? 85 * f : 30); R(`genou_${s}.flexion`, d ?? (lever ? 80 : 60) * f); }
      }
      break;
    }
    case "pied": {
      const s = S.length === 2 ? "d" : S[0];
      if (/\borteils?\b/.test(c) && lever) R(`cheville_${s}.flexion`, -25);
      else if (/\bpointe\b/.test(c) || V.tendre.test(c)) R(`cheville_${s}.flexion`, d ?? 35);
      else if (lever) { R(`hanche_${s}.flexion`, 30 * f); R(`genou_${s}.flexion`, 65 * f); }
      else if (baisser) { R(`hanche_${s}.flexion`, 0); R(`genou_${s}.flexion`, 0); R(`cheville_${s}.flexion`, 0); }
      break;
    }
    case "bassin": {
      if (baisser) R("bassin.abaissement", d ?? 18 * f);
      else if (lever) R("bassin.abaissement", 0);
      else if (V.tourner.test(c) && dir) R("tronc.rotation", -25 * dir);
      break;
    }
    default: break;
  }
  return out;
}

/* ── Déplacements et orientation ───────────────────────── */
function deplacement(c, schema) {
  const dist = c.match(/(\d+(?:[.,]\d+)?)\s*(pas|metres?|m\b|cm|centimetres?)/);
  let metres = null;
  if (dist) { const n = Number(dist[1].replace(",", ".")); metres = Math.round((dist[2] === "pas" ? n * 0.6 : /^c/.test(dist[2]) ? n / 100 : n) * 100) / 100; }
  if (/\b(demitour|retourne[- ]toi|fais volte-face)\b/.test(c)) return { type: "orienter", angle: 180, relatif: true };
  if (/\b(de dos|tourne le dos)\b/.test(c)) return { type: "orienter", angle: 180 };
  if (/\b(de profil)\b/.test(c)) return { type: "orienter", angle: 90 * (sens(c) || 1) };
  if (/\b(trois[- ]quarts?)\b/.test(c)) return { type: "orienter", angle: 40 * (sens(c) || 1) };
  if (/\b(fais face|face au public|de face|regarde[- ]?(nous|le public) de face)\b/.test(c)) return { type: "orienter", angle: 0 };
  if (/\btourne[- ]toi\b|\bpivote\b|\btourne sur toi/.test(c)) {
    const d = degres(c);
    return { type: "orienter", angle: (d ?? 90) * (sens(c) || 1), relatif: true };
  }
  const lieu = c.match(/\b(va|vas|allez|marche|rends[- ]toi|deplace[- ]toi|cours|dirige[- ]toi|file|avance|recule)\b.*?\b(cote cour|cote jardin|cour|jardin|lointain|fond|avant[- ]scene|devant|au centre|centre|milieu)\b/);
  if (lieu) {
    const L = schema.lieux;
    let x = 0, z = 0;
    if (/\bcour\b/.test(c)) x = L.cour[0]; else if (/\bjardin\b/.test(c)) x = L.jardin[0];
    if (/\b(lointain|fond)\b/.test(c)) z = L.lointain[1]; else if (/\b(avant[- ]scene|devant)\b/.test(c)) z = L.avant_scene[1];
    return { type: "deplacer", x, z, course: /\bcours\b/.test(c) };
  }
  if (/\b(approche|viens (vers moi|ici|pres)|rapproche[- ]toi)\b/.test(c)) return { type: "deplacer", avant: metres ?? 0.8 };
  if (/\b(eloigne[- ]toi|va[- ]t'en|recule)\b/.test(c)) return { type: "deplacer", avant: -(metres ?? 0.6) };
  if (/\b(avance|marche|fais \d+(?:[.,]\d+)? pas|fais un pas|cours)\b/.test(c)) {
    const dir = sens(c);
    if (dir && /\b(vers|a|sur) (la |ta |ma |sa )?(gauche|droite)\b/.test(c)) return { type: "deplacer", lateral: (metres ?? 0.8) * dir };
    return { type: "deplacer", avant: metres ?? (/\bun pas\b/.test(c) ? 0.6 : 1.0), course: /\bcours\b/.test(c) };
  }
  return null;
}

function regard(c) {
  if (!/\b(regarde|fixe|observe|yeux vers|tourne les yeux|leve les yeux|baisse les yeux)\b/.test(c)) return null;
  if (/\b(moi|nous|le public|la salle|la camera|l'objectif|vers moi|dans les yeux)\b/.test(c)) return { type: "regard", cible: "public" };
  if (/\b(en haut|le ciel|au plafond|vers le haut|leve les yeux)\b/.test(c)) return { type: "regard", cible: "haut" };
  if (/\b(en bas|le sol|par terre|vers le bas|baisse les yeux|tes pieds)\b/.test(c)) return { type: "regard", cible: "bas" };
  if (/\b(au loin|l'horizon|dans le vide|au lointain)\b/.test(c)) return { type: "regard", cible: "loin" };
  const s = sens(c);
  if (s > 0) return { type: "regard", cible: "gauche" };
  if (s < 0) return { type: "regard", cible: "droite" };
  if (/\b(ailleurs|autour|partout)\b/.test(c)) return { type: "regard", cible: "libre" };
  return { type: "regard", cible: "public" };
}

function camera(c) {
  if (!/\b(vue|camera|cadre|plan|zoom|plongee|contre-plongee|recadre|filme)\b/.test(c)) return null;
  const T = [["gros_plan", /\b(gros plan|visage|zoom avant|rapproche la camera)\b/], ["plan_americain", /\bplan americain\b/],
    ["plan_large", /\b(plan large|plan d'ensemble|zoom arriere|recule la camera)\b/], ["plein_pied", /\b(plein pied|en pied|corps entier)\b/],
    ["contre_plongee", /\bcontre-plongee\b/], ["plongee", /\b(plongee|d'en haut|du dessus)\b/], ["profil", /\bprofil\b/],
    ["dos", /\b(de dos|derriere)\b/], ["trois_quarts", /\btrois[- ]quarts?\b/], ["face", /\b(de face|face)\b/]];
  for (const [vue, re] of T) if (re.test(c)) return { type: "camera", vue };
  return null;
}

function lumiere(c) {
  if (!/\b(lumiere|eclairage|eclaire|projecteur|plein feux|douche|contre-jour)\b/.test(c)) return null;
  const T = [["douche", /\bdouche\b/], ["contre_jour", /\bcontre-jour\b/], ["chaude", /\b(chaude|ambre|doree)\b/],
    ["froide", /\b(froide|bleue|lunaire)\b/], ["plein_feux", /\b(plein feux|pleins feux|normale|allume|eclaire)\b/]];
  for (const [mode, re] of T) if (re.test(c)) return { type: "lumiere", mode };
  return null;
}

/* ── Répertoire élargi (version 2.2) : gestes, poses et mouvements de scène supplémentaires ── */
const GESTES_PLUS = [
  ["salut_militaire", /\b(salut militaire|salue militairement|salue comme un soldat|salue au garde[- ]a[- ]vous)/],
  ["bras_au_ciel", /\b(bras au ciel|leve les bras au ciel|victoire|hourra|youpi|triomphe|lance les bras en l'air)/],
  ["mains_jointes", /\b(mains jointes|joins les mains|prie\b|prier|priere|supplie|implore)/],
  ["signe_venir", /\b(signe de venir|signe d'approcher|invite[- ]le a venir|fais[- ]le venir|appelle[- ]le de la main)/],
  ["chasser", /\b(signe de partir|(?<!pas )chasse\b|chasser|congedie|revers de (la )?main|fais[- ]le partir)/],
  ["chut", /\b(chut|doigt sur la bouche|demande le silence|fais taire)/],
  ["mains_dos", /\bmains? (dans|derriere) (le |ton )?dos/],
  ["mains_poches", /\bmains? (dans|aux) (les |tes )?poches/],
  ["pouce_leve", /\b(pouce leve|leve le pouce|pouce en l'air|fais ok|fais signe que c'est bon)/],
  ["se_designer", /\b(montre[- ]toi du doigt|designe[- ]toi|pointe[- ]toi|qui\? moi|moi\?)/],
  ["tete_mains", /\b(tete dans (les|tes) mains|prends ta tete|prends[- ]toi la tete|desespoir)/],
  ["frapper_porte", /\b(frappe a la porte|toque|cogne a la porte|frappe trois coups)/],
  ["boire", /\b(bois\b|boire|bois un verre|trinque|prends un verre)/],
  ["telephoner", /\b(telephone|au telephone|decroche|appelle quelqu'un|passe un coup de fil)/],
  ["ecrire", /\b(ecris|ecrire|prends des notes|note quelque chose|signe le papier|redige)/],
  ["lire", /\b(lis un livre|lire un livre|lit un livre|feuillette|lis une lettre|lis le journal|lecture)/],
  ["montre", /\b(regarde (ta|sa|la) montre|regarde l'heure|quelle heure|consulte ta montre)/],
  ["essuyer_front", /\b(essuie[- ]toi le front|essuie le front|essuie la sueur|il fait chaud|eponge[- ]toi)/],
  ["bailler", /\b(baille|bailler|baillement)/],
  ["frotter_yeux", /\b(frotte[- ]toi les yeux|frotte les yeux|reveille[- ]toi|tu te reveilles)/],
  ["sautiller", /\b(sautille|sautiller|trepigne|petits sauts)/],
  ["sauter", /\b(saute|sauter|bondis|bondir|fais un saut|saut)\b/],
  ["serrer_main", /\b(serre la main|serre[- ]lui la main|poignee de main|tends la main pour saluer|serrer la main)/],
  ["repousser", /\b(repousse|repousser|tiens[- ]le a distance|garde tes distances|recule de la main)/],
  ["trembler", /\b(tremble|trembler|frissonne|grelotte|frisson|tu as froid)/],
  ["frotter_mains", /\b(frotte[- ]toi les mains|frotte les mains|se frotter les mains)/],
  ["muscles", /\b(montre tes muscles|fais le fort|biceps|fais le costaud|bombe le torse)/],
  ["accolade", /\b(prends[- ]le dans tes bras|accolade|enlace|etreins|serre[- ]le dans tes bras|embrasse)/],
  ["lancer", /\b(lance|jette|lancer|jeter)\b/],
  ["ramasser", /\b(ramasse|ramasser|cueille|prends quelque chose par terre)/],
  ["coup_de_pied", /\b(coup de pied|shoote|frappe du pied|botte)/],
  ["boxer", /\b(boxe|boxer|coup de poing|coups de poing|uppercut|frappe\b|cogne\b|bats[- ]toi)/],
  ["pousser", /\b(pousse|pousser)\b/],
  ["tirer", /\b(tire\b|tirer|hale|tire la corde)/],
  ["pointes_pieds", /\b(pointe des pieds|pointes des pieds|sur les pointes|demi[- ]pointes)/],
  ["tituber", /\b(titube|tituber|chancelle|ivre|vacille|tu es saoul)/],
  ["regarder_loin", /\b(main en visiere|scrute|cherche au loin|guette)/],
  ["eternuer", /\b(eternue|eternuer|atchoum)/],
  ["tousser", /\b(tousse|tousser|toux|racle[- ]toi la gorge)/],
  ["compter", /\b(compte sur (tes|les) doigts|compte jusqu|compte\b)/],
  ["menacer", /\b(menace|menacer|doigt menacant|sermonne|gronde|fais la morale)/],
  ["hesiter", /\b(hesite|hesiter|indecis|tu ne sais pas quoi faire|tergiverse)/],
  ["ecouter", /\b(tends l'oreille|main a l'oreille|ecoute bien|ecoute\b|tu entends)/],
  ["bercer", /\b(berce|bercer|un bebe|nourrisson)/],
  ["mimer_mur", /\b(mur invisible|mime un mur|fais le mime)/],
  ["dormir", /\b(dors\b|dormir|endors|sommeil|fais dodo|sieste|assoupis)/],
];
POSES.unshift(
  ["effondre", /\b(effondre|ecroule|evanouis|s'evanouir|tombe\b|tombe par terre|fais le mort|allonge|couche[- ]toi|etends[- ]toi par terre)/],
  ["en_garde", /\b(en garde|garde de boxe|position de combat|pret a te battre|pret au combat)/],
  ["penseur", /\b(penseur|pose du penseur)/],
  ["statue", /\b(statue|fais la statue|liberte eclairant)/],
);

/* Mouvements de scène composés (plusieurs déplacements) */
function mouvementsScene(c, schema) {
  const L = schema.lieux, d = (x, z, extra = {}) => ({ type: "deplacer", ...(x !== null ? { x } : {}), ...(z !== null ? { z } : {}), ...extra });
  if (/\b(tourne sur toi[- ]meme|pirouette|virevolte|tour sur toi|tour complet|tourbillonne)/.test(c)) return [{ type: "orienter", angle: 360, relatif: true }];
  if (/\b(fais le tour|tour du plateau|tour de (la )?scene|fais un tour|parcours (la scene|le plateau))/.test(c))
    return [d(1.5, -1.0), d(-1.5, -1.0), d(-1.5, 1.0), d(1.5, 1.0), d(0, 0)];
  if (/\b(cent pas|100 pas|va[- ]et[- ]vient|vas et viens|aller[- ]retour|arpente)/.test(c)) return [d(1.2, null), d(-1.2, null), d(1.2, null), d(0, null)];
  if (/\b(sors|sortie|quitte la scene|quitte le plateau|va[- ]t'en de la scene|disparais)/.test(c)) {
    const x = /\bjardin\b/.test(c) ? schema.plateau.x[0] : schema.plateau.x[1];
    return [d(x, null, { course: /\b(vite|cours|en courant)/.test(c) })];
  }
  if (/\b(entre en scene|fais ton entree|reviens en scene|reviens au centre|va au centre|place[- ]toi au centre)/.test(c)) return [d(L.centre[0], L.centre[1])];
  if (/^(re)?monte\b/.test(c)) return [d(null, L.lointain[1])];
  if (/^(re)?descends\b/.test(c)) return [d(null, L.avant_scene[1])];
  if (/\b(pas chasses?|chasse[- ]croise|decale[- ]toi|glisse sur le cote)/.test(c) || (/\b(va|vas|marche|deplace[- ]toi)\b/.test(c) && /\b(a|vers) (ta |ma |sa |la )?(gauche|droite)\b/.test(c))) {
    const s = sens(c) || 1;
    const m = c.match(/(\d+(?:[.,]\d+)?)\s*(pas|metres?|m\b)/);
    const metres = m ? (m[2] === "pas" ? Number(m[1].replace(",", ".")) * 0.6 : Number(m[1].replace(",", "."))) : 1.0;
    return [{ type: "deplacer", lateral: metres * s }];
  }
  return null;
}

/* ── Exemples : vocabulaire de référence (aide, correction orthographique, rapprochement, tests) ── */
export const EXEMPLES = [
  "lève le bras droit", "lève le bras gauche", "lève les deux bras", "baisse les bras", "tends le bras droit devant toi", "écarte les bras sur le côté",
  "plie le coude", "tends le bras", "ouvre la main", "ferme le poing", "lève la main", "tourne la tête à gauche", "tourne la tête à droite",
  "baisse la tête", "lève la tête", "penche la tête sur le côté", "redresse la tête", "penche-toi en avant", "penche-toi en arrière",
  "penche le buste à gauche", "tourne le buste à droite", "hausse les épaules", "lève les épaules", "plie les genoux", "plie le genou droit",
  "lève la jambe droite", "lève le pied gauche", "tends la jambe", "écarte les jambes", "pointe le pied", "baisse le bassin",
  "souris", "fronce les sourcils", "lève les sourcils", "ferme les yeux", "ouvre les yeux", "ouvre la bouche", "fais la moue", "grimace",
  "sois en colère", "sois joyeux", "sois triste", "aie peur", "sois surpris", "sois tendre", "sois méprisant", "sois ironique", "sois las",
  "sois sûr de toi", "sois dégoûté", "reste neutre", "plus joyeux", "moins triste",
  "salue", "salue le public", "fais une révérence", "hoche la tête", "fais non de la tête", "croise les bras", "mains sur les hanches",
  "réfléchis", "applaudis", "ouvre les bras", "pointe vers la gauche", "lève le poing", "main sur le cœur", "gratte-toi la tête",
  "ris", "pleure", "soupire", "fais un clin d'œil", "danse", "tape du pied", "cache ton visage", "étire-toi", "respire profondément",
  "marche sur place", "fais un salut militaire", "lève les bras au ciel", "joins les mains", "fais signe de venir", "fais signe de partir",
  "chut", "mains dans le dos", "mains dans les poches", "lève le pouce", "désigne-toi", "prends ta tête dans tes mains",
  "frappe à la porte", "bois un verre", "téléphone", "écris", "lis un livre", "regarde ta montre", "essuie-toi le front", "bâille",
  "frotte-toi les yeux", "saute", "sautille", "serre la main", "repousse", "tremble", "frotte-toi les mains", "montre tes muscles",
  "prends-le dans tes bras", "lance", "ramasse quelque chose", "pousse", "tire", "boxe", "donne un coup de pied", "mets-toi sur la pointe des pieds",
  "titube", "scrute l'horizon", "éternue", "tousse", "compte sur tes doigts", "menace", "hésite", "tends l'oreille", "berce un bébé", "mime un mur invisible", "fais semblant de dormir",
  "assieds-toi", "lève-toi", "accroupis-toi", "mets-toi à genoux", "garde-à-vous", "recroqueville-toi", "effondre-toi", "mets-toi en garde",
  "prends la pose du penseur", "fais la statue", "repos",
  "avance", "avance de trois pas", "recule", "va côté cour", "va côté jardin", "va au lointain", "va à l'avant-scène", "approche-toi", "éloigne-toi",
  "cours vers le jardin", "tourne-toi vers la droite", "fais demi-tour", "tourne sur toi-même", "fais le tour de la scène", "fais les cent pas",
  "sors côté cour", "entre en scène", "va au centre", "fais un pas chassé à gauche", "monte", "descends", "de profil", "de dos", "fais face au public",
  "regarde-moi", "regarde en haut", "regarde en bas", "regarde au loin", "regarde à gauche",
  "dis bonjour", "chuchote je suis là", "crie au secours",
  "gros plan", "vue de face", "vue de profil", "plan large", "lumière douche", "contre-jour", "lumière chaude",
  "plus vite", "plus lentement", "mémorise cette pose sous le nom attente", "reprends la pose attente", "annule", "répète", "stop", "aide",
  "mets une chemise rouge", "barbe pleine", "cheveux gris", "plus grand", "plus costaud", "tu as 60 ans", "rase-toi",
  "habille-toi en monarque", "mets ton habit de soirée", "déguise-toi en clown", "mets un chapeau melon noir", "mets une cape rouge",
  "enlève ton chapeau", "mets une cravate bordeaux", "mets des gants blancs",
];

const VIDES = new Set(["le", "la", "les", "un", "une", "des", "de", "du", "d", "l", "a", "au", "aux", "et", "ou", "ton", "ta", "tes", "te", "toi", "moi",
  "me", "mon", "ma", "mes", "son", "sa", "ses", "sur", "dans", "en", "pour", "avec", "par", "vers", "stp", "svp", "s'il", "plait", "fais", "fait", "faire",
  "peu", "tres", "une", "maintenant", "quelque", "chose", "truc", "machin", "comme", "ca", "cela", "ceci", "genre", "alors", "donc", "encore", "bien", "tu", "vous", "il", "elle", "on", "je", "j", "y", "qu", "que", "qui", "ce", "cet", "cette"]);
let _lex = null;
function lexique() {
  if (_lex) return _lex;
  _lex = new Set();
  const extra = "lever baisser tourner pencher plier tendre ouvrir fermer marcher courir avancer reculer sauter danser saluer regarder bras main mains jambe jambes tete pied pieds genou genoux epaule epaules coude poignet doigt doigts dos ventre buste tronc bassin hanche hanches visage yeux bouche sourcils gauche droite droit devant derriere haut bas cote lentement doucement vite rapidement beaucoup completement legerement cour jardin lointain public scene plateau centre pirouette virevolte tourbillonne arpente chasse chasses decale glisse entree sors sortie quitte disparais monte descends dormir dors sieste semblant genou";
  // mots des exemples et de toutes les expressions reconnues (gestes, poses, émotions, verbes, parties du corps)
  const sources = [...GESTES_PLUS, ...GESTES, ...POSES, ...EMO, ...PARTIES].map(([, re]) => re.source).concat(Object.values(V).map((re) => re.source));
  const mots = sources.join(" ").replace(/\\[bdsw]/g, " ").replace(/[^a-z' -]+/g, " ");
  for (const e of [...EXEMPLES, extra, mots]) for (const w of chiffres(normaliser(e)).split(/\s+/)) if (w.length >= 3 && !/['-]$|^['-]/.test(w)) _lex.add(w);
  return _lex;
}
function distance(a, b) {
  const m = a.length, n = b.length, d = Array.from({ length: m + 1 }, (_, i) => [i, ...Array(n).fill(0)]);
  for (let j = 1; j <= n; j++) d[0][j] = j;
  for (let i = 1; i <= m; i++) for (let j = 1; j <= n; j++) {
    const c = a[i - 1] === b[j - 1] ? 0 : 1;
    d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c);
    if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
  }
  return d[m][n];
}
/* Correction des fautes de frappe : chaque mot inconnu de 4 lettres ou plus est remplacé par le mot connu le plus proche
   (1 erreur jusqu'à 7 lettres, 2 au-delà), à condition que la première lettre concorde. */
export function corriger(c) {
  const L = lexique();
  return c.split(/\s+/).map((w) => {
    if (w.length < 4 || L.has(w) || /\d/.test(w) || VIDES.has(w)) return w;
    const tol = w.length >= 8 ? 2 : 1;
    let meilleur = null, dmin = tol + 1;
    for (const x of L) {
      if (x[0] !== w[0] || Math.abs(x.length - w.length) > tol) continue;
      const dd = distance(w, x);
      if (dd < dmin) { dmin = dd; meilleur = x; }
    }
    return meilleur || w;
  }).join(" ");
}
function racines(c) {
  return new Set(c.split(/[\s'’-]+/).filter((w) => w.length > 1 && !VIDES.has(w)).map((w) => w.slice(0, 5)));
}
/* Rapprochement : exemple le plus proche par recouvrement des racines (coefficient de Dice). */
export function rapprocher(c, n = 1) {
  const A = racines(c);
  if (!A.size) return [];
  return EXEMPLES.map((e) => {
    const B = racines(chiffres(normaliser(e)));
    let k = 0; for (const x of A) if (B.has(x)) k++;
    return { exemple: e, score: B.size ? (2 * k) / (A.size + B.size) : 0 };
  }).sort((a, b) => b.score - a.score).slice(0, n);
}

/* ── Analyse d'une proposition (clause) ────────────────── */
function analyserClause(c, original, schema) {
  const f = facteur(c);
  const vit = vitesseDe(c);
  const avec = (a) => (vit && a && !("vitesse" in a) ? { ...a, vitesse: vit } : a);
  const out = [];

  if (/^(stop|arrete|arrete[- ]toi|arret|fige[- ]toi|ne bouge plus|immobile|on arrete|halte)\b/.test(c)) return [{ type: "arret" }];
  if (/^(repete|encore une fois|recommence|refais|une autre fois|bis)\b/.test(c)) return [{ type: "repeter" }];
  if (/^(annule|defais|reviens en arriere|retour arriere)\b/.test(c)) return [{ type: "annuler" }];
  if (/^(aide|help|que sais[- ]tu faire|qu'est[- ]ce que tu sais faire|que peux[- ]tu faire|quelles commandes|liste des commandes|commandes)\b/.test(c)) return [{ type: "aide" }];
  if (/^(lis|lit|lire) (un livre|une lettre|le journal|ce livre)/.test(c)) return [{ type: "geste", nom: "lire", intensite: 1 }];
  const dire = original.match(/^\s*(dis|dit|dire|prononce|recite|declame|déclame|récite|reponds|réponds|chuchote|murmure|crie|hurle|parle|annonce|lis)\b\s*:?\s*(.*)$/i);
  if (dire && dire[2].trim()) {
    const verbe = normaliser(dire[1]);
    const maniere = /chuchote|murmure/.test(verbe) ? "chuchote" : /crie|hurle/.test(verbe) ? "crie" : null;
    let texte = dire[2].trim().replace(/^(que|qu')\s*/i, "").replace(/^(a|à) (tout le monde|moi|nous|la salle)\s*:?\s*/i, "");
    return [{ type: "dire", texte, ...(maniere ? { maniere } : {}) }];
  }
  const mem = c.match(/\b(memorise|retiens|enregistre|sauvegarde|garde) (cette |la |ta )?(pose|position|posture)(?: (?:sous|comme|en tant que)(?: le nom)?)? ?([a-z0-9' -]+)?$/);
  if (mem) return [{ type: "memoriser", nom: (mem[4] || "").trim() || "pose" }];
  const rap = c.match(/\b(reprends|rappelle|retrouve|reviens a|reviens en|prends|fais|adopte) (la |ta )?(pose|position|posture) ([a-z0-9' -]+)$/);
  if (rap) {
    const nom = rap[4].trim().replace(/^(du|de la|de l'|des|de|d')\s*/, "");
    const interne = POSES.find(([n, re]) => n === nom.replace(/[ -]/g, "_") || normaliser(n.replace(/_/g, " ")) === nom || re.test(nom));
    return [interne ? avec({ type: "pose", nom: interne[0] }) : { type: "rappeler", nom }];
  }
  const cam = camera(c); if (cam) return [cam];
  const lum = lumiere(c); if (lum) return [lum];

  for (const [nom, re] of [...GESTES_PLUS, ...GESTES]) {
    if (re.test(c)) {
      const g = { type: "geste", nom, intensite: f };
      if (["saluer", "pointer", "poing_leve", "main_coeur", "gratter_tete", "taper_pied", "salut_militaire", "signe_venir", "chasser", "pouce_leve"].includes(nom) && /\b(gauche|droite?)\b/.test(c) && !/\b(vers|a) (la |ta |ma )?(gauche|droite)\b/.test(c)) g.cote = cotes(c)[0];
      if (nom === "pointer") { const s = sens(c); g.direction = /\b(haut|ciel)\b/.test(c) ? "haut" : /\b(bas|sol)\b/.test(c) ? "bas" : s > 0 ? "gauche" : s < 0 ? "droite" : "devant"; }
      const rep = c.match(/\b(\d+) fois\b/); if (rep) g.repetitions = Math.min(8, Number(rep[1]));
      out.push(avec(g));
      const e = EMO.find(([, re2]) => re2.test(c));
      if (e && nom !== "rire" && nom !== "pleurer") out.push({ type: "emotion", nom: e[0], intensite: intensiteDe(c) });
      return out;
    }
  }
  for (const [nom, re] of POSES) {
    if (re.test(c) && !(nom === "debout" && PARTIES.some(([p, r]) => p !== "tronc" && r.test(c)))) {
      if (nom === "repos" && /\b(bras|jambes?|tete|visage)\b/.test(c)) break;
      return [avec({ type: "pose", nom })];
    }
  }
  const vis = visage(c, f);
  if (vis) return [vis];

  const reg = regard(c);
  const partie = /\b(penche|bascule|courbe|plie|incline)[- ]toi\b/.test(c) && !/\b(tete|bras|jambes?|genoux?)\b/.test(c)
    ? ["tronc"] : PARTIES.find(([, re]) => re.test(c));
  if (partie && !["sourcils", "yeux", "bouche"].includes(partie[0]) && !(reg && partie[0] === "tete" && !V.tourner.test(c) && !V.lever.test(c) && !V.baisser.test(c))) {
    const arts = articulations(c, partie[0], f).map(avec);
    if (arts.length) {
      out.push(...arts);
      const e = EMO.find(([, re2]) => re2.test(c));
      if (e) out.push({ type: "emotion", nom: e[0], intensite: intensiteDe(c) });
      return out;
    }
  }
  if (reg) return [reg];
  const mvt = mouvementsScene(c, schema);
  if (mvt) return mvt.map(avec);
  const dep = deplacement(c, schema);
  if (dep) return [avec(dep)];

  const app = apparence(c, schema);
  if (app.length) return app;

  const emo = EMO.find(([, re]) => re.test(c));
  if (emo) {
    const plus = /\b(plus|davantage|encore plus)\b/.test(c), moins = /\bmoins\b/.test(c);
    if (plus || moins) return [{ type: "emotion", nom: emo[0], intensite: plus ? 2 : -2, relatif: true }];
    return [{ type: "emotion", nom: emo[0], intensite: emo[0] === "neutre" ? 0 : intensiteDe(c) }];
  }
  if (vit) return [{ type: "vitesse", facteur: vit }];
  if (/\b(vitesse normale|rythme normal)\b/.test(c)) return [{ type: "vitesse", facteur: 1 }];
  return [];
}

const DETERMINANTS = new Set(["le", "la", "les", "l", "ton", "ta", "tes", "son", "sa", "ses", "un", "une", "des", "du", "aussi"]);
const VERBES_DIRE =/^(dis|dit|dire|prononce|recite|declame|reponds|chuchote|murmure|crie|hurle|parle|annonce|lis)\b/;

/* Découpe : phrases, puis « puis / ensuite / et puis », puis « , » et « et » (sauf dans une parole). */
export function decouper(texte) {
  const guillemets = [];
  const protege = String(texte || "").replace(/[«“"]\s*([^»”"]+?)\s*[»”"]/g, (_, t) => `⟦${guillemets.push(t) - 1}⟧`);
  const restaurer = (s) => s.replace(/⟦(\d+)⟧/g, (_, i) => guillemets[Number(i)]);
  const clauses = [];
  for (const phrase of protege.split(/(?<!\d)[.;!?\n]+(?!\d)/)) {
    for (const bloc of phrase.split(/\s*,?\s+(?:et puis|puis|ensuite|apres quoi|après quoi|enfin)\s+/i)) {
      const b = bloc.trim();
      if (!b) continue;
      if (VERBES_DIRE.test(normaliser(b))) { clauses.push(restaurer(b)); continue; }
      let verbe = null;
      for (const brut of b.split(/\s*,\s*|\s+et\s+/i)) {
        let p = brut.trim();
        if (!p) continue;
        const premier = normaliser(p).split(/[\s']/)[0];
        // « lève le bras droit et le gauche » : le fragment sans verbe hérite du verbe précédent
        if (DETERMINANTS.has(premier) && verbe) p = `${verbe} ${p}`;
        else if (!DETERMINANTS.has(premier)) verbe = p.split(/\s+/)[0];
        clauses.push(restaurer(p));
      }
    }
  }
  return clauses;
}

/* Point d'entrée : renvoie {actions, ignores, clauses}. */
export function interpreter(texte, schema) {
  const actions = [], ignores = [], suggestions = {}, clauses = decouper(texte);
  let partiePrecedente = null;
  for (const brut of clauses) {
    const c = chiffres(normaliser(brut));
    let a = [], note = null;
    // fautes de frappe corrigées d'abord (« marche vers le jardain »), sauf dans une parole
    const cc = VERBES_DIRE.test(c) || /[«"“]/.test(brut) ? c : corriger(c);
    if (cc !== c) { a = analyserClause(cc, cc, schema); if (a.length) note = { corrige: cc }; }
    if (!a.length) a = analyserClause(c, brut, schema);
    // « fais semblant de dormir », « mime la peur », « imite un boxeur »
    const sem = c.match(/^(fais semblant de|fais comme si tu|mime|imite|joue a|joue)\s+(.+)$/);
    if (!a.length && sem) { a = analyserClause(corriger(sem[2]), sem[2], schema); if (a.length) note = { approx: sem[2] }; }
    // « lève le bras droit et le gauche » : le fragment reprend la partie du corps précédente
    if (!a.length && partiePrecedente && /\b(gauche|droite?)\b/.test(c)) {
      const c2 = c.replace(/\b(le|la|l')\s*(gauche|droite?)\b/, `$1 ${partiePrecedente} $2`);
      if (c2 !== c) a = analyserClause(c2, brut, schema);
    }
    // fautes de frappe (« lève le brass droit », « assied-toi »)
    if (!a.length) {
      const c3 = corriger(c);
      if (c3 !== c) { a = analyserClause(c3, c3, schema); if (a.length) note = { corrige: c3 }; }
    }
    // formulation voisine d'une commande connue
    if (!a.length) {
      const [r] = rapprocher(corriger(c));
      if (r && r.score >= 0.6) { const e = chiffres(normaliser(r.exemple)); a = analyserClause(e, r.exemple, schema); if (a.length) note = { approx: r.exemple }; }
    }
    if (/\b(allonge|couche[- ]toi|etends[- ]toi par terre)/.test(c) && a.length) note = { approx: "effondre-toi (la position allongée n'est pas modélisée)" };
    const p = PARTIES.find(([, re]) => re.test(c));
    if (p) partiePrecedente = c.match(p[1])[0];
    if (a.length) actions.push(...a.map((x) => ({ ...x, clause: brut, ...(note || {}) })));
    else { ignores.push(brut); suggestions[brut] = rapprocher(corriger(c), 3).filter((x) => x.score > 0).map((x) => x.exemple); }
  }
  return { actions: valider(actions, schema).actions, ignores, suggestions, clauses };
}

/* Validation stricte (même règle que bridge/partenaire/avatar.py) : type connu, valeurs bornées. */
export function valider(actions, schema) {
  const ok = [], rejets = [];
  const borne = (v, a, b) => Math.max(a, Math.min(b, Number(v)));
  for (const a of Array.isArray(actions) ? actions : []) {
    if (!a || typeof a !== "object") { rejets.push({ action: a, motif: "objet attendu" }); continue; }
    const x = { ...a };
    switch (x.type) {
      case "articulation": {
        const d = schema.dofs[x.dof];
        if (!d || !Number.isFinite(Number(x.valeur))) { rejets.push({ action: a, motif: "articulation inconnue ou valeur non numérique" }); continue; }
        x.valeur = x.relatif ? borne(x.valeur, -(d.max - d.min), d.max - d.min) : borne(x.valeur, d.min, d.max);
        break;
      }
      case "emotion":
        if (!schema.emotions.includes(x.nom)) { rejets.push({ action: a, motif: "émotion inconnue" }); continue; }
        x.intensite = x.relatif ? borne(x.intensite ?? 2, -10, 10) : borne(x.intensite ?? 7, 0, 10); break;
      case "geste": if (!schema.gestes.includes(x.nom)) { rejets.push({ action: a, motif: "geste inconnu" }); continue; } break;
      case "pose": if (!schema.poses.includes(x.nom)) { rejets.push({ action: a, motif: "pose inconnue" }); continue; } break;
      case "regard": if (!schema.regards.includes(x.cible)) { rejets.push({ action: a, motif: "cible de regard inconnue" }); continue; } break;
      case "camera": if (!schema.vues.includes(x.vue)) { rejets.push({ action: a, motif: "vue inconnue" }); continue; } break;
      case "lumiere": if (!schema.lumieres.includes(x.mode)) { rejets.push({ action: a, motif: "éclairage inconnu" }); continue; } break;
      case "dire": x.texte = String(x.texte || "").slice(0, 600); if (!x.texte.trim()) { rejets.push({ action: a, motif: "texte vide" }); continue; } break;
      case "visage": {
        const au = {};
        for (const [k, v] of Object.entries(x.au || {})) if (/^au\d{1,2}(_[gd])?$/.test(k) && Number.isFinite(Number(v))) au[k] = borne(v, 0, 1);
        x.au = au; break;
      }
      case "deplacer": {
        const P = schema.plateau;
        if ("x" in x) x.x = borne(x.x, P.x[0], P.x[1]);
        if ("z" in x) x.z = borne(x.z, P.z[0], P.z[1]);
        if ("avant" in x) x.avant = borne(x.avant, -3, 3);
        if ("lateral" in x) x.lateral = borne(x.lateral, -3, 3);
        break;
      }
      case "orienter": x.angle = borne(x.angle, -360, 360); break;
      case "vitesse": x.facteur = borne(x.facteur, 0.2, 3); break;
      case "apparence": {
        const A = schema.apparence;
        if (["taille", "carrure", "corpulence", "age"].includes(x.cle)) {
          const r = A[x.cle];
          x.valeur = x.relatif ? borne(x.valeur, -(r.max - r.min), r.max - r.min) : borne(x.valeur, r.min, r.max);
        } else if (x.cle === "cheveux" && !A.cheveux.includes(x.valeur)) { rejets.push({ action: a, motif: "coiffure inconnue" }); continue; }
        else if (x.cle === "barbe" && !A.barbe.includes(x.valeur)) { rejets.push({ action: a, motif: "barbe inconnue" }); continue; }
        else if (x.cle === "manches" && !A.manches.includes(x.valeur)) { rejets.push({ action: a, motif: "manches inconnues" }); continue; }
        else if (x.cle === "peau" && !A.peau.includes(x.valeur)) { rejets.push({ action: a, motif: "teinte inconnue" }); continue; }
        else if (["haut", "bas", "chaussures", "couleur_cheveux"].includes(x.cle) && !(x.valeur in A.couleurs) && !/^#[0-9a-f]{6}$/i.test(String(x.valeur))) { rejets.push({ action: a, motif: "couleur inconnue" }); continue; }
        else if (["matiere", "chapeau", "cou", "cape", "jupe"].includes(x.cle) && !(A[x.cle] || []).includes(x.valeur)) { rejets.push({ action: a, motif: `valeur inconnue pour ${x.cle}` }); continue; }
        else if (x.cle === "habillage" && !(A.habillages || {})[x.valeur]) { rejets.push({ action: a, motif: "habillage inconnu" }); continue; }
        else if (["couleur_chapeau", "accessoire"].includes(x.cle) && !(x.valeur in A.couleurs) && !/^#[0-9a-f]{6}$/i.test(String(x.valeur))) { rejets.push({ action: a, motif: "couleur inconnue" }); continue; }
        else if (x.cle === "gants") x.valeur = !!x.valeur;
        else if (!["taille", "carrure", "corpulence", "age", "cheveux", "barbe", "manches", "peau", "haut", "bas", "chaussures", "couleur_cheveux", "moustache", "yeux",
          "matiere", "chapeau", "couleur_chapeau", "cou", "cape", "jupe", "gants", "accessoire", "habillage"].includes(x.cle)) { rejets.push({ action: a, motif: "attribut d'apparence inconnu" }); continue; }
        break;
      }
      case "memoriser": case "rappeler": x.nom = String(x.nom || "pose").slice(0, 40); break;
      case "arret": case "repeter": case "annuler": case "aide": break;
      default: rejets.push({ action: a, motif: "type d'action inconnu" }); continue;
    }
    if ("vitesse" in x && x.type !== "vitesse") x.vitesse = borne(x.vitesse, 0.2, 3);
    ok.push(x);
  }
  return { actions: ok, rejets };
}
