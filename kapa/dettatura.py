"""Dettatura locale in due passaggi, con destinazione esistente e non ambigua.

La richiesta di dettatura viene riconosciuta solo se include un nome di file,
una cartella e un invito esplicito a dettare nel turno successivo. Se la frase
non è abbastanza chiara, il normale gestore Groq può chiedere chiarimenti.
Il testo del turno successivo NON viene riformulato dall'IA.
"""

import re

from . import tools

_CARTELLE = r"scrivania|desktop|documenti|docs|download|downloads|home|immagini|foto|video|musica"
_DESTINAZIONE = r"(?:sulla|sullo|sul|su|in|nella|nei|nel)\s+(?P<cartella>" + _CARTELLE + r")"
_FILE = r"file(?:\s+di\s+testo)?"
_VERBO = r"(?:scrivi|trascrivi|aggiungi|inserisci)"
_DETTA = (
    r"(?:quello\s+che\s+(?:ti\s+)?(?:dico(?:\s+io)?|dir[oò]|detto\s+io|sto\s+per\s+dire)|"
    r"(?:il\s+)?testo\s+che\s+ti\s+detter[oò]|"
    r"ci[oò]\s+che\s+ti\s+dico(?:\s+io)?|"
    r"(?:questa|la\s+seguente)\s+frase|"
    r"(?:questo|il\s+seguente)\s+testo)"
)
# Entrambi gli ordini più frequenti; 'file di testo' è opzionale. Nomi
# non chiari NON vengono indovinati e nomi simili restano distinti.
_SCHEMI = (
    re.compile(
        r"^" + _VERBO + r"(?:\s+(?:del|il)\s+testo)?\s+(?:nel|al|sul|dentro\s+il)\s+"
        + _FILE + r"\s+(?P<nome>.+?)\s+" + _DESTINAZIONE + r"\s+" + _DETTA + r"$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^(?:nel|al|sul|dentro\s+il)\s+" + _FILE + r"\s+(?P<nome>.+?)\s+"
        + _DESTINAZIONE + r"\s+" + _VERBO + r"(?:\s+(?:del|il)\s+testo)?\s+" + _DETTA + r"$",
        flags=re.IGNORECASE,
    ),
)


def estrai_richiesta(testo: str):
    """Ritorna (nome, cartella) oppure None: mai un nome inventato."""
    testo = re.sub(r"\s+", " ", testo.strip().replace(",", " ")).rstrip(".!?;: ")
    for schema in _SCHEMI:
        match = schema.fullmatch(testo)
        if match:
            nome = match.group("nome").strip().strip("'\"“” ")
            if nome:
                return nome, match.group("cartella").lower()
    return None


class Dettatura:
    def __init__(self):
        self._destinazione = None

    def gestisci(self, testo: str):
        """Risposta locale, o None per lasciare intervenire il gestore IA."""
        if self._destinazione is not None:
            if testo.strip().casefold().rstrip("!., ") in ("annulla dettatura", "annulla la dettatura"):
                self._destinazione = None
                return "Dettatura annullata: non ho scritto nulla."
            nome, cartella = self._destinazione
            self._destinazione = None  # mai lasciare lo stato pendente dopo la scrittura
            return tools.scrivi_file(nome, testo, cartella)

        destinazione = estrai_richiesta(testo)
        if destinazione is not None:
            nome, cartella = destinazione
            percorso, errore = tools._percorso_file_esistente(nome, cartella)
            if errore:
                return errore
            # Il nome è quello RISOLTO (estensione compresa), non quello
            # ipotizzato da Whisper. Non selezioniamo file simili.
            self._destinazione = (percorso.name, cartella)
            return (f"Pronto. Detta il testo da aggiungere a '{percorso.name}'. "
                    "Per annullare, di' 'annulla dettatura'.")
        return None
