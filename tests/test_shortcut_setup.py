"""Test della guida: nessuna dipendenza Qt richiesta."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from kapa.shortcut_setup import desktop_family, instructions
from kapa.configura_scorciatoia import main


def test_desktops():
    for environment, expected in [
        ({'XDG_CURRENT_DESKTOP':'KDE'}, 'KDE Plasma'),
        ({'XDG_CURRENT_DESKTOP':'GNOME'}, 'GNOME'),
        ({'DESKTOP_SESSION':'cinnamon'}, 'Cinnamon'),
        ({'XDG_CURRENT_DESKTOP':'XFCE'}, 'XFCE'),
        ({'XDG_CURRENT_DESKTOP':'MATE'}, 'MATE'),
        ({'XDG_CURRENT_DESKTOP':'wayland:hyprland'}, 'Linux'),
    ]:
        assert desktop_family(environment)==expected
        guide=instructions(environment)
        assert guide.first and guide.second


def test_cli_fallback(capsys,monkeypatch):
    monkeypatch.setenv('XDG_CURRENT_DESKTOP','GNOME')
    assert main(['--testo']) == 0
    output=capsys.readouterr().out
    assert 'Scorciatoia su GNOME' in output
    assert 'trigger.py' in output
    assert 'toggle' in output
