# config.py
#
# Questo file contiene SOLO impostazioni (nomi, percorsi, chiavi).
# Non fa nulla da solo: gli altri file (main.py, tools.py) leggono
# queste informazioni da qui invece di riscriverle ogni volta.
#
# Perché separarlo? Se domani cambi modello Groq, o vuoi aggiungere
# una cartella nuova, la modifichi UNA volta qui, non la cerchi
# sparsa in mezzo alla logica.

import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from .app_paths import SOCKET_PATH, PROJECT_DIR

# Carica il file .env (dove tieni la chiave segreta GROQ_API_KEY)
load_dotenv(PROJECT_DIR / '.env')

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# llama-3.3-70b-versatile è stato deprecato da Groq il 17 giugno 2026.
# openai/gpt-oss-120b è il sostituto raccomandato ufficialmente da Groq,
# con supporto al tool calling e prestazioni migliori secondo la loro
# stessa documentazione. Se in futuro anche questo dovesse sparire, il
# nome giusto si controlla su console.groq.com/docs/deprecations.
GROQ_MODEL = "openai/gpt-oss-120b"

# Opzionale: se non la configuri, le funzioni YouTube "intelligenti"
# (che aprono direttamente il video giusto) ripiegano da sole su una
# semplice ricerca. Chiave gratuita su console.cloud.google.com,
# abilitando "YouTube Data API v3".
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
OBS_PORT = os.getenv('OBS_PORT', '4455')
OBS_PASSWORD = os.getenv('OBS_PASSWORD', '')

# Cartella "home" dell'utente (es: /home/tuonome)
HOME = Path.home()


def _rileva_cartella_utente(nome_xdg: str, nome_italiano: str, nome_inglese: str) -> Path:
    """
    Trova il percorso REALE di una cartella utente (Scrivania, Documenti, ecc.)
    in modo indipendente dalla lingua del sistema. Usiamo 'xdg-user-dir', un
    comando standard su Linux che conosce le cartelle nella lingua giusta:
    su un sistema in italiano ritorna '.../Scrivania', sullo stesso sistema
    ma in inglese '.../Desktop' — è Linux stesso a "tradurre", non dobbiamo
    indovinare noi né elencare a mano ogni lingua possibile.

    Se per qualche motivo xdg-user-dir non è disponibile (raro), proviamo
    prima il nome italiano, poi quello inglese, come rete di sicurezza.
    """
    try:
        risultato = subprocess.run(
            ["xdg-user-dir", nome_xdg],
            capture_output=True, text=True, timeout=3, check=True,
        )
        valore = risultato.stdout.strip()
        percorso = Path(valore)
        if valore and percorso.is_absolute() and percorso.is_dir():
            return percorso
    except Exception:
        pass  # xdg-user-dir non c'è o ha fallito: proviamo i fallback sotto

    if (HOME / nome_italiano).exists():
        return HOME / nome_italiano
    if (HOME / nome_inglese).exists():
        return HOME / nome_inglese

    # Nessuna delle due esiste ancora (es. prima volta): usiamo il nome
    # italiano come predefinito, verrà creata al primo utilizzo.
    return HOME / nome_italiano


# Mappa nome-parlato -> percorso reale, rilevato automaticamente sopra.
# "home" è un caso speciale: non è una sottocartella specifica come le altre,
# è la cartella personale dell'utente nella sua interezza. Path.home() la
# rileva DAL SISTEMA (funziona su qualunque PC Linux, con qualunque nome
# utente): non è mai scritta a mano, esattamente come xdg-user-dir per le
# altre cartelle. Il progetto deve restare "portabile" per chiunque lo usi.
CARTELLE_UTENTE = {
    "scrivania": _rileva_cartella_utente("DESKTOP", "Scrivania", "Desktop"),
    "documenti": _rileva_cartella_utente("DOCUMENTS", "Documenti", "Documents"),
    "download": _rileva_cartella_utente("DOWNLOAD", "Scaricati", "Downloads"),
    "immagini": _rileva_cartella_utente("PICTURES", "Immagini", "Pictures"),
    "video": _rileva_cartella_utente("VIDEOS", "Video", "Videos"),
    "musica": _rileva_cartella_utente("MUSIC", "Musica", "Music"),
    "home": HOME,
}

# Sinonimi: modi diversi (spesso in inglese, a volte in altre lingue) di
# chiamare le stesse cartelle. Formato: {nome_vero: [lista di sinonimi]}.
# Usato da comprensione.interpreta(), che riconosce anche piccoli errori
# di battitura oltre ai sinonimi elencati qui. Per aggiungere un nuovo modo
# di dire una cartella, basta aggiungere una riga qui.
#
# Nota: i NOMI REALI delle cartelle sul disco vengono già rilevati in modo
# automatico e indipendente dalla lingua (vedi _rileva_cartella_utente sopra).
# Questi alias servono per un'altra cosa: capire in che lingua/modo la
# PERSONA chiede la cartella, che può essere diverso dalla lingua del sistema
# (es. sistema in italiano, ma dici "desktop" o "pictures" all'inglese).
ALIAS_CARTELLE = {
    "scrivania": ["desktop", "escritorio", "bureau"],
    "documenti": ["docs", "document", "documents", "documentos", "documento"],
    "download": ["downloads", "scaricati", "descargas", "telechargements", "scaricamenti"],
    "immagini": ["pictures", "images", "imagenes", "photos", "foto", "immagine"],
    "video": ["videos", "vidéos", "videoclip", "filmati", "film"],
    "musica": ["music", "musique", "canzoni", "brani"],
    "home": ["cartella home", "home directory", "la mia home", "cartella personale"],
}

# ---------------------------------------------------------------------------
# INPUT VOCALE (modalità background: python main.py --background)
# ---------------------------------------------------------------------------
# Il microfono si apre SOLO quando premi la scorciatoia da tastiera (che
# lancia trigger.py) e si richiude appena finisci di parlare. Nessun
# ascolto continuo. Whisper gira in locale, a Groq arriva solo il TESTO.
# La diagnostica facoltativa può salvare WAV locali; normalmente è disattiva.

# Modello Whisper (via faster-whisper, gira su CPU: la GPU AMD non è
# supportata da questa libreria). Più grande = capisce meglio ma è più lento:
#   "small"  -> veloce, discreto in italiano
# Il modello operativo resta Small, come stabilito in AGENTS.md.
# Il primo avvio scarica il modello (da internet, una volta sola).
WHISPER_MODEL = "small"
WHISPER_LINGUA = "it"
WHISPER_COMPUTE = "int8"      # int8 = molto più leggero/veloce su CPU, qualità quasi uguale
WHISPER_THREADS = 6           # thread CPU usati; abbassa se rallenta il gioco

# Suggerimenti alla trascrizione (NON sono un dizionario obbligatorio).
# Termini comuni a molti utenti Linux/KDE e a comandi vocali in italiano.
# Nomi particolari come artisti, periferiche o giochi non vanno inseriti qui:
# puoi scriverli nel file facoltativo vocabolario_personale.txt (una riga per nome).
WHISPER_TERMINI_COMUNI = [
    # Linguaggio quotidiano dei comandi, dispositivi e sistemi diffusi.
    "file di testo", "scrivania", "volume", "percentuale", "screenshot",
    "browser", "Wi-Fi", "Bluetooth", "USB", "Linux", "Windows",
    "macOS", "Android", "KDE Plasma", "Firefox", "YouTube", "Steam",
    # Terminologia tecnica generale, non riferita a un singolo utente.
    "GPU Screen Recorder", "Docker", "Nginx", "PostgreSQL", "GitHub",
    "repository", "SSL", "DNS", "firewall", "Flatpak", "DNF", "PipeWire",
    "OBS Studio", "Discord", "Spotify", "terminale",
]

# File di nomi personali, opzionale: NON pubblicarlo con i dati degli utenti.
WHISPER_FILE_PERSONALE = PROJECT_DIR / "vocabolario_personale.txt"

# Rimuove soltanto i falsi crediti video più riconoscibili in FONDO alla
# trascrizione (es. "Sottotitoli a cura di QTSS"). Il testo originale resta
# visibile nel log per diagnosticare eventuali falsi positivi. Non rimuove
# frasi comuni come "buon appetito", che potrebbero essere state pronunciate.
WHISPER_FILTRA_CREDITI = True

# Frasi che Whisper a volte "inventa" quando registra silenzio o rumore.
FRASI_SPAZZATURA = [
    "sottotitoli",
    "amaraorg",
    "grazie per l'attenzione",
    "alla prossima",
    "grazie per la visione",
]

# Microfono: None = quello predefinito del sistema. Per sceglierne uno:
#   pactl list short sources      (copia il nome della colonna 2)
MIC_DEVICE = None

# Quando smettere di ascoltare (il microfono si chiude da solo):
VOCE_ATTESA_INIZIO = 6.0      # secondi: se non parli entro questo tempo, si chiude
VOCE_SILENZIO_FINE = 1.3      # secondi di silenzio dopo che hai parlato -> fine
VOCE_MAX_SECONDI = 45.0       # tetto massimo di registrazione, per sicurezza
VOCE_CODA_AUDIO = 0.35     # secondi di audio lasciati dopo il parlato (riduce rumore finale)
VOCE_SOGLIA_MIN = 0.012       # sensibilità minima (0-1): alza se scatta col rumore di fondo

# Le operazioni installa_applicazione/aggiorna_sistema aprono un terminale
# e chiedono conferma separata; nessuna password passa dall'assistente.
# Manteniamo bloccate a voce le operazioni distruttive sui file.
VOCE_FUNZIONI_ESCLUSE = ["elimina_file", "svuota_cestino"]

# Feedback: suoni (bip quando il microfono si apre/chiude) e notifiche.
# I suoni funzionano anche dentro i giochi a schermo intero; le notifiche
# popup di KDE invece possono essere soppresse dalla modalità "Non disturbare"
# (si attiva da sola con le app a schermo intero). Se i popup non compaiono
# in gioco, metti "critical" qui sotto.
VOCE_SUONI = True
VOCE_NOTIFICHE_URGENZA = "normal"   # "low", "normal" o "critical"

# Socket locale su cui il processo in background riceve il comando della
# scorciatoia. Solo il tuo utente può scriverci (permessi 0600).

# ---------------------------------------------------------------------------
# GPU SCREEN RECORDER
# ---------------------------------------------------------------------------
# "screen" cattura il primo monitor rilevato da GPU Screen Recorder, senza
# dipendere da nomi hardware (DP-1, HDMI-A-1, ...). Su PC multi-monitor,
# l'utente puo' scegliere un monitor esplicito tramite variabile d'ambiente:
# IA_GSR_TARGET=DP-1. La lista vera si ottiene con --list-monitors.
# "portal" e' disponibile su Wayland, ma puo' richiedere una selezione grafica.
GSR_TARGET = os.getenv("IA_GSR_TARGET", "screen").strip() or "screen"
GSR_AUDIO = "default_output"    # nome del dispositivo audio da registrare
GSR_FRAMERATE = 60
GSR_CARTELLA_OUTPUT = "video"   # una delle cartelle mappate sopra
