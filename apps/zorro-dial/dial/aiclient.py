"""Asking zorro-ai: one request per connection on its unix socket, JSON lines back."""
import json
import os
import socket
import threading
from pathlib import Path

CONNECT_LIMIT = 3                       # seconds
QUIET_LIMIT = 180                       # seconds without a line from the service: give up
NO_SERVICE = 'The AI service is not running.'


def socket_path():
    return Path(os.environ.get('XDG_RUNTIME_DIR') or '/tmp') / 'zorro-ai.sock'


def connect(path=None):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(CONNECT_LIMIT)
        sock.connect(str(path or socket_path()))
    except OSError:
        sock.close()
        raise
    return sock


def available(path=None):
    """does the service answer? (its status op; call it in a thread)"""
    try:
        with connect(path) as sock:
            sock.sendall(b'{"op": "status"}\n')
            return bool(sock.makefile('r', encoding='utf-8').readline().strip())
    except (OSError, ValueError):
        return False


class Ask:
    """One question. The replies (start, text, note, done, error) go to on_event from a thread
    of its own; cancel() closes the connection, which stops the answer at the service."""

    def __init__(self, messages, on_event, path=None, place='dialer'):
        self.request = {'op': 'ask', 'place': place, 'messages': messages, 'context': [],
                        'engine': None}
        self.on_event = on_event
        self.path = path
        self.sock = None
        self.cancelled = False
        self.lock = threading.Lock()

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()
        return self

    def cancel(self):
        with self.lock:
            self.cancelled = True
            sock = self.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def tell(self, event):
        if not self.cancelled:
            self.on_event(event)

    def run(self):
        try:
            sock = connect(self.path)
        except OSError:
            self.tell({'type': 'error', 'code': 'no_service', 'message': NO_SERVICE})
            return
        with self.lock:
            self.sock = sock
        with sock:
            if not self.cancelled:
                self.tell(self.read(sock))

    def read(self, sock):
        """pass the replies on as they come; the last one (done or error) is returned"""
        try:
            sock.settimeout(QUIET_LIMIT)
            sock.sendall((json.dumps(self.request) + '\n').encode())
            for line in sock.makefile('r', encoding='utf-8'):
                event = json.loads(line)
                if not isinstance(event, dict):
                    continue
                if event.get('type') in ('done', 'error'):
                    return event
                self.tell(event)
        except (OSError, ValueError) as e:
            return {'type': 'error', 'code': 'lost', 'message': f'The answer stopped: {e}'}
        return {'type': 'error', 'code': 'lost', 'message': 'The answer stopped early.'}
