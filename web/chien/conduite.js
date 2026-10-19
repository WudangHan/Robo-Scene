/* Robo-Scène — conduite du chien de scène : repères joués au GO, validés avant d'être joués (même logique que le
   drone). Chaque marche est une ligne droite à secousse minimale, échantillonnée tous les 5 cm contre le sol
   praticable ; une durée trop courte est allongée, jamais raccourcie ; le GO reste bloqué tant qu'un trajet
   quitte le sol praticable, approche le public en représentation ou traverse le cercle d'un interprète.

   Format : { "titre": "…", "mode": "…", "reperes": [ { "id": "C1", "nom": "…",
     "action": "lever" | "coucher" | "posture" | "allure" | "aller" | "tourner" | "attendre" | "regarder",
     "vers": "centre" | [x, z], "duree": 6, "lacet": 0 (degrés : 0 = vers la salle, 90 = vers cour), "posture": "assis", "allure": "joyeux",
     "regard": "salle" | [x, y, z] | null, "note": "…" } ] } */
import { pointSol, verifierSol, verifierTrajet } from "./sol.js";
import { ALLURES, POSTURES, dureeMarche } from "./chien.js";

export const ACTIONS = ["lever", "coucher", "posture", "allure", "aller", "tourner", "attendre", "regarder"];

export function cibleRegard(salle, r) {
  if (r === null || r === undefined) return null;
  if (Array.isArray(r) && r.length === 3) return r.slice();
  if (r === "salle") return [0, 1.2, 9];
  if (typeof r === "string" && salle.reperes[r]) return salle.reperes[r].slice();
  const p = pointSol(salle, r); return [p[0], 0.4, p[1]];
}

export function compiler(salle, conduite, depart, ctx = {}) {
  const erreurs = [], avert = [], segments = [];
  const mode = ctx.mode || conduite.mode || "plateau";
  const c = { mode, interpretes: ctx.interpretes || [] };
  let p = (depart || salle.sol.aire.centre).slice(), t = 0, debout = !!ctx.debout, allure = ctx.allure || "neutre";
  const ids = new Set();
  (conduite.reperes || []).forEach((r, i) => {
    const id = r.id || `C${i + 1}`, action = r.action || "aller";
    if (ids.has(id)) erreurs.push(`${id} : identifiant en double`);
    ids.add(id);
    if (!ACTIONS.includes(action)) { erreurs.push(`${id} : action inconnue « ${action} »`); return; }
    let p1 = p.slice(), T = r.duree ?? 1.0, extra = {};
    try {
      if (action === "lever") { T = Math.max(1.0, r.duree ?? 1.0); debout = true; }
      else if (action === "coucher") { T = Math.max(1.0, r.duree ?? 1.0); debout = false; }
      else if (action === "posture") {
        if (!POSTURES[r.posture]) throw new Error(`posture inconnue « ${r.posture} »`);
        if (!debout && !["couche", "debout"].includes(r.posture)) erreurs.push(`${id} : le robot doit être debout pour « ${POSTURES[r.posture].libelle} »`);
        T = Math.max(1.2, r.duree ?? 2.0); extra.posture = r.posture;
        if (r.posture === "debout") debout = true; if (r.posture === "couche") debout = false;
      } else if (action === "allure") {
        if (!ALLURES[r.allure]) throw new Error(`allure inconnue « ${r.allure} »`);
        allure = r.allure; extra.allure = r.allure; T = r.duree ?? 0.3;
      } else if (action === "aller") {
        p1 = pointSol(salle, r.vers);
        if (!debout) erreurs.push(`${id} : le robot doit se lever avant de marcher`);
        const v = verifierSol(salle, p1, c);
        if (!v.ok) erreurs.push(`${id} (${r.nom || action}) : destination interdite — ${v.motif}`);
        else {
          const s = verifierTrajet(salle, p, p1, c);
          if (!s.ok) erreurs.push(`${id} (${r.nom || action}) : trajet interdit à ${Math.round(s.fraction * 100)} % — ${s.motif}`);
        }
        const D = dureeMarche(salle, p, p1, mode, r.duree, ALLURES[allure].vitesse);
        if (D.ralenti) avert.push(`${id} : durée allongée de ${r.duree} à ${D.T.toFixed(1)} s (plafonds de vitesse du sol${allure !== "neutre" ? `, allure ${ALLURES[allure].libelle.toLowerCase()}` : ""})`);
        T = D.T + 0.6;
      } else if (action === "tourner") {
        if (!debout) erreurs.push(`${id} : le robot doit être debout pour tourner`);
        T = Math.max(0.8, r.duree ?? 1.5);
      } else if (action === "attendre") T = Math.max(0.2, r.duree ?? 2);
      else if (action === "regarder") { extra.regard = cibleRegard(salle, r.regard); T = r.duree ?? 0.5; }
    } catch (e) { erreurs.push(`${id} : ${e.message}`); return; }
    segments.push({ id, nom: r.nom || "", action, p0: p.slice(), p1, debut: t, T, lacet: r.lacet ?? null, note: r.note || "", ...extra });
    t += T; p = p1;
  });
  if (debout && segments.length) avert.push("La conduite se termine debout (aucun repère « coucher »)");
  return { ok: erreurs.length === 0, erreurs, avertissements: avert, segments, duree: t, mode };
}

export const CONDUITE_EXEMPLE = {
  titre: "Le chien du veilleur — essai de conduite",
  mode: "salle_vide",
  reperes: [
    { id: "C1", nom: "Réveil", action: "lever" },
    { id: "C2", nom: "Curiosité", action: "allure", allure: "curieux" },
    { id: "C3", nom: "Vers le centre", vers: "centre", duree: 9 },
    { id: "C4", nom: "Regard vers la salle", action: "regarder", regard: "salle", duree: 1.5 },
    { id: "C5", nom: "Il s'assoit", action: "posture", posture: "assis", duree: 3 },
    { id: "C6", nom: "Il donne la patte", action: "posture", posture: "patte", duree: 2.5, note: "L'interprète s'accroupit à 1,5 m" },
    { id: "C7", nom: "Joie", action: "allure", allure: "joyeux" },
    { id: "C8", nom: "Il se relève", action: "posture", posture: "debout" },
    { id: "C9", nom: "Vers l'avant-scène", vers: "avant_scene", duree: 6 },
    { id: "C10", nom: "Vers l'escalier cour", vers: "haut_escalier_cour", duree: 8 },
    { id: "C11", nom: "Descente", vers: "bas_escalier_cour", duree: 8, note: "Escalier éprouvé hors public" },
    { id: "C12", nom: "Traversée devant le premier rang", vers: "avant_salle_centre", duree: 10, lacet: 180 },
    { id: "C13", nom: "Révérence au plateau", action: "posture", posture: "etirement", duree: 3 },
    { id: "C14", nom: "Repos", action: "coucher" },
  ],
};
