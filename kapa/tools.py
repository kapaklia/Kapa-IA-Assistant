# tools.py
#
# QUESTO FILE CONTIENE TUTTO QUELLO CHE L'ASSISTENTE SA FARE:
#   1. la funzione vera (il codice che esegue l'azione)
#   2. il suo "biglietto da visita" per Groq (nome, descrizione, parametri)
#
# Tenerli vicini (funzione + biglietto da visita) evita un problema classico:
# aggiungi una funzione nuova e ti dimentichi di "presentarla" a Groq, oppure
# la presenti ma poi la lista visibile all'utente non si aggiorna. Qui invece
# c'è UN SOLO posto da modificare per aggiungere un comando nuovo.
#
# In fondo al file trovi TOOLS_SCHEMA e FUNZIONI_DISPONIBILI: sono costruiti
# automaticamente leggendo la lista qui sotto, main.py li importa e basta.

import os
import math
import stat
import re
import shlex
import shutil
import signal
import subprocess
import threading
import tempfile
import time
from datetime import datetime
from pathlib import Path

from . import config
from . import root_tools
from . import comprensione
from . import obs_control


# ---------------------------------------------------------------------------
# RISOLUZIONE CARTELLE
#
# Questa funzione è usata da TUTTE le funzioni sotto che devono capire "dove"
# lavorare. Prima ogni funzione faceva config.CARTELLE_UTENTE.get(cartella,
# default_documenti): se Groq scriveva qualcosa come "scrivania/scimmietta"
# (una sottocartella), quella stringa non esisteva nella mappa e si finiva
# SEMPRE E SILENZIOSAMENTE in Documenti, anche se l'utente aveva chiesto la
# scrivania. Il codice diceva "fatto" ma il file finiva nel posto sbagliato.
#
# Ora: se il nome non è valido, si ritorna None e la funzione chiamante deve
# dirlo chiaramente all'utente, MAI ripiegare in silenzio su un'altra cartella.
# ---------------------------------------------------------------------------
def _risolvi_cartella(cartella: str):
    """
    Traduce un nome di cartella in un percorso reale.
    Accetta sia un nome semplice ('scrivania') sia un sottopercorso
    ('scrivania/scimmietta'), purché resti dentro una delle cartelle
    mappate in config.py. Ritorna None se il nome non è valido o se
    il sottopercorso tenta di "scappare" fuori (es. con ../..).
    """
    if not cartella:
        return config.CARTELLE_UTENTE["documenti"]

    if not isinstance(cartella, str) or Path(cartella).is_absolute():
        return None
    cartella = cartella.strip().rstrip("/")
    if any(p.startswith('.') for p in cartella.split('/')):
        return None
    parti = cartella.split("/", 1)
    base_nome_grezzo = parti[0].lower()

    # comprensione.interpreta riconosce sia i sinonimi (es. "desktop") sia
    # piccoli errori di battitura (es. "scrivanie" invece di "scrivania").
    base_nome = comprensione.interpreta(base_nome_grezzo, config.ALIAS_CARTELLE)

    if base_nome is None or base_nome not in config.CARTELLE_UTENTE:
        return None

    base = config.CARTELLE_UTENTE[base_nome]

    if len(parti) == 1:
        return base

    percorso_finale = (base / parti[1]).resolve()
    base_risolta = base.resolve()

    if percorso_finale != base_risolta and base_risolta not in percorso_finale.parents:
        return None  # ha provato a uscire dalla cartella base con ../..

    return percorso_finale


def _percorso_sicuro(cartella_base: Path, percorso: Path) -> bool:
    """Controlla che un percorso stia DAVVERO dentro la cartella prevista,
    senza scappatoie tipo '../../' (usata per nomi di FILE, non di cartelle:
    la validazione della cartella la fa già _risolvi_cartella sopra)."""
    return cartella_base.resolve() in percorso.resolve().parents


def _permesso_negato() -> str:
    """
    Messaggio uniforme quando il sistema operativo stesso nega l'accesso
    (es. un file di root finito per errore dentro la home, o permessi
    particolari su una sottocartella). REGOLA IMPORTANTE: l'assistente non
    gestisce MAI password per le operazioni sui file — quel meccanismo è
    riservato alle sole operazioni di installazione e aggiornamento. Se un'azione
    sui file richiede permessi elevati, ci si ferma qui, punto.
    """
    return (
        "Permesso negato: questa operazione richiede diritti che il tuo utente "
        "non ha su questo file o cartella. Non gestisco password per le "
        "operazioni sui file: se vuoi procedere, fallo direttamente dal terminale "
        "con i permessi giusti."
    )


# ---------------------------------------------------------------------------
# CREA / AGGIUNGI TESTO A FILE (mai sovrascrivere inavvertitamente)
# ---------------------------------------------------------------------------
_ESTENSIONI_MODIFICABILI = {"", ".txt", ".md", ".csv", ".log"}


def _nome_file_valido(nome_file: str):
    """Rifiuta percorsi assoluti, sottopercorsi e nomi nascosti.
    La cartella si sceglie SOLO con l'argomento 'cartella'.
    """
    if not isinstance(nome_file, str):
        return None
    nome = nome_file.strip().strip('\"“”')
    if (not nome or nome in (".", "..") or nome.startswith(".")
            or "/" in nome or "\\" in nome or "\x00" in nome
            or len(nome) > 200):
        return None
    return nome


def _nome_senza_estensione_testuale(nome: str) -> bool:
    """Anche 'livello 2.0' è un nome SENZA estensione di testo.

    Una coda numerica (.0, .1, .2026) può far parte del nome, non è
    necessariamente un'estensione: in quel caso aggiungiamo/cercamo .txt.
    Al contrario, .pdf o .py restano estensioni esplicite non modificabili.
    """
    estensione = Path(nome).suffix
    return not estensione or bool(re.fullmatch(r"\.\d+", estensione))


def _estensione_testo(nome: str) -> bool:
    return (_nome_senza_estensione_testuale(nome)
            or Path(nome).suffix.lower() in _ESTENSIONI_MODIFICABILI)


def _percorso_file_esistente(nome_file: str, cartella: str = "documenti"):
    """Individua un file di testo senza indovinare se ci sono più alternative.

    Se chiedi 'Test Whisper', trova 'Test Whisper.txt' quando è l'unico
    candidato, ma NON sceglie tra entrambi se esistono anche 'Test Whisper'
    (il caso reale emerso nei test). Non segue link simbolici.
    """
    base = _risolvi_cartella(cartella)
    if base is None:
        return None, f"Cartella '{cartella}' non valida."
    nome = _nome_file_valido(nome_file)
    if nome is None or not _estensione_testo(nome):
        return None, "Specifica un nome di file di testo valido (.txt, .md, .csv o .log)."
    if not base.is_dir():
        return None, f"La cartella '{cartella}' non esiste."
    try:
        alternative = {nome.casefold()}
        if _nome_senza_estensione_testuale(nome):
            alternative.add((nome + ".txt").casefold())
        trovati = [e for e in base.iterdir() if e.name.casefold() in alternative]
        if not trovati:
            return None, f"Non trovo il file '{nome}' in {base}. Non ne creo uno diverso: chiedimi prima di crearlo."
        if len(trovati) > 1:
            nomi = ", ".join(repr(p.name) for p in sorted(trovati, key=lambda x: x.name))
            return None, f"Ci sono più file possibili ({nomi}). Pronuncia il nome completo, inclusa l'estensione."
        percorso = trovati[0]
        if percorso.is_symlink() or not percorso.is_file() or not _percorso_sicuro(base, percorso):
            return None, "Il percorso non è un normale file all'interno della cartella consentita."
        if not _estensione_testo(percorso.name):
            return None, "Posso aggiungere testo solo a file di testo."
        return percorso, None
    except PermissionError:
        return None, _permesso_negato()
    except OSError as e:
        return None, f"Errore nell'accesso al file: {e}"


def crea_file(nome_file: str, contenuto: str = "", cartella: str = "documenti") -> str:
    """Crea un NUOVO file di testo .txt per default, senza sovrascrivere."""
    base = _risolvi_cartella(cartella)
    if base is None:
        return f"Cartella '{cartella}' non valida."
    nome = _nome_file_valido(nome_file)
    if nome is None:
        return "Nome file non valido: usa un nome semplice, senza percorsi o slash."
    if _nome_senza_estensione_testuale(nome):
        nome += ".txt"
    if not _estensione_testo(nome):
        return "Questa funzione crea solo file di testo (.txt, .md, .csv o .log)."
    try:
        base.mkdir(parents=True, exist_ok=True)
        percorso = base / nome
        if not _percorso_sicuro(base, percorso):
            return "Il file richiesto è fuori dalla cartella consentita."
        # La modalità 'x' fallisce se esiste già: NON tronca il file.
        with percorso.open("x", encoding="utf-8") as f:
            f.write(contenuto if isinstance(contenuto, str) else str(contenuto))
        return f"File '{nome}' creato in {base} con successo."
    except FileExistsError:
        return f"Il file '{nome}' esiste già in {base}: non lo sovrascrivo. Per continuare a scrivere, usa 'aggiungi al file'."
    except PermissionError:
        return _permesso_negato()
    except OSError as e:
        return f"Errore durante la creazione del file: {e}"


SCHEMA_CREA_FILE = {
    "type": "function",
    "function": {
        "name": "crea_file",
        "description": (
            "Crea un NUOVO file di testo. Senza estensione aggiunge .txt. "
            "NON sovrascrive file già esistenti: per scriverci usa scrivi_file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nome_file": {"type": "string", "description": "Nome del file, es. lista.txt. Se manca .txt viene aggiunto."},
                "contenuto": {"type": "string", "description": "Testo da scrivere, se pronunciato nello stesso comando"},
                "cartella": {"type": "string", "description": "scrivania, documenti, download, immagini, video, musica, home o una sottocartella"},
            },
            "required": ["nome_file"],
        },
    },
}


def scrivi_file(nome_file: str, contenuto: str, cartella: str = "documenti") -> str:
    """Aggiunge testo a un file esistente senza alterarne il contenuto.

    Non crea file, non sovrascrive, non segue link simbolici. Un comando
    esplicito di sostituzione del contenuto richiederebbe un altro flusso
    con conferma: intenzionalmente non è supportato qui.
    """
    percorso, errore = _percorso_file_esistente(nome_file, cartella)
    if errore:
        return errore
    if not isinstance(contenuto, str) or not contenuto.strip():
        return "Non ho ricevuto alcun testo da scrivere."
    try:
        # O_NOFOLLOW evita la sostituzione del file con un link simbolico
        # tra il controllo e l'apertura. O_APPEND evita di troncare il file.
        flags = os.O_RDWR | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(percorso, flags)
        try:
            dimensione = os.fstat(fd).st_size
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return "Il file non è un file di testo regolare."
            separatore = "\n" if dimensione and os.pread(fd, 1, dimensione - 1) != b"\n" else ""
            dati = (separatore + contenuto).encode("utf-8")
            while dati:
                scritti = os.write(fd, dati)
                if scritti <= 0:
                    raise OSError("Scrittura interrotta")
                dati = dati[scritti:]
        finally:
            os.close(fd)
        return f"Testo aggiunto a '{percorso.name}' in {percorso.parent}, senza cancellare quello precedente."
    except PermissionError:
        return _permesso_negato()
    except OSError as e:
        return f"Errore durante la scrittura nel file: {e}"


SCHEMA_SCRIVI_FILE = {
    "type": "function",
    "function": {
        "name": "scrivi_file",
        "description": (
            "AGGIUNGE un testo a un file già esistente, senza sovrascrivere. "
            "Usa per 'scrivi nel file X', 'aggiungi al file X', 'trascrivi nel file X'. "
            "Se il file non esiste, segnala errore: NON creare un altro file. "
            "Quando il nome è senza estensione cerca anche nome.txt; se ambiguo chiede chiarimenti."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nome_file": {"type": "string", "description": "Nome del file di testo esistente"},
                "contenuto": {"type": "string", "description": "Testo ESATTO pronunciato dall'utente; non parafrasare e non correggere"},
                "cartella": {"type": "string", "description": "scrivania, documenti, download, immagini, video, musica, home o sottocartella"},
            },
            "required": ["nome_file", "contenuto"],
        },
    },
}


# ---------------------------------------------------------------------------
# LEGGI FILE
# ---------------------------------------------------------------------------
def leggi_file(nome_file: str, cartella: str = "documenti") -> str:
    """Legge e ritorna il contenuto di un file di testo."""
    cartella_scelta = _risolvi_cartella(cartella)
    if cartella_scelta is None:
        return f"Cartella '{cartella}' non valida. Usa scrivania, documenti, download, immagini, video, musica, oppure 'home' per l'intera cartella personale."

    nome = _nome_file_valido(nome_file)
    if nome is None:
        return "Nome file non valido."
    percorso = cartella_scelta / nome
    if percorso.is_symlink() or not _percorso_sicuro(cartella_scelta, percorso):
        return "Il percorso non è un file consentito."

    if not percorso.exists():
        return f"Il file '{nome_file}' non esiste in {cartella_scelta}."

    try:
        fd = os.open(percorso, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'r', encoding='utf-8') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return "Il percorso non è un file regolare."
            contenuto = stream.read(65537)
        if len(contenuto) > 65536:
            return "File troppo grande: limite di lettura 65536 caratteri."
        return contenuto if contenuto else "Il file è vuoto."
    except PermissionError:
        return _permesso_negato()
    except Exception as e:
        return f"Errore durante la lettura del file: {e}"


SCHEMA_LEGGI_FILE = {
    "type": "function",
    "function": {
        "name": "leggi_file",
        "description": "Legge e mostra il contenuto di un file di testo esistente.",
        "parameters": {
            "type": "object",
            "properties": {
                "nome_file": {"type": "string", "description": "Nome del file da leggere"},
                "cartella": {"type": "string", "description": "Cartella dove si trova: scrivania, documenti, download, immagini, video, musica, oppure 'home' per l'intera cartella personale (anche con sottocartelle, es. 'scrivania/nome_sottocartella')"},
            },
            "required": ["nome_file"],
        },
    },
}


# ---------------------------------------------------------------------------
# ELENCA FILE
# ---------------------------------------------------------------------------
def elenca_file(cartella: str = "documenti") -> str:
    """Elenca i file presenti in una cartella."""
    cartella_scelta = _risolvi_cartella(cartella)
    if cartella_scelta is None:
        return f"Cartella '{cartella}' non valida. Usa scrivania, documenti, download, immagini, video, musica, oppure 'home' per l'intera cartella personale."

    if not cartella_scelta.exists():
        return f"La cartella {cartella_scelta} non esiste."

    try:
        file_trovati = [f.name for f in cartella_scelta.iterdir() if f.is_file()]
    except PermissionError:
        return _permesso_negato()
    except Exception as e:
        return f"Errore durante la lettura della cartella: {e}"

    if not file_trovati:
        return f"La cartella {cartella_scelta} è vuota."

    return f"File in {cartella_scelta}: " + ", ".join(sorted(file_trovati))


SCHEMA_ELENCA_FILE = {
    "type": "function",
    "function": {
        "name": "elenca_file",
        "description": "Elenca i file presenti in una cartella (scrivania, documenti, download, immagini, video, musica, oppure 'home' per l'intera cartella personale).",
        "parameters": {
            "type": "object",
            "properties": {
                "cartella": {"type": "string", "description": "Cartella da elencare: scrivania, documenti, download, immagini, video, musica, oppure 'home' per l'intera cartella personale (anche con sottocartelle)"},
            },
        },
    },
}


# ---------------------------------------------------------------------------
# CREA CARTELLA
# ---------------------------------------------------------------------------
def crea_cartella(nome_cartella: str, cartella_padre: str = "documenti") -> str:
    """Crea una nuova sottocartella dentro una delle cartelle mappate."""
    padre = _risolvi_cartella(cartella_padre)
    if padre is None:
        return f"Cartella '{cartella_padre}' non valida. Usa scrivania, documenti, download, immagini, video, musica, oppure 'home' per l'intera cartella personale."

    nome = _nome_file_valido(nome_cartella)
    if nome is None:
        return "Nome cartella non valido: usa un nome semplice."
    nuova = padre / nome
    if nuova.is_symlink() or not _percorso_sicuro(padre, nuova):
        return "Percorso cartella non consentito."

    try:
        nuova.mkdir(parents=True, exist_ok=True)
        return f"Cartella '{nome_cartella}' creata in {padre}."
    except PermissionError:
        return _permesso_negato()
    except Exception as e:
        return f"Errore durante la creazione della cartella: {e}"


SCHEMA_CREA_CARTELLA = {
    "type": "function",
    "function": {
        "name": "crea_cartella",
        "description": "Crea una nuova cartella dentro scrivania, documenti, download, immagini, video, musica, oppure 'home' per l'intera cartella personale.",
        "parameters": {
            "type": "object",
            "properties": {
                "nome_cartella": {"type": "string", "description": "Nome della nuova cartella"},
                "cartella_padre": {"type": "string", "description": "Dove crearla: scrivania, documenti, download, immagini, video, musica, oppure 'home' per l'intera cartella personale (anche con sottocartelle esistenti)"},
            },
            "required": ["nome_cartella"],
        },
    },
}


# ---------------------------------------------------------------------------
# SVUOTA CESTINO
#
# Importante: il cestino (~/.local/share/Trash) è DENTRO la home dell'utente,
# quindi un utente normale ha già tutti i permessi per svuotarlo. Questa
# funzione esiste apposta per evitare che Groq "improvvisi" un comando shell
# con sudo per un'operazione che non ne ha bisogno (è successo: un comando
# con $USER non espanso che falliva in silenzio, senza svuotare nulla).
# ---------------------------------------------------------------------------
def svuota_cestino() -> str:
    """Svuota il cestino dell'utente. Non richiede permessi di root."""
    if shutil.which('gio'):
        try:
            subprocess.run(['gio', 'trash', '--empty'], check=True,
                           capture_output=True, timeout=15)
            return 'Cestino svuotato.'
        except (OSError, subprocess.SubprocessError):
            return 'Svuotamento del cestino non riuscito: verifica dal gestore file.'
    xdg = os.environ.get('XDG_DATA_HOME', '')
    base = Path(xdg) if xdg and Path(xdg).is_absolute() else config.HOME / '.local/share'
    cartella_cestino = base / 'Trash'

    if not cartella_cestino.exists():
        return "Il cestino è vuoto (non è ancora stato usato)."

    rimossi = 0
    try:
        for sottocartella in ("files", "info"):
            percorso = cartella_cestino / sottocartella
            if not percorso.exists():
                continue
            for elemento in percorso.iterdir():
                if elemento.is_dir() and not elemento.is_symlink():
                    shutil.rmtree(elemento)
                else:
                    elemento.unlink()
                rimossi += 1
    except PermissionError:
        return _permesso_negato()
    except Exception as e:
        return f"Errore durante lo svuotamento del cestino: {e}"

    if rimossi == 0:
        return "Il cestino era già vuoto."
    return f"Cestino svuotato: rimossi {rimossi} elementi."


SCHEMA_SVUOTA_CESTINO = {
    "type": "function",
    "function": {
        "name": "svuota_cestino",
        "description": (
            "Svuota il cestino dell'utente. NON richiede permessi di root: il cestino "
            "è dentro la home, un utente normale può già svuotarlo. Usa SEMPRE questa "
            "funzione per svuotare il cestino, mai esegui_come_root."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


# ---------------------------------------------------------------------------
# YOUTUBE
#
# Due funzioni, non una: youtube_cerca funziona SEMPRE (apre solo i
# risultati, nessuna chiave richiesta). youtube_riproduci prova ad aprire
# direttamente il video giusto usando la YouTube Data API di Google, ma se
# la chiave manca o qualcosa va storto (rete assente, quota esaurita),
# ripiega da sola su youtube_cerca — non deve mai fallire "a vuoto".
#
# Usiamo xdg-open per aprire il link: è lo standard Linux che apre
# qualunque URL nel browser predefinito dell'utente, non solo Brave.
# ---------------------------------------------------------------------------
def _apri_url(url: str) -> bool:
    """Apre un URL nel browser predefinito del sistema. Ritorna True/False
    a seconda che sia riuscito a lanciare il comando."""
    try:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _cerca_id_video_youtube(query: str):
    """Interroga la YouTube Data API per trovare l'ID del video più
    pertinente. Ritorna None (senza sollevare errori) se manca la chiave,
    la rete non risponde, la quota è esaurita, o qualunque altro problema:
    il chiamante deve poter ripiegare senza preoccuparsi del motivo esatto."""
    if not config.YOUTUBE_API_KEY:
        return None

    import urllib.parse
    import urllib.request
    import json as json_lib

    parametri = urllib.parse.urlencode({
        "part": "snippet",
        "maxResults": 1,
        "q": query,
        "type": "video",
        "key": config.YOUTUBE_API_KEY,
    })
    url = f"https://www.googleapis.com/youtube/v3/search?{parametri}"

    try:
        with urllib.request.urlopen(url, timeout=5) as risposta:
            dati = json_lib.loads(risposta.read().decode("utf-8"))
        elementi = dati.get("items", [])
        return elementi[0]["id"]["videoId"] if elementi else None
    except Exception:
        return None


def google_cerca(query: str) -> str:
    """Apre i risultati Google nel browser predefinito, senza API."""
    import urllib.parse
    query = query.strip()
    if not query:
        return "Specifica cosa cercare su Google."
    url = "https://www.google.com/search?" + urllib.parse.urlencode({"q": query})
    if _apri_url(url):
        return f"Ho aperto la ricerca Google per '{query}'."
    return "Non sono riuscito ad aprire il browser."


SCHEMA_GOOGLE_CERCA = {
    "type": "function",
    "function": {
        "name": "google_cerca",
        "description": "Cerca su Google aprendo i risultati nel browser predefinito. Non legge né riassume le pagine e non richiede chiavi API Google.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Testo da cercare su Google"}},
            "required": ["query"],
        },
    },
}


def youtube_cerca(query: str) -> str:
    """Apre la pagina dei risultati di ricerca YouTube. Non richiede
    nessuna configurazione, funziona sempre."""
    import urllib.parse
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)

    if _apri_url(url):
        return f"Ho aperto la ricerca YouTube per '{query}'."
    return "Non sono riuscito ad aprire il browser."


SCHEMA_YOUTUBE_CERCA = {
    "type": "function",
    "function": {
        "name": "youtube_cerca",
        "description": (
            "Apre la pagina dei risultati di ricerca YouTube per una query, mostrando "
            "una lista tra cui scegliere (non apre direttamente un video). Funziona "
            "sempre, non richiede configurazione."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Cosa cercare su YouTube"}},
            "required": ["query"],
        },
    },
}


def youtube_riproduci(query: str) -> str:
    """Cerca e apre DIRETTAMENTE il video più pertinente su YouTube (pronto
    a partire), usando la YouTube Data API. Se non riesce (chiave assente,
    errore di rete, quota esaurita), ripiega automaticamente sulla ricerca
    semplice invece di fallire senza fare nulla."""
    id_video = _cerca_id_video_youtube(query)

    if id_video:
        url = f"https://www.youtube.com/watch?v={id_video}"
        if _apri_url(url):
            return f"Ho aperto '{query}' su YouTube, dovrebbe partire in automatico."
        return "Ho trovato il video giusto ma non sono riuscito ad aprire il browser."

    # Ripiego: niente ID trovato (chiave assente, rete assente, ecc.)
    esito_ricerca = youtube_cerca(query)
    return f"Non sono riuscito ad aprire direttamente il video giusto, ho aperto la ricerca invece. {esito_ricerca}"


SCHEMA_YOUTUBE_RIPRODUCI = {
    "type": "function",
    "function": {
        "name": "youtube_riproduci",
        "description": (
            "Cerca e apre DIRETTAMENTE il video più pertinente su YouTube, pronto a "
            "partire in automatico. Usa questa (non youtube_cerca) quando l'utente "
            "chiede di 'mettere', 'riprodurre' o 'far partire' qualcosa su YouTube. "
            "Se la chiave API non è configurata, ripiega da sola sulla ricerca semplice."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Cosa riprodurre su YouTube (es. nome della canzone o del video)"}},
            "required": ["query"],
        },
    },
}


# ---------------------------------------------------------------------------
# RICERCA FILE (in tutte le cartelle insieme, se non specifichi quale)
# ---------------------------------------------------------------------------
def cerca_file(pattern: str, cartella: str = None, estensione: str = None, max_risultati: int = 15) -> str:
    """
    Cerca un file per nome (corrispondenza parziale, case-insensitive).
    Se 'cartella' non è specificata, cerca in TUTTE le cartelle standard
    insieme (scrivania, documenti, download, immagini, video, musica) —
    non serve sapere in anticipo dove si trova.
    """
    if not pattern or not pattern.strip():
        return "Specifica almeno una parte del nome del file da cercare."

    if type(max_risultati) is not int or not 1 <= max_risultati <= 100:
        return 'Il numero di risultati deve essere tra 1 e 100.'
    if cartella:
        base = _risolvi_cartella(cartella)
        if base is None:
            return f"Cartella '{cartella}' non valida."
        cartelle_da_cercare = [base]
    else:
        nomi_standard = ["scrivania", "documenti", "download", "immagini", "video", "musica"]
        viste = set()
        cartelle_da_cercare = []
        for nome in nomi_standard:
            percorso = config.CARTELLE_UTENTE[nome]
            if percorso.exists() and percorso not in viste:
                cartelle_da_cercare.append(percorso)
                viste.add(percorso)

    pattern_norm = pattern.lower()
    estensione_norm = ("." + estensione.lower().lstrip(".")) if estensione else None
    trovati = []

    for base in cartelle_da_cercare:
        try:
            for elemento in base.rglob("*"):
                if not elemento.is_file():
                    continue
                if elemento.is_symlink() or any(p.startswith('.') for p in elemento.relative_to(base).parts):
                    continue
                if pattern_norm not in elemento.name.lower():
                    continue
                if estensione_norm and not elemento.name.lower().endswith(estensione_norm):
                    continue
                trovati.append(elemento)
                if len(trovati) >= max_risultati:
                    break
        except PermissionError:
            continue  # saltiamo cartelle senza permesso, non blocchiamo tutta la ricerca
        if len(trovati) >= max_risultati:
            break

    if not trovati:
        return f"Nessun file trovato per '{pattern}'."

    elenco = "\n".join(str(f) for f in trovati)
    return f"Trovati {len(trovati)} file (mostro fino a {max_risultati}):\n{elenco}"


SCHEMA_CERCA_FILE = {
    "type": "function",
    "function": {
        "name": "cerca_file",
        "description": (
            "Cerca un file per nome (anche parziale). Se non sai in quale cartella si "
            "trova, NON specificare 'cartella': cerca automaticamente in tutte le "
            "cartelle standard insieme (scrivania, documenti, download, immagini, "
            "video, musica). Usa questa invece di elenca_file quando non conosci la "
            "posizione esatta."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Parte del nome del file da cercare"},
                "cartella": {"type": "string", "description": "Opzionale: limita la ricerca a una sola cartella"},
                "estensione": {"type": "string", "description": "Opzionale: filtra per estensione, es. 'pdf'"},
            },
            "required": ["pattern"],
        },
    },
}


# ---------------------------------------------------------------------------
# SCREENSHOT: backend disponibile, senza dipendenza obbligatoria da KDE.
# Su Wayland utilizza Spectacle (KDE), grim (wlroots) o GNOME Screenshot;
# su X11 usa Spectacle, GNOME Screenshot o scrot. Non esegue comandi shell.
# Su altri desktop Wayland senza questi strumenti occorrera' il portale XDG.
# ---------------------------------------------------------------------------
def _comandi_screenshot(percorso: Path, destinazione='tutti', schermo=None):
    """Generator of (backend, argv) respecting the display protocol."""
    wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
    if wayland:
        opzioni = [
            ("spectacle", ["spectacle", "-b", "-n", "-f", "-o", str(percorso)]),
            ("grim", ["grim", str(percorso)]),
            ("gnome-screenshot", ["gnome-screenshot", "-f", str(percorso)]),
        ]
    else:
        opzioni = [
            ("spectacle", ["spectacle", "-b", "-n", "-f", "-o", str(percorso)]),
            ("gnome-screenshot", ["gnome-screenshot", "-f", str(percorso)]),
            ("scrot", ["scrot", str(percorso)]),
        ]
    if destinazione == 'finestra':
        opzioni = [
            ('spectacle', ['spectacle', '-b', '-n', '-a', '-o', str(percorso)]),
            ('gnome-screenshot', ['gnome-screenshot', '-w', '-f', str(percorso)]),
        ]
        if not wayland:
            opzioni.append(('scrot', ['scrot', '-u', str(percorso)]))
    elif wayland and schermo is not None:
        opzioni = [(nome, ['grim', '-o', schermo['name'], str(percorso)] if nome == 'grim' else comando)
                   for nome, comando in opzioni]
    return [(nome, comando) for nome, comando in opzioni if shutil.which(nome)]


def fai_screenshot(nome_file: str = None, cartella: str = "immagini",
                   destinazione: str = 'principale', monitor: int = None) -> str:
    """Cattura principale, indice rilevato, desktop completo o finestra attiva."""
    from .screen_capture import detect_monitors, select_monitor, crop_monitor
    try:
        monitors = detect_monitors() if destinazione in ('principale', 'monitor') else []
        selected = select_monitor(monitors, destinazione, monitor)
    except ValueError as exc:
        return str(exc)
    cartella_scelta = _risolvi_cartella(cartella)
    if cartella_scelta is None:
        return f"Cartella '{cartella}' non valida."

    if not nome_file:
        nome_file = datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
    # Evita percorsi e nomi che puntano fuori dalla cartella richiesta.
    if _nome_file_valido(nome_file) is None:
        return "Nome del file screenshot non valido."
    if not nome_file.lower().endswith(".png"):
        nome_file += ".png"
    percorso = cartella_scelta / nome_file
    try:
        cartella_scelta.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        return "Non ho i permessi per scrivere nella cartella richiesta."
    if percorso.exists():
        return f"Esiste gia' uno screenshot con nome '{nome_file}'. Scegli un altro nome."

    # I backend scrivono in uno spazio privato; la pubblicazione usa creazione
    # esclusiva e non può sovrascrivere il file scelto dall'utente.
    with tempfile.TemporaryDirectory(prefix='ia-screenshot-') as temporary:
        cattura = Path(temporary) / 'capture.png'
        return _cattura_screenshot(cattura, percorso, destinazione, selected, monitors, crop_monitor)


def _cattura_screenshot(cattura, percorso, destinazione, selected, monitors, crop_monitor):
    disponibili = _comandi_screenshot(cattura, destinazione, selected)
    if not disponibili:
        sessione = "Wayland" if os.environ.get("WAYLAND_DISPLAY") else "X11"
        return (f"Nessun programma screenshot disponibile per {sessione}. "
                "Installa un backend compatibile: spectacle, grim (wlroots), "
                "gnome-screenshot oppure scrot (X11).")

    errori = []
    for backend, comando in disponibili:
        try:
            esito = subprocess.run(comando, capture_output=True, text=True, timeout=15)
            if esito.returncode == 0 and cattura.is_file() and cattura.stat().st_size > 0:
                if selected is not None and backend != 'grim':
                    if len(monitors) > 1:
                        crop_monitor(cattura, monitors, selected)
                with cattura.open('rb') as source, percorso.open('xb') as output:
                    os.fchmod(output.fileno(), 0o600)
                    shutil.copyfileobj(source, output)
                return f"Screenshot salvato in {percorso} (tramite {backend})."
            errori.append(f"{backend}: {(esito.stderr or esito.stdout or 'nessuna immagine prodotta').strip()[:180]}")
        except FileExistsError:
            return 'La destinazione esiste già: nessuno screenshot sovrascritto.'
        except (OSError, ValueError, ImportError, subprocess.TimeoutExpired) as e:
            errori.append(f"{backend}: {e}")
        # Pulisci eventuali file incompleti prima di tentare con un altro backend.
        try:
            if cattura.is_file():
                cattura.unlink()
        except OSError:
            return f"Screenshot non riuscito; file parziale in {percorso}."
    return "Screenshot non riuscito. " + "; ".join(errori)


SCHEMA_FAI_SCREENSHOT = {
    "type": "function",
    "function": {
        "name": "fai_screenshot",
        "description": "Screenshot: senza indicazioni usa il monitor principale; monitor N usa indice da 1; tutti cattura il desktop completo; finestra cattura la finestra attiva se supportata.",
        "parameters": {
            "type": "object",
            "properties": {
                "nome_file": {"type": ["string", "null"], "description": "Nome del file opzionale; ometti o usa null per generarlo con data e ora."},
                "destinazione": {"type": "string", "enum": ["principale", "monitor", "tutti", "finestra"]},
                "monitor": {"type": "integer", "description": "Indice da 1, solo con destinazione monitor"},
                "cartella": {"type": "string", "description": "Dove salvarlo: scrivania, documenti, download, immagini, video, musica, oppure 'home' (default: immagini)"},
            },
        },
    },
}


# ---------------------------------------------------------------------------
# REGISTRAZIONE SCHERMO (GPU Screen Recorder)
#
# Per impostazione predefinita GSR registra il primo monitor rilevato
# (-w screen). Su sistemi multi-monitor scegliere con IA_GSR_TARGET
# un monitor elencato da gpu-screen-recorder --list-monitors.
#
# Teniamo il processo in una variabile del modulo per poterlo fermare dopo:
# 'ferma_registrazione_schermo' manda un segnale a QUESTO stesso processo,
# non ne cerca uno a caso in giro per il sistema.
# ---------------------------------------------------------------------------
_processo_registrazione = None
_processo_buffer_replay = None
_percorso_registrazione = None
_registrazione_obs = None
_replay_obs = None
_lock_catture = threading.RLock()


def _serializza_cattura(funzione):
    from functools import wraps
    @wraps(funzione)
    def esegui(*args, **kwargs):
        with _lock_catture:
            return funzione(*args, **kwargs)
    return esegui


def _backend_video(backend):
    if backend not in ('auto', 'gsr', 'obs'):
        raise ValueError('Programma video non valido: usa auto, gsr oppure obs.')
    # Se GSR manca proviamo OBS anche se il suo eseguibile non è nel PATH
    # (per esempio OBS Flatpak già aperto e raggiungibile via WebSocket).
    return ('gsr' if shutil.which('gpu-screen-recorder') else 'obs') if backend == 'auto' else backend


def _avvia_obs(replay=False):
    global _registrazione_obs, _replay_obs
    session = obs_control.ObsSession()
    try:
        status = 'GetReplayBufferStatus' if replay else 'GetRecordStatus'
        if session.call(status)['outputActive']:
            session.close()
            return 'OBS ha già una cattura attiva: gestiscila da OBS prima di avviarne un’altra.'
    except Exception:
        session.close()
        raise
    # Conserva il collegamento anche se la risposta di avvio si perde:
    # l’arresto successivo può verificare e chiudere la cattura in OBS.
    if replay:
        _replay_obs = session
    else:
        _registrazione_obs = session
    session.call('StartReplayBuffer' if replay else 'StartRecord')
    if replay:
        return "Buffer replay attivo con OBS; durata e cartella sono quelle configurate in OBS."
    return "Registrazione avviata con OBS; usa scena, audio e cartella configurati in OBS."


def _ferma_obs(replay=False):
    global _registrazione_obs, _replay_obs
    session = _replay_obs if replay else _registrazione_obs
    try:
        status = 'GetReplayBufferStatus' if replay else 'GetRecordStatus'
        result = {}
        if session.call(status)['outputActive']:
            result = session.call('StopReplayBuffer' if replay else 'StopRecord')
    except obs_control.ObsError as exc:
        return str(exc)  # conserva il collegamento per un nuovo tentativo
    session.close()
    if replay:
        _replay_obs = None
        return 'Buffer replay OBS fermato.'
    _registrazione_obs = None
    path = result.get('outputPath')
    return f'Registrazione OBS salvata: {path}' if path else 'La registrazione OBS non è più attiva.'


def _avvia_processo_gsr(argomenti_extra: list, verifica_secondi: float = 0.6):
    """
    Avvia gpu-screen-recorder con gli argomenti extra dati (oltre a monitor/
    framerate/audio, sempre uguali), e VERIFICA che sia rimasto vivo dopo
    un istante: se gli argomenti sono sbagliati, GSR può chiudersi subito
    da solo, e senza questo controllo diremmo "avviato" anche se in realtà
    non ha fatto nulla (è successo davvero col buffer replay).

    Ritorna (processo, None) se tutto ok, oppure (None, messaggio_errore)
    con l'errore VERO stampato da gpu-screen-recorder, non un messaggio
    generico — utile per capire quale flag correggere se qualcosa non va.
    """
    comando = [
        "gpu-screen-recorder", "-w", config.GSR_TARGET,
        "-f", str(config.GSR_FRAMERATE), "-a", config.GSR_AUDIO,
        # La CLI non eredita le preferenze della GUI GSR. Evita Opus in
        # MP4: H.264 + AAC e colore 4:2:0 favoriscono la condivisione.
        "-k", "h264", "-ac", "aac", "-pixfmt", "yuv420", "-cr", "limited",
    ] + argomenti_extra

    # L'output va su un FILE temporaneo, non su una pipe: nessuno legge una
    # pipe mentre registra, e quando si riempie (64 KB) il programma si
    # blocca. Un file non si riempie mai in modo problematico.
    import tempfile
    log = tempfile.NamedTemporaryFile(mode="w+", prefix="gsr-", suffix=".log", delete=False)
    try:
        processo = subprocess.Popen(comando, stdout=log, stderr=log, text=True)
    except FileNotFoundError:
        log.close()
        Path(log.name).unlink(missing_ok=True)
        return None, "gpu-screen-recorder non è installato."
    except Exception as e:
        log.close()
        Path(log.name).unlink(missing_ok=True)
        return None, f"Errore nell'avvio di gpu-screen-recorder: {e}"
    log.close()

    time.sleep(verifica_secondi)
    codice_uscita = processo.poll()

    if codice_uscita is not None:
        # Si è già chiuso da solo: qualcosa negli argomenti non va bene.
        try:
            errore = Path(log.name).read_text(errors="ignore").strip()[-400:]
        except Exception:
            errore = ""
        dettaglio = errore if errore else f"nessun messaggio d'errore (codice di uscita {codice_uscita})"
        Path(log.name).unlink(missing_ok=True)
        return None, f"gpu-screen-recorder si è chiuso subito dopo l'avvio: {dettaglio}"

    Path(log.name).unlink(missing_ok=True)  # il figlio mantiene aperto il descrittore
    return processo, None


@_serializza_cattura
def avvia_registrazione_schermo(nome_file: str = None, backend: str = 'auto') -> str:
    """Avvia la registrazione dello schermo (video + audio di sistema)."""
    global _processo_registrazione, _percorso_registrazione

    if _registrazione_obs is not None or (_processo_registrazione and _processo_registrazione.poll() is None):
        return "C'è già una registrazione in corso. Fermala prima di avviarne un'altra."

    if nome_file is not None and _nome_file_valido(nome_file) is None:
        return 'Nome del video non valido.'
    try:
        if _backend_video(backend) == 'obs':
            if nome_file:
                return 'Con OBS il nome del file viene deciso dalle impostazioni OBS. Ometti nome_file.'
            return _avvia_obs()
    except (ValueError, obs_control.ObsError) as exc:
        return str(exc)

    cartella = _risolvi_cartella(config.GSR_CARTELLA_OUTPUT)
    if cartella is None:
        return "Cartella di output per la registrazione non valida."
    if not nome_file:
        nome_file = datetime.now().strftime("registrazione_%Y%m%d_%H%M%S.mp4")
    nome_file = _nome_file_valido(nome_file)
    if nome_file is None:
        return "Nome del video non valido."
    if not nome_file.lower().endswith(".mp4"):
        nome_file += ".mp4"
    percorso = cartella / nome_file
    if percorso.exists() or percorso.is_symlink() or not _percorso_sicuro(cartella, percorso):
        return "Destinazione video già esistente o non consentita."
    try:
        cartella.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return f'Impossibile preparare la cartella video: {exc}'

    processo, errore = _avvia_processo_gsr(["-o", str(percorso)])
    if errore:
        return errore

    _processo_registrazione = processo
    _percorso_registrazione = percorso
    return f"Registrazione avviata, salverà in {percorso}."


SCHEMA_AVVIA_REGISTRAZIONE = {
    "type": "function",
    "function": {
        "name": "avvia_registrazione_schermo",
        "description": "Avvia la registrazione dello schermo intero (video + audio di sistema).",
        "parameters": {
            "type": "object",
            "properties": {"nome_file": {"type": ["string", "null"], "description": "Nome del file opzionale; ometti o usa null per generarlo con data e ora."}},
        },
    },
}


@_serializza_cattura
def ferma_registrazione_schermo() -> str:
    """Ferma la registrazione in corso e salva il file."""
    global _processo_registrazione, _percorso_registrazione

    if _registrazione_obs is not None:
        return _ferma_obs()

    if not _processo_registrazione or _processo_registrazione.poll() is not None:
        return "Non c'è nessuna registrazione in corso."

    _processo_registrazione.send_signal(signal.SIGINT)
    try:
        _processo_registrazione.wait(timeout=10)
    except subprocess.TimeoutExpired:
        return "Registrazione ancora in chiusura: riprova a fermarla tra poco."
    _processo_registrazione = None
    percorso = _percorso_registrazione
    if percorso and percorso.exists() and percorso.stat().st_size > 0:
        mb = percorso.stat().st_size / (1024 * 1024)
        return f"Registrazione salvata: {percorso.name} ({mb:.1f} MB)."
    return ("Ho fermato la registrazione, ma il file non risulta creato. "
            "Controlla IA_GSR_TARGET e GSR_AUDIO in config.py.")


SCHEMA_FERMA_REGISTRAZIONE = {
    "type": "function",
    "function": {
        "name": "ferma_registrazione_schermo",
        "description": "Ferma la registrazione dello schermo attualmente in corso.",
        "parameters": {"type": "object", "properties": {}},
    },
}


@_serializza_cattura
def registra_schermo_per(secondi, backend: str = 'auto') -> str:
    """Registra lo schermo per un numero preciso di secondi e si ferma da sola
    (es. "fai un video di 10 secondi"). Avvisa con una notifica a fine lavoro."""
    try:
        durata = float(secondi)
    except (TypeError, ValueError):
        return "Durata non valida: indica un numero di secondi."
    if not 1 <= durata <= 600:
        return "La durata deve essere tra 1 e 600 secondi."

    esito = avvia_registrazione_schermo(backend=backend)
    if not esito.startswith("Registrazione avviata"):
        return esito
    processo = _registrazione_obs if _registrazione_obs is not None else _processo_registrazione

    @_serializza_cattura
    def ferma_da_sola():
        # Fermiamo solo QUESTA registrazione, non una eventualmente avviata dopo.
        corrente = _registrazione_obs if _registrazione_obs is not None else _processo_registrazione
        if corrente is processo:
            invia_notifica("🎬 Registrazione", ferma_registrazione_schermo())

    timer = threading.Timer(durata, ferma_da_sola)
    timer.daemon = True
    timer.start()
    return f"Registro lo schermo per {durata:g} secondi, poi mi fermo da solo e ti avviso."


SCHEMA_REGISTRA_PER = {
    "type": "function",
    "function": {
        "name": "registra_schermo_per",
        "description": (
            "Registra lo schermo per un numero preciso di secondi e poi si ferma da "
            "sola. Usala per richieste come 'fai un video di 10 secondi'."
        ),
        "parameters": {
            "type": "object",
            "properties": {"secondi": {"type": "number", "description": "Durata in secondi (1-600)"}},
            "required": ["secondi"],
        },
    },
}


@_serializza_cattura
def avvia_buffer_replay(secondi: int = None, backend: str = 'auto') -> str:
    """Avvia il buffer replay: tiene sempre pronti in memoria gli ultimi N
    secondi, pronti da salvare a comando (utile per catturare a posteriori
    un momento di gioco senza registrare in continuo)."""
    global _processo_buffer_replay

    if _replay_obs is not None or (_processo_buffer_replay and _processo_buffer_replay.poll() is None):
        return "Il buffer replay è già attivo."

    if secondi is not None and (type(secondi) is not int or not 1 <= secondi <= 600):
        return 'Il buffer deve durare da 1 a 600 secondi.'
    try:
        if _backend_video(backend) == 'obs':
            if secondi is not None:
                return 'Con OBS imposta la durata del buffer nelle impostazioni OBS, poi chiedi di avviare il replay senza durata.'
            return _avvia_obs(replay=True)
    except (ValueError, obs_control.ObsError) as exc:
        return str(exc)
    if secondi is None:
        secondi = 30

    cartella = _risolvi_cartella(config.GSR_CARTELLA_OUTPUT)
    if cartella is None:
        return "Cartella di output non valida."
    cartella.mkdir(parents=True, exist_ok=True)

    if type(secondi) is not int or not 1 <= secondi <= 600:
        return 'Il buffer deve durare da 1 a 600 secondi.'

    # -c mp4 è obbligatorio insieme a -r: in modalità buffer replay -o punta
    # a una CARTELLA (non a un file con estensione), quindi gpu-screen-recorder
    # non può indovinare da solo il formato del contenitore video, va detto esplicitamente.
    processo, errore = _avvia_processo_gsr(["-r", str(secondi), "-c", "mp4", "-o", str(cartella)])
    if errore:
        return errore

    _processo_buffer_replay = processo
    return f"Buffer replay attivo (ultimi {secondi} secondi). Di' 'salva il replay' per catturarlo."


SCHEMA_AVVIA_BUFFER_REPLAY = {
    "type": "function",
    "function": {
        "name": "avvia_buffer_replay",
        "description": "Avvia il buffer replay in background: tiene pronti gli ultimi N secondi, salvabili a comando con salva_replay.",
        "parameters": {
            "type": "object",
            "properties": {"secondi": {"type": "integer", "description": "Quanti secondi tenere nel buffer (default 30)"}},
        },
    },
}


@_serializza_cattura
def salva_replay() -> str:
    """Salva su file gli ultimi secondi tenuti nel buffer replay."""
    if _replay_obs is not None:
        try:
            _replay_obs.call('SaveReplayBuffer')
            return 'Salvataggio replay richiesto a OBS nella cartella configurata in OBS.'
        except obs_control.ObsError as exc:
            return str(exc)

    if not _processo_buffer_replay or _processo_buffer_replay.poll() is not None:
        return "Il buffer replay non è attivo. Avvialo prima con avvia_buffer_replay."

    cartella = _risolvi_cartella(config.GSR_CARTELLA_OUTPUT)
    prima = time.time()
    precedenti = {f.name: (f.stat().st_mtime_ns, f.stat().st_size) for f in cartella.glob('*.mp4')}
    _processo_buffer_replay.send_signal(signal.SIGUSR1)

    # Non diciamo "salvato" finché non vediamo davvero un file nuovo.
    for _ in range(20):
        time.sleep(0.25)
        nuovi = [f for f in cartella.glob("*.mp4") if f.name not in precedenti
                 and f.stat().st_mtime >= prima and f.stat().st_size > 0
                 and f != _percorso_registrazione]
        if nuovi:
            ultimo = max(nuovi, key=lambda f: f.stat().st_mtime)
            dimensione = ultimo.stat().st_size
            time.sleep(0.25)
            if ultimo.stat().st_size == dimensione:
                return f"Replay salvato: {ultimo.name}"
    return (f"Ho mandato il comando di salvataggio ma non vedo nessun file nuovo in "
            f"{cartella}. Il buffer potrebbe non essere attivo da abbastanza tempo.")


SCHEMA_SALVA_REPLAY = {
    "type": "function",
    "function": {
        "name": "salva_replay",
        "description": "Salva su file gli ultimi secondi catturati dal buffer replay attivo.",
        "parameters": {"type": "object", "properties": {}},
    },
}


@_serializza_cattura
def ferma_buffer_replay() -> str:
    """Ferma il buffer replay (senza salvare nulla di ulteriore)."""
    global _processo_buffer_replay

    if _replay_obs is not None:
        return _ferma_obs(replay=True)

    if not _processo_buffer_replay or _processo_buffer_replay.poll() is not None:
        return "Il buffer replay non è attivo."

    _processo_buffer_replay.send_signal(signal.SIGINT)
    try:
        _processo_buffer_replay.wait(timeout=10)
    except subprocess.TimeoutExpired:
        return 'Buffer ancora in chiusura: riprova a fermarlo tra poco.'
    _processo_buffer_replay = None
    return "Buffer replay fermato."


@_serializza_cattura
def arresta_catture():
    """Termina soltanto i processi GSR avviati da questa istanza."""
    global _processo_registrazione, _processo_buffer_replay
    if _registrazione_obs is not None:
        _ferma_obs()
    if _replay_obs is not None:
        _ferma_obs(replay=True)
    for processo in (_processo_registrazione, _processo_buffer_replay):
        if processo is not None and processo.poll() is None:
            try:
                processo.send_signal(signal.SIGINT)
                processo.wait(timeout=10)
            except subprocess.TimeoutExpired:
                processo.terminate()
                try:
                    processo.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    processo.kill()
                    processo.wait(timeout=2)
            except ProcessLookupError:
                pass
    _processo_registrazione = _processo_buffer_replay = None


SCHEMA_FERMA_BUFFER_REPLAY = {
    "type": "function",
    "function": {
        "name": "ferma_buffer_replay",
        "description": "Ferma il buffer replay attivo.",
        "parameters": {"type": "object", "properties": {}},
    },
}


# ---------------------------------------------------------------------------
# VOLUME A UN VALORE PRECISO (oltre ad alza/abbassa relativi)
# ---------------------------------------------------------------------------
def imposta_volume(percentuale) -> str:
    """Imposta il volume a un valore esatto (0-100), invece di alzarlo/abbassarlo relativamente."""
    try:
        percentuale = int(round(float(percentuale)))
    except (TypeError, ValueError, OverflowError):
        return "Percentuale non valida, indicane una tra 0 e 100."

    percentuale = max(0, min(100, percentuale))

    try:
        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percentuale}%"],
            check=True, capture_output=True,
            timeout=5,
        )
        return f"Volume impostato al {percentuale}%."
    except FileNotFoundError:
        return "pactl non trovato: verifica di avere PulseAudio/PipeWire attivo."
    except PermissionError:
        return _permesso_negato()
    except Exception as e:
        return f"Errore impostazione volume: {e}"


SCHEMA_IMPOSTA_VOLUME = {
    "type": "function",
    "function": {
        "name": "imposta_volume",
        "description": (
            "Imposta il volume a una percentuale ESATTA (0-100), es. 'metti il volume "
            "al 30%' o 'abbassa il volume AL 20%'. "
            "Per 'alza/abbassa il volume DEL N%' usa regolazione_volume "
            "passando la percentuale N."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "percentuale": {"type": "number", "description": "Valore da 0 a 100"}
            },
            "required": ["percentuale"],
        },
    },
}


# ---------------------------------------------------------------------------
# NOTIFICHE DI SISTEMA (con notify-send, standard su KDE/GNOME)
# ---------------------------------------------------------------------------
def invia_notifica(titolo: str, messaggio: str = "") -> str:
    """Mostra una notifica di sistema (popup), come quelle di qualunque app."""
    try:
        comando = ["notify-send", titolo]
        if messaggio:
            comando.append(messaggio)
        subprocess.run(comando, check=True, capture_output=True, timeout=5)
        return "Notifica inviata."
    except FileNotFoundError:
        return "notify-send non è installato (di norma già presente su KDE/GNOME)."
    except Exception as e:
        return f"Errore invio notifica: {e}"


SCHEMA_INVIA_NOTIFICA = {
    "type": "function",
    "function": {
        "name": "invia_notifica",
        "description": "Mostra una notifica di sistema (popup) con un titolo e un messaggio opzionale.",
        "parameters": {
            "type": "object",
            "properties": {
                "titolo": {"type": "string", "description": "Titolo della notifica"},
                "messaggio": {"type": "string", "description": "Testo della notifica (opzionale)"},
            },
            "required": ["titolo"],
        },
    },
}


# ---------------------------------------------------------------------------
# APPUNTI / CLIPBOARD (wl-copy/wl-paste: versione Wayland, non xclip/xsel
# che sono per X11 e non funzionano sul tuo sistema con Wayland)
# ---------------------------------------------------------------------------
def copia_negli_appunti(testo: str) -> str:
    """Copia del testo negli appunti di sistema."""
    try:
        comando = ['wl-copy'] if os.environ.get('WAYLAND_DISPLAY') else ['xclip', '-selection', 'clipboard']
        subprocess.run(comando, input=testo.encode('utf-8'), check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=5)
        return "Testo copiato negli appunti."
    except FileNotFoundError:
        return "Backend appunti assente: serve wl-clipboard su Wayland oppure xclip su X11."
    except Exception as e:
        return f"Errore copia appunti: {e}"


SCHEMA_COPIA_NEGLI_APPUNTI = {
    "type": "function",
    "function": {
        "name": "copia_negli_appunti",
        "description": "Copia del testo negli appunti di sistema (clipboard), pronto per essere incollato altrove.",
        "parameters": {
            "type": "object",
            "properties": {"testo": {"type": "string", "description": "Testo da copiare"}},
            "required": ["testo"],
        },
    },
}


def leggi_appunti() -> str:
    """Legge il contenuto attuale degli appunti di sistema."""
    try:
        comando = ['wl-paste', '--no-newline'] if os.environ.get('WAYLAND_DISPLAY') else ['xclip', '-selection', 'clipboard', '-o']
        risultato = subprocess.run(comando, capture_output=True, text=True, timeout=5, check=True)
        testo = risultato.stdout.strip()
        return testo if testo else "Gli appunti sono vuoti."
    except FileNotFoundError:
        return "Backend appunti assente: serve wl-clipboard su Wayland oppure xclip su X11."
    except Exception as e:
        return f"Errore lettura appunti: {e}"


SCHEMA_LEGGI_APPUNTI = {
    "type": "function",
    "function": {
        "name": "leggi_appunti",
        "description": "Legge il contenuto attuale degli appunti di sistema (quello che hai copiato di recente).",
        "parameters": {"type": "object", "properties": {}},
    },
}


# ---------------------------------------------------------------------------
# PROMEMORIA / TIMER
#
# Gira su un thread separato (threading.Timer): il resto dell'assistente
# continua a funzionare normalmente nel frattempo, non resta "bloccato" ad
# aspettare. Nota: se chiudi il programma prima che scatti, il promemoria
# NON parte (non c'è persistenza tra un avvio e l'altro).
# ---------------------------------------------------------------------------
def imposta_promemoria(minuti, messaggio: str) -> str:
    """Imposta un promemoria che notifica dopo N minuti (funziona anche se
    nel frattempo usi l'assistente per altro)."""
    try:
        minuti_float = float(minuti)
        secondi = minuti_float * 60
    except (TypeError, ValueError):
        return "Numero di minuti non valido."

    if not math.isfinite(secondi) or not 0 < secondi <= 31536000:
        return "La durata deve essere finita, maggiore di zero e non oltre un anno."

    def scatta():
        invia_notifica("⏰ Promemoria", messaggio)

    timer = threading.Timer(secondi, scatta)
    timer.daemon = True  # non deve impedire la chiusura del programma
    timer.start()

    return f"Promemoria impostato: tra {minuti_float:g} minuti ti ricorderò '{messaggio}'."


SCHEMA_IMPOSTA_PROMEMORIA = {
    "type": "function",
    "function": {
        "name": "imposta_promemoria",
        "description": (
            "Imposta un promemoria che scatta dopo un certo numero di minuti, "
            "mostrando una notifica di sistema. Il promemoria funziona solo se "
            "l'assistente resta aperto fino a quel momento."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "minuti": {"type": "number", "description": "Tra quanti minuti avvisare"},
                "messaggio": {"type": "string", "description": "Cosa ricordare"},
            },
            "required": ["minuti", "messaggio"],
        },
    },
}


# ---------------------------------------------------------------------------
# ELIMINA FILE
# ---------------------------------------------------------------------------
def elimina_file(nome_file: str, cartella: str = "documenti") -> str:
    """
    Elimina un file. Per sicurezza funziona SOLO dentro le cartelle mappate
    in config.py (scrivania/documenti/download, anche sottocartelle): non può
    cancellare file fuori da lì, anche se qualcuno prova a passare un percorso strano.
    """
    cartella_scelta = _risolvi_cartella(cartella)
    if cartella_scelta is None:
        return f"Cartella '{cartella}' non valida. Usa scrivania, documenti, download, immagini, video, musica, oppure 'home' per l'intera cartella personale."

    nome = _nome_file_valido(nome_file)
    if nome is None:
        return 'Nome file non valido.'
    percorso = cartella_scelta / nome
    if percorso.is_symlink():
        return 'Non elimino collegamenti simbolici tramite questa funzione.'

    # Controllo di sicurezza: il file risolto deve stare DAVVERO dentro
    # la cartella scelta, non essere "scappato" fuori con un ../../
    if not _percorso_sicuro(cartella_scelta, percorso):
        return "Per sicurezza posso eliminare solo file dentro le cartelle conosciute."

    if not percorso.exists():
        return f"Il file '{nome_file}' non esiste in {cartella_scelta}."

    try:
        percorso.unlink()
        return f"File '{nome_file}' eliminato da {cartella_scelta}."
    except PermissionError:
        return _permesso_negato()
    except Exception as e:
        return f"Errore durante l'eliminazione del file: {e}"


SCHEMA_ELIMINA_FILE = {
    "type": "function",
    "function": {
        "name": "elimina_file",
        "description": "Elimina un file esistente in scrivania, documenti, download, immagini, video, musica, oppure 'home' per l'intera cartella personale.",
        "parameters": {
            "type": "object",
            "properties": {
                "nome_file": {"type": "string", "description": "Nome del file da eliminare"},
                "cartella": {"type": "string", "description": "Cartella dove si trova: scrivania, documenti, download, immagini, video, musica, oppure 'home' per l'intera cartella personale (anche con sottocartelle, es. 'scrivania/nome_sottocartella')"},
            },
            "required": ["nome_file"],
        },
    },
}


# ---------------------------------------------------------------------------
# Piccola funzione di appoggio, usata da copia/sposta/rinomina: controlla che
# un percorso stia DAVVERO dentro la cartella prevista, senza scappatoie
# tipo "../../" (lo stesso controllo già usato in elimina_file).
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# COPIA FILE
# ---------------------------------------------------------------------------
def _trasferisci_file(nome_file, cartella_origine, cartella_destinazione, nuovo_nome=None,
                     rimuovi_origine=False):
    """Copia esclusiva: una collisione non sostituisce mai dati esistenti."""
    origine_base = _risolvi_cartella(cartella_origine)
    destinazione_base = _risolvi_cartella(cartella_destinazione)
    nome = _nome_file_valido(nome_file)
    finale = _nome_file_valido(nuovo_nome if nuovo_nome is not None else nome_file)
    if origine_base is None or destinazione_base is None or nome is None or finale is None:
        return "Cartella o nome file non valido."
    origine, destinazione = origine_base / nome, destinazione_base / finale
    if (origine.is_symlink() or destinazione.is_symlink()
            or not _percorso_sicuro(origine_base, origine)
            or not _percorso_sicuro(destinazione_base, destinazione)):
        return "Percorso non consentito."
    creato = False
    try:
        fd = os.open(origine, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as ingresso:
            info = os.fstat(ingresso.fileno())
            if not stat.S_ISREG(info.st_mode):
                return "L'origine non è un file regolare."
            destinazione_base.mkdir(parents=True, exist_ok=True)
            with destinazione.open('xb') as uscita:
                creato = True
                shutil.copyfileobj(ingresso, uscita)
                os.fchmod(uscita.fileno(), stat.S_IMODE(info.st_mode) & 0o777)
                uscita.flush()
                os.utime(uscita.fileno(), ns=(info.st_atime_ns, info.st_mtime_ns))
                os.fsync(uscita.fileno())
        if rimuovi_origine:
            attuale = origine.stat(follow_symlinks=False)
            if ((attuale.st_dev, attuale.st_ino, attuale.st_size, attuale.st_mtime_ns)
                    != (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)):
                return "Copia creata, ma l'origine è cambiata: non è stata rimossa."
            origine.unlink()
        verbo = 'spostato' if rimuovi_origine else 'copiato'
        return f"File {verbo}: '{nome}' in {destinazione_base} come '{finale}'."
    except FileExistsError:
        return "La destinazione esiste già: non sovrascrivo alcun file."
    except OSError as exc:
        # Una copia parziale viene conservata: non rischiamo di cancellare
        # un file che un altro processo potrebbe avere sostituito.
        dettaglio = " La copia può essere parziale; l'origine è conservata." if creato else ""
        return f"Trasferimento non completato: {exc}.{dettaglio}"


def copia_file(nome_file: str, cartella_origine: str = "documenti",
                cartella_destinazione: str = "documenti", nuovo_nome: str = None) -> str:
    """Copia un file da una cartella mappata a un'altra (può anche restare
    nella stessa cartella, utile per fare un duplicato)."""
    return _trasferisci_file(nome_file, cartella_origine, cartella_destinazione, nuovo_nome)


SCHEMA_COPIA_FILE = {
    "type": "function",
    "function": {
        "name": "copia_file",
        "description": "Copia un file da una cartella a un'altra (scrivania, documenti, download), eventualmente rinominandolo.",
        "parameters": {
            "type": "object",
            "properties": {
                "nome_file": {"type": "string", "description": "Nome del file da copiare"},
                "cartella_origine": {"type": "string", "description": "Cartella dove si trova ora: scrivania, documenti, download, immagini, video, musica, oppure 'home' per l'intera cartella personale (anche con sottocartelle)"},
                "cartella_destinazione": {"type": "string", "description": "Cartella dove copiarlo: scrivania, documenti, download, immagini, video, musica, oppure 'home' per l'intera cartella personale (anche con sottocartelle)"},
                "nuovo_nome": {"type": "string", "description": "Nuovo nome per la copia (opzionale)"},
            },
            "required": ["nome_file"],
        },
    },
}


# ---------------------------------------------------------------------------
# SPOSTA FILE
# ---------------------------------------------------------------------------
def sposta_file(nome_file: str, cartella_origine: str = "documenti",
                 cartella_destinazione: str = "documenti") -> str:
    """Sposta (non copia) un file da una cartella mappata a un'altra."""
    return _trasferisci_file(nome_file, cartella_origine, cartella_destinazione,
                            rimuovi_origine=True)


SCHEMA_SPOSTA_FILE = {
    "type": "function",
    "function": {
        "name": "sposta_file",
        "description": "Sposta un file da una cartella a un'altra (scrivania, documenti, download).",
        "parameters": {
            "type": "object",
            "properties": {
                "nome_file": {"type": "string", "description": "Nome del file da spostare"},
                "cartella_origine": {"type": "string", "description": "Cartella dove si trova ora: scrivania, documenti, download, immagini, video, musica, oppure 'home' per l'intera cartella personale (anche con sottocartelle)"},
                "cartella_destinazione": {"type": "string", "description": "Cartella di destinazione: scrivania, documenti, download, immagini, video, musica, oppure 'home' per l'intera cartella personale (anche con sottocartelle)"},
            },
            "required": ["nome_file"],
        },
    },
}


# ---------------------------------------------------------------------------
# RINOMINA FILE
# ---------------------------------------------------------------------------
def rinomina_file(nome_file: str, nuovo_nome: str, cartella: str = "documenti") -> str:
    """Rinomina un file, restando nella stessa cartella."""
    return _trasferisci_file(nome_file, cartella, cartella, nuovo_nome,
                            rimuovi_origine=True)


SCHEMA_RINOMINA_FILE = {
    "type": "function",
    "function": {
        "name": "rinomina_file",
        "description": "Rinomina un file esistente, senza cambiarlo di cartella.",
        "parameters": {
            "type": "object",
            "properties": {
                "nome_file": {"type": "string", "description": "Nome attuale del file"},
                "nuovo_nome": {"type": "string", "description": "Nuovo nome da dargli"},
                "cartella": {"type": "string", "description": "Cartella dove si trova: scrivania, documenti, download, immagini, video, musica, oppure 'home' per l'intera cartella personale (anche con sottocartelle, es. 'scrivania/nome_sottocartella')"},
            },
            "required": ["nome_file", "nuovo_nome"],
        },
    },
}


# ---------------------------------------------------------------------------
# APRI APPLICAZIONE
# ---------------------------------------------------------------------------
# Formato: {comando_vero_da_lanciare: [nomi/sinonimi con cui potresti chiamarlo]}
# comprensione.interpreta() tollera anche piccoli errori di battitura
# (es. "spotifi" viene comunque riconosciuto come "spotify").
MAPPA_APP = {
    "firefox": ["browser", "internet"],
    "konsole": ["terminale", "console", "terminal"],
    "dolphin": ["file", "cartella", "gestore file", "file manager", "esplora file"],
    "spotify": [],
    "discord": [],
    "steam": [],
    "qbittorrent": ["torrent", "cubi"],
    "code": ["vscode", "visual studio code", "editor di codice"],
    "gimp": ["editor immagini", "fotoritocco"],
    "libreoffice": ["office", "writer", "documento", "scrivi un documento"],
    "vlc": ["lettore video", "player video", "riproduttore"],
    "thunderbird": ["posta", "email", "client email", "client di posta"],
    "kate": ["editor di testo", "blocco note", "notepad"],
    "telegram": [],
}


def _risolvi_applicazione(nome_app: str) -> str:
    """Traduce quello che dici in un comando reale da lanciare. Se non
    trova nessuna corrispondenza (nemmeno simile), prova comunque a usare
    il nome esattamente come l'hai scritto: magari è un programma che
    conosci tu e che non è nella mappa, e potrebbe funzionare comunque."""
    riconosciuto = comprensione.interpreta(nome_app, MAPPA_APP, soglia=0.7)
    return riconosciuto if riconosciuto else nome_app.lower().strip()


# ---------------------------------------------------------------------------
# PIANO B: ricerca tra i file .desktop del sistema
#
# MAPPA_APP sopra copre solo le app che conosciamo in anticipo. Ma tantissime
# app (specialmente quelle installate con Flatpak, comuni su Nobara) non
# hanno un comando semplice tipo "nomeapp" nel PATH: serve qualcosa come
# "flatpak run com.esempio.NomeApp". Linux tiene già questa informazione,
# per QUALUNQUE app con un'icona nel menu, dentro un file .desktop.
# Invece di aggiungere eccezioni a mano una per una, cerchiamo lì.
# ---------------------------------------------------------------------------
def _cartelle_file_desktop():
    """Le cartelle standard dove Linux tiene i file .desktop: di sistema,
    e quelle specifiche di Flatpak/Snap (che coprono anche zapzap e simili)."""
    return [
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
        Path("/var/lib/flatpak/exports/share/applications"),
        Path("/var/lib/snapd/desktop/applications"),
        config.HOME / ".local/share/applications",
        config.HOME / ".local/share/flatpak/exports/share/applications",
    ]


def _leggi_file_desktop(percorso: Path):
    """Legge un file .desktop e ritorna (nome_app, comando_da_lanciare),
    oppure (None, None) se non è leggibile o non ha le righe che servono."""
    try:
        testo = percorso.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None, None

    nome = None
    riga_exec = None
    for riga in testo.splitlines():
        if riga.startswith("Name=") and nome is None:
            nome = riga[len("Name="):].strip()
        elif riga.startswith("Exec=") and riga_exec is None:
            riga_exec = riga[len("Exec="):].strip()
        if nome and riga_exec:
            break

    if not riga_exec:
        return nome, None

    # Le righe Exec contengono "codici" come %U %f %i che il sistema
    # sostituisce con file/URL passati all'app: per aprirla senza
    # argomenti, li togliamo semplicemente.
    comando_pulito = re.sub(r"%[a-zA-Z]", "", riga_exec).strip()
    return nome, comando_pulito


def _cerca_app_tra_i_desktop_file(nome_app: str):
    """Cerca tra tutte le app installate (via i loro file .desktop) quella
    il cui nome assomiglia di più a quello richiesto. Ritorna il comando
    reale da lanciare, o None se non trova nulla di abbastanza simile."""
    candidati = {}
    for cartella in _cartelle_file_desktop():
        if not cartella.exists():
            continue
        for file_desktop in cartella.glob("*.desktop"):
            nome, comando = _leggi_file_desktop(file_desktop)
            if nome and comando:
                candidati[nome] = comando

    if not candidati:
        return None

    trovato = comprensione.trova_piu_simile(nome_app, candidati.keys(), soglia=0.6)
    return candidati[trovato] if trovato else None


# ---------------------------------------------------------------------------
# GIOCHI STEAM (piano C, dopo eseguibile diretto e file .desktop)
#
# Steam tiene un file "appmanifest_<id>.acf" per ogni gioco installato,
# dentro le sue cartelle libreria (semplice testo chiave-valore). Lo
# leggiamo per costruire una mappa {nome_gioco: id}, e per avviarlo
# usiamo l'URL speciale steam://rungameid/<id>, che Steam stesso
# intercetta — riusiamo _apri_url, lo stesso meccanismo di YouTube.
# ---------------------------------------------------------------------------
def _cartelle_steam_base():
    """Le posizioni standard dove può stare l'installazione di Steam
    (nativa via dnf, o Flatpak)."""
    candidate = [
        config.HOME / ".local/share/Steam/steamapps",
        config.HOME / ".steam/steam/steamapps",
        config.HOME / ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps",
    ]
    return [c for c in candidate if c.exists()]


def _librerie_steam_aggiuntive(cartella_steamapps: Path):
    """Legge libraryfolders.vdf per trovare altre cartelle libreria Steam
    (es. un disco esterno aggiunto a mano)."""
    percorso_vdf = cartella_steamapps / "libraryfolders.vdf"
    trovate = []
    if not percorso_vdf.exists():
        return trovate
    try:
        testo = percorso_vdf.read_text(encoding="utf-8", errors="ignore")
        for corrispondenza in re.finditer(r'"path"\s*"([^"]+)"', testo):
            percorso = Path(corrispondenza.group(1)) / "steamapps"
            if percorso.exists():
                trovate.append(percorso)
    except Exception:
        pass
    return trovate


def _giochi_steam_installati() -> dict:
    """Ritorna {nome_gioco: appid} leggendo tutti i manifest Steam trovati."""
    cartelle = list(_cartelle_steam_base())
    for base in list(cartelle):
        cartelle.extend(_librerie_steam_aggiuntive(base))

    viste = set()
    cartelle_finali = []
    for c in cartelle:
        risolta = c.resolve()
        if risolta not in viste:
            viste.add(risolta)
            cartelle_finali.append(c)

    giochi = {}
    for cartella in cartelle_finali:
        for manifest in cartella.glob("appmanifest_*.acf"):
            try:
                testo = manifest.read_text(encoding="utf-8", errors="ignore")
                id_trovato = re.search(r'"appid"\s*"(\d+)"', testo)
                nome_trovato = re.search(r'"name"\s*"([^"]+)"', testo)
                if id_trovato and nome_trovato:
                    giochi[nome_trovato.group(1)] = id_trovato.group(1)
            except Exception:
                continue
    return giochi


def _cerca_gioco_steam(nome_gioco: str):
    """Cerca un gioco installato su Steam per nome (con tolleranza a piccole
    differenze). Ritorna l'appid, o None se non trova nulla."""
    giochi = _giochi_steam_installati()
    if not giochi:
        return None
    trovato = comprensione.trova_piu_simile(nome_gioco, giochi.keys(), soglia=0.6)
    return giochi[trovato] if trovato else None


def apri_applicazione(nome_app: str) -> str:
    """Apre un'applicazione grafica sul computer (o un gioco Steam)."""
    comando = _risolvi_applicazione(nome_app)
    if not isinstance(nome_app, str) or '/' in nome_app or '\\' in nome_app or '\x00' in nome_app:
        return 'Specifica il nome di una applicazione installata, senza percorsi.'

    try:
        subprocess.Popen([comando], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Ho aperto '{comando}'."
    except FileNotFoundError:
        # Piano B: il nome non è un eseguibile diretto nel PATH (tipico
        # delle app Flatpak/Snap): cerchiamo tra i file .desktop.
        comando_alternativo = _cerca_app_tra_i_desktop_file(nome_app)
        if comando_alternativo:
            try:
                subprocess.Popen(
                    shlex.split(comando_alternativo),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                return f"Ho aperto '{nome_app}'."
            except Exception as e:
                return f"Ho trovato l'app ma non sono riuscito ad aprirla: {e}"

        # Piano C: magari è un gioco installato su Steam.
        appid = _cerca_gioco_steam(nome_app)
        if appid:
            if _apri_url(f"steam://rungameid/{appid}"):
                return f"Ho avviato '{nome_app}' tramite Steam."
            return "Ho trovato il gioco su Steam ma non sono riuscito ad avviarlo."

        return f"Non ho trovato l'applicazione '{comando}' sul sistema."
    except PermissionError:
        return _permesso_negato()
    except Exception as e:
        return f"Errore durante l'apertura di {comando}: {e}"


SCHEMA_APRI_APPLICAZIONE = {
    "type": "function",
    "function": {
        "name": "apri_applicazione",
        "description": (
            "Apre un programma sul computer, es. firefox, spotify, dolphin, "
            "oppure un gioco installato su Steam."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nome_app": {"type": "string", "description": "Nome dell'applicazione o del gioco da aprire"}
            },
            "required": ["nome_app"],
        },
    },
}


# ---------------------------------------------------------------------------
# VERIFICA APP INSTALLATA (senza aprirla)
#
# Serve una funzione SEPARATA da apri_applicazione: una domanda tipo "ho
# zapzap installato?" non è una richiesta di aprire l'app, è una domanda
# informativa. Senza uno strumento dedicato, Groq usava l'unico che aveva
# (apri_applicazione), sbagliando intento — la app si apriva anche solo
# per "controllare" se esisteva.
# ---------------------------------------------------------------------------
def verifica_app_installata(nome_app: str) -> str:
    """Controlla se un'applicazione (o un gioco Steam) è installata, SENZA aprirla."""
    comando = _risolvi_applicazione(nome_app)

    if shutil.which(comando):
        return f"Sì, '{nome_app}' risulta installato (comando: {comando})."

    comando_desktop = _cerca_app_tra_i_desktop_file(nome_app)
    if comando_desktop:
        return f"Sì, '{nome_app}' risulta installato."

    appid = _cerca_gioco_steam(nome_app)
    if appid:
        return f"Sì, '{nome_app}' risulta installato su Steam."

    return f"Non risulta installata nessuna applicazione chiamata '{nome_app}'."


SCHEMA_VERIFICA_APP_INSTALLATA = {
    "type": "function",
    "function": {
        "name": "verifica_app_installata",
        "description": (
            "Controlla se un'applicazione è installata sul sistema, SENZA aprirla. "
            "Usa questa funzione per domande tipo 'ho X installato?' o 'esiste X sul "
            "mio pc?'. Usa invece apri_applicazione solo quando l'utente chiede "
            "esplicitamente di APRIRE/AVVIARE un programma."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nome_app": {"type": "string", "description": "Nome dell'applicazione da verificare"}
            },
            "required": ["nome_app"],
        },
    },
}


# ---------------------------------------------------------------------------
# CHIUDI APPLICAZIONE
# ---------------------------------------------------------------------------
def chiudi_applicazione(nome_app: str) -> str:
    """Chiude/termina un'applicazione in esecuzione."""
    comando = _risolvi_applicazione(nome_app)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}', comando):
        return "Nome processo non valido: specifica un'applicazione, senza opzioni o pattern."

    try:
        result = subprocess.run(["pkill", "-i", "-x", "--", re.escape(comando)],
                                capture_output=True, timeout=5)
        if result.returncode == 1:
            return f"Nessun processo attivo per '{comando}'."
        if result.returncode != 0:
            return f"Chiusura di '{comando}' non riuscita."
        return f"Ho chiuso '{comando}'."
    except PermissionError:
        return _permesso_negato()
    except Exception as e:
        return f"Errore durante la chiusura di {comando}: {e}"


SCHEMA_CHIUDI_APPLICAZIONE = {
    "type": "function",
    "function": {
        "name": "chiudi_applicazione",
        "description": "Chiude un'applicazione o programma attualmente in esecuzione.",
        "parameters": {
            "type": "object",
            "properties": {
                "nome_app": {"type": "string", "description": "Nome dell'applicazione da chiudere"}
            },
            "required": ["nome_app"],
        },
    },
}


# ---------------------------------------------------------------------------
# VOLUME
# ---------------------------------------------------------------------------
AZIONI_VOLUME = {
    "alza": (["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"], "Volume alzato del 10%.",
              ["su", "piu", "aumenta", "alto", "forte", "piu forte"]),
    "abbassa": (["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"], "Volume abbassato del 10%.",
                ["giu", "meno", "diminuisci", "basso", "piano", "piu piano"]),
    "muta": (["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"], "Audio mutato.",
             ["silenzia", "silenzioso", "disattiva audio", "mute", "spegni audio", "muto"]),
    "smuta": (["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"], "Audio riattivato.",
              ["riattiva audio", "unmute", "accendi audio", "togli il muto", "smutalo"]),
}

# comprensione.interpreta si aspetta {canonico: [sinonimi]}, senza i comandi
# pactl in mezzo: costruiamo quella versione "pulita" a parte.
_ALIAS_VOLUME = {nome: dati[2] for nome, dati in AZIONI_VOLUME.items()}


def regolazione_volume(azione: str, percentuale: int = 10) -> str:
    """Alza/abbassa di N punti percentuali (10 di default), muta o smuta."""
    azione_canonica = comprensione.interpreta(azione, _ALIAS_VOLUME)
    if azione_canonica is None:
        return f"Azione volume '{azione}' non riconosciuta (usa: alza, abbassa, muta, smuta)."

    if azione_canonica in ("alza", "abbassa"):
        try:
            # La percentuale non era prevista nelle prime versioni: se Groq
            # non la fornisce, conserviamo il vecchio comportamento (+/-10).
            numero = 10 if percentuale is None else int(round(float(percentuale)))
        except (TypeError, ValueError, OverflowError):
            return "Percentuale non valida: indica un numero tra 1 e 100."
        if not 1 <= numero <= 100:
            return "Percentuale non valida: indica un numero tra 1 e 100."
        try:
            livello = subprocess.run(['pactl', 'get-sink-volume', '@DEFAULT_SINK@'],
                                     capture_output=True, text=True, check=True, timeout=5)
            valori = [int(n) for n in re.findall(r'(\d+)%', livello.stdout)]
            if not valori:
                return 'Non posso determinare il volume corrente: nessuna modifica eseguita.'
            finale = max(0, min(100, max(valori) + (numero if azione_canonica == 'alza' else -numero)))
            return imposta_volume(finale)
        except (OSError, subprocess.SubprocessError):
            return 'Lettura del volume corrente non riuscita: nessuna modifica eseguita.'
    else:
        # Per mute/unmute il numero è irrilevante.
        comando, messaggio, _ = AZIONI_VOLUME[azione_canonica]

    try:
        subprocess.run(comando, check=True, capture_output=True, timeout=5)
        return messaggio
    except FileNotFoundError:
        return "pactl non trovato: verifica di avere PulseAudio/PipeWire attivo."
    except PermissionError:
        return _permesso_negato()
    except Exception as e:
        return f"Errore regolazione volume: {e}"


SCHEMA_REGOLAZIONE_VOLUME = {
    "type": "function",
    "function": {
        "name": "regolazione_volume",
        "description": (
            "Regola il volume RELATIVAMENTE al livello attuale, oppure muta/smuta. "
            "'Alza il volume DEL 20%' -> azione='alza', percentuale=20; "
            "'Abbassa il volume DEL 30%' -> azione='abbassa', percentuale=30. "
            "Senza numero usa 10. Per 'volume AL 20%' usa invece imposta_volume."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "azione": {
                    "type": "string",
                    "enum": ["alza", "abbassa", "muta", "smuta"],
                    "description": "Come modificare il volume."
                },
                "percentuale": {
                    "type": "number",
                    "description": (
                        "Punti percentuali da aggiungere o sottrarre (1-100). "
                        "Passa il numero esatto pronunciato. Se non specificato, usa 10. "
                        "Non serve per muta/smuta."
                    ),
                },
            },
            "required": ["azione"],
        },
    },
}


# ---------------------------------------------------------------------------
# CONTROLLO MULTIMEDIALE (play/pausa/avanti/indietro su Spotify, browser, ecc.)
# ---------------------------------------------------------------------------
AZIONI_MULTIMEDIALI = {
    "play": (["playerctl", "play"], ["riprendi", "continua", "riproduci", "parti", "avvia"]),
    "pausa": (["playerctl", "pause"], ["fermalo", "sospendi"]),
    "play_pausa": (["playerctl", "play-pause"], ["alterna"]),
    "avanti": (["playerctl", "next"], ["prossima", "successiva", "successivo", "prossimo", "salta", "dopo"]),
    "indietro": (["playerctl", "previous"], ["precedente", "prima", "torna"]),
    "stop": (["playerctl", "stop"], ["ferma", "arresta", "blocca", "interrompi"]),
    "ripeti_traccia": (["playerctl", "loop", "Track"], ["ripeti la traccia", "ripeti il brano", "ripeti la canzone"]),
    "ripeti_playlist": (["playerctl", "loop", "Playlist"], ["ripeti la playlist"]),
    "disattiva_ripetizione": (["playerctl", "loop", "None"], ["disattiva ripetizione", "disattiva la ripetizione"]),
    "casuale": (["playerctl", "shuffle", "On"], ["attiva riproduzione casuale", "attiva la riproduzione casuale"]),
    "disattiva_casuale": (["playerctl", "shuffle", "Off"], ["disattiva riproduzione casuale", "disattiva la riproduzione casuale"]),
    "ricomincia": (["playerctl", "position", "0"], ["ricomincia il brano", "ricomincia la traccia", "ricomincia la canzone"]),
}

_ALIAS_MULTIMEDIALI = {nome: dati[1] for nome, dati in AZIONI_MULTIMEDIALI.items()}


def controllo_multimediale(azione: str, lettore: str = None) -> str:
    """
    Controlla la riproduzione multimediale (Spotify, YouTube nel browser, ecc.)
    tramite playerctl, uno standard Linux che funziona con quasi tutti i player.
    Richiede il pacchetto 'playerctl' installato (sudo dnf install playerctl).
    """
    azione_canonica = comprensione.interpreta(azione, _ALIAS_MULTIMEDIALI)
    if azione_canonica is None:
        return f"Azione multimediale '{azione}' non riconosciuta."

    comando, _ = AZIONI_MULTIMEDIALI[azione_canonica]
    try:
        from .lettori import scegli_lettore
        selezionato, errore = scegli_lettore(lettore)
        if errore:
            return errore
        subprocess.run([comando[0], f'--player={selezionato}', *comando[1:]],
                       check=True, capture_output=True, timeout=5)
        risposte = {
            'ripeti_traccia': 'Ripetizione del brano attivata.',
            'ripeti_playlist': 'Ripetizione della playlist attivata.',
            'disattiva_ripetizione': 'Ripetizione disattivata.',
            'casuale': 'Riproduzione casuale attivata.',
            'disattiva_casuale': 'Riproduzione casuale disattivata.',
            'ricomincia': 'Brano riportato all’inizio.',
        }
        return risposte.get(azione_canonica, f"Comando multimediale eseguito: {azione_canonica}.") + f' Lettore: {selezionato}.'
    except FileNotFoundError:
        return "playerctl non è installato. Installa con: sudo dnf install playerctl"
    except subprocess.TimeoutExpired:
        return "Il lettore non ha risposto in tempo. Verifica lo stato della riproduzione."
    except subprocess.CalledProcessError:
        return "Comando non riuscito: nessun player disponibile oppure funzione non supportata dal player."
    except PermissionError:
        return _permesso_negato()
    except Exception as e:
        return f"Errore controllo multimediale: {e}"


SCHEMA_CONTROLLO_MULTIMEDIALE = {
    "type": "function",
    "function": {
        "name": "controllo_multimediale",
        "description": "Controlla la riproduzione multimediale (Spotify, browser, ecc.): play, pausa, tracce, ripetizione, riproduzione casuale e ritorno all'inizio. Le funzioni disponibili dipendono dal player.",
        "parameters": {
            "type": "object",
            "properties": {
                "lettore": {
                    "type": "string",
                    "description": "Nome del lettore SOLO se indicato esplicitamente (es. spotify, vlc, firefox). Altrimenti ometti: la selezione è automatica, con priorità ai browser. Non chiedere all'utente quale lettore usare.",
                },
                "azione": {
                    "type": "string",
                    "description": "Azione: play, pausa, play_pausa, avanti, indietro, stop, ripeti_traccia, ripeti_playlist, disattiva_ripetizione, casuale, disattiva_casuale, ricomincia. Non interpretare 'ripeti' da solo come comando musicale senza contesto.",
                    "enum": list(AZIONI_MULTIMEDIALI),
                }
            },
            "required": ["azione"],
        },
    },
}


# ---------------------------------------------------------------------------
# TABELLA RIASSUNTIVA: da qui vengono generati TOOLS_SCHEMA e FUNZIONI_DISPONIBILI
# Aggiungere una funzione nuova = scriverla sopra + aggiungere UNA riga qui.
# ---------------------------------------------------------------------------
_REGISTRO = [
    (crea_file, SCHEMA_CREA_FILE),
    (scrivi_file, SCHEMA_SCRIVI_FILE),
    (leggi_file, SCHEMA_LEGGI_FILE),
    (elenca_file, SCHEMA_ELENCA_FILE),
    (crea_cartella, SCHEMA_CREA_CARTELLA),
    (svuota_cestino, SCHEMA_SVUOTA_CESTINO),
    (google_cerca, SCHEMA_GOOGLE_CERCA),
    (youtube_cerca, SCHEMA_YOUTUBE_CERCA),
    (youtube_riproduci, SCHEMA_YOUTUBE_RIPRODUCI),
    (cerca_file, SCHEMA_CERCA_FILE),
    (fai_screenshot, SCHEMA_FAI_SCREENSHOT),
    (imposta_volume, SCHEMA_IMPOSTA_VOLUME),
    (invia_notifica, SCHEMA_INVIA_NOTIFICA),
    (copia_negli_appunti, SCHEMA_COPIA_NEGLI_APPUNTI),
    (leggi_appunti, SCHEMA_LEGGI_APPUNTI),
    (imposta_promemoria, SCHEMA_IMPOSTA_PROMEMORIA),
    (avvia_registrazione_schermo, SCHEMA_AVVIA_REGISTRAZIONE),
    (ferma_registrazione_schermo, SCHEMA_FERMA_REGISTRAZIONE),
    (registra_schermo_per, SCHEMA_REGISTRA_PER),
    (avvia_buffer_replay, SCHEMA_AVVIA_BUFFER_REPLAY),
    (salva_replay, SCHEMA_SALVA_REPLAY),
    (ferma_buffer_replay, SCHEMA_FERMA_BUFFER_REPLAY),
    (elimina_file, SCHEMA_ELIMINA_FILE),
    (copia_file, SCHEMA_COPIA_FILE),
    (sposta_file, SCHEMA_SPOSTA_FILE),
    (rinomina_file, SCHEMA_RINOMINA_FILE),
    (apri_applicazione, SCHEMA_APRI_APPLICAZIONE),
    (verifica_app_installata, SCHEMA_VERIFICA_APP_INSTALLATA),
    (chiudi_applicazione, SCHEMA_CHIUDI_APPLICAZIONE),
    (regolazione_volume, SCHEMA_REGOLAZIONE_VOLUME),
    (controllo_multimediale, SCHEMA_CONTROLLO_MULTIMEDIALE),
    (root_tools.cerca_pacchetto, root_tools.SCHEMA_CERCA_PACCHETTO),
    (root_tools.installa_applicazione, root_tools.SCHEMA_INSTALLA_APP),
    (root_tools.aggiorna_sistema, root_tools.SCHEMA_AGGIORNA_SISTEMA),
]

for _schema_video in (SCHEMA_AVVIA_REGISTRAZIONE, SCHEMA_REGISTRA_PER, SCHEMA_AVVIA_BUFFER_REPLAY):
    _schema_video['function']['parameters']['properties']['backend'] = {
        'type': 'string', 'enum': ['auto', 'gsr', 'obs'],
        'description': 'Ometti per GSR se installato, altrimenti OBS. Usa obs solo su richiesta esplicita, gsr per richiesta esplicita di GPU Screen Recorder.'}
    _schema_video['function']['description'] += ' Supporta OBS su richiesta o quando GSR non è installato. OBS usa le proprie scene e impostazioni.'
SCHEMA_AVVIA_BUFFER_REPLAY['function']['parameters']['properties']['secondi']['description'] = 'Durata GSR (default 30). Con OBS ometti: usa la durata configurata in OBS.'

TOOLS_SCHEMA = [schema for _, schema in _REGISTRO]
FUNZIONI_DISPONIBILI = {schema["function"]["name"]: funzione for funzione, schema in _REGISTRO}


def lista_comandi() -> str:
    """Ritorna un elenco leggibile di tutti i comandi disponibili, generato
    automaticamente dal registro qui sopra: non si disallinea mai."""
    righe = ["Comandi disponibili:"]
    for _, schema in _REGISTRO:
        nome = schema["function"]["name"]
        descrizione = schema["function"]["description"]
        righe.append(f"  - {nome}: {descrizione}")
    return "\n".join(righe)
