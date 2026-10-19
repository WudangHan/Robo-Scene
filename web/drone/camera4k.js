/* Robo-Scène — caméra du drone : image virtuelle (rendu de la caméra embarquée) et flux réel 4K.

   Virtuelle : aperçu en direct, image fixe rendue à 3840 × 2160 (UHD « 4K ») et enregistrement WebM du canevas.
   Réelle : deux voies, sans aucun logiciel propriétaire dans la page.
     1. Carte de capture HDMI → USB (UVC) branchée sur la sortie HDMI de la radiocommande ou du récepteur vidéo :
        elle se présente comme une webcam ; la page demande 3840 × 2160 à 30 i/s (contraintes « ideal ») et affiche
        la définition réellement obtenue, que le navigateur peut abaisser selon le matériel.
     2. Flux WebRTC lu par WHEP (WebRTC-HTTP Egress Protocol, projet IETF draft-ietf-wish-whep) : un serveur tel que
        MediaMTX reçoit le flux RTSP ou SRT de la caméra du drone et le sert à l'adresse http://hôte:8889/<chemin>/whep.
   Garde-fou G-06 : la plateforme n'enregistre ni ne conserve aucune image du flux réel (aucune option ne le permet) ;
   seule la caméra virtuelle, qui ne filme aucune personne, peut être enregistrée. */
import * as THREE from "three";

export const UHD = { largeur: 3840, hauteur: 2160 };

export class CameraVirtuelle {
  constructor(canevas, theatre) {
    this.theatre = theatre;
    this.rendu = new THREE.WebGLRenderer({ canvas: canevas, antialias: true, preserveDrawingBuffer: true });
    this.rendu.outputColorSpace = THREE.SRGBColorSpace; this.rendu.toneMapping = THREE.ACESFilmicToneMapping;
    this.rendu.shadowMap.enabled = true;
    this.definition = [1280, 720];
    this.rendu.setPixelRatio(1); this.rendu.setSize(...this.definition, false);
    this.enregistreur = null; this.morceaux = []; this.debutEnr = 0;
  }
  regler(largeur, hauteur) { this.definition = [largeur, hauteur]; this.rendu.setSize(largeur, hauteur, false); }
  rendre() { this.theatre.rendreCamera(this.rendu); }

  /* Image fixe à la définition UHD, rendue hors écran puis restituée en PNG. */
  async photo4K() {
    const [w, h] = this.definition;
    this.rendu.setSize(UHD.largeur, UHD.hauteur, false);
    this.theatre.rendreCamera(this.rendu);
    const blob = await new Promise((ok) => this.rendu.domElement.toBlob(ok, "image/png"));
    this.rendu.setSize(w, h, false);
    return blob;
  }

  get enregistre() { return !!this.enregistreur && this.enregistreur.state === "recording"; }

  demarrerEnregistrement(ips = 30) {
    if (this.enregistre) return;
    const flux = this.rendu.domElement.captureStream(ips);
    const types = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm", "video/mp4"];
    const type = types.find((t) => window.MediaRecorder?.isTypeSupported?.(t));
    if (!type) throw new Error("Enregistrement vidéo non pris en charge par ce navigateur");
    this.morceaux = [];
    this.enregistreur = new MediaRecorder(flux, { mimeType: type, videoBitsPerSecond: this.definition[0] >= 3840 ? 40e6 : 12e6 });
    this.enregistreur.ondataavailable = (e) => e.data.size && this.morceaux.push(e.data);
    this.enregistreur.start(500); this.debutEnr = performance.now(); this.type = type;
  }

  arreterEnregistrement() {
    return new Promise((ok) => {
      if (!this.enregistreur) return ok(null);
      this.enregistreur.onstop = () => { ok(new Blob(this.morceaux, { type: this.type })); this.enregistreur = null; };
      this.enregistreur.stop();
    });
  }
}

/* Sources vidéo réelles. Aucun enregistrement : l'élément <video> ne fait qu'afficher. */
export class FluxReel {
  constructor(video) { this.video = video; this.flux = null; this.pc = null; this.session = null; this.source = null; }

  static async cameras() {
    if (!navigator.mediaDevices?.enumerateDevices) return [];
    return (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput");
  }

  async ouvrirCapture(deviceId) {
    await this.fermer();
    if (!navigator.mediaDevices?.getUserMedia) throw new Error("Capture vidéo indisponible (page non sécurisée ou navigateur trop ancien)");
    const contraintes = { audio: false, video: { width: { ideal: 3840 }, height: { ideal: 2160 }, frameRate: { ideal: 30 } } };
    if (deviceId) contraintes.video.deviceId = { exact: deviceId };
    this.flux = await navigator.mediaDevices.getUserMedia(contraintes);
    this.video.srcObject = this.flux; await this.video.play().catch(() => {});
    this.source = "capture";
    return this.reglages();
  }

  reglages() {
    const piste = this.flux?.getVideoTracks?.()[0];
    const s = piste?.getSettings?.() || {};
    return { largeur: s.width || this.video.videoWidth || 0, hauteur: s.height || this.video.videoHeight || 0,
      ips: s.frameRate ? Math.round(s.frameRate) : null, nom: piste?.label || this.source || "" };
  }

  /* Lecture WHEP : offre SDP en réception seule, POST application/sdp, réponse 201 avec l'adresse de session. */
  async ouvrirWHEP(url, jeton = "") {
    await this.fermer();
    if (location.protocol === "https:" && url.startsWith("http:")) {
      throw new Error("Page en ligne (https) et serveur vidéo en http : le navigateur bloque ce « contenu mixte ». Ouvrez la version locale de la page (servie par le pont) ou servez WHEP en https.");
    }
    const pc = (this.pc = new RTCPeerConnection());
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.addTransceiver("audio", { direction: "recvonly" });
    this.flux = new MediaStream();
    pc.ontrack = (e) => { this.flux.addTrack(e.track); this.video.srcObject = this.flux; this.video.play().catch(() => {}); };
    await pc.setLocalDescription(await pc.createOffer());
    await new Promise((ok) => {               // candidats ICE regroupés dans l'offre (pas de « trickle » ici)
      if (pc.iceGatheringState === "complete") return ok();
      const fin = () => { if (pc.iceGatheringState === "complete") { pc.removeEventListener("icegatheringstatechange", fin); ok(); } };
      pc.addEventListener("icegatheringstatechange", fin); setTimeout(ok, 2000);
    });
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/sdp", ...(jeton ? { Authorization: `Bearer ${jeton}` } : {}) }, body: pc.localDescription.sdp });
    if (r.status !== 201 && r.status !== 200) throw new Error(`Serveur WHEP : HTTP ${r.status}`);
    const loc = r.headers.get("Location");
    this.session = loc ? new URL(loc, url).href : null;
    await pc.setRemoteDescription({ type: "answer", sdp: await r.text() });
    this.source = "whep";
    return new Promise((ok) => {
      const t0 = performance.now();
      const att = () => (this.video.videoWidth || performance.now() - t0 > 6000 ? ok(this.reglages()) : setTimeout(att, 200));
      att();
    });
  }

  async fermer() {
    if (this.session) { try { await fetch(this.session, { method: "DELETE" }); } catch (e) { /* serveur déjà fermé */ } }
    this.session = null;
    this.pc?.close(); this.pc = null;
    this.flux?.getTracks().forEach((t) => t.stop()); this.flux = null;
    this.video.srcObject = null; this.source = null;
  }
}

/* Surimpression de cadrage (grille des tiers, zones de sécurité, horizon, mentions) dans un canevas 2D. */
export function dessinerCadre(ctx, w, h, o = {}) {
  ctx.clearRect(0, 0, w, h);
  ctx.lineWidth = Math.max(1, w / 900);
  if (o.tiers) {
    ctx.strokeStyle = "rgba(255,255,255,.35)";
    for (const f of [1 / 3, 2 / 3]) { ctx.beginPath(); ctx.moveTo(w * f, 0); ctx.lineTo(w * f, h); ctx.moveTo(0, h * f); ctx.lineTo(w, h * f); ctx.stroke(); }
    ctx.strokeStyle = "rgba(242,181,68,.45)"; ctx.setLineDash([6, 6]); ctx.strokeRect(w * 0.05, h * 0.05, w * 0.9, h * 0.9); ctx.setLineDash([]);
  }
  if (o.horizon !== undefined) {
    const y = h / 2 - (o.horizon / 45) * (h / 2);
    ctx.strokeStyle = "rgba(111,168,255,.6)"; ctx.beginPath(); ctx.moveTo(w * 0.42, y); ctx.lineTo(w * 0.58, y); ctx.stroke();
  }
  const fs = Math.max(11, Math.round(w / 60));
  ctx.font = `600 ${fs}px ui-monospace, Menlo, monospace`; ctx.textBaseline = "top";
  ctx.fillStyle = "rgba(0,0,0,.55)"; ctx.fillRect(8, 8, ctx.measureText(o.texte || "").width + 14, fs + 8);
  ctx.fillStyle = "#e7e9ee"; ctx.fillText(o.texte || "", 15, 12);
  if (o.rec) { ctx.fillStyle = "#ff3b3b"; ctx.beginPath(); ctx.arc(w - fs * 5.2, 12 + fs / 2, fs / 2.4, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = "#fff"; ctx.fillText(o.rec, w - fs * 4.4, 12); }
  if (o.alerte) {
    ctx.fillStyle = "rgba(160,20,30,.75)"; const tw = ctx.measureText(o.alerte).width + 20;
    ctx.fillRect((w - tw) / 2, h - fs - 22, tw, fs + 12); ctx.fillStyle = "#fff"; ctx.fillText(o.alerte, (w - tw) / 2 + 10, h - fs - 16);
  }
}
