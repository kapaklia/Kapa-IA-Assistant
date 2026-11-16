#!/usr/bin/env python3
"""Apre la stessa guida della GUI, anche da un terminale.

Uso: python scripts/configura_scorciatoia.py
     python scripts/configura_scorciatoia.py --testo   (solo istruzioni, senza Qt)
"""
import sys
from .gui_preferences import trigger_command
from .shortcut_setup import instructions


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if '--testo' in args:
        guide = instructions()
        print(f"Kapa — Scorciatoia su {guide.desktop}")
        print('1. ' + guide.first)
        print('2. ' + guide.second)
        print('Comando da incollare se richiesto:')
        print(trigger_command())
        print("Avvia l'assistente, poi prova il tasto scelto.")
        return 0
    try:
        from .gui_backend import AssistantController
        ctl = AssistantController()
        state = ctl.hotkey_state().split('|', 1)[0]
        if ctl.state() and state in ('attiva', 'non_assegnata'):
            response = ctl.configure_hotkey()
            if response == 'richiesta':
                print('Configurazione aperta dal desktop. Scegli la scorciatoia e conferma.')
                return 0
    except OSError:
        pass
    try:
        from PySide6.QtWidgets import QApplication
        from .gui import ShortcutDialog, STYLE
        from .gui_backend import AssistantController
    except ImportError:
        print('Manca PySide6. Mostro le istruzioni da terminale.\n')
        return main(['--testo'])
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    window = ShortcutDialog(None, AssistantController())
    window.exec()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
