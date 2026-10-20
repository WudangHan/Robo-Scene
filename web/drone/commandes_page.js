/* Robo-Scène — commandes en langage naturel (voix ou texte) pour les pages Drone et Chien : interface, file d'actions
   exécutées l'une après l'autre. Chaque action passe par les fonctions ordinaires de la page (lancer), donc par les
   mêmes vérifications (zones du drone, sol praticable du chien, pont et sécurités du robot réel). La voix ne commande
   jamais la coupure des moteurs ; « arrêt d'urgence » déclenche l'ARRÊT ordinaire, qui exige un réarmement distinct. */
import { AIDE_VOIX, EcouteVocale, decouperRotations, interpreter } from "./commande.js";

const deg = (x) => `${Math.round(Math.abs(x))}°`;
const m = (x) => `${Math.abs(x).toLocaleString("fr-CA", { maximumFractionDigits: 2 })} m`;
export function decrire(a) {
  switch (a.type) {
    case "deplacer": return [a.avant && `${a.avant > 0 ? "avancer" : "reculer"} de ${m(a.avant)}`, a.droite && `glisser à ${a.droite > 0 ? "droite" : "gauche"} de ${m(a.droite)}`,
      a.haut && `${a.haut > 0 ? "monter" : "descendre"} de ${m(a.haut)}`].filter(Boolean).join(" et ");
    case "tourner": return `tourner de ${deg(a.angle)} vers la ${a.angle >= 0 ? "gauche" : "droite"}`;
    case "aller": return `aller à « ${a.repere.replace(/_/g, " ")} »`;
    case "point": return `aller au point (${a.p.map((x) => x.toLocaleString("fr-CA", { maximumFractionDigits: 1 })).join(" ; ")})`;
    case "decoller": return a.hauteur ? `décoller à ${m(a.hauteur)}` : "décoller";
    case "posture": return `posture « ${a.nom} »`;
    case "allure": return `allure « ${a.nom} »`;
    case "regarder": return a.cible ? `regarder ${a.cible === "salle" ? "la salle" : `« ${a.cible.replace(/_/g, " ")} »`}` : "regarder devant";
    default: return { atterrir: "atterrir", retour: "retour", lever: "se lever", coucher: "se coucher", arreter: "arrêter", urgence: "ARRÊT", go: "GO (repère suivant)" }[a.type] || a.type;
  }
}

/* robot : "drone" | "chien" ; reperes : { nom: position } ; lancer(action) → false (refus : la file est vidée),
   { fin: () => booléen } (attendre), ou autre (action instantanée) ; preparer(actions) → actions (ex. décollage ajouté) ;
   arreterTout() : arrêt ordinaire ; urgence() : ARRÊT ; journal(niveau, texte).
   Dialogue (facultatif, objet rendu par installerDialogue de ../dialogue.js, branché ensuite par cmds.dialogue = …) :
   une phrase qui n'est pas une commande part à la conversation ; pendant que la machine parle, seuls « stop » et
   « arrêt d'urgence » sont écoutés (le reste est l'écho de sa propre voix). */
export function installerCommandes({ robot, reperes, lancer, preparer = (a) => a, arreterTout, urgence, journal }) {
  const $ = (s) => document.querySelector(s);
  const file = []; let courante = null; let dialogue = null;

  function vider() { file.length = 0; courante = null; }
  function executerActions(actions, libelle) {
    if (!actions.length) return;
    if (actions.some((a) => a.type === "urgence")) { vider(); urgence(); journal("alerte", `${libelle} → ARRÊT`); return; }
    if (actions[0].type === "arreter") { vider(); arreterTout(); journal("info", `${libelle} → arrêter`); return; }
    vider();                                   // une nouvelle commande remplace celle en cours
    const a2 = preparer(actions.slice());
    journal("info", `${libelle} → ${a2.map(decrire).join(", puis ")}`);
    file.push(...decouperRotations(a2));      // plus de 120° : par étapes, dans le sens demandé
  }
  function executer(texte, source = "texte") {
    const t = String(texte || "").trim(); if (!t) return { actions: [], inconnu: [] };
    const r = interpreter(t, robot, reperes), icone = source === "voix" ? "🎙" : "⌨";
    const qui = robot === "drone" ? "le drone" : "le chien";
    // une destination inexistante pour ce robot fait refuser toute la phrase : rien n'est exécuté à moitié
    if (r.absents?.length) { journal("refus", `${icone} « ${t} » refusée : repère inexistant pour ${qui} (« ${r.absents.join(" », « ")} »)`); return r; }
    if (!r.actions.length && dialogue?.actif()) { dialogue.demander(t, source); return r; }
    if (!r.actions.length) { journal("refus", `${icone} « ${t} » : commande non comprise (voir les exemples)`); return r; }
    if (r.inconnu.length) journal("avert", `${icone} partie non comprise, ignorée : « ${r.inconnu.join(" / ")} »`);
    executerActions(r.actions, `${icone} « ${t} »`);
    return r;
  }
  /* À appeler à chaque image : lance l'action suivante quand la précédente est terminée (ou après 60 s). */
  function pas() {
    if (courante) {
      if (performance.now() - courante.t0 > 60000) { journal("avert", "Commande abandonnée : délai dépassé"); vider(); return; }
      if (!courante.fin()) return;
      courante = null;
    }
    while (file.length) {
      const a = file.shift(), r = lancer(a);
      if (r === false || r?.ok === false) { if (file.length) journal("avert", `Suite de la commande annulée (${file.map(decrire).join(", ")})`); vider(); return; }
      if (r && typeof r.fin === "function") { courante = { fin: r.fin, t0: performance.now() }; return; }
    }
  }

  /* ── Interface ── */
  const bouton = $("#b-parler"), etat = $("#voix-etat"), interim = $("#voix-interim");
  const ecoute = new EcouteVocale({
    surTexte: (t) => {
      interim.textContent = "";
      if (dialogue?.parle()) {                  // demi-duplex : la machine parle, seul l'arrêt passe
        const r = interpreter(t, robot, reperes);
        if (r.actions.some((a) => a.type === "urgence" || a.type === "arreter")) { dialogue.taire(); executer(t, "voix"); }
        return;
      }
      if (dialogue?.estEcho(t)) { journal("info", `🎙 écho de la voix de la machine ignoré : « ${t} »`); return; }
      executer(t, "voix");
    },
    surInterim: (t) => { interim.textContent = t ? `… ${t}` : ""; },
    surEtat: (e, msg) => {
      const actif = e === "ecoute";
      bouton.setAttribute("aria-pressed", String(actif)); bouton.classList.toggle("ecoute", actif);
      bouton.textContent = actif ? "🎙 J'écoute… (cliquer pour arrêter)" : "🎙 Parler";
      etat.textContent = msg || (actif ? ($("#voix-continue").checked ? "Écoute continue" : "Une phrase, puis arrêt") : "");
      if (e === "erreur" || e === "indisponible") journal("avert", `Voix : ${msg}`);
    },
  });
  if (!EcouteVocale.disponible()) { bouton.disabled = true; etat.textContent = "Reconnaissance vocale non prise en charge par ce navigateur : utiliser le champ de texte (Chrome ou Edge pour la voix)"; }
  bouton.onclick = () => (ecoute.active ? ecoute.arreter() : ecoute.demarrer({ continu: $("#voix-continue").checked, local: $("#voix-local").checked }));
  $("#voix-local").onchange = (e) => { if (!e.target.checked) journal("avert", "Voix : reconnaissance sur l'appareil désactivée — le navigateur peut envoyer l'audio à un service distant"); if (ecoute.active) ecoute.arreter(); };
  const champ = $("#commande-texte");
  $("#b-commande").onclick = () => { executer(champ.value, "texte"); champ.select(); };
  champ.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); executer(champ.value, "texte"); champ.select(); } });
  $("#voix-aide").innerHTML = AIDE_VOIX[robot].map((x) => `<li><button type="button" class="lien" data-phrase="${x.replace(/"/g, "&quot;")}">${x}</button></li>`).join("");
  $("#voix-aide").onclick = (e) => { const b = e.target.closest("[data-phrase]"); if (b) { champ.value = b.dataset.phrase; champ.focus(); } };
  window.addEventListener("keydown", (e) => {   // V : parler (hors champs de saisie)
    if (e.key.toLowerCase() === "v" && !e.repeat && !/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) && !bouton.disabled) { e.preventDefault(); bouton.click(); }
  });

  return { executer, executerActions, pas, vider, ecoute, get occupe() { return !!courante || file.length > 0; },
    get dialogue() { return dialogue; }, set dialogue(d) { dialogue = d; } };
}
