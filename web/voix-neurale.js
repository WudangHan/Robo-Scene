/* Robo-Scène — voix neuronale (client) : demande au pont le rendu d'une réplique par un moteur vocal
   dirigeable (Eleven v3, voix neuronales québécoises d'Azure, gpt-4o-mini-tts, Piper local), suit le
   pré-rendu d'une répétition et joue les sons rendus.

   Principes :
   - Le pont décide du moteur (ordre de config.toml, aiguillage de sensibilité D03) et range chaque son
     dans son cache : une réplique déjà rendue se rejoue sans délai ni coût, toujours identique.
   - Si le pont est injoignable, si aucun moteur n'est disponible ou si le rendu tarde, l'appelant se rabat
     sur la voix du navigateur, désormais dite une PHRASE à la fois (segments de la partition prosodique).
   - Le lecteur expose l'énergie du signal (analyseur Web Audio) : le robot virtuel en tire l'ouverture de
     la bouche, et les instants de début des mots quand le moteur les fournit (Eleven v3).

   Le module ne dépend que de fonctions passées en paramètre (envoi au pont) et s'exécute aussi sous Node.js
   pour les tests (sans lecteur audio). */
"use strict";
(function (racine) {
  /* Adresse http(s) du pont à partir de l'adresse ws(s) de la page. */
  function base(urlWs) {
    try { const u = new URL(String(urlWs || "").replace(/^ws/, "http")); return `${u.protocol}//${u.host}`; }
    catch (e) { return "http://127.0.0.1:8765"; }
  }
  function absolue(url, urlWs) {
    if (!url) return null;
    return /^https?:/.test(url) ? url : base(urlWs) + url;
  }
  const texteDe = (rendu) => (rendu?.segments || []).map((s) => s.texte).join(" ").trim();

  /* Client du service vocal du pont. envoyer(op, data) : envoi WebSocket ; urlWs() : adresse du pont. */
  function creer({ envoyer, urlWs = () => (racine.ROBO_PONT && racine.ROBO_PONT.url) || "ws://127.0.0.1:8765/ws",
                   delaiMs = 25000 } = {}) {
    let jeton = 0;
    const attentes = new Map();
    const prerendus = new Map();          // id de réplique → {url, cle, duree_ms, moteur, mots}
    const suivis = new Map();             // jeton de pré-rendu → rappel(progrès)
    const client = {
      etat: null, actifVoulu: true, derniere: "",
      /* Vrai si le pont annonce un moteur neuronal disponible (et que l'opératrice ne l'a pas désactivé). */
      actif() { return client.actifVoulu && !!client.etat?.actif; },
      moteur() { return client.etat?.actif || null; },
      demanderEtat() { envoyer("voix_etat", {}); },
      /* À appeler pour chaque message du pont ; vrai si le message relevait de la voix. */
      surMessage(m) {
        if (!m || typeof m.type !== "string" || !m.type.startsWith("voix_")) return false;
        if (m.type === "voix_etat") { client.etat = m; client.surEtat?.(m); return true; }
        if (m.type === "voix_progres") {
          if (m.statut === "audio" && m.id) prerendus.set(m.id, { url: absolue(m.url, urlWs()), cle: m.cle, duree_ms: m.duree_ms, moteur: m.moteur, mots: m.mots || [] });
          suivis.get(m.jeton)?.(m);
          if (m.fait >= m.total) suivis.delete(m.jeton);
          return true;
        }
        const f = attentes.get(m.jeton);
        if (f) { attentes.delete(m.jeton); f(m); }
        else if (m.type === "voix_erreur") client.derniere = m.msg || "";
        return true;
      },
      /* Rendu d'un texte : {texte, variation, regime, marques, personnage, role, indice, profil, base, prise}.
         Résout {statut:"audio", url, …} ou {statut:"repli", segments, motif} ; null si le pont ne répond pas. */
      rendre(demande, delai = delaiMs) {
        const j = `v${++jeton}`;
        return new Promise((ok) => {
          const garde = setTimeout(() => { attentes.delete(j); ok(null); }, delai);
          attentes.set(j, (m) => {
            clearTimeout(garde);
            if (m.type === "voix_erreur") { client.derniere = m.msg || ""; return ok(null); }
            if (m.url) m.url = absolue(m.url, urlWs());
            ok(m);
          });
          envoyer("voix_rendre", { ...demande, jeton: j });
        });
      },
      /* Pré-rendu des répliques d'une répétition ; progres(m) reçoit chaque avancement. */
      prerendre(items, progres) {
        const j = `p${++jeton}`;
        if (progres) suivis.set(j, progres);
        envoyer("voix_prerendre", { items, jeton: j });
        return j;
      },
      prerendu(id) { return prerendus.get(id) || null; },
      oublier() { prerendus.clear(); },
      distribuer(personnage, moteur, voix) { envoyer("voix_distribuer", { personnage, moteur, voix }); },
      surRobot(cle, texte) { envoyer("voix_robot", { cle, texte, jeton: `r${++jeton}` }); },
    };
    return client;
  }

  /* Éléments d'une répétition à pré-rendre : répliques du partenaire, voix humaine seulement. */
  function itemsRepetition(plan) {
    const persos = [...new Set((plan?.items || []).filter((x) => x.type === "replique" && !x.acteur).map((x) => x.perso))];
    return (plan?.items || []).filter((x) => x.type === "replique" && !x.acteur && x.voix && x.voix.parler !== false
                                          && x.voix.type_voix !== "machinique")
      .map((x) => ({ id: x.id, texte: x.texte, variation: x.variation, regime: x.voix.type_voix || "humain",
                     marques: x.voix.marques || null, personnage: x.nom || x.perso, indice: persos.indexOf(x.perso),
                     base: { debit: x.voix.debit, hauteur: x.voix.hauteur, volume: x.voix.volume } }));
  }

  /* Lecteur : joue une adresse, résout vrai à la fin (faux si interrompu ou bloqué). surEnergie(rms 0–1) est
     appelé à chaque image ; bloque(e) si le navigateur refuse la lecture (aucune interaction avec la page). */
  class Lecteur {
    constructor() { this.jeton = 0; this.audio = null; this.ctx = null; this.analyseur = null; this.energie = 0; this.joue = false; }
    annuler() {
      const t = this._terminer; this._terminer = null; t?.(false);
      this.jeton++; this.joue = false; this.energie = 0;
      if (this.audio) { try { this.audio.pause(); this.audio.removeAttribute("src"); this.audio.load(); } catch (e) {} this.audio = null; }
    }
    _contexte() {
      const AC = racine.AudioContext || racine.webkitAudioContext;
      if (!AC) return null;
      if (!this.ctx) { try { this.ctx = new AC(); } catch (e) { this.ctx = null; } }
      if (this.ctx && this.ctx.state === "suspended") this.ctx.resume().catch(() => {});
      return this.ctx;
    }
    jouer(url, opts = {}) {
      const { volume = 1, surEnergie = null, surDebut = null, analyser = true } = opts;
      this.annuler();
      this.dernierBloque = false;
      const j = ++this.jeton;
      const a = new Audio();
      this.audio = a;
      if (analyser) a.crossOrigin = "anonymous";
      a.preload = "auto"; a.volume = Math.max(0, Math.min(1, volume));
      a.src = url;
      let tampon = null, lien = null;
      const ctx = analyser ? this._contexte() : null;
      if (ctx) {
        try {
          lien = ctx.createMediaElementSource(a);
          const an = ctx.createAnalyser(); an.fftSize = 1024; tampon = new Float32Array(an.fftSize);
          lien.connect(an); an.connect(ctx.destination); this.analyseur = an;
        } catch (e) { lien = null; }
      }
      return new Promise((fin) => {
        let fini = false;
        const terminer = (ok) => { if (fini) return; fini = true; if (this._terminer === terminer) this._terminer = null; this.joue = false; this.energie = 0; surEnergie?.(0); try { lien?.disconnect(); } catch (e) {} fin(ok && j === this.jeton); };
        this._terminer = terminer;
        const boucle = () => {
          if (fini || j !== this.jeton) return terminer(false);
          if (this.analyseur && tampon && lien) {
            this.analyseur.getFloatTimeDomainData(tampon);
            let s = 0; for (let i = 0; i < tampon.length; i++) s += tampon[i] * tampon[i];
            this.energie = Math.min(1, Math.sqrt(s / tampon.length) * 6);
            surEnergie?.(this.energie);
          } else surEnergie?.(null);                  // pas d'analyseur : l'appelant garde son horloge seule
          (racine.requestAnimationFrame || ((f) => setTimeout(f, 16)))(boucle);
        };
        a.onplaying = () => { this.joue = true; surDebut?.(a); boucle(); };
        a.onended = () => terminer(true);
        a.onerror = () => {
          // Sans en-tête CORS (page servie d'une origine non déclarée), le son se relit sans analyseur :
          // la bouche suit alors le débit estimé au lieu de l'énergie du signal.
          if (analyser && !fini && j === this.jeton) { fini = true; try { lien?.disconnect(); } catch (e) {}
            this.jouer(url, { ...opts, analyser: false }).then(fin); return; }
          terminer(false);
        };
        const p = a.play();
        if (p && p.catch) p.catch((e) => { if (e && e.name === "NotAllowedError") this.dernierBloque = true; if (!(e && e.name === "AbortError")) terminer(false); });
      });
    }
  }

  /* ── Repli sur la voix du navigateur ────────────────────────────────────────────────────────────
     1) Jamais un énoncé par virgule : les segments qui finissent par « , ; : » sont rattachés à la phrase
        suivante (un ancien pont découpait encore ainsi ; chaque énoncé repartait de zéro et hachait la
        réplique). 2) Tempo propre à chaque phrase si le pont ne l'a pas fixé. 3) Les voix les plus naturelles
        d'abord : neuronales (« Natural », dont les voix québécoises de Microsoft Edge), « Premium »,
        « Améliorée », puis standard ; les voix anciennes ou de fantaisie en dernier. */
  function phrasesNavigateur(segments, base = {}) {
    const out = [];
    let cour = null;
    for (const s of segments || []) {
      const t = String(s.texte || "").trim();
      if (!t) continue;
      if (!cour) cour = { ...s, texte: t };
      else cour.texte += " " + t;
      cour.pause_apres_ms = s.pause_apres_ms || 0;
      if (!/[,;:]$/.test(t) || cour.texte.length > 260) { out.push(cour); cour = null; }
    }
    if (cour) out.push(cour);
    let g = 0x811c9dc5;
    const txt = out.map((x) => x.texte).join(" ");
    for (let i = 0; i < txt.length; i++) { g ^= txt.charCodeAt(i); g = Math.imul(g, 0x01000193); }
    const alea = () => { g = (g + 0x6d2b79f5) >>> 0; let t = g; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
    return out.map((x, i) => {
      const d = x.debit ?? (base.debit || 1) * (1 + (alea() - 0.5) * 0.08) * (i === out.length - 1 && out.length > 2 ? 0.96 : 1);
      const fin = x.texte.slice(-1);
      const h = x.hauteur ?? (base.hauteur || 1) * (fin === "?" ? 1.04 : fin === "!" ? 1.03 : 1) * (1 + (alea() - 0.5) * 0.03);
      const pause = i === out.length - 1 ? 0 : Math.max(x.pause_apres_ms || 0, fin === "…" ? 650 : 380);
      return { ...x, debit: +Math.min(1.6, Math.max(0.6, d)).toFixed(3), hauteur: +Math.min(1.6, Math.max(0.4, h)).toFixed(3), pause_apres_ms: pause };
    });
  }
  const ANCIENNES = /\beddy\b|\bflo\b|grandma|grandpa|\breed\b|rocko|\bsandy\b|shelley|compact|espeak|robot|albert|bad news|good news|\bbells\b|boing|bubbles|cellos|jester|\borgan\b|superstar|trinoids|whisper|wobble|zarvox|bahh/i;
  function qualiteVoix(v) {
    const n = (v && v.name) || "";
    if (ANCIENNES.test(n)) return 0;
    if (/natural|neural|naturel/i.test(n)) return 4;
    if (/premium/i.test(n)) return 3;
    if (/enhanced|am[ée]lior[ée]e?|siri/i.test(n)) return 2;
    return 1;
  }
  /* Voix françaises de la meilleure à la moins bonne ; à qualité égale, le français du Canada d'abord. */
  function classerVoix(voix, { localesSeulement = false } = {}) {
    return (voix || []).filter((v) => v && /^fr/i.test(v.lang || "") && (!localesSeulement || v.localService !== false))
      .map((v, i) => ({ v, s: qualiteVoix(v) * 10 + (/fr[-_]ca/i.test(v.lang) ? 3 : 0) + (v.localService !== false ? 1 : 0), i }))
      .sort((a, b) => b.s - a.s || a.i - b.i).map((x) => x.v);
  }

  const api = { base, absolue, creer, itemsRepetition, texteDe, Lecteur, phrasesNavigateur, qualiteVoix, classerVoix };
  racine.VoixNeurale = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
