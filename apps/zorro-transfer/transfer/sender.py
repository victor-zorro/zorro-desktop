"""The sending side (zorro-transfer send): runs only while the app started it.

Listens on the port, shows a 6-digit code, answers "who sends?" on the local network and
serves the files of the groups the receiver asked for (serve.py). It stops when the window
is closed and nothing is being sent (an unfinished transfer: once the receiver stopped
trying), or when the window says stop.

Guessing the code: one pairing at a time, a longer wait after each wrong code, a new code
after every 3, and after 10 no pairing at all until the user asks for a new code."""
import json
import os
import secrets
import signal
import socket
import sys
import threading
import time

from . import check, generated, net, state
from .serve import Serving

MAX_FAILS = 10                  # wrong codes before pairing is switched off
FIRST_WAIT = 2                  # seconds after the first wrong code; doubles, up to LONGEST
LONGEST_WAIT = 60
IDLE_EXIT = 60                  # seconds without a window and without work before it stops
LOCKED = 'Too many wrong codes: pairing is off until you ask for a new code.'


def new_session_id():
    return secrets.token_hex(8)


def fresh(sessions):
    """the saved sessions that may still continue: not done, not older than RETRY_FOR"""
    now = time.time()
    return {sid: s for sid, s in (sessions if isinstance(sessions, dict) else {}).items()
            if check.is_session(sid) and isinstance(s, dict) and check.is_secret(s.get('secret'))
            and s.get('status') != 'done'
            and now - s.get('updated', s.get('started', 0)) < state.RETRY_FOR}


class Sender:
    def __init__(self, gui_pid=None):
        self.gui_pid = gui_pid
        self.lock = threading.Lock()
        self.pairing = threading.Lock()
        self.sessions = fresh(state.read_state('sender.json').get('sessions'))
        self.active = 0
        self.fails, self.not_before = 0, 0
        self.stopping = False
        self.new_code()

    def new_code(self):
        self.code = f'{secrets.randbelow(10 ** 6):06d}'

    def pairing_off(self):
        return self.fails >= MAX_FAILS

    def save(self, status='waiting'):
        off = self.pairing_off()
        with self.lock:
            state.write_state('sender.json', {
                'pid': os.getpid(), 'code': '' if off else self.code,
                'status': 'locked' if off and status in ('waiting', 'wrong code') else status,
                'why': LOCKED if off else '', 'fails': self.fails,
                'name': state.device_name(), 'port': net.PORT, 'updated': time.time(),
                'sessions': self.sessions})

    def unfinished(self):
        """a transfer that started and did not finish: the receiver comes back for it"""
        return any(s.get('total') for s in fresh(self.sessions).values())

    def gui_alive(self):
        """the window that shows this sender; it may have been closed and opened again"""
        if self.gui_pid is None:
            return True
        return state.is_transfer(state.read_pid('window.pid')) or state.is_transfer(self.gui_pid)

    def told(self, name):
        """did the window leave a signal file for this sender? (it is used up)"""
        if state.read_pid(name) != os.getpid():
            return False
        (state.STATE / name).unlink(missing_ok=True)
        return True

    def run(self):
        net.need_psk()
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        for name in ('sender.stop', 'sender.unlock'):       # left by an earlier sender
            (state.STATE / name).unlink(missing_ok=True)
        srv = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        srv.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)     # IPv4 too
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('::', net.PORT))
        srv.listen(4)
        srv.settimeout(1)
        threading.Thread(target=self.discovery, daemon=True).start()
        try:
            self.save()
            self.listen(srv)
        finally:
            self.stopping = True
            generated.remove()
            srv.close()
            self.save('stopped')

    def listen(self, srv):
        """take connections until the window is gone and nothing is being sent, or stop"""
        idle_since = time.time()
        while not self.told('sender.stop'):
            try:
                conn, addr = srv.accept()
                peer = addr[0][7:] if addr[0].startswith('::ffff:') else addr[0]   # IPv4 inside IPv6
                threading.Thread(target=self.handle, args=(conn, peer), daemon=True).start()
            except socket.timeout:
                pass
            if self.told('sender.unlock'):
                self.fails, self.not_before = 0, 0
                self.new_code()
                self.save()
            if self.active:
                idle_since = time.time()
            # the app closed: a minute for a reconnect; while a transfer is unfinished, as
            # long as the receiver keeps trying
            wait = IDLE_EXIT + (state.RETRY_FOR if self.unfinished() else 0)
            if not self.gui_alive() and not self.active and time.time() - idle_since > wait:
                break

    def discovery(self):
        """answer 'who sends?' on the local network"""
        try:
            u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            u.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            u.bind(('', net.DISCOVER_PORT))
            u.settimeout(2)
        except OSError:
            return
        me = json.dumps({'name': state.device_name(), 'port': net.PORT}).encode()
        while not self.stopping:
            try:
                data, addr = u.recvfrom(512)
                if data == net.MAGIC + b' who?':
                    u.sendto(me, addr)
            except OSError:
                pass

    def handle(self, sock, peer):
        """one connection: who is it, then serve it"""
        try:
            sock.settimeout(30)
            hello = net.recv_json(sock)
            op = hello.get('op')
            if op == 'probe':
                net.send_json(sock, {'name': state.device_name(), 'magic': net.MAGIC.decode()})
                return
            t, sid = self.pair(sock, hello, peer) if op == 'pair' else self.resume(sock, hello)
            if t is None:
                return
            with self.lock:
                self.active += 1
            try:
                Serving(self, t, sid, peer).run()
            finally:
                with self.lock:
                    self.active -= 1
        except (OSError, ValueError, TypeError, KeyError):
            pass                            # a lost or confused connection: the receiver retries
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def refusal(self):
        """why a new device cannot pair right now, '' when it can"""
        if self.pairing_off():
            return 'too many wrong codes: ask for a new code on the sending device'
        if self.active:
            return 'busy sending to another device'     # one device at a time
        wait = self.not_before - time.time()
        if wait > 0:
            return f'a wrong code was typed: wait {int(wait) + 1} s and try again'
        return ''

    def pair(self, sock, hello, peer):
        """pairing with the code: (the secured connection, session id) or (None, None)"""
        why = self.refusal()
        if why or not self.pairing.acquire(blocking=False):
            net.send_json(sock, {'ok': False, 'error': why or 'another device is pairing: try again'})
            return None, None
        try:
            net.send_json(sock, {'ok': True, 'name': state.device_name()})
            try:
                t = net.secure(sock, net.spake(self.code, 'B', sock), server=True)
            except Exception:               # whatever went wrong, it was one guess at the code
                self.wrong_code()
                return None, None
            sid, secret = new_session_id(), secrets.token_hex(32)
            name = hello.get('name')
            with self.lock:
                self.sessions[sid] = {'secret': secret, 'started': time.time(), 'status': 'paired',
                                      'peer': name[:64] if isinstance(name, str) and name else peer}
            self.fails = 0
            self.new_code()                 # a code works once
            net.send_json(t, {'session': sid, 'secret': secret})
            return t, sid
        finally:
            self.pairing.release()

    def wrong_code(self):
        self.fails += 1
        self.not_before = time.time() + min(FIRST_WAIT * 2 ** (self.fails - 1), LONGEST_WAIT)
        if self.fails % 3 == 0:
            self.new_code()
        self.save('wrong code')

    def resume(self, sock, hello):
        """an interrupted transfer comes back with its session: no new code needed"""
        sid = hello.get('session') if hello.get('op') == 'resume' else None
        with self.lock:
            s = self.sessions.get(sid) if isinstance(sid, str) else None
            if s and not fresh({sid: s}):           # done, or left alone too long
                del self.sessions[sid]
                s = None
        if not s:
            net.send_json(sock, {'ok': False, 'error': 'unknown session'})
            return None, None
        net.send_json(sock, {'ok': True, 'name': state.device_name()})
        return net.secure(sock, bytes.fromhex(s['secret']), server=True), sid
