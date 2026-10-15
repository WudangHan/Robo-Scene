/* Robo-Scène — répertoire émotionnel du robot virtuel.
   • Visage : prototypes en unités d'action du Facial Action Coding System (Ekman, Friesen et Hager) :
     joie 6+12 ; tristesse 1+4+15 ; surprise 1+2+5+26 ; peur 1+2+4+5+7+20+26 ; colère 4+5+7+23 ;
     dégoût 9+15+17 ; mépris 12+14 unilatéraux. Les états non prototypiques du répertoire
     théâtral (tendresse, ironie, lassitude, assurance) sont des compositions de conception,
     signalées comme telles dans le guide.
   • Corps : postures inspirées des observations de Wallbott (1998) sur l'expression corporelle
     (affaissement de la tristesse, expansion de la joie et de la fierté, recul de la peur).
   • Effort (Laban) et prosodie : valeurs identiques à bridge/partenaire/variations.py, pour que
     la voix et le geste du robot virtuel suivent les mêmes variations que le partenaire. */

export const EMOTIONS = {
  neutre:    { au: {}, posture: {}, effort: [0, 0, 0, 0], prosodie: [0, 0, 0, 0], regard: null },
  "colère":  { au: { au4: 1, au5: 0.6, au7: 0.7, au23: 0.8, au24: 0.4, au17: 0.3 },
               posture: { "tronc.flexion": 8, "tete.flexion": 6, "epaule_g.haussement": 8, "epaule_d.haussement": 8,
                          "epaule_g.abduction": 12, "epaule_d.abduction": 12, "coude_g.flexion": 35, "coude_d.flexion": 35,
                          "main_g.fermeture": 90, "main_d.fermeture": 90 },
               effort: [0.9, 0.7, 0.8, 0.7], prosodie: [0.18, 0.12, 0.30, -0.35], regard: "public" },
  joie:      { au: { au6: 0.8, au12: 1, au25: 0.35 },
               posture: { "tete.flexion": -8, "tronc.flexion": -4, "epaule_g.abduction": 10, "epaule_d.abduction": 10,
                          "coude_g.flexion": 15, "coude_d.flexion": 15 },
               effort: [-0.5, 0.6, -0.4, -0.7], prosodie: [0.15, 0.18, 0.15, -0.2], regard: "public" },
  tristesse: { au: { au1: 0.85, au4: 0.5, au15: 0.8, au17: 0.35, au43: 0.3 },
               posture: { "tete.flexion": 22, "tronc.flexion": 12, "epaule_g.rotation": 12, "epaule_d.rotation": 12,
                          "epaule_g.flexion": 5, "epaule_d.flexion": 5, "coude_g.flexion": 10, "coude_d.flexion": 10, "bassin.abaissement": 2 },
               effort: [-0.2, -0.8, -0.4, 0.2], prosodie: [-0.28, -0.15, -0.30, 0.7], regard: "bas" },
  peur:      { au: { au1: 0.9, au2: 0.8, au4: 0.5, au5: 1, au7: 0.3, au20: 0.8, au26: 0.5, au25: 0.6 },
               posture: { "tronc.flexion": -6, "tete.flexion": 5, "epaule_g.haussement": 20, "epaule_d.haussement": 20,
                          "epaule_g.flexion": 30, "epaule_d.flexion": 30, "coude_g.flexion": 75, "coude_d.flexion": 75,
                          "epaule_g.rotation": 25, "epaule_d.rotation": 25, "main_g.fermeture": 30, "main_d.fermeture": 30 },
               effort: [-0.6, 0.8, -0.6, 0.9], prosodie: [0.12, 0.20, -0.15, 0.3], regard: "public" },
  tendresse: { au: { au12: 0.45, au6: 0.3, au43: 0.2, au1: 0.2 },
               posture: { "tete.inclinaison": 12, "tete.flexion": 6, "epaule_g.abduction": 5, "epaule_d.abduction": 5, "coude_g.flexion": 20, "coude_d.flexion": 20 },
               effort: [-0.8, -0.7, -0.5, -0.6], prosodie: [-0.15, 0.05, -0.25, 0.3], regard: "public" },
  "mépris":  { au: { au12_d: 0.6, au14_d: 0.8, au2_d: 0.3 },
               posture: { "tete.flexion": -12, "tete.inclinaison": 6, "tronc.rotation": -10, "tronc.flexion": -4 },
               effort: [0.5, -0.4, 0.8, 0.6], prosodie: [-0.10, -0.08, 0.05, 0.2], regard: "public" },
  surprise:  { au: { au1: 1, au2: 1, au5: 0.8, au26: 0.75, au25: 0.8 },
               posture: { "tete.flexion": -10, "tronc.flexion": -5, "epaule_g.abduction": 15, "epaule_d.abduction": 15,
                          "coude_g.flexion": 35, "coude_d.flexion": 35, "main_g.fermeture": 0, "main_d.fermeture": 0 },
               effort: [-0.3, 0.9, 0.7, -0.2], prosodie: [0.10, 0.25, 0.15, 0.1], regard: "public" },
  ironie:    { au: { au12_g: 0.55, au14_g: 0.3, au2_g: 0.6 },
               posture: { "tete.inclinaison": -8, "tete.flexion": -4, "tronc.rotation": 8 },
               effort: [-0.6, 0.3, -0.7, -0.4], prosodie: [0.05, 0.10, 0.0, 0.25], regard: "gauche" },
  lassitude: { au: { au43: 0.45, au1: 0.3, au15: 0.3 },
               posture: { "tete.flexion": 15, "tronc.flexion": 10, "tronc.inclinaison": 4, "epaule_g.rotation": 8, "epaule_d.rotation": 8 },
               effort: [-0.1, -0.9, -0.6, -0.5], prosodie: [-0.25, -0.12, -0.20, 0.5], regard: "bas" },
  assurance: { au: { au12: 0.3, au6: 0.1, au24: 0.2 },
               posture: { "tete.flexion": -10, "tronc.flexion": -6, "epaule_g.abduction": 8, "epaule_d.abduction": 8,
                          "epaule_g.rotation": -12, "epaule_d.rotation": -12 },
               effort: [0.7, -0.5, 0.9, -0.2], prosodie: [-0.05, -0.05, 0.20, 0.15], regard: "public" },
  "dégoût":  { au: { au9: 0.9, au10: 0.5, au15: 0.5, au17: 0.5, au4: 0.3 },
               posture: { "tete.rotation": 15, "tete.flexion": -5, "tronc.flexion": -8, "epaule_d.flexion": 15, "coude_d.flexion": 50, "poignet_d.flexion": -30 },
               effort: [0.2, 0.5, 0.3, 0.6], prosodie: [-0.05, -0.05, 0.05, 0.3], regard: "droite" },
};

/* Gestes : suites d'images clés {t: secondes depuis le début, p: pose partielle, au: visage}.
   « X » est remplacé par le côté (g ou d) ; « Y » par le côté opposé. */
export const GESTES = {
  saluer: (r) => [
    { t: 0, p: { "epaule_X.abduction": 105, "epaule_X.flexion": 20, "coude_X.flexion": 80, "epaule_X.rotation": -75, "main_X.fermeture": 0 }, au: { au12: 0.6, au6: 0.4 } },
    ...Array.from({ length: 3 * r }, (_, i) => ({ t: 0.55 + i * 0.32, p: { "epaule_X.rotation": i % 2 ? -60 : -88 } })),
    { t: 0.55 + 3 * r * 0.32 + 0.2, p: { "epaule_X.abduction": 0, "epaule_X.flexion": 0, "coude_X.flexion": 5, "epaule_X.rotation": 0 }, fin: true },
  ],
  reverence: () => [
    { t: 0, p: { "epaule_d.flexion": 35, "epaule_d.rotation": 70, "coude_d.flexion": 95, "epaule_g.abduction": 20 } },
    { t: 0.5, p: { "tronc.flexion": 48, "tete.flexion": 18 } },
    { t: 1.9, p: { "tronc.flexion": 0, "tete.flexion": 0, "epaule_d.flexion": 0, "epaule_d.rotation": 0, "coude_d.flexion": 5, "epaule_g.abduction": 0 }, fin: true },
  ],
  hocher: (r) => [
    ...Array.from({ length: 2 * r }, (_, i) => ({ t: i * 0.28, p: { "tete.flexion": i % 2 ? -4 : 16 } })),
    { t: 2 * r * 0.28, p: { "tete.flexion": 0 }, fin: true },
  ],
  non: (r) => [
    ...Array.from({ length: 4 * r }, (_, i) => ({ t: i * 0.26, p: { "tete.rotation": i % 2 ? -22 : 22 } })),
    { t: 4 * r * 0.26, p: { "tete.rotation": 0 }, fin: true },
  ],
  hausser_epaules: () => [
    { t: 0, p: { "epaule_g.haussement": 22, "epaule_d.haussement": 22, "coude_g.flexion": 75, "coude_d.flexion": 75,
                 "epaule_g.rotation": -45, "epaule_d.rotation": -45, "epaule_g.abduction": 18, "epaule_d.abduction": 18, "tete.inclinaison": 10,
                 "main_g.fermeture": 0, "main_d.fermeture": 0 }, au: { au1: 0.6, au2: 0.7, au15: 0.4, au17: 0.4 } },
    { t: 1.2, p: { "epaule_g.haussement": 0, "epaule_d.haussement": 0, "coude_g.flexion": 5, "coude_d.flexion": 5, "epaule_g.rotation": 0,
                   "epaule_d.rotation": 0, "epaule_g.abduction": 0, "epaule_d.abduction": 0, "tete.inclinaison": 0 }, fin: true },
  ],
  croiser_bras: () => [{ t: 0, p: { "epaule_g.flexion": 42, "epaule_d.flexion": 46, "epaule_g.abduction": 14, "epaule_d.abduction": 14,
                                    "epaule_g.rotation": 72, "epaule_d.rotation": 78, "coude_g.flexion": 118, "coude_d.flexion": 112,
                                    "main_g.fermeture": 30, "main_d.fermeture": 30 } }],
  mains_hanches: () => [{ t: 0, p: { "epaule_g.abduction": 42, "epaule_d.abduction": 42, "epaule_g.rotation": 35, "epaule_d.rotation": 35,
                                     "coude_g.flexion": 105, "coude_d.flexion": 105, "epaule_g.flexion": -12, "epaule_d.flexion": -12,
                                     "main_g.fermeture": 60, "main_d.fermeture": 60 } }],
  reflechir: () => [{ t: 0, p: { "epaule_d.flexion": 40, "epaule_d.rotation": 45, "coude_d.flexion": 140, "poignet_d.flexion": -10, "main_d.fermeture": 70,
                                 "epaule_g.flexion": 25, "epaule_g.rotation": 70, "coude_g.flexion": 95, "tete.flexion": 6, "tete.inclinaison": 6 },
                      au: { au4: 0.35, au24: 0.3, au17: 0.3 }, regard: "haut" }],
  applaudir: (r) => [
    { t: 0, p: { "epaule_g.flexion": 55, "epaule_d.flexion": 55, "epaule_g.rotation": 50, "epaule_d.rotation": 50, "coude_g.flexion": 70, "coude_d.flexion": 70,
                 "epaule_g.abduction": 22, "epaule_d.abduction": 22, "main_g.fermeture": 0, "main_d.fermeture": 0 }, au: { au12: 0.7, au6: 0.5 } },
    ...Array.from({ length: 8 * r }, (_, i) => ({ t: 0.5 + i * 0.16, p: { "epaule_g.abduction": i % 2 ? 22 : 6, "epaule_d.abduction": i % 2 ? 22 : 6 } })),
    { t: 0.5 + 8 * r * 0.16 + 0.1, p: { "epaule_g.flexion": 0, "epaule_d.flexion": 0, "epaule_g.rotation": 0, "epaule_d.rotation": 0, "coude_g.flexion": 5,
                                        "coude_d.flexion": 5, "epaule_g.abduction": 0, "epaule_d.abduction": 0 }, fin: true },
  ],
  bras_ouverts: () => [{ t: 0, p: { "epaule_g.abduction": 65, "epaule_d.abduction": 65, "epaule_g.flexion": 30, "epaule_d.flexion": 30, "coude_g.flexion": 15,
                                    "coude_d.flexion": 15, "epaule_g.rotation": -30, "epaule_d.rotation": -30, "main_g.fermeture": 0, "main_d.fermeture": 0,
                                    "tete.flexion": -5 }, au: { au12: 0.6, au6: 0.4, au1: 0.2, au2: 0.3 } }],
  pointer: (r, dir) => {
    const p = { "epaule_X.flexion": 88, "coude_X.flexion": 4, "main_X.fermeture": 85, "poignet_X.flexion": -5, pointe_X: 1 };
    if (dir === "haut") p["epaule_X.flexion"] = 150;
    if (dir === "bas") p["epaule_X.flexion"] = 40;
    if (dir === "gauche" || dir === "droite") { p["epaule_X.flexion"] = 20; p["epaule_X.abduction"] = 85; }
    return [{ t: 0, p, regard: dir === "devant" ? "public" : dir }];
  },
  poing_leve: () => [{ t: 0, p: { "epaule_X.flexion": 165, "epaule_X.abduction": 15, "coude_X.flexion": 20, "main_X.fermeture": 100 }, au: { au4: 0.4, au24: 0.4 } }],
  main_coeur: () => [{ t: 0, p: { "epaule_d.flexion": 32, "epaule_d.rotation": 68, "coude_d.flexion": 118, "main_d.fermeture": 10, "tete.inclinaison": 8, "tete.flexion": 6 },
                       au: { au1: 0.4, au12: 0.3 } }],
  gratter_tete: (r) => [
    { t: 0, p: { "epaule_X.flexion": 110, "epaule_X.abduction": 55, "coude_X.flexion": 140, "main_X.fermeture": 40, "tete.inclinaison": -8 }, au: { au4: 0.3, au20: 0.3 } },
    ...Array.from({ length: 4 * r }, (_, i) => ({ t: 0.6 + i * 0.15, p: { "poignet_X.flexion": i % 2 ? 25 : -10 } })),
    { t: 0.6 + 4 * r * 0.15 + 0.2, p: { "epaule_X.flexion": 0, "epaule_X.abduction": 0, "coude_X.flexion": 5, "poignet_X.flexion": 0, "tete.inclinaison": 0 }, fin: true },
  ],
  rire: (r) => [
    { t: 0, p: { "tete.flexion": -14, "tronc.flexion": -6 }, au: { au6: 1, au12: 1, au25: 1, au26: 0.6 } },
    ...Array.from({ length: 6 * r }, (_, i) => ({ t: 0.3 + i * 0.18, p: { "epaule_g.haussement": i % 2 ? 4 : 12, "epaule_d.haussement": i % 2 ? 4 : 12, "tronc.flexion": i % 2 ? -6 : -2 },
                                                   au: { au26: i % 2 ? 0.3 : 0.75 } })),
    { t: 0.3 + 6 * r * 0.18 + 0.3, p: { "tete.flexion": 0, "tronc.flexion": 0, "epaule_g.haussement": 0, "epaule_d.haussement": 0 }, au: { au6: 0.5, au12: 0.6, au25: 0.2, au26: 0 }, fin: true },
  ],
  pleurer: (r) => [
    { t: 0, p: { "tete.flexion": 28, "tronc.flexion": 15, "epaule_g.flexion": 72, "epaule_d.flexion": 72, "epaule_g.rotation": 35, "epaule_d.rotation": 35,
                 "coude_g.flexion": 140, "coude_d.flexion": 140, "main_g.fermeture": 20, "main_d.fermeture": 20 }, au: { au1: 1, au4: 0.7, au15: 1, au17: 0.6, au43: 0.6 } },
    ...Array.from({ length: 5 * r }, (_, i) => ({ t: 0.6 + i * 0.4, p: { "epaule_g.haussement": i % 2 ? 3 : 10, "epaule_d.haussement": i % 2 ? 3 : 10 } })),
  ],
  soupirer: () => [
    { t: 0, p: { "tronc.flexion": -5, "epaule_g.haussement": 12, "epaule_d.haussement": 12, "tete.flexion": -6 }, au: { au25: 0.4 }, souffle: 1 },
    { t: 1.0, p: { "tronc.flexion": 6, "epaule_g.haussement": 0, "epaule_d.haussement": 0, "tete.flexion": 10 }, au: { au43: 0.4, au25: 0.25 }, souffle: -1 },
    { t: 2.4, p: { "tronc.flexion": 0, "tete.flexion": 0 }, au: { au43: 0, au25: 0 }, fin: true },
  ],
  clin_oeil: () => [{ t: 0, au: { au46_d: 1, au12_d: 0.5, au6: 0.2 } }, { t: 0.35, au: { au46_d: 0, au12_d: 0.15 }, fin: true }],
  danser: (r) => Array.from({ length: 8 * r }, (_, i) => ({
    t: i * 0.45,
    p: { "tronc.inclinaison": i % 2 ? 10 : -10, "tete.inclinaison": i % 2 ? -8 : 8, "epaule_g.abduction": i % 2 ? 40 : 20, "epaule_d.abduction": i % 2 ? 20 : 40,
         "coude_g.flexion": 70, "coude_d.flexion": 70, "genou_g.flexion": i % 2 ? 20 : 0, "genou_d.flexion": i % 2 ? 0 : 20, "bassin.abaissement": 4 },
    au: { au12: 0.7, au6: 0.5 },
  })).concat([{ t: 8 * r * 0.45, p: { "tronc.inclinaison": 0, "tete.inclinaison": 0, "epaule_g.abduction": 0, "epaule_d.abduction": 0, "coude_g.flexion": 5, "coude_d.flexion": 5,
                                     "genou_g.flexion": 0, "genou_d.flexion": 0, "bassin.abaissement": 0 }, fin: true }]),
  taper_pied: (r) => [
    ...Array.from({ length: 4 * r }, (_, i) => ({ t: i * 0.3, p: { "cheville_X.flexion": i % 2 ? 0 : -28 } })),
    { t: 4 * r * 0.3, p: { "cheville_X.flexion": 0 }, fin: true },
  ],
  cacher_visage: () => [{ t: 0, p: { "epaule_g.flexion": 80, "epaule_d.flexion": 80, "epaule_g.rotation": 40, "epaule_d.rotation": 40, "coude_g.flexion": 145,
                                     "coude_d.flexion": 145, "tete.flexion": 20, "tronc.flexion": 10, "main_g.fermeture": 0, "main_d.fermeture": 0 }, au: { au43: 1 } }],
  etirer: () => [
    { t: 0, p: { "epaule_g.flexion": 175, "epaule_d.flexion": 175, "coude_g.flexion": 0, "coude_d.flexion": 0, "tete.flexion": -15, "tronc.flexion": -10,
                 "cheville_g.flexion": 20, "cheville_d.flexion": 20, "main_g.fermeture": 0, "main_d.fermeture": 0 }, au: { au43: 0.7, au26: 0.6, au25: 1 } },
    { t: 1.8, p: { "epaule_g.flexion": 0, "epaule_d.flexion": 0, "coude_g.flexion": 5, "coude_d.flexion": 5, "tete.flexion": 0, "tronc.flexion": 0,
                   "cheville_g.flexion": 0, "cheville_d.flexion": 0 }, au: { au43: 0, au26: 0, au25: 0 }, fin: true },
  ],
  respirer: () => [
    { t: 0, p: { "tronc.flexion": -6, "epaule_g.haussement": 10, "epaule_d.haussement": 10, "tete.flexion": -5 }, au: { au43: 0.5 }, souffle: 1 },
    { t: 2.2, p: { "tronc.flexion": 0, "epaule_g.haussement": 0, "epaule_d.haussement": 0, "tete.flexion": 0 }, au: { au43: 0 }, souffle: -1, fin: true },
  ],
  marcher_sur_place: (r) => Array.from({ length: 8 * r }, (_, i) => ({
    t: i * 0.42,
    p: { "hanche_g.flexion": i % 2 ? 0 : 40, "genou_g.flexion": i % 2 ? 0 : 60, "hanche_d.flexion": i % 2 ? 40 : 0, "genou_d.flexion": i % 2 ? 60 : 0,
         "epaule_g.flexion": i % 2 ? 22 : -18, "epaule_d.flexion": i % 2 ? -18 : 22, "coude_g.flexion": 25, "coude_d.flexion": 25 },
  })).concat([{ t: 8 * r * 0.42, p: { "hanche_g.flexion": 0, "genou_g.flexion": 0, "hanche_d.flexion": 0, "genou_d.flexion": 0, "epaule_g.flexion": 0,
                                       "epaule_d.flexion": 0, "coude_g.flexion": 5, "coude_d.flexion": 5 }, fin: true }]),
};

/* Poses de corps entier (le tabouret apparaît pour « assis »). */
export const POSES = {
  repos: {},
  debout: {},
  garde_a_vous: { "epaule_g.abduction": -4, "epaule_d.abduction": -4, "tete.flexion": -3, "tronc.flexion": -3, "main_g.fermeture": 20, "main_d.fermeture": 20 },
  assis: { "bassin.abaissement": 46, "hanche_g.flexion": 88, "hanche_d.flexion": 88, "genou_g.flexion": 88, "genou_d.flexion": 88, "tronc.flexion": 6,
           "epaule_g.flexion": 25, "epaule_d.flexion": 25, "coude_g.flexion": 55, "coude_d.flexion": 55, "hanche_g.abduction": 8, "hanche_d.abduction": 8 },
  accroupi: { "bassin.abaissement": 52, "hanche_g.flexion": 118, "hanche_d.flexion": 118, "genou_g.flexion": 135, "genou_d.flexion": 135,
              "cheville_g.flexion": -30, "cheville_d.flexion": -30, "tronc.flexion": 28, "epaule_g.flexion": 45, "epaule_d.flexion": 45,
              "coude_g.flexion": 40, "coude_d.flexion": 40, "hanche_g.abduction": 14, "hanche_d.abduction": 14 },
  a_genoux: { "bassin.abaissement": 49, "hanche_g.flexion": 2, "hanche_d.flexion": 2, "genou_g.flexion": 90, "genou_d.flexion": 90,
              "cheville_g.flexion": 40, "cheville_d.flexion": 40, "tronc.flexion": 4 },
  recroqueville: { "tete.flexion": 35, "tronc.flexion": 30, "epaule_g.flexion": 60, "epaule_d.flexion": 60, "epaule_g.rotation": 55, "epaule_d.rotation": 55,
                   "coude_g.flexion": 120, "coude_d.flexion": 120, "epaule_g.haussement": 18, "epaule_d.haussement": 18, "bassin.abaissement": 6,
                   "genou_g.flexion": 15, "genou_d.flexion": 15, "hanche_g.flexion": 10, "hanche_d.flexion": 10 },
};

/* Voix : même arithmétique que rendu_voix (régime humain, style réaliste) pour l'intensité k = i/10. */
export function prosodie(nom, intensite) {
  const e = EMOTIONS[nom] || EMOTIONS.neutre;
  const k = (intensite ?? 7) / 10;
  const [d, h, v] = e.prosodie.map((x) => x * k);
  return {
    debit: Math.min(1.6, Math.max(0.6, 1 + d)),
    hauteur: Math.min(1.6, Math.max(0.4, 1 + h)),
    volume: Math.min(1, Math.max(0.15, 0.8 + v)),
    pause: e.prosodie[3] * k,
  };
}
