"""The getting side: pairs with the code, asks for the groups, fetches them into a staging
folder (fetch.py) and puts them in place (place.py).

A lost connection is retried with the session secret (no new code) for as long as bytes keep
arriving, and RETRY_FOR after the last one. "By itself" (auto) everything is put in place
when it is here, after the steps that need the admin password ran at the start
(fetch_first + root_setup). Progress goes to receiver.json, which the app shows."""
import os
import ssl
import time

from . import after, check, generated, net, place, state
from .fetch import Fetch


class Refused(ConnectionError):
    """the sender said no, with a reason for the user"""


class Receiver:
    def __init__(self):
        self.st = check.saved(state.read_state('receiver.json'))
        self.got = 0                        # bytes that arrived in this process

    def save(self, **kv):
        self.st.update(kv, updated=time.time(), pid=os.getpid())
        state.write_state('receiver.json', self.st)

    def stage(self):
        """the folder the received files wait in; its name is checked each time"""
        sid = self.st.get('session')
        if not check.is_session(sid):
            raise check.BadPeer('no transfer to go on with: pair again')
        return state.STAGE / sid

    def open(self, code=None):
        """a TLS connection to the sender: pairing with the code, or the saved session"""
        net.need_psk()
        if not code:
            self.stage()
        sock = net.connect(self.st['host'], self.st.get('port', net.PORT))
        sock.settimeout(net.IDLE)
        hello = {'op': 'pair'} if code else {'op': 'resume', 'session': self.st['session']}
        net.send_json(sock, dict(hello, name=state.device_name()))
        hi = net.recv_json(sock)
        if not hi.get('ok'):
            sock.close()
            if code:
                raise Refused(str(hi.get('error', 'refused')))
            raise PermissionError('the sender does not know this transfer any more')
        if not code:
            return net.secure(sock, bytes.fromhex(self.st['secret']), server=False)
        key = net.spake(code, 'A', sock)
        try:
            t = net.secure(sock, key, server=False)
            reply = net.recv_json(t)
        except (ssl.SSLError, ConnectionError):
            raise PermissionError('wrong code') from None
        sid, secret = check.session(reply)
        self.save(session=sid, secret=secret, sender=str(hi.get('name') or '?')[:64])
        return t

    def offer(self, host, code):
        """pair, then the groups the sender offers"""
        self.st = {'host': host, 'status': 'pairing', 'route': state.route_kind(host)}
        t = self.open(code)
        try:
            net.send_json(t, {'op': 'offer'})
            groups, running = check.offer(net.recv_json(t))
        finally:
            t.close()
        state.clean_stage(keep=self.st['session'])      # what earlier transfers left behind
        self.save(status='paired', offer=groups, sender_running=running)
        return groups

    def fetch(self, groups=None):
        """get the chosen groups (or continue the saved transfer), retrying a lost
        connection. One fetch at a time on a device: state.Busy when another runs."""
        with state.locked('receiver.lock'):
            self.stage()
            if groups is not None:
                self.save(groups=groups, status='starting', files=None, error='', failed=[])
            here = groups is None and self.st.get('status') == 'received'
            if not here and not self.fetch_all():
                return False
            if self.st.get('auto'):
                return place.apply_when_free(self)
            state.notify('Transfer: everything is here', 'Open Transfer and press "Put in place".')
            return True

    def fetch_all(self):
        """try until everything is here; False when it failed or the time was up"""
        give_up = time.time() + state.RETRY_FOR
        error = ''
        while time.time() < give_up:
            before = self.got
            try:
                self.fetch_once()
                self.save(status='received', error='')
                return True
            except (PermissionError, check.BadPeer, net.TooOld) as e:
                self.save(status='failed', error=str(e))
                return False
            except (OSError, ValueError) as e:
                error = str(e)
            if self.got > before:           # only real progress buys more time
                give_up = time.time() + state.RETRY_FOR
            self.save(status='reconnecting', error=error)
            time.sleep(state.RETRY_PAUSE)
        self.save(status='interrupted', error=error)
        state.notify('Transfer stopped', 'Open Transfer on both devices to go on where it stopped.')
        return False

    def fetch_once(self, first=False):
        stage = self.stage()
        t = self.open()
        try:
            if not first:
                self.save(status='receiving', error='')
            Fetch(self, t, stage, first).run()
        finally:
            t.close()

    def fetch_first(self, groups):
        """before the big part: only the login look and the accounts list (a few KB), so the
        steps that need the admin password can run now, while you are here"""
        with state.locked('receiver.lock'):
            self.save(groups=groups, status='starting', files=None, error='', failed=[])
            self.fetch_once(first=True)

    def new_accounts(self):
        """other people's accounts that apply() makes: they need a password typed here"""
        try:
            return generated.new_accounts(self.stage() / 'generated/accounts.json')
        except check.BadPeer:
            return []

    def root_setup(self, passwords):
        return after.root_setup(self, self.stage(), passwords)

    def conflicts(self):
        return place.conflicts(self)

    def apply(self, passwords=None):
        """put what was received into place; place.AppsOpen when apps must be closed first"""
        with state.locked('receiver.lock'):
            return place.apply(self, passwords)
