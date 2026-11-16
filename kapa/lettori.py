"""Scelta automatica dei lettori MPRIS, con priorità ai browser."""
import re
import subprocess
import time
import unicodedata


def _nome(testo):
    testo = unicodedata.normalize('NFKD', testo.casefold())
    return ''.join(c for c in testo if c.isalnum())


def _browser(nome):
    componenti = re.split(r'[._-]+', nome.casefold())
    return bool(set(componenti) & {
        'brave', 'chromium', 'chrome', 'firefox', 'vivaldi', 'opera',
        'edge', 'msedge', 'librewolf', 'waterfox', 'floorp', 'zen',
        'falkon', 'epiphany', 'browser',
    })


def _scegli_automatico(lettori):
    stati = {}
    scadenza = time.monotonic() + 4
    for nome in lettori:
        residuo = scadenza - time.monotonic()
        if residuo <= 0:
            break
        try:
            stato = subprocess.run(['playerctl', f'--player={nome}', 'status'],
                                   capture_output=True, text=True, timeout=min(1, residuo))
        except (subprocess.TimeoutExpired, OSError):
            continue
        if stato.returncode == 0:
            stati[nome] = stato.stdout.strip()
    # Ordine stabile a parità di priorità. Un lettore che non risponde
    # non impedisce di controllare gli altri disponibili.
    return min(lettori, key=lambda nome: (
        not _browser(nome),
        stati.get(nome) != 'Playing',
        stati.get(nome) != 'Paused',
    ))


def scegli_lettore(lettore=None):
    elenco = subprocess.run(['playerctl', '--list-all'], capture_output=True,
                            text=True, timeout=3)
    if elenco.returncode:
        return None, 'Nessun lettore multimediale disponibile.'
    lettori = list(dict.fromkeys(
        riga.strip() for riga in elenco.stdout.splitlines()
        if re.fullmatch(r'[\w.-]+', riga.strip()) and riga.strip() != 'playerctld'))
    if not lettori:
        return None, 'Nessun lettore multimediale disponibile.'
    if lettore is not None:
        if not isinstance(lettore, str) or not _nome(lettore):
            return None, 'Specifica il nome del lettore da controllare.'
        # Nessun selettore playerctl, wildcard o elenco proveniente dall'utente.
        esatti = [nome for nome in lettori if nome.casefold() == lettore.casefold()]
        candidati = esatti or [nome for nome in lettori
                               if _nome(nome.split('.')[0]) == _nome(lettore)]
        if len(candidati) == 1:
            return candidati[0], None
        if not candidati:
            return None, f'Lettore «{lettore}» non trovato. Disponibili: {", ".join(lettori)}.'
        return _scegli_automatico(candidati), None
    if len(lettori) == 1:
        return lettori[0], None
    return _scegli_automatico(lettori), None
