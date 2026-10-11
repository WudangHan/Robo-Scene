// Trousse JavaScript (Node.js ≥ 18, sans dépendance) pour écrire le pilote d'un robot ROBO-SCÈNE.
// Langage unifié : PROTOCOLE.md v2 — un objet JSON par ligne.
//
// Un pilote crée un PiloteRobot avec ses articulations et ses fonctions matérielles :
//   new PiloteRobot({ nom, articulations: [[nom, min, max, repos], …], propulsion,
//                     appliquerServos(deg, ms), appliquerPropulsion(g, d), figer(), lireEtat() }).executer();
// La trousse borne localement, applique le chien de garde (500 ms) et le verrou d'arrêt, publie la télémétrie.
// Relier au pont : profil « externe » (executer : stdin/stdout) ou « ligne_json » en TCP (servirTcp(port)).

import { createInterface } from "node:readline";
import { createServer } from "node:net";

export class PiloteRobot {
  constructor(o) {
    this.nom = o.nom ?? "ROBOT-JS";
    this.articulations = o.articulations ?? [];
    this.propulsion = !!o.propulsion;
    this.appliquerServos = o.appliquerServos ?? (() => {});
    this.appliquerPropulsion = o.appliquerPropulsion ?? (() => {});
    this.figer = o.figer ?? (() => {});
    this.lireEtat = o.lireEtat ?? (() => ({}));
    this.deg = this.articulations.map((a) => a[3]);
    this.roues = [0, 0];
    this.estop = false;
    this.dernier = Date.now();
    this.t0 = Date.now();
    this.ecrire = () => {};
  }

  envoyer(d) { this.ecrire(JSON.stringify(d) + "\n"); }

  info() {
    return { t: "info", nom: this.nom, fw: "sdk-js-1.0.0", servos: this.articulations.length,
             propulsion: this.propulsion, articulations: this.articulations.map((a) => a[0]) };
  }

  traiter(ligne) {
    ligne = ligne.trim();
    if (!ligne.startsWith("{")) return;
    let m;
    try { m = JSON.parse(ligne); } catch { return; }   // ligne illisible : ignorée
    this.dernier = Date.now();
    const t = m.t;
    if (t === "hello") this.envoyer(this.info());
    else if (t === "estop") { this.estop = true; this.roues = [0, 0]; this.figer(); }
    else if (t === "reset") this.estop = false;
    else if (["servos", "drive", "geste"].includes(t) && this.estop) this.envoyer({ t: "err", msg: "estop" });
    else if (t === "servos") {
      const deg = m.deg ?? [];
      if (deg.length !== this.articulations.length) { this.envoyer({ t: "err", msg: "nombre d'angles incorrect" }); return; }
      this.deg = deg.map((d, i) => Math.max(this.articulations[i][1], Math.min(this.articulations[i][2], Number(d))));
      this.appliquerServos(this.deg, Number(m.ms ?? 0));
    } else if (t === "drive" && this.propulsion) {
      const b = (x) => Math.max(-1, Math.min(1, Number(x ?? 0)));
      this.roues = [b(m.l), b(m.r)];
      this.appliquerPropulsion(...this.roues);
    }
  }

  demarrerTelemetrie() {
    return setInterval(() => {
      if (Date.now() - this.dernier > 500 && (this.roues[0] || this.roues[1])) {
        this.roues = [0, 0];
        this.appliquerPropulsion(0, 0);
      }
      this.envoyer({ t: "tel", ms: Date.now() - this.t0, deg: this.deg.map((d) => Math.round(d * 10) / 10),
                     drive: this.roues, estop: this.estop, ...this.lireEtat() });
    }, 50);
  }

  executer() {
    this.ecrire = (s) => process.stdout.write(s);
    const minuterie = this.demarrerTelemetrie();
    this.envoyer(this.info());
    const rl = createInterface({ input: process.stdin });
    rl.on("line", (l) => this.traiter(l));
    rl.on("close", () => { clearInterval(minuterie); this.figer(); process.exit(0); });
  }

  servirTcp(port = 3333) {
    createServer((sock) => {
      this.ecrire = (s) => sock.write(s);
      const minuterie = this.demarrerTelemetrie();
      createInterface({ input: sock }).on("line", (l) => this.traiter(l));
      sock.on("close", () => { clearInterval(minuterie); this.roues = [0, 0]; this.figer(); });
      sock.on("error", () => {});
    }).listen(port);
  }
}
