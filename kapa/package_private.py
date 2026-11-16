#!/usr/bin/env python3
"""Crea il pacchetto sorgente Alpha da allowlist, senza dati personali."""
import ast
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile
from .app_paths import PROJECT_DIR

VERSION = '0.1.0-alpha'
ROOT_NAME = 'Kapa-' + VERSION
PUBLIC_FILES = (
    'LICENSE',
    '.gitignore',
    'README.md',
    'README.it.md',
    'CHANGELOG.md',
    'CONTRIBUTING.md',
    'SECURITY.md',
    'docs/RELEASE_v0.1.0-alpha.md',
    'docs/PUBBLICAZIONE.md',
    'docs/LICENZA.md',
    'docs/THIRD_PARTY.md',
    'docs/DEPENDENCIES.md',
    'docs/FILE_DISTRIBUITI.txt',
    'PROVA_IN_VM.md',
    'installa.sh',
    'gui.py',
    'main.py',
    'trigger.py',
    'kapa/__init__.py',
    'docs/INTERVENTI.md',
    'COSA_SA_FARE.md',
    'docs/ISTRUZIONI_FEDORA_KDE.md',
    'docs/SCHEDA_TEST_FEDORA.md',
    'requirements.txt',
    'requirements-voce.txt',
    'requirements-gui.txt',
    'requirements-dev.txt',
    'assets/vocabolario_comune.txt',
    'kapa/app_paths.py',
    'kapa/attivita.py',
    'kapa/lettori.py',
    'kapa/obs_control.py',
    'kapa/comandi_rapidi.py',
    'kapa/comprensione.py',
    'kapa/config.py',
    'kapa/configura_scorciatoia.py',
    'kapa/confronta_whisper.py',
    'kapa/demone.py',
    'kapa/dettatura.py',
    'kapa/diagnostica_audio.py',
    'kapa/gui.py',
    'kapa/gui_backend.py',
    'kapa/gui_preferences.py',
    'kapa/gui_instance.py',
    'kapa/hotkey_portal.py',
    'kapa/installa_launcher.py',
    'kapa/main.py',
    'kapa/memoria.py',
    'kapa/root_tools.py',
    'kapa/screen_capture.py',
    'kapa/setup_assistant.py',
    'kapa/shortcut_setup.py',
    'kapa/shortcut_status.py',
    'kapa/stt.py',
    'kapa/tool_validation.py',
    'kapa/tools.py',
    'kapa/trigger.py',
    'kapa/package_private.py',
    'docs/AVVIO_GUI.md',
    'assets/microphone.svg',
    'assets/assistant-icon.png',
    'assets/sfondo.png',
    'tests/conftest.py',
    'tests/run_safe_tests.py',
    'tests/safe_config.py',
    'tests/test_gui_backend.py',
    'tests/test_gui_preferences.py',
    'tests/test_gui_safe.py',
    'tests/test_project_layout.py',
    'tests/test_installer.py',
    'tests/test_hotkey_portal.py',
    'tests/test_patch.py',
    'tests/test_regressions.py',
    'tests/test_shortcut_setup.py',
    'tests/test_shortcut_status.py',
    'scripts/configura_scorciatoia.py',
    'scripts/confronta_whisper.py',
    'scripts/diagnostica_audio.py',
    'scripts/installa_launcher.py',
    'scripts/package_private.py',
    'scripts/root_tools.py',
    'scripts/setup_assistant.py',
    'scripts/assistente-ia.service',
)


def build():
    root = PROJECT_DIR
    payload = {}
    for name in PUBLIC_FILES:
        path = root / name
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f'File pubblico mancante o symlink: {name}')
        data = path.read_bytes()
        # Una vecchia fixture usa un percorso personale: rendilo sintetico
        # soltanto nella copia distribuita, senza toccare i dati dell'utente.
        if name.startswith('tests/'):
            data = data.replace((str(Path.home()) + '/').encode(), b'/home/testuser/')
        if re.search(rb'(?:gsk_[A-Za-z0-9]{16,}|AIza[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{24,})', data):
            raise RuntimeError(f'Possibile credenziale in un file pubblico: {name}; archivio non creato.')
        if name.endswith('.py'):
            ast.parse(data.decode('utf-8'), filename=name)
        payload[name] = data
    # Modelli generati da zero: non leggere .env o gli esempi locali.
    payload['.env.example'] = b'GROQ_API_KEY=\nYOUTUBE_API_KEY=\nOBS_PORT=4455\nOBS_PASSWORD=\n'
    payload['vocabolario_personale.example.txt'] = (
        '# Facoltativo: una voce per riga, solo sul PC di prova.\n'
        '# Salva come vocabolario_personale.txt; non distribuirlo.\n').encode()
    manifest = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n'
                       for name, data in sorted(payload.items()))
    payload['MANIFEST.sha256'] = manifest.encode()
    output = root / 'dist'
    output.mkdir(exist_ok=True)
    archive = output / (ROOT_NAME + '.zip')
    if archive.exists():
        raise RuntimeError('Archivio già presente: non sovrascrivo una versione esistente.')
    try:
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for name, data in sorted(payload.items()):
                info = zipfile.ZipInfo(ROOT_NAME + '/' + name, date_time=(2026, 11, 11, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
                z.writestr(info, data)
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            assert set(z.namelist()) == {ROOT_NAME + '/' + name for name in payload}
            for name, data in payload.items():
                assert z.read(ROOT_NAME + '/' + name) == data
            with tempfile.TemporaryDirectory(prefix='ia-package-test-') as temporary:
                z.extractall(temporary)  # nomi tutti generati dalla allowlist sopra
                result = subprocess.run([sys.executable, '-B', 'tests/run_safe_tests.py'],
                    cwd=Path(temporary) / ROOT_NAME, capture_output=True, text=True, timeout=60)
                if result.returncode:
                    raise RuntimeError('Test del pacchetto falliti:\n' + result.stderr[-5000:])
                summary = re.search(r'Ran \d+ tests[^\n]*', result.stderr)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        checksum = archive.with_suffix('.zip.sha256')
        with checksum.open('x', encoding='utf-8') as stream:
            stream.write(digest + '  ' + archive.name + '\n')
        print('Archivio:', archive)
        print('File inclusi:', len(payload))
        print('Dimensione:', archive.stat().st_size, 'byte')
        print('Integrità ZIP, allowlist e contenuti: OK')
        print('Test dalla copia estratta:', summary.group(0) if summary else 'OK')
        print('SHA256:', digest)
    except Exception:
        archive.unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    build()
