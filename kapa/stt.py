# stt.py (Speech-To-Text)
#
# Gestisce la voce in ENTRATA, in due pezzi separati:
#
#   Registratore  -> apre il microfono, registra finché non finisci di
#                    parlare, poi lo CHIUDE. Esiste solo mentre registra.
#   Trascrittore  -> trasforma l'audio in testo con Whisper (in locale).
#
# Garanzie sulla privacy (le volevi esplicitamente):
#   - il microfono si apre SOLO quando viene chiamato Registratore.registra()
#     (cioè quando premi la scorciatoia), e si chiude appena finisce
#   - l'audio resta in memoria, salvo diagnostica locale esplicitamente attivata
#   - l'audio non va mai su internet: a Groq arriva solo il testo trascritto
#
# Per registrare usiamo "parecord" (strumento di sistema, lo stesso pacchetto
# di pactl/paplay) invece di una libreria Python per l'audio: quando lo
# terminiamo, il microfono è davvero chiuso, e non serve installare altro.

import os
import re
import select
import shutil
import subprocess
import threading
import time

import numpy as np

from . import config
from .comprensione import normalizza

# Il Nortec (come molti microfoni USB) lavora meglio alla frequenza nativa
# di 48 kHz. Resta possibile tornare alla cattura precedente, senza modificare
# file di configurazione: IA_AUDIO_LEGACY=1 python main.py --background.
FREQUENZA_WHISPER = 16000
AUDIO_LEGACY = os.environ.get("IA_AUDIO_LEGACY", "").strip() == "1"
FREQUENZA = 16000 if AUDIO_LEGACY else 48000
CANALI = 1 if AUDIO_LEGACY else 2
SECONDI_PER_BLOCCO = 0.1
BYTES_PER_BLOCCO = int(FREQUENZA * SECONDI_PER_BLOCCO) * 2 * CANALI
BLOCCHI_CALIBRAZIONE = 4
BLOCCHI_VOCE_MINIMI = 3


def prepara_audio_whisper(blocchi: list[np.ndarray], rumore_rms: float = 0.0) -> np.ndarray:
    """Da s16le 48 kHz stereo a float32 16 kHz mono, senza dipendenze nuove.

    Nella modalità legacy i blocchi sono già mono a 16 kHz. Il filtro passa-
    alto rimuove il ronzio molto basso (< ~85 Hz), non la voce. Il guadagno
    viene limitato per non amplificare indiscriminatamente il rumore.
    """
    if not blocchi:
        return np.empty(0, dtype=np.float32)
    acquisito = np.concatenate(blocchi)
    if AUDIO_LEGACY:
        return acquisito.astype(np.float32, copy=False)

    # Rileviamo il canale più utile: se un ingresso è molto più debole dell'altro
    # evitiamo di fare la media di un canale vuoto con quello della voce.
    stereo = acquisito.reshape(-1, 2)
    rms_canali = np.sqrt(np.mean(stereo.astype(np.float64) ** 2, axis=0))
    if min(rms_canali) < max(rms_canali) * 0.35:
        mono = stereo[:, int(np.argmax(rms_canali))].copy()
    else:
        mono = stereo.mean(axis=1)

    # Filtro FIR passa-alto: togliamo il rumore continuo a bassissima frequenza
    # senza usare filtri PipeWire globali o cambiare la sorgente del sistema.
    # In frequenza lavoriamo sull'intera registrazione già conclusa.
    n = len(mono)
    spettro = np.fft.rfft(mono)
    freq = np.fft.rfftfreq(n, d=1.0 / FREQUENZA)
    # Transizione morbida 65-100 Hz: niente tagli bruschi in frequenza.
    attenuazione = np.clip((freq - 65.0) / 35.0, 0.0, 1.0)
    mono = np.fft.irfft(spettro * attenuazione, n=n).astype(np.float32)

    # Filtro antialias per sottocampionare 48 -> 16 kHz: cutoff ~7.3 kHz.
    tap = np.arange(-48, 49, dtype=np.float64)
    taglio = 7300.0 / FREQUENZA
    fir = 2 * taglio * np.sinc(2 * taglio * tap) * np.hamming(len(tap))
    fir /= fir.sum()
    mono = np.convolve(mono, fir.astype(np.float32), mode="same")[::3]

    # Solo guadagno moderato e controllato sui tratti vocali (non sui silenzi).
    # Rumore rilevato all'inizio in scala 0..1, senza soppressione aggressiva.
    blocchi_rms = [float(np.sqrt(np.mean(b ** 2))) for b in np.array_split(mono, max(1, len(mono) // 1600)) if len(b)]
    attivi = [r for r in blocchi_rms if r > max(0.012, rumore_rms * 2.5)]
    if attivi:
        livello_voce = float(np.median(attivi))
        guadagno = min(3.5, max(1.0, 0.11 / max(livello_voce, 1e-6)))
        picco = float(np.max(np.abs(mono))) if len(mono) else 0.0
        if picco:
            guadagno = min(guadagno, 0.9 / picco)
        mono *= guadagno
    return np.clip(mono, -1.0, 1.0).astype(np.float32)


class MicrofonoNonDisponibile(Exception):
    pass


def comando_registrazione() -> list:
    """Il comando che registra dal microfono scrivendo l'audio grezzo su stdout."""
    if not shutil.which("parecord"):
        raise MicrofonoNonDisponibile(
            "parecord non trovato. Installa con: sudo dnf install pulseaudio-utils"
        )
    comando = [
        "parecord", "--raw", "--format=s16le",
        f"--rate={FREQUENZA}", f"--channels={CANALI}", "--latency-msec=50",
    ]
    if config.MIC_DEVICE:
        comando.append(f"--device={config.MIC_DEVICE}")
    return comando


def _blocchi(processo, ferma: threading.Event, limite: float):
    """Legge l'audio dal processo e lo restituisce a blocchi esatti da 0,1 s.
    Si interrompe se 'ferma' viene impostato, se si supera il 'limite' di
    tempo, o se il processo di registrazione termina."""
    buffer = b""
    while not ferma.is_set() and time.monotonic() < limite:
        pronto, _, _ = select.select([processo.stdout], [], [], 0.2)
        if not pronto:
            if processo.poll() is not None:
                return
            continue
        parte = os.read(processo.stdout.fileno(), BYTES_PER_BLOCCO)
        if not parte:
            return
        buffer += parte
        while len(buffer) >= BYTES_PER_BLOCCO:
            yield buffer[:BYTES_PER_BLOCCO]
            buffer = buffer[BYTES_PER_BLOCCO:]


class Registratore:
    def registra(self, ferma: threading.Event = None):
        """
        Apre il microfono e registra finché succede UNA di queste cose:
          - finisci di parlare (silenzio per VOCE_SILENZIO_FINE secondi)
          - 'ferma' viene impostato (secondo tocco della scorciatoia)
          - passano VOCE_MAX_SECONDI (tetto di sicurezza)
          - non parli entro VOCE_ATTESA_INIZIO secondi
        Poi chiude il microfono. Ritorna l'audio (array numpy float32, 16 kHz)
        oppure None se non è stato rilevato parlato.
        """
        ferma = ferma or threading.Event()
        comando = comando_registrazione()
        processo = subprocess.Popen(
            comando, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0
        )

        inizio = time.monotonic()
        limite = inizio + config.VOCE_MAX_SECONDI
        blocchi = []
        livelli = []
        soglia = None
        rumore = 0.0
        ha_parlato = False
        blocchi_voce = 0
        silenzio = 0.0
        fine_per_silenzio = False

        def valuta(livello: float) -> bool:
            """Aggiorna lo stato con un blocco; True se abbiamo finito di parlare."""
            nonlocal ha_parlato, blocchi_voce, silenzio
            if livello >= soglia:
                ha_parlato = True
                blocchi_voce += 1
                silenzio = 0.0
            elif ha_parlato:
                silenzio += SECONDI_PER_BLOCCO
            return ha_parlato and silenzio >= config.VOCE_SILENZIO_FINE

        try:
            for blocco in _blocchi(processo, ferma, limite):
                campioni = np.frombuffer(blocco, dtype=np.int16).astype(np.float32) / 32768.0
                # In stereo la voce può essere su un solo canale: rileviamo
                # il parlato dal canale più forte, non dalla media dei due.
                if CANALI == 2:
                    canali = campioni.reshape(-1, 2)
                    livello = float(np.max(np.sqrt(np.mean(canali ** 2, axis=0))))
                else:
                    livello = float(np.sqrt(np.mean(campioni ** 2)))
                blocchi.append(campioni)

                if soglia is None:
                    # Fase di calibrazione: misuriamo il rumore di fondo nei
                    # primi 0,4 s per decidere quanto "forte" deve essere la voce.
                    livelli.append(livello)
                    if len(livelli) < BLOCCHI_CALIBRAZIONE:
                        continue
                    rumore = float(np.median(livelli))
                    minimo = config.VOCE_SOGLIA_MIN
                    # Se già all'inizio il livello è alto, probabilmente stavi
                    # già parlando (non è rumore): usiamo la soglia minima.
                    soglia = minimo if rumore > minimo * 3 else max(minimo, rumore * 2.5)
                    if any([valuta(l) for l in livelli]):
                        break
                    continue

                if valuta(livello):
                    fine_per_silenzio = True
                    break
                if not ha_parlato and time.monotonic() - inizio >= config.VOCE_ATTESA_INIZIO:
                    break
        finally:
            # In ogni caso (fine normale, errore, stop) chiudiamo il microfono.
            codice_prima_stop = processo.poll()
            if codice_prima_stop is None:
                processo.terminate()
            try:
                processo.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                processo.kill()
                processo.wait()
            if processo.stdout:
                processo.stdout.close()
            if processo.stderr:
                processo.stderr.close()
        if codice_prima_stop is not None and codice_prima_stop != 0:
            raise MicrofonoNonDisponibile('Acquisizione audio fallita: verifica sorgente e server PulseAudio/PipeWire.')

        if not ha_parlato or blocchi_voce < BLOCCHI_VOCE_MINIMI:
            return None
        if fine_per_silenzio:
            # Non inviare a Whisper tutto il silenzio usato per decidere di
            # terminare: può inventare frasi durante quel tratto vuoto.
            # Lasciamo 0,35 s per non tagliare le consonanti finali morbide.
            da_togliere = max(0, int((silenzio - config.VOCE_CODA_AUDIO) / SECONDI_PER_BLOCCO))
            if da_togliere and len(blocchi) > da_togliere:
                blocchi = blocchi[:-da_togliere]
        return prepara_audio_whisper(blocchi, rumore_rms=rumore if soglia is not None else 0.0)


class Trascrittore:
    def __init__(self, modello=None):
        """'modello' serve solo per i test: normalmente viene caricato
        faster-whisper (la prima volta scarica il modello da internet)."""
        if modello is None:
            from faster_whisper import WhisperModel
            print(f"Caricamento del modello vocale '{config.WHISPER_MODEL}' "
                  "(la prima volta viene scaricato, può volerci un po')...", flush=True)
            modello = WhisperModel(
                config.WHISPER_MODEL,
                device="cpu",
                compute_type=config.WHISPER_COMPUTE,
                cpu_threads=config.WHISPER_THREADS,
            )
        self.modello = modello
        self.ultima_trascrizione_grezza = ""

    @staticmethod
    def pulisci_allucinazioni(testo: str) -> str:
        """Elimina SOLO crediti di sottotitoli standard, quando sono in coda.

        Non prova a correggere nomi propri o a cancellare frasi generiche:
        'Buon appetito', per esempio, potrebbe essere stato pronunciato.
        Manteniamo la trascrizione grezza per controllare eventuali falsi
        positivi (viene mostrata dal demone se differisce dalla versione pulita).
        """
        if not config.WHISPER_FILTRA_CREDITI:
            return testo.strip()
        credito = (
            r"(?:Sottotitoli\s+a\s+cura\s+di\s+(?:QTSS|QTS|QSS)|"
            r"Sottotitoli\s+creati\s+dalla\s+comunit[àa]\s+Amara(?:\.org)?)"
        )
        # Rimuovi solo il credito finale, separato da una frase conclusa
        # oppure presente come unica trascrizione. Non tagliare il contenuto
        # autentico che si trova prima del punto.
        fine = re.search(r"(?:^|(?<=[.!?])\s+)" + credito + r"[.!?]*\s*$",
                         testo.strip(), flags=re.IGNORECASE)
        return (testo[:fine.start()] if fine else testo).strip()

    def trascrivi(self, audio, prompt: str = None) -> str:
        """Trasforma l'audio in testo. 'prompt' è un elenco di parole attese
        (comandi, nomi dei giochi): aiuta Whisper a non storpiarle."""
        segmenti, _ = self.modello.transcribe(
            audio,
            language=config.WHISPER_LINGUA,
            beam_size=5,
            temperature=0.0,
            vad_filter=False,                 # la registrazione ha già rilevato il parlato
            condition_on_previous_text=False,
            initial_prompt=prompt,
        )
        grezzo = " ".join(s.text.strip() for s in segmenti).strip()
        self.ultima_trascrizione_grezza = grezzo
        return self.pulisci_allucinazioni(grezzo)

    @staticmethod
    def e_allucinazione(testo: str) -> bool:
        """Filtra le frasi tipiche che Whisper 'inventa' su silenzio/rumore."""
        testo_norm = normalizza(testo)
        # Una frase legittima lunga NON va scartata solo perché contiene
        # "grazie per l'attenzione" o una parola simile.
        return len(testo_norm) < 2 or testo_norm in {normalizza(f) for f in config.FRASI_SPAZZATURA}
