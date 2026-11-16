"""Test delle preferenze della GUI, senza dipendenze Qt."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kapa.gui_preferences import (  # noqa: E402
    keyboard_settings_command, preferences_path, read_preferred_shortcut,
    save_preferred_shortcut, trigger_command,
)
import pytest


def test_pref_path_respects_xdg(tmp_path):
    assert preferences_path({"XDG_CONFIG_HOME": str(tmp_path)}, tmp_path) == tmp_path / "ia-assistant/gui.json"
    assert preferences_path({"XDG_CONFIG_HOME": "relative"}, tmp_path) == tmp_path / ".config/ia-assistant/gui.json"


def test_read_and_save_shortcut(tmp_path):
    path = tmp_path / 'nested/gui.json'
    assert read_preferred_shortcut(path) == ''
    save_preferred_shortcut('Ctrl+Alt+Space', path)
    assert read_preferred_shortcut(path) == 'Ctrl+Alt+Space'
    assert json.loads(path.read_text()) == {'shortcut': 'Ctrl+Alt+Space'}
    save_preferred_shortcut('F9', path)  # un solo tasto
    assert read_preferred_shortcut(path) == 'F9'
    assert path.stat().st_mode & 0o077 == 0


def test_reject_bad_shortcuts(tmp_path):
    with pytest.raises(ValueError):
        save_preferred_shortcut('', tmp_path / 'gui.json')
    with pytest.raises(ValueError):
        save_preferred_shortcut('x' * 100, tmp_path / 'gui.json')
    path = tmp_path / 'gui.json'
    path.write_text('invalid-json')
    assert read_preferred_shortcut(path) == ''


def test_trigger_command_path_with_spaces(tmp_path):
    result = trigger_command('/usr/bin/python3', tmp_path / 'IA Assistant')
    assert result == "/usr/bin/python3 '" + str(tmp_path / 'IA Assistant/trigger.py') + "' toggle"


def test_system_shortcut_settings_selection():
    which = lambda executable: '/fake/' + executable if executable == 'kcmshell6' else None
    assert keyboard_settings_command('KDE', which) == ['kcmshell6', 'kcm_keys']
    which2 = lambda executable: executable if executable == 'gnome-control-center' else None
    assert keyboard_settings_command('GNOME', which2) == ['gnome-control-center', 'keyboard']
    assert keyboard_settings_command('UNKNOWN', lambda _: None) is None
