# Kapa

Versione iniziale **v0.1.0 Alpha**. Per la prima prova senza catture dello schermo,
segui [PROVA_IN_VM.md](PROVA_IN_VM.md).

Assistente desktop per Linux, in italiano. Puoi scrivere le richieste oppure
dettarle: Kapa trascrive la voce sul PC e mostra le risposte per iscritto.

Per iniziare segui le sezioni **1–3**, poi consulta le guide delle funzioni
che vuoi usare. L'elenco completo è in [COSA_SA_FARE.md](COSA_SA_FARE.md),
nella cartella principale, accanto a questo README. Il pulsante **Guida**
dell'app apre lo stesso file.

## 1. Requirements e installazione

### Cosa serve

Servono Linux con una sessione grafica, Python **3.10 o successivo** e Internet
per installare le dipendenze. La modalità vocale scarica Whisper Small al
primo utilizzo. Per avviare il motore serve una chiave Groq, da inserire nel
passaggio 2. Non avviare Kapa come root.

| File | A cosa serve |
|---|---|
| `requirements.txt` | Motore delle richieste, configurazione e collegamento OBS |
| `requirements-voce.txt` | Trascrizione vocale locale con Whisper |
| `requirements-gui.txt` | Interfaccia desktop e scorciatoie tramite Portal |
| `requirements-dev.txt` | Strumenti di test facoltativi per lo sviluppo |

I requirements installano librerie Python. Gli strumenti di sistema per
audio, multimedia, screenshot e registrazioni sono separati.

### Installazione guidata

Estrai tutto lo ZIP in una posizione stabile nella tua home. Apri un
terminale nella cartella che contiene questo README ed esegui:

```bash
bash installa.sh
```

Lo script installa i pacchetti di sistema su Fedora/Nobara e
Debian/Ubuntu/Mint, crea l'ambiente `.venv`, installa i tre requirements
necessari all'app e aggiunge Kapa al menu. Chiede la password tramite sudo
quando serve per i pacchetti di sistema; esegui lo script come utente normale.
Crea `.env` se manca e conserva le configurazioni esistenti.

GPU Screen Recorder, OBS e gli strumenti screenshot vanno installati
separatamente per usare le rispettive funzioni. Per altre distribuzioni,
prepara le dipendenze di sistema e usa `bash installa.sh --skip-system`.

### Installazione manuale alternativa

Se hai già preparato le dipendenze di sistema, dalla cartella principale:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-voce.txt -r requirements-gui.txt
.venv/bin/python scripts/setup_assistant.py --check
```

Per i pacchetti di sistema e una procedura dettagliata consulta la
[guida Fedora KDE](docs/ISTRUZIONI_FEDORA_KDE.md). Il controllo `--check`
mostra anche gli strumenti opzionali mancanti: servono solo alle funzioni
che li utilizzano.

Dopo aver configurato le chiavi nel passaggio 2, genera i collegamenti:

```bash
.venv/bin/python scripts/installa_launcher.py
.venv/bin/python scripts/installa_launcher.py --local
```

Non spostare la cartella dopo l'installazione: i collegamenti ne usano il
percorso. Se la sposti, rigenera i collegamenti dalla nuova posizione.

### Aggiornare le dipendenze di un'installazione esistente

Chiudi Kapa dal tray, poi dalla cartella principale esegui:

```bash
.venv/bin/python -m pip install -r requirements.txt -r requirements-voce.txt -r requirements-gui.txt
.venv/bin/python scripts/setup_assistant.py --check
```

Questi comandi usano l'ambiente `.venv` creato dall'installer. Se avvii Kapa
con un altro ambiente Python, usa lo stesso interprete anche per installare
le dipendenze. Infine riapri Kapa.

## 2. Configurazione iniziale: file .env e chiavi

Il file **`.env`** deve stare nella cartella principale, accanto a `gui.py`
e `installa.sh`, fuori da `.venv`. Abilita la visualizzazione dei file
nascosti nel gestore file per trovarlo. Se manca, crea una copia di
`.env.example` chiamata `.env`; se esiste già, modifica quello.

```dotenv
GROQ_API_KEY=INSERISCI_LA_TUA_CHIAVE_GROQ
YOUTUBE_API_KEY=
OBS_PORT=4455
OBS_PASSWORD=
```

Sostituisci il segnaposto Groq con la chiave reale. Scrivi una voce per riga,
senza spazi intorno a `=`. YouTube e OBS sono facoltativi: puoi lasciare
vuote le password e le chiavi che non usi.

| Voce | Quando serve |
|---|---|
| `GROQ_API_KEY` | Necessaria per avviare il motore e interpretare le richieste tramite Groq |
| `YOUTUBE_API_KEY` | Facoltativa, per cercare e aprire direttamente un video YouTube |
| `OBS_PORT` | Porta del server WebSocket locale OBS; predefinita `4455` |
| `OBS_PASSWORD` | Password del server WebSocket OBS, se vuoi usare OBS |

Salva il file e riavvia Kapa dopo le modifiche. Non condividere `.env`:
contiene credenziali personali ed è escluso dal pacchetto di distribuzione.

## 3. Primo avvio e comandi dell'interfaccia

Apri **Kapa.desktop** con doppio clic oppure cerca **Kapa** nel menu
applicazioni. Per avviarlo da terminale:

```bash
.venv/bin/python gui.py
```

Il motore parte con la finestra. Al primo avvio vocale attendi il download
e il caricamento di Whisper. Il microfono resta chiuso fino a **Parla ora**
o alla scorciatoia. Premi **Scorciatoie** e segui il dialogo del desktop
per configurare il tasto.

Prova «metti il volume al trenta per cento». La finestra mostra la frase
trascritta, l'azione e il risultato. Le risposte sono scritte, senza sintesi
vocale.

Rimpicciolendo la finestra rimane il microfono. Altri clic sull'avviatore
richiamano la finestra già aperta. La X la nasconde nel tray, se disponibile;
per uscire del tutto scegli **Chiudi** dal menu del tray. Senza tray, la X
chiude finestra e motore.

Per usare solo il terminale:

```bash
.venv/bin/python main.py
```

Scrivi «aiuto» per vedere i comandi. Per il solo motore in background usa
`.venv/bin/python main.py --background`. Per altre indicazioni consulta
[Avvio con doppio clic](docs/AVVIO_GUI.md).

## 4. Audio e dettatura

La voce viene trascritta localmente con Whisper Small. Servono le dipendenze
vocali e gli strumenti audio di sistema, installati dalla procedura guidata.
Se non viene registrata la voce, verifica prima il microfono selezionato e i
livelli nelle impostazioni audio del desktop.

Puoi dettare testo per un file: indica il file esistente, poi detta cosa
aggiungere quando Kapa lo chiede. «Annulla dettatura» interrompe l'operazione.
Il testo viene aggiunto senza sostituire il contenuto precedente.

Per aiutare il riconoscimento di nomi ricorrenti, usa
`vocabolario_personale.example.txt` come modello per
`vocabolario_personale.txt`, nella cartella principale.

## 5. Multimedia: volume, musica e video

Serve `playerctl` per controllare i lettori compatibili con MPRIS e `pactl`
per il volume di sistema. L'installer prepara questi strumenti.

| Richiesta | Risultato |
|---|---|
| «Metti il volume al trenta per cento» | Imposta il volume al 30% |
| «Alza il volume del venti per cento» | Aumenta di 20 punti, fino al massimo del 100% |
| «Metti pausa» / «metti play» | Controlla il lettore selezionato automaticamente |
| «Prossima traccia su Spotify» | Usa il lettore indicato |
| «Ripeti la traccia» / «attiva riproduzione casuale» | Usa la funzione se supportata dal lettore |

Kapa dà priorità ai browser rilevati come lettori, prima in riproduzione,
poi in pausa. Se non trova browser, sceglie tra gli altri lettori disponibili.
Puoi sempre specificarne uno: «metti play su Firefox» o «metti pausa su VLC».
Un browser senza una sessione multimediale rilevabile non compare tra i lettori.

## 6. Internet: Google e YouTube

### Ricerca Google

«Cerca su Google ricette per la pizza» apre i risultati nel browser
predefinito. Non serve una chiave API Google. Scegli tu i risultati da aprire:
Kapa non legge né riassume le pagine. L'interpretazione della richiesta usa Groq.

### Ricerca e riproduzione YouTube

«Cerca jazz su YouTube» apre la pagina dei risultati, senza chiave YouTube.
Per «metti [titolo e artista] su YouTube», Kapa può invece trovare e aprire
direttamente il video usando `YOUTUBE_API_KEY`.

Per questa funzione abilita **YouTube Data API v3** nel tuo progetto Google
Cloud e inserisci la chiave nel `.env`. Se manca, non funziona o la quota è
esaurita, Kapa apre la ricerca e scegli tu il video. La riproduzione automatica
dipende dalle impostazioni del browser.

## 7. Video: registrazioni e replay

### Scelta tra GPU Screen Recorder e OBS

| Disponibilità o richiesta | Programma usato |
|---|---|
| GPU Screen Recorder installato | GSR come predefinito |
| GSR assente | OBS |
| Entrambi installati, richiesta generica | GSR |
| Richiesta esplicita «con OBS» | OBS |

Se GSR è installato ma dà un errore, Kapa lo segnala senza passare
automaticamente a OBS. «Ferma la registrazione», «salva il replay» e
«ferma il buffer replay» seguono la cattura avviata da Kapa.

### GPU Screen Recorder

Installa separatamente GPU Screen Recorder per la tua distribuzione e GPU:
Kapa usa il comando `gpu-screen-recorder`. Prova:

- «Registra lo schermo», poi «ferma la registrazione».
- «Fai un video di dieci secondi»: si ferma automaticamente.
- «Avvia il buffer replay da sessanta secondi», poi «salva il replay».
- «Ferma il buffer replay» quando hai finito.

La durata delle registrazioni a tempo e del buffer GSR va da 1 a 600 secondi.
I video GSR vengono salvati nella cartella Video rilevata dal sistema, in
MP4 con H.264 e AAC. La CLI usa le impostazioni di Kapa, senza ereditare le
preferenze della GUI di GSR.

Per scegliere il monitor, consulta `gpu-screen-recorder --list-monitors`
e imposta `IA_GSR_TARGET` nel `.env` con il nome riportato. Il valore
predefinito è `screen`. Audio, framerate e cartella sono in `kapa/config.py`
(`GSR_AUDIO`, `GSR_FRAMERATE`, `GSR_CARTELLA_OUTPUT`). Riavvia dopo le modifiche.

### Preparare OBS

1. Installa OBS **28 o successivo**, nativo oppure Flatpak (`com.obsproject.Studio`).
2. Apri OBS e configura le sorgenti video e audio, il formato e la cartella di registrazione.
3. In **Strumenti → Impostazioni server WebSocket** abilita il server e copia la password.
4. Inserisci la password in `OBS_PASSWORD` nel `.env`. Se la porta è diversa da `4455`, modifica anche `OBS_PORT`.
5. Assicurati di aver aggiornato i requirements del passaggio 1: il collegamento richiede `websocket-client`.
6. Riavvia Kapa e prova «registra lo schermo con OBS», poi «ferma la registrazione».

OBS registra la **scena attuale**, con il proprio audio e le proprie
impostazioni di output. Kapa prova ad aprire OBS se il server locale non
risponde; completa prima la configurazione iniziale dell'app.

Per il replay abilita e configura il buffer nelle impostazioni di output
di OBS. Poi chiedi «avvia il buffer replay con OBS» e «salva il replay».
La durata è quella configurata in OBS: omettila nel comando. Anche il nome
dei video viene deciso da OBS; nomi personalizzati e durate replay esplicite
vengono segnalati come non supportati, senza modificare le impostazioni.

Kapa non prende in carico catture OBS già avviate manualmente. Alla chiusura
prova a fermare le proprie catture e lascia aperto OBS. Se il collegamento
si interrompe, controlla in OBS se la cattura è ancora attiva.

Il collegamento segue il [protocollo ufficiale OBS WebSocket 5](https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md).

## 8. Screenshot

Installa uno strumento compatibile con il desktop: Spectacle su KDE, oppure
uno dei backend supportati come Grim su compositor wlroots, GNOME Screenshot
o Scrot, secondo la sessione in uso. L'installer segnala se non trova backend.

Prova «fai uno screenshot», «fai uno screenshot del monitor due», «fai uno
screenshot di tutti i monitor» o «fai uno screenshot della finestra attiva».
La disponibilità delle catture dipende dal backend e dal desktop. Scale diverse
tra monitor possono impedire alcuni ritagli; il backend screenshot XDG Portal
non è ancora implementato.

## 9. Applicazioni e gestione del sistema

«Apri Firefox», «chiudi VLC» e «ho GIMP installato?» permettono di avviare,
chiudere o verificare un'app. Puoi anche chiedere di cercare un programma
nei repository, installarlo o aggiornare il sistema.

Installazioni e aggiornamenti aprono un terminale per conferma ed eventuale
password. Inserisci la password nel terminale, senza dettarla a Kapa.
Le procedure dipendono dalla distribuzione; su Nobara l'aggiornamento usa
`nobara-sync cli`.

## 10. File, appunti e promemoria

Puoi creare, leggere, cercare, copiare, spostare e rinominare file e cartelle.
Esempi: «crea un file note sul desktop», «cerca il file fattura» oppure
«aggiungi questo testo al file note». La scrittura aggiunge contenuto a file
esistenti; la sostituzione completa non è disponibile.

L'eliminazione dei file e lo svuotamento del cestino sono disponibili solo
in modalità testuale. Per i file Kapa non chiede password amministrative.

«Copia questo testo negli appunti» e «leggi gli appunti» usano `wl-copy` e
`wl-paste` su Wayland oppure `xclip` su X11. «Ricordami tra un minuto di…»
mostra una notifica: Kapa deve restare attivo, perché i promemoria non vengono
conservati alla chiusura.

## 11. Problemi comuni e verifiche

| Problema | Cosa controllare |
|---|---|
| Il motore non parte | `GROQ_API_KEY` nel `.env` e dipendenze nell'ambiente Python usato per l'avvio |
| La GUI non si apre | Requirements GUI e risultato di `scripts/setup_assistant.py --check` |
| Non sente la voce | Microfono, livelli del desktop e dipendenze vocali |
| Play o pausa non funzionano | `playerctl`, lettore già aperto e sessione MPRIS disponibile |
| OBS non si collega | Server WebSocket abilitato, password, porta e `websocket-client` |
| GSR si chiude subito | Messaggio restituito, monitor selezionato e compatibilità GPU/driver |
| Screenshot non disponibile | Backend installato e compatibilità con la sessione grafica |
| Scorciatoia non disponibile | Pulsante Scorciatoie e istruzioni del desktop nel dialogo |

Le richieste locali riconosciute, come play, volume e registrazione, evitano
la chiamata a Groq. Le richieste complesse usano Groq e richiedono Internet;
la trascrizione vocale resta sul PC. La lingua attuale è l'italiano.

Prove pratiche confermate su Nobara KDE, Ubuntu GNOME e Linux Mint Cinnamon.
Fedora e Arch non sono ancora completamente verificati; hardware e backend
richiedono prove specifiche. Le dipendenze Python non hanno
ancora un lockfile.

## 12. Dove trovare file e documentazione

| Percorso | Contenuto |
|---|---|
| `README.md` | Installazione, configurazione e guide per funzione |
| `COSA_SA_FARE.md` | Elenco delle capacità e miniguide |
| `.env` | Chiavi e configurazione personale |
| `vocabolario_personale.txt` | Parole personali per la trascrizione |
| `kapa/` | Codice dell'applicazione e `config.py` |
| `assets/` | Icone, sfondo e vocabolario comune |
| `docs/` | Guide di dettaglio e schede di prova |
| `scripts/` | Setup, diagnostica e preparazione del pacchetto |
| `tests/` | Test isolati |

I nuovi log e le conversazioni sono in
`${XDG_DATA_HOME:-~/.local/share}/ia-assistant`. La memoria di conversazione
riparte da zero al riavvio. Le configurazioni personali restano nella
cartella principale.

Altre guide: [Cosa sa fare](COSA_SA_FARE.md),
[Avvio con doppio clic](docs/AVVIO_GUI.md),
[Prova su Fedora KDE](docs/ISTRUZIONI_FEDORA_KDE.md) e
[Scheda risultati](docs/SCHEDA_TEST_FEDORA.md).

## 13. Sviluppo e pacchetto di distribuzione

Dalla cartella principale, usando l'ambiente del progetto:

```bash
.venv/bin/python -B tests/run_safe_tests.py
```

I test usano configurazione sintetica e file temporanei: non aprono il
microfono e non inviano richieste online. Per la suite pytest facoltativa:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -B -m pytest -p no:cacheprovider tests
```

Per generare la bozza locale del pacchetto Alpha:

```bash
.venv/bin/python scripts/package_private.py
```

Il pacchetto usa un elenco esplicito di file pubblici e genera esempi vuoti.
Licenza del codice Kapa: **GNU GPLv3-only**, identificatore `GPL-3.0-only`.
Il testo completo è in [LICENSE](LICENSE); non si concede automaticamente l’uso
di versioni successive. Il programma è fornito senza garanzie. Prima della
pubblicazione completa la verifica dei diritti degli asset e dei file distribuiti:
chiavi, conversazioni, log, registrazioni e ambienti Python sono personali.
Per stampare un modello di servizio utente, senza installarlo, usa
`.venv/bin/python scripts/setup_assistant.py --print-service`.
