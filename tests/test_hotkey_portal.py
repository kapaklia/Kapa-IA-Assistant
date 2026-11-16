import tempfile
import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from kapa.hotkey_portal import GlobalHotkey, SHORTCUT_ID, display_trigger
from kapa.gui_backend import VALID_COMMANDS


class HotkeyPortalTests(unittest.TestCase):
    def test_display_trigger_real_value(self):
        bound = [types.SimpleNamespace(id=SHORTCUT_ID, trigger_description='Alt+Q')]
        self.assertEqual(display_trigger(bound), 'Alt+Q')
        self.assertEqual(display_trigger([types.SimpleNamespace(id='other', trigger_description='F9')]), '')

    def test_missing_optional_library_preserves_voice(self):
        with patch.dict('sys.modules', {'global_shortcut_portal': None}):
            hk = GlobalHotkey(lambda: None)
            import asyncio
            asyncio.run(hk._serve())
            self.assertEqual(hk.state(), 'libreria_mancante')
            self.assertEqual(hk.configure(), 'non_disponibile')

    def test_no_shortcut_is_claimed_active_prematurely(self):
        hk = GlobalHotkey(lambda: None)
        self.assertEqual(hk.state(), 'avvio')
        self.assertEqual(hk.configure(), 'avvio')
        hk._set('attiva','F9')
        self.assertEqual(hk.state(), 'attiva|F9')

    def test_backend_supports_shortcut_commands(self):
        self.assertIn('hotkey-stato', VALID_COMMANDS)
        self.assertIn('hotkey-configura', VALID_COMMANDS)

    def test_portal_activation_routes_to_existing_toggle(self):
        toggles = []
        manager = GlobalHotkey(lambda: toggles.append("toggle"))

        class FakePortal:
            async def connect(self): pass
            async def close(self): pass

        class FakeSession:
            def __init__(self, portal, app_id, callback):
                self.callback = callback
            async def connect(self): pass
            async def list_shortcuts(self):
                return [types.SimpleNamespace(id=SHORTCUT_ID, trigger_description='Alt+Q')]
            async def bind(self, shortcuts):
                self.callback.on_activated(types.SimpleNamespace(shortcut_id=SHORTCUT_ID))
                manager._stop.set()
                return [types.SimpleNamespace(id=SHORTCUT_ID, trigger_description="Alt+Q")]
            async def close(self): pass

        class FakeShortcut:
            def __init__(self, **fields):
                self.fields = fields

        class FakeCallback: pass
        fake = types.SimpleNamespace(
            Portal=FakePortal, GlobalShortcutsSession=FakeSession,
            Shortcut=FakeShortcut, SessionCallback=FakeCallback)
        with patch.dict(sys.modules, {'global_shortcut_portal': fake}):
            asyncio.run(manager._serve())
        self.assertEqual(toggles, ['toggle'])
        self.assertEqual(manager.state(), 'attiva|Alt+Q')

    def test_launcher_matches_app_id(self):
        from kapa import installa_launcher
        from kapa.hotkey_portal import APP_ID
        self.assertEqual(installa_launcher.TARGET.name, APP_ID + '.desktop')
        with tempfile.TemporaryDirectory() as td:
            with patch.object(installa_launcher, 'TARGET', Path(td) / (APP_ID + '.desktop')):
                path = installa_launcher.ensure_launcher()
                self.assertTrue(path.is_file())
                self.assertIn('Name=Kapa', path.read_text())
                path.write_text('custom desktop config', encoding='utf-8')
                installa_launcher.ensure_launcher()
                self.assertEqual(path.read_text(), 'custom desktop config')
                installa_launcher.ensure_launcher(replace=True)
                self.assertIn('Name=Kapa', path.read_text())
                self.assertIn(str(installa_launcher.ROOT / 'gui.py'), path.read_text())

    def test_launcher_refreshes_kde_menu(self):
        from kapa import installa_launcher
        with patch.object(installa_launcher.shutil, 'which', side_effect=[None, '/usr/bin/kbuildsycoca5']), \
                patch.object(installa_launcher.subprocess, 'run') as run:
            installa_launcher.refresh_menu()
        self.assertEqual(run.call_args.args[0], ['/usr/bin/kbuildsycoca5', '--noincremental'])


if __name__ == '__main__':
    unittest.main()
