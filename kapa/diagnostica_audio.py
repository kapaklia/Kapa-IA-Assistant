#!/usr/bin/env python3
"""Diagnostica vocale facoltativa: WAV locale dell'audio passato a Whisper.

Attiva: python scripts/diagnostica_audio.py on
Disattiva: python scripts/diagnostica_audio.py off
I file sono personali e NON devono essere pubblicati su GitHub.
"""

import json
import os
import sys
import uuid
import wave
from datetime import datetime
from pathlib import Path

import numpy as np
from .app_paths import PROJECT_DIR

BASE = PROJECT_DIR
FLAG = BASE / ".diagnostica_audio_attiva"
DESTINAZIONE = BASE / "diagnostica_audio"
FREQUENZA = 16000


def attiva() -> bool:
    return FLAG.is_file()


def salva_audio(audio) -> Path | None:
    """Salva lo stesso array passato al modello, senza elaborarlo prima del test."""
    if not attiva() or audio is None:
        return None
    try:
        dati = np.asarray(audio, dtype=np.float32)
        if dati.ndim != 1 or len(dati) == 0:
            return None
        DESTINAZIONE.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(DESTINAZIONE, 0o700)
        nome = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid.uuid4().hex[:6]
        percorso = DESTINAZIONE / f"{nome}.wav"
        audio_pcm = (np.clip(dati, -1.0, 1.0) * 32767).astype('<i2')
        fd = os.open(percorso, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as uscita, wave.open(uscita, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(FREQUENZA)
            wav.writeframes(audio_pcm.tobytes())
        return percorso
    except (OSError, ValueError, TypeError) as exc:
        print(f"[Diagnostica audio] Impossibile salvare WAV: {exc}", flush=True)
        return None


def salva_trascrizione(percorso: Path | None, testo: str, grezzo: str, secondi: float):
    if percorso is None:
        return
    try:
        dati = {
            "file_audio": percorso.name,
            "frequenza_hz": FREQUENZA,
            "trascrizione_whisper": grezzo,
            "trascrizione_filtrata": testo,
            "tempo_trascrizione_secondi": round(float(secondi), 3),
        }
        uscita = percorso.with_suffix('.json')
        fd = os.open(uscita, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(dati, f, ensure_ascii=False, indent=2)
    except (OSError, ValueError, TypeError) as exc:
        print(f"[Diagnostica audio] Impossibile salvare trascrizione: {exc}", flush=True)


def main() -> int:
    comando = sys.argv[1].lower() if len(sys.argv) == 2 else ''
    if comando == 'on':
        fd = os.open(FLAG, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(fd)
        print("Diagnostica ATTIVA: ogni comando registrato salverà un WAV locale.")
    elif comando == 'off':
        FLAG.unlink(missing_ok=True)
        print("Diagnostica DISATTIVATA. I WAV precedenti restano nella cartella diagnostica_audio/.")
    elif comando == 'status':
        print("Diagnostica ATTIVA" if attiva() else "Diagnostica disattivata")
    else:
        print("Uso: python scripts/diagnostica_audio.py on | off | status")
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
