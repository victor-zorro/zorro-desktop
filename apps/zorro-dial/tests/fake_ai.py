"""A small stand-in for zorro-ai that speaks its protocol (plan/SPEC.md): one JSON line in,
JSON lines out, on a unix socket. For the tests and the screenshots; never the real service.

  fake_ai.py SOCKET [seconds between replies]     serve a fixed answer until killed
"""
import json
import os
import socket
import sys
import threading
import time

ANSWER = [{'type': 'start', 'engine': 'mistral', 'model': 'fake-small', 'sent': []},
          {'type': 'note', 'text': 'Claude not reachable: answering with Mistral'},
          {'type': 'text', 'delta': 'A dial is a round face '},
          {'type': 'text', 'delta': 'with marks on it. '},
          {'type': 'text', 'delta': 'Here it holds your apps, music, notes '},
          {'type': 'text', 'delta': 'and this chat, around the clock.'},
          {'type': 'done', 'engine': 'mistral', 'seconds': 0.4}]


class FakeAi:
    def __init__(self, path, replies=None, delay=0.0):
        self.path, self.replies, self.delay = str(path), replies or ANSWER, delay
        self.requests = []                  # every request line received
        self.hung_up = threading.Event()    # a caller closed before the answer was complete
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.path)
        os.chmod(self.path, 0o600)
        self.sock.listen(8)
        self.sock.settimeout(0.2)
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while not self.stopping.is_set():
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self.answer, args=(conn,), daemon=True).start()

    def answer(self, conn):
        with conn:
            try:
                request = json.loads(conn.makefile('r', encoding='utf-8').readline())
            except ValueError:
                return
            self.requests.append(request)
            if request.get('op') != 'ask':
                conn.sendall(b'{"engines": {"mistral": {"ready": true, "why": ""}}}\n')
                return
            for reply in self.replies:
                time.sleep(self.delay)
                try:
                    conn.sendall((json.dumps(reply) + '\n').encode())
                except OSError:
                    self.hung_up.set()
                    return

    def stop(self):
        self.stopping.set()
        self.thread.join(2)
        self.sock.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass


if __name__ == '__main__':
    service = FakeAi(sys.argv[1], delay=float(sys.argv[2]) if len(sys.argv) > 2 else 0.0)
    try:
        service.thread.join()
    except KeyboardInterrupt:
        service.stop()
