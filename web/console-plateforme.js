/* Console : flotte multi-robots, observateur de sécurité, règle de l'IA, saisies de traçabilité (N-07, N-08),
   surtitres et voix de synthèse divulguée (O-12). S'appuie sur app.js (envoyer, $). */
"use strict";
(() => {
  const echap = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let debutTete = null;

  function surConfig(c) {
    const sel = $("#pf-robot");
    sel.innerHTML = (c.flotte || []).map((r) => `<option value="${echap(r.id)}"${r.id === c.robot_id ? " selected" : ""}>
      ${echap(r.nom || r.id)} — ${echap(r.simulation ? "simulation" : r.pilote)}${r.rayon_exclusion_m ? ` · zone ${r.rayon_exclusion_m} m` : ""}</option>`).join("");
    const actifs = new Set((c.flotte || []).map((r) => r.id));
    $("#pf-profil").innerHTML = (c.profils || []).filter((p) => !actifs.has(p.id))
      .map((p) => `<option value="${echap(p.id)}">${echap(p.nom || p.id)} (${echap(p.pilote)})</option>`).join("");
    $("#pf-activer").disabled = !$("#pf-profil").options.length;
    $("#pf-flotte").innerHTML = (c.flotte || []).map((r) => `<span class="pastille ${r.lien === "connecte" ? "ok" : "neutre"}">${echap(r.id)} · ${echap(r.lien || "—")}</span>`).join(" ");
    $("#pf-obs-etat").textContent = c.observateur ? `Présent : ${c.observateur.initiales} (depuis ${c.observateur.depuis})`
      : (c.rayon_exclusion_m ? `Absent — exigé pour ${c.robot} en mode réel (zone ${c.rayon_exclusion_m} m)` : "Absent");
    $("#pf-regle").value = c.regle_ia;
    $("#pf-regle").querySelector('[value="angles_s04"]').disabled = c.type_seance !== "S04";
  }

  function parler(texte) {
    if (!$("#pf-voix").checked || !("speechSynthesis" in window) || !texte) return;
    const u = new SpeechSynthesisUtterance(texte);
    u.lang = document.documentElement.lang === "en" ? "en-CA" : "fr-CA";
    u.pitch = 0.4; u.rate = 0.9;          // timbre volontairement non humain (régime « machinique »)
    window.speechSynthesis.speak(u);
  }

  window.surMessagePlateforme = (m) => {
    if (m.type === "config") surConfig(m);
    else if (m.type === "surtitre") {
      $("#pf-surtitre").innerHTML = `${echap(m.texte)}${m.en ? `<span class="en" lang="en">${echap(m.en)}</span>` : ""}<span class="prov">${echap(m.provenance)}</span>`;
    } else if (m.type === "voix") {
      $("#pf-surtitre").innerHTML = `${echap(m.texte)}<span class="prov">voix de synthèse — divulguée au public</span>`;
      parler(m.texte);
    }
  };

  $("#pf-robot").onchange = (e) => envoyer("robot_choisir", { robot: e.target.value });
  $("#pf-activer").onclick = () => envoyer("robot_activer", { robot: $("#pf-profil").value, simulation: true });
  $("#pf-obs-on").onclick = () => envoyer("observateur", { present: true, initiales: $("#pf-obs").value });
  $("#pf-obs-off").onclick = () => envoyer("observateur", { present: false });
  $("#pf-regle").onchange = (e) => envoyer("regle_ia", { valeur: e.target.value });
  $("#pf-tete-txt").addEventListener("focus", () => { if (!debutTete) debutTete = Date.now() / 1000; });
  $("#pf-tete").onsubmit = (e) => {
    e.preventDefault();
    envoyer("transformation_de_tete", { description: $("#pf-tete-txt").value, debut: debutTete });
    $("#pf-tete-txt").value = ""; debutTete = null;
  };
  $("#pf-autre").onsubmit = (e) => {
    e.preventDefault();
    envoyer("operation_autre", { categorie: $("#pf-autre-cat").value, description: $("#pf-autre-txt").value });
    $("#pf-autre-txt").value = "";
  };
})();
