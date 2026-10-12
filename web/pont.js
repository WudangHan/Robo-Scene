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
  function afficher(visible) {
    if (local) return;
    if (!bandeau) {
      bandeau = document.createElement("div");
      bandeau.className = "bandeau-pont";
      bandeau.innerHTML = `<b>Pont ROBO-SCÈNE non joint</b> à <code>${url.replace(/[<>&"]/g, "")}</code>. Lancez le pont sur votre ordinateur
        (dans le dossier Robo-Scene : <code>bash lancer.command</code>, ou une fois pour toutes : <code>bash outils/demarrage_automatique.sh installer</code>), puis attendez quelques secondes.
        Le robot, vos documents et les données des acteurs restent sur votre machine.
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
  return {
    local, url,
    ouvert() { echecs = 0; afficher(false); },
    ferme() { echecs += 1; if (echecs >= 2) afficher(true); },
  };
})();
