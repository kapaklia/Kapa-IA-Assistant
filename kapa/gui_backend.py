"""Collegamento GUI-demone con sola libreria standard.

Nessun import di Groq, Qt, Whisper o del motore: aprire la GUI è veloce.
Il processo vocale rimane separato e continua a usare la hotkey esistente.
"""

from __future__ import annotations

import ast
import os
import re
import socket
import subprocess
import sys
from pathlib import Path
from .app_paths import SOCKET_PATH, PROJECT_DIR, data_dir, private_append

GUI_LOG = data_dir() / "gui-avvio.log"
VOICE_LOG = data_dir() / "trascrizioni.log"
VALID_COMMANDS = frozenset({"stato", "toggle", "esci", "hotkey-stato", "hotkey-configura"})
VALID_STATES = frozenset({"attesa", "ascolto", "elaborazione"})


class AssistantError(Exception):
    """Errore gestibile nell'interfaccia, senza terminare la GUI."""


def send_command(command: str, socket_path: Path = SOCKET_PATH, timeout: float = 0.5) -> str:
    """Protocollo già presente in demone.py; mai avvia una shell."""
    if command not in VALID_COMMANDS:
        raise ValueError("Comando socket non ammesso")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(timeout)
        conn.connect(str(socket_path))
        conn.sendall(command.encode("utf-8"))
        return conn.recv(64).decode("utf-8", "replace").strip()


def get_state(socket_path: Path = SOCKET_PATH) -> str | None:
    """None significa non disponibile, inclusa la fase di caricamento."""
    try:
        value = send_command("stato", socket_path)
        return value if value in VALID_STATES else None
    except (OSError, ConnectionError):
        return None


def file_tail(path: Path, max_bytes: int = 18000) -> str:
    """Legge solo la coda dei log, senza caricare conversazioni intere in RAM."""
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            end = stream.tell()
            stream.seek(max(0, end - max_bytes))
            raw = stream.read()
        text = raw.decode("utf-8", "replace")
        if end > max_bytes and "\n" in text:
            remainder = text.split("\n", 1)[1]
            if remainder.strip():
                text = remainder
        return text.rstrip()
    except (FileNotFoundError, PermissionError, OSError):
        return ""


def last_transcription(path: Path = VOICE_LOG) -> str:
    """Estrae l'ultima frase riconosciuta; non legge i dati tramite Groq."""
    for line in reversed(file_tail(path, 12000).splitlines()):
        match = re.search(r"\| sentito: (.*?) \| esito:", line)
        if match:
            try:
                text = ast.literal_eval(match.group(1))
                if isinstance(text, str) and text.strip():
                    return text.strip()
            except (ValueError, SyntaxError):
                continue
    return ""




def last_response(path: Path = VOICE_LOG) -> str:
    """L'ultima risposta completa dell'assistente, non la trascrizione."""
    for line in reversed(file_tail(path, 24000).splitlines()):
        match = re.search(r"\| sentito: .*? \| esito: (.*)$", line)
        if match:
            value = match.group(1).strip()
            if value:
                return value
    return ""

class AssistantController:
    """GUI come pannello di controllo, non come sostituto del demone."""

    def __init__(self, project_dir: Path = PROJECT_DIR,
                 socket_path: Path = SOCKET_PATH, python_executable: str | None = None):
        self.project_dir = Path(project_dir)
        self.socket_path = Path(socket_path)
        self.python_executable = python_executable or sys.executable
        self.process: subprocess.Popen | None = None
        self._loading = False
        self._gui_log = GUI_LOG if self.project_dir == PROJECT_DIR else self.project_dir / GUI_LOG.name
        self._voice_log = VOICE_LOG if self.project_dir == PROJECT_DIR else self.project_dir / VOICE_LOG.name

    def state(self) -> str | None:
        return get_state(self.socket_path)

    def is_starting(self) -> bool:
        if self._loading and self.process and self.process.poll() is not None:
            self._loading = False
        state = self.state()
        if state:
            self._loading = False
        return self._loading and state is None

    def start(self) -> str:
        if self.state():
            return "L'assistente è già attivo."
        if self.is_starting():
            return "Caricamento già in corso."
        main = self.project_dir / "main.py"
        if not main.is_file():
            raise AssistantError("Non trovo main.py nella cartella del progetto.")
        try:
            # Il logfile non contiene chiavi API per scelta di questa GUI;
            # eventuali errori stampati dal motore possono però contenere dati privati.
            with private_append(self._gui_log) as logfile:
                logfile.write("\n--- Avvio da interfaccia ---\n")
            with private_append(self._gui_log, binary=True) as logfile:
                self.process = subprocess.Popen(
                    [self.python_executable, "-u", str(main), "--background"],
                    cwd=str(self.project_dir),
                    stdin=subprocess.DEVNULL,
                    stdout=logfile,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                )
            self._loading = True
            return "Avvio in corso: caricamento del modello vocale…"
        except OSError as exc:
            raise AssistantError(f"Non riesco ad avviare l'assistente: {exc}") from exc

    def stop(self) -> str:
        if self.state():
            try:
                reply = send_command("esci", self.socket_path)
                return "Arresto richiesto." if reply == "ok" else f"Risposta: {reply}"
            except OSError as exc:
                raise AssistantError(f"Non riesco a fermare l'assistente: {exc}") from exc
        if self.is_starting() and self.process:
            # Possiamo fermare solo il caricamento che questa finestra ha avviato.
            self.process.terminate()
            self._loading = False
            return "Caricamento annullato."
        return "L'assistente non è in esecuzione."

    def hotkey_state(self) -> str:
        try:
            return send_command("hotkey-stato", self.socket_path)
        except OSError:
            return "non_disponibile"

    def configure_hotkey(self) -> str:
        try:
            return send_command("hotkey-configura", self.socket_path)
        except OSError as exc:
            raise AssistantError("Avvia prima l'assistente per configurare la scorciatoia.") from exc

    def listen(self) -> str:
        state = self.state()
        if state is None:
            raise AssistantError("Avvia prima l'assistente.")
        if state == "elaborazione":
            return "Sto ancora elaborando la richiesta precedente."
        try:
            result = send_command("toggle", self.socket_path)
            return {
                "ascolto": "Microfono attivato.",
                "stop": "Fine ascolto richiesta.",
                "occupato": "Sto elaborando la richiesta precedente.",
            }.get(result, f"Risposta assistente: {result}")
        except OSError as exc:
            raise AssistantError(f"Comunicazione non riuscita: {exc}") from exc

    def logs(self) -> str:
        # Quando la GUI ha avviato il demone, il suo stdout contiene anche
        # APERTO/CHIUSO, trascrizione e risposta. Se il demone è stato avviato
        # da Konsole o systemd, mostriamo la cronologia vocale disponibile.
        if self.process is not None or (self._gui_log.exists() and
                (not self._voice_log.exists() or
                 self._gui_log.stat().st_mtime >= self._voice_log.stat().st_mtime)):
            return file_tail(self._gui_log)
        return file_tail(self._voice_log)

    def latest_response(self) -> str:
        return last_response(self._voice_log)

    def latest_activity(self) -> dict:
        from .attivita import ultima_attivita, ACTIVITY_LOG
        path = ACTIVITY_LOG if self.project_dir == PROJECT_DIR else self.project_dir / ACTIVITY_LOG.name
        return ultima_attivita(path)

    def latest_text(self) -> str:
        # Durante l'elaborazione il log della GUI può già contenere la riga
        # '🗣️'; il registro delle trascrizioni viene scritto a richiesta finita.
        if self.process is not None:
            for line in reversed(file_tail(self._gui_log, 12000).splitlines()):
                if "🗣" in line:
                    _, _, text = line.partition("🗣")
                    return text.strip("️  ")
        return last_transcription(self._voice_log)
