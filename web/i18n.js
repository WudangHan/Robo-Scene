/* Interface bilingue (français, anglais) et barre de navigation commune à toutes les pages.
   Le français est la langue source : chaque élément marqué data-i18n porte son texte français, que le
   dictionnaire traduit ; data-i18n-ph traduit un texte indicatif (placeholder), data-i18n-title une info-bulle.
   Le choix de langue est mémorisé dans le navigateur quand c'est possible (sans effet sur les données). */
"use strict";
window.I18N = (() => {
  const CLE = "robo-scene-langue";
  const EN = {
    // Navigation
    "Console": "Console", "Partenaire": "Partner", "Atelier": "Workshop", "Scène": "Stage", "Spectateur": "Audience",
    "Surtitres": "Surtitles", "Recherche": "Research", "Gouvernance": "Governance", "Régie": "Project office",
    "Tableau public": "Public dashboard", "Plateforme intégrée": "Integrated platform",
    // Commun
    "Actualiser": "Refresh", "Enregistrer": "Save", "Valider": "Approve", "Rejeter": "Reject", "Fermer": "Close",
    "Ouvrir": "Open", "Lancer": "Run", "Pseudonyme": "Pseudonym", "Par (pseudonyme ou initiales)": "By (pseudonym or initials)",
    "Mode": "Mode", "Essai": "Trial", "Public": "Public", "État": "Status", "Fichier": "File", "Langue": "Language",
    "Aucune donnée.": "No data.", "Verrou de gouvernance": "Governance lock",
    // Console
    "Flotte et règles": "Fleet and rules", "Robot actif": "Active robot", "Activer un profil": "Enable a profile",
    "Activer (simulation)": "Enable (simulation)", "Observateur de sécurité": "Safety observer",
    "Initiales de l'observateur": "Observer's initials", "Présent": "Present", "Absent": "Absent",
    "Règle de l'IA": "AI rule", "Bibliothèque fermée": "Closed library", "Angles proposés (S04 seulement)": "Proposed angles (S04 only)",
    "Transformation « de tête »": "Transformation done “by heart”", "Décrire la transformation": "Describe the transformation",
    "Consigner": "Record", "Opération « autre »": "“Other” operation", "Catégorie": "Category",
    "Surtitre en cours": "Current surtitle", "Voix de synthèse (divulguée)": "Synthetic voice (disclosed)",
    // Scène
    "Conduite": "Cue script", "Charger l'exemple": "Load the example", "Charger le texte": "Load the text",
    "Texte YAML de la conduite": "Cue script YAML", "Aperçu": "Preview", "Simuler (jumeau)": "Simulate (digital twin)",
    "Retour": "Back", "ARRÊT conduite": "STOP cue script", "Reprendre les gestes": "Resume gestures",
    "Repères": "Cues", "Journal de la scène": "Stage log", "Écho (R-06)": "Echo (R-06)",
    "Ce que fait l'interprète": "What the performer does", "Geste choisi": "Chosen gesture", "Jouer l'écho": "Play the echo",
    // Spectateur
    "Tirage des conditions X.2": "X.2 condition draw", "Représentations": "Performances", "Graine": "Seed",
    "Sans facteur support (D08)": "Without the medium factor (D08)", "Effectuer le tirage scellé": "Run the sealed draw",
    "Séance P3 (rétroaction en salle)": "P3 session (live feedback)", "Identifiant de représentation": "Performance ID",
    "Provenance affichée (essai)": "Provenance shown (trial)", "Ouvrir la séance": "Open session", "Fermer la séance": "Close session",
    "Questionnaires": "Questionnaires", "Instrument": "Instrument", "Ouvrir la passation": "Open the questionnaire",
    "Fermer la passation": "Close the questionnaire", "Serveur public des questionnaires": "Public questionnaire server",
    "Démarrer": "Start", "Arrêter": "Stop", "Avis au public (S-06)": "Notice to the audience (S-06)",
    // Surtitres
    "Importer depuis la conduite": "Import from the cue script", "Proposer (IA)": "Propose (AI)",
    "Contenu confidentiel (modèle local)": "Confidential content (local model)", "Exporter WebVTT": "Export WebVTT",
    "Source": "Source", "Proposition": "Proposal", "Version validée": "Approved version", "Saisir": "Type in",
    // Recherche
    "Analyse (Q-01 à Q-05)": "Analysis (Q-01 to Q-05)", "Représentations exclues": "Excluded performances",
    "Codeur (Q-05)": "Coder (Q-05)", "Lancer l'analyse": "Run the analysis", "Codage des entretiens (local)": "Interview coding (local)",
    "Transcription pseudonymisée": "Pseudonymised transcript", "Découper": "Segment", "Suggérer (modèle local)": "Suggest (local model)",
    "Veille bibliographique (O-08)": "Literature watch (O-08)", "Requête": "Query", "Chercher": "Search",
    "Vérifiée": "Verified", "Écartée": "Discarded", "Note de vérification": "Verification note",
    "Bibliographie MLA (notices vérifiées)": "MLA bibliography (verified records)",
    "Tableau public (O-09)": "Public dashboard (O-09)", "Préparer le brouillon": "Prepare draft", "Publier": "Publish",
    // Gouvernance
    "Verrous": "Locks", "Incidents": "Incidents", "Décisions en attente (G-05)": "Pending decisions (G-05)",
    "Conservation (G-07)": "Retention (G-07)", "Systèmes d'IA (G-03)": "AI systems (G-03)", "Couverture des fonctions": "Function coverage",
    "Clore l'incident": "Close incident", "Gravité": "Severity", "Cause": "Cause", "Mesures": "Measures",
    // Régie
    "Tâches": "Tasks", "Régisseur IA (lecture seule)": "AI stage manager (read only)", "Question": "Question",
    "Demander": "Ask", "Revue trimestrielle (P-04)": "Quarterly review (P-04)", "Produire la revue": "Produce the review",
    "Robot virtuel": "Virtual robot", "Drone": "Drone", "Chien": "Dog", "Aide": "Help",
    "Dépôts du jour (P-03)": "Today's deposits (P-03)", "Inventaire mensuel (P-02)": "Monthly inventory (P-02)",
  };
  const PAGES = [["/", "Console"], ["/partenaire", "Partenaire"], ["/atelier", "Atelier"], ["/scene", "Scène"],
    ["/spectateur", "Spectateur"], ["/surtitres", "Surtitres"], ["/recherche", "Recherche"], ["/gouvernance", "Gouvernance"],
    ["/regie", "Régie"], ["/tableau-public", "Tableau public"], ["/avatar", "Robot virtuel"], ["/drone", "Drone"], ["/chien", "Chien"], ["/aide", "Aide"]];
  let langue = "fr";
  try { langue = localStorage.getItem(CLE) || "fr"; } catch (e) { /* stockage indisponible : français */ }
  if (!["fr", "en"].includes(langue)) langue = "fr";
  const t = (fr) => (langue === "en" && EN[fr]) || fr;

  function appliquer(racine = document) {
    document.documentElement.lang = langue;
    racine.querySelectorAll("[data-i18n]").forEach((el) => {
      if (!el.dataset.fr) el.dataset.fr = el.textContent.trim();
      el.textContent = t(el.dataset.fr);
    });
    racine.querySelectorAll("[data-i18n-ph]").forEach((el) => {
      if (!el.dataset.frPh) el.dataset.frPh = el.getAttribute("placeholder") || "";
      el.setAttribute("placeholder", t(el.dataset.frPh));
    });
    racine.querySelectorAll("[data-i18n-title]").forEach((el) => {
      if (!el.dataset.frTitle) el.dataset.frTitle = el.getAttribute("title") || "";
      el.setAttribute("title", t(el.dataset.frTitle));
    });
  }

  function nav() {
    document.querySelectorAll("nav[data-nav]").forEach((n) => {
      const ici = location.pathname.replace(/\/$/, "") || "/";
      n.className = "nav-pages";
      n.setAttribute("aria-label", t("Plateforme intégrée"));
      n.innerHTML = PAGES.map(([h, l]) => `<a href="${h}"${h === ici ? ' aria-current="page"' : ""} data-i18n>${l}</a>`).join("")
        + `<button type="button" class="langue discret" lang="${langue === "fr" ? "en" : "fr"}">${langue === "fr" ? "EN" : "FR"}</button>`;
      n.querySelector(".langue").setAttribute("aria-label", langue === "fr" ? "English" : "Français");
      n.querySelector(".langue").onclick = () => {
        langue = langue === "fr" ? "en" : "fr";
        try { localStorage.setItem(CLE, langue); } catch (e) { /* sans mémoire */ }
        nav(); appliquer(); document.dispatchEvent(new CustomEvent("langue", { detail: langue }));
      };
    });
  }
  document.addEventListener("DOMContentLoaded", () => { nav(); appliquer(); });
  return { t, appliquer, get langue() { return langue; } };
})();
