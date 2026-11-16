#!/usr/bin/env python3
"""Kapa — pannello verticale PySide6.

Le scorciatoie via portale sono gestite dal demone anche a GUI chiusa.
"""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

try:
    from PySide6.QtCore import Qt, QTimer, QUrl, QSize, QRectF
    from PySide6.QtGui import QDesktopServices, QIcon, QTextCursor, QPainter, QColor, QPixmap, QImageReader
    from PySide6.QtWidgets import (
        QApplication, QDialog, QFrame, QHBoxLayout, QLabel,
        QMainWindow, QMessageBox, QMenu, QPlainTextEdit, QPushButton,
        QScrollArea, QSizePolicy, QSystemTrayIcon, QVBoxLayout, QWidget,
        QGraphicsDropShadowEffect, QLayout,
    )
except ImportError:
    print("Manca PySide6. Installa con: python -m pip install -r requirements-gui.txt",
          file=sys.stderr)
    raise SystemExit(1)

from .gui_backend import AssistantController, AssistantError, PROJECT_DIR
from .shortcut_status import current_shortcuts
from .gui_preferences import keyboard_settings_command, trigger_command
from .shortcut_setup import instructions
from .app_paths import ASSETS_DIR

STYLE = """
QMainWindow, QDialog { background: #302f2d; color: #f3f1ed;
    font-family: 'Noto Sans', 'DejaVu Sans', sans-serif; font-size: 13px; }
QWidget#root { background: transparent; color: #f3f1ed;
    font-family: 'Noto Sans', 'DejaVu Sans', sans-serif; font-size: 13px; }
QWidget#scrollBody, QWidget#page { background: transparent; color: #f3f1ed;
    font-family: 'Noto Sans', 'DejaVu Sans', sans-serif; font-size: 13px;
}
QWidget { color: #f3f1ed; font-family: 'Noto Sans', 'DejaVu Sans', sans-serif; font-size: 13px; }
QLabel { background: transparent; border: none; }
QFrame#card { background: rgba(61, 60, 57, 238); border: 1px solid #605d57; border-radius: 22px; }
QLabel#title { font-size: 25px; font-weight: 700; }
QLabel#subtitle, QLabel#muted { color: #d6d1c8; font-size: 12px; }
QLabel#section { font-size: 14px; font-weight: 700; }
QLabel#status { font-size: 18px; font-weight: 700; color: #68e6a6; }
QLabel#shortcutKey { background: #45433f; color: #f0ece4; border: 1px solid #68645d;
    border-radius: 12px; padding: 8px 11px; font-weight: 600; }
QLabel#last { background: #343330; border: none; border-radius: 15px;
    padding: 15px 16px; font-size: 14px; }
QPushButton { background: #514e49; border: 1px solid #706b62; color: #f5f2ed;
    border-radius: 15px; padding: 10px 14px; font-size: 13px; font-weight: 600; }
QPushButton:hover { background: #615d55; }
QPushButton:pressed { background: #45413c; }
QPushButton:disabled { color: #aaa49a; background: #413e39; border-color: #565149; }
QPushButton#primary { background: #2473ed; border-color: #428bff; }
QPushButton#primary:hover { background: #3985fc; }
QPushButton#danger { background: #392737; border-color: #754655; }
QPushButton#danger:hover { background: #573649; }
QPushButton#listen { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 #30bdb8, stop:1 #3878cb); border: 3px solid #4fb7cf;
    border-radius: 48px; padding: 0px; }
QPushButton#listen:hover { background: #359dab; border-color: #8bebe4; }
QPushButton#listen:pressed { background: #286c86; }
QPushButton#listen[recording="true"] { background: #b95170; border-color: #f49ab0; }
QPushButton#listen[recording="true"]:hover { background: #cf607f; }
QPushButton#listen:disabled { background: #4b4943; border-color: #6a655c; }
QLabel#listenCaption { font-size: 15px; font-weight: 600; }
QPlainTextEdit { background: #2f2e2b; border: 1px solid #615c54;
    border-radius: 9px; padding: 12px; color: #ded9cf;
    font-family: 'DejaVu Sans Mono', monospace; font-size: 11px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #33322f; width: 9px; }
QScrollBar::handle:vertical { background: #777166; border-radius: 4px; min-height: 22px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
"""


class AmbientBackground(QWidget):
    """Sfondo centrato in modalità cover, senza alterare le proporzioni."""

    def __init__(self, parent=None):
        super().__init__(parent)
        reader = QImageReader(str(ASSETS_DIR / 'sfondo.png'))
        reader.setAutoTransform(True)
        self._background = QPixmap.fromImage(reader.read())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#302f2d'))
        image = self._background
        if image.isNull() or self.width() <= 0 or self.height() <= 0:
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        scale = max(self.width() / image.width(), self.height() / image.height())
        width, height = self.width() / scale, self.height() / scale
        source = QRectF((image.width() - width) / 2,
                        (image.height() - height) / 2, width, height)
        painter.drawPixmap(QRectF(self.rect()), image, source)


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        item.setObjectName(name)
    item.setWordWrap(wrap)
    return item


def button(text: str, name: str = "", tooltip: str = "") -> QPushButton:
    item = QPushButton(text)
    if name:
        item.setObjectName(name)
    if tooltip:
        item.setToolTip(tooltip)
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    return item


def card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    shadow = QGraphicsDropShadowEffect(frame)
    shadow.setBlurRadius(24)
    shadow.setOffset(0, 6)
    shadow.setColor(QColor(0, 0, 0, 65))
    frame.setGraphicsEffect(shadow)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 19)
    layout.setSpacing(9)
    return frame, layout


class LogWindow(QDialog):
    def __init__(self, parent, log_text: str):
        super().__init__(parent)
        self.setWindowTitle("Kapa — Log attività")
        self.resize(750, 460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(label("Log attività", "section"))
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setPlainText(log_text)
        self.view.moveCursor(QTextCursor.MoveOperation.End)
        layout.addWidget(self.view)
        close = button("Chiudi")
        close.setFixedWidth(100)
        close.clicked.connect(self.close)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)


class ShortcutDialog(QDialog):
    """Fallback desktop quando GlobalShortcuts non è disponibile."""
    def __init__(self, parent=None, controller=None):
        super().__init__(parent)
        self.setWindowTitle('Configura scorciatoia Kapa')
        self.resize(520, 260)
        layout = QVBoxLayout(self)
        guide = instructions()
        layout.addWidget(label(guide.first + '\n\n' + guide.second, wrap=True))
        command = trigger_command()
        text = QPlainTextEdit(command)
        text.setReadOnly(True)
        layout.addWidget(text)
        copy = button('Copia comando')
        copy.clicked.connect(lambda: QApplication.clipboard().setText(command))
        layout.addWidget(copy)
        settings = button('Apri impostazioni tastiera')
        def open_settings():
            args = keyboard_settings_command()
            if args:
                try:
                    subprocess.Popen(args)
                except OSError:
                    QMessageBox.information(self, 'Scorciatoie', 'Apri le impostazioni tastiera dal menu del desktop.')
            else:
                QMessageBox.information(self, 'Scorciatoie', 'Apri le impostazioni tastiera dal menu del desktop.')
        settings.clicked.connect(open_settings)
        layout.addWidget(settings)


class AssistantWindow(QMainWindow):
    def __init__(self, controller: AssistantController | None = None):
        super().__init__()
        self.controller = controller or AssistantController()
        self.setWindowTitle("Kapa")
        icon = QIcon(str(PROJECT_DIR / 'assets/assistant-icon.png'))
        if icon.isNull():
            icon = QIcon.fromTheme("audio-input-microphone")
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.resize(490, 720)
        self.setMinimumSize(140, 160)
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry().size() if screen else QSize(560, 900)
        self.setMaximumSize(min(560, available.width()), min(900, available.height()))
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self._last_response = None
        self._last_state = None
        self._quit_gui = False
        self._first_tray_hide = True
        self._log_dialog = None
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='ia-gui')
        self._state_future = None
        self._shortcut_future = None
        self._snapshot = (None, False, '', None, {})
        QApplication.instance().aboutToQuit.connect(
            lambda: self._executor.shutdown(wait=False, cancel_futures=True))

        root = AmbientBackground()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 15, 16, 12)
        outer.setSpacing(8)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

        scroller = QScrollArea()
        self._scroller = scroller
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.Shape.NoFrame)
        scroll_body = QWidget()
        scroll_body.setObjectName("scrollBody")
        center_layout = QHBoxLayout(scroll_body)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.addStretch(1)
        page = QWidget()
        page.setObjectName("page")
        page.setMaximumWidth(530)
        page.setMinimumWidth(335)
        page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(3, 3, 3, 3)
        page_layout.setSpacing(18)
        center_layout.addWidget(page)
        center_layout.addStretch(1)
        scroller.setWidget(scroll_body)
        outer.addWidget(scroller, 1)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("Kapa", "title"))
        titles.addWidget(label("Il tuo assistente per Linux", "subtitle"))
        header.addLayout(titles, 1)
        self.guide_btn = button("Guida ↗", tooltip="Apri COSA_SA_FARE.md")
        self.guide_btn.setFixedWidth(96)
        self.guide_btn.clicked.connect(self._open_help)
        header.addWidget(self.guide_btn, alignment=Qt.AlignmentFlag.AlignVCenter)
        page_layout.addLayout(header)

        status_frame, status_layout = card()
        status_layout.addWidget(label("IL TUO ASSISTENTE", "muted"))
        self.status_label = label("●  Non attivo", "status")
        status_layout.addWidget(self.status_label)
        self.mic_label = label("Microfono chiuso", "muted", True)
        status_layout.addWidget(self.mic_label)
        page_layout.addWidget(status_frame)

        controls = QVBoxLayout()
        controls.setSpacing(10)
        self.listen_btn = button("", "listen", "Parla ora")
        self.listen_btn.setIcon(QIcon(str(PROJECT_DIR / 'assets/microphone.svg')))
        self.listen_btn.setIconSize(QSize(42, 42))
        self.listen_btn.setFixedSize(96, 96)
        self.listen_btn.setAccessibleName("Parla ora")
        self.listen_btn.clicked.connect(self._listen)
        controls.addWidget(self.listen_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.listen_caption = label("Parla ora", "listenCaption")
        controls.addWidget(self.listen_caption, alignment=Qt.AlignmentFlag.AlignHCenter)
        page_layout.addLayout(controls)
        self._normal_controls = controls

        # Un piccolo controllo, senza una card dedicata e senza configurazioni ambigue.
        shortcut_row = QHBoxLayout()
        shortcut_row.setSpacing(9)
        shortcut_row.addStretch(1)
        self.shortcut_btn = button("⚙  Scorciatoie", tooltip="Configura il tasto nelle impostazioni native di Linux")
        self.shortcut_btn.setFixedWidth(145)
        self.shortcut_btn.clicked.connect(self._open_shortcut_settings)
        shortcut_row.addWidget(self.shortcut_btn)
        self.shortcut_label = label("Verifico…", "shortcutKey")
        self.shortcut_label.setToolTip("Scorciatoie configurate nel desktop Linux")
        shortcut_row.addWidget(self.shortcut_label)
        shortcut_row.addStretch(1)
        page_layout.addLayout(shortcut_row)
        self._refresh_shortcut()
        self._shortcut_timer = QTimer(self)
        self._shortcut_timer.timeout.connect(self._refresh_shortcut)
        self._shortcut_timer.start(4000)

        last_frame, last_layout = card()
        last_layout.addWidget(label("Ultima richiesta", "section"))
        self.heard_label = label("Hai detto: —", "muted", True)
        self.route_label = label("", "muted", True)
        self.action_label = label("Azione: —", "muted", True)
        last_layout.addWidget(self.heard_label)
        last_layout.addWidget(self.route_label)
        last_layout.addWidget(self.action_label)
        last_layout.addWidget(label("Risposta", "section"))
        self.last_label = label("Nessuna risposta ancora", "last", True)
        self.last_label.setMinimumHeight(55)
        self.last_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        last_layout.addWidget(self.last_label)
        page_layout.addWidget(last_frame)

        logs_row = QHBoxLayout()
        logs_row.addWidget(label("Log attività", "section"))
        logs_row.addStretch(1)
        self.log_btn = button("Apri log ↗", tooltip="Visualizza il registro in una finestra separata")
        self.log_btn.setFixedWidth(110)
        self.log_btn.clicked.connect(self._open_logs)
        logs_row.addWidget(self.log_btn)
        page_layout.addLayout(logs_row)

        self.info = label("Il microfono resta chiuso finché non attivi l'ascolto.", "muted", True)
        page_layout.addWidget(self.info)
        page_layout.addStretch(1)

        self._compact = False
        self._compact_panel = QWidget()
        self._compact_layout = QVBoxLayout(self._compact_panel)
        self._compact_layout.setContentsMargins(0, 0, 0, 0)
        self._compact_panel.hide()
        outer.addWidget(self._compact_panel, 1)

        self._make_tray()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(550)
        self._start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, '_compact_panel'):
            return
        compact = self.width() < 390 or self.height() < 450
        if compact == self._compact:
            return
        self._compact = compact
        if compact:
            self._normal_controls.removeWidget(self.listen_btn)
            self._compact_layout.addWidget(self.listen_btn, 0, Qt.AlignmentFlag.AlignCenter)
            self._scroller.hide()
            self._compact_panel.show()
        else:
            self._compact_layout.removeWidget(self.listen_btn)
            self._normal_controls.insertWidget(0, self.listen_btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self._compact_panel.hide()
            self._scroller.show()
        self.listen_btn.show()

    def _refresh_shortcut(self):
        # Il portale mostra il tasto realmente connesso al demone.
        if self._shortcut_future is None:
            self._shortcut_future = self._executor.submit(
                lambda: (self.controller.hotkey_state(), current_shortcuts()))
            QTimer.singleShot(150, self._refresh_shortcut)
            return
        if not self._shortcut_future.done():
            QTimer.singleShot(150, self._refresh_shortcut)
            return
        try:
            portal, (keys, supported) = self._shortcut_future.result()
        except Exception:
            portal, keys, supported = 'non_disponibile', [], False
        self._shortcut_future = None
        state, _, trigger = portal.partition("|")
        if state == "attiva" and trigger:
            self.shortcut_label.setText(trigger)
            self.shortcut_label.setToolTip("Scorciatoia attiva tramite portale Linux")
            return
        # Scorciatoie tradizionali già configurate nel desktop.
        if keys:
            self.shortcut_label.setText("  /  ".join(keys))
            self.shortcut_label.setToolTip("Scorciatoia configurata nel desktop Linux")
        elif state in ("avvio", "verifica"):
            self.shortcut_label.setText("Verifico…")
        elif state in ("non_assegnata", "desktop") or supported:
            self.shortcut_label.setText("Da configurare")
        else:
            self.shortcut_label.setText("Da verificare")

    def _open_shortcut_settings(self):
        try:
            response = self.controller.configure_hotkey()
        except AssistantError as exc:
            ShortcutDialog(self, self.controller).exec()
            return
        if response == "richiesta":
            self._notice("Configura la scorciatoia nella finestra di Linux.")
        elif response == "avvio":
            self._notice("Il servizio scorciatoie si sta avviando: riprova.", True)
        else:
            ShortcutDialog(self, self.controller).exec()
        QTimer.singleShot(1500, self._refresh_shortcut)

    def _make_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = self.windowIcon()
        if icon.isNull():
            return
        tray = QSystemTrayIcon(icon, self)
        tray.setToolTip("Kapa — Microfono chiuso")
        menu = QMenu()
        open_action = menu.addAction("Apri Kapa")
        open_action.triggered.connect(self._show_window)
        speak_action = menu.addAction("Parla ora")
        speak_action.triggered.connect(self._listen)
        menu.addSeparator()
        quit_action = menu.addAction("Chiudi")
        quit_action.triggered.connect(self._exit_all)
        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        tray.show()
        self.tray = tray

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_window()

    def _show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _exit_gui(self):
        self._quit_gui = True
        QApplication.instance().quit()

    def _exit_all(self):
        if self._stop_for_exit():
            self._exit_gui()

    def _stop_for_exit(self):
        try:
            self.controller.stop()
        except (AssistantError, OSError) as exc:
            self._show_window()
            self._notice(f"Impossibile chiudere l'assistente: {exc}", True)
            return False
        return True

    def closeEvent(self, event):
        if self.tray and self.tray.isVisible() and not self._quit_gui:
            event.ignore()
            self.hide()
            if self._first_tray_hide:
                self.tray.showMessage("Kapa",
                                      "La finestra è nascosta. Per uscire, fai clic destro "
                                      "sull'icona e scegli «Chiudi».",
                                      QSystemTrayIcon.MessageIcon.Information, 2500)
                self._first_tray_hide = False
        else:
            if self._quit_gui or self._stop_for_exit():
                event.accept()
            else:
                event.ignore()

    def _notice(self, message: str, error: bool = False):
        self.info.setText(message)
        self.info.setStyleSheet("color: #ffad9a;" if error else "color: #d1cbc0;")

    def _start(self):
        try:
            self._notice(self.controller.start())
        except AssistantError as exc:
            self._notice(str(exc), True)
        self._refresh()

    def _listen(self):
        if self._snapshot[0] is None and not self._snapshot[1]:
            self._start()
            return
        try:
            self._notice(self.controller.listen())
        except AssistantError as exc:
            self._notice(str(exc), True)
        self._refresh()

    def _open_help(self):
        doc = PROJECT_DIR / "COSA_SA_FARE.md"
        if not doc.is_file():
            QMessageBox.information(self, "Guida", "Non trovo COSA_SA_FARE.md.")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(doc))):
            QMessageBox.information(self, "Guida", f"Apri manualmente:\n{doc}")

    def _open_logs(self):
        self._log_dialog = LogWindow(self, self.controller.logs() or "Nessun log disponibile.")
        self._log_dialog.show()

    def _refresh(self):
        try:
            show_logs = bool(self._log_dialog and self._log_dialog.isVisible())
            if self._state_future is not None and self._state_future.done():
                self._snapshot = self._state_future.result()
                self._state_future = None
            if self._state_future is None:
                def read_snapshot():
                    state = self.controller.state()
                    return (state, self.controller.is_starting() if not state else False,
                            self.controller.latest_response(), self.controller.logs() if show_logs else None,
                            self.controller.latest_activity())
                self._state_future = self._executor.submit(read_snapshot)
            state, starting, response, log_snapshot, activity = self._snapshot
            self.heard_label.setText('Hai detto: ' + (activity.get('sentito') or '—'))
            route = {'locale': 'Locale · Nessuna chiamata a Groq',
                     'scartato': 'Ascolto non riconosciuto · Nessuna chiamata a Groq',
                     'groq': 'Groq · Richiesta online'}.get(activity.get('percorso'), '')
            self.route_label.setText(route)
            actions = activity.get('azioni', [])
            names = {
                'avvia_buffer_replay': 'Avvio buffer replay', 'salva_replay': 'Salvataggio replay',
                'ferma_buffer_replay': 'Arresto buffer replay',
                'avvia_registrazione_schermo': 'Avvio registrazione schermo',
                'ferma_registrazione_schermo': 'Arresto registrazione schermo',
                'registra_schermo_per': 'Registrazione a tempo',
                'apri_applicazione': 'Apertura applicazione', 'leggi_appunti': 'Lettura appunti',
                'controllo_multimediale': 'Controllo riproduzione',
                'regolazione_volume': 'Regolazione volume', 'imposta_volume': 'Impostazione volume',
                'fai_screenshot': 'Screenshot', 'dettatura': 'Dettatura',
            }
            self.action_label.setText('Azione richiesta: ' + (
                ', '.join(names.get(name, name.replace('_', ' ')) for name in actions)
                if actions else 'Nessuna azione'))
            if activity:
                response = activity['esito']
            if state == "attesa":
                status, mic, color = "●  Assistente pronto", "Microfono chiuso · In attesa della scorciatoia", "#65e8a0"
            elif state == "ascolto":
                status, mic, color = "●  In ascolto", "Microfono aperto · Parla ora", "#5dcbff"
            elif state == "elaborazione":
                status, mic, color = "●  Elaborazione", "Microfono chiuso · Sto interpretando", "#f4bd68"
            elif starting:
                status, mic, color = "●  Caricamento", "Caricamento di Whisper · Microfono chiuso", "#f4bd68"
            else:
                status, mic, color = "●  Non attivo", "Microfono chiuso", "#a9b7cc"
            if self._last_state != (state, starting):
                self.status_label.setText(status)
                self.status_label.setStyleSheet(f"color: {color};")
                self.mic_label.setText(mic)
                if self.tray:
                    self.tray.setToolTip(f"Kapa — {mic}")
                self._last_state = (state, starting)
            self.listen_btn.setEnabled(not starting and state != "elaborazione")
            caption = ("Termina ascolto" if state == "ascolto" else
                       "Parla ora" if state else
                       "Caricamento…" if starting else "Riprova avvio")
            self.listen_caption.setText(caption)
            self.listen_btn.setAccessibleName(caption)
            self.listen_btn.setToolTip(caption)
            recording = state == "ascolto"
            if self.listen_btn.property('recording') != recording:
                self.listen_btn.setProperty('recording', recording)
                self.listen_btn.style().unpolish(self.listen_btn)
                self.listen_btn.style().polish(self.listen_btn)
                self.listen_btn.update()
            if response != self._last_response:
                self.last_label.setText(response or "Nessuna risposta ancora")
                self._last_response = response
            if self._log_dialog and self._log_dialog.isVisible():
                logs = log_snapshot
                view = self._log_dialog.view
                if logs is not None and logs != view.toPlainText():
                    scroll = view.verticalScrollBar()
                    follow = scroll.value() >= scroll.maximum() - 20
                    view.setPlainText(logs)
                    if follow:
                        scroll.setValue(scroll.maximum())
        except OSError as exc:
            self._notice(f"Impossibile leggere lo stato: {exc}", True)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Kapa")
    app.setQuitOnLastWindowClosed(True)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    from .gui_instance import GuiInstance
    instance = GuiInstance(parent=app)
    try:
        if not instance.acquire():
            return 0
        window = AssistantWindow()
        instance.activated.connect(window._show_window)
        if window.tray:
            app.setQuitOnLastWindowClosed(False)
        window.show()
        return app.exec()
    except RuntimeError as exc:
        QMessageBox.warning(None, 'Kapa', str(exc))
        return 1
    finally:
        instance.close()


if __name__ == "__main__":
    raise SystemExit(main())
