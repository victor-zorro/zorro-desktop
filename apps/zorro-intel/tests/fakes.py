"""Fakes for the tests: a private HOME, a fake zorro-ai and a fake zorro-search on real sockets.

  python3 tests/fakes.py     serve both in $XDG_RUNTIME_DIR until stopped (for the window tests)
"""
import json
import os
import shutil
import signal
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ENV = ('HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_RUNTIME_DIR')
MODELS = [
    {'id': 'small-1b', 'name': 'Small 1B', 'family': 'test', 'size': 0.8, 'ram': 1.4, 'installed': True,
     'good_for': 'very fast: short answers, good on battery', 'speed': '21.5 words/s on this laptop'},
    {'id': 'middle-3b', 'name': 'Middle 3B', 'family': 'test', 'size': 2.0, 'ram': 3.0, 'installed': False,
     'good_for': 'the middle: everyday questions at a comfortable speed', 'speed': 'not measured yet'},
    {'id': 'large-8b', 'name': 'Large 8B', 'family': 'test', 'size': 4.9, 'ram': 6.0, 'installed': False,
     'good_for': 'the best answers that fit this laptop; slowest', 'speed': 'not measured yet'},
]
SETTINGS = {'places': {'dialer': 'auto', 'intel': 'auto', 'devs': 'claude'},
            'local_only': False, 'local_model': None, 'local_model_battery': None}
ENGINES = {'claude': {'ready': True, 'why': '', 'model': 'claude-test'},
           'mistral': {'ready': False, 'why': 'has no key yet (put your Mistral API key in ...)', 'model': 'mistral-test'},
           'local': {'ready': False, 'why': 'has no llama-server yet (run: zorro-ai install-local)', 'model': ''}}


class SocketService:
    """A unix socket that answers each connection's one JSON line through reply(request, send)."""
    name = 'service.sock'

    def __init__(self, folder=None):
        self.path = os.path.join(folder or os.environ['XDG_RUNTIME_DIR'], self.name)
        self.requests = []
        self.stopping = threading.Event()
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.path)
        self.sock.listen(8)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while not self.stopping.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    def _client(self, conn):
        with conn:
            try:
                request = json.loads(conn.makefile('r').readline() or '{}')
                self.requests.append(request)
                self.reply(request, lambda obj: conn.sendall((json.dumps(obj) + '\n').encode()))
            except (OSError, ValueError):
                pass

    def stop(self):
        self.stopping.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
        self.thread.join(3)
        try:
            os.unlink(self.path)
        except OSError:
            pass


class FakeAI(SocketService):
    """zorro-ai's protocol. mode: answer | fallback | error | slow | hangup."""
    name = 'zorro-ai.sock'

    def __init__(self, folder=None, mode='answer', pieces=('Hello', ' from', ' the fake'), delay=0.0):
        self.mode, self.pieces, self.delay = mode, pieces, delay
        self.settings = json.loads(json.dumps(SETTINGS))
        self.engines = json.loads(json.dumps(ENGINES))
        self.models = json.loads(json.dumps(MODELS))
        self.hung_up = threading.Event()
        super().__init__(folder)

    def reply(self, request, send):
        op = request.get('op')
        if op == 'ask':
            self.ask(request, send)
        elif op == 'status':
            send({'type': 'status', 'engines': self.engines, 'models': self.models,
                  'settings': self.settings, 'on_battery': False})
        elif op == 'models':
            send({'type': 'models', 'models': self.models})
        elif op == 'settings':
            self.change(request.get('set') or {}, send)
        else:
            send({'type': 'error', 'code': 'bad_request', 'message': f'unknown op: {op}'})

    def change(self, changes, send):
        for key, value in changes.items():
            if key not in self.settings:
                send({'type': 'error', 'code': 'bad_setting', 'message': f'unknown setting: {key}'})
                return
            if key == 'places':
                self.settings['places'].update(value)
            else:
                self.settings[key] = value
        send({'type': 'settings', 'settings': self.settings})

    def ask(self, request, send):
        sent = [c['path'] for c in request.get('context') or []]
        if self.mode == 'error':
            send({'type': 'error', 'code': 'no_engine', 'message': 'Claude is not installed; Local has no model yet'})
            return
        if self.mode == 'fallback':
            send({'type': 'start', 'engine': 'claude', 'model': 'claude-test', 'sent': sent})
            send({'type': 'note', 'text': 'Claude failed (no login): answering with Mistral'})
            send({'type': 'start', 'engine': 'mistral', 'model': 'mistral-test', 'sent': sent})
            engine, model = 'mistral', 'mistral-test'
        else:
            engine, model = 'claude', 'claude-test'
            send({'type': 'start', 'engine': engine, 'model': model, 'sent': sent})
        try:
            self.speak(send)
        except OSError:
            self.hung_up.set()
            return
        if self.mode != 'hangup':
            send({'type': 'done', 'engine': engine, 'model': model + '-exact', 'seconds': 0.1})

    def speak(self, send):
        for piece in self.pieces:
            send({'type': 'text', 'delta': piece})
            time.sleep(self.delay)
        deadline = time.monotonic() + 20
        while self.mode == 'slow' and time.monotonic() < deadline and not self.stopping.is_set():
            send({'type': 'text', 'delta': ' more'})
            time.sleep(0.05)


class FakeSearch(SocketService):
    name = 'zorro-search.sock'

    def __init__(self, hits=(), folder=None):
        self.hits = list(hits)
        super().__init__(folder)

    def reply(self, request, send):
        if request.get('cmd') == 'status':
            send({'files': len(self.hits), 'pieces': len(self.hits), 'busy': False})
        else:
            send(self.hits[:int(request.get('n', 30))])


def hit(path, snippet='some words', score=0.9, kind='note'):
    return {'path': str(path), 'title': Path(path).stem, 'score': score, 'snippet': snippet, 'kind': kind}


class SandboxCase(unittest.TestCase):
    """Every test gets its own HOME and XDG folders; the user's real files are never touched."""

    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in ENV}
        self.home = Path(tempfile.mkdtemp(prefix='zin', dir='/tmp'))     # short: a socket path is at most 108 bytes
        for var, sub in (('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                         ('XDG_STATE_HOME', 'state'), ('XDG_RUNTIME_DIR', 'run')):
            (self.home / sub).mkdir(mode=0o700)
            os.environ[var] = str(self.home / sub)
        os.environ['HOME'] = str(self.home)
        self.services = []

    def tearDown(self):
        for service in self.services:
            service.stop()
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.home, ignore_errors=True)

    def fake_ai(self, **kw):
        self.services.append(FakeAI(**kw))
        return self.services[-1]

    def fake_search(self, hits=()):
        self.services.append(FakeSearch(hits))
        return self.services[-1]

    def notes(self, *names):
        """a folder `notes` with these files in it; the folder's path"""
        folder = self.home / 'notes'
        folder.mkdir(exist_ok=True)
        for name in names:
            (folder / name).write_text(f'# {name}\nwords of {name}\n')
        return folder


def wait_until(test, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if test():
            return True
        time.sleep(0.02)
    return test()


def main():
    """Both fakes in $XDG_RUNTIME_DIR, with hits for every .md under $HOME, until SIGTERM."""
    home = Path(os.environ['HOME'])
    files = sorted(home.rglob('*.md'))
    hits = [hit(p, p.read_text()[:300].replace('\n', ' '), 0.93 - 0.03 * i) for i, p in enumerate(files)]
    pieces = ['The harbour ', 'trip is planned ', 'for the second ', 'week of May. ',
              'You wrote that ', 'the ferry leaves ', 'at nine and that ', 'the bikes go along.']
    services = []
    if 'ai' not in os.environ.get('FAKES_SKIP', ''):
        services.append(FakeAI(mode=os.environ.get('FAKE_AI_MODE', 'answer'), pieces=pieces,
                               delay=float(os.environ.get('FAKE_AI_DELAY', '0.4'))))
    if 'search' not in os.environ.get('FAKES_SKIP', ''):
        services.append(FakeSearch(hits))
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    print('fakes up', flush=True)
    stop.wait(600)
    for service in services:
        service.stop()


if __name__ == '__main__':
    main()
