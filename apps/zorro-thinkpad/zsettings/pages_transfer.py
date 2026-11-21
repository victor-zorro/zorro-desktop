"""Desktop → Transfer: set up another device like this one (apps/zorro-transfer). The work
happens in the Transfer window; this page opens it on the right side and shows how a transfer
that runs in the background is doing."""
import json
import os
import shutil

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk  # noqa: E402

from .base import HOME, spawn
from .ui import Pages, button, heading, note

ZT = shutil.which('zorro-transfer', path=f'{HOME}/.local/bin:{os.environ.get("PATH", "")}')
STATE = os.path.join(os.environ.get('XDG_STATE_HOME', f'{HOME}/.local/state'), 'zorro-transfer')


def state(name):
    try:
        with open(os.path.join(STATE, name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def alive(pid):
    return bool(pid) and os.path.exists(f'/proc/{pid}')


def gb(n):
    return f'{(n or 0) / 1e9:.1f} GB'


def summary():
    """one line about a transfer going on (or the last one), '' when there is none"""
    snd, rcv = state('sender.json'), state('receiver.json')
    if alive(snd.get('pid')) and snd.get('status') != 'stopped':
        busy = [s for s in (snd.get('sessions') or {}).values() if s.get('status') == 'connected']
        if busy:
            s = busy[0]
            return f"Sending to {s.get('peer', '?')}: {gb(s.get('done'))} of {gb(s.get('total'))}"
        if snd.get('status') == 'locked':
            return 'Too many wrong codes: open Transfer and press "New code".'
        return 'This device is ready to send (the code is in the Transfer window).'
    st = rcv.get('status')
    frm = rcv.get('sender', 'the other device')
    if st in ('starting', 'receiving', 'reconnecting') and alive(rcv.get('pid')):
        return f"Getting the setup from {frm}: {gb(rcv.get('done'))} of {gb(rcv.get('total'))}"
    if st in ('received', 'waiting for apps', 'putting in place') and alive(rcv.get('pid')):
        return f"Putting it in place… {rcv.get('error') and 'close ' + rcv['error'] or ''}"
    if st in ('starting', 'receiving', 'reconnecting', 'interrupted'):
        return f'Stopped while getting the setup from {frm}: open Transfer to go on where it stopped.'
    if st in ('received', 'apps open', 'waiting for apps'):
        return 'Everything is here: open Transfer and press "Put in place".'
    if st == 'applied':
        return f"Last transfer: from {frm}, {rcv.get('moved', 0)} files put in place."
    return ''


class TransferPages:
    def transfer_page(self):
        box = Pages()
        box.add(heading('Transfer', 'Transfer'))
        box.add(note('Set up another device like this one: settings, launcher, logins, apps\' '
                     'data, personal files, installers and user accounts. On the same network or '
                     'anywhere through NetBird; a network cable is fastest. Open Transfer on both '
                     'devices: the one that has the setup sends, the new one gets it with the '
                     '6-digit code. On the new device you choose everything and type the password '
                     'once at the start; the rest runs on its own and goes on after an '
                     'interruption.'))
        row = Gtk.Box(spacing=8, margin_top=10)
        row.add(button('Send this setup', lambda: spawn([ZT, '--send']), primary=True))
        row.add(button('Get a setup from another device', lambda: spawn([ZT, '--get'])))
        row.set_sensitive(bool(ZT))
        box.add(row)
        self.tr_line = note('' if ZT else 'Transfer is missing: run ~/zorro-desktop/install.sh once.')
        self.tr_line.set_margin_top(8)
        box.add(self.tr_line)
        if ZT:
            self.tr_tick()
            self.timers.append(GLib.timeout_add_seconds(2, self.tr_tick))
        return box

    def tr_tick(self):
        if not getattr(self, 'dead', False):
            self.tr_line.set_text(summary())
        return True
