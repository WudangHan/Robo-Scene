/* Adresse du pont ROBO-SCÈNE.
   Servie par le pont (http://127.0.0.1:8765), l'interface se connecte à lui-même.
   Servie en ligne (Netlify), elle joint le pont qui tourne sur l'ordinateur de l'utilisateur. */
"use strict";
window.ROBO_PONT = (() => {
  const CLE = "robo-scene-pont";
  const local = location.protocol === "http:" || ["127.0.0.1", "localhost"].includes(location.hostname);
  let url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;
  if (!local) {
    let memo = null;
    try { memo = localStorage.getItem(CLE); } catch (e) { /* stockage indisponible */ }
    url = memo || "ws://127.0.0.1:8765/ws";
  }
  let bandeau = null, echecs = 0;
  // ?simulation=1 : démonstration sans robot, même quand le pont tourne (présentations, essais)
  const forcerSimulation = /[?&]simulation=1(&|$)/.test(location.search);
  function afficher(visible) {
    if (local) return;
    if (!bandeau) {
      bandeau = document.createElement("div");
      bandeau.className = "bandeau-pont";
      bandeau.innerHTML = `<b>Pont ROBO-SCÈNE non joint</b> à <code>${url.replace(/[<>&"]/g, "")}</code>. Sur un ordinateur où le service
        « Pont ROBO-SCÈNE » est installé, il se relance de lui-même en moins d'une minute ; sinon, l'installer une fois pour toutes
        (dans le dossier Robo-Scene : <code>bash outils/demarrage_automatique.sh installer</code>) ou ouvrir l'application « ROBO-SCÈNE ».
        La page se reconnecte seule. Le robot, vos documents et les données des acteurs restent sur votre machine.
        <button type="button">Modifier l'adresse</button>`;
      bandeau.querySelector("button").onclick = () => {
        const v = prompt("Adresse WebSocket du pont", url);
        if (v && /^wss?:\/\/[^\s]+$/.test(v.trim())) { try { localStorage.setItem(CLE, v.trim()); } catch (e) {} location.reload(); }
      };
      const ancre = document.querySelector("header.barre");
      ancre ? ancre.insertAdjacentElement("afterend", bandeau) : document.body.prepend(bandeau);
    }
    bandeau.hidden = !visible;
  }
  /* Bandeau de simulation : non intrusif, remplace celui du pont manquant (Console seulement). */
  function simulation() {
    if (local && !forcerSimulation) return;
    if (bandeau) bandeau.hidden = true;
    const b = document.createElement("div");
    b.className = "bandeau-pont bandeau-simulation";
    b.setAttribute("role", "status");
    const titre = forcerSimulation ? "Mode démonstration demandé (?simulation=1) — simulation autonome dans le navigateur"
      : "Pont local non détecté — mode simulation autonome dans le navigateur actif";
    b.innerHTML = `<b>${titre}</b> (aucune commande
      matérielle ; rien n'est consigné ni versionné ; l'IA supervisée exige le pont). Téléopération, séquences et
      télémétrie sont simulées ici. <button type="button" data-a="pont">Réessayer le pont</button>
      <button type="button" data-a="adresse" class="discret">Modifier l'adresse</button>
      <a href="/avatar">Ouvrir le robot virtuel 3D</a>`;
    b.querySelector('[data-a="pont"]').onclick = () => (forcerSimulation ? location.assign(location.pathname) : location.reload());
    b.querySelector('[data-a="adresse"]').onclick = () => {
      const v = prompt("Adresse WebSocket du pont", url);
      if (v && /^wss?:\/\/[^\s]+$/.test(v.trim())) { try { localStorage.setItem(CLE, v.trim()); } catch (e) {} location.reload(); }
    };
    const ancre = document.querySelector("header.barre");
    ancre ? ancre.insertAdjacentElement("afterend", b) : document.body.prepend(b);
    window.I18N?.appliquer?.(b);
  }
  return {
    local, url, simulation, forcerSimulation,
    ouvert() { echecs = 0; afficher(false); },
    ferme() { echecs += 1; if (echecs >= 2) afficher(true); },
  };
})();
