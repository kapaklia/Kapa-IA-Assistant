# demone.py
#
# Il processo in background ("demone"). Quando è avviato (python main.py
# --background) non fa NIENTE di visibile: non ascolta, il microfono è
# chiuso. Aspetta soltanto un messaggio su un "socket" locale — un canale
# di comunicazione tra programmi dello stesso PC, accessibile solo al tuo
# utente.
#
# Quel messaggio lo manda trigger.py, che è il comando che associ alla
# scorciatoia da tastiera di KDE. Il ciclo è:
#
#   1. premi la scorciatoia  -> trigger.py manda "toggle" al demone
#   2. il demone fa un bip, APRE il microfono e ti ascolta
#   3. smetti di parlare (o premi di nuovo la scorciatoia) -> microfono CHIUSO
#   4. Whisper trascrive, Groq capisce, l'azione viene eseguita
#   5. il risultato ti arriva come notifica (e un bip)
#
# Stati: "attesa" (microfono chiuso) -> "ascolto" -> "elaborazione" -> "attesa"
#
# Il microfono è aperto SOLO nello stato "ascolto". Con i giochi a schermo
# intero non puoi guardare il terminale, per questo il feedback è fatto di
# suoni e notifiche.

import os
import math
import struct
import signal
import socket
import subprocess
import threading
import time
import traceback
import stat
from datetime import datetime
from pathlib import Path

from . import config
from .app_paths import data_dir, private_append, ASSETS_DIR
from .diagnostica_audio import salva_audio, salva_trascrizione
try:
    from .stt import Registratore, crea_trascrittore, MicrofonoNonDisponibile
except ImportError:
    # stt.py "vecchio" (solo Whisper): non ha crea_trascrittore
    from .stt import Registratore, Trascrittore, MicrofonoNonDisponibile

    def crea_trascrittore():
        return Trascrittore()

_CARTELLE_SUONI = [Path("/usr/share/sounds/freedesktop/stereo")]
_SUONI = {
    "ascolto": ["message-new-instant.oga", "message.oga", "bell.oga"],
    "chiuso": ["message.oga", "complete.oga"],
    "errore": ["dialog-error.oga", "dialog-warning.oga", "bell.oga"],
}


def _trova_suono(nome: str):
    for cartella in _CARTELLE_SUONI:
        for file in _SUONI[nome]:
            if (cartella / file).exists():
                return str(cartella / file)
    return None


def _suono(nome: str, bloccante: bool = False):
    """Riproduce un bip di sistema (se disponibile). Non fa mai fallire nulla."""
    if not config.VOCE_SUONI:
        return
    percorso = _trova_suono(nome)
    if not percorso:
        return
    try:
        if bloccante:
            subprocess.run(["paplay", percorso], timeout=3,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["paplay", percorso],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _notifica(titolo: str, testo: str = "", urgenza: str = None):
    """Mostra una notifica di sistema (notify-send). Non fa mai fallire nulla."""
    try:
        comando = ["notify-send", "-a", "Assistente", "-t", "5000",
                   "-u", urgenza or config.VOCE_NOTIFICHE_URGENZA, titolo]
        if testo:
            comando.append(testo[:400])
        subprocess.Popen(comando, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    except Exception:
        pass



def _bip_pronto(tono: float = 440):
    """Bip breve prima di aprire il microfono: niente suono registrato da Whisper.

    Genera 120 ms di PCM in memoria, con attacco e rilascio morbidi.
    Se paplay non risponde, si procede comunque dopo massimo 0,4 secondi.
    """
    if not config.VOCE_SUONI:
        return
    frequenza = 16000
    durata = 0.12
    campioni = int(frequenza * durata)
    # Tono più basso e discreto; l'inviluppo evita gli scatti ai bordi.
    audio = b"".join(struct.pack("<h", int(
        4000 * math.sin(math.pi * i / (campioni - 1)) ** 2
        * math.sin(2 * math.pi * tono * i / frequenza)))
                     for i in range(campioni))
    processo = None
    try:
        processo = subprocess.Popen(
            ["paplay", "--raw", "--format=s16le", "--rate=16000", "--channels=1"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processo.communicate(input=audio, timeout=0.4)
    except (OSError, subprocess.TimeoutExpired):
        if processo is not None:
            processo.kill()
            processo.communicate()



# Registro di ogni comando vocale, scritto SUBITO (non alla chiusura): serve a
# capire cosa ha sentito Whisper davvero. Una riga per comando.
_FILE_TRASCRIZIONI = data_dir() / "trascrizioni.log"


def _registra_trascrizione(testo: str, esito: str):
    try:
        with private_append(_FILE_TRASCRIZIONI) as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | sentito: {testo!r} | esito: {esito}\n")
    except Exception:
        pass


def _log(messaggio: str):
    print(messaggio, flush=True)


def costruisci_prompt_whisper(giochi=()):
    """Suggerimento Whisper compatto, bilingue e focalizzato sui comandi.

    Il dizionario comune e quello personale sono estensibili; non bisogna
    inviare a Whisper un intero dizionario, che peggiorerebbe i risultati.
    """
    # Questo incipit è stato confrontato con i WAV: Small riconosceva sia
    # «metti play» sia «metti pausa» con questo prompt.
    base = (
        "Comandi vocali in italiano: metti play, metti pausa, alza il volume, "
        "abbassa il volume, apri Firefox. Avvia il buffer replay, "
        "salva il replay, ferma il buffer replay. GPU Screen Recorder. "
    )
    limite_totale = 480
    gruppi = {"comandi": [], "multimedia": [], "applicazioni": [],
              "sistema": [], "rete": [], "file": [], "inglese": []}
    percorso = ASSETS_DIR / "vocabolario_comune.txt"
    try:
        gruppo = None
        for riga in percorso.read_text(encoding="utf-8").splitlines():
            voce = riga.strip()
            if not voce or voce.startswith("#"):
                continue
            if voce.startswith("[") and voce.endswith("]"):
                nome = voce[1:-1].casefold()
                gruppo = nome if nome in gruppi else None
            elif gruppo and len(voce) <= 80:
                gruppi[gruppo].append(voce)
    except OSError:
        # L'app continua a funzionare anche se il file non è stato copiato.
        pass

    personali = []
    try:
        if config.WHISPER_FILE_PERSONALE.is_file():
            personali = [r.strip() for r in
                         config.WHISPER_FILE_PERSONALE.read_text(encoding="utf-8").splitlines()
                         if r.strip() and not r.lstrip().startswith("#")]
    except OSError:
        pass

    # Prima le azioni, poi i nomi specifici, poi i termini tecnici.
    # Piccoli limiti per gruppo, per non sacrificare il prompt dei comandi.
    categorie = [
        ("comandi", gruppi["comandi"], 95),
        ("nomi", personali, 80),
        ("giochi", giochi, 55),
        ("multimedia", gruppi["multimedia"], 45),
        ("app", gruppi["applicazioni"], 40),
        ("sistema", gruppi["sistema"], 40),
        ("termini", config.WHISPER_TERMINI_COMUNI, 40),
        ("inglese", gruppi["inglese"], 30),
    ]
    testo = base
    visti = {x.casefold() for x in ("metti play", "metti pausa", "alza il volume",
                                    "abbassa il volume", "apri Firefox", "GPU Screen Recorder")}
    for etichetta, termini, budget in categorie:
        selezionati = []
        usati = 0
        for termine in termini:
            termine = str(termine).strip()
            if not termine or len(termine) > 80 or termine.casefold() in visti:
                continue
            costo = len(termine) + (2 if selezionati else 0)
            if usati + costo > budget:
                continue
            selezionati.append(termine)
            usati += costo
            visti.add(termine.casefold())
        if selezionati:
            aggiunta = etichetta + ": " + ", ".join(selezionati) + ". "
            if len(testo) + len(aggiunta) <= limite_totale:
                testo += aggiunta
    return testo.strip()


class Demone:
    def __init__(self, gestore, vocabolario_extra=None, registratore=None, trascrittore=None):
        """
        gestore: funzione che prende il testo trascritto e ritorna la risposta
                 (in pratica gestisci_richiesta di main.py, già configurata).
        vocabolario_extra: nomi (es. giochi Steam) da passare a Whisper per
                 aiutarlo a riconoscerli.
        registratore / trascrittore: servono solo per i test.
        """
        self.gestore = gestore
        self.registratore = registratore or Registratore()
        self.trascrittore = trascrittore
        self.prompt = costruisci_prompt_whisper(vocabolario_extra or ())

        self._stato = "attesa"
        self._lock = threading.Lock()
        self._ferma_ascolto = threading.Event()
        self._arresta = threading.Event()
        self._hotkey = None
        self._worker = None

    # ------------------------------------------------------------------ socket
    def _prepara_socket(self) -> socket.socket:
        percorso = config.SOCKET_PATH
        percorso.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = percorso.parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077):
            raise RuntimeError('Directory socket non privata o non appartenente al tuo utente.')

        if percorso.exists() or percorso.is_symlink():
            if not stat.S_ISSOCK(percorso.lstat().st_mode):
                raise RuntimeError('Il percorso socket è occupato da un file non valido.')
            # C'è già un file: o un altro demone è attivo, o è un residuo
            # di un'esecuzione interrotta. Proviamo a connetterci per capirlo.
            prova = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            prova.settimeout(1)
            try:
                prova.connect(str(percorso))
                prova.close()
                raise RuntimeError("Un'altra istanza dell'assistente è già in esecuzione.")
            except (ConnectionRefusedError, FileNotFoundError):
                percorso.unlink(missing_ok=True)
            except socket.timeout as exc:
                raise RuntimeError('Socket occupato o non rispondente: nessun file rimosso.') from exc
            finally:
                prova.close()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        vecchia_umask = os.umask(0o177)          # il socket nasce già accessibile solo a te
        try:
            server.bind(str(percorso))
        finally:
            os.umask(vecchia_umask)
        os.chmod(percorso, 0o600)
        server.listen(4)
        server.settimeout(1.0)
        return server

    def esegui(self):
        """Avvia il demone e resta in attesa dei comandi finché non viene fermato."""
        if self.trascrittore is None:
            self.trascrittore = crea_trascrittore()

        server = self._prepara_socket()
        # Ctrl+C e "systemctl stop" fermano il demone in modo pulito (chiudendo
        # il socket). Python permette di registrare i segnali solo dal thread
        # principale, dove di norma gira: negli altri casi (es. test) si salta.
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, lambda *_: self._arresta.set())

        try:
            from .hotkey_portal import GlobalHotkey
            self._hotkey = GlobalHotkey(lambda: self.gestisci_comando("toggle"))
            self._hotkey.start()
        except Exception as exc:
            _log(f"Scorciatoia automatica non disponibile: {exc}")
        _log(f"✅ Assistente in background pronto. Microfono CHIUSO. "
             f"In attesa della scorciatoia (socket: {config.SOCKET_PATH})")
        try:
            while not self._arresta.is_set():
                try:
                    connessione, _ = server.accept()
                except socket.timeout:
                    continue
                with connessione:
                    connessione.settimeout(2)
                    try:
                        comando = connessione.recv(64).decode("utf-8", "ignore").strip()
                        connessione.sendall(self.gestisci_comando(comando).encode("utf-8"))
                    except Exception:
                        pass
        finally:
            self._arresta.set()
            self._ferma_ascolto.set()
            if self._hotkey:
                self._hotkey.stop()
            server.close()
            if self._worker:
                self._worker.join(timeout=35)
            try:
                config.SOCKET_PATH.unlink()
            except FileNotFoundError:
                pass
            _log("Assistente in background fermato.")

    # --------------------------------------------------------------- comandi
    def arresto_richiesto(self):
        return self._arresta.is_set()

    def gestisci_comando(self, comando: str) -> str:
        """Interpreta un messaggio arrivato dal socket. Ritorna una breve risposta."""
        with self._lock:
            if comando == "toggle":
                if self._arresta.is_set():
                    return 'occupato'
                if self._stato == "attesa":
                    self._stato = "ascolto"
                    self._ferma_ascolto.clear()
                    self._worker = threading.Thread(target=self._ciclo_vocale, daemon=False)
                    self._worker.start()
                    return "ascolto"
                if self._stato == "ascolto":
                    self._ferma_ascolto.set()    # secondo tocco: smetti di ascoltare adesso
                    return "stop"
                return "occupato"

            if comando == "stop":
                if self._stato == "ascolto":
                    self._ferma_ascolto.set()
                return self._stato

            if comando == "stato":
                return self._stato

            if comando == "hotkey-stato":
                return self._hotkey.state() if self._hotkey else "non_disponibile"

            if comando == "hotkey-configura":
                return self._hotkey.configure() if self._hotkey else "non_disponibile"

            if comando == "esci":
                self._arresta.set()
                self._ferma_ascolto.set()
                return "ok"

        return "comando sconosciuto"

    def _imposta_stato(self, stato: str):
        with self._lock:
            self._stato = stato

    # ------------------------------------------------------------ ciclo vocale
    def _ciclo_vocale(self):
        """Un intero giro: ascolta -> trascrive -> esegue -> risponde."""
        testo = ""
        evento = None
        try:
            _bip_pronto()  # Suono completato prima della cattura
            _notifica("🎤 Ti ascolto", "Parla ora...", "low")  # non bloccante
            _log("🎤 Microfono APERTO")

            audio = self.registratore.registra(self._ferma_ascolto)
            if self._arresta.is_set():
                return

            _log("🔇 Microfono CHIUSO")
            _bip_pronto(330)  # Stesso timbro morbido, più basso alla chiusura
            self._imposta_stato("elaborazione")

            if audio is None:
                evento = {'sentito': '', 'esito': 'Nessun parlato rilevato.',
                          'percorso': 'scartato', 'azioni': []}
                _registra_trascrizione("", "nessun parlato rilevato")
                _notifica("🤷 Non ho sentito niente")
                return

            wav_diagnostico = salva_audio(audio)
            if wav_diagnostico is not None:
                _log(f"🔬 Audio diagnostico salvato: {wav_diagnostico.name}")
            t0 = time.monotonic()
            testo = self.trascrittore.trascrivi(audio, self.prompt)
            if self._arresta.is_set():
                return
            t_trascrizione = time.monotonic() - t0
            grezzo = getattr(self.trascrittore, "ultima_trascrizione_grezza", testo)
            salva_trascrizione(wav_diagnostico, testo, grezzo, t_trascrizione)
            if grezzo != testo:
                _log(f"🧹 Whisper: coda sospetta filtrata (originale: {grezzo!r})")
                _registra_trascrizione(grezzo, "trascrizione grezza: credito finale filtrato")
            if not testo or self.trascrittore.e_allucinazione(testo):
                evento = {'sentito': testo, 'esito': 'Trascrizione vuota o sospetta: riprova.',
                          'percorso': 'scartato', 'azioni': []}
                _registra_trascrizione(testo, "scartato (vuoto o allucinazione)")
                _notifica("🤷 Non ho capito, riprova")
                return

            _log(f"🗣️  {testo}")
            _notifica("🗣️ Ho capito", testo)

            evento = {'sentito': testo, 'esito': '', 'percorso': 'sconosciuto',
                      'azioni': [], 'ora': datetime.now().isoformat(timespec='seconds')}
            t0 = time.monotonic()
            risposta = self.gestore(testo)
            evento.update(getattr(self.gestore, 'diagnostica', {}))
            evento['esito'] = risposta or 'Fatto'
            _log(f"⏱  trascrizione {t_trascrizione:.1f}s, azione {time.monotonic() - t0:.1f}s")
            _log(f"🤖 {risposta}")
            _notifica("✅ Assistente", risposta or "Fatto")
            _registra_trascrizione(testo, risposta or "Fatto")

        except MicrofonoNonDisponibile as e:
            _suono("errore")
            _notifica("⚠️ Microfono non disponibile", str(e), "critical")
            _log(f"⚠️ {e}")
        except Exception as e:
            if evento is not None:
                evento.update(getattr(self.gestore, 'diagnostica', {}))
                evento['esito'] = f'Errore: {e}'
            _suono("errore")
            _registra_trascrizione(testo, f"ERRORE: {e}")
            _notifica("⚠️ Errore", str(e)[:200], "critical")
            _log(f"⚠️ Errore: {e}\n{traceback.format_exc()}")
        finally:
            if evento is not None:
                from .attivita import registra_attivita
                registra_attivita(evento)
            if self._arresta.is_set():
                from . import tools
                tools.arresta_catture()
            self._imposta_stato("attesa")
