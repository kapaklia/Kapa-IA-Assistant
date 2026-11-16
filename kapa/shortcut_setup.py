"""Guida breve e portabile alla registrazione di scorciatoie Linux.

Non scrive nei file di configurazione del desktop. Le associazioni globali
sono gestite dal sistema; qui generiamo istruzioni adatte all'ambiente.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ShortcutGuide:
    desktop: str
    first: str
    second: str


def desktop_family(environment=None) -> str:
    env = os.environ if environment is None else environment
    text = " ".join((env.get('XDG_CURRENT_DESKTOP', ''), env.get('DESKTOP_SESSION', ''))).lower()
    for label, aliases in [
        ('KDE Plasma', ('kde', 'plasma')),
        ('GNOME', ('gnome', 'unity')),
        ('Cinnamon', ('cinnamon',)),
        ('XFCE', ('xfce', 'xfce4')),
        ('MATE', ('mate',)),
    ]:
        if any(alias in text for alias in aliases):
            return label
    return 'Linux'


def instructions(environment=None) -> ShortcutGuide:
    family = desktop_family(environment)
    if family == 'KDE Plasma':
        return ShortcutGuide(family,
            "Cerca 'Kapa' nelle scorciatoie e selezionalo. Se non c'è, scegli 'Aggiungi nuovo → Comando o script'.",
            "Assegna il tasto scelto. Se crei una nuova voce, incolla nel campo Comando ciò che la GUI ha copiato.")
    if family == 'GNOME':
        return ShortcutGuide(family,
            "Apri 'Scorciatoie personalizzate' e premi '+'.",
            "Nome: Kapa. Incolla il comando copiato e assegna il tasto scelto.")
    if family in ('Cinnamon', 'XFCE', 'MATE'):
        return ShortcutGuide(family,
            "Apri la sezione delle scorciatoie personalizzate e aggiungi una nuova azione.",
            "Nome: Kapa. Incolla il comando copiato e assegna il tasto scelto.")
    return ShortcutGuide(family,
        "Apri le impostazioni della tastiera e cerca le scorciatoie personalizzate.",
        "Aggiungi Kapa, incolla il comando copiato e assegna il tasto scelto.")
