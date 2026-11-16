"""Controlli GUI offscreen con controller interamente sintetico."""
import os
import tempfile
import unittest
import subprocess
import sys
import time
import socket
from pathlib import Path
from unittest.mock import patch, Mock


class GuiTests(unittest.TestCase):
    def test_single_instance_reactivation_and_crash_recovery(self):
        try:
            from PySide6.QtWidgets import QApplication
            from kapa.gui_instance import GuiInstance
        except ImportError:
            self.skipTest('PySide6 non disponibile')
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'QT_QPA_PLATFORM': 'offscreen', 'XDG_RUNTIME_DIR': directory}):
            # Alcuni ambienti isolati vietano perfino i socket Unix locali.
            try:
                with socket.socket(socket.AF_UNIX) as probe:
                    probe.bind(str(Path(directory) / 'probe.sock'))
            except PermissionError:
                self.skipTest('Socket Unix locali vietati da questo ambiente')
            app = QApplication.instance() or QApplication([])
            path = Path(directory) / 'gui.sock'
            first = GuiInstance(path)
            activations = []
            first.activated.connect(lambda: activations.append(True))
            self.assertTrue(first.acquire())
            script = '''
import sys, os
from PySide6.QtCore import QCoreApplication
from kapa.gui_instance import GuiInstance
app = QCoreApplication([])
instance = GuiInstance(sys.argv[1])
print(instance.acquire(), flush=True)
if len(sys.argv) > 2:
    os._exit(0)
instance.close()
'''
            children = []
            try:
                for _ in range(3):
                    children.append(subprocess.Popen(
                        [sys.executable, '-B', '-c', script, str(path)],
                        cwd=Path(__file__).resolve().parents[1],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
                for child in children:
                    output, error = child.communicate(timeout=10)
                    self.assertEqual(child.returncode, 0, error)
                    self.assertEqual(output.strip(), 'False')
                deadline = time.monotonic() + 2
                while len(activations) < 3 and time.monotonic() < deadline:
                    app.processEvents()
                self.assertEqual(len(activations), 3)
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                        child.communicate()
                first.close()
            # Dopo un'uscita regolare è possibile riaprire la GUI.
            reopened = GuiInstance(path)
            try:
                self.assertTrue(reopened.acquire())
            finally:
                reopened.close()
            # Anche un crash non deve lasciare Kapa bloccato al prossimo avvio.
            crashed = subprocess.run([sys.executable, '-B', '-c', script, str(path), 'crash'],
                                     cwd=Path(__file__).resolve().parents[1],
                                     capture_output=True, text=True, timeout=10)
            self.assertEqual(crashed.returncode, 0, crashed.stderr)
            self.assertEqual(crashed.stdout.strip(), 'True')
            recovered = GuiInstance(path)
            try:
                self.assertTrue(recovered.acquire())
            finally:
                recovered.close()

    def test_refresh_and_shortcut_dialog_offscreen(self):
        try:
            import PySide6
        except ImportError:
            self.skipTest('PySide6 non disponibile')
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'QT_QPA_PLATFORM':'offscreen', 'XDG_RUNTIME_DIR':directory}):
            from kapa import gui
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance() or QApplication([])
            class Controller:
                start = Mock(return_value='Avvio automatico')
                def state(self): return 'attesa'
                def is_starting(self): return False
                def hotkey_state(self): return 'non_disponibile'
                def latest_response(self): return 'Risposta sintetica'
                def latest_activity(self):
                    return {'sentito': 'prossima traccia', 'esito': 'Risposta sintetica',
                            'percorso': 'locale', 'azioni': ['controllo_multimediale']}
                def logs(self): return 'Log sintetico'
            with patch.object(gui, 'current_shortcuts', return_value=([], False)), \
                 patch.object(gui.QSystemTrayIcon, 'isSystemTrayAvailable', return_value=False):
                window = gui.AssistantWindow(Controller())
                try:
                    window._state_future.result(timeout=2)
                    window._refresh()
                    self.assertEqual(window.last_label.text(), 'Risposta sintetica')
                    self.assertIn('prossima traccia', window.heard_label.text())
                    self.assertIn('Nessuna chiamata a Groq', window.route_label.text())
                    self.assertIn('Controllo riproduzione', window.action_label.text())
                    self.assertTrue(window.listen_btn.isEnabled())
                    window.controller.start.assert_called_once_with()
                    self.assertFalse(hasattr(window, 'start_btn'))
                    self.assertFalse(hasattr(window, 'stop_btn'))
                    window.show()
                    window.resize(140, 160)
                    app.processEvents()
                    self.assertTrue(window._compact)
                    self.assertTrue(window.listen_btn.isVisible())
                    self.assertFalse(window._scroller.isVisible())
                    self.assertEqual(window._compact_layout.indexOf(window.listen_btn), 0)
                    window.resize(490, 720)
                    app.processEvents()
                    self.assertFalse(window._compact)
                    self.assertTrue(window._scroller.isVisible())
                    self.assertTrue(window.listen_btn.isVisible())
                    self.assertEqual(window._normal_controls.indexOf(window.listen_btn), 0)
                    self.assertFalse(window.centralWidget()._background.isNull())
                    window.resize(1600, 1000)
                    self.assertLessEqual(window.width(), 560)
                    self.assertLessEqual(window.height(), 900)
                    dialog = gui.ShortcutDialog(window, window.controller)
                    self.assertIn('scorciatoia', dialog.windowTitle())
                    dialog.close()
                    # L'uscita completa arresta il demone prima di chiudere Qt.
                    calls = Mock()
                    window.controller.stop = calls.stop
                    with patch.object(window, '_exit_gui', calls.quit):
                        window._exit_all()
                    self.assertEqual(calls.mock_calls, [unittest.mock.call.stop(),
                                                       unittest.mock.call.quit()])
                    # Se l'arresto fallisce, la GUI resta disponibile per riprovare.
                    window.controller.stop = Mock(side_effect=gui.AssistantError('errore sintetico'))
                    with patch.object(window, '_exit_gui') as quit_gui, \
                         patch.object(window, '_show_window'):
                        window._exit_all()
                    quit_gui.assert_not_called()
                    self.assertIn('errore sintetico', window.info.text())
                    # Senza tray anche la X deve arrestare il demone.
                    event = Mock()
                    window.controller.stop = Mock()
                    window.closeEvent(event)
                    window.controller.stop.assert_called_once_with()
                    event.accept.assert_called_once_with()
                    # Dopo un avvio fallito resta possibile riprovare.
                    window._snapshot = (None, False, '', None, {})
                    with patch.object(window, '_start') as retry:
                        window._listen()
                    retry.assert_called_once_with()
                finally:
                    window._timer.stop()
                    window._shortcut_timer.stop()
                    window._executor.shutdown(wait=True, cancel_futures=True)
                    window._quit_gui = True
                    window.close()
