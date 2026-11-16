# comprensione.py
#
# PERCHÉ QUESTO FILE ESISTE
# Il codice, per natura, vuole confronti esatti: "if testo == 'si'". Ma le
# persone non parlano così: dicono "sì", "certo", "ok", "vai", o scrivono
# "scrivania" con un typo come "scrivanie". Ogni "if testo == 'parola'"
# sparso nel codice è un punto fragile — funziona solo se indovini esattamente
# come l'utente scriverà quella cosa.
#
# Questo file fa da "cuscinetto" tra il linguaggio libero dell'utente e le
# parole esatte che il resto del codice si aspetta. Si usa così:
#
#   ALIAS = {
#       "si": ["sì", "s", "yes", "ok", "va bene", "certo", "procedi"],
#       "no": ["n", "no grazie", "annulla", "stop"],
#   }
#   interpreta("vabbene", ALIAS)   -> "si"   (sinonimo riconosciuto)
#   interpreta("scrivanie", {...cartelle...})  -> "scrivania" (typo tollerato)
#
# Un solo posto dove vive questa logica: se un giorno vuoi che riconosca
# anche il dialetto o l'inglese maccheronico, la aggiungi qui e si applica
# automaticamente a tutti i punti del progetto che la usano.

import difflib
import re
import unicodedata


def normalizza(testo: str) -> str:
    """Minuscolo, senza spazi ai lati, senza accenti, senza punteggiatura —
    così 'più' e 'piu', 'sì' e 'si', o 'certo!' e 'certo' contano uguali."""
    testo = testo.strip().lower()
    testo = unicodedata.normalize("NFKD", testo)
    testo = "".join(carattere for carattere in testo if not unicodedata.combining(carattere))
    testo = "".join(carattere for carattere in testo if carattere.isalnum() or carattere.isspace())
    return testo.strip()


def _contiene_come_parola(testo: str, frase: str) -> bool:
    """True se 'frase' compare dentro 'testo' come parola/e intere, con i
    bordi giusti — non come pezzo di un'altra parola diversa. Es. 'su' in
    'alza su' conta, 'su' dentro 'sushi' no. Permette di riconoscere
    'prossima' anche dentro 'prossima traccia', senza dover elencare a
    mano ogni possibile frase con parole extra intorno."""
    if not frase:
        return False
    pattern = r"(?<!\w)" + re.escape(frase) + r"(?!\w)"
    return re.search(pattern, testo) is not None


def interpreta(testo_utente: str, alias: dict, soglia: float = 0.75, contenimento: bool = True):
    """
    alias: dizionario {"nome_canonico": ["sinonimo1", "sinonimo2", ...]}
    Ritorna il nome_canonico più adatto a quello che ha scritto l'utente,
    oppure None se non trova nulla di sufficientemente simile.

    Come funziona, in ordine:
    1. Corrispondenza ESATTA sull'intera frase (anche tra i sinonimi)
    2. Se 'contenimento' è attivo: la frase CONTIENE per intero uno dei
       sinonimi conosciuti, anche con altre parole intorno (es. "prossima
       traccia" trova "prossima" anche se non è scritto da solo)
    3. Corrispondenza SIMILE sull'intera frase (tollera i typo)

    'contenimento' va disattivato solo dove serve più prudenza — es. i
    comandi locali ("esci"/"aiuto") o la conferma sì/no, dove una frase
    lunga potrebbe contenere per caso una parola "giusta" senza che
    l'utente intendesse davvero quel comando.
    """
    testo_norm = normalizza(testo_utente)

    parola_a_canonico = {}
    for canonico, sinonimi in alias.items():
        parola_a_canonico[normalizza(canonico)] = canonico
        for sinonimo in sinonimi:
            parola_a_canonico[normalizza(sinonimo)] = canonico

    if testo_norm in parola_a_canonico:
        return parola_a_canonico[testo_norm]

    if contenimento:
        # Ordiniamo dalla parola/frase più lunga alla più corta: se "volume
        # su" e "su" sono entrambi sinonimi, preferiamo il match più specifico.
        for parola in sorted(parola_a_canonico.keys(), key=len, reverse=True):
            if _contiene_come_parola(testo_norm, parola):
                return parola_a_canonico[parola]

    candidati = difflib.get_close_matches(
        testo_norm, parola_a_canonico.keys(), n=1, cutoff=soglia
    )
    if candidati:
        return parola_a_canonico[candidati[0]]

    return None


def trova_piu_simile(testo: str, opzioni, soglia: float = 0.6):
    """
    Come interpreta(), ma per liste DINAMICHE invece che sinonimi fissi:
    utile quando le opzioni non sono note in anticipo (es. i nomi delle
    app o dei giochi installati, letti al momento). Ritorna l'opzione più
    simile al testo, o None se nessuna è abbastanza simile.
    """
    testo_norm = normalizza(testo)
    mappa = {normalizza(opzione): opzione for opzione in opzioni}

    if testo_norm in mappa:
        return mappa[testo_norm]

    # Se il testo cercato è contenuto per intero in un'opzione (o viceversa),
    # è quasi certamente quello giusto — utile per nomi parziali, es.
    # "motor town" dentro "Motor Town: Behind The Wheel". Richiediamo
    # almeno 3 caratteri per evitare che una sigla cortissima "catturi"
    # opzioni a caso.
    if len(testo_norm) >= 3:
        corrispondenze = [n for n in mappa if testo_norm in n or n in testo_norm]
        if corrispondenze:
            migliore = min(corrispondenze, key=len)  # la più corta = di solito la più specifica
            return mappa[migliore]

    candidati = difflib.get_close_matches(testo_norm, mappa.keys(), n=1, cutoff=soglia)
    return mappa[candidati[0]] if candidati else None
