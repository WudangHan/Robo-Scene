// Exemple de pilote JavaScript : robot simulé à deux servos et deux roues (robots/exemple_externe_javascript.toml).
import { PiloteRobot } from "./robo-scene-pilote.mjs";

new PiloteRobot({
  nom: "SIM-JS",
  articulations: [["base", 10, 170, 90], ["tete", 30, 150, 90]],
  propulsion: true,
  appliquerServos(deg, ms) { /* appel au matériel : bibliothèque Johnny-Five, port série, etc. */ },
  appliquerPropulsion(g, d) {},
  figer() {},
  lireEtat() { return { vbat: 7.9 }; },
}).executer();
