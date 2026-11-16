"""Registro locale strutturato delle richieste vocali, senza audio."""
import json
from .app_paths import data_dir, private_append

ACTIVITY_LOG = data_dir() / 'attivita.jsonl'


def registra_attivita(evento, path=ACTIVITY_LOG):
    try:
        with private_append(path) as stream:
            stream.write(json.dumps(evento, ensure_ascii=False) + '\n')
    except OSError:
        pass


def ultima_attivita(path=ACTIVITY_LOG):
    from .gui_backend import file_tail
    for line in reversed(file_tail(path, 32000).splitlines()):
        try:
            evento = json.loads(line)
        except ValueError:
            continue
        if (isinstance(evento, dict)
                and all(isinstance(evento.get(key), str)
                        for key in ('sentito', 'esito', 'percorso'))
                and isinstance(evento.get('azioni'), list)
                and all(isinstance(value, str) for value in evento['azioni'])):
            return evento
    return {}
