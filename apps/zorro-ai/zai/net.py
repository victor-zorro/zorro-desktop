"""Is a host reachable? Decided by one short TCP connect, remembered for half a minute."""
import socket
import threading
import time

TIMEOUT = 2.0
KEEP = 30.0
_seen = {}
_lock = threading.Lock()


def _connects(host, port, result):
    try:
        socket.create_connection((host, port), timeout=TIMEOUT).close()
        result.append(True)
    except OSError:
        result.append(False)


def reachable(host, port=443):
    now = time.monotonic()
    with _lock:
        seen = _seen.get((host, port))
        if seen and now - seen[0] < KEEP:
            return seen[1]
    result = []
    probe = threading.Thread(target=_connects, args=(host, port, result), daemon=True)
    probe.start()
    probe.join(TIMEOUT)             # a slow name lookup counts as not reachable
    ok = bool(result and result[0])
    with _lock:
        _seen[(host, port)] = (now, ok)
    return ok


def forget():
    with _lock:
        _seen.clear()
