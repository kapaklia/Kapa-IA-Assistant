# Kapa — prova privata su Fedora KDE

Versione: **0.1.0-alpha.5**. Pacchetto per test privati con installazione
guidata da script shell. Non contiene chiavi, ambiente Python o modello Whisper.

Per l'installazione automatica, estrai lo ZIP in una posizione stabile,
apri un terminale nella cartella estratta ed esegui `bash installa.sh`,
senza sudo davanti. Lo script richiede sudo solo per le dipendenze di sistema.
Poi inserisci la chiave Groq nel file `.env` e avvia Kapa dal menu applicazioni.
Le sezioni seguenti descrivono la procedura manuale alternativa.

## 1. Estrazione

Apri lo ZIP con Ark ed estrai la cartella `Kapa-0.1.0-alpha.5` in una
posizione stabile, per esempio dentro `Applicazioni` nella tua home. Non
eseguirlo direttamente dall'anteprima dello ZIP. Apri Konsole nella cartella
estratta: tutti i comandi seguenti vanno eseguiti da lì, come utente normale.

## 2. Dipendenze Fedora

Verifica la versione Python:

```sh
python3 --version
```

Il codice richiede Python >= 3.10; la disponibilità delle dipendenze va
verificata con l'installazione seguente. Non copiare `.venv` da un altro PC.

Se mancano i pacchetti, installali sul PC di prova:

```sh
sudo dnf install python3 python3-pip pulseaudio-utils libnotify playerctl wl-clipboard xdg-utils xdg-user-dirs spectacle
```

Questo comando installa software; non esegue aggiornamenti di sistema.
Non rimuovere o sostituire PipeWire: vengono usate le sue interfacce PulseAudio.
Su una sessione X11, per gli appunti serve anche:

```sh
sudo dnf install xclip
```

Riferimenti ufficiali: [pulseaudio-utils](https://packages.fedoraproject.org/pkgs/pulseaudio/pulseaudio-utils/),
[Spectacle](https://packages.fedoraproject.org/pkgs/spectacle/spectacle/),
[wl-clipboard](https://packages.fedoraproject.org/pkgs/wl-clipboard/wl-clipboard/),
[playerctl](https://packages.fedoraproject.org/pkgs/playerctl/).

## 3. Ambiente Python locale

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-voce.txt -r requirements-gui.txt
.venv/bin/python scripts/setup_assistant.py --check
```

Serve Internet per scaricare dipendenze e, al primo avvio vocale, Whisper
Small. Le dipendenze non sono tutte bloccate a versioni precise: questa alpha
serve anche a verificare l'installazione su un secondo PC. Se pip fallisce,
conserva il messaggio d'errore senza includere dati personali.

## 4. Chiave Groq

Nel gestore file abilita la visualizzazione dei file nascosti. Crea nella
cartella del progetto un file `.env`, copiando il modello `.env.example`.
Aprilo in un editor e inserisci la chiave Groq del PC di prova dopo
`GROQ_API_KEY=`. `YOUTUBE_API_KEY` può rimanere vuota: YouTube ripiegherà sulla
ricerca nel browser. Proteggi il file dopo averlo creato:

```sh
chmod 600 .env
```

Non inviare `.env` con i risultati dei test. Il pacchetto non contiene né
riutilizza la chiave del PC di origine.

## 5. Test sicuri e primo avvio

```sh
.venv/bin/python -B tests/run_safe_tests.py
.venv/bin/python gui.py
```

La suite usa configurazione sintetica e file temporanei; non usa la chiave
Groq, il microfono o il desktop reale. I test disponibili sono eseguiti dal
runner. Le prove reali seguenti vanno
eseguite separatamente.

Aprendo la GUI il demone parte automaticamente: attendi Whisper Small. Il
microfono rimane chiuso fino a **Parla ora** o alla scorciatoia.

## 6. Scorciatoia e collegamento nel menu

Con l'assistente attivo premi **Scorciatoie** e completa la richiesta nativa
di KDE. Se il Portal non è disponibile, usa le istruzioni del dialogo e copia
il comando proposto nelle scorciatoie personalizzate di KDE. Deve richiamare
il Python della `.venv` di questo PC, non un percorso del PC di origine.

Per aggiungere il collegamento al menu applicazioni:

```sh
.venv/bin/python scripts/setup_assistant.py --launcher
```

Mantieni inizialmente disattivato l'avvio automatico all'accesso a Linux. Non copiare servizi
systemd già configurati sull'altro PC. Il launcher conserva il percorso
attuale: se sposti il progetto, il collegamento deve essere riconfigurato.

## 7. Sequenza di prova consigliata

Usa una cartella e file di prova, senza documenti personali.

| Prova | Risultato atteso |
|---|---|
| Apri Kapa / Chiudi dal tray | Il demone parte e termina; il microfono non resta aperto |
| Parla ora / scorciatoia | Ascolto soltanto su richiesta, poi chiusura |
| «Metti pausa» / «metti play» | Controllo di un player MPRIS già aperto |
| «Metti il volume al trenta per cento» | Livello al 30% |
| «Alza il volume del venti per cento» | Incremento, con massimo al 100% |
| Creare e aggiungere testo a un file di prova | Nessuna sovrascrittura del file esistente |
| Screenshot semplice | Monitor principale indicato dalla sessione |
| Screenshot del monitor 1 e del monitor 2 | Monitor nell'ordine rilevato, se presenti |
| Screenshot di tutti i monitor | Desktop completo |
| Screenshot della finestra attiva | Finestra attiva, se supportata dal backend |
| Aprire un'applicazione / ricerca YouTube | Avvio dell'app o del browser |
| Promemoria di un minuto | Notifica mantenendo il motore aperto |

La registrazione richiede **GPU Screen Recorder**, installato separatamente
da una fonte appropriata per il tuo Fedora e la tua GPU. Non è incluso e non
è necessario per le altre prove. Se già disponibile, prova una registrazione
breve e il suo arresto; il target si può configurare con `IA_GSR_TARGET`.

Per questo primo giro non è necessario provare installazioni o aggiornamenti
tramite assistente. Le uniche operazioni amministrative disponibili rimangono
installazione software e aggiornamento con conferma nel terminale; su Nobara
l'aggiornamento usa `nobara-sync cli`.

## 8. Limiti noti e risultati

- Le scale monitor differenti possono impedire il ritaglio con alcuni backend.
- Il backend screenshot XDG Portal non è ancora implementato.
- Il comportamento dipende da GPU, driver, sessione e versioni dei pacchetti.
- I promemoria si perdono chiudendo il motore; Whisper resta Small su CPU.

I nuovi dati locali sono in `${XDG_DATA_HOME:-~/.local/share}/ia-assistant`.
Non inviare interi log, conversazioni o registrazioni. Per segnalare un
problema compila `docs/SCHEDA_TEST_FEDORA.md` e aggiungi soltanto l'errore pertinente,
senza chiavi o contenuti personali. Per riavviare dopo una prova usa
«Chiudi» dal tray e apri nuovamente Kapa.

L'integrità del pacchetto si può verificare dalla cartella estratta con:

```sh
sha256sum --check MANIFEST.sha256
```
