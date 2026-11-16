#!/usr/bin/env python3
"""Confronto offline di faster-whisper su WAV della diagnostica Kapa.
Non cambia il programma, non attiva il microfono e non esegue comandi vocali.
"""
import argparse
import sys
import time
import wave
from pathlib import Path

import numpy as np


def leggi_wav(path):
    with wave.open(str(path), 'rb') as f:
        channels, width, rate = f.getnchannels(), f.getsampwidth(), f.getframerate()
        if width != 2:
            raise ValueError(f'{path.name}: WAV non PCM 16 bit (width={width})')
        raw = f.readframes(f.getnframes())
    x = np.frombuffer(raw, dtype='<i2').astype('float32') / 32768.0
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)
    if rate != 16000:
        raise ValueError(f'{path.name}: atteso WAV a 16000 Hz, trovato {rate} Hz')
    return x


def main():
    parser = argparse.ArgumentParser(description='Confronta Whisper Small e Medium senza modificare Kapa')
    parser.add_argument('cartella', nargs='?', default='diagnostica_audio', help='Cartella con i WAV (default: diagnostica_audio)')
    parser.add_argument('--solo-small', action='store_true', help='Non scarica Medium')
    parser.add_argument('--confronta-medium', action='store_true', help='Confronto diagnostico esplicito; può scaricare Medium, senza cambiare il motore')
    args = parser.parse_args()
    p = Path(args.cartella).expanduser()
    if p.is_file() and p.suffix.lower() == '.wav':
        files = [p]
    else:
        files = sorted(p.glob('*.wav')) if p.is_dir() else []
    if not files:
        sys.exit(f'Nessun WAV trovato in: {p.resolve()}')
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit('Manca faster-whisper nell’ambiente Python attivo. Avvia il test nello stesso ambiente dell’assistente.')

    print(f'WAV trovati: {len(files)}; nessun audio verrà inviato online.\n', flush=True)
    for name in (['small', 'medium'] if args.confronta_medium and not args.solo_small else ['small']):
        print(f'=== Caricamento {name} (Medium può essere scaricato al primo utilizzo) ===', flush=True)
        try:
            start = time.perf_counter()
            model = WhisperModel(name, device='cpu', compute_type='int8', cpu_threads=6)
            print(f'Modello pronto in {time.perf_counter()-start:.1f}s', flush=True)
            for audio_file in files:
                audio = leggi_wav(audio_file)
                for variant, prompt in (
                    ('senza prompt', None),
                    ('con prompt', 'Comandi vocali in italiano: metti play, metti pausa, alza il volume, abbassa il volume, apri Firefox.'),
                ):
                    start = time.perf_counter()
                    segments, _ = model.transcribe(
                        audio, language='it', beam_size=5, temperature=0.0,
                        vad_filter=False, condition_on_previous_text=False,
                        initial_prompt=prompt,
                    )
                    text = ' '.join(s.text.strip() for s in segments).strip()
                    elapsed = time.perf_counter() - start
                    print(f'{audio_file.name} | {variant}: {text!r} | {elapsed:.2f}s', flush=True)
        except Exception as exc:
            print(f'ERRORE con {name}: {exc}', file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
