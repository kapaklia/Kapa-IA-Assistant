# Riordino del progetto

Il codice ora è nel pacchetto `kapa/`, le guide in `docs/`, le risorse in
`assets/` e i comandi di servizio in `scripts/`. Gli ingressi `gui.py`,
`main.py` e `trigger.py` rimangono nella cartella principale per conservare
avviatore, servizio e scorciatoie. Import interni e percorsi sono aggiornati.

Chiavi, vocabolario personale, log e diagnostica esistenti non vengono
spostati. Il caricamento di `.env` usa la cartella principale anche quando
il programma viene avviato da un'altra directory. La lingua resta italiana.

## Note storiche dell'audit precedente

Applicati controlli sui percorsi, lettura limitata, trasferimenti esclusivi,
chiusura esatta dei processi, validazione locale delle function call, esiti
nel riepilogo Groq, deadline online, metriche aggregate e conservazione degli
esiti in caso di errore del riepilogo. Implementata selezione screenshot
dinamica e percorso locale per le richieste semplici. Aggiornati arresto dei
worker/GSR, validazione timer/replay, appunti X11/Wayland, volume limitato,
fallback scorciatoie, polling GUI e percorsi privati XDG.

Nuovi moduli: app_paths.py, tool_validation.py, screen_capture.py,
setup_assistant.py. Nessuna installazione, modifica root o lettura di dati
privati è necessaria per i test. Whisper operativo rimane Small.

Restano da validare: hardware audio e GPU, monitor fisici, scale miste,
backend Portal reali, GNOME Wayland, sessione systemd e installazioni pulite
su Nobara/Fedora, Debian/Ubuntu e Arch. I controlli amministrativi originali
sono conservati, incluso nobara-sync cli.

File operativi modificati: config.py, main.py, tools.py, demone.py, stt.py,
memoria.py, comandi_rapidi.py, gui.py, gui_backend.py, shortcut_status.py,
trigger.py, scripts/installa_launcher.py e confronta_whisper.py.
Aggiornati i test test_patch.py, test_hotkey_portal.py e test_shortcut_status.py;
aggiunti safe_config.py, conftest.py, run_safe_tests.py, test_regressions.py e
test_gui_safe.py. Aggiunti requirements-dev.txt e README.md; riallineate le
indicazioni principali di COSA_SA_FARE.md e marcate come storiche le vecchie note.

Verifica: suite isolata di 67 test superata, inclusa GUI offscreen con controller
fittizio e ritaglio di PNG sintetici. Pytest non è installato nell'ambiente:
i vecchi test scritti come funzioni pytest non sono stati eseguiti. Nessuna
dipendenza è stata installata. Lo SDK Groq locale supporta i parametri di timeout
e max_completion_tokens usati. Parsing AST valido per 36 file Python.

Lavori successivi: backend screenshot XDG Portal, gestione delle scale miste
per backend che non selezionano direttamente l'output, parser desktop più
completo, promemoria persistenti opzionali, retention conversazioni, lockfile
verificati e scelta della licenza. Non vengono dichiarati risolti dai test
simulati. Vedere README.md per i limiti e i comandi di verifica.
