"""The sending page: the code to type on the other device, then the progress.
The sender itself is a process of its own (zorro-transfer send); this page shows its state
and tells it to stop, or to offer a new code after too many wrong ones."""
import os
import subprocess
import time

from .. import state
from .widgets import GLib, Gtk, ROUTE, btn, eta, human, label, num, spawn


def addresses():
    ips = []
    try:
        out = subprocess.run(['ip', '-o', '-4', 'addr', 'show', 'scope', 'global'],
                             capture_output=True, text=True, timeout=3).stdout
        for ln in out.splitlines():
            f = ln.split()
            kind = 'NetBird' if f[1].startswith('wt') else 'Wi-Fi' if f[1].startswith('wl') else \
                'cable' if f[1].startswith(('en', 'eth')) else f[1]
            ips.append(f"{f[3].split('/')[0]} ({kind})")
    except (OSError, subprocess.SubprocessError, IndexError):
        pass
    return 'Reachable at ' + ', '.join(ips) if ips else ''


class Send:
    def __init__(self, win, start):
        self.win = win
        if start:
            win.sender = spawn('send', '--gui-pid', str(os.getpid()))
        win.put(label('Sending this setup', big=True))
        self.how = win.put(label(f'On the other device: open Transfer, choose "Get the setup", pick '
                                 f'"{state.device_name()}" and type this code:', dim=True))
        self.code = win.put(label('…', markup=True))
        win.put(label(addresses(), dim=True))
        self.bar = win.put(Gtk.ProgressBar(show_text=True, no_show_all=True))
        self.line = win.put(label('', dim=True))
        row = Gtk.Box(spacing=8)
        row.add(btn('Go on in the background', win.destroy))
        row.add(btn('Stop', self.stop))
        self.fresh = btn('New code', lambda: self.signal('sender.unlock'))
        self.fresh.set_no_show_all(True)
        row.add(self.fresh)
        win.put(row)
        win.tip()
        win.every(500, self.tick)

    def sender_pid(self):
        """the sender this page belongs to, None when none runs"""
        mine = self.win.sender
        if mine and mine.poll() is None:
            return mine.pid
        pid = state.read_state('sender.json').get('pid')
        return pid if state.is_transfer(pid) else None

    def signal(self, name):
        pid = self.sender_pid()
        if pid:                             # no sender: no file left for the next one
            state.write_pid(name, pid)

    def stop(self):
        self.signal('sender.stop')
        self.win.go('start')

    def show_code(self, st, busy):
        code = str(st.get('code') or '')
        self.how.set_visible(not busy and bool(code))
        self.fresh.set_visible(bool(st.get('why')))
        if busy:                            # one at a time: no code while sending
            peer = GLib.markup_escape_text(str(busy.get('peer', '?')))
            self.code.set_markup(f"<span size='x-large' weight='bold'>Sending to {peer}</span>")
        elif st.get('why'):
            self.code.set_markup(f"<b>{GLib.markup_escape_text(str(st['why']))}</b>")
        else:
            self.code.set_markup(f'<span size="300%" weight="bold" letter_spacing="6000">'
                                 f'{code[:3]} {code[3:]}</span>' if code else '…')

    def show_progress(self, st, busy, sessions):
        if busy:
            total, done, speed = (num(busy.get(k)) for k in ('total', 'done', 'speed'))
            self.bar.show()
            self.bar.set_fraction(min(1, done / total) if total else 0)
            self.bar.set_text(f'{human(done)} of {human(total)}' if total else 'connected')
            self.line.set_text(f"To {busy.get('peer', '?')}, {ROUTE.get(busy.get('route'), '')} · "
                               f"{human(speed)}/s · {eta(total - done, speed)}\n"
                               f"{busy.get('current', '')}")
        elif any(s.get('status') == 'done' and time.time() - num(s.get('updated')) < 600
                 for s in sessions):
            self.bar.show()
            self.bar.set_fraction(1)
            self.bar.set_text('Done: everything was sent')
            self.line.set_text('')
        elif st.get('status') == 'wrong code':
            self.line.set_text('Someone typed a wrong code. Each wrong try makes the next one wait '
                               'longer; after 10 no code is offered any more.')

    def tick(self):
        st = state.read_state('sender.json')
        sessions = [s for s in (st.get('sessions') or {}).values() if isinstance(s, dict)]
        busy = [s for s in sessions if s.get('status') in ('connected', 'paired')
                and time.time() - num(s.get('updated')) < 30]
        busy = busy[-1] if busy else None
        self.show_code(st, busy)
        self.show_progress(st, busy, sessions)
        if not self.sender_pid():
            self.line.set_text('Not sending any more.')
        return True
