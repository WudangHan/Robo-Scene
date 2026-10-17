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
  reflechir: () => [{ t: 0, p: { "epaule_d.flexion": 88, "epaule_d.abduction": 4, "epaule_d.rotation": 54, "coude_d.flexion": 126, "poignet_d.flexion": 8, "main_d.fermeture": 70,
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
    { t: 0, p: { "epaule_X.flexion": 104, "epaule_X.abduction": 26, "epaule_X.rotation": -11, "coude_X.flexion": 115, "poignet_X.flexion": -12, "main_X.fermeture": 40, "tete.inclinaison": -8 }, au: { au4: 0.3, au20: 0.3 } },
    ...Array.from({ length: 4 * r }, (_, i) => ({ t: 0.6 + i * 0.15, p: { "poignet_X.flexion": i % 2 ? 25 : -10 } })),
    { t: 0.6 + 4 * r * 0.15 + 0.2, p: { "epaule_X.flexion": 0, "epaule_X.abduction": 0, "epaule_X.rotation": 0, "coude_X.flexion": 5, "poignet_X.flexion": 0, "tete.inclinaison": 0 }, fin: true },
  ],
  rire: (r) => [
    { t: 0, p: { "tete.flexion": -14, "tronc.flexion": -6 }, au: { au6: 1, au12: 1, au25: 1, au26: 0.6 } },
    ...Array.from({ length: 6 * r }, (_, i) => ({ t: 0.3 + i * 0.18, p: { "epaule_g.haussement": i % 2 ? 4 : 12, "epaule_d.haussement": i % 2 ? 4 : 12, "tronc.flexion": i % 2 ? -6 : -2 },
                                                   au: { au26: i % 2 ? 0.3 : 0.75 } })),
    { t: 0.3 + 6 * r * 0.18 + 0.3, p: { "tete.flexion": 0, "tronc.flexion": 0, "epaule_g.haussement": 0, "epaule_d.haussement": 0 }, au: { au6: 0.5, au12: 0.6, au25: 0.2, au26: 0 }, fin: true },
  ],
  pleurer: (r) => [
    { t: 0, p: { "tete.flexion": 28, "tronc.flexion": 15, "epaule_g.flexion": 65, "epaule_g.abduction": 8, "epaule_g.rotation": 25, "coude_g.flexion": 122, "poignet_g.flexion": 16, "epaule_d.flexion": 65, "epaule_d.abduction": 8, "epaule_d.rotation": 25, "coude_d.flexion": 122, "poignet_d.flexion": 16, "main_g.fermeture": 20, "main_d.fermeture": 20 }, au: { au1: 1, au4: 0.7, au15: 1, au17: 0.6, au43: 0.6 } },
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
  cacher_visage: () => [{ t: 0, p: { "epaule_g.flexion": 82, "epaule_g.abduction": -6, "epaule_g.rotation": 43, "coude_g.flexion": 111, "poignet_g.flexion": -22, "epaule_d.flexion": 82, "epaule_d.abduction": -6, "epaule_d.rotation": 43, "coude_d.flexion": 111, "poignet_d.flexion": -22, "tete.flexion": 20, "tronc.flexion": 10, "main_g.fermeture": 0, "main_d.fermeture": 0 }, au: { au43: 1 } }],
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

/* ── Répertoire élargi (version 2.2) ─────────────────────────────────────────────
   Gestes du quotidien, de la scène et du combat de théâtre ; « X » = côté choisi. */
const osc = (n, pas, t0, a, b) => Array.from({ length: n }, (_, i) => ({ t: t0 + i * pas, p: i % 2 ? b : a }));
const finDe = (t, au) => ({ t, p: {}, fin: true, ...(au ? { au } : {}) });
Object.assign(GESTES, {
  salut_militaire: () => [
    { t: 0, p: { "epaule_X.flexion": 91, "epaule_X.abduction": -2, "epaule_X.rotation": 4, "coude_X.flexion": 118, "poignet_X.flexion": 34, "main_X.fermeture": 0, "tete.flexion": -4 } },
    finDe(1.9)],
  bras_au_ciel: () => [
    { t: 0, p: { "epaule_g.flexion": 165, "epaule_d.flexion": 165, "epaule_g.abduction": 25, "epaule_d.abduction": 25, "coude_g.flexion": 10, "coude_d.flexion": 10,
                 "main_g.fermeture": 0, "main_d.fermeture": 0, "tete.flexion": -15 }, au: { au6: 0.8, au12: 1, au25: 0.8, au26: 0.4 } },
    finDe(2.2, {})],
  mains_jointes: () => [{ t: 0, p: { "epaule_g.flexion": 45, "epaule_d.flexion": 45, "epaule_g.rotation": 65, "epaule_d.rotation": 65, "coude_g.flexion": 115,
                                     "coude_d.flexion": 115, "main_g.fermeture": 10, "main_d.fermeture": 10, "poignet_g.flexion": -20, "poignet_d.flexion": -20, "tete.flexion": 10 },
                          au: { au1: 0.5, au43: 0.3 } }],
  signe_venir: (r) => [
    { t: 0, p: { "epaule_X.flexion": 70, "epaule_X.rotation": -60, "coude_X.flexion": 30, "main_X.fermeture": 30 }, au: { au12: 0.4, au2: 0.3 } },
    ...osc(4 * r, 0.3, 0.45, { "coude_X.flexion": 95, "main_X.fermeture": 70 }, { "coude_X.flexion": 35, "main_X.fermeture": 20 }), finDe(0.6 + 1.2 * r)],
  chasser: (r) => [
    { t: 0, p: { "epaule_X.flexion": 40, "epaule_X.abduction": 10, "epaule_X.rotation": 30, "coude_X.flexion": 90, "main_X.fermeture": 0, "tete.rotation": 25 }, au: { au9: 0.4, au4: 0.4 } },
    ...osc(3 * r, 0.3, 0.4, { "epaule_X.abduction": 45, "poignet_X.flexion": -40 }, { "epaule_X.abduction": 10, "poignet_X.flexion": 20 }), finDe(0.6 + 0.9 * r, {})],
  chut: () => [{ t: 0, p: { "epaule_d.flexion": 68, "epaule_d.abduction": -10, "epaule_d.rotation": 57, "coude_d.flexion": 123, "poignet_d.flexion": -26, "main_d.fermeture": 75, pointe_d: 1 }, au: { au18: 0.7, au2: 0.3 } }, finDe(2.0, {})],
  mains_dos: () => [{ t: 0, p: { "epaule_g.flexion": -30, "epaule_d.flexion": -30, "epaule_g.abduction": 5, "epaule_d.abduction": 5, "epaule_g.rotation": 40, "epaule_d.rotation": 40,
                                 "coude_g.flexion": 70, "coude_d.flexion": 70, "tete.flexion": -4 } }],
  pouce_leve: () => [{ t: 0, p: { "epaule_X.flexion": 60, "coude_X.flexion": 80, "epaule_X.rotation": -20, "main_X.fermeture": 100 }, au: { au12: 0.7, au6: 0.4 } }, finDe(1.6, {})],
  se_designer: () => [{ t: 0, p: { "epaule_d.flexion": 35, "epaule_d.rotation": 70, "coude_d.flexion": 120, "main_d.fermeture": 80, pointe_d: 1, "tete.flexion": 10 }, au: { au1: 0.5, au2: 0.5 } }, finDe(1.6, {})],
  tete_mains: () => [{ t: 0, p: { "epaule_g.flexion": 105, "epaule_g.abduction": 64, "epaule_g.rotation": -63, "coude_g.flexion": 117, "poignet_g.flexion": 32, "epaule_d.flexion": 105, "epaule_d.abduction": 64, "epaule_d.rotation": -63, "coude_d.flexion": 117, "poignet_d.flexion": 32, "tete.flexion": 22, "tronc.flexion": 15 }, au: { au1: 0.8, au4: 0.6, au15: 0.7, au43: 0.5 } }],
  frapper_porte: (r) => [
    { t: 0, p: { "epaule_d.flexion": 75, "epaule_d.rotation": 10, "coude_d.flexion": 100, "main_d.fermeture": 100 } },
    ...osc(6 * r, 0.18, 0.45, { "coude_d.flexion": 80 }, { "coude_d.flexion": 100 }), finDe(0.6 + 1.1 * r)],
  boire: () => [
    { t: 0, p: { "epaule_d.flexion": 105, "epaule_d.abduction": -4, "epaule_d.rotation": 53, "coude_d.flexion": 107, "poignet_d.flexion": -20, "main_d.fermeture": 60 } },
    { t: 0.8, p: { "tete.flexion": -22, "poignet_d.flexion": -57 }, au: { au18: 0.5 } }, finDe(2.3, {})],
  telephoner: () => [{ t: 0, p: { "epaule_d.flexion": 97, "epaule_d.abduction": 5, "epaule_d.rotation": 12, "coude_d.flexion": 132, "poignet_d.flexion": -9, "main_d.fermeture": 70, "tete.inclinaison": -10 } }, finDe(3.5)],
  ecrire: (r) => [
    { t: 0, p: { "epaule_g.flexion": 45, "coude_g.flexion": 100, "epaule_g.rotation": 40, "main_g.fermeture": 0, "epaule_d.flexion": 50, "coude_d.flexion": 95,
                 "epaule_d.rotation": 35, "main_d.fermeture": 80, "tete.flexion": 25 }, regard: "bas" },
    ...osc(8 * r, 0.22, 0.6, { "poignet_d.flexion": 15 }, { "poignet_d.flexion": -15 }), { t: 0.8 + 1.8 * r, p: {}, fin: true, regard: "public" }],
  lire: () => [{ t: 0, p: { "epaule_g.flexion": 40, "epaule_d.flexion": 40, "coude_g.flexion": 110, "coude_d.flexion": 110, "epaule_g.rotation": 30, "epaule_d.rotation": 30,
                            "main_g.fermeture": 20, "main_d.fermeture": 20, "poignet_g.flexion": -30, "poignet_d.flexion": -30, "tete.flexion": 25 }, regard: "bas" },
               { t: 3.5, p: {}, fin: true, regard: "public" }],
  montre: () => [{ t: 0, p: { "epaule_g.flexion": 55, "coude_g.flexion": 120, "epaule_g.rotation": 70, "poignet_g.flexion": 10, "tete.flexion": 20, "tete.rotation": 10 }, regard: "bas" },
                 { t: 1.8, p: {}, fin: true, regard: "public" }],
  essuyer_front: () => [
    { t: 0, p: { "epaule_d.flexion": 114, "epaule_d.abduction": -10, "epaule_d.rotation": 49, "coude_d.flexion": 94, "poignet_d.flexion": -35, "main_d.fermeture": 20 }, au: { au43: 0.3, au25: 0.3 } },
    { t: 0.6, p: { "epaule_d.flexion": 106, "epaule_d.abduction": -10, "epaule_d.rotation": 25, "coude_d.flexion": 107, "poignet_d.flexion": 10 } }, { t: 1.0, p: { "epaule_d.flexion": 114, "epaule_d.abduction": -10, "epaule_d.rotation": 49, "coude_d.flexion": 94, "poignet_d.flexion": -35 } }, finDe(1.6, {})],
  bailler: () => [{ t: 0, p: { "epaule_d.flexion": 98, "epaule_d.abduction": 21, "epaule_d.rotation": 18, "coude_d.flexion": 109, "poignet_d.flexion": -5, "tete.flexion": -12, "tronc.flexion": -5 }, au: { au26: 1, au25: 1, au43: 0.7 } },
                  finDe(2.2, {})],
  frotter_yeux: (r) => [
    { t: 0, p: { "epaule_g.flexion": 97, "epaule_g.abduction": 60, "epaule_g.rotation": -32, "coude_g.flexion": 108, "poignet_g.flexion": -7, "epaule_d.flexion": 97, "epaule_d.abduction": 60, "epaule_d.rotation": -32, "coude_d.flexion": 108, "poignet_d.flexion": -7, "main_g.fermeture": 60, "main_d.fermeture": 60 }, au: { au43: 1 } },
    ...osc(6 * r, 0.2, 0.5, { "poignet_g.flexion": 3, "poignet_d.flexion": -17 }, { "poignet_g.flexion": -17, "poignet_d.flexion": 3 }), finDe(0.7 + 1.2 * r, {})],
  sauter: (r) => Array.from({ length: r }, (_, k) => [
    { t: k * 1.0, p: { "bassin.abaissement": 12, "hanche_g.flexion": 35, "hanche_d.flexion": 35, "genou_g.flexion": 55, "genou_d.flexion": 55, "cheville_g.flexion": -15, "cheville_d.flexion": -15,
                       "epaule_g.flexion": -25, "epaule_d.flexion": -25, "tronc.flexion": 12 } },
    { t: k * 1.0 + 0.32, p: { "bassin.abaissement": 0, "bassin.elevation": 28, "hanche_g.flexion": 5, "hanche_d.flexion": 5, "genou_g.flexion": 10, "genou_d.flexion": 10,
                              "cheville_g.flexion": 35, "cheville_d.flexion": 35, "epaule_g.flexion": 140, "epaule_d.flexion": 140, "tronc.flexion": -4 }, au: { au12: 0.6, au26: 0.3 } },
    { t: k * 1.0 + 0.62, p: { "bassin.elevation": 0, "bassin.abaissement": 10, "genou_g.flexion": 45, "genou_d.flexion": 45, "hanche_g.flexion": 30, "hanche_d.flexion": 30,
                              "cheville_g.flexion": -10, "cheville_d.flexion": -10, "epaule_g.flexion": 30, "epaule_d.flexion": 30 } },
  ]).flat().concat([finDe(r * 1.0 + 0.3, {})]),
  sautiller: (r) => [...osc(8 * r, 0.26, 0, { "bassin.elevation": 9, "cheville_g.flexion": 30, "cheville_d.flexion": 30, "genou_g.flexion": 10, "genou_d.flexion": 10 },
                                             { "bassin.elevation": 0, "cheville_g.flexion": 0, "cheville_d.flexion": 0, "genou_g.flexion": 25, "genou_d.flexion": 25 }),
                     finDe(8 * r * 0.26 + 0.1)],
  serrer_main: (r) => [
    { t: 0, p: { "epaule_d.flexion": 50, "epaule_d.abduction": 10, "coude_d.flexion": 30, "main_d.fermeture": 40 }, au: { au12: 0.6, au6: 0.3 } },
    ...osc(4 * r, 0.22, 0.6, { "coude_d.flexion": 45 }, { "coude_d.flexion": 28 }), finDe(0.8 + 0.9 * r, {})],
  repousser: () => [{ t: 0, p: { "epaule_g.flexion": 85, "epaule_d.flexion": 85, "coude_g.flexion": 10, "coude_d.flexion": 10, "poignet_g.flexion": -60, "poignet_d.flexion": -60,
                                 "main_g.fermeture": 0, "main_d.fermeture": 0, "tronc.flexion": -8, "tete.flexion": 6 }, au: { au4: 0.5, au7: 0.4 } }, finDe(1.6, {})],
  trembler: (r) => [...osc(20 * r, 0.07, 0, { "epaule_g.haussement": 12, "epaule_d.haussement": 12, "coude_g.flexion": 40, "coude_d.flexion": 40, "tete.inclinaison": 2, "genou_g.flexion": 8 },
                                            { "epaule_g.haussement": 6, "epaule_d.haussement": 6, "coude_g.flexion": 34, "coude_d.flexion": 34, "tete.inclinaison": -2, "genou_g.flexion": 4 })
                      .map((im, i) => (i === 0 ? { ...im, au: { au1: 0.6, au20: 0.5, au25: 0.3 } } : im)), finDe(20 * r * 0.07 + 0.1, {})],
  frotter_mains: (r) => [
    { t: 0, p: { "epaule_g.flexion": 40, "epaule_d.flexion": 40, "epaule_g.rotation": 60, "epaule_d.rotation": 60, "coude_g.flexion": 95, "coude_d.flexion": 95, "main_g.fermeture": 10, "main_d.fermeture": 10 }, au: { au12: 0.6, au6: 0.3 } },
    ...osc(8 * r, 0.15, 0.5, { "epaule_g.abduction": 4, "epaule_d.abduction": 12 }, { "epaule_g.abduction": 12, "epaule_d.abduction": 4 }), finDe(0.6 + 1.2 * r, {})],
  muscles: () => [{ t: 0, p: { "epaule_g.abduction": 90, "epaule_d.abduction": 90, "epaule_g.rotation": -80, "epaule_d.rotation": -80, "coude_g.flexion": 120, "coude_d.flexion": 120,
                               "main_g.fermeture": 100, "main_d.fermeture": 100 }, au: { au4: 0.3, au12: 0.5, au24: 0.4 } }, finDe(2.2, {})],
  accolade: () => [
    { t: 0, p: { "epaule_g.abduction": 60, "epaule_d.abduction": 60, "epaule_g.flexion": 50, "epaule_d.flexion": 50, "coude_g.flexion": 40, "coude_d.flexion": 40 }, au: { au12: 0.7, au6: 0.5 } },
    { t: 0.7, p: { "epaule_g.abduction": 20, "epaule_d.abduction": 20, "epaule_g.flexion": 70, "epaule_d.flexion": 70, "epaule_g.rotation": 50, "epaule_d.rotation": 50,
                   "coude_g.flexion": 100, "coude_d.flexion": 100, "tete.inclinaison": 10 } }, finDe(2.2, {})],
  lancer: () => [
    { t: 0, p: { "epaule_d.flexion": -40, "epaule_d.abduction": 30, "coude_d.flexion": 90, "epaule_d.rotation": -40, "tronc.rotation": 25, "main_d.fermeture": 80 } },
    { t: 0.45, p: { "epaule_d.flexion": 150, "coude_d.flexion": 10, "epaule_d.rotation": 0, "tronc.rotation": -20, "main_d.fermeture": 0, "hanche_g.flexion": 15 } }, finDe(1.3)],
  ramasser: () => [
    { t: 0, p: { "tronc.flexion": 60, "bassin.abaissement": 14, "genou_g.flexion": 40, "genou_d.flexion": 40, "hanche_g.flexion": 40, "hanche_d.flexion": 40,
                 "epaule_d.flexion": 80, "coude_d.flexion": 10, "main_d.fermeture": 0, "tete.flexion": 20 }, regard: "bas" },
    { t: 1.0, p: { "main_d.fermeture": 85 } }, { t: 1.6, p: {}, fin: true, regard: "public" }],
  pousser: () => [
    { t: 0, p: { "epaule_g.flexion": 85, "epaule_d.flexion": 85, "coude_g.flexion": 70, "coude_d.flexion": 70, "poignet_g.flexion": -50, "poignet_d.flexion": -50, "main_g.fermeture": 0, "main_d.fermeture": 0 } },
    { t: 0.5, p: { "coude_g.flexion": 10, "coude_d.flexion": 10, "tronc.flexion": 15, "hanche_d.flexion": -15, "hanche_g.flexion": 25, "genou_g.flexion": 25 }, au: { au4: 0.4, au24: 0.6 } }, finDe(1.8, {})],
  tirer: () => [
    { t: 0, p: { "epaule_g.flexion": 75, "epaule_d.flexion": 75, "coude_g.flexion": 10, "coude_d.flexion": 10, "main_g.fermeture": 100, "main_d.fermeture": 100 } },
    { t: 0.5, p: { "coude_g.flexion": 100, "coude_d.flexion": 100, "tronc.flexion": -15, "hanche_g.flexion": 25, "genou_g.flexion": 30 }, au: { au4: 0.4, au24: 0.6 } }, finDe(1.8, {})],
  boxer: (r) => [
    { t: 0, p: { "epaule_g.flexion": 60, "epaule_d.flexion": 60, "epaule_g.rotation": 40, "epaule_d.rotation": 40, "coude_g.flexion": 130, "coude_d.flexion": 130,
                 "main_g.fermeture": 100, "main_d.fermeture": 100, "tete.flexion": 10 }, au: { au4: 0.7, au24: 0.6 } },
    ...Array.from({ length: 2 * r }, (_, i) => {
      const s = i % 2 ? "g" : "d";
      return [{ t: 0.4 + i * 0.6, p: { [`epaule_${s}.flexion`]: 90, [`coude_${s}.flexion`]: 5, [`epaule_${s}.rotation`]: 0, "tronc.rotation": s === "d" ? -20 : 20 } },
              { t: 0.65 + i * 0.6, p: { [`epaule_${s}.flexion`]: 60, [`coude_${s}.flexion`]: 130, [`epaule_${s}.rotation`]: 40, "tronc.rotation": 0 } }];
    }).flat(), finDe(0.5 + 1.2 * r, {})],
  coup_de_pied: () => [
    { t: 0, p: { "hanche_d.flexion": 70, "genou_d.flexion": 70, "epaule_g.abduction": 30, "epaule_d.abduction": 30, "tronc.flexion": -6 } },
    { t: 0.3, p: { "genou_d.flexion": 5, "cheville_d.flexion": 30 } }, finDe(0.9)],
  pointes_pieds: () => [{ t: 0, p: { "cheville_g.flexion": 35, "cheville_d.flexion": 35, "bassin.elevation": 8, "epaule_g.abduction": 20, "epaule_d.abduction": 20, "tete.flexion": -5 } }],
  tituber: (r) => [...Array.from({ length: 4 * r }, (_, i) => ({
    t: i * 0.55, p: { "tronc.inclinaison": i % 2 ? 14 : -14, "tete.inclinaison": i % 2 ? -10 : 10, "hanche_g.abduction": i % 2 ? 10 : 0, "hanche_d.abduction": i % 2 ? 0 : 10,
                      "epaule_g.abduction": i % 2 ? 35 : 15, "epaule_d.abduction": i % 2 ? 15 : 35, "genou_g.flexion": i % 2 ? 15 : 0 },
    ...(i === 0 ? { au: { au43: 0.4, au12_g: 0.3 } } : {}) })), finDe(4 * r * 0.55 + 0.2, {})],
  regarder_loin: () => [{ t: 0, p: { "epaule_d.flexion": 113, "epaule_d.abduction": 48, "epaule_d.rotation": -30, "coude_d.flexion": 87, "poignet_d.flexion": -3, "main_d.fermeture": 0, "tete.flexion": -5 },
                          au: { au7: 0.5 }, regard: "loin" }, { t: 2.6, p: {}, fin: true, regard: "public" }],
  eternuer: () => [
    { t: 0, p: { "tete.flexion": -20, "tronc.flexion": -8 }, au: { au43: 0.5, au25: 0.6, au9: 0.5, au1: 0.4 } },
    { t: 0.8, p: { "tete.flexion": 30, "tronc.flexion": 20, "epaule_d.flexion": 77, "epaule_d.abduction": -1, "epaule_d.rotation": 43, "coude_d.flexion": 116, "poignet_d.flexion": 22 }, au: { au43: 1, au26: 0.6, au9: 0.6 } }, finDe(1.6, {})],
  tousser: (r) => [
    { t: 0, p: { "epaule_d.flexion": 82, "epaule_d.abduction": -2, "epaule_d.rotation": 46, "coude_d.flexion": 115, "poignet_d.flexion": 4, "main_d.fermeture": 80, "tete.flexion": 15 }, au: { au43: 0.5, au4: 0.3 } },
    ...osc(3 * r, 0.28, 0.3, { "tronc.flexion": 12 }, { "tronc.flexion": 2 }), finDe(0.5 + 0.9 * r, {})],
  mains_poches: () => [{ t: 0, p: { "epaule_g.flexion": -10, "epaule_d.flexion": -10, "epaule_g.abduction": 12, "epaule_d.abduction": 12, "epaule_g.rotation": 20, "epaule_d.rotation": 20,
                                    "coude_g.flexion": 25, "coude_d.flexion": 25, "main_g.fermeture": 70, "main_d.fermeture": 70, "poignet_g.flexion": 20, "poignet_d.flexion": 20 } }],
  compter: (r) => [
    { t: 0, p: { "epaule_g.flexion": 55, "coude_g.flexion": 110, "epaule_g.rotation": 40, "main_g.fermeture": 50, "epaule_d.flexion": 55, "coude_d.flexion": 105, "epaule_d.rotation": 40,
                 "main_d.fermeture": 80, pointe_d: 1, "tete.flexion": 15 }, regard: "bas" },
    ...osc(5 * r, 0.4, 0.5, { "poignet_d.flexion": 15 }, { "poignet_d.flexion": -10 }), { t: 0.7 + 2 * r, p: {}, fin: true, regard: "public" }],
  menacer: (r) => [
    { t: 0, p: { "epaule_d.flexion": 95, "coude_d.flexion": 40, "main_d.fermeture": 85, pointe_d: 1, "tete.flexion": 8 }, au: { au4: 0.8, au24: 0.5, au7: 0.4 } },
    ...osc(4 * r, 0.25, 0.4, { "poignet_d.flexion": 25 }, { "poignet_d.flexion": -15 }), finDe(0.6 + r, {})],
  hesiter: () => [
    { t: 0, p: { "tronc.inclinaison": 8, "tete.inclinaison": 10, "epaule_d.flexion": 40, "epaule_d.rotation": 45, "coude_d.flexion": 140, "main_d.fermeture": 60 }, au: { au20: 0.3, au1: 0.4, au24: 0.3 } },
    { t: 0.9, p: { "tronc.inclinaison": -8, "tete.inclinaison": -10, "epaule_d.flexion": 20, "coude_d.flexion": 60 } },
    { t: 1.8, p: { "tronc.inclinaison": 6, "tete.inclinaison": 8, "epaule_g.haussement": 12, "epaule_d.haussement": 12 } }, finDe(2.6, {})],
  ecouter: () => [{ t: 0, p: { "epaule_d.flexion": 96, "epaule_d.abduction": -10, "epaule_d.rotation": 28, "coude_d.flexion": 132, "poignet_d.flexion": -29, "main_d.fermeture": 10, "tete.inclinaison": -15, "tete.rotation": 20 },
                    au: { au1: 0.4, au2: 0.4 }, regard: "loin" }, { t: 2.6, p: {}, fin: true, regard: "public" }],
  bercer: (r) => [
    { t: 0, p: { "epaule_g.flexion": 45, "epaule_d.flexion": 45, "epaule_g.rotation": 65, "epaule_d.rotation": 65, "coude_g.flexion": 100, "coude_d.flexion": 100,
                 "epaule_g.abduction": 10, "epaule_d.abduction": 10, "tete.flexion": 15, "tete.inclinaison": 10 }, au: { au12: 0.5, au6: 0.3 }, regard: "bas" },
    ...osc(4 * r, 0.7, 0.4, { "tronc.rotation": 10 }, { "tronc.rotation": -10 }), { t: 0.6 + 2.8 * r, p: {}, fin: true, regard: "public" }],
  dormir: () => [{ t: 0, p: { "tete.inclinaison": 25, "tete.flexion": 15, "epaule_g.flexion": 91, "epaule_g.abduction": 1, "epaule_g.rotation": 38, "coude_g.flexion": 145, "poignet_g.flexion": -32, "epaule_d.flexion": 109, "epaule_d.abduction": 40, "epaule_d.rotation": 29, "coude_d.flexion": 108, "poignet_d.flexion": -10, "main_g.fermeture": 10, "main_d.fermeture": 10, "tronc.inclinaison": 6 }, au: { au43: 1 }, souffle: 1 }],
  mimer_mur: (r) => [
    { t: 0, p: { "epaule_g.flexion": 90, "epaule_d.flexion": 90, "coude_g.flexion": 25, "coude_d.flexion": 25, "poignet_g.flexion": -70, "poignet_d.flexion": -70,
                 "main_g.fermeture": 0, "main_d.fermeture": 0, "epaule_g.abduction": 20, "epaule_d.abduction": 20 } },
    ...osc(4 * r, 0.6, 0.6, { "epaule_g.abduction": 40, "epaule_d.flexion": 110 }, { "epaule_g.abduction": 20, "epaule_d.flexion": 85, "epaule_d.abduction": 40 }), finDe(0.8 + 2.4 * r)],
});

Object.assign(POSES, {
  effondre: { "bassin.abaissement": 49, "hanche_g.flexion": 10, "hanche_d.flexion": 10, "genou_g.flexion": 90, "genou_d.flexion": 90, "cheville_g.flexion": 40, "cheville_d.flexion": 40,
              "tronc.flexion": 55, "tete.flexion": 40, "epaule_g.flexion": 10, "epaule_d.flexion": 10, "epaule_g.rotation": 20, "epaule_d.rotation": 20, "coude_g.flexion": 20,
              "coude_d.flexion": 20, "main_g.fermeture": 30, "main_d.fermeture": 30 },
  en_garde: { "hanche_g.flexion": 15, "genou_g.flexion": 20, "hanche_d.flexion": -10, "genou_d.flexion": 15, "bassin.abaissement": 6, "tronc.rotation": -20, "tronc.flexion": 5,
              "epaule_g.flexion": 60, "epaule_d.flexion": 60, "epaule_g.rotation": 40, "epaule_d.rotation": 40, "coude_g.flexion": 130, "coude_d.flexion": 130,
              "main_g.fermeture": 100, "main_d.fermeture": 100, "tete.flexion": 10 },
  penseur: { "bassin.abaissement": 46, "hanche_g.flexion": 88, "hanche_d.flexion": 88, "genou_g.flexion": 88, "genou_d.flexion": 88, "hanche_g.abduction": 8, "hanche_d.abduction": 8,
             "tronc.flexion": 30, "tete.flexion": 10, "epaule_d.flexion": 101, "epaule_d.abduction": -10, "epaule_d.rotation": 70, "coude_d.flexion": 126, "poignet_d.flexion": 27, "main_d.fermeture": 70,
             "epaule_g.flexion": 30, "epaule_g.rotation": 50, "coude_g.flexion": 70 },
  statue: { "epaule_d.flexion": 170, "epaule_d.abduction": 10, "coude_d.flexion": 5, "main_d.fermeture": 90, "epaule_g.flexion": 30, "epaule_g.rotation": 60, "coude_g.flexion": 100,
            "tete.flexion": -8, "hanche_g.flexion": 8, "genou_g.flexion": 6 },
});

/* ── Contacts main-visage (2026-10-16) ─────────────────────────────────────────────
   Pour chaque geste : {indice de l'image clé : {X|g|d : [point de la main, repère du visage, décalage (m)]}}.
   Le contact commence à cette image et dure jusqu'au retour (image « fin »), ou tant que le geste est tenu ;
   « null » le relâche. Points : paume, dos, index, doigts (bout du majeur), poing (jointures), avantbras
   (pli du coude). Repères : humanoide.js, REPERES_VISAGE. Les angles des images clés donnent l'approche et
   le style du bras ; la passe géométrique corrige la position finale de la main. */
export const CONTACTS = {
  reflechir: { 0: { d: ["poing", "menton_dessous", [0, -0.012, 0]] } },
  gratter_tete: { 0: { X: ["doigts", "crane_d", [0, 0.012, 0]] } },
  pleurer: { 0: { g: ["paume", "oeil_g", [0.006, -0.012, 0.018]], d: ["paume", "oeil_d", [-0.006, -0.012, 0.018]] } },
  cacher_visage: { 0: { g: ["paume", "oeil_g", [0.004, -0.01, 0.02]], d: ["paume", "oeil_d", [-0.004, -0.01, 0.02]] } },
  salut_militaire: { 0: { X: ["index", "sourcil_d", [-0.012, 0.006, 0.012]] } },
  chut: { 0: { d: ["index", "levres", [0, 0, 0.012]] } },
  tete_mains: { 0: { g: ["paume", "tempe_g", [0.016, 0, 0]], d: ["paume", "tempe_d", [-0.016, 0, 0]] } },
  boire: { 1: { d: ["poing", "bouche", [0, -0.025, 0.05]] } },
  telephoner: { 0: { d: ["paume", "joue_d", [-0.02, 0.01, -0.015]] } },
  essuyer_front: { 0: { d: ["dos", "front", [0.02, 0, 0.016]] }, 1: { d: ["dos", "front", [-0.04, 0, 0.012]] },
                   2: { d: ["dos", "front", [0.02, 0, 0.016]] } },
  bailler: { 0: { d: ["paume", "bouche", [0, 0, 0.03]] } },
  frotter_yeux: { 0: { g: ["poing", "oeil_g", [0, -0.004, 0.014]], d: ["poing", "oeil_d", [0, -0.004, 0.014]] } },
  eternuer: { 1: { d: ["avantbras", "nez", [0, -0.01, 0.03]] } },
  tousser: { 0: { d: ["poing", "bouche", [0, -0.005, 0.03]] } },
  regarder_loin: { 0: { d: ["paume", "front", [0, 0.012, 0.03]] } },
  ecouter: { 0: { d: ["paume", "oreille_d", [-0.012, 0, 0.022]] } },
  dormir: { 0: { g: ["dos", "joue_g", [0.022, -0.012, -0.01]], d: ["paume", "joue_g", [0.012, -0.03, 0.01]] } },
};
export const CONTACTS_POSES = {
  penseur: { d: ["poing", "menton_dessous", [0, -0.012, 0]] },
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
