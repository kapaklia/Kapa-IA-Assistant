# main.py
#
# Questo è il file che avvii tu (con: python main.py).
# Fa da "direttore d'orchestra": non sa fare nulla di concreto da solo,
# ma sa a chi chiedere:
#   1. legge quello che scrivi da tastiera
#   2. lo manda a Groq (l'intelligenza artificiale) chiedendo "cosa vuole fare l'utente?"
#   3. Groq risponde indicando quale funzione chiamare (tra quelle in tools.py)
#   4. main.py esegue quella funzione e stampa il risultato

import argparse
import json
import time
import re
from groq import Groq, APIStatusError

from . import config
from . import tools
from . import memoria
from . import comprensione
from .tool_validation import validate_arguments
from .comandi_rapidi import (riconosci as riconosci_comando_rapido,
                            rifiuta_volume_non_valido, valida_parametri_volume)

# ---------------------------------------------------------------------------
# 1) Colleghiamo Python a Groq usando la chiave segreta letta da config.py
# ---------------------------------------------------------------------------
if not config.GROQ_API_KEY:
    print("❌ Manca GROQ_API_KEY nel file .env. Crealo prima di continuare.")
    exit(1)

# Non moltiplicare le attese con retry automatici nascosti della SDK.
# Il timeout vale per ciascuna chiamata, non per l'intera richiesta.
client = Groq(api_key=config.GROQ_API_KEY, max_retries=0, timeout=15.0)


# ---------------------------------------------------------------------------
# 2) Il "menù" delle funzioni che Groq può usare, e la mappa nome->funzione
#    vera, sono ORA DEFINITI DENTRO tools.py (vicino a ogni funzione).
#    Qui li importiamo soltanto: main.py non deve sapere i dettagli di
#    ogni singola funzione, sa solo che tools.py gliele fornisce già pronte.
# ---------------------------------------------------------------------------
TOOLS_SCHEMA = tools.TOOLS_SCHEMA
FUNZIONI_DISPONIBILI = tools.FUNZIONI_DISPONIBILI


SYSTEM_PROMPT = """Sei un assistente per computer Linux. La distribuzione viene rilevata localmente dalle funzioni amministrative.

STILE DI RISPOSTA:
- Rispondi sempre in italiano, in modo breve (1-2 frasi)
- Usa sempre la funzione corrispondente per creare/copiare/spostare/rinominare/
  eliminare file, aprire o chiudere applicazioni, gestire volume e multimedia

CARTELLE DISPONIBILI:
- scrivania, documenti, download, immagini, video, musica
- 'home' per l'intera cartella personale dell'utente
- Nomi accettati sia in italiano che in inglese comune (desktop, downloads,
  pictures, videos, music, docs): il codice li riconosce entrambi

REGOLE DI SICUREZZA SUI FILE (priorità alta, non derogabili):
- "Crea un NUOVO file X" -> crea_file. Se non specifichi l'estensione,
  crea_file aggiunge .txt; se il file già esiste non viene sovrascritto.
- "Scrivi/aggiungi/trascrivi nel file ESISTENTE X" -> scrivi_file,
  NON crea_file. scrivi_file aggiunge senza cancellare il contenuto precedente
  e riconosce X.txt quando l'utente dice solo X; se il file manca o il nome
  è ambiguo, riferisci l'errore e chiedi il nome preciso, non creare file.
- Se l'utente detta testo da inserire in un file, NON riscriverlo,
  tradurlo, correggerlo o riassumerlo: usa esattamente il testo ricevuto.
- La SOSTITUZIONE del contenuto di un file non è disponibile: non simulare
  la sostituzione chiamando crea_file o eseguendo comandi generici.
- Se l'utente chiede di dettare il testo nel turno successivo, chiedi di
  pronunciarlo; non inventare contenuti e non scrivere file vuoti.
- Se un'operazione sui file ritorna un errore di permesso negato, NON
  proporre mai di usare una password: quell'operazione va fatta dall'utente
  direttamente nel terminale. Non gestisci password per i file, solo per
  l'installazione software (vedi sotto)

CASI SPECIALI CON FUNZIONE DEDICATA (usa SEMPRE queste, mai un comando generico):
- Registrazione e replay: ometti backend per usare GSR se installato, altrimenti
  OBS. Se l'utente specifica OBS passa backend="obs"; per GPU Screen Recorder
  esplicito passa backend="gsr". Non cambiare programma dopo un errore.
  OBS usa le proprie scene, audio, cartelle e durata replay: non inventare
  impostazioni e non passare secondi al buffer OBS se non richiesti.
  Per fermare o salvare usa le funzioni esistenti: ricordano il programma avviato.
- "Cerca X su Google" / "cerca su internet X" -> usa google_cerca.
  Apre i risultati nel browser: non affermare di aver letto le pagine.
- Svuotare il cestino -> usa svuota_cestino, mai una funzione amministrativa (il
  cestino è dentro la home, non serve root)
- "Ho X installato?" / "esiste X sul pc?" (domanda) -> usa
  verifica_app_installata, NON apri_applicazione. Apri l'app solo se
  l'utente chiede esplicitamente di aprirla/avviarla
- "Metti/riproduci/fai partire X su YouTube" -> usa youtube_riproduci
  (apre direttamente il video). "Cerca X su YouTube" (senza dire di
  aprirlo) -> usa youtube_cerca (mostra solo i risultati)
- Non sai in quale cartella si trova un file -> usa cerca_file (cerca in
  tutte le cartelle insieme), non elenca_file cartella per cartella
- Volume ASSOLUTO ("metti/imposta/porta il volume al 30%", oppure
  "abbassa il volume AL 20%") -> usa imposta_volume con percentuale=30 o 20.
- Volume RELATIVO ("alza/abbassa il volume DEL 20%") -> usa
  regolazione_volume con azione="alza"/"abbassa" e percentuale=20.
  Trasmetti SEMPRE il numero richiesto: non ignorarlo e non sostituirlo con 10.
- "Alza/abbassa il volume" SENZA numero -> usa regolazione_volume senza
  percentuale (applica il valore predefinito di 10 punti percentuali).
- "Muta/smuta" -> usa regolazione_volume con azione="muta"/"smuta".
- apri_applicazione funziona anche per i giochi installati su Steam, non
  solo per app normali: se l'utente chiede di aprire qualcosa che sembra
  un gioco, prova comunque con apri_applicazione
- "Fai un video di N secondi" -> usa registra_schermo_per (si ferma da sola).
  "Salva/clippa gli ultimi N secondi" -> salva_replay (richiede il buffer attivo)
- Registrazione schermo: avvia_registrazione_schermo / ferma_registrazione_schermo
  per una registrazione normale. avvia_buffer_replay / salva_replay /
  ferma_buffer_replay per il buffer replay (tiene pronti gli ultimi N
  secondi, salvabili a comando senza registrare in continuo) — sono due
  modalità DIVERSE, non mescolarle. Anche se l'utente dice "apri il
  registratore schermo" o "apri gpu screen recorder", usa
  avvia_registrazione_schermo, NON apri_applicazione: intende avviare
  una registrazione, non aprire un programma generico
- Se avvia_registrazione_schermo o avvia_buffer_replay danno un errore che
  parla di opzioni/argomenti mancanti o non supportati, NON è un problema
  di installazione (il programma è già installato e funzionante): dillo
  all'utente e suggerisci di controllare GSR_TARGET/GSR_AUDIO in config.py,
  NON proporre di installare il pacchetto in quel caso

INSTALLAZIONE E AGGIORNAMENTO DEL SISTEMA:
- "cerca GIMP nei repository" -> cerca_pacchetto (non richiede root).
- Solo su richiesta esplicita: "installa GIMP" -> installa_applicazione(nome_app="gimp").
- "aggiorna il sistema" / "fai gli aggiornamenti" -> aggiorna_sistema().
- Non inventare comandi shell: i gestori pacchetti e la distribuzione sono rilevati localmente.
- Su Nobara gli aggiornamenti usano nobara-sync cli (non dnf upgrade).
- Le funzioni aprono un terminale dove l'utente conferma e, se serve, digita la password.
- Non dichiarare installazione/aggiornamento completati prima della conferma del terminale.
- Non proporre o eseguire disinstallazioni, modifiche a servizi, file di sistema o altri comandi root.
"""


class LimiteGroq(Exception):
    """Limite temporaneo del provider, senza esporre traceback o dati interni."""


def _messaggio_limite_groq(errore):
    attesa = None
    try:
        valore = errore.response.headers.get('retry-after')
        if valore is not None:
            attesa = max(1, min(3600, int(float(valore)) + 1))
    except (AttributeError, ValueError, TypeError):
        pass
    if attesa is None:
        # Fallback sul messaggio del provider (es. "Please try again in 3.7s").
        corpo = getattr(errore, 'body', None)
        dettagli = corpo.get('error', {}) if isinstance(corpo, dict) else {}
        descrizione = str(dettagli.get('message', '')) if isinstance(dettagli, dict) else ''
        trovato = re.search(r'(?i)try again in\s+([0-9]+(?:\.[0-9]+)?)s', descrizione)
        if trovato:
            attesa = max(1, min(3600, int(float(trovato.group(1))) + 1))
    if attesa is None:
        return 'Groq ha raggiunto un limite temporaneo di richieste. Riprova fra poco.'
    return f'Groq ha raggiunto il limite temporaneo. Riprova tra circa {attesa} secondi.'


def chiamata_groq_sicura(**argomenti):
    """
    Involucro attorno a client.chat.completions.create che gestisce un bug
    noto di Groq/Llama-3.3: a volte il modello genera una chiamata di
    funzione in un formato sbagliato (invece di JSON pulito scrive qualcosa
    tipo <function=nome{...}></function>), e Groq risponde con un errore
    400 'tool_use_failed'. Non è un problema del nostro codice, è il
    modello che ogni tanto "inciampa" nella sintassi: la soluzione è riprovare una sola volta, evitando attese cumulative.

    Ritorna la risposta se va a buon fine, e solleva l’errore se falliscono entrambi i tentativi.
    """
    scadenza = argomenti.pop('_scadenza', time.monotonic() + 35)
    tentativi_massimi = 2
    for tentativo in range(1, tentativi_massimi + 1):
        residuo = scadenza - time.monotonic()
        if residuo <= 0:
            raise TimeoutError('Tempo complessivo della richiesta esaurito.')
        argomenti['timeout'] = min(15.0, residuo)
        inizio = time.monotonic()
        try:
            risposta = client.chat.completions.create(**argomenti)
            usage = getattr(risposta, 'usage', None)
            if usage is not None:
                print(f"   Token Groq: input={usage.prompt_tokens}, output={usage.completion_tokens}", flush=True)
            print(f"   ⏱ Groq tentativo {tentativo}: {time.monotonic()-inizio:.2f}s", flush=True)
            return risposta
        except APIStatusError as e:
            codice_errore = None
            try:
                codice_errore = e.body.get("error", {}).get("code")
            except Exception:
                pass

            print(f"   ⏱ Groq tentativo {tentativo}: {time.monotonic()-inizio:.2f}s (errore: {codice_errore or e.status_code})", flush=True)
            if e.status_code == 429:
                raise LimiteGroq(_messaggio_limite_groq(e)) from None
            if codice_errore == "tool_use_failed" and tentativo < tentativi_massimi:
                print("   (chiamata funzione malformata, un solo nuovo tentativo...)")
                time.sleep(0.2)
                continue

            raise  # errore diverso, o abbiamo già riprovato: lo lasciamo passare


def _pulisci_risposta_testuale(testo: str) -> str:
    """
    Rete di sicurezza: a volte il modello, quando in quel momento non ha
    strumenti disponibili per agire (es. nella risposta finale dopo aver
    già eseguito una funzione), scrive per errore la sintassi di una
    chiamata a funzione come TESTO letterale invece di parole normali
    (es. "<function=esegui_come_root>{...}</function>"). Non deve mai
    arrivare a schermo così com'è: teniamo solo la parte di spiegazione
    prima di quel tentativo, che di solito è comunque comprensibile.
    """
    if not testo:
        return testo
    if "<function=" in testo:
        parte_pulita = testo.split("<function=")[0].strip()
        return parte_pulita if parte_pulita else "Ho notato un problema, puoi ripetere la richiesta?"
    return testo



# Selezione prudente: le richieste riconoscibili inviano solo pochi strumenti.
# In caso di dubbio si mantiene il catalogo completo: mai perdere le capacità.
_GRUPPI_FUNZIONI = {
    "app": {"apri_applicazione", "chiudi_applicazione", "verifica_app_installata", "cerca_pacchetto", "installa_applicazione"},
    "file": {"crea_file", "scrivi_file", "leggi_file", "elenca_file", "cerca_file", "elimina_file", "copia_file", "sposta_file", "rinomina_file", "crea_cartella"},
    "youtube": {"youtube_cerca", "youtube_riproduci"},
    "web": {"google_cerca"},
    "volume": {"regolazione_volume", "imposta_volume", "controllo_multimediale"},
    "schermo": {"fai_screenshot", "avvia_registrazione_schermo", "ferma_registrazione_schermo", "registra_schermo_per", "avvia_buffer_replay", "salva_replay", "ferma_buffer_replay"},
    "sistema": {"aggiorna_sistema", "installa_applicazione", "cerca_pacchetto"},
    "altro": {"invia_notifica", "imposta_promemoria", "copia_negli_appunti", "leggi_appunti", "svuota_cestino"},
}


def _scegli_schemi(testo, schemi):
    import re
    s = testo.casefold().strip()
    # Domande di conoscenza generale: il modello deve rispondere, non agire.
    # Niente tool per "quali applicazioni consigli per modificare immagini?".
    domanda = bool(re.match(r"^(dimmi|spiegami|consigliami|quali|quale|che cosa|cosa|come posso|mi consigli|suggeriscimi)\b", s))
    informativa = domanda and any(w in s for w in (
        "posso usare", "potrei usare", "consigli", "consiglieresti", "alternative",
        "differenza", "miglior", "adatt", "modificare le immagini", "modificare immagini", "programmi per", "applicazioni per", "software per"))
    ricerca_web = bool(re.search(r"\bgoogle\b|\b(?:cerca|ricerca)\b.*\b(?:internet|web|online)\b", s))
    if informativa and not ricerca_web:
        return []
    gruppi = set()
    if ricerca_web:
        gruppi.add("web")
    if any(w in s for w in ("youtube", "you tube")):
        gruppi.add("youtube")
    if re.search(r"\b(volume|audio|musica|pausa|play|riproduzione|muto|mute)\b", s) and not gruppi:
        gruppi.add("volume")
    if any(w in s for w in ("screenshot", "schermo", "replay", "registrazione", "registra video", "clip")):
        gruppi.add("schermo")
    if any(w in s for w in ("aggiorna il sistema", "aggiornamenti", "aggiorna nobara", "aggiorna fedora", "aggiorna linux")):
        gruppi.add("sistema")
    if re.search(r"\b(installa|installare|repository|pacchetto|disinstalla)\b", s):
        gruppi.add("app")
    if re.search(r"\b(apri|avvia|lancia|chiudi)\b", s) and not gruppi:
        gruppi.add("app")
    if any(w in s for w in ("file", "cartella", "documento", "scrivania", "download", "rinomina", "sposta", "copia ", "cancella ", "elimina ", "scrivi ", "leggimi ")):
        gruppi.add("file")
    if any(w in s for w in ("promemoria", "notifica", "appunti", "cestino")):
        gruppi.add("altro")
    if not gruppi:
        return schemi  # ambiguità e riferimenti al contesto: non restringere
    ammessi = set().union(*(_GRUPPI_FUNZIONI[g] for g in gruppi))
    selezionati = [f for f in schemi if f["function"]["name"] in ammessi]
    return selezionati if selezionati else schemi


def _messaggi_compatti(cronologia, ultimi=9):
    # Non inviare nuovamente dettagli tecnici di chiamate a tool. Teniamo
    # domande e risposte naturali, salvando comunque tutta la storia localmente.
    ridotti = []
    messaggi = cronologia.messaggi[1:]
    ultimo_utente = max((i for i, m in enumerate(messaggi)
                        if isinstance(m, dict) and m.get('role') == 'user'), default=-1)
    for indice, m in enumerate(messaggi):
        if isinstance(m, dict):
            role, content = m.get("role"), m.get("content")
        else:
            role, content = getattr(m, "role", None), getattr(m, "content", None)
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            ridotti.append({"role": role, "content": content if indice == ultimo_utente else content[:1000]})
    # Include sempre l'ultimo turno dell'utente.
    return [cronologia.messaggi[0]] + ridotti[-ultimi:]

def gestisci_richiesta(testo_utente: str, cronologia: memoria.Memoria,
                       tools_schema=None, funzioni=None, riassumi=True, annullato=None,
                       diagnostica=None) -> str:
    """Prende quello che ha scritto (o detto) l'utente, chiede a Groq cosa
    fare, esegue l'eventuale funzione e ritorna la risposta finale.

    tools_schema / funzioni: di norma tutte le funzioni disponibili; la
    modalità vocale in background ne passa una lista RIDOTTA (senza i
    comandi root, che richiedono un terminale per la password).

    Rispetto a prima, i messaggi non partono più da zero ad ogni chiamata:
    vengono presi da `cronologia`, che li mantiene tra un turno e l'altro
    (questa è la "memoria" della conversazione)."""

    diagnostica = diagnostica if diagnostica is not None else {}
    diagnostica.clear()
    diagnostica.update(percorso='locale', azioni=[])
    tools_schema = tools_schema if tools_schema is not None else TOOLS_SCHEMA
    funzioni = funzioni if funzioni is not None else FUNZIONI_DISPONIBILI
    annullato = annullato or (lambda: False)
    scadenza = time.monotonic() + 35
    if annullato():
        return 'Richiesta annullata.'
    if not isinstance(testo_utente, str) or len(testo_utente) > 20000:
        return "Richiesta troppo lunga: usa al massimo 20000 caratteri."

    # Prima di qualunque chiamata AI, rifiuta un volume esplicitamente >100%.
    if rifiuta_volume_non_valido(testo_utente):
        risultato = 'Per il volume usa una percentuale intera tra 0 e 100.'
        print('   🛑 locale: volume fuori limite, nessuna richiesta a Groq', flush=True)
        cronologia.aggiungi({'role': 'user', 'content': testo_utente})
        cronologia.aggiungi({'role': 'assistant', 'content': risultato})
        return risultato

    # Percorso diretto soltanto per frasi corte, inequivocabili e senza
    # riferimenti contestuali. Le richieste complesse restano a Groq.
    rapido = riconosci_comando_rapido(testo_utente)
    if rapido is not None:
        nome_funzione, parametri = rapido
        funzione = funzioni.get(nome_funzione)
        if funzione is not None:
            diagnostica['azioni'].append(nome_funzione)
            inizio_locale = time.monotonic()
            risultato = str(funzione(**parametri))
            print(f"   ⚡ locale: {nome_funzione}{parametri} in {time.monotonic()-inizio_locale:.2f}s", flush=True)
            cronologia.aggiungi({"role": "user", "content": testo_utente})
            cronologia.aggiungi({"role": "assistant", "content": risultato})
            return risultato

    cronologia.aggiungi({"role": "user", "content": testo_utente})

    # Prima chiamata: chiediamo a Groq di capire la richiesta,
    # passandogli TUTTA la cronologia finora, non solo l'ultimo messaggio.
    # temperature bassa apposta: qui Groq deve scegliere la funzione giusta
    # in modo affidabile, non "essere creativo". Con la temperatura di
    # default il modello tende a inventare più facilmente, specialmente
    # sui retry (ogni tentativo rischia di uscire diverso).
    diagnostica['percorso'] = 'groq'
    schemi_ridotti = _scegli_schemi(testo_utente, tools_schema)
    messaggi_groq = _messaggi_compatti(cronologia)
    print(f"   📉 Groq: {len(schemi_ridotti)}/{len(tools_schema)} funzioni; "
          f"{len(messaggi_groq)} messaggi", flush=True)
    parametri_groq = dict(model=config.GROQ_MODEL, messages=messaggi_groq,
                         temperature=0.2, max_completion_tokens=2048, _scadenza=scadenza)
    if schemi_ridotti:
        parametri_groq.update(tools=schemi_ridotti, tool_choice="auto")
    try:
        risposta = chiamata_groq_sicura(**parametri_groq)
    except LimiteGroq as e:
        testo_errore = str(e)
        print(f'   ⚠️ {testo_errore}', flush=True)
        cronologia.aggiungi({'role': 'assistant', 'content': testo_errore})
        return testo_errore

    messaggio_ia = risposta.choices[0].message

    # Se Groq NON ha chiesto di usare nessuna funzione, la sua risposta
    # di testo è già la risposta finale.
    if not messaggio_ia.tool_calls:
        testo_pulito = _pulisci_risposta_testuale(messaggio_ia.content)
        cronologia.aggiungi({"role": "assistant", "content": testo_pulito})
        return testo_pulito

    # Se invece Groq vuole usare una funzione, la eseguiamo qui.
    cronologia.aggiungi(messaggio_ia)

    risultati = []
    schemi_ammessi = {s['function']['name']: s['function']['parameters'] for s in schemi_ridotti}
    messaggi_esiti = []
    for chiamata in messaggio_ia.tool_calls:
        nome_funzione = chiamata.function.name
        t_funzione = time.monotonic()
        try:
            if annullato():
                raise ValueError('Richiesta annullata: azione non eseguita.')
            if nome_funzione not in schemi_ammessi or nome_funzione not in funzioni:
                raise ValueError('Funzione non autorizzata per questa richiesta.')
            if len(messaggio_ia.tool_calls) > 8:
                raise ValueError('Troppe azioni: suddividi la richiesta.')
            argomenti = json.loads(chiamata.function.arguments or '{}')
            if argomenti is None and not schemi_ammessi[nome_funzione].get('properties'):
                argomenti = {}
            validate_arguments(schemi_ammessi[nome_funzione], argomenti)
            errore_volume = valida_parametri_volume(nome_funzione, argomenti)
            if not errore_volume:
                diagnostica['azioni'].append(nome_funzione)
            esito = errore_volume or funzioni[nome_funzione](**argomenti)
        except (ValueError, TypeError) as exc:
            esito = f"Azione rifiutata: {exc}"
        except Exception:
            esito = "Azione interrotta: verifica il risultato prima di ripetere la richiesta."

        print(f"   ⏱ funzione {nome_funzione}: {time.monotonic()-t_funzione:.2f}s", flush=True)

        # Mostriamo anche l'esito GREZZO, prima che Groq lo riformuli in
        # linguaggio naturale: utile per il debug, specialmente con
        # comandi tecnici (es. errori di gpu-screen-recorder) dove la
        # parafrasi finale può perdere dettagli tecnici importanti.
        esito_breve = (esito[:300] + "...") if isinstance(esito, str) and len(esito) > 300 else esito
        print(f"   -> {esito_breve}")
        risultati.append(str(esito))

        # Diciamo a Groq cosa è successo, così può formulare una risposta
        # in italiano naturale invece di farci leggere l'esito grezzo.
        messaggio_esito = {
            "role": "tool",
            "tool_call_id": chiamata.id,
            "content": json.dumps({"risultato": str(esito)}),
        }
        cronologia.aggiungi(messaggio_esito)
        messaggi_esiti.append(messaggio_esito)

    if not riassumi or sum(len(r) for r in risultati) > 12000 or annullato():
        # Modalità vocale: l'esito di ogni funzione è già una frase chiara in
        # italiano ("Volume alzato del 10%."), quindi saltiamo la seconda
        # chiamata a Groq: risposta molto più rapida e metà delle richieste.
        testo_risposta = " ".join(risultati)
        cronologia.aggiungi({"role": "assistant", "content": testo_risposta})
        return testo_risposta

    # Seconda chiamata: ora che Groq sa l'esito, gli chiediamo di
    # riassumerlo in una risposta naturale per l'utente.
    try:
        risposta_finale = chiamata_groq_sicura(
            model=config.GROQ_MODEL,
            messages=messaggi_groq + [{
                'role': 'assistant', 'content': messaggio_ia.content,
                'tool_calls': [{'id': c.id, 'type': 'function', 'function': {
                    'name': c.function.name, 'arguments': c.function.arguments or '{}'}}
                    for c in messaggio_ia.tool_calls],
            }] + messaggi_esiti,
            temperature=0.3,
            max_completion_tokens=2048,
            _scadenza=scadenza,
        )
    except LimiteGroq as e:
        # La funzione è già stata eseguita: non perdere il suo risultato.
        testo_risposta = ' '.join(risultati) + ' (Risposta Groq temporaneamente limitata.)'
        cronologia.aggiungi({'role': 'assistant', 'content': testo_risposta})
        return testo_risposta
    except Exception:
        testo_risposta = ' '.join(risultati) + ' (Riepilogo online non disponibile; non ripetere le azioni già completate.)'
        cronologia.aggiungi({'role': 'assistant', 'content': testo_risposta})
        return testo_risposta
    testo_risposta = _pulisci_risposta_testuale(risposta_finale.choices[0].message.content)
    cronologia.aggiungi({"role": "assistant", "content": testo_risposta})
    return testo_risposta


# Comandi gestiti in locale, senza chiamare Groq: sono domande "su noi stessi"
# o richieste di chiusura, la risposta non richiede intelligenza artificiale.
_ALIAS_COMANDI_LOCALI = {
    "esci": ["exit", "quit", "basta", "chiudi", "stop", "arrivederci", "chiudi tutto"],
    "aiuto": ["help", "comandi", "cosa sai fare", "cosa puoi fare", "lista comandi"],
}


# ---------------------------------------------------------------------------
# MODALITÀ VOCALE IN BACKGROUND
# ---------------------------------------------------------------------------
# Aggiunto in coda al prompt SOLO nella modalità vocale: il testo arriva da
# una trascrizione, quindi può contenere errori, e le risposte vengono
# mostrate come notifiche (devono essere brevissime).
SUFFISSO_PROMPT_VOCE = """
MODALITÀ VOCALE (assistente in background):
- Il testo che ricevi è la trascrizione di una frase detta a voce: può
  contenere errori di ascolto. Se una richiesta è ambigua o sembra una
  trascrizione sbagliata, NON eseguire nulla: chiedi di ripetere
- Rispondi con una frase brevissima (verrà mostrata come notifica)
- Se l'utente chiede esplicitamente installazione o aggiornamenti, usa solo
  installa_applicazione o aggiorna_sistema: aprono un terminale separato
  che richiede conferma e password localmente
"""


def avvia_background():
    """Avvia l'assistente come processo in background: resta in attesa di
    un segnale (la scorciatoia da tastiera) e apre il microfono SOLO in quel
    momento. Vedi demone.py."""
    try:
        from .demone import Demone
    except ImportError as e:
        print(f"❌ Mancano le librerie per la voce ({e}).")
        print("   Installa con: pip install -r requirements-voce.txt")
        return

    escluse = set(config.VOCE_FUNZIONI_ESCLUSE)
    schema_voce = [t for t in TOOLS_SCHEMA if t["function"]["name"] not in escluse]
    funzioni_voce = {n: f for n, f in FUNZIONI_DISPONIBILI.items() if n not in escluse}

    cronologia = memoria.Memoria(SYSTEM_PROMPT + SUFFISSO_PROMPT_VOCE)

    from .dettatura import Dettatura
    dettatura = Dettatura()

    def gestore(testo: str) -> str:
        gestore.diagnostica = {'percorso': 'locale', 'azioni': []}
        # Per "scrivi nel file X quello che ti dico", il turno successivo
        # viene scritto ESATTAMENTE come lo trascrive Whisper. Non chiediamo
        # a Groq di ricopiare il testo: evita correzioni e nomi inventati.
        risposta_locale = dettatura.gestisci(testo)
        if risposta_locale is not None:
            gestore.diagnostica['azioni'].append('dettatura')
            cronologia.aggiungi({"role": "user", "content": "[Comando di dettatura vocale]"})
            cronologia.aggiungi({"role": "assistant", "content": risposta_locale})
            return risposta_locale
        return gestisci_richiesta(testo, cronologia, schema_voce, funzioni_voce,
                                  riassumi=False, annullato=demone.arresto_richiesto,
                                  diagnostica=gestore.diagnostica)

    # I nomi dei giochi Steam installati vengono passati a Whisper come
    # "suggerimento": senza, nomi come "Motor Town" possono essere storpiati.
    try:
        giochi = list(tools._giochi_steam_installati().keys())[:25]
    except Exception:
        giochi = []

    try:
        demone = Demone(gestore, vocabolario_extra=giochi)
        demone.esegui()
    finally:
        tools.arresta_catture()
        cronologia.salva_su_disco()


def parse_argomenti():
    parser = argparse.ArgumentParser(description="Assistente per il PC")
    parser.add_argument(
        "--background", action="store_true",
        help="Modalità vocale in background: il microfono si apre solo quando "
             "premi la scorciatoia da tastiera (vedi trigger.py)",
    )
    return parser.parse_args()


def main():
    # La memoria viene creata UNA volta all'avvio e passata ad ogni turno:
    # è lei che tiene tutta la cronologia della sessione corrente.
    cronologia = memoria.Memoria(SYSTEM_PROMPT)

    print("--- Assistente pronto (scrivi 'esci' per uscire, 'aiuto' per la lista comandi) ---")
    try:
        while True:
            testo_utente = input("\nTu: ").strip()

            if not testo_utente:
                continue

            # contenimento=False qui apposta: una richiesta lunga che contiene
            # per caso la parola "aiuto" o "esci" in mezzo non deve essere
            # scambiata per il comando locale (es. "aiutami a trovare...").
            comando_locale = comprensione.interpreta(
                testo_utente, _ALIAS_COMANDI_LOCALI, contenimento=False
            )

            if comando_locale == "esci":
                print("Alla prossima!")
                break

            # "aiuto" è gestito QUI, in locale, senza nemmeno chiamare Groq:
            # è una domanda su noi stessi, la risposta la sappiamo già a priori,
            # non serve un'intelligenza artificiale per rispondere.
            if comando_locale == "aiuto":
                print(tools.lista_comandi())
                continue

            try:
                risposta = gestisci_richiesta(testo_utente, cronologia)
                print(f"Assistente: {risposta}")
            except APIStatusError as e:
                # Distinguiamo DUE casi diversi, che prima mostravano lo
                # stesso messaggio generico (fuorviante): il bug noto
                # tool_use_failed esaurito dopo tutti i retry (raro ma
                # innocuo, va bene un messaggio semplice), oppure un
                # errore DIVERSO di Groq (es. limite di richieste
                # superato, chiave non valida) — quello va mostrato per
                # esteso, altrimenti è impossibile capire cosa sta succedendo.
                codice_errore = None
                try:
                    codice_errore = e.body.get("error", {}).get("code")
                except Exception:
                    pass

                cronologia.rimuovi_ultimo()

                if codice_errore == "tool_use_failed":
                    print("Assistente: Ho avuto un problema a capire la richiesta, puoi riformularla?")
                else:
                    print(f"⚠️  Errore da Groq (codice: {codice_errore or 'sconosciuto'}): {e}")
            except Exception as e:
                cronologia.rimuovi_ultimo()
                print(f"Errore: {e}")
    finally:
        # Qualunque sia il motivo dell'uscita (comando 'esci', Ctrl+C, errore),
        # salviamo comunque la conversazione su disco prima di chiudere.
        tools.arresta_catture()
        cronologia.salva_su_disco()


def run():
    if parse_argomenti().background:
        avvia_background()
    else:
        main()


if __name__ == "__main__":
    run()
