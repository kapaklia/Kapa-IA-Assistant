# memoria.py
#
# Fino ad ora, ogni volta che scrivevi qualcosa, main.py ripartiva da zero:
# non si ricordava la frase precedente. Questo file risolve la cosa: tiene
# una lista di messaggi che cresce turno dopo turno (finché il programma
# resta aperto), così se dici "crea un file note.txt" e poi "scrivici dentro
# anche la data di oggi", il secondo messaggio ha ancora il contesto del primo.
#
# Per evitare che la lista cresca all'infinito (e che ogni chiamata a Groq
# diventi più lenta e costosa), teniamo solo gli ultimi N scambi: quelli più
# vecchi vengono scartati automaticamente, ma il messaggio di "istruzioni
# iniziali" (system prompt) resta sempre in cima.
#
# Alla chiusura del programma, la conversazione viene salvata su disco in un
# file JSON dentro la cartella conversazioni/ — utile se vuoi rileggere cosa
# hai chiesto, ma NON viene più ricaricata all'avvio successivo: ogni sessione
# parte "fresca". Se un giorno vuoi che si ricordi anche tra un avvio e
# l'altro, è una scelta che si può cambiare qui dentro.

import json
import datetime
import os
import uuid
from pathlib import Path
from .app_paths import data_dir

MAX_MESSAGGI = 30  # oltre questa soglia, i messaggi più vecchi vengono scartati

CARTELLA_CONVERSAZIONI = data_dir() / "conversazioni"


class Memoria:
    def __init__(self, system_prompt: str):
        self._system_message = {"role": "system", "content": system_prompt}
        self.messaggi = [self._system_message]
        self._avviata_alle = datetime.datetime.now()

    def aggiungi(self, messaggio):
        """Aggiunge un messaggio (dell'utente, dell'assistente, o di un tool)
        alla cronologia, e pulisce quelli troppo vecchi se serve."""
        self.messaggi.append(messaggio)
        self._pulisci_se_troppo_lunga()

    def rimuovi_ultimo(self):
        if len(self.messaggi) > 1:
            self.messaggi.pop()

    def _ruolo_di(self, messaggio) -> str:
        """Ricava il 'role' di un messaggio, sia che sia un dict semplice
        (quelli che creiamo noi) sia un oggetto vero e proprio della
        libreria Groq (i messaggi assistant con tool_calls arrivano così,
        non come dict — .get() su quelli romperebbe)."""
        if isinstance(messaggio, dict):
            return messaggio.get("role")
        return getattr(messaggio, "role", None)

    def _pulisci_se_troppo_lunga(self):
        if len(self.messaggi) <= MAX_MESSAGGI + 1:  # +1 per il system prompt
            return

        corpo = self.messaggi[1:]
        taglio = len(corpo) - MAX_MESSAGGI

        # IMPORTANTE: il messaggio che resta per primo dopo il taglio non
        # deve mai essere un "tool" (risposta tecnica di una funzione):
        # vorrebbe dire che il messaggio "assistant" che l'aveva richiesta
        # è stato tagliato via, lasciando un pezzo orfano senza contesto —
        # cosa che confonde il modello nelle richieste successive (può
        # essere proprio l'origine di risposte a vuoto o inaffidabili).
        while taglio < len(corpo) and self._ruolo_di(corpo[taglio]) == "tool":
            taglio += 1

        corpo = corpo[taglio:]
        self.messaggi = [self._system_message] + corpo

    def salva_su_disco(self):
        """Scrive la conversazione in un file JSON, uno per sessione.
        Un file tipico pesa pochi KB: anche usandolo ogni giorno per anni
        il totale resta trascurabile (parliamo di testo, non di media)."""
        try:
            CARTELLA_CONVERSAZIONI.mkdir(parents=True, exist_ok=True, mode=0o700)
            nome_file = self._avviata_alle.strftime("conversazione_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8] + '.json'
            percorso = CARTELLA_CONVERSAZIONI / nome_file

            serializzabili = []
            for m in self.messaggi:
                if isinstance(m, dict):
                    serializzabili.append(m)
                else:
                    # I messaggi che arrivano da Groq non sono dict semplici:
                    # prendiamo solo le informazioni utili da salvare.
                    serializzabili.append({
                        "role": getattr(m, "role", "assistant"),
                        "content": getattr(m, "content", None),
                    })

            fd = os.open(percorso, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                json.dump(serializzabili, output, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"(non sono riuscito a salvare la conversazione: {e})")
