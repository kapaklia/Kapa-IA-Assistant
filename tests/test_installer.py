"""Installazione simulata: nessun pip, sudo o download reale."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / 'Kapa con spazi'
        self.project.mkdir()
        root = Path(__file__).resolve().parents[1]
        shutil.copyfile(root / 'installa.sh', self.project / 'installa.sh')
        for name in ('requirements.txt', 'requirements-voce.txt', 'requirements-gui.txt',
                     'scripts/setup_assistant.py', 'scripts/installa_launcher.py'):
            path = self.project / name
            path.parent.mkdir(exist_ok=True)
            path.write_text('')
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        self.trace = self.base / 'trace'
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        TEST_PROJECT=str(self.project), TEST_BIN=str(self.bin),
                        TEST_TRACE=str(self.trace))
        self.shim('id', 'echo 1000')
        self.shim('sudo', 'printf "sudo %s\\n" "$*" >> "$TEST_TRACE"')
        self.shim('dnf', 'exit 0')
        self.shim('python3', '''
printf 'python3 %s\n' "$*" >> "$TEST_TRACE"
if [[ "$*" == '-m venv .venv' ]]; then
    mkdir -p "$TEST_PROJECT/.venv/bin"
    cp "$TEST_BIN/venv-python" "$TEST_PROJECT/.venv/bin/python"
fi
''')
        self.shim('venv-python', '''
printf 'venv %s\n' "$*" >> "$TEST_TRACE"
if [[ "${TEST_FAIL_PIP:-}" == 1 && "$*" == '-m pip install -r '* ]]; then
    exit 9
fi
''')

    def shim(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\nset -eu\n' + body + '\n')
        path.chmod(0o755)

    def run_installer(self, *arguments):
        return subprocess.run(['bash', str(self.project / 'installa.sh'), *arguments],
                              cwd=self.base, env=self.env, capture_output=True,
                              text=True, timeout=10)

    def test_install_from_other_directory_and_repeat_preserves_configuration(self):
        first = self.run_installer('--skip-system')
        self.assertEqual(first.returncode, 0, first.stderr)
        config = self.project / '.env'
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        config.write_text('GROQ_API_KEY=synthetic-test\n')
        second = self.run_installer('--skip-system')
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(config.read_text(), 'GROQ_API_KEY=synthetic-test\n')
        trace = self.trace.read_text()
        self.assertNotIn('sudo', trace)
        self.assertEqual(trace.count('python3 -m venv .venv'), 1)
        self.assertIn('-r requirements.txt -r requirements-voce.txt -r requirements-gui.txt', trace)
        self.assertIn('scripts/installa_launcher.py --local', trace)
        self.assertNotIn('synthetic-test', first.stdout + second.stdout + trace)

    def test_system_packages_use_sudo_but_python_stays_local(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        trace = self.trace.read_text()
        self.assertIn('sudo dnf install python3', trace)
        self.assertNotIn('sudo pip', trace)
        self.assertNotIn('sudo python', trace)

    def test_failed_requirements_stop_before_configuration_and_launcher(self):
        self.env['TEST_FAIL_PIP'] = '1'
        result = self.run_installer('--skip-system')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Installazione interrotta', result.stderr)
        self.assertNotIn('scripts/installa_launcher.py', self.trace.read_text())
        self.assertFalse((self.project / '.env').exists())

    def test_root_and_invalid_arguments_are_rejected_before_changes(self):
        result = self.run_installer('--unknown')
        self.assertNotEqual(result.returncode, 0)
        self.shim('id', 'echo 0')
        result = self.run_installer('--skip-system')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('senza sudo', result.stderr)
        self.assertFalse(self.trace.exists())
