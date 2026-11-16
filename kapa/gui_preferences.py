"""Preferenze della sola interfaccia: non cambiano le impostazioni del demone.

Le scorciatoie GLOBALI vengono registrate dall'ambiente desktop: la GUI
salva una proposta e assiste l'utente nella configurazione di sistema.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from .app_paths import PROJECT_DIR

APP_DIR_NAME = "ia-assistant"


def preferences_path(env=None, home=None) -> Path:
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)
    base = env.get("XDG_CONFIG_HOME")
    if not base or not Path(base).is_absolute():
        base = home / ".config"
    return Path(base) / APP_DIR_NAME / "gui.json"


def read_preferred_shortcut(path: Path | None = None) -> str:
    path = preferences_path() if path is None else Path(path)
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        value = info.get("shortcut", "")
        return value if isinstance(value, str) and len(value) <= 80 else ""
    except (FileNotFoundError, OSError, ValueError, TypeError, AttributeError):
        return ""


def save_preferred_shortcut(sequence: str, path: Path | None = None) -> None:
    """Scrive una preferenza, NON installa un hotkey di sistema."""
    if not isinstance(sequence, str) or not sequence.strip() or len(sequence) > 80:
        raise ValueError("Scorciatoia non valida")
    path = preferences_path() if path is None else Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    import tempfile
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent),
                                         delete=False) as stream:
            temp = Path(stream.name)
            json.dump({"shortcut": sequence}, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temp.chmod(0o600)
        temp.replace(path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def trigger_command(python_executable: str | None = None, project_dir: Path | None = None) -> str:
    import shlex
    root = PROJECT_DIR if project_dir is None else Path(project_dir)
    executable = sys.executable if python_executable is None else python_executable
    return shlex.join([str(executable), str(root / "trigger.py"), "toggle"])


def keyboard_settings_command(desktop: str | None = None, which=None):
    """Restituisce un elenco di argomenti, mai una stringa shell.

    Su desktop sconosciuti l'utente puo' usare manualmente le impostazioni.
    """
    desktop = (desktop if desktop is not None else os.environ.get("XDG_CURRENT_DESKTOP", "")).lower()
    which = shutil.which if which is None else which
    candidates = []
    if "kde" in desktop or "plasma" in desktop:
        candidates = [["kcmshell6", "kcm_keys"], ["systemsettings", "kcm_keys"],
                      ["systemsettings6", "kcm_keys"], ["kcmshell5", "kcm_keys"]]
    elif "gnome" in desktop or "unity" in desktop:
        candidates = [["gnome-control-center", "keyboard"]]
    elif "cinnamon" in desktop:
        candidates = [["cinnamon-settings", "keyboard"]]
    elif "xfce" in desktop:
        candidates = [["xfce4-keyboard-settings"]]
    elif "mate" in desktop:
        candidates = [["mate-keybinding-properties"]]
    for args in candidates:
        if which(args[0]):
            return args
    return None
