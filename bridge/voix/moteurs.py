"""Moteurs de synthèse vocale neuronale : Eleven v3 (ElevenLabs), voix neuronales d'Azure (dont fr-CA),
gpt-4o-mini-tts (OpenAI) et Piper (local, hors ligne).

Chaque moteur reçoit une partition prosodique (partition.py), la traduit dans sa langue de commande et rend
un fichier audio, avec ce qui a été DEMANDÉ et ce qui a été réellement envoyé (traçabilité A-08 du cahier).
Les moteurs distants ne reçoivent jamais un contenu que le routeur de sensibilité D03 a écarté : ce tri se
fait en amont, dans service.py.

Paramètres vérifiés dans la documentation des éditeurs le 31 octobre 2026 :
* Eleven v3 : modèle « eleven_v3 », balises de jeu entre crochets ([sighs], [whispers]…), pas de balise SSML
  <break> ; vitesse dans voice_settings (0,7 à 1,2) ; sortie PCM brute (pcm_24000) ; point d'accès
  « with-timestamps » qui rend l'alignement caractère par caractère (synchronisation des lèvres).
* Azure : voix neuronales fr-CA-SylvieNeural, fr-CA-JeanNeural, fr-CA-AntoineNeural, fr-CA-ThierryNeural ;
  SSML (prosody, break), sortie riff-24khz-16bit-mono-pcm.
* OpenAI : modèle gpt-4o-mini-tts, paramètre « instructions » (ton, émotion, rythme, accent), « speed »,
  sortie wav.
"""
from __future__ import annotations

import base64
import io
import json
import os
import shutil
import struct
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import partition as P

Transport = Callable[[str, bytes, dict[str, str], float], tuple[bytes, str]]


class ErreurVoix(Exception):
    pass


@dataclass
class Audio:
    donnees: bytes
    format: str                      # "wav" ou "mp3"
    duree_ms: int
    moteur: str
    modele: str
    voix: str
    mots: list[dict[str, Any]] = field(default_factory=list)   # [{mot, t_ms}] si le moteur fournit l'alignement
    envoye: dict[str, Any] = field(default_factory=dict)        # commande exacte (texte balisé, SSML, consigne)
    distant: bool = True


# ── Utilitaires audio ─────────────────────────────────────────────────────────────────────────────────
def pcm_vers_wav(pcm: bytes, taux: int = 24000, canaux: int = 1, largeur: int = 2) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(canaux)
        w.setsampwidth(largeur)
        w.setframerate(taux)
        w.writeframes(pcm)
    return b.getvalue()


def duree_wav_ms(donnees: bytes) -> int:
    try:
        with wave.open(io.BytesIO(donnees), "rb") as w:
            return int(w.getnframes() / max(1, w.getframerate()) * 1000)
    except (wave.Error, EOFError, struct.error):
        return 0


def concatener_wav(morceaux: list[tuple[bytes, int]]) -> bytes:
    """Assemble des WAV de même format, chacun suivi d'un silence (ms)."""
    params = None
    pcm = bytearray()
    for donnees, silence in morceaux:
        with wave.open(io.BytesIO(donnees), "rb") as w:
            p = (w.getnchannels(), w.getsampwidth(), w.getframerate())
            if params and p != params:
                raise ErreurVoix("formats WAV incompatibles")
            params = p
            pcm += w.readframes(w.getnframes())
            pcm += b"\x00" * (int(p[2] * silence / 1000) * p[0] * p[1])
    if not params:
        return b""
    return pcm_vers_wav(bytes(pcm), params[2], params[0], params[1])


def _http(url: str, corps: bytes, entetes: dict[str, str], delai: float) -> tuple[bytes, str]:
    from ..tls import contexte
    req = urllib.request.Request(url, data=corps, headers=entetes, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=delai, context=contexte()) as r:
            return r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raise ErreurVoix(f"HTTP {e.code} : {e.read().decode('utf-8', 'replace')[:300]}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ErreurVoix(f"réseau : {e}") from e


# ── Base ──────────────────────────────────────────────────────────────────────────────────────────────
class Moteur:
    nom = "?"
    libelle = "?"
    distant = True
    variable_cle = ""

    def __init__(self, cfg: dict[str, Any] | None = None, transport: Transport | None = None):
        self.cfg = dict(cfg or {})
        self.transport = transport or _http
        self.delai = float(self.cfg.get("delai_s", 45))

    def cle(self) -> str:
        return os.environ.get(self.variable_cle, "") if self.variable_cle else ""

    def voix_pour(self, role: str, indice: int = 0, profil: str | None = None) -> str:
        """Voix configurée pour un rôle (« partenaire », « avatar », « direction ») et un indice de distribution."""
        if role == "direction" and profil:
            d = self.cfg.get("direction", {}) or {}
            if d.get(profil):
                return d[profil]
        liste = self.cfg.get(f"voix_{role}") or self.cfg.get("voix_partenaire") or []
        if isinstance(liste, str):
            liste = [liste]
        return liste[indice % len(liste)] if liste else ""

    def disponible(self) -> tuple[bool, str]:
        if self.variable_cle and not self.cle():
            return False, f"variable {self.variable_cle} absente"
        if not self.voix_pour("partenaire"):
            return False, "aucune voix configurée"
        return True, ""

    def empreinte(self) -> dict[str, Any]:
        """Ce qui, en plus du texte et de la partition, change le son : sert à la clé du cache."""
        return {"moteur": self.nom, "modele": self.cfg.get("modele", "")}

    def synthetiser(self, part: dict[str, Any], voix: str) -> Audio:  # pragma: no cover - abstrait
        raise NotImplementedError


# ── ElevenLabs (Eleven v3) ────────────────────────────────────────────────────────────────────────────
class MoteurElevenLabs(Moteur):
    nom = "elevenlabs"
    libelle = "ElevenLabs — Eleven v3 (jeu le plus expressif)"
    variable_cle = "ELEVENLABS_API_KEY"

    def empreinte(self):
        return {"moteur": self.nom, "modele": self.cfg.get("modele", "eleven_v3")}

    def synthetiser(self, part, voix):
        cmd = P.vers_elevenlabs(part)
        modele = self.cfg.get("modele", "eleven_v3")
        corps = {"text": cmd["text"][:4800], "model_id": modele, "language_code": "fr",
                 "voice_settings": cmd["voice_settings"]}
        url = (f"https://api.elevenlabs.io/v1/text-to-speech/{urllib.parse.quote(voix)}/with-timestamps"
               f"?output_format=pcm_24000")
        brut, _ = self.transport(url, json.dumps(corps).encode("utf-8"),
                                 {"xi-api-key": self.cle(), "Content-Type": "application/json",
                                  "Accept": "application/json"}, self.delai)
        try:
            rep = json.loads(brut.decode("utf-8"))
            pcm = base64.b64decode(rep["audio_base64"])
        except (ValueError, KeyError) as e:
            raise ErreurVoix(f"réponse ElevenLabs illisible : {e}") from e
        wav = pcm_vers_wav(pcm, 24000)
        return Audio(wav, "wav", duree_wav_ms(wav), self.nom, modele, voix,
                     mots=mots_depuis_alignement(rep.get("alignment") or rep.get("normalized_alignment") or {}),
                     envoye={"texte_balise": corps["text"], "voice_settings": corps["voice_settings"]})


def mots_depuis_alignement(al: dict[str, Any]) -> list[dict[str, Any]]:
    """Alignement caractère par caractère (ElevenLabs) → début de chaque mot dit, balises [..] exclues."""
    car = al.get("characters") or []
    debuts = al.get("character_start_times_seconds") or []
    mots, courant, t0, dans_balise = [], "", None, False
    for c, t in zip(car, debuts):
        if c == "[":
            dans_balise = True
        if dans_balise:
            if c == "]":
                dans_balise = False
            continue
        if c.isalnum() or c in "'’-":
            if not courant:
                t0 = t
            courant += c
        elif courant:
            mots.append({"mot": courant, "t_ms": int(t0 * 1000)})
            courant = ""
    if courant:
        mots.append({"mot": courant, "t_ms": int((t0 or 0) * 1000)})
    return mots


# ── Azure (voix neuronales, dont fr-CA) ───────────────────────────────────────────────────────────────
class MoteurAzure(Moteur):
    nom = "azure"
    libelle = "Azure — voix neuronales québécoises (SSML)"
    variable_cle = "AZURE_SPEECH_KEY"

    def region(self) -> str:
        return os.environ.get("AZURE_SPEECH_REGION", "") or self.cfg.get("region", "")

    def disponible(self):
        ok, motif = super().disponible()
        if ok and not self.region():
            return False, "région Azure absente (AZURE_SPEECH_REGION ou [voix.azure].region)"
        return ok, motif

    def synthetiser(self, part, voix):
        styles = (self.cfg.get("styles", {}) or {}).get(voix, {}) or {}
        style = styles.get(part["emotion"]) if isinstance(styles, dict) else None
        langue = "-".join(voix.split("-")[:2]) if voix.count("-") >= 2 else part.get("langue", "fr-CA")
        ssml = P.vers_ssml(part, voix, langue, style)
        url = f"https://{self.region()}.tts.speech.microsoft.com/cognitiveservices/v1"
        donnees, _ = self.transport(url, ssml.encode("utf-8"),
                                    {"Ocp-Apim-Subscription-Key": self.cle(), "Content-Type": "application/ssml+xml",
                                     "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
                                     "User-Agent": "robo-scene"}, self.delai)
        if donnees[:4] != b"RIFF":
            raise ErreurVoix("réponse Azure : WAV attendu")
        return Audio(donnees, "wav", duree_wav_ms(donnees), self.nom, "neural", voix, envoye={"ssml": ssml})


# ── OpenAI (gpt-4o-mini-tts, consigne de jeu) ─────────────────────────────────────────────────────────
class MoteurOpenAI(Moteur):
    nom = "openai"
    libelle = "OpenAI — gpt-4o-mini-tts (consigne de jeu)"
    variable_cle = "OPENAI_API_KEY"

    def empreinte(self):
        return {"moteur": self.nom, "modele": self.cfg.get("modele", "gpt-4o-mini-tts"), "accent": self.cfg.get("accent", "québécois")}

    def synthetiser(self, part, voix):
        cmd = P.vers_openai(part, self.cfg.get("accent", "québécois"))
        modele = self.cfg.get("modele", "gpt-4o-mini-tts")
        corps = {"model": modele, "voice": voix, "input": cmd["input"][:4000], "instructions": cmd["instructions"],
                 "response_format": "wav", "speed": cmd["speed"]}
        donnees, _ = self.transport("https://api.openai.com/v1/audio/speech", json.dumps(corps).encode("utf-8"),
                                    {"Authorization": f"Bearer {self.cle()}", "Content-Type": "application/json"},
                                    self.delai)
        if donnees[:4] != b"RIFF":
            raise ErreurVoix("réponse OpenAI : WAV attendu")
        return Audio(donnees, "wav", duree_wav_ms(donnees), self.nom, modele, voix,
                     envoye={"instructions": corps["instructions"], "speed": corps["speed"]})


# ── Piper (local, hors ligne) ─────────────────────────────────────────────────────────────────────────
class MoteurPiper(Moteur):
    """Synthèse locale : aucun texte ne quitte l'ordinateur (seul moteur admis pour un contenu sensible, D03).
    Les voix Piper françaises disponibles sont de France (siwis, upmc, tom) : pas d'accent québécois."""
    nom = "piper"
    libelle = "Piper — local, hors ligne (voix de France)"
    distant = False

    def __init__(self, cfg=None, transport=None, executer: Callable[..., bytes] | None = None):
        super().__init__(cfg, transport)
        self.interne = executer is None              # vrai : Piper installé sur ce poste (sinon exécutant de test)
        self.executer = executer or self._executer

    def _modele(self, voix: str) -> Path | None:
        if not voix:
            return None
        p = Path(voix).expanduser()
        if not p.is_absolute():
            p = Path(self.cfg.get("dossier_modeles", "~/.local/share/piper")).expanduser() / voix
        if p.suffix != ".onnx":
            p = p.with_name(p.name + ".onnx")
        return p if p.exists() else None

    @staticmethod
    def _api_python():
        try:
            import piper  # type: ignore
            return piper if hasattr(piper, "PiperVoice") else None
        except ImportError:
            return None

    def disponible(self):
        if not self.voix_pour("partenaire"):
            return False, "aucune voix Piper configurée"
        if self.interne and not (self._api_python() or shutil.which(self.cfg.get("binaire", "piper"))):
            return False, "Piper introuvable (pip install piper-tts)"
        if self.interne and not self._modele(self.voix_pour("partenaire")):
            return False, "modèle .onnx introuvable"
        return True, ""

    def _executer(self, modele: Path, texte: str, length_scale: float, noise_scale: float, noise_w: float) -> bytes:
        piper = self._api_python()
        if piper is not None:                     # bibliothèque piper-tts (API Python : PiperVoice, SynthesisConfig)
            if not hasattr(self, "_voix_chargees"):
                self._voix_chargees: dict[str, Any] = {}
            v = self._voix_chargees.get(str(modele)) or piper.PiperVoice.load(str(modele))
            self._voix_chargees[str(modele)] = v
            conf = None
            if hasattr(piper, "SynthesisConfig"):
                conf = piper.SynthesisConfig(length_scale=length_scale, noise_scale=noise_scale, noise_w_scale=noise_w)
            b = io.BytesIO()
            with wave.open(b, "wb") as w:
                v.synthesize_wav(texte, w, syn_config=conf) if conf else v.synthesize_wav(texte, w)
            return b.getvalue()
        with tempfile.TemporaryDirectory() as d:   # programme en ligne de commande (anciennes versions)
            sortie = Path(d) / "p.wav"
            subprocess.run([self.cfg.get("binaire", "piper"), "--model", str(modele), "--output_file", str(sortie),
                            "--length_scale", str(length_scale), "--noise_scale", str(noise_scale),
                            "--noise_w", str(noise_w)], input=texte.encode("utf-8"), check=True,
                           capture_output=True, timeout=self.delai)
            return sortie.read_bytes()

    def synthetiser(self, part, voix):
        modele = self._modele(voix) if self.interne else Path(voix)
        if modele is None:
            raise ErreurVoix(f"modèle Piper introuvable : {voix}")
        morceaux = []
        for s in P.vers_piper(part):
            try:
                morceaux.append((self.executer(modele, s["texte"], s["length_scale"], s["noise_scale"], s["noise_w"]),
                                 s["silence_ms"]))
            except (subprocess.SubprocessError, OSError) as e:
                raise ErreurVoix(f"piper : {e}") from e
        wav = concatener_wav(morceaux)
        return Audio(wav, "wav", duree_wav_ms(wav), self.nom, "piper", Path(voix).name, distant=False,
                     envoye={"phrases": P.vers_piper(part)})


CLASSES = {c.nom: c for c in (MoteurElevenLabs, MoteurAzure, MoteurOpenAI, MoteurPiper)}
