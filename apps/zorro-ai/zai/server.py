"""The unix socket: one request per connection, JSON lines; a caller that hangs up cancels its answer."""
import json
import os
import select
import socket
import threading

from . import paths, service

REQUEST_LIMIT = 16 << 20        # bytes of one request line
READ_TIMEOUT = 10
WRITE_TIMEOUT = 30


class Server:
    def __init__(self, engines, path=None):
        self.engines = engines
        self.path = str(path or paths.socket_path())
        self.sock = None
        self.stopping = threading.Event()
        self.answering = set()          # the stop signals of the answers running now

    def bind(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old = os.umask(0o177)
        try:
            self.sock.bind(self.path)
        finally:
            os.umask(old)
        os.chmod(self.path, 0o600)
        self.sock.listen(16)

    def serve(self):
        """Answer callers until stop() is called."""
        while not self.stopping.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                break
            threading.Thread(target=self.client, args=(conn,), daemon=True).start()
        self.close()

    def stop(self):
        self.stopping.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)      # wakes accept()
        except OSError:
            pass

    def close(self):
        try:
            self.sock.close()
            os.unlink(self.path)
        except OSError:
            pass
        for stop_event in list(self.answering):       # answers still running end with the service
            stop_event.set()
        local = self.engines.get('local')
        if local is not None:
            local.shutdown()

    def client(self, conn):
        stop_event, finished = threading.Event(), threading.Event()
        self.answering.add(stop_event)
        write_lock = threading.Lock()

        def send(obj):
            try:
                with write_lock:
                    conn.sendall((json.dumps(obj, ensure_ascii=False) + '\n').encode())
            except OSError:
                stop_event.set()

        with conn:
            try:
                conn.settimeout(READ_TIMEOUT)
                line = conn.makefile('rb').readline(REQUEST_LIMIT)
                request = json.loads(line)
            except (OSError, ValueError):
                send({'type': 'error', 'code': 'bad_request', 'message': 'expected one JSON line'})
                return
            conn.settimeout(WRITE_TIMEOUT)
            threading.Thread(target=watch_hangup, args=(conn, stop_event, finished), daemon=True).start()
            try:
                service.handle(request, send, stop_event, self.engines)
            except Exception as e:      # noqa: BLE001 - one bad request must not end the service
                send({'type': 'error', 'code': 'internal', 'message': f'{type(e).__name__}: {e}'})
            finally:
                self.answering.discard(stop_event)
                finished.set()
                hang_up(conn)


def hang_up(conn):
    """End the connection now; this also wakes watch_hangup."""
    try:
        conn.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def watch_hangup(conn, stop_event, finished):
    """Set stop_event when the caller closes the connection before the answer is finished.
    A caller that only closes its sending side keeps its answer."""
    poller = select.poll()
    try:
        poller.register(conn.fileno(), select.POLLHUP | select.POLLERR)
        while not finished.is_set():
            if poller.poll(5000) and not finished.is_set():
                stop_event.set()
                return
    except (OSError, ValueError):
        return
