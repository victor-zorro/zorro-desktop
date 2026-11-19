"""app: Mobile tab, the built-in LTE modem (zorro-lte through pkexec)"""
import json
import os
import shutil
import subprocess
import threading

from .base import load_conf, update_conf
from .ui import Pages, heading, idle, later, note
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk  # noqa: E402

LTE = '/usr/local/lib/zorro-lte/zorro-lte'     # root-owned copy (apps/zorro-thinkpad/install.sh)


def lte(*args, stdin=None, timeout=180):
    """run the root-owned zorro-lte through polkit; (ok, output)"""
    if not shutil.which('pkexec'):
        return False, '!! pkexec is not installed: sudo apt install pkexec'
    try:
        r = subprocess.run(['pkexec', LTE, *args], input=stdin, capture_output=True, text=True,
                           timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def last_line(out):
    """the tool's last '==' or '!!' line: what the user needs to read"""
    lines = [ln.strip('=! ').strip() for ln in out.splitlines() if ln.startswith(('==', '!!'))]
    return lines[-1] if lines else (out.strip().splitlines() or [''])[-1]


class MobilePages:
    """Mobile tab: modem status, SIM PIN, mobile data (a mixin of the app window)"""

    def mobile_page(self):
        box = Pages()
        self.lte_busy = False
        self.lte_msg = note()
        box.footer(self.lte_msg)

        box.add(heading('Built-in LTE modem', 'Status'))
        self.lte_status = Gtk.Label(xalign=0, wrap=True)
        box.add(self.lte_status)
        row = Gtk.Box(spacing=8, margin_top=8)
        self.lte_wake_btn = Gtk.Button(label='Start the modem')
        self.lte_wake_btn.connect('clicked', lambda b: self.lte_run(
            'Starting the modem (up to a minute)…', 'wake'))
        row.add(self.lte_wake_btn)
        b = Gtk.Button(label='Restart the modem')
        b.connect('clicked', lambda b: self.lte_run('Restarting the modem (up to a minute)…',
                                                    'reset'))
        row.add(b)
        b = Gtk.Button(label='Check again')
        b.connect('clicked', lambda b: self.lte_refresh())
        row.add(b)
        box.add(row)
        box.add(note('The Intel XMM7360 in this T14. After a start or a standby it can be deaf '
                     'until it is restarted; Start does that by itself when needed.'))

        box.add(heading('SIM PIN', 'SIM'))
        self.lte_sim = Gtk.Label(xalign=0, wrap=True)
        box.add(self.lte_sim)
        row = Gtk.Box(spacing=8, margin_top=6)
        self.lte_pin = Gtk.Entry(visibility=False, max_length=8, width_chars=10,
                                 input_purpose=Gtk.InputPurpose.PIN, placeholder_text='PIN')
        self.lte_pin.connect('activate', lambda e: self.lte_unlock())
        row.add(self.lte_pin)
        self.lte_remember = Gtk.CheckButton(label='Remember on this laptop')
        row.add(self.lte_remember)
        b = Gtk.Button(label='Unlock')
        b.get_style_context().add_class('suggested-action')
        b.connect('clicked', lambda b: self.lte_unlock())
        row.add(b)
        box.add(row)
        self.lte_forget = Gtk.Button(label='Forget the stored PIN', halign=Gtk.Align.START,
                                     margin_top=6)
        self.lte_forget.connect('clicked', lambda b: self.lte_run('Forgetting the PIN…',
                                                                  'forget-pin'))
        box.add(self.lte_forget)
        box.add(note('The PIN is tried once per click: after three wrong PINs the SIM needs '
                     'its PUK (from your provider). Remembered, it is stored readable for root '
                     'only and unlocks the SIM whenever the modem starts; a stored PIN that '
                     'turns out wrong is deleted at once.'))

        box.add(heading('Mobile data', 'Data'))
        self.lte_data = Gtk.Switch(halign=Gtk.Align.START)
        self.lte_data_id = self.lte_data.connect('notify::active', self.lte_data_toggled)
        line = Gtk.Box(spacing=12)
        line.add(Gtk.Label(label='Mobile data'))
        line.add(self.lte_data)
        box.add(line)
        grid = Gtk.Grid(column_spacing=12, row_spacing=8, margin_top=8)
        grid.attach(Gtk.Label(label='Access point (APN)', xalign=0), 0, 0, 1, 1)
        self.lte_apn = Gtk.Entry(placeholder_text='automatic (from the SIM)', width_chars=24,
                                 text=load_conf().get('lte', {}).get('apn', ''))
        self.lte_apn.connect('changed', lambda e: later('apn', lambda: update_conf('lte', apn=e.get_text().strip())))
        grid.attach(self.lte_apn, 1, 0, 1, 1)
        box.add(grid)
        box.add(note('Wi-Fi and the cable stay first: mobile data is only used while they are '
                     'off. Leave the APN empty: it is looked up for your SIM; type one only if '
                     'your provider tells you to.'))

        missing = [] if shutil.which('pkexec') else ['sudo apt install pkexec']
        if not os.path.exists(LTE):
            missing.append('sudo apps/zorro-thinkpad/install.sh')
        if missing:
            self.lte_status.set_text('Not installed yet, run at the laptop:\n' + '\n'.join(missing))
            for w in (self.lte_wake_btn, self.lte_pin, self.lte_data):
                w.set_sensitive(False)
        else:
            self.lte_refresh()
            self.timers.append(GLib.timeout_add_seconds(30, self.lte_tick))
        return box

    def lte_tick(self):
        if self.tab_on('network') and not self.lte_busy:
            self.lte_refresh(quiet=True)
        return True

    def lte_bg(self, busy, fn, then):
        if self.lte_busy:
            return
        self.lte_busy = True
        if busy:
            self.lte_msg.set_text(busy)

        def work():
            res = fn()
            idle(lambda: (setattr(self, 'lte_busy', False), then(res)) and False)
        threading.Thread(target=work, daemon=True).start()

    def lte_run(self, busy, *args, stdin=None):
        def done(res):
            ok, out = res
            self.lte_msg.set_text(last_line(out) if out else ('Done' if ok else 'Failed'))
            self.lte_refresh(quiet=True)
        self.lte_bg(busy, lambda: lte(*args, stdin=stdin), done)

    def lte_refresh(self, quiet=False):
        def done(res):
            ok, out = res
            try:
                st = json.loads(out.strip().splitlines()[-1]) if ok else None
            except (ValueError, IndexError):
                st = None
            self.lte_show(st, out)
            if not quiet:
                self.lte_msg.set_text('')
        self.lte_bg('' if quiet else 'Asking the modem…', lambda: lte('state', timeout=40), done)

    def lte_show(self, st, out=''):
        if st is None:
            self.lte_status.set_text('No answer from zorro-lte: ' + last_line(out or ''))
            return
        if not st['modem']:
            text = 'No LTE modem found.'
        elif not st['awake']:
            text = 'The modem is asleep. Start it.'
        elif st['sim'] != 'READY':
            text = 'The modem is on; the SIM is locked.' if st['sim'] == 'SIM PIN' else \
                f'The modem is on; SIM: {st["sim"] or "?"}'
        elif st['registered']:
            sig = f'{st["signal"]}%' if st['signal'] is not None else '?'
            text = (f'{st["operator"] or "Network"} {st["tech"]}  ·  signal {sig}'
                    + ('  ·  roaming' if st['roaming'] else ''))
        else:
            text = 'The SIM is unlocked; looking for a network…'
        if st['data']:
            text += f'\nMobile data on: {st["ip"]}'
        self.lte_status.set_text(text)
        self.lte_wake_btn.set_label('Start the modem' if not st['awake'] else 'Start again')
        self.lte_sim.set_text({'READY': 'The SIM is unlocked.',
                               'SIM PIN': 'The SIM asks for its PIN.',
                               'SIM PUK': 'The SIM is blocked: it needs its PUK (use a phone).',
                               '': 'Start the modem first.'}.get(st['sim'], f'SIM: {st["sim"]}'))
        self.lte_forget.set_visible(st['pin_stored'])
        self.lte_data.handler_block(self.lte_data_id)
        self.lte_data.set_active(st['data'])
        self.lte_data.handler_unblock(self.lte_data_id)
        self.lte_data.set_sensitive(st['awake'] and st['sim'] == 'READY')

    def lte_unlock(self):
        pin = self.lte_pin.get_text().strip()
        if not pin.isdigit() or not 4 <= len(pin) <= 8:
            self.lte_msg.set_text('A PIN is 4 to 8 digits')
            return
        self.lte_pin.set_text('')
        args = ['pin-stdin'] + (['--remember'] if self.lte_remember.get_active() else [])
        self.lte_run('Unlocking the SIM…', *args, stdin=pin + '\n')

    def lte_data_toggled(self, sw, _p):
        if sw.get_active():
            apn = load_conf().get('lte', {}).get('apn', '').strip()
            self.lte_run('Connecting mobile data (up to a minute)…', 'up', *([apn] if apn else []))
        else:
            self.lte_run('Mobile data off…', 'down')
