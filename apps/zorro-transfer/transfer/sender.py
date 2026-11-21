"""The sending side (zorro-transfer send): runs only while the app started it.

Listens on the port, shows a 6-digit code and serves the files of the groups the receiver
asked for (serve.py). Other devices find it through the beacon (beacon.py), which reads
sender.json. It stops when the Send page is closed and nothing is being sent (an unfinished
transfer: once the receiver stopped trying), or when the window says stop.

Who may connect: this device, NetBird peers and the home network (zorro_net), a few at a
time. Guessing the code: one pairing at a time, PAIR_TIME at most for the whole of it; the
device that guessed wrong waits longer each time and after PEER_FAILS is not let in any
more; every 3 wrong codes a new code; after MAX_FAILS in all no pairing at all until the
user asks for a new code."""
import os
import secrets
import signal
import socket
import sys
import threading
import time

from . import check, generated, net, state
from .serve import Serving

PAIR_TIME = 15                  # seconds for a whole pairing, from the first byte to the key
MAX_CONNECTIONS = 8             # connections at the same time; more are closed at once
PEER_FAILS = 10                 # wrong codes from one device before it is not let in
MAX_FAILS = 100                 # wrong codes from everyone before pairing is switched off
FIRST_WAIT = 2                  # seconds after a device's first wrong code; doubles, up to LONGEST
LONGEST_WAIT = 60
IDLE_EXIT = 60                  # seconds without a window and without work before it stops
DONE_SHOWN = 600                # seconds a finished transfer stays listed (without its secret)
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


def kept(sid, s, now):
    """does a session stay in the list? a finished one only a while, to show it was done"""
    age = now - s.get('updated', s.get('started', 0))
    return age < (DONE_SHOWN if s.get('status') == 'done' else state.RETRY_FOR)


class Sender:
    def __init__(self, gui_pid=None):
        self.gui_pid = gui_pid
        self.lock = threading.Lock()
        self.pairing = threading.Lock()
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self.sessions = fresh(state.read_state('sender.json').get('sessions'))
        self.active = 0
        self.fails, self.peers = 0, {}     # wrong codes in all; address: [wrong codes, wait until]
        self.new_code()

    def new_code(self):
        self.code = f'{secrets.randbelow(10 ** 6):06d}'

    def pairing_off(self):
        return self.fails >= MAX_FAILS

    def save(self, status='waiting'):
        off = self.pairing_off()
        with self.lock:
            now = time.time()
            for sid, s in list(self.sessions.items()):
                if not kept(sid, s, now):
                    del self.sessions[sid]
                elif s.get('status') == 'done':
                    s.pop('secret', None)   # a finished transfer cannot come back
            state.write_state('sender.json', {
                'pid': os.getpid(), 'code': '' if off else self.code,
                'status': 'locked' if off and status in ('waiting', 'wrong code') else status,
                'why': LOCKED if off else '', 'fails': self.fails,
                'name': state.device_name(), 'port': net.PORT, 'updated': now,
                'sessions': self.sessions})

    def unfinished(self):
        """a transfer that started and did not finish: the receiver comes back for it"""
        return any(s.get('total') for s in fresh(self.sessions).values())

    def gui_alive(self):
        """a Send page that shows this sender (the window may have been closed and opened
        again): only the Send page leaves window.pid, and takes it away when it goes. No
        window at all (gui_pid None): the command line, it runs until stopped"""
        if self.gui_pid is None:
            return True
        return state.is_transfer(state.read_pid('window.pid'))

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
        state.touch('window.seen')          # Transfer is open: knocks may be shown again
        srv = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        srv.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)     # IPv4 too
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('::', net.PORT))
        srv.listen(4)
        srv.settimeout(1)
        try:
            self.save()
            self.listen(srv)
        finally:
            generated.remove()
            srv.close()
            self.save('stopped')

    def accept(self, srv):
        """take one connection, when there is one: only from a trusted address, a few at a time"""
        try:
            conn, addr = srv.accept()
        except socket.timeout:
            return
        peer = addr[0][7:] if addr[0].startswith('::ffff:') else addr[0]   # IPv4 inside IPv6
        if not net.trusted(peer) or not self.slots.acquire(blocking=False):
            conn.close()
            return
        threading.Thread(target=self.handle, args=(conn, peer), daemon=True).start()

    def listen(self, srv):
        """take connections until the window is gone and nothing is being sent, or stop"""
        idle_since = time.time()
        while not self.told('sender.stop'):
            self.accept(srv)
            if self.told('sender.unlock'):
                self.fails, self.peers = 0, {}
                self.new_code()
                self.save()
            if self.active:
                idle_since = time.time()
            # the app closed: a minute for a reconnect; while a transfer is unfinished, as
            # long as the receiver keeps trying
            wait = IDLE_EXIT + (state.RETRY_FOR if self.unfinished() else 0)
            if not self.gui_alive() and not self.active and time.time() - idle_since > wait:
                break

    def handle(self, sock, peer):
        """one connection: who is it, then serve it"""
        deadline = net.Deadline(sock, PAIR_TIME)
        try:
            hello = net.recv_json(sock, limit=net.SMALL_FRAME)
            op = hello.get('op')
            if op == 'probe':
                net.send_json(sock, {'name': state.device_name(), 'magic': net.MAGIC.decode()})
                return
            t, sid = self.pair(sock, hello, peer, deadline) if op == 'pair' else \
                self.resume(sock, hello, deadline)
            if t is None:
                return
            with self.lock:
                self.active += 1
            try:
                Serving(self, t, sid, peer).run()
            finally:
                t.close()
                with self.lock:
                    self.active -= 1
        except (OSError, ValueError, TypeError, KeyError):
            pass                            # a lost or confused connection: the receiver retries
        finally:
            deadline.cancel()
            self.slots.release()
            try:
                sock.close()
            except OSError:
                pass

    def refusal(self, peer):
        """why this device cannot pair right now, '' when it can"""
        if self.pairing_off():
            return 'too many wrong codes: ask for a new code on the sending device'
        if self.active:
            return 'busy sending to another device'     # one device at a time
        fails, not_before = self.peers.get(peer, (0, 0))
        if fails >= PEER_FAILS:
            return 'too many wrong codes from this device: ask for a new code on the sending device'
        wait = not_before - time.time()
        if wait > 0:
            return f'a wrong code was typed: wait {int(wait) + 1} s and try again'
        return ''

    def pair(self, sock, hello, peer, deadline):
        """pairing with the code: (the secured connection, session id) or (None, None)"""
        why = self.refusal(peer)
        if why or not self.pairing.acquire(blocking=False):
            net.send_json(sock, {'ok': False, 'error': why or 'another device is pairing: try again'})
            return None, None
        try:
            net.send_json(sock, {'ok': True, 'name': state.device_name()})
            try:
                t = net.secure(sock, net.spake(self.code, 'B', sock), server=True)
            except Exception:               # whatever went wrong, it was one guess at the code
                t = None
            if t is None or not deadline.cancel():
                self.wrong_code(peer)
                return None, None
            return t, self.paired(t, hello, peer)
        finally:
            self.pairing.release()

    def paired(self, t, hello, peer):
        sid, secret = new_session_id(), secrets.token_hex(32)
        name = hello.get('name')
        with self.lock:
            self.sessions[sid] = {'secret': secret, 'started': time.time(), 'status': 'paired',
                                  'peer': name[:64] if isinstance(name, str) and name else peer}
        self.peers.pop(peer, None)
        self.new_code()                     # a code works once
        net.send_json(t, {'session': sid, 'secret': secret})
        return sid

    def wrong_code(self, peer):
        self.fails += 1
        fails = self.peers.get(peer, (0, 0))[0] + 1
        self.peers[peer] = (fails, time.time() + min(FIRST_WAIT * 2 ** (fails - 1), LONGEST_WAIT))
        if self.fails % 3 == 0:
            self.new_code()
        self.save('wrong code')

    def resume(self, sock, hello, deadline):
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
        t = net.secure(sock, bytes.fromhex(s['secret']), server=True)
        return (t, sid) if deadline.cancel() else (None, None)
