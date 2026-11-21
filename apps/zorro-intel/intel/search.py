"""Ask zorro-search (search by meaning, on this laptop) over its socket."""
import json
import socket

from . import paths


def _ask(request, timeout):
    """the service's one answer line, or None when it does not run or does not answer"""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(paths.search_socket()))
            s.sendall((json.dumps(request) + '\n').encode())
            return json.loads(s.makefile('r', encoding='utf-8').readline())
    except (OSError, ValueError):
        return None


def ask(text, n=30, timeout=5):
    """[{path, title, score, snippet, kind}], best first; None when the service does not run"""
    hits = _ask({'q': text, 'n': n}, timeout)
    if not isinstance(hits, list):
        return None
    return [h for h in hits if isinstance(h, dict) and isinstance(h.get('path'), str)]


def running():
    return isinstance(_ask({'cmd': 'status'}, 3), dict)
