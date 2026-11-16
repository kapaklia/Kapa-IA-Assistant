#!/usr/bin/env python3
# trigger.py
#
# Questo è il comando che associ alla scorciatoia da tastiera di KDE.
# NON ascolta nulla e non tocca il microfono: si limita a mandare un breve
# messaggio al processo in background (demone.py), che è quello che decide
# cosa fare. Poi termina subito.
#
# Uso:
#   python3 trigger.py toggle    -> inizia ad ascoltare (o smette, se sta già ascoltando)
#   python3 trigger.py stop      -> smette di ascoltare
#   python3 trigger.py stato     -> dice in che stato è (attesa/ascolto/elaborazione)
#   python3 trigger.py esci      -> ferma il processo in background
#
# Usa SOLO la libreria standard di Python (niente import del progetto), così
# parte in un attimo anche se premi la scorciatoia in mezzo a una partita.

import os
import socket
import subprocess
import sys
from pathlib import Path

# Deve restare uguale a SOCKET_PATH in config.py
from .app_paths import SOCKET_PATH


def main() -> int:
    comando = sys.argv[1] if len(sys.argv) > 1 else "toggle"

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(2)
    try:
        client.connect(str(SOCKET_PATH))
        client.sendall(comando.encode("utf-8"))
        risposta = client.recv(64).decode("utf-8", "ignore")
    except (FileNotFoundError, ConnectionRefusedError, socket.timeout):
        messaggio = "L'assistente non è attivo (avvialo con: python main.py --background)"
        print(messaggio, file=sys.stderr)
        try:
            subprocess.run(["notify-send", "-a", "Assistente", "-u", "critical",
                            "⚠️ Assistente non attivo", messaggio], timeout=3)
        except Exception:
            pass
        return 1
    finally:
        client.close()

    print(risposta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
