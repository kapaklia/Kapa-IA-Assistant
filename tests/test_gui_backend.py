"""Test del pannello di controllo: non richiedono PySide6 o Groq."""
import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kapa.gui_backend import (
    AssistantController, AssistantError, file_tail, get_state, last_transcription, send_command,
)
import pytest


class StubServer:
    def __init__(self, path):
        self.path = path
        self.requests = []
        self.state = 'attesa'
        self.stop_event = threading.Event()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self.serve, daemon=True)

    def __enter__(self):
        self.thread.start()
        assert self.ready.wait(2)
        return self

    def __exit__(self, *_):
        self.stop_event.set()
        self.thread.join(2)

    def serve(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(self.path))
            server.listen()
            server.settimeout(0.05)
            self.ready.set()
            while not self.stop_event.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                with conn:
                    cmd = conn.recv(64).decode()
                    self.requests.append(cmd)
                    if cmd == 'stato':
                        reply = self.state
                    elif cmd == 'toggle':
                        self.state = 'ascolto' if self.state == 'attesa' else 'attesa'
                        reply = 'ascolto' if self.state == 'ascolto' else 'stop'
                    elif cmd == 'esci':
                        self.state = 'stopped'
                        reply = 'ok'
                    else:
                        reply = 'unknown'
                    conn.sendall(reply.encode())
            self.path.unlink(missing_ok=True)


def test_socket_protocol(tmp_path):
    sock = tmp_path / 'assistant.sock'
    assert get_state(sock) is None
    with StubServer(sock) as server:
        ctl = AssistantController(tmp_path, sock)
        assert ctl.state() == 'attesa'
        assert 'attivato' in ctl.listen()
        assert ctl.state() == 'ascolto'
        assert 'Fine ascolto' in ctl.listen()
        assert ctl.state() == 'attesa'
        assert 'già attivo' in ctl.start()
        assert 'Arresto' in ctl.stop()
        assert server.requests.count('toggle') == 2


def test_reject_unexpected_socket_commands(tmp_path):
    with pytest.raises(ValueError):
        send_command('rm -rf /', tmp_path / 'socket')


def test_file_tail_and_last_transcription(tmp_path):
    path = tmp_path / 'trascrizioni.log'
    assert file_tail(path) == ''
    assert last_transcription(path) == ''
    path.write_text("2026-11-09 10:00:01 | sentito: 'Apri Firefox' | esito: ok\n"
                    "2026-11-09 10:00:02 | sentito: 'Volume al 20%' | esito: ok\n", encoding='utf8')
    assert last_transcription(path) == 'Volume al 20%'
    assert file_tail(path, max_bytes=55).endswith("| esito: ok")


def test_launch_is_detached_and_terminable_during_loading(tmp_path):
    fake = tmp_path / 'main.py'
    fake.write_text('import time\nprint("CARICAMENTO", flush=True)\ntime.sleep(60)\n', encoding='utf8')
    ctl = AssistantController(tmp_path, tmp_path / 'missing.sock')
    try:
        message = ctl.start()
        assert 'Avvio' in message
        assert ctl.is_starting()
        assert 'già in corso' in ctl.start()
        assert 'annullato' in ctl.stop()
        assert not ctl.is_starting()
    finally:
        if ctl.process and ctl.process.poll() is None:
            ctl.process.terminate()
            ctl.process.wait(timeout=5)


def test_missing_project_file(tmp_path):
    ctl = AssistantController(tmp_path, tmp_path / 'nothing.sock')
    with pytest.raises(AssistantError):
        ctl.start()


def test_log_priority_and_latest_text(tmp_path):
    ctl = AssistantController(tmp_path, tmp_path / 'nothing.sock')
    ctl._voice_log.write_text("2026-11-09 10:00:01 | sentito: 'Crea file' | esito: ok\n", encoding='utf8')
    assert ctl.latest_text() == 'Crea file'
    assert 'Crea file' in ctl.logs()
    ctl._gui_log.write_text('🗣️  Nuova frase\n', encoding='utf8')
    assert 'Nuova frase' in ctl.logs()


def test_launcher_file_works_with_spaces(tmp_path):
    from kapa.installa_launcher import desktop_file
    content = desktop_file('/usr/bin/python3', tmp_path / 'IA Assistant')
    assert 'Exec="/usr/bin/python3" "' in content
    assert 'IA Assistant/gui.py' in content
    assert 'Terminal=false' in content
