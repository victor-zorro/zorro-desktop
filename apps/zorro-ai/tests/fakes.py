"""Fakes for the tests: a private HOME, a fake engine, a fake Mistral, fake claude and llama-server programs."""
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zai import net  # noqa: E402
from zai.engines import EngineError  # noqa: E402
from zai.server import Server  # noqa: E402

ENV = ('HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_RUNTIME_DIR', 'PATH')


class SandboxCase(unittest.TestCase):
    """Every test gets its own HOME and XDG folders; the user's real files are never touched."""

    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in ENV}
        self.home = Path(tempfile.mkdtemp(prefix='zai', dir='/tmp'))    # short: a socket path is at most 108 bytes
        for var, sub in (('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_RUNTIME_DIR', 'run')):
            (self.home / sub).mkdir(mode=0o700)
            os.environ[var] = str(self.home / sub)
        os.environ['HOME'] = str(self.home)
        self.online = set()
        self.real_reachable = net.reachable
        net.reachable = lambda host, port=443: host in self.online
        self.cleanups = []

    def tearDown(self):
        for undo in reversed(self.cleanups):
            undo()
        net.reachable = self.real_reachable
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.home, ignore_errors=True)

    def serve(self, engines):
        server = Server(engines)
        server.bind()
        thread = threading.Thread(target=server.serve, daemon=True)
        thread.start()

        def stop():
            server.stop()
            thread.join(5)
        self.cleanups.append(stop)
        return server


class FakeEngine:
    def __init__(self, name, ready=True, host=None, pieces=('Hello', ' world'), fail=None, endless=False):
        self.name, self.title, self.host = name, name.capitalize(), host
        self.is_ready, self.pieces, self.fail, self.endless = ready, pieces, fail, endless
        self.asked, self.forced = [], None
        self.stopped = threading.Event()

    def model(self):
        return self.forced or f'{self.name}-model'

    def use(self, model_id):
        self.forced = model_id
        return self

    def ready(self):
        return (True, '') if self.is_ready else (False, 'is not set up')

    def ask(self, messages, context, on_text, stop_event):
        self.asked.append((messages, context))
        if self.fail:
            raise EngineError(self.fail)
        for piece in self.pieces:
            on_text(piece)
        if self.endless:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not stop_event.wait(0.05):
                on_text('.')
            if stop_event.is_set():
                self.stopped.set()
        return self.model()

    def shutdown(self):
        pass


def ask_socket(request, path=None):
    """an open connection with the request sent, and its line reader"""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect(path or os.path.join(os.environ['XDG_RUNTIME_DIR'], 'zorro-ai.sock'))
    sock.sendall((json.dumps(request) + '\n').encode())
    return sock, sock.makefile('r', encoding='utf-8')


def exchange(request):
    """all reply lines of one request"""
    sock, lines = ask_socket(request)
    with sock, lines:
        return [json.loads(line) for line in lines]


def wait_until(test, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if test():
            return True
        time.sleep(0.05)
    return test()


def alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] != 'Z'
    except OSError:
        return False


class FakeMistral:
    """A small HTTP server that speaks Mistral's streaming chat-completions shape."""
    KEY = 'test-key-not-real'

    def __init__(self):
        fake = self
        self.requests, self.hung_up = [], threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fake.requests.append({'path': self.path, 'headers': dict(self.headers), 'body': body})
                if self.headers.get('Authorization') != f'Bearer {fake.KEY}':
                    self._json(401, {'message': 'Unauthorized'})
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                slow = 'SLOW' in body['messages'][-1]['content']
                try:
                    for piece in ['Bon', 'jour'] + ['.'] * (60 if slow else 0):
                        self._event({'model': 'mistral-small-2506', 'choices': [{'index': 0, 'delta': {'content': piece}}]})
                        if slow:
                            time.sleep(0.05)
                    self._event({'model': 'mistral-small-2506', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})
                    self.wfile.write(b'data: [DONE]\n\n')
                except OSError:
                    fake.hung_up.set()

            def _event(self, obj):
                self.wfile.write(f'data: {json.dumps(obj)}\n\n'.encode())
                self.wfile.flush()

            def _json(self, code, obj):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.httpd.daemon_threads = True
        self.url = f'http://127.0.0.1:{self.httpd.server_address[1]}/v1/chat/completions'
        threading.Thread(target=self.httpd.serve_forever, args=(0.05,), daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


FAKE_CLAUDE = r'''#!/usr/bin/python3
import json, os, sys, time
log = os.environ["FAKE_LOG"]
prompt = sys.stdin.read()
with open(log, "a") as f:
    f.write(json.dumps({"pid": os.getpid(), "argv": sys.argv[1:], "cwd_files": os.listdir("."), "prompt": prompt}) + "\n")
def out(obj):
    print(json.dumps(obj), flush=True)
def delta(text):
    out({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}})
out({"type": "system", "subtype": "init", "model": "claude-fake-1", "tools": [], "mcp_servers": []})
out({"type": "stream_event", "event": {"type": "message_start"}})
if "FAIL" in prompt:
    out({"type": "result", "subtype": "error", "is_error": True, "result": "Not logged in"})
    sys.exit(1)
delta("O")
delta("K")
if "SLOW" in prompt:
    for _ in range(200):
        time.sleep(0.05)
        delta(".")
out({"type": "assistant", "message": {"content": [{"type": "text", "text": "OK"}]}})
out({"type": "result", "subtype": "success", "is_error": False, "result": "OK"})
'''

FAKE_LLAMA = r'''#!/usr/bin/python3
import json, os, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
args = sys.argv[1:]
model = os.path.basename(args[args.index("-m") + 1])
port = int(args[args.index("--port") + 1])
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps({"pid": os.getpid(), "model": model}) + "\n")
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def do_GET(self):
        self.send_response(200 if self.path == "/health" else 404)
        self.send_header("Content-Length", "0")
        self.end_headers()
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        if self.headers.get("Authorization") != "Bearer " + os.environ.get("LLAMA_API_KEY", ""):
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for piece in ["from ", model]:
            self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": piece}}]}) + "\n\n").encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
HTTPServer(("127.0.0.1", port), Handler).serve_forever()
'''


def write_program(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)
    return path


def read_log(path):
    try:
        return [json.loads(line) for line in Path(path).read_text().splitlines()]
    except OSError:
        return []
