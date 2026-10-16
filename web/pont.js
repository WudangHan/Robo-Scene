/* Adresse du pont ROBO-SCÈNE.
   Servie par le pont (http://127.0.0.1:8765), l'interface se connecte à lui-même.
   Servie en ligne (Netlify), elle joint le pont qui tourne sur l'ordinateur de l'utilisateur.

   Depuis Chrome 147 (avril 2026), une page publique ne peut ouvrir une WebSocket vers 127.0.0.1 qu'avec
   l'autorisation « Accès au réseau local » (Local Network Access) ; Safari refuse ws:// depuis une page https.
   La version locale de chaque page, servie par le pont lui-même, n'est soumise à aucune de ces règles :
   le bandeau la propose donc en premier, et n'invoque l'installation du service qu'en dernier recours. */
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
  const echap = (s) => String(s).replace(/[<>&"]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c]));

  /* Même page, servie par le pont (http://hôte-du-pont/chemin) : aucune règle de réseau local ne s'y applique. */
  function adresseLocale() {
    let hote = "127.0.0.1:8765";
    try { const u = new URL(url.replace(/^ws/, "http")); hote = u.host; } catch (e) { /* adresse par défaut */ }
    const chemin = { "/console": "/", "/public": "/tableau-public", "/index.html": "/" }[location.pathname]
      || location.pathname.replace(/\.html$/, "");
    const requete = location.search.replace(/[?&]simulation=1(?=&|$)/, "").replace(/^&/, "?");
    return `http://${hote}${chemin}${requete === "?" ? "" : requete}`;
  }

  /* État de l'autorisation « Accès au réseau local » (Chrome) ; null si le navigateur ne l'expose pas. */
  async function autorisationReseauLocal() {
    for (const name of ["local-network-access", "loopback-network", "local-network"]) {
      try { return (await navigator.permissions.query({ name })).state; } catch (e) { /* nom inconnu */ }
    }
    return null;
  }

  function cause(etat) {
    const safari = /^((?!chrome|android|crios|edg).)*safari/i.test(navigator.userAgent);
    if (safari) return "Safari refuse qu'une page en ligne (https) joigne le pont de votre ordinateur (ws://).";
    if (etat === "denied") return "Chrome a refusé à ce site l'« Accès au réseau local » : cliquez sur l'icône à gauche de "
      + "l'adresse, puis Paramètres du site → Accès au réseau local → Autoriser, et rechargez la page.";
    if (etat === "prompt") return "Chrome doit vous demander l'« Accès au réseau local » pour ce site : choisissez « Autoriser » "
      + "dans la demande qui s'affiche près de l'adresse (rechargez la page si elle n'apparaît pas).";
    if (etat === "granted") return "L'accès au réseau local est autorisé : le pont n'est donc probablement pas lancé. Sur un "
      + "ordinateur où le service « Pont ROBO-SCÈNE » est installé, il redémarre de lui-même en moins d'une minute ; sinon, "
      + "dans le dossier Robo-Scene : <code>bash outils/demarrage_automatique.sh installer</code>.";
    return "Cause la plus fréquente : depuis Chrome 147, un site en ligne doit obtenir l'« Accès au réseau local » (icône à "
      + "gauche de l'adresse → Paramètres du site). Si le pont n'est pas lancé, il redémarre de lui-même en moins d'une minute "
      + "là où le service est installé (sinon : <code>bash outils/demarrage_automatique.sh installer</code>).";
  }

  function modifierAdresse() {
    const v = prompt("Adresse WebSocket du pont", url);
    if (v && /^wss?:\/\/[^\s]+$/.test(v.trim())) { try { localStorage.setItem(CLE, v.trim()); } catch (e) {} location.reload(); }
  }

  function placer(el) {
    const ancre = document.querySelector("header.barre");
    ancre ? ancre.insertAdjacentElement("afterend", el) : document.body.prepend(el);
  }

  function afficher(visible) {
    if (local) return;
    if (!bandeau) {
      bandeau = document.createElement("div");
      bandeau.className = "bandeau-pont";
      bandeau.setAttribute("role", "status");
      const sansPont = location.pathname.startsWith("/avatar")
        ? " Le robot virtuel fonctionne sans pont ; seuls le journal de séance et l'interprète par modèle en dépendent." : "";
      bandeau.innerHTML = `<b>Pont ROBO-SCÈNE non joint depuis cette page en ligne.</b> <span data-cause></span>${sansPont}
        <span class="actions"><a class="bouton" href="${echap(adresseLocale())}">Ouvrir la version locale de cette page</a>
        <button type="button" data-a="recharger">Réessayer</button>
        <button type="button" data-a="adresse" class="discret">Modifier l'adresse</button></span>`;
      bandeau.querySelector('[data-a="recharger"]').onclick = () => location.reload();
      bandeau.querySelector('[data-a="adresse"]').onclick = modifierAdresse;
      bandeau.querySelector("[data-cause]").innerHTML = cause(null);
      autorisationReseauLocal().then((etat) => { if (etat) bandeau.querySelector("[data-cause]").innerHTML = cause(etat); });
      placer(bandeau);
    }
    bandeau.hidden = !visible;
  }

  /* Bandeau de simulation (Console seulement) : remplace celui du pont manquant. */
  function simulation() {
    if (local && !forcerSimulation) return;
    if (bandeau) bandeau.hidden = true;
    const b = document.createElement("div");
    b.className = "bandeau-pont bandeau-simulation";
    b.setAttribute("role", "status");
    const titre = forcerSimulation ? "Mode démonstration demandé (?simulation=1) — simulation autonome dans le navigateur"
      : "Pont local non joint — mode simulation autonome dans le navigateur actif";
    const suite = forcerSimulation ? "" : ` Pour piloter le robot : <a class="bouton" href="${echap(adresseLocale())}">ouvrir la console locale</a>
      (servie par le pont de cet ordinateur, sans restriction du navigateur). <span data-cause class="petit"></span>`;
    b.innerHTML = `<b>${titre}</b> (aucune commande matérielle ; rien n'est consigné ni versionné ; l'IA supervisée exige le
      pont). Téléopération, séquences et télémétrie sont simulées ici.${suite}
      <span class="actions"><button type="button" data-a="pont">Réessayer le pont</button>
      <button type="button" data-a="adresse" class="discret">Modifier l'adresse</button>
      <a href="/avatar">Robot virtuel 3D</a></span>`;
    b.querySelector('[data-a="pont"]').onclick = () => (forcerSimulation ? location.assign(location.pathname) : location.reload());
    b.querySelector('[data-a="adresse"]').onclick = modifierAdresse;
    const c = b.querySelector("[data-cause]");
    if (c) { c.innerHTML = cause(null); autorisationReseauLocal().then((etat) => { if (etat) c.innerHTML = cause(etat); }); }
    placer(b);
    window.I18N?.appliquer?.(b);
  }

  /* Pages de la plateforme (atelier, scène, recherche…) : leurs données viennent de l'API du pont (/api/…),
     que le site en ligne ne sert pas ; on l'annonce d'emblée au lieu de laisser des erreurs HTTP 404. */
  function pageDeDonnees() {
    if (local || bandeau) return;
    bandeau = document.createElement("div");
    bandeau.className = "bandeau-pont";
    bandeau.setAttribute("role", "status");
    bandeau.innerHTML = `<b>Cette page lit les données du pont ROBO-SCÈNE de votre ordinateur</b> (atelier, séances, analyses,
      gouvernance) ; le site en ligne n'en contient aucune. <span class="actions"><a class="bouton"
      href="${echap(adresseLocale())}">Ouvrir la version locale de cette page</a></span>
      <span class="petit">Le pont doit tourner sur cet ordinateur ; là où le service « Pont ROBO-SCÈNE » est installé, il
      redémarre de lui-même en moins d'une minute (sinon : <code>bash outils/demarrage_automatique.sh installer</code>).</span>`;
    placer(bandeau);
  }

  return {
    local, url, simulation, forcerSimulation, adresseLocale, pageDeDonnees,
    ouvert() { echecs = 0; afficher(false); },
    ferme() { echecs += 1; if (echecs >= 2) afficher(true); },
  };
})();
