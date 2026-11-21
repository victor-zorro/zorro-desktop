"""What the tests share: two made-up devices in a temporary folder, each with its own home,
state and stand-in tools, talking over localhost on a port of their own."""
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from transfer import net  # noqa: E402

HOST = '127.0.0.1'


def free_port():
    """a TCP port whose neighbour (the UDP one) is free too"""
    for _ in range(50):
        port = random.randrange(20000, 40000, 2)
        try:
            with socket.socket() as a, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as b:
                a.bind((HOST, port))
                b.bind((HOST, port + 1))
            return port
        except OSError:
            continue
    raise RuntimeError('no free port')


def wait_for(check, seconds=15, what='it'):
    end = time.time() + seconds
    while time.time() < end:
        got = check()
        if got:
            return got
        time.sleep(0.05)
    raise AssertionError(f'waited {seconds} s for {what}')


class Side:
    """one device: a home folder, state, and the command line run with stand-ins"""

    def __init__(self, root, name, port, **cfg):
        self.root, self.name, self.port = root / name, name, port
        self.home = self.root / 'home'
        self.state_dir = self.root / 'state' / 'zorro-transfer'
        self.stage = self.root / 'data' / 'zorro-transfer'
        self.home.mkdir(parents=True)
        self.nm = self.root / 'nm.json'
        self.helper_log = self.root / 'helper.json'
        self.cfg = dict({'helper': str(HERE / 'bin/helper'), 'running': str(self.root / 'running'),
                         'RETRY_PAUSE': 0.2, 'APPS_POLL': 0.2}, **cfg)
        self.procs = []

    def env(self):
        return {'HOME': str(self.home), 'XDG_STATE_HOME': str(self.root / 'state'),
                'XDG_DATA_HOME': str(self.root / 'data'), 'PATH': f'{HERE}/bin:/usr/bin:/bin',
                'ZORRO_TRANSFER_PORT': str(self.port), 'ZORRO_TRANSFER_NAME': self.name,
                'ZT_TEST': json.dumps(self.cfg), 'ZT_NM': str(self.nm),
                'ZT_HELPER_LOG': str(self.helper_log), 'LANG': 'C.UTF-8'}

    def start(self, *args):
        p = subprocess.Popen([sys.executable, str(HERE / 'side.py'), *args], env=self.env(),
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
        self.procs.append(p)
        return p

    def run(self, *args, text='', timeout=60):
        return subprocess.run([sys.executable, str(HERE / 'side.py'), *args], env=self.env(),
                              input=text, capture_output=True, text=True, timeout=timeout,
                              start_new_session=True)

    def read(self, name):
        try:
            return json.loads((self.state_dir / name).read_text())
        except (OSError, ValueError):
            return {}

    def write(self, rel, data, mode=0o644):
        p = self.home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode())
        os.chmod(p, mode)
        return p

    def send(self, *args):
        """start sending; wait until the code is shown"""
        p = self.start('send', *args)
        wait_for(lambda: self.read('sender.json').get('pid') == p.pid or p.poll() is not None,
                 what='the sender')
        return p

    def code(self):
        return self.read('sender.json').get('code')

    def stop(self):
        for p in self.procs:
            if p.poll() is None:
                p.terminate()
        for p in self.procs:
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()
            for pipe in (p.stdout, p.stderr):
                if pipe:
                    pipe.close()


class Proxy:
    """sits between the two devices; can cut the connection after a number of bytes"""

    def __init__(self, to_port):
        self.to_port, self.cut_after, self.cuts, self.down = to_port, None, 0, 0
        self.srv = socket.create_server((HOST, 0))
        self.port = self.srv.getsockname()[1]
        self.open = True
        threading.Thread(target=self.accept, daemon=True).start()

    def accept(self):
        while self.open:
            try:
                a, _ = self.srv.accept()
            except OSError:
                return
            try:
                b = socket.create_connection((HOST, self.to_port))
            except OSError:
                a.close()
                continue
            limit, self.cut_after = self.cut_after, None       # the cut is for one connection
            threading.Thread(target=self.up, args=(a, b), daemon=True).start()
            threading.Thread(target=self.down_to, args=(b, a, limit), daemon=True).start()

    def down_to(self, sender, receiver, limit):
        """sender to receiver, counted; at the limit the receiver sees the end, as when the
        other device goes away (what was sent before still arrives)"""
        sent = 0
        try:
            while chunk := sender.recv(65536):
                receiver.sendall(chunk)
                sent += len(chunk)
                self.down += len(chunk)
                if limit is not None and sent >= limit:
                    self.cuts += 1
                    break
            receiver.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        sender.close()

    def up(self, receiver, sender):
        """receiver to sender, until the receiver hangs up"""
        try:
            while chunk := receiver.recv(65536):
                try:
                    sender.sendall(chunk)
                except OSError:
                    pass                    # cut: keep listening until the receiver is done
        except OSError:
            pass
        receiver.close()
        sender.close()

    def close(self):
        self.open = False
        self.srv.close()


class Peer:
    """a receiver that speaks the wire by hand, for tests of what the sender allows"""

    def __init__(self, port):
        self.port = port

    def hello(self, msg):
        sock = net.connect(HOST, self.port)
        sock.settimeout(10)
        net.send_json(sock, dict(msg, name='peer'))
        return sock, net.recv_json(sock)

    def pair(self, code):
        """(the secured connection, the sender's session message), or (None, the refusal)"""
        sock, hi = self.hello({'op': 'pair'})
        if not hi.get('ok'):
            sock.close()
            return None, hi
        t = net.secure(sock, net.spake(code, 'A', sock), server=False)
        return t, net.recv_json(t)

    def wrong_code(self, code='000000'):
        """one wrong guess; True when the sender let us try"""
        try:
            t, reply = self.pair(code)
        except OSError:
            return True
        if t:
            t.close()
            raise AssertionError('a wrong code paired')
        return False

    def resume(self, session, secret):
        sock, hi = self.hello({'op': 'resume', 'session': session})
        if not hi.get('ok'):
            sock.close()
            return None
        return net.secure(sock, bytes.fromhex(secret), server=False)

    @staticmethod
    def ask(t, **msg):
        net.send_json(t, msg)
        return net.recv_json(t)


class Case(unittest.TestCase):
    """a test with a sending and a getting device"""
    sender_cfg, receiver_cfg = {}, {}

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='zt-test-'))
        self.port = free_port()
        self.old = Side(self.root, 'old', self.port, **self.sender_cfg)
        self.new = Side(self.root, 'new', self.port, **self.receiver_cfg)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(self.old.stop)
        self.addCleanup(self.new.stop)

    def get(self, groups, **kw):
        """pair with the code the sender shows and fetch these groups"""
        return self.new.run('get', HOST, '--code', self.old.code(), '--groups', groups, **kw)

    def tree(self, top):
        return sorted(str(p.relative_to(top)) for p in top.rglob('*'))
