"""Lettura non invasiva delle scorciatoie desktop associate al trigger vocale.

Questo modulo NON registra tasti e NON dichiara attiva una preferenza salvata
nella GUI. Sui desktop non riconosciuti mostra uno stato indeterminato.
"""
from __future__ import annotations

import configparser
from pathlib import Path
import shutil
import re
import subprocess
import time

from .shortcut_setup import desktop_family


def _is_trigger_command(command: str) -> bool:
    """Identifica il collegamento legacy o quello dedicato, non l'avvio della GUI."""
    return "trigger.py" in command and "toggle" in command


def _desktop_command(entry: str, applications: Path) -> str:
    if not entry.endswith('.desktop') or '/' in entry or '\\' in entry:
        return ''
    path = applications / entry
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.startswith('Exec='):
                return line[5:].strip()
    except (OSError, UnicodeError):
        pass
    return ''


def _kde_primary_shortcuts(value: str) -> list[str]:
    """KGlobalAccel: active,default,description; active può contenere TAB."""
    selected = value.split(',', 1)[0]
    return [key.strip() for key in re.split(r'\\t|\t', selected)
            if key.strip() and key.strip().lower() not in {'none', 'no', 'disabled'}]


def kde_shortcuts(config_path: Path | None = None, applications: Path | None = None) -> list[str]:
    config_path = config_path or (Path.home() / '.config' / 'kglobalshortcutsrc')
    applications = applications or (Path.home() / '.local' / 'share' / 'applications')
    parser = configparser.RawConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    try:
        with config_path.open(encoding='utf-8') as stream:
            parser.read_file(stream)
    except (OSError, configparser.Error, UnicodeError):
        return []

    keys: list[str] = []
    for section in parser.sections():
        # KDE Plasma 6 registra le scorciatoie applicative in [services][ID.desktop].
        if not (section.startswith('services][') and section.endswith('.desktop')):
            continue
        entry = section[len('services]['):]
        if not _is_trigger_command(_desktop_command(entry, applications)):
            continue
        value = parser.get(section, '_launch', fallback='')
        for key in _kde_primary_shortcuts(value):
            if key not in keys:
                keys.append(key)
    return keys


def _gsettings_value(schema: str, key: str, path: str | None = None) -> str:
    args = ['gsettings', 'get', schema]
    if path is not None:
        args[-1] = f'{schema}:{path}'
    try:
        result = subprocess.run([*args, key], capture_output=True, text=True, timeout=0.8, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ''
    return result.stdout.strip() if result.returncode == 0 else ''


def _gsettings_str(value: str) -> str:
    # Output GVariant per stringhe semplici: 'Alt+Q', eventualmente @as [] per liste.
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1].replace("\\'", "'")
    return ''


def gnome_shortcuts() -> list[str]:
    if not shutil.which('gsettings'):
        return []
    base_schema = 'org.gnome.settings-daemon.plugins.media-keys'
    raw_paths = _gsettings_value(base_schema, 'custom-keybindings')
    import ast
    try:
        paths = ast.literal_eval(raw_paths.removeprefix('@as ').strip())
    except (ValueError, SyntaxError):
        return []
    if not isinstance(paths, list):
        return []
    schema = 'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding'
    result = []
    deadline = time.monotonic() + 2
    for path in paths[:100]:
        if time.monotonic() >= deadline:
            break
        if not isinstance(path, str) or not path.startswith('/org/gnome/'):
            continue
        command = _gsettings_str(_gsettings_value(schema, 'command', path))
        if not _is_trigger_command(command):
            continue
        bind = _gsettings_str(_gsettings_value(schema, 'binding', path))
        if bind and bind.lower() not in ('disabled', 'none') and bind not in result:
            result.append(bind)
    return result


def current_shortcuts(desktop: str | None = None,
                      kde_config: Path | None = None,
                      applications: Path | None = None) -> tuple[list[str], bool]:
    """(scorciatoie, lettura_supportata). True non garantisce l'esecuzione reale."""
    desktop = desktop or desktop_family()
    if desktop == 'KDE Plasma':
        return kde_shortcuts(kde_config, applications), True
    if desktop == 'GNOME':
        return gnome_shortcuts(), bool(shutil.which('gsettings'))
    return [], False
