"""llama-server, started when a local answer is wanted and stopped after some idle minutes."""
import http.client
import os
import secrets
import socket
import subprocess
import threading
import time

from . import paths

IDLE = 300              # seconds without a question before the model leaves RAM
LOAD_DEADLINE = 180     # seconds a model may take to load
CONTEXT = 4096


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def healthy(port):
    try:
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
        conn.request('GET', '/health')
        ok = conn.getresponse().status == 200
        conn.close()
        return ok
    except (OSError, http.client.HTTPException):
        return False


class LlamaServer:
    def __init__(self, idle=IDLE):
        self.idle = idle
        self.lock = threading.Lock()
        self.proc = None
        self.model = None
        self.port = None
        self.key = None
        self.timer = None

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def ensure(self, binary, model_file, stop_event):
        """Have llama-server up with this model; (port, key), or None when stopped or it did not load."""
        with self.lock:
            self._cancel_timer()
            if self.running() and self.model == str(model_file):
                return self.port, self.key
            self._stop()
            self._start(binary, model_file)
            if self._wait_loaded(stop_event):
                return self.port, self.key
            self._stop()
            return None

    def _start(self, binary, model_file):
        self.port, self.key = free_port(), secrets.token_hex(16)
        paths.data_dir().mkdir(parents=True, exist_ok=True)
        log = open(paths.data_dir() / 'llama-server.log', 'w')
        args = [binary, '-m', str(model_file), '--host', '127.0.0.1', '--port', str(self.port),
                '-c', str(CONTEXT), '-np', '1', '--no-webui']
        env = {**os.environ, 'LLAMA_API_KEY': self.key}
        self.proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env)
        log.close()
        self.model = str(model_file)

    def _wait_loaded(self, stop_event):
        deadline = time.monotonic() + LOAD_DEADLINE
        while time.monotonic() < deadline and self.running():
            if healthy(self.port):
                return True
            if stop_event.wait(0.3):
                return False
        return False

    def released(self):
        """An answer is over: stop the server after the idle time."""
        with self.lock:
            self._cancel_timer()
            self.timer = threading.Timer(self.idle, self.stop)
            self.timer.daemon = True
            self.timer.start()

    def stop(self):
        with self.lock:
            self._cancel_timer()
            self._stop()

    def _cancel_timer(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None

    def _stop(self):
        proc, self.proc, self.model = self.proc, None, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(5)
