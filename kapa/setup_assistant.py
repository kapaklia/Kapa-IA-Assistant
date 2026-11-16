#!/usr/bin/env python3
"""Verifica dipendenze e genera il servizio utente; non installa pacchetti."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import sys
from .app_paths import PROJECT_DIR


def _quote(value):
    text = str(value)
    if '\n' in text or '\r' in text:
        raise ValueError('Percorso con caratteri di controllo non supportato.')
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def service_text(root=None, python=None):
    root = PROJECT_DIR if root is None else Path(root)
    python = sys.executable if python is None else python
    return '\n'.join([
        '[Unit]', 'Description=Kapa vocale',
        'After=graphical-session.target', 'PartOf=graphical-session.target', '',
        '[Service]', 'Type=simple', f'WorkingDirectory={_quote(root)}',
        f'ExecStart={_quote(python)} {_quote(root / "main.py")} --background',
        'Environment=PYTHONUNBUFFERED=1', 'Restart=on-failure', 'RestartSec=5',
        'TimeoutStopSec=90', '', '[Install]', 'WantedBy=graphical-session.target', '',
    ])


def check():
    print('Python:', sys.version.split()[0], '(richiesto >= 3.10)')
    for module in ('groq', 'dotenv', 'numpy', 'faster_whisper', 'PySide6', 'global_shortcut_portal', 'websocket'):
        print(f'{module}:', 'disponibile' if importlib.util.find_spec(module) else 'mancante')
    for command in ('xdg-user-dir', 'xdg-open', 'parecord', 'paplay', 'pactl',
                    'notify-send', 'playerctl', 'gpu-screen-recorder', 'obs', 'spectacle',
                    'grim', 'gnome-screenshot', 'scrot', 'wl-copy', 'wl-paste', 'xclip'):
        print(f'{command}:', 'disponibile' if shutil.which(command) else 'assente/opzionale')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Solo verifica, nessuna installazione')
    parser.add_argument('--print-service', action='store_true', help='Stampa servizio per percorso e Python correnti')
    parser.add_argument('--launcher', action='store_true', help='Crea solo il launcher utente, senza sovrascrivere')
    args = parser.parse_args(argv)
    if args.print_service:
        print(service_text(), end='')
    if args.launcher:
        from .installa_launcher import ensure_launcher
        print(ensure_launcher())
    if args.check or not (args.print_service or args.launcher):
        check()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
