"""Una sola GUI per utente, con richiamo della finestra già aperta."""
from pathlib import Path
import time

from PySide6.QtCore import QObject, QLockFile, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .app_paths import SOCKET_PATH


class GuiInstance(QObject):
    activated = Signal()

    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.path = Path(path) if path is not None else SOCKET_PATH.with_name('kapa-gui.sock')
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = QLockFile(str(self.path) + '.lock')
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._activate)
        self._owner = False

    def acquire(self):
        if not self.lock.tryLock(0):
            if self.lock.error() != QLockFile.LockError.LockFailedError:
                raise RuntimeError('Impossibile verificare le istanze aperte di Kapa.')
            # La prima GUI potrebbe avere il lock ma non aver ancora aperto il server.
            for _ in range(30):
                client = QLocalSocket()
                client.connectToServer(str(self.path))
                if client.waitForConnected(100):
                    client.disconnectFromServer()
                    return False
                time.sleep(0.05)
            raise RuntimeError('Kapa è già aperto, ma la finestra non risponde. Riprova tra poco.')
        self._owner = True
        # Solo il proprietario del lock può rimuovere un socket rimasto dopo un crash.
        QLocalServer.removeServer(str(self.path))
        if not self.server.listen(str(self.path)):
            error = self.server.errorString()
            self.close()
            raise RuntimeError(f'Impossibile predisporre il controllo di istanza unica: {error}')
        return True

    def _activate(self):
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            client.close()
            client.deleteLater()
            self.activated.emit()

    def close(self):
        if self._owner:
            self.server.close()
            self.lock.unlock()
            self._owner = False
