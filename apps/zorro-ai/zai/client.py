"""Ask the running service: send one request, read the reply lines."""
import json
import socket

from . import paths


class NoService(Exception):
    pass


def replies(request, timeout=600):
    """The reply objects of one request, as they come in. Closing the generator cancels the answer."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(3)
        sock.connect(str(paths.socket_path()))
    except OSError as e:
        sock.close()
        raise NoService(str(e)) from e
    with sock:
        sock.settimeout(timeout)
        sock.sendall((json.dumps(request) + '\n').encode())
        for line in sock.makefile('r', encoding='utf-8'):
            yield json.loads(line)


def one(request, timeout=30):
    """the single reply of status / models / settings"""
    for reply in replies(request, timeout):
        return reply
    return None
