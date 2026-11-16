# Prima prova in VM — Kapa v0.1.0 Alpha

Questa versione contiene le funzioni aggiornate, incluse Google e OBS.
Per questa prima prova lascia inutilizzati screenshot, registrazioni e replay:
non occorre installare GPU Screen Recorder, OBS o strumenti screenshot.
Le relative funzioni non sono disabilitate: semplicemente non richiederle.

## Installazione

1. Usa una VM Linux con desktop grafico e connessione Internet. Per dettare,
   rendi disponibile il microfono alla VM; puoi iniziare anche da terminale.
2. Estrai tutto lo ZIP in una posizione stabile nella home della VM.
3. Apri il terminale nella cartella estratta ed esegui `bash installa.sh`
   come utente normale. I messaggi sugli strumenti video assenti non impediscono
   di provare le altre funzioni.
4. Apri il file nascosto `.env` nella cartella estratta e inserisci la tua
   `GROQ_API_KEY`. Non ci sono chiavi precompilate. YouTube e OBS sono facoltativi.
5. Avvia Kapa dal menu applicazioni o con doppio clic su `Kapa.desktop`.
   Il primo avvio vocale richiede Internet per scaricare Whisper Small.

Per i dettagli, leggi prima README.md; COSA_SA_FARE.md è accanto al README.
L'installer prepara l'ambiente Python nella VM, senza usare quello del PC origine.

## Prove iniziali, senza catture dello schermo

- Avvio GUI, riduzione della finestra, richiamo e chiusura dal tray.
- «Metti il volume al trenta per cento» (agisce sull'audio della VM).
- Play/pausa con un lettore MPRIS aperto nella VM, se disponibile.
- «Apri Firefox», se Firefox è installato nella VM.
- «Cerca su Google ricette per la pizza» e ricerca YouTube senza chiave YouTube.
- Creazione, lettura, aggiunta di testo e copia di soli file di prova.
- Copia e lettura degli appunti della VM.
- Promemoria breve, tenendo Kapa aperto fino alla notifica.
- «Parla ora», trascrizione e scorciatoia, se il microfono è disponibile.

Il sistema di virtualizzazione può intercettare le scorciatoie o non inoltrare
il microfono: controlla anche le impostazioni della VM. Per ora lascia fuori
installazioni e aggiornamenti tramite assistente: non servono per questa prova.

## Verifica del pacchetto e test isolati

Dalla cartella estratta:

```bash
sha256sum --check MANIFEST.sha256
.venv/bin/python -B tests/run_safe_tests.py
```

I test isolati non usano chiavi reali, microfono o catture reali dello schermo.
Per annotare risultati e problemi usa docs/SCHEDA_TEST_FEDORA.md, indicando
anche distribuzione e programma di virtualizzazione. Segna screenshot e video
come «non provati». Non allegare chiavi, `.env` o conversazioni personali.

## Contenuto distribuibile

Lo ZIP è costruito da una lista esplicita di file pubblici. Esclude `.env`,
conversazioni, log, vocabolario personale, ambienti Python, cache e collegamenti
con i percorsi del PC origine. Include esempi di configurazione vuoti e un
manifest SHA256. Le dipendenze e il modello vocale vengono scaricati nella VM.
