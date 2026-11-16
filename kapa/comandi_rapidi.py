"""Instradamento locale rigoroso dei comandi multimediali più semplici.

Non cerca parole in mezzo a richieste complesse: un falso positivo può
innescare azioni non richieste. Restituisce (nome_funzione, kwargs) o None.
"""
import re
import unicodedata


def _normalizza(testo):
    testo = unicodedata.normalize('NFKC', testo).casefold().strip()
    testo = re.sub(r'[.,!?;:]+', ' ', testo)
    return re.sub(r'\s+', ' ', testo).strip()



_NUMERI = {
    "zero": 0, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4,
    "cinque": 5, "sei": 6, "sette": 7, "otto": 8, "nove": 9,
    "dieci": 10, "undici": 11, "dodici": 12, "tredici": 13,
    "quattordici": 14, "quindici": 15, "sedici": 16, "diciassette": 17,
    "diciotto": 18, "diciannove": 19, "venti": 20, "trenta": 30,
    "quaranta": 40, "cinquanta": 50, "sessanta": 60,
    "settanta": 70, "ottanta": 80, "novanta": 90, "cento": 100,
}


def _numero_italiano(parole):
    parole = parole.replace("per cento", "").replace("percento", "").strip()
    if parole.isdigit():
        return int(parole)
    token = parole.replace("-", " ").split()
    if len(token) == 1:
        parola = token[0]
        if parola in _NUMERI:
            return _NUMERI[parola]
        for prefisso, centinaia in [('cento', 100), ('duecento', 200), ('trecento', 300),
                                  ('quattrocento', 400), ('cinquecento', 500), ('seicento', 600),
                                  ('settecento', 700), ('ottocento', 800), ('novecento', 900)]:
            if parola == prefisso:
                return centinaia
            if parola.startswith(prefisso):
                resto = _numero_italiano(parola[len(prefisso):])
                if resto is not None and 0 < resto < 100:
                    return centinaia + resto
        # 21-99, compresi ventuno, ventotto, trentacinque, ecc.
        for decina, valore in _NUMERI.items():
            if valore not in range(20, 100, 10):
                continue
            for unita, numero in _NUMERI.items():
                if not 1 <= numero <= 9:
                    continue
                base = decina[:-1] if numero in (1, 8) else decina
                if parola == base + unita:
                    return valore + numero
    if len(token) == 2 and token[0] in _NUMERI and token[1] in _NUMERI:
        decina, unita = _NUMERI[token[0]], _NUMERI[token[1]]
        if decina in range(20, 100, 10) and 1 <= unita <= 9:
            return decina + unita
    return None


def _normalizza_percentuali(frase):
    # Converte solo la porzione dopo la preposizione, mai parole in altri contesti.
    m = re.search(r"\b(del|di|al|a) (.+?)(?: ?%| per cento| percento)?$", frase)
    if m:
        n = _numero_italiano(m.group(2))
        if n is not None:
            return frase[:m.start(2)] + str(n)
    return frase

def riconosci(testo):
    diretto = _riconosci_base(testo)
    if diretto is not None:
        return diretto
    frase = unicodedata.normalize('NFKC', testo).casefold().strip().rstrip('.!?;:')
    if len(frase) > 120:
        return None
    video = re.fullmatch(r'(.+) (?:con|su|tramite) (obs|obs studio|gsr|gpu sr|gpu screen recorder)', frase)
    if video:
        comando = _riconosci_base(video.group(1))
        if comando and comando[0] in {'avvia_registrazione_schermo', 'registra_schermo_per', 'avvia_buffer_replay'}:
            backend = 'obs' if video.group(2).startswith('obs') else 'gsr'
            return comando[0], dict(comando[1], backend=backend)
    # Separa un comando completo dal nome del lettore; la risoluzione
    # avviene solo tra i lettori realmente disponibili, senza fuzzy matching.
    parole = frase.split()
    for fine in range(len(parole) - 1, 0, -1):
        comando = _riconosci_base(' '.join(parole[:fine]))
        if comando is None or comando[0] != 'controllo_multimediale':
            continue
        resto = parole[fine:]
        if resto[0] in {'su', 'in', 'di', 'sul', 'nel'}:
            resto = resto[1:]
        if resto and resto[0] in {'il', 'sul', 'nel'}:
            resto = resto[1:]
        if (not resto or len(resto) > 5
                or any(p in {'e', 'poi', 'non', 'anche', 'ma', 'tutti'} for p in resto)):
            return None
        return comando[0], dict(comando[1], lettore=' '.join(resto))
    return None


def _riconosci_base(testo):
    frase = _normalizza_percentuali(_normalizza(testo))
    if not frase or len(frase) > 90:
        return None
    # Frasi complete: nessun fuzzy matching su verbi o richieste ambigue.
    # Le varianti del sostantivo sono errori STT osservati; richiediamo
    # comunque un verbo esplicito per evitare azioni da parole isolate.
    replay = r'(?:replay|re play|reblay|rebli|reblesi)'
    if re.fullmatch(r'(?:salva|clippa)(?: il| i)? ' + replay, frase):
        return 'salva_replay', {}
    if re.fullmatch(r'(?:avvia|attiva)(?: il)? (?:buffer(?: di)? )?' + replay, frase):
        return 'avvia_buffer_replay', {}
    if re.fullmatch(r'(?:ferma|disattiva)(?: il)? (?:buffer(?: di)? )?' + replay, frase):
        return 'ferma_buffer_replay', {}
    durata = re.fullmatch(
        r'(?:avvia|attiva)(?: il)? (?:buffer(?: di)? )?' + replay
        + r' (?:da|di|per) (.+) secondi', frase)
    if durata:
        secondi = _numero_italiano(durata.group(1))
        if secondi is not None and 1 <= secondi <= 600:
            return 'avvia_buffer_replay', {'secondi': secondi}
    if frase in {'avvia registrazione schermo', 'avvia la registrazione dello schermo',
                 'registra lo schermo', 'inizia a registrare lo schermo'}:
        return 'avvia_registrazione_schermo', {}
    if frase in {'ferma registrazione schermo', 'ferma la registrazione',
                 'ferma la registrazione dello schermo', 'termina la registrazione'}:
        return 'ferma_registrazione_schermo', {}
    durata = re.fullmatch(r'(?:registra lo schermo per|fai un video di) (.+) secondi', frase)
    if durata:
        secondi = _numero_italiano(durata.group(1))
        if secondi is not None and 1 <= secondi <= 600:
            return 'registra_schermo_per', {'secondi': secondi}
    # Elenco chiuso: una richiesta con dettagli o più azioni resta a Groq.
    applicazioni = {
        'firefox': 'firefox', 'il browser': 'firefox', 'browser': 'firefox',
        'il terminale': 'konsole', 'terminale': 'konsole', 'konsole': 'konsole',
        'dolphin': 'dolphin', 'il gestore file': 'dolphin',
        'spotify': 'spotify', 'discord': 'discord', 'steam': 'steam',
        'vlc': 'vlc', 'telegram': 'telegram', 'kate': 'kate',
    }
    apri = re.fullmatch(r'(?:apri|avvia) (.+)', frase)
    if apri and apri.group(1) in applicazioni:
        return 'apri_applicazione', {'nome_app': applicazioni[apri.group(1)]}
    if frase in {'leggi gli appunti', 'leggi appunti', 'mostra gli appunti'}:
        return 'leggi_appunti', {}
    for azione, frasi in {
        'avanti': {'prossima traccia', 'prossima canzone', 'brano successivo', 'traccia successiva'},
        'indietro': {'traccia precedente', 'canzone precedente', 'brano precedente'},
        'stop': {'ferma la musica', 'ferma la riproduzione', 'interrompi la riproduzione'},
        'ripeti_traccia': {'ripeti la traccia', 'ripeti il brano', 'ripeti la canzone', 'ripeti traccia'},
        'ripeti_playlist': {'ripeti la playlist', 'ripeti playlist'},
        'disattiva_ripetizione': {'disattiva ripetizione', 'disattiva la ripetizione'},
        'casuale': {'attiva riproduzione casuale', 'attiva la riproduzione casuale'},
        'disattiva_casuale': {'disattiva riproduzione casuale', 'disattiva la riproduzione casuale'},
        'ricomincia': {'ricomincia il brano', 'ricomincia la traccia', 'ricomincia la canzone'},
    }.items():
        if frase in frasi:
            return 'controllo_multimediale', {'azione': azione}
    screenshot = re.fullmatch(r'(?:fai|scatta)(?: uno| un| lo)? screenshot(?: (.+))?', frase)
    if screenshot:
        dettaglio = screenshot.group(1)
        if dettaglio is None:
            return 'fai_screenshot', {}
        if dettaglio in ('di tutti i monitor', 'di tutti gli schermi', 'del desktop completo'):
            return 'fai_screenshot', {'destinazione': 'tutti'}
        if dettaglio in ('della finestra attiva', 'della finestra in primo piano'):
            return 'fai_screenshot', {'destinazione': 'finestra'}
        if dettaglio in ('del monitor principale', 'dello schermo principale'):
            return 'fai_screenshot', {}
        numero = re.fullmatch(r'del monitor (.+)', dettaglio)
        if numero:
            indice = _numero_italiano(numero.group(1))
            if indice is not None and indice > 0:
                return 'fai_screenshot', {'destinazione': 'monitor', 'monitor': indice}

    pause = {'metti pausa', 'metti in pausa', 'pausa', 'pause', 'metti pause'}
    play = {'metti play', 'play', 'riprendi la riproduzione', 'riprendi riproduzione',
            'riprendi il video', 'riprendi la musica'}
    mute = {'silenzia audio', 'silenzia il volume', 'metti mute', 'muta audio',
            'togli audio', 'metti muto', 'disattiva audio'}
    unmute = {'riattiva audio', 'riattiva l audio', 'togli il muto', 'togli mute',
              'togli il mute', 'smuta audio', 'unmute'}
    if frase in pause:
        return 'controllo_multimediale', {'azione': 'pausa'}
    if frase in play:
        return 'controllo_multimediale', {'azione': 'play'}
    if frase in mute:
        return 'regolazione_volume', {'azione': 'muta'}
    if frase in unmute:
        return 'regolazione_volume', {'azione': 'smuta'}

    # Non indovinare percentuali da trascrizioni poco chiare.
    m = re.fullmatch(r'(alza|aumenta|abbassa|diminuisci)(?: (?:il )?volume)?(?: (del|di|al|a) ([0-9]{1,3}) ?%?)?', frase)
    if m:
        azione = 'alza' if m.group(1) in ('alza', 'aumenta') else 'abbassa'
        preposizione, numero = m.group(2), m.group(3)
        if numero is None:
            return 'regolazione_volume', {'azione': azione}
        percentuale = int(numero)
        if preposizione in ('del', 'di') and 1 <= percentuale <= 100:
            return 'regolazione_volume', {'azione': azione, 'percentuale': percentuale}
        if preposizione in ('al', 'a') and 0 <= percentuale <= 100:
            # alza/abbassa al 20% = livello assoluto, non variazione relativa.
            return 'imposta_volume', {'percentuale': percentuale}
        return None

    m = re.fullmatch(r'(?:metti|imposta|porta)(?: il)? volume (?:al|a) ([0-9]{1,3}) ?%?', frase)
    if m and 0 <= int(m.group(1)) <= 100:
        return 'imposta_volume', {'percentuale': int(m.group(1))}
    return None


def rifiuta_volume_non_valido(testo):
    """Blocca SOLO richieste di volume esplicite con percentuale fuori 0..100.

    False positive evitati: domande su percentuali, video, altre richieste.
    Non sostituisce il controllo sui parametri delle funzioni.
    """
    grezzo = unicodedata.normalize('NFKC', testo).casefold().strip().rstrip('.!?')
    esplicito = re.fullmatch(
        r'(?:metti|imposta|porta|alza|aumenta|abbassa|diminuisci)(?: il)? volume '
        r'(?:al|a|del|di) ([+-]?\d+(?:[.,]\d+)?)\s*(?:%|per cento|percento)?', grezzo)
    if esplicito:
        valore = float(esplicito.group(1).replace(',', '.'))
        return not (valore.is_integer() and 0 <= valore <= 100)
    frase = _normalizza(testo)
    if not frase or len(frase) > 130:
        return False
    # Accetta frasi imperative brevi; niente ricerca libera di numeri nel testo.
    if not re.match(r'^(?:metti|imposta|porta|alza|aumenta|abbassa|diminuisci)\b', frase):
        return False
    if not re.search(r'\bvolume\b', frase):
        return False
    m = re.fullmatch(
        r'(?:metti|imposta|porta|alza|aumenta|abbassa|diminuisci)'
        r'(?: il)? volume (?:al|a|del|di) (.+?)\s*(?:%|per cento|percento)?', frase)
    if not m:
        return False
    numero = re.sub(r'(?:\s*%|\s*per cento|\s*percento)$', '', m.group(1)).strip()
    # Rifiuta esplicitamente il numero impossibile, non un testo incerto.
    if numero.isdecimal():
        return int(numero) > 100
    interpretato = _numero_italiano(numero)
    if interpretato is not None:
        return interpretato > 100
    # Il parsificatore normale copre solo 0..100; includiamo centinaia comuni.
    numeri_oltre = {'duecento', 'trecento', 'quattrocento', 'cinquecento',
                    'seicento', 'settecento', 'ottocento', 'novecento', 'mille'}
    return numero in numeri_oltre


def valida_parametri_volume(nome_funzione, parametri):
    """Seconda barriera sui parametri prodotti da Groq prima dell'esecuzione."""
    if nome_funzione not in ('imposta_volume', 'regolazione_volume'):
        return None
    if nome_funzione == 'regolazione_volume' and 'percentuale' not in parametri:
        return None
    valore = parametri.get('percentuale')
    if isinstance(valore, bool):
        return 'Percentuale del volume non valida: usa un valore tra 0 e 100.'
    try:
        numero = float(valore)
    except (TypeError, ValueError, OverflowError):
        return 'Percentuale del volume non valida: usa un valore tra 0 e 100.'
    if not (numero.is_integer() and 0 <= numero <= 100):
        return 'Percentuale del volume non valida: usa un valore tra 0 e 100.'
    if nome_funzione == 'regolazione_volume' and numero == 0:
        return 'Per variare il volume, specifica una percentuale tra 1 e 100.'
    parametri['percentuale'] = int(numero)
    return None
