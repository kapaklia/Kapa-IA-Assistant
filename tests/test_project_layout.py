"""Verifiche dei punti d'ingresso dopo il riordino, senza dispositivi reali."""
from pathlib import Path
import runpy
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from safe_config import install
install()
from kapa.app_paths import PROJECT_DIR, ASSETS_DIR, DOCS_DIR


class ProjectLayoutTests(unittest.TestCase):
    def test_legacy_entrypoints_delegate_without_starting_real_services(self):
        for name, function in (('gui', 'main'), ('main', 'run'), ('trigger', 'main')):
            with self.subTest(entry=name), patch(f'kapa.{name}.{function}', return_value=0) as entry:
                with self.assertRaises(SystemExit) as result:
                    runpy.run_path(str(PROJECT_DIR / f'{name}.py'), run_name='__main__')
                self.assertEqual(result.exception.code, 0)
                entry.assert_called_once_with()

    def test_setup_scripts_work_from_another_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            for script, option, expected in (
                    ('setup_assistant', '--print-service', str(PROJECT_DIR / 'main.py')),
                    ('configura_scorciatoia', '--testo', str(PROJECT_DIR / 'trigger.py'))):
                with self.subTest(script=script):
                    result = subprocess.run(
                        [sys.executable, '-B', str(PROJECT_DIR / f'scripts/{script}.py'), option],
                        cwd=temporary, capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(expected, result.stdout)

    def test_launcher_trigger_and_resources_follow_project_root(self):
        from kapa.installa_launcher import desktop_file
        from kapa.gui_preferences import trigger_command
        import configparser
        desktop = configparser.ConfigParser(interpolation=None)
        desktop.read_string(desktop_file())
        self.assertEqual(shlex.split(desktop['Desktop Entry']['Exec'])[1], str(PROJECT_DIR / 'gui.py'))
        self.assertEqual(shlex.split(trigger_command())[1], str(PROJECT_DIR / 'trigger.py'))
        for path in (ASSETS_DIR / 'sfondo.png', ASSETS_DIR / 'microphone.svg',
                     ASSETS_DIR / 'assistant-icon.png', ASSETS_DIR / 'vocabolario_comune.txt',
                     PROJECT_DIR / 'COSA_SA_FARE.md'):
            self.assertTrue(path.is_file(), str(path))

    def test_admin_terminal_uses_the_new_script_without_executing_it(self):
        from kapa import root_tools
        with patch.object(root_tools, 'detect_distro', return_value='fedora'), \
             patch.object(root_tools.shutil, 'which', return_value='/synthetic/terminal'), \
             patch.object(root_tools.subprocess, 'Popen') as launch:
            result = root_tools.installa_applicazione('vlc')
        command = launch.call_args.args[0]
        self.assertIn(str(PROJECT_DIR / 'scripts/root_tools.py'), command)
        self.assertEqual(command[-3:], ['--run', 'install', 'vlc'])
        self.assertIn('non ancora completata', result)
