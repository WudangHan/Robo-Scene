"""Pilote « programme externe » : un pilote écrit dans N'IMPORTE QUEL langage (Python, JavaScript, C++,
Rust, Go…) est lancé comme sous-processus ; il lit le langage unifié sur son entrée standard et répond sur sa
sortie standard, un objet JSON par ligne — exactement le contrat de PROTOCOLE.md. Les gabarits du dossier
sdk/ (Python, JavaScript, C++, Arduino) implémentent ce contrat.

Le flux d'erreur du programme est relayé au journal de séance ; s'il s'arrête, le pont le relance.
"""
from __future__ import annotations

import asyncio
import json
import shlex
from pathlib import Path
from typing import Any

from .base import Pilote
from ... import transports


class PiloteExterne(Pilote):
    type = "externe"

    def __init__(self, desc, racine: Path | None = None):
        super().__init__(desc)
        c = desc.connexion
        cmd = c.get("commande")
        if not cmd:
            raise ValueError("Pilote externe : préciser [connexion] commande = [\"programme\", \"argument\", …]")
        self.commande = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
        self.dossier = Path(c.get("dossier") or racine or ".")
        self._proc: asyncio.subprocess.Process | None = None

    async def ouvrir(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            *self.commande, cwd=str(self.dossier), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        asyncio.create_task(self._relayer_erreurs())

    async def _relayer_erreurs(self) -> None:
        while self._proc and self._proc.stderr:
            ligne = await self._proc.stderr.readline()
            if not ligne:
                return
            self.pousser({"t": "err", "msg": f"[{self.commande[0]}] {ligne.decode('utf-8', 'replace').strip()[:300]}",
                          "niveau": "info"})

    async def envoyer(self, msg: dict[str, Any]) -> None:
        if not self._proc or self._proc.returncode is not None:
            raise ConnectionError("programme pilote arrêté")
        self._proc.stdin.write((json.dumps(msg, separators=(",", ":")) + "\n").encode())
        await self._proc.stdin.drain()

    async def recevoir(self) -> dict[str, Any]:
        while True:
            if not self._file.empty():
                return self._file.get_nowait()
            lecture = asyncio.ensure_future(self._proc.stdout.readline())
            attente = asyncio.ensure_future(self._file.get())
            fait, _ = await asyncio.wait({lecture, attente}, return_when=asyncio.FIRST_COMPLETED)
            if attente in fait:
                lecture.cancel()
                return attente.result()
            attente.cancel()
            ligne = lecture.result()
            if not ligne:
                return {"t": "lien", "etat": "perdu", "msg": f"programme pilote terminé (code {self._proc.returncode})"}
            m = transports._decoder(ligne)
            if m is not None:
                return m

    async def fermer(self) -> None:
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.stdin.close()
                await asyncio.wait_for(self._proc.wait(), 2)
            except (asyncio.TimeoutError, BrokenPipeError, ConnectionResetError):
                self._proc.kill()
