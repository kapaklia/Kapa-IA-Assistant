"""Verifica dei tasti mostrati nella GUI senza leggere dati privati reali."""
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from kapa import shortcut_status as ss
from kapa.hotkey_portal import GlobalHotkey


class ShortcutStatusTests(TestCase):
    def test_native_default_does_not_open_portal_on_daemon_start(self):
        with patch.dict('os.environ', {'IA_ASSISTANT_SHORTCUT_MODE': 'desktop'}, clear=True):
            hotkey = GlobalHotkey(lambda: None)
            with patch.object(hotkey, '_thread_main', side_effect=AssertionError('NO PORTAL')):
                hotkey.start()
            self.assertEqual(hotkey.state(), 'desktop')
            self.assertIsNone(hotkey._thread)

    def test_kde_reads_only_trigger_and_not_gui_launcher(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            apps = root / 'applications'
            apps.mkdir()
            (apps / 'net.local.python3.desktop').write_text(
                '[Desktop Entry]\nName=IA Assistant\nExec=python3 "/home/testuser/Scrivania/IA Assistant/trigger.py" toggle\n',
                encoding='utf-8')
            (apps / 'org.iaassistant.IAAssistant.desktop').write_text(
                '[Desktop Entry]\nName=IA Assistant\nExec=python3 "/home/testuser/Scrivania/IA Assistant/gui.py"\n',
                encoding='utf-8')
            (root / 'shortcuts').write_text(
                '[services][net.local.python3.desktop]\n_launch=Alt+Q\n'
                '[services][org.iaassistant.IAAssistant.desktop]\n_launch=Ctrl+Alt+J,none,gui\n',
                encoding='utf-8')
            self.assertEqual(ss.kde_shortcuts(root / 'shortcuts', apps), ['Alt+Q'])
            self.assertEqual(ss.current_shortcuts('KDE Plasma', root / 'shortcuts', apps), (['Alt+Q'], True))

    def test_kde_multiple_and_unbound(self):
        self.assertEqual(ss._kde_primary_shortcuts('Ctrl+Alt+J\\tF9,none,foo'), ['Ctrl+Alt+J', 'F9'])
        self.assertEqual(ss._kde_primary_shortcuts('Meta+F12\tF10'), ['Meta+F12', 'F10'])
        self.assertEqual(ss._kde_primary_shortcuts('none,Alt+Q,foo'), [])
        self.assertEqual(ss._kde_primary_shortcuts(''), [])

    def test_kde_does_not_show_old_saved_preference_as_active(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            apps = root / 'applications'
            apps.mkdir()
            (apps / 'net.local.python3.desktop').write_text('[Desktop Entry]\nExec=python3 trigger.py toggle\n')
            (root / 'shortcuts').write_text('[services][net.local.python3.desktop]\n_launch=none\n')
            self.assertEqual(ss.current_shortcuts('KDE Plasma', root / 'shortcuts', apps), ([], True))

    def test_gnome_uses_command_and_binding_not_name(self):
        paths = "['/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/']"
        def fake_gsettings(schema, key, path=None):
            if key == 'custom-keybindings': return paths
            if key == 'command': return "'python3 /tmp/IA\\ Assistant/trigger.py toggle'"
            if key == 'binding': return "'<Alt>q'"
            return ''
        with patch.object(ss.shutil, 'which', return_value='/usr/bin/gsettings'):
            with patch.object(ss, '_gsettings_value', side_effect=fake_gsettings):
                self.assertEqual(ss.current_shortcuts('GNOME'), (['<Alt>q'], True))

    def test_unknown_desktop_reports_unverified(self):
        self.assertEqual(ss.current_shortcuts('XFCE'), ([], False))
