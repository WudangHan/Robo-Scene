/* Robo-Scène — sol praticable du chien de scène (zones au sol).
   Module pur, sans dépendance : utilisé par le chien virtuel, par sa conduite et par les tests (Node).
   La même règle est appliquée par le pont (bridge/chien/sol.py) à partir du même fichier web/drone/salle.json
   (bloc « sol ») ; un test vérifie que les deux implantations rendent le même verdict.

   Règle, pour la position (x, z) du centre du robot :
     1. les neuf points du carré de demi-côté « rayon » qui entoure le robot sont tous sur une surface praticable
        ouverte par le mode (plateau ; escaliers, avant-salle, allées) : le robot ne peut ni s'approcher du nez de
        scène, ni de la fosse, ni des rangées, sauf par les escaliers ;
     2. aucun de ces points n'est dans un obstacle au sol (cadre de scène, éléments de décor déclarés) ;
     3. en représentation, le centre reste à plus de « rayon + marge du public » de chaque bloc de sièges ;
     4. le centre reste hors du cercle de chaque interprète déclaré. */

const DANS = (b, x, z) => x >= b.x[0] && x <= b.x[1] && z >= b.z[0] && z <= b.z[1];
const DIST_RECT = (b, x, z) => Math.hypot(Math.max(b.x[0] - x, 0, x - b.x[1]), Math.max(b.z[0] - z, 0, z - b.z[1]));

export function surfaceDe(salle, x, z, mode = "plateau") {
  const S = salle.sol, ids = (S.modes[mode] || S.modes.plateau).surfaces;
  for (const id of ids) { const s = S.surfaces.find((u) => u.id === id); if (s && DANS(s, x, z)) return s; }
  return null;
}

/* Hauteur du sol sous (x, z) : interpolation de y0 (bord z0) à y1 (bord z1) ; null hors des surfaces. */
export function hauteurSol(salle, x, z, mode = "salle_vide") {
  const s = surfaceDe(salle, x, z, mode);
  if (!s) return null;
  const u = (z - s.z[0]) / (s.z[1] - s.z[0]);
  return s.y0 + (s.y1 - s.y0) * u;
}

export function vitesseMax(salle, x, z, mode = "plateau") {
  const R = salle.sol.regles, s = surfaceDe(salle, x, z, mode);
  let v = Math.min(R.vitesse_max_m_s, s ? s.vitesse_max_m_s : R.vitesse_max_m_s);
  if (mode === "representation" && s && s.id !== "plateau") v = Math.min(v, R.vitesse_max_representation_m_s);
  return v;
}

export function verifierSol(salle, p, ctx = {}) {
  const S = salle.sol, R = S.regles, mode = ctx.mode && S.modes[ctx.mode] ? ctx.mode : "plateau";
  if (!Array.isArray(p) || p.length < 2 || !Number.isFinite(p[0]) || !Number.isFinite(p[1])) return { ok: false, motif: "Position invalide", surface: null };
  const [x, z] = p, r = R.rayon_m;
  const s = surfaceDe(salle, x, z, mode);
  if (!s) return { ok: false, motif: "Hors du sol praticable dans ce mode", surface: null };
  for (const dx of [-r, 0, r]) for (const dz of [-r, 0, r]) {
    if (!surfaceDe(salle, x + dx, z + dz, mode)) return { ok: false, motif: `Trop près d'un bord (nez de scène, fosse, rangées) — rayon ${r} m`, surface: s.id };
  }
  const obstacles = S.obstacles.map((id) => salle.obstacles.find((o) => o.id === id)).filter(Boolean).concat(S.decor || []);
  for (const o of obstacles) {
    for (const dx of [-r, 0, r]) for (const dz of [-r, 0, r]) {
      if (DANS(o, x + dx, z + dz)) return { ok: false, motif: `Trop près : ${o.libelle}`, surface: s.id, obstacle: o.id };
    }
  }
  if (S.modes[mode].public === "marge") {
    for (const b of salle.public) {
      if (DIST_RECT(b, x, z) < r + R.marge_public_m) return { ok: false, motif: `Trop près du public : ${b.libelle} (marge ${R.marge_public_m} m)`, surface: s.id, public: b.id };
    }
  }
  for (const [i, it] of (ctx.interpretes || []).entries()) {
    const ix = Array.isArray(it) ? it[0] : it.x, iz = Array.isArray(it) ? it[1] : it.z;
    if (Math.hypot(x - ix, z - iz) < R.rayon_interpretes_m) return { ok: false, motif: `Trop près de l'interprète ${i + 1} (${R.rayon_interpretes_m} m)`, surface: s.id };
  }
  return { ok: true, motif: "", surface: s.id };
}

export function verifierTrajet(salle, a, b, ctx = {}, pas = 0.05) {
  const d = Math.hypot(b[0] - a[0], b[1] - a[1]), n = Math.max(1, Math.ceil(d / pas));
  for (let i = 0; i <= n; i++) {
    const u = i / n, p = [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u];
    const v = verifierSol(salle, p, ctx);
    if (!v.ok) return { ...v, point: p, fraction: u };
  }
  return { ok: true, motif: "" };
}

export function pointSol(salle, cible) {
  if (Array.isArray(cible) && cible.length === 2 && cible.every((v) => typeof v === "number")) return cible.slice();
  if (typeof cible === "string" && salle.sol.reperes[cible]) return salle.sol.reperes[cible].slice();
  throw new Error(`Repère inconnu : ${JSON.stringify(cible)}`);
}
