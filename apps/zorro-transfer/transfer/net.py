"""Transfer's wire: pairing with a short code, then an encrypted connection.

Pairing: the receiver types the 6-digit code the sender shows. SPAKE2 (as in magic-wormhole)
turns that short code into a strong shared key: someone who listens in learns nothing, and a
wrong guess costs a whole new try (the sender allows one try at a time, PAIR_TIME at most,
and makes the device that guessed wrong wait longer each time). The key
becomes the pre-shared key of a TLS 1.3 connection (no certificates needed: only the two who
know the code can finish the handshake). After pairing, the sender hands out a session secret
so an interrupted transfer continues without a new code.

Messages are length-prefixed frames: JSON for requests, raw bytes for file data."""
import hashlib
import hmac
import json
import os
import socket
import ssl
import struct
import sys
import threading
from pathlib import Path

from . import check

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'zorro-fx'))
import zorro_net  # noqa: E402  (who may use the small servers on this device)

# the sender listens on PORT (LAN and NetBird); the beacon answers "who is a Zorro device?"
# on the next one (UDP, the local network) and on the one after (TCP, NetBird peers). The
# variable moves all three (tests).
PORT = int(os.environ.get('ZORRO_TRANSFER_PORT') or 47820)
DISCOVER_PORT = PORT + 1
BEACON_PORT = PORT + 2
MAGIC = b'zorro-transfer/2'
WHO = MAGIC + b' who?'           # the question on the discovery port
IDLE = 60                       # seconds a side waits for the other's next message
SMALL_FRAME = 4096              # bytes: what may arrive before pairing (hello, SPAKE2)


class TooOld(Exception):
    """this Python cannot do TLS with a pre-shared key"""


def need_psk():
    """TLS 1.3 with a pre-shared key came with Python 3.13 (Ubuntu 24.04 has 3.12)"""
    if not hasattr(ssl.SSLContext, 'set_psk_server_callback'):
        have = '.'.join(map(str, sys.version_info[:2]))
        raise TooOld(f'Transfer needs Python 3.13 or newer; this device has {have}.')


def trusted(addr):
    """may this address talk to the sender and the beacon? (tests replace this one function)"""
    return zorro_net.trusted(addr)


class Deadline:
    """closes a connection when its time is up, however slowly the bytes drip in"""

    def __init__(self, sock, seconds):
        self.watch = socket.socket(fileno=os.dup(sock.fileno()))
        self.lock, self.over = threading.Lock(), False
        self.timer = threading.Timer(seconds, self.expire)
        self.timer.daemon = True
        self.timer.start()
        sock.settimeout(seconds)

    def expire(self):
        with self.lock:
            if not self.over:
                self.over = True
                try:
                    self.watch.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self.watch.close()

    def cancel(self):
        """stop watching; True when it was still in time"""
        self.timer.cancel()
        with self.lock:
            in_time, self.over = not self.over, True
            if in_time:
                self.watch.close()
        return in_time


def patience(offset):
    """how long to wait for a file that continues at offset: the other side first reads
    (and checks) what came before"""
    return IDLE + offset // (10 << 20)


def send_frame(sock, data):
    sock.sendall(struct.pack('>I', len(data)) + data)


def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(min(n - len(buf), 1 << 20))
        if not chunk:
            raise ConnectionError('the other side closed the connection')
        buf += chunk
    return bytes(buf)


def recv_frame(sock, limit=64 << 20):
    n, = struct.unpack('>I', recv_exact(sock, 4))
    if n > limit:
        raise ConnectionError('frame too big')
    return recv_exact(sock, n)


def send_json(sock, obj):
    send_frame(sock, json.dumps(obj).encode())


def recv_json(sock, limit=64 << 20):
    """the one place messages are read: anything that is not a JSON object is a bad peer"""
    data = recv_frame(sock, limit)
    try:
        msg = json.loads(data.decode())
    except (ValueError, RecursionError, MemoryError):
        msg = None
    if not isinstance(msg, dict):
        raise check.BadPeer(check.ODD + ' (message)')
    return msg


def kdf(key, label):
    return hmac.new(key, MAGIC + b' ' + label.encode(), hashlib.sha256).digest()


def spake(code, side, sock):
    """SPAKE2 over the plain socket; side 'A' (receiver) or 'B' (sender): the shared key"""
    from spake2 import SPAKE2_A, SPAKE2_B
    s = (SPAKE2_A if side == 'A' else SPAKE2_B)(code.encode(), idA=b'receiver', idB=b'sender')
    send_frame(sock, s.start())
    return s.finish(recv_frame(sock, limit=SMALL_FRAME))


def _ctx(server, psk):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if server else ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.set_ciphers('PSK')                  # TLS 1.2 fallback never happens (minimum 1.3)
    if server:
        ctx.set_psk_server_callback(lambda identity: psk if identity == 'zorro-transfer' else b'')
    else:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE     # no certificates: the PSK proves who is who
        ctx.set_psk_client_callback(lambda hint: ('zorro-transfer', psk))
    return ctx


def secure(sock, key, server):
    """wrap the socket in TLS 1.3 with a key from pairing or the session secret"""
    need_psk()
    psk = kdf(key, 'tls')
    return _ctx(server, psk).wrap_socket(sock, server_side=server)


def connect(host, port=PORT, timeout=8):
    s = socket.create_connection((host, port), timeout=timeout)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return s
