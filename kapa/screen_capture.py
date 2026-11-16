"""Topologia aggiornata ad ogni cattura; nessun connettore predefinito."""
import json
import subprocess
import sys

_SCREEN_PROBE = '''
import json
from PySide6.QtGui import QGuiApplication
app = QGuiApplication([])
primary = app.primaryScreen()
print(json.dumps([dict(name=s.name(), x=s.geometry().x(), y=s.geometry().y(),
 w=s.geometry().width(), h=s.geometry().height(), primary=s == primary,
 scale=s.devicePixelRatio()) for s in app.screens()]))
'''


def detect_monitors():
    """Qt interroga Wayland/X11 in un processo isolato dal thread vocale."""
    try:
        result = subprocess.run([sys.executable, '-c', _SCREEN_PROBE],
                                capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            raise ValueError('Rilevamento monitor non disponibile: verifica PySide6 e la sessione grafica.')
        screens = json.loads(result.stdout)
        if not screens or any(s['w'] <= 0 or s['h'] <= 0 for s in screens):
            raise ValueError('Nessun monitor attivo rilevato.')
        return screens
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError('Impossibile rilevare i monitor della sessione.') from exc


def select_monitor(monitors, target='principale', monitor=None):
    if target not in ('principale', 'monitor', 'tutti', 'finestra'):
        raise ValueError('Destinazione screenshot non valida.')
    if target == 'monitor':
        if type(monitor) is not int or not 1 <= monitor <= len(monitors):
            raise ValueError(f'Indice monitor non valido: disponibili 1–{len(monitors)}.')
        return monitors[monitor - 1]
    if monitor is not None:
        raise ValueError('Specifica un indice solo con destinazione monitor.')
    if target == 'principale':
        primary = next((s for s in monitors if s['primary']), None)
        if primary is None:
            raise ValueError('La sessione non indica un monitor principale.')
        return primary
    return None


def crop_monitor(path, monitors, selected):
    """Ritaglia il desktop completo solo quando la geometria è verificabile."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage
    if len({s['scale'] for s in monitors}) > 1:
        raise ValueError('Scale monitor differenti: ritaglio non affidabile con questo backend.')
    image = QImage(str(path))
    left = min(s['x'] for s in monitors)
    top = min(s['y'] for s in monitors)
    width = max(s['x'] + s['w'] for s in monitors) - left
    height = max(s['y'] + s['h'] for s in monitors) - top
    sx, sy = image.width() / width, image.height() / height
    if image.isNull() or abs(sx - sy) > 0.02 or sx <= 0:
        raise ValueError('Geometria della cattura incompatibile con i monitor rilevati.')
    rect = QRect(round((selected['x'] - left) * sx), round((selected['y'] - top) * sy),
                 round(selected['w'] * sx), round(selected['h'] * sy))
    if not image.rect().contains(rect) or not image.copy(rect).save(str(path), 'PNG'):
        raise ValueError('Ritaglio del monitor non riuscito.')
