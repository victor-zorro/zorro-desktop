"""Transfer's wire: pairing with a short code, then an encrypted connection.

Pairing: the receiver types the 6-digit code the sender shows. SPAKE2 (as in magic-wormhole)
turns that short code into a strong shared key: someone who listens in learns nothing, and a
wrong guess costs a whole new try (the sender makes a new code after 3 wrong ones). The key
becomes the pre-shared key of a TLS 1.3 connection (no certificates needed: only the two who
know the code can finish the handshake). After pairing, the sender hands out a session secret
so an interrupted transfer continues without a new code.

Messages are length-prefixed frames: JSON for requests, raw bytes for file data."""
import hashlib
import hmac
import json
import socket
import ssl
import struct

PORT = 47820                    # the sender listens here (LAN and NetBird)
DISCOVER_PORT = 47821           # UDP: "who sends?" on the local network
MAGIC = b'zorro-transfer/1'


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


def recv_json(sock):
    return json.loads(recv_frame(sock).decode())


def kdf(key, label):
    return hmac.new(key, MAGIC + b' ' + label.encode(), hashlib.sha256).digest()


def spake(code, side, sock):
    """SPAKE2 over the plain socket; side 'A' (receiver) or 'B' (sender): the shared key"""
    from spake2 import SPAKE2_A, SPAKE2_B
    s = (SPAKE2_A if side == 'A' else SPAKE2_B)(code.encode(), idA=b'receiver', idB=b'sender')
    send_frame(sock, s.start())
    return s.finish(recv_frame(sock, limit=4096))


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
    psk = kdf(key, 'tls')
    return _ctx(server, psk).wrap_socket(sock, server_side=server)


def connect(host, port=PORT, timeout=8):
    s = socket.create_connection((host, port), timeout=timeout)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return s
