"""Controllo locale OBS WebSocket 5; nessuna modifica a scene o profili."""
import base64
import hashlib
import json
import shutil
import subprocess
import time
import uuid

from . import config


class ObsError(Exception):
    pass


def comando_obs():
    if shutil.which('obs'):
        return ['obs']
    if shutil.which('flatpak'):
        try:
            result = subprocess.run(['flatpak', 'info', 'com.obsproject.Studio'],
                                    capture_output=True, timeout=3)
            if result.returncode == 0:
                return ['flatpak', 'run', 'com.obsproject.Studio']
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


class ObsSession:
    """Una connessione per cattura: se OBS riparte non controlliamo la nuova istanza."""
    def __init__(self):
        try:
            from websocket import create_connection
        except ImportError:
            raise ObsError('Manca websocket-client: aggiorna le dipendenze con pip install -r requirements.txt.') from None
        self.ws = None
        try:
            port = int(config.OBS_PORT)
            if not 1 <= port <= 65535:
                raise ValueError
            url = f'ws://127.0.0.1:{port}'
            try:
                self.ws = create_connection(url, timeout=3, http_no_proxy=['127.0.0.1'])
            except ConnectionRefusedError:
                command = comando_obs()
                if not command:
                    raise ObsError('OBS non è installato o non è raggiungibile.')
                subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                for _ in range(12):
                    time.sleep(0.5)
                    try:
                        self.ws = create_connection(url, timeout=1, http_no_proxy=['127.0.0.1'])
                        break
                    except ConnectionRefusedError:
                        continue
                if self.ws is None:
                    raise ObsError('OBS è stato aperto: abilita il server WebSocket in Strumenti e riprova.')
            hello = self._receive()
            if hello.get('op') != 0:
                raise ObsError('Il server OBS non usa WebSocket 5 (serve OBS 28 o successivo).')
            identify = {'rpcVersion': 1, 'eventSubscriptions': 0}
            auth = hello['d'].get('authentication')
            if auth:
                if not config.OBS_PASSWORD:
                    raise ObsError('Imposta OBS_PASSWORD nel file .env con la password WebSocket di OBS e riavvia Kapa.')
                secret = base64.b64encode(hashlib.sha256((config.OBS_PASSWORD + auth['salt']).encode()).digest())
                identify['authentication'] = base64.b64encode(hashlib.sha256(secret + auth['challenge'].encode()).digest()).decode()
            self.ws.send(json.dumps({'op': 1, 'd': identify}))
            if self._receive().get('op') != 2:
                raise ObsError('Autenticazione OBS fallita: controlla OBS_PASSWORD e la porta WebSocket.')
        except Exception as exc:
            self.close()
            if isinstance(exc, ObsError):
                raise
            raise ObsError('Collegamento OBS fallito: controlla il server WebSocket, OBS_PORT e OBS_PASSWORD nel file .env.') from None

    def _receive(self):
        return json.loads(self.ws.recv())

    def call(self, name):
        request_id = str(uuid.uuid4())
        try:
            self.ws.send(json.dumps({'op': 6, 'd': {'requestType': name, 'requestId': request_id}}))
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                response = self._receive()
                data = response.get('d', {})
                if response.get('op') != 7 or data.get('requestId') != request_id:
                    continue
                status = data['requestStatus']
                if not status['result']:
                    raise ObsError(f'OBS ha rifiutato {name} (codice {status.get("code")}). Controlla le impostazioni di registrazione o replay in OBS.')
                return data.get('responseData', {})
            raise ObsError('OBS non ha risposto in tempo; verifica la cattura in OBS prima di riprovare.')
        except ObsError:
            raise
        except Exception:
            raise ObsError('Collegamento OBS interrotto: verifica la cattura in OBS prima di riprovare.') from None

    def close(self):
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass
