"""The beacon (zorro-transfer beacon): a small user service that is always on, so a new device
finds this one by itself.

It tells only three things: this device's name, the protocol (MAGIC) and whether it is
sending right now. On the local network it answers "who?" on the discovery port (UDP); for
NetBird peers, which a broadcast does not reach, it answers on a TCP port of its own:

  {"op": "probe"}                 -> {"name": ..., "magic": ..., "sending": true|false}
  {"op": "knock", "name": "PC"}   -> {"ok": true} or {"ok": false, "error": ...}

A knock shows a notification here ("PC wants this device's setup"); its Send button opens
the Transfer window, nothing more. It never starts sending and never tells the code. Only
devices on a private network, NetBird or this device get an answer; requests are small,
slow ones are dropped, a few connections at a time."""
import html
import ipaddress
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time

from . import net, state

MAX_REQUEST = 512               # bytes of JSON in one request
MAX_CONNECTIONS = 8             # served at the same time; more are closed at once
TIMEOUT = 3                     # seconds for a whole request to arrive
KNOCK_EACH = 60                 # seconds before the same device may knock again
KNOCK_ALL = 3                   # notifications per minute, from everyone together
KNOCK_SHOWN = 120               # seconds a notification waits for a choice
NETBIRD = ipaddress.ip_network('100.64.0.0/10')


def private(addr):
    """an address on a private network, NetBird or this device"""
    try:
        ip = ipaddress.ip_address(addr.split('%')[0])
    except (ValueError, AttributeError):
        return False
    ip = getattr(ip, 'ipv4_mapped', None) or ip
    return ip.is_private or ip.is_loopback or ip in NETBIRD


def sending():
    """is Transfer sending on this device right now?"""
    st = state.read_state('sender.json')
    return state.is_transfer(st.get('pid')) and st.get('status') != 'stopped'


def about():
    return {'name': state.device_name(), 'magic': net.MAGIC.decode(), 'sending': sending()}


def clean_name(name):
    """the asker's name as it may be shown: printable, at most 64 characters, or ''"""
    if not isinstance(name, str):
        return ''
    return ''.join(c for c in name if c.isprintable()).strip()[:64]


def read_request(conn):
    """one length-prefixed JSON request, whole within TIMEOUT; ValueError or OSError if not"""
    end = time.monotonic() + TIMEOUT
    buf = b''
    while True:
        need = 4 + int.from_bytes(buf[:4], 'big') if len(buf) >= 4 else 4
        if need > 4 + MAX_REQUEST:
            raise ValueError('request too big')
        if len(buf) >= 4 and len(buf) == need:
            return json.loads(buf[4:])
        left = end - time.monotonic()
        if left <= 0:
            raise TimeoutError('request too slow')
        conn.settimeout(left)
        chunk = conn.recv(need - len(buf))
        if not chunk:
            raise ConnectionError('closed')
        buf += chunk


class Knocks:
    """how often others may make this device show a notification"""

    def __init__(self):
        self.lock = threading.Lock()
        self.last, self.recent = {}, []

    def allow(self, who, now):
        with self.lock:
            self.recent = [t for t in self.recent if now - t < 60]
            self.last = {k: t for k, t in self.last.items() if now - t < KNOCK_EACH}
            if who in self.last or len(self.recent) >= KNOCK_ALL:
                return False
            self.last[who] = now
            self.recent.append(now)
            return True


def send_command():
    """what the notification's Send button runs: the Transfer window, on the sending side"""
    return [os.path.realpath(sys.argv[0]), '--send']


def desktop_env():
    """a service may lack the screen's DISPLAY; the session manager knows it"""
    env = dict(os.environ)
    if not env.get('DISPLAY'):
        try:
            out = subprocess.run(['systemctl', '--user', 'show-environment'], capture_output=True,
                                 text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            out = ''
        for line in out.splitlines():
            key, _, value = line.partition('=')
            if key in ('DISPLAY', 'XAUTHORITY') and value:
                env[key] = value
        env.setdefault('DISPLAY', ':0')
    return env


def ask_user(name):
    """the notification; its Send button opens Transfer (the user then reads out the code)"""
    title = html.escape(f"{name} wants this device's setup", quote=False)    # dunst: markup
    body = 'Open Transfer to send it.'
    base = ['notify-send', '-a', 'Transfer', '-i', 'folder-remote', '-t', str(KNOCK_SHOWN * 1000)]
    try:
        r = subprocess.run(base + ['--action=send=Send', '--wait', '--', title, body],
                           capture_output=True, text=True, timeout=KNOCK_SHOWN + 5)
        if r.returncode != 0:           # an older notify-send without actions
            subprocess.run(base + ['--', title, body], capture_output=True, timeout=10)
        elif r.stdout.strip() == 'send':
            subprocess.Popen(send_command(), env=desktop_env(), start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        pass


class Beacon:
    def __init__(self):
        self.stop = threading.Event()
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self.knocks = Knocks()

    def reply(self, req, peer):
        """the answer to one request, None for no answer at all"""
        if not private(peer) or not isinstance(req, dict):
            return None
        op = req.get('op')
        if op == 'probe' and len(req) == 1:
            return about()
        if op == 'knock' and set(req) == {'op', 'name'}:
            return self.knock(clean_name(req.get('name')), peer)
        return None

    def knock(self, name, peer):
        if not name:
            return None
        if sending():
            return {'ok': True}         # it already sends: the asker sees that on its list
        if not self.knocks.allow(peer, time.monotonic()):
            return {'ok': False, 'error': 'already asked: try again in a minute'}
        threading.Thread(target=ask_user, args=(name,), daemon=True).start()
        return {'ok': True}

    def handle(self, conn, peer):
        try:
            answer = self.reply(read_request(conn), peer)
            if answer is not None:
                conn.settimeout(TIMEOUT)
                net.send_json(conn, answer)
        except (OSError, ValueError):
            pass                        # malformed, too big or too slow: no answer
        finally:
            conn.close()
            self.slots.release()

    def serve_tcp(self, srv):
        while not self.stop.is_set():
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:             # out of file handles, say: a moment's rest
                time.sleep(0.5)
                continue
            peer = addr[0][7:] if addr[0].startswith('::ffff:') else addr[0]
            if not private(peer) or not self.slots.acquire(blocking=False):
                conn.close()
                continue
            threading.Thread(target=self.handle, args=(conn, peer), daemon=True).start()

    def serve_udp(self, u):
        while not self.stop.is_set():
            try:
                data, addr = u.recvfrom(MAX_REQUEST)
                if data == net.WHO and private(addr[0]):
                    u.sendto(json.dumps(about()).encode(), addr)
            except socket.timeout:
                pass
            except OSError:
                time.sleep(0.2)

    def run(self):
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: self.stop.set())
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)    # no REUSE: the only responder
        u.bind(('', net.DISCOVER_PORT))
        u.settimeout(1)
        srv = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        srv.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)     # IPv4 too
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('::', net.BEACON_PORT))
        srv.listen(MAX_CONNECTIONS)
        srv.settimeout(1)
        state.write_state('beacon.json', {'pid': os.getpid(), 'name': state.device_name(),
                                          'port': net.BEACON_PORT, 'started': time.time()})
        udp = threading.Thread(target=self.serve_udp, args=(u,), daemon=True)
        udp.start()
        try:
            self.serve_tcp(srv)
        finally:
            self.stop.set()
            udp.join(3)
            srv.close()
            u.close()
            (state.STATE / 'beacon.json').unlink(missing_ok=True)
