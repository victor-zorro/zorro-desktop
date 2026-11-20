"""The two sides of a transfer, each in its own process so it can go on in the background.

Sender  (zorro-transfer send): only while the app started it. Listens on PORT, shows a 6-digit
        code, answers "who sends?" on the local network, serves only the files of the groups
        the receiver asked for. Stops when the app is closed and nothing is being sent (an
        unfinished transfer: once the receiver stopped trying).
Receiver (zorro-transfer get): pairs with the code, asks for the groups, fetches file by file
        into a staging folder. A file that was half done continues where it stopped; a lost
        connection is retried for a while with the session secret (no new code). Apply then
        moves everything into place, keeping what it replaces as NAME.before-transfer; "by
        itself" (auto) it does so when everything is here, after the steps that need the
        admin password ran at the start (fetch_first + root_setup).

Both write their progress to ~/.local/state/zorro-transfer/ (sender.json, receiver.json), which
the app shows on each device."""
import json
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import threading
import time
from pathlib import Path

from . import items, net

STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'zorro-transfer'
STAGE = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'zorro-transfer'
CHUNK = 1 << 20
SMALL = 512 << 10               # files up to this size come in batches
RETRY_FOR = 30 * 60             # a lost connection: keep trying this long (seconds)


def write_state(name, data):
    STATE.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE, 0o700)
    tmp = STATE / f'.{name}.tmp'
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f:
        json.dump(data, f)
    tmp.replace(STATE / name)


def read_state(name):
    try:
        return json.loads((STATE / name).read_text())
    except (OSError, ValueError):
        return {}


def notify(title, body=''):
    try:
        subprocess.Popen(['notify-send', '-a', 'Transfer', '-i', 'folder-remote', title, body],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def device_name():
    return os.environ.get('ZORRO_TRANSFER_NAME') or socket.gethostname()   # the variable: tests


def route_kind(host):
    """how we reach the other device: 'cable', 'wifi', 'netbird', 'mobile' or ''"""
    try:
        ip = socket.getaddrinfo(host, None)[0][4][0]
        out = json.loads(subprocess.run(['ip', '-j', 'route', 'get', ip], capture_output=True,
                                        text=True, timeout=3).stdout or '[]')
        dev = out[0].get('dev', '') if out else ''
    except (OSError, ValueError, IndexError, subprocess.SubprocessError, socket.gaierror):
        return ''
    return ('netbird' if dev.startswith('wt') else 'wifi' if dev.startswith('wl') else
            'mobile' if dev.startswith('ww') else 'cable' if dev.startswith(('en', 'eth')) else
            'local' if dev == 'lo' else '')


# ---------------------------------------------------------------- sender
class Sender:
    def __init__(self, gui_pid=None):
        self.gui_pid = gui_pid
        self.lock = threading.Lock()
        old = read_state('sender.json')
        self.sessions = old.get('sessions', {})     # earlier sessions can still continue
        self.active = 0
        self.new_code()

    def new_code(self):
        self.code, self.tries = f'{secrets.randbelow(10 ** 6):06d}', 0

    def save(self, status='waiting'):
        with self.lock:
            write_state('sender.json', {'pid': os.getpid(), 'code': self.code, 'status': status,
                                        'name': device_name(), 'port': net.PORT,
                                        'updated': time.time(), 'sessions': self.sessions})

    def unfinished(self):
        """a transfer that started and did not finish: the receiver comes back for it"""
        return any(s.get('status') != 'done' and time.time() - s.get('updated', s.get('started', 0)) < RETRY_FOR
                   for s in self.sessions.values() if s.get('total'))

    def gui_alive(self):
        return self.gui_pid is None or Path(f'/proc/{self.gui_pid}').exists()

    def run(self):
        srv = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        srv.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)     # IPv4 too
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('::', net.PORT))
        srv.listen(4)
        srv.settimeout(1)
        threading.Thread(target=self.discovery, daemon=True).start()
        self.save()
        idle_since = time.time()
        while True:
            try:
                conn, addr = srv.accept()
                peer = addr[0][7:] if addr[0].startswith('::ffff:') else addr[0]     # IPv4 inside IPv6
                threading.Thread(target=self.handle, args=(conn, peer), daemon=True).start()
            except socket.timeout:
                pass
            if self.active:
                idle_since = time.time()
            # the app closed: stop once nothing is being sent (a minute for a reconnect; while
            # a transfer is unfinished, as long as the receiver keeps trying)
            wait = RETRY_FOR + 60 if self.unfinished() else 60
            if not self.gui_alive() and not self.active and time.time() - idle_since > wait:
                break
            if Path(STATE / 'sender.stop').exists():
                (STATE / 'sender.stop').unlink(missing_ok=True)
                break
        for f in ('wifi.json', 'accounts.json'):       # the Wi-Fi passwords: not left lying
            (items.GEN / f).unlink(missing_ok=True)
        self.save('stopped')

    def discovery(self):
        """answer 'who sends?' on the local network"""
        try:
            u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            u.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            u.bind(('', net.DISCOVER_PORT))
        except OSError:
            return
        while True:
            data, addr = u.recvfrom(512)
            if data == net.MAGIC + b' who?':
                u.sendto(json.dumps({'name': device_name(), 'port': net.PORT}).encode(), addr)

    def handle(self, sock, peer):
        try:
            sock.settimeout(30)
            hello = net.recv_json(sock)
            op = hello.get('op')
            if op == 'probe':
                net.send_json(sock, {'name': device_name(), 'magic': net.MAGIC.decode()})
                return
            if op == 'pair':
                if self.active:                     # one device at a time
                    net.send_json(sock, {'ok': False, 'error': 'busy sending to another device'})
                    return
                net.send_json(sock, {'ok': True, 'name': device_name()})
                key = net.spake(self.code, 'B', sock)
                try:
                    t = net.secure(sock, key, server=True)
                except ssl.SSLError:
                    self.tries += 1
                    if self.tries >= 3:             # 3 wrong codes: a new one
                        self.new_code()
                    self.save('wrong code')
                    return
                sid, secret = secrets.token_hex(8), secrets.token_hex(32)
                with self.lock:
                    self.sessions[sid] = {'secret': secret, 'peer': hello.get('name') or peer,
                                          'started': time.time(), 'status': 'paired'}
                self.new_code()                     # a code works once
                net.send_json(t, {'session': sid, 'secret': secret})
            elif op == 'resume' and hello.get('session') in self.sessions:
                sid = hello['session']
                net.send_json(sock, {'ok': True, 'name': device_name()})
                try:
                    t = net.secure(sock, bytes.fromhex(self.sessions[sid]['secret']), server=True)
                except ssl.SSLError:
                    return
            else:
                net.send_json(sock, {'ok': False, 'error': 'unknown session'})
                return
            self.active += 1
            try:
                self.serve(t, sid, peer)
            finally:
                self.active -= 1
        except (OSError, ValueError, ConnectionError):
            pass
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def serve(self, t, sid, peer):
        s = self.sessions[sid]
        s.update(status='connected', route=route_kind(peer), updated=time.time())
        self.save('sending')
        allowed = {}
        while True:
            req = net.recv_json(t)
            op = req.get('op')
            if op == 'offer':                   # the groups, with their sizes
                offer = []
                for gid, (title, about, _paths) in items.all_groups().items():
                    fl = items.files(gid)
                    offer.append({'id': gid, 'title': title, 'about': about,
                                  'files': len(fl), 'bytes': sum(f[1] for f in fl)})
                net.send_json(t, {'groups': offer, 'running': items.running(list(items.RUNNING))})
            elif op == 'manifest':
                fl = [{'group': g, 'path': p, 'size': sz, 'mtime': mt}
                      for g in req.get('groups', []) for p, sz, mt in items.files(g)]
                allowed = {f['path']: f for f in fl}
                s.update(groups=req.get('groups', []), total=sum(f['size'] for f in fl))
                net.send_json(t, {'files': fl})
            elif op == 'get':
                f = allowed.get(req.get('path'))           # only what the list holds
                path = items.source(f['path']) if f else None
                if not f or not items.safe_rel(f['path']) or not path.is_file():
                    net.send_json(t, {'ok': False})
                    continue
                size = path.stat().st_size
                off = max(0, min(int(req.get('offset', 0)), size))
                net.send_json(t, {'ok': True, 'size': size, 'mtime': int(path.stat().st_mtime)})
                base = int(req.get('done', 0)) - off    # the receiver's bytes before this file
                mark, last = (time.time(), base + off), 0
                with open(path, 'rb') as fh:
                    fh.seek(off)
                    left = size - off
                    while left > 0:
                        chunk = fh.read(min(CHUNK, left))
                        if not chunk:           # the file shrank: fill (the receiver re-checks)
                            chunk = b'\0' * min(CHUNK, left)
                        t.sendall(chunk)
                        left -= len(chunk)
                        now = time.time()
                        if now - last > 0.5:    # our own count: the receiver's reports wait
                            cur = base + size - left
                            dt = now - mark[0]
                            if dt > 0.4:
                                s['speed'] = (cur - mark[1]) / dt
                            if dt > 3:
                                mark = (now, cur)
                            s.update(done=cur, current=f['path'], updated=now)
                            self.save('sending')
                            last = now
            elif op == 'batch':                 # many small files in one go (no wait per file)
                sizes, paths = [], []
                for rel in req.get('paths', [])[:1000]:
                    f = allowed.get(rel)
                    path = items.source(rel) if f and items.safe_rel(rel) else None
                    ok = path is not None and path.is_file()
                    sizes.append(path.stat().st_size if ok else -1)
                    paths.append(path if ok else None)
                net.send_json(t, {'sizes': sizes})
                for path, size in zip(paths, sizes):
                    if path is None:
                        continue
                    with open(path, 'rb') as fh:
                        data = fh.read(size)
                    t.sendall(data + b'\0' * (size - len(data)))     # it shrank meanwhile: fill
                s.update(done=int(req.get('done', 0)) + sum(x for x in sizes if x > 0),
                         current=req.get('paths', [''])[-1], updated=time.time())
                self.save('sending')
            elif op == 'progress':              # the receiver's numbers: both show the same
                s.update(done=req.get('done', 0), total=req.get('total', s.get('total', 0)),
                         current=req.get('current', ''), speed=req.get('speed', 0),
                         updated=time.time())
                self.save('sending')
            elif op == 'finished':
                s.update(status='done', done=s.get('total', 0), updated=time.time())
                self.save('done')
                notify('Transfer: everything was sent', f"to {s.get('peer', 'the other device')}")
                net.send_json(t, {'ok': True})
                return


# ---------------------------------------------------------------- receiver
def discover(wait=1.5):
    """senders on the local network and among the NetBird peers: [{name, host, via}]"""
    found = {}
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    u.settimeout(0.3)
    try:
        u.sendto(net.MAGIC + b' who?', ('255.255.255.255', net.DISCOVER_PORT))
    except OSError:
        pass
    peers = netbird_peers()
    probes = []

    def probe(host, name):
        try:
            s = net.connect(host, timeout=2)
            net.send_json(s, {'op': 'probe'})
            r = net.recv_json(s)
            s.close()
            if r.get('magic') == net.MAGIC.decode():
                found[host] = {'name': r.get('name') or name, 'host': host, 'via': 'netbird'}
        except (OSError, ValueError, ConnectionError):
            pass
    for host, name in peers:
        th = threading.Thread(target=probe, args=(host, name), daemon=True)
        th.start()
        probes.append(th)
    end = time.time() + wait
    while time.time() < end:
        try:
            data, addr = u.recvfrom(512)
            r = json.loads(data)
            found.setdefault(addr[0], {'name': r.get('name', addr[0]), 'host': addr[0],
                                       'via': route_kind(addr[0]) or 'local network'})
        except (socket.timeout, ValueError):
            pass
    for th in probes:
        th.join(max(0, end - time.time()) + 1)
    mine = {device_name()}
    return [f for f in found.values() if f['name'] not in mine or f['host'] in ('127.0.0.1', '::1')]


def netbird_peers():
    try:
        st = json.loads(subprocess.run(['netbird', 'status', '--json'], capture_output=True,
                                       text=True, timeout=4).stdout or '{}')
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    out = []
    for p in (st.get('peers') or {}).get('details') or []:
        if p.get('status') == 'Connected':
            ip = (p.get('netbirdIp') or '').split('/')[0]
            if ip:
                out.append((ip, (p.get('fqdn') or ip).split('.')[0]))
    return out


class Receiver:
    def __init__(self):
        self.st = read_state('receiver.json')

    def save(self, **kv):
        self.st.update(kv, updated=time.time(), pid=os.getpid())
        write_state('receiver.json', self.st)

    def open(self, code=None):
        """a TLS connection to the sender: pairing with the code, or the saved session"""
        sock = net.connect(self.st['host'], self.st.get('port', net.PORT))
        sock.settimeout(60)
        if code:
            net.send_json(sock, {'op': 'pair', 'name': device_name()})
            hi = net.recv_json(sock)
            if not hi.get('ok'):
                raise ConnectionError(hi.get('error', 'refused'))
            key = net.spake(code, 'A', sock)
            try:
                t = net.secure(sock, key, server=False)
                r = net.recv_json(t)
            except (ssl.SSLError, ConnectionError):
                raise PermissionError('wrong code')
            self.save(session=r['session'], secret=r['secret'], sender=hi.get('name'))
            return t
        net.send_json(sock, {'op': 'resume', 'session': self.st['session'], 'name': device_name()})
        if not net.recv_json(sock).get('ok'):
            raise PermissionError('the sender does not know this transfer any more')
        return net.secure(sock, bytes.fromhex(self.st['secret']), server=False)

    def offer(self, host, code):
        """pair, then the groups the sender offers"""
        self.st = {'host': host, 'status': 'pairing', 'route': route_kind(host)}
        t = self.open(code)
        net.send_json(t, {'op': 'offer'})
        r = net.recv_json(t)
        self.save(status='paired', offer=r['groups'], sender_running=r.get('running', []))
        t.close()
        return r['groups']

    def fetch(self, groups=None):
        """get the chosen groups (or continue the saved transfer), retrying a lost connection"""
        if groups is not None:
            self.save(groups=groups, status='starting', files=None, error='')
        stage = STAGE / self.st['session']
        give_up = time.time() + RETRY_FOR
        while True:
            try:
                t = self.open()
                give_up = time.time() + RETRY_FOR
                self.save(status='receiving', error='')
                self.fetch_on(t, stage)
                self.save(status='received')
                if self.st.get('auto'):
                    return self.apply_when_free()
                notify('Transfer: everything is here', 'Open Transfer and press "Put in place".')
                return True
            except PermissionError as e:
                self.save(status='failed', error=str(e))
                return False
            except (OSError, ConnectionError, ValueError) as e:
                if time.time() > give_up:
                    self.save(status='interrupted', error=str(e))
                    notify('Transfer stopped', 'Open Transfer on both devices to go on where it stopped.')
                    return False
                self.save(status='reconnecting', error=str(e))
                time.sleep(5)

    def fetch_first(self, groups):
        """before the big part: only the login look and the accounts list (a few KB), so the
        steps that need the admin password can run now, while you are here"""
        self.save(groups=groups, status='starting', files=None, error='')
        t = self.open()
        try:
            self.fetch_on(t, STAGE / self.st['session'], first=True)
        finally:
            t.close()

    def root_setup(self, passwords):
        """login look and accounts with one admin password (zorro-transfer-helper); notes"""
        stage = STAGE / self.st['session']
        look, people = stage / 'system/etc/zorro-dm/look.json', stage / 'generated/accounts.json'
        req = {'look': None, 'accounts': [], 'passwords': passwords or {}}
        try:
            if look.exists():
                req['look'] = json.loads(look.read_text())
            if people.exists():
                req['accounts'] = json.loads(people.read_text())
        except (OSError, ValueError):
            pass
        notes = []
        if req['look'] is None and not req['accounts']:
            pass
        elif not Path(items.SETUP_HELPER).exists():
            notes.append('login look and accounts: first run  sudo ~/zorro-desktop/apps/'
                         'zorro-transfer/install-system.sh  then "Put in place" again')
        else:
            try:
                r = subprocess.run(['pkexec', items.SETUP_HELPER, 'setup'], input=json.dumps(req),
                                   capture_output=True, text=True, timeout=300)
                out = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else None
            except (OSError, ValueError, IndexError, subprocess.SubprocessError):
                out = None
            if out is None:
                notes.append('login look and accounts not set (password cancelled)')
            else:
                if out.get('look') is not None:
                    notes.append('login look saved' if out['look'] else 'login look not saved')
                if out.get('me') is not None:
                    notes.append('your name and groups set (groups count from the next login)'
                                 if out['me'] else 'your groups not set')
                for key, text in (('made', 'accounts made'), ('skipped', 'no password, not made'),
                                  ('failed', 'not made')):
                    if out.get(key):
                        notes.append(f'{text}: ' + ', '.join(out[key]))
        self.save(root_done=True, root_notes=notes)
        return notes

    def apply_when_free(self):
        """put in place by itself; apps whose files would change: wait until they are closed"""
        told = None
        while True:
            try:
                self.apply()
                notes = self.st.get('notes') or []
                notify('Transfer: done', 'Everything is in place.' + (' ' + '; '.join(notes) if notes else ''))
                return True
            except PermissionError as e:
                self.save(status='waiting for apps', error=str(e))
                if str(e) != told:
                    notify('Transfer: almost done', f'Close {e} to finish.')
                    told = str(e)
                time.sleep(10)

    def fetch_on(self, t, stage, first=False):
        net.send_json(t, {'op': 'manifest', 'groups': self.st['groups']})
        files = net.recv_json(t)['files']
        total = sum(f['size'] for f in files)
        self.save(files=files, total=total)
        if first:
            files = [f for f in files if f['path'].startswith(('system/', 'generated/accounts'))]
        done = 0
        t0, last = time.time(), 0
        speed_mark = (time.time(), 0)
        batch = []

        def flush():
            """fetch the waiting small files in one request"""
            nonlocal done, last, speed_mark
            if not batch:
                return
            net.send_json(t, {'op': 'batch', 'paths': [f['path'] for f in batch], 'done': done})
            sizes = net.recv_json(t)['sizes']
            for f, size in zip(batch, sizes):
                if size < 0:                # gone on the sender
                    continue
                data = net.recv_exact(t, size)
                final = stage / f['path']
                final.parent.mkdir(parents=True, exist_ok=True)
                tmp = final.with_name(final.name + '.part')
                tmp.write_bytes(data)
                os.utime(tmp, (f['mtime'], f['mtime']))
                tmp.replace(final)
                done += f['size']
            batch.clear()
            now = time.time()
            if now - last > 0.5:
                dt = now - speed_mark[0]
                speed = (done - speed_mark[1]) / dt if dt > 0 else 0
                if dt > 3:
                    speed_mark = (now, done)
                self.save(done=done, current=f['path'], speed=speed)
                net.send_json(t, {'op': 'progress', 'done': done, 'total': total,
                                  'current': f['path'], 'speed': speed})
                last = now

        for f in files:
            if not items.safe_rel(f['path']):
                continue
            final = stage / f['path']
            if final.exists() and final.stat().st_size == f['size']:
                done += f['size']
                continue
            if f['size'] <= SMALL and not (stage / (f['path'] + '.meta')).exists():
                batch.append(f)
                if len(batch) >= 500 or sum(x['size'] for x in batch) >= 16 * CHUNK:
                    flush()
                continue
            flush()
            part = stage / (f['path'] + '.part')
            final = stage / f['path']
            meta = stage / (f['path'] + '.meta')
            if final.exists() and final.stat().st_size == f['size']:
                done += f['size']
                continue
            part.parent.mkdir(parents=True, exist_ok=True)
            # half done earlier: continue, unless the file changed on the sender meanwhile
            have = part.stat().st_size if part.exists() else 0
            if have and (not meta.exists() or meta.read_text() != f"{f['size']} {f['mtime']}"):
                have = 0
            if have > f['size']:
                have = 0
            meta.write_text(f"{f['size']} {f['mtime']}")
            net.send_json(t, {'op': 'get', 'path': f['path'], 'offset': have, 'done': done + have})
            hdr = net.recv_json(t)
            if not hdr.get('ok'):
                continue                    # gone on the sender: skip it
            left = hdr['size'] - have
            with open(part, 'ab' if have else 'wb') as fh:
                while left > 0:
                    chunk = t.recv(min(CHUNK, left))
                    if not chunk:
                        raise ConnectionError('connection lost')
                    fh.write(chunk)
                    left -= len(chunk)
                    now = time.time()
                    if now - last > 0.5:    # progress, here and on the sender
                        cur = done + hdr['size'] - left
                        dt = now - speed_mark[0]
                        speed = (cur - speed_mark[1]) / dt if dt > 0 else 0
                        if dt > 3:
                            speed_mark = (now, cur)
                        self.save(done=cur, current=f['path'], speed=speed)
                        net.send_json(t, {'op': 'progress', 'done': cur, 'total': total,
                                          'current': f['path'], 'speed': speed})
                        last = now
            os.utime(part, (f['mtime'], f['mtime']))
            part.replace(final)
            meta.unlink(missing_ok=True)
            done += f['size']
        flush()
        if first:
            return
        self.save(done=total, current='', speed=0, took=time.time() - t0)
        net.send_json(t, {'op': 'finished'})
        net.recv_json(t)

    def conflicts(self):
        """received files that would replace a different file here"""
        out = []
        stage = STAGE / self.st.get('session', '-')
        for f in self.st.get('files') or []:
            src, dst = stage / f['path'], items.source(f['path'])
            if src.exists() and dst.exists() and not dst.is_symlink() and not same_file(src, dst):
                out.append(f['path'])
        return out

    def new_accounts(self):
        """other people's accounts that apply() makes: they need a password typed here"""
        return items.new_accounts(STAGE / self.st.get('session', '-') / 'generated/accounts.json')

    def apply(self, passwords=None):
        """move what was received into place; what it replaces stays as NAME.before-transfer.
        Apps whose files would change must be closed first: PermissionError with their names.
        passwords: {account name: password} for the new accounts (new_accounts())."""
        busy = items.running(self.st.get('groups') or [])
        if busy:
            raise PermissionError(', '.join(busy))
        stage = STAGE / self.st['session']
        moved = kept = 0
        for f in self.st.get('files') or []:
            if not items.safe_rel(f['path']):
                continue
            src, dst = stage / f['path'], items.HOME / f['path']
            if not src.exists():
                continue
            if f['path'].startswith(('system/', 'generated/')):     # after() below
                continue
            if dst.is_symlink():            # set up by this device's own install: leave it
                kept += 1
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                if same_file(src, dst):
                    src.unlink()
                    continue
                os.replace(dst, dst.with_name(dst.name + '.before-transfer'))
            try:
                os.replace(src, dst)        # same disk: instant, even for 40 GB
            except OSError:
                shutil.move(str(src), str(dst))
            moved += 1
        notes = self.after(stage, passwords or {})
        shutil.rmtree(stage, ignore_errors=True)
        self.save(status='applied', moved=moved, kept=kept, notes=notes)
        return moved, kept

    def after(self, stage, passwords):
        """rebuild what Settings makes from the choices; system files with a password"""
        notes = []
        if self.st.get('root_done'):        # done at the start (put in place by itself)
            notes += self.st.get('root_notes') or []
        else:
            notes += self.root_setup(passwords)
        wifi = stage / 'generated/wifi.json'
        if wifi.exists():
            n = items.wifi_import(wifi)
            notes.append(f'{n} Wi-Fi network{"s" if n != 1 else ""} added' if n else 'Wi-Fi networks were known already')
        if 'desktop' not in set(self.st.get('groups') or []):
            return notes
        settings = Path.home() / '.local/bin/zorro-settings'
        if settings.exists():               # theme, compositor, terminal, GTK colours, text size
            r = subprocess.run([str(settings), '--apply-windows'], capture_output=True, timeout=120)
            notes.append('settings applied' if r.returncode == 0 else 'settings: open Zorro Settings once')
        icons = Path(os.path.realpath(__file__)).parents[2] / 'zorro-icons' / 'build-icons'
        if icons.exists():
            subprocess.run([str(icons)], capture_output=True, timeout=300)
            notes.append('icons rebuilt')
        return notes


def same_file(a, b):
    if a.stat().st_size != b.stat().st_size:
        return False
    with open(a, 'rb') as x, open(b, 'rb') as y:
        while True:
            p, q = x.read(CHUNK), y.read(CHUNK)
            if p != q:
                return False
            if not p:
                return True
