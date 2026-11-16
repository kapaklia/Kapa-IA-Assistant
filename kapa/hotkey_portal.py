"""Scorciatoie Linux tramite XDG Desktop Portal (senza dipendenza da KDE).

All'avvio legge le assegnazioni salvate: se esistono le riattiva; se mancano,
NON apre finestre. La configurazione nativa viene richiesta solo dalla GUI.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Callable

APP_ID = "org.iaassistant.IAAssistant"
SHORTCUT_ID = "microfono"
PREFERRED = "ALT+Q"


def display_trigger(shortcuts) -> str:
    for item in shortcuts:
        if getattr(item, "id", None) == SHORTCUT_ID:
            return str(getattr(item, "trigger_description", "") or "").strip()
    return ""


def matching_shortcut(shortcuts) -> bool:
    return any(getattr(item, "id", None) == SHORTCUT_ID for item in shortcuts)


class GlobalHotkey:
    def __init__(self, toggle: Callable[[], None]):
        self.toggle = toggle
        self._lock = threading.Lock()
        self._state = "avvio"
        self._detail = ""
        self._thread = None
        self._loop = None
        self._session = None
        self._stop = threading.Event()
        self._ready = False
        self._bound = False
        self._config_pending = False

    def _set(self, state: str, detail: str = ""):
        with self._lock:
            self._state, self._detail = state, detail[:120]

    def state(self) -> str:
        with self._lock:
            return f"{self._state}|{self._detail}" if self._detail else self._state

    def start(self):
        # Default: prova il portale se presente. 'desktop' disabilita il portale.
        if os.environ.get("IA_ASSISTANT_SHORTCUT_MODE", "auto").lower() in ("desktop", "off"):
            self._set("desktop")
            return
        if self._thread is not None:
            return
        try:
            from global_shortcut_portal import Portal  # noqa: F401
        except ImportError:
            self._set("libreria_mancante")
            return
        try:
            from .installa_launcher import ensure_launcher
            ensure_launcher()
        except OSError as exc:
            logging.warning("Impossibile creare collegamento desktop: %s", exc)
        self._thread = threading.Thread(target=self._thread_main, name="ia-shortcut-portal", daemon=True)
        self._thread.start()

    def _thread_main(self):
        try:
            asyncio.run(self._serve())
        except Exception as exc:
            logging.exception("Portale scorciatoie non disponibile: %s", exc)
            self._set("non_disponibile")

    async def _serve(self):
        try:
            from global_shortcut_portal import Portal, GlobalShortcutsSession, Shortcut, SessionCallback
        except ImportError:
            self._set("libreria_mancante")
            return

        owner = self

        class Callback(SessionCallback):
            def on_activated(self, event):
                if getattr(event, "shortcut_id", None) == SHORTCUT_ID:
                    try:
                        owner.toggle()
                    except Exception:
                        logging.exception("Errore durante attivazione scorciatoia")

            def on_shortcuts_changed(self, session, shortcuts):
                trigger = display_trigger(shortcuts)
                owner._set("attiva" if trigger else "non_assegnata", trigger)

            def on_error(self, error):
                logging.warning("Errore portale scorciatoie: %s", error)

        portal = Portal()
        try:
            await portal.connect()
            session = GlobalShortcutsSession(portal, app_id=APP_ID, callback=Callback())
            await session.connect()
            self._loop = asyncio.get_running_loop()
            self._session = session
            # Il portale restituisce anche le assegnazioni persistenti precedenti,
            # prima che BindShortcuts sia richiamato in questa sessione.
            saved = await session.list_shortcuts()
            if matching_shortcut(saved) and display_trigger(saved):
                # Riaggancia l'ID esistente. Plasma conserva il tasto già salvato.
                # Alcuni altri backend possono comunque chiedere autorizzazione:
                # questa limitazione è sotto il controllo dell'ambiente desktop.
                current = await session.bind([Shortcut(
                    id=SHORTCUT_ID, description="Attiva o termina l'ascolto vocale",
                    preferred_trigger=PREFERRED,
                )])
                self._bound = True
                trigger = display_trigger(current)
            else:
                # Nessuna assegnazione: NON configurare all'avvio.
                trigger = ""
                self._bound = False
            self._set("attiva" if trigger else "non_assegnata", trigger)
            self._ready = True
            while not self._stop.is_set():
                await asyncio.sleep(0.25)
        finally:
            self._ready = False
            self._loop, self._session = None, None
            if 'session' in locals():
                try:
                    await session.close()
                except Exception:
                    pass
            try:
                await portal.close()
            except Exception:
                pass

    def configure(self) -> str:
        if not self._ready or self._session is None or self._loop is None:
            return "avvio" if self.state() == "avvio" else "non_disponibile"
        if self._config_pending:
            return "richiesta"
        try:
            self._config_pending = True
            future = asyncio.run_coroutine_threadsafe(self._configure(), self._loop)
            future.add_done_callback(self._configuration_done)
            return "richiesta"
        except RuntimeError:
            self._config_pending = False
            return "non_disponibile"

    async def _configure(self):
        if not self._bound:
            # Prima configurazione: BindShortcuts apre la finestra nativa.
            from global_shortcut_portal import Shortcut
            bound = await self._session.bind([Shortcut(
                id=SHORTCUT_ID, description="Attiva o termina l'ascolto vocale",
                preferred_trigger=PREFERRED,
            )])
            self._bound = True
        else:
            # Successive modifiche: apri la configurazione nativa su richiesta.
            await self._session.configure()
            bound = await self._session.list_shortcuts()
        trigger = display_trigger(bound)
        self._set("attiva" if trigger else "non_assegnata", trigger)

    def _configuration_done(self, future):
        self._config_pending = False
        try:
            future.result()
        except Exception as exc:
            logging.warning("Configurazione scorciatoia non riuscita: %s", exc)
            self._set("configurazione_non_disponibile")

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
