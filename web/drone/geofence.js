/* Robo-Scène — zones de vol du drone (géorepérage intérieur).
   Module pur, sans dépendance : utilisé par le drone virtuel, par la conduite et par les tests (Node).
   La même règle est appliquée par le pont (bridge/drone/zones.py) à partir du même fichier salle.json ;
   un test vérifie que les deux implantations rendent le même verdict sur des milliers de points.

   Règle : un point est permis si
     1. le cube de demi-côté « marge » qui l'entoure (sauf vers le bas) est tout entier dans l'union des volumes
        ouverts par le mode de vol (plateau ; plateau + salle) ;
     2. ce cube ne touche aucun obstacle (cadre, manteau, porteuses, balcon, régie) ;
     3. il est à au moins « hauteur_min » du sol du volume, sauf au-dessus de l'aire de décollage ;
     4. il respecte le public : en « salle vide », les fauteuils sont un obstacle bas ; en « représentation »,
        chaque bloc de sièges devient une colonne d'exclusion de toute hauteur, élargie de la marge du public ;
     5. il reste hors du cylindre de chaque interprète déclaré (rayon et hauteur réglables). */

const DEDANS = (b, p, m = 0) => p[0] >= b.x[0] - m && p[0] <= b.x[1] + m && p[1] >= b.y[0] - m && p[1] <= b.y[1] + m
  && p[2] >= b.z[0] - m && p[2] <= b.z[1] + m;
const DEDANS_XZ = (b, p, m = 0) => p[0] >= b.x[0] - m && p[0] <= b.x[1] + m && p[2] >= b.z[0] - m && p[2] <= b.z[1] + m;

/* Décalages d'échantillonnage du cube de marge : 3 × 2 × 3 (pas de décalage vers le bas, le sol est traité à part). */
function decalages(m) {
  const o = [];
  for (const dx of [-m, 0, m]) for (const dy of [0, m]) for (const dz of [-m, 0, m]) o.push([dx, dy, dz]);
  return o;
}

export function volumeDe(salle, p, mode = "plateau") {
  const ids = (salle.modes[mode] || salle.modes.plateau).volumes;
  for (const id of ids) if (DEDANS(salle.volumes[id], p)) return id;
  return null;
}

export function verifier(salle, p, ctx = {}) {
  const R = salle.regles, mode = ctx.mode && salle.modes[ctx.mode] ? ctx.mode : "plateau";
  const M = salle.modes[mode], m = R.marge_m;
  if (!Array.isArray(p) || p.length !== 3 || p.some((v) => typeof v !== "number" || !Number.isFinite(v))) {
    return { ok: false, motif: "Position invalide", zone: null };
  }
  const zone = volumeDe(salle, p, mode);
  if (!zone) return { ok: false, motif: `Hors des volumes ouverts en mode « ${M.libelle} »`, zone: null };
  const vols = M.volumes.map((id) => salle.volumes[id]);
  for (const d of decalages(m)) {
    const q = [p[0] + d[0], p[1] + d[1], p[2] + d[2]];
    if (!vols.some((v) => DEDANS(v, q))) return { ok: false, motif: `Trop près de la limite du volume (marge ${m} m)`, zone };
  }
  for (const o of salle.obstacles) {
    if (DEDANS(o, p, m)) return { ok: false, motif: `Trop près : ${o.libelle} (marge ${m} m)`, zone, obstacle: o.id };
  }
  const aire = salle.aire, dA = Math.hypot(p[0] - aire.centre[0], p[2] - aire.centre[2]);
  const sol = salle.volumes[zone].y[0];
  if (p[1] - sol < R.hauteur_min_m && dA > aire.rayon) {
    return { ok: false, motif: `Trop bas (moins de ${R.hauteur_min_m} m du sol hors de l'aire de décollage)`, zone };
  }
  if (M.volumes.includes("salle")) {
    for (const b of salle.public) {
      if (M.public === "colonnes" && DEDANS_XZ(b, p, R.marge_public_m)) {
        return { ok: false, motif: `Survol du public interdit : ${b.libelle} (marge ${R.marge_public_m} m)`, zone, public: b.id };
      }
      if (M.public === "fauteuils") {
        const f = { x: b.x, y: [b.y[0], b.y[0] + R.hauteur_fauteuils_m], z: b.z };
        if (DEDANS(f, p, m)) return { ok: false, motif: `Trop près des fauteuils : ${b.libelle}`, zone, public: b.id };
      }
    }
  }
  for (const [i, it] of (ctx.interpretes || []).entries()) {
    const x = Array.isArray(it) ? it[0] : it.x, z = Array.isArray(it) ? it[1] : it.z;
    if (Math.hypot(p[0] - x, p[2] - z) < R.rayon_interpretes_m && p[1] < R.hauteur_interpretes_m) {
      return { ok: false, motif: `Trop près de l'interprète ${i + 1} (${R.rayon_interpretes_m} m sous ${R.hauteur_interpretes_m} m)`, zone };
    }
  }
  return { ok: true, motif: "", zone };
}

/* Vérifie un segment par échantillonnage (pas de 5 cm par défaut) ; rend le premier point fautif. */
export function verifierSegment(salle, a, b, ctx = {}, pas = 0.05) {
  const d = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]), n = Math.max(1, Math.ceil(d / pas));
  for (let i = 0; i <= n; i++) {
    const u = i / n, p = [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u];
    const v = verifier(salle, p, ctx);
    if (!v.ok) return { ...v, ok: false, point: p, fraction: u };
  }
  return { ok: true, motif: "" };
}

/* Point de repère nommé ou coordonnées explicites → [x, y, z]. */
export function point(salle, cible) {
  if (Array.isArray(cible) && cible.length === 3 && cible.every((v) => typeof v === "number")) return cible.slice();
  if (typeof cible === "string" && salle.reperes[cible]) return salle.reperes[cible].slice();
  throw new Error(`Repère inconnu : ${JSON.stringify(cible)}`);
}
