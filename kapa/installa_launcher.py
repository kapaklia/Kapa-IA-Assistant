#!/usr/bin/env python3
"""Aggiunge Kapa al menu applicazioni dell'utente Linux."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from .app_paths import data_dir, PROJECT_DIR
ROOT = PROJECT_DIR
TARGET = data_dir().parent / "applications/org.iaassistant.IAAssistant.desktop"


def quote_exec(text):
    text = str(text)
    if any(c in text for c in ('\n', '\r')):
        raise ValueError('Percorso launcher non valido.')
    for old, new in [('\\', '\\\\'), ('"', '\\"'), ('`', '\\`'), ('$', '\\$'), ('%', '%%')]:
        text = text.replace(old, new)
    return '"' + text + '"'


def desktop_file(python=sys.executable, root=ROOT):
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=Kapa",
        "Comment=Assistente vocale per Linux",
        f"Exec={quote_exec(python)} {quote_exec(root / 'gui.py')}",
        f"Path={root}",
        f"Icon={root / 'assets/assistant-icon.png'}" if (root / 'assets/assistant-icon.png').is_file()
        else "Icon=audio-input-microphone",
        "Terminal=false",
        "StartupNotify=true",
        "Categories=Utility;Accessibility;",
        "Keywords=voice;microphone;assistente;voce;",
        "",
    ])


def ensure_launcher(*, replace=False):
    """Crea una identità desktop stabile, necessaria a certi portali.

    Preserva le personalizzazioni salvo aggiornamento esplicito con replace=True.
    """
    if TARGET.is_file() and not replace:
        return TARGET
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    if replace:
        TARGET.write_text(desktop_file(), encoding='utf-8')
        return TARGET
    try:
        with TARGET.open('x', encoding='utf-8') as output:
            output.write(desktop_file())
    except FileExistsError:
        pass
    return TARGET


def refresh_menu():
    """Aggiorna la cache KDE quando il relativo comando è disponibile."""
    command = shutil.which('kbuildsycoca6') or shutil.which('kbuildsycoca5')
    if command:
        try:
            subprocess.run([command, '--noincremental'], check=True,
                           capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            print('Cache del menu non aggiornata: esci e rientra nella sessione se Kapa non compare.',
                  file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local', action='store_true',
                        help='Crea il collegamento nella cartella del progetto')
    args = parser.parse_args()
    if args.local:
        target = ROOT / 'Kapa.desktop'
        # Il collegamento funziona anche senza attivare prima il virtualenv.
        python = next((path for path in (ROOT / '.venv/bin/python', ROOT / 'venv/bin/python')
                       if path.is_file()), sys.executable)
        target.write_text(desktop_file(python=python), encoding='utf-8')
        target.chmod(0o755)
        print(f"Collegamento pronto: {target}\nAprilo con doppio clic.")
    else:
        # L'installazione esplicita aggiorna anche nome e percorsi delle vecchie versioni.
        # Le chiamate automatiche a ensure_launcher() preservano le personalizzazioni.
        target = ensure_launcher(replace=True)
        refresh_menu()
        print(f"Collegamento pronto: {target}\nCerca 'Kapa' nel menu applicazioni.")


if __name__ == "__main__":
    main()
