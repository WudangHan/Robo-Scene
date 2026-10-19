/* Robo-Scène — conduite du drone : liste de repères (cues) jouée au GO, validée avant d'être jouée.
   Module pur (testé sous Node). Chaque repère est un déplacement en ligne droite selon une loi à secousse minimale ;
   la validation échantillonne chaque segment contre les zones de vol (géorepérage), allonge les durées trop courtes
   au lieu de refuser (comme la couche de sécurité du pont pour les articulations) et bloque le GO tant qu'un segment
   traverse un obstacle, le public ou le cylindre d'un interprète.

   Format (JSON) :
   { "titre": "…", "mode": "plateau" | "salle_vide" | "representation",
     "reperes": [ { "id": "D1", "nom": "…", "action": "decoller" | "aller" | "stationnaire" | "atterrir",
                    "vers": "centre" | [x, y, z], "duree": 6, "vitesse": 0.8, "lacet": 0,
                    "camera": { "viser": "centre" | [x, y, z] | null, "inclinaison": -20, "zoom": 1 },
                    "led": "#f2b544", "note": "…" } ] } */
import { point, verifier, verifierSegment } from "./geofence.js";
import { dureeMin } from "./vol.js";

export const ACTIONS = ["decoller", "aller", "stationnaire", "atterrir"];

export function compiler(salle, conduite, depart, ctx = {}) {
  const erreurs = [], avert = [], segments = [];
  const mode = ctx.mode || conduite.mode || "plateau";
  const c = { mode, interpretes: ctx.interpretes || [] };
  let p = (depart || salle.aire.centre).slice(), t = 0, enVol = (depart || salle.aire.centre)[1] > 0.05;
  const ids = new Set();
  (conduite.reperes || []).forEach((r, i) => {
    const id = r.id || `D${i + 1}`, action = r.action || "aller";
    if (ids.has(id)) erreurs.push(`${id} : identifiant en double`);
    ids.add(id);
    if (!ACTIONS.includes(action)) { erreurs.push(`${id} : action inconnue « ${action} »`); return; }
    let p1;
    try {
      if (action === "decoller") p1 = [p[0], p[1] + (r.hauteur ?? 1.5), p[2]];
      else if (action === "atterrir") p1 = [p[0], 0, p[2]];
      else if (action === "stationnaire") p1 = p.slice();
      else p1 = point(salle, r.vers);
    } catch (e) { erreurs.push(`${id} : ${e.message}`); return; }
    if (action === "decoller" && enVol) erreurs.push(`${id} : décollage alors que le drone est déjà en vol`);
    if (action !== "decoller" && !enVol) erreurs.push(`${id} : le drone doit décoller avant ce repère`);
    if (action === "atterrir") {
      const zone = salle.volumes.plateau.z[1] < p[2] ? salle.volumes.salle.y[0] : 0;
      p1[1] = zone;
      const dA = Math.hypot(p[0] - salle.aire.centre[0], p[2] - salle.aire.centre[2]);
      if (dA > salle.aire.rayon) avert.push(`${id} : atterrissage hors de l'aire de décollage`);
    } else if (action !== "stationnaire") {
      const v = verifier(salle, p1, c);
      if (!v.ok) erreurs.push(`${id} (${r.nom || action}) : destination interdite — ${v.motif}`);
      const s = verifierSegment(salle, p, p1, c);
      if (v.ok && !s.ok) erreurs.push(`${id} (${r.nom || action}) : trajectoire interdite à ${Math.round(s.fraction * 100)} % du trajet — ${s.motif}`);
    }
    let T;
    if (action === "stationnaire") T = { T: Math.max(0.5, r.duree ?? 3), ralenti: false };
    else if (action === "decoller" || action === "atterrir") {
      const d = Math.abs(p1[1] - p[1]);
      T = { T: Math.max(r.duree ?? 0, d / Math.min(0.45, salle.regles.vitesse_max_v_m_s) + 0.5), ralenti: false };
    } else T = dureeMin(salle.regles, p, p1, r.duree, r.vitesse);
    if (T.ralenti) avert.push(`${id} : durée allongée de ${r.duree ?? "?"} à ${T.T.toFixed(1)} s (plafonds de vitesse)`);
    segments.push({ id, nom: r.nom || "", action, p0: p.slice(), p1, debut: t, T: T.T, lacet: r.lacet ?? null,
      camera: r.camera || null, led: r.led || null, note: r.note || "" });
    t += T.T; p = p1; enVol = action !== "atterrir";
  });
  if (enVol && segments.length) avert.push("La conduite se termine en vol (aucun repère « atterrir »)");
  return { ok: erreurs.length === 0, erreurs, avertissements: avert, segments, duree: t, mode };
}

export const CONDUITE_EXEMPLE = {
  titre: "L'oiseau de lumière — essai de conduite",
  mode: "salle_vide",
  reperes: [
    { id: "D1", nom: "Envol", action: "decoller", hauteur: 1.5, led: "#f2b544", camera: { viser: "centre", zoom: 1 } },
    { id: "D2", nom: "Approche du centre", vers: "centre", duree: 6, lacet: 0, camera: { viser: "avant_scene", inclinaison: -15 } },
    { id: "D3", nom: "Regard vers cour", vers: "cour", duree: 5, lacet: 90, led: "#6fa8ff", camera: { viser: "jardin" } },
    { id: "D4", nom: "Montée au lointain", vers: "lointain", duree: 6, lacet: 0, led: "#ffffff", camera: { viser: "centre", inclinaison: -30 } },
    { id: "D5", nom: "Suspension", action: "stationnaire", duree: 3, note: "Silence ; la poursuite se pose sur le drone" },
    { id: "D6", nom: "Passage du cadre", vers: "cadre_passage", duree: 7, lacet: 0, camera: { viser: "salle_centre" } },
    { id: "D7", nom: "Entrée en salle", vers: "salle_centre", duree: 8, led: "#ff5d5d", camera: { viser: "centre", inclinaison: -10 }, note: "Salle vide seulement (répétition)" },
    { id: "D8", nom: "Retour au plateau", vers: "centre_haut", duree: 9, lacet: 180, camera: { viser: "lointain" } },
    { id: "D9", nom: "Retour à l'aire", vers: "aire_haut", duree: 6, lacet: 180 },
    { id: "D10", nom: "Atterrissage", action: "atterrir" },
  ],
};

/* Position, vitesse et repère courant de la conduite compilée à l'instant t (aperçu et lecture simulée). */
export function etatA(comp, t) {
  const s = comp.segments.find((x) => t >= x.debut && t < x.debut + x.T) || comp.segments.at(-1);
  if (!s) return null;
  const u = Math.max(0, Math.min(1, (t - s.debut) / s.T)), f = u ** 3 * (10 - 15 * u + 6 * u * u);
  return { segment: s, p: s.p0.map((a, i) => a + (s.p1[i] - a) * f), u };
}
