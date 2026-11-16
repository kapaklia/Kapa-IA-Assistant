"""Percorsi XDG condivisi, senza letture di segreti o scritture all'import."""
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = PROJECT_DIR / 'assets'
DOCS_DIR = PROJECT_DIR / 'docs'


def data_dir():
    value = os.environ.get('XDG_DATA_HOME', '')
    root = Path(value) if value and Path(value).is_absolute() else Path.home() / '.local/share'
    return root / 'ia-assistant'


def private_append(path, binary=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() and not path.is_symlink() and path.stat().st_size > 2_000_000:
        path.replace(path.with_name(path.name + '.1'))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    os.fchmod(fd, 0o600)
    return os.fdopen(fd, 'ab' if binary else 'a', **({} if binary else {'encoding': 'utf-8'}))


SOCKET_PATH = Path(os.environ.get('XDG_RUNTIME_DIR', f'/tmp/ia-assistant-{os.getuid()}')) / 'assistente-ia.sock'
