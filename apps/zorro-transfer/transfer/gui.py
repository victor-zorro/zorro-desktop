"""The Transfer window, the same on both devices.

Start: two choices, "Send this setup" and "Get the setup". A transfer only starts from here,
with this window open; once it runs, "Go on in the background" closes the window and the copy
continues (open Transfer again to see it). Both devices show the same progress."""
import os
import socket
import subprocess
import sys
import threading
import time

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from . import engine, items  # noqa: E402

ME = os.path.realpath(sys.argv[0])
ROUTE = {'cable': 'over the cable', 'wifi': 'over Wi-Fi', 'netbird': 'over NetBird (internet)',
         'mobile': 'over mobile data', 'local': 'on this device', 'local network': 'on the local network'}


def human(n):
    for unit in ('bytes', 'KB', 'MB', 'GB', 'TB'):
        if n < 1000 or unit == 'TB':
            return f'{n:.0f} {unit}' if unit in ('bytes', 'KB') else f'{n:.1f} {unit}'
        n /= 1000


def eta(left, speed):
    if speed <= 0:
        return ''
    s = int(left / speed)
    return f'{s // 3600} h {s % 3600 // 60:02d} min left' if s >= 3600 else \
        f'{s // 60} min {s % 60:02d} s left' if s >= 60 else f'{s} s left'


def alive(pid):
    try:
        return bool(pid) and 'zorro-transfer' in open(f'/proc/{pid}/cmdline').read()
    except OSError:
        return False


def own_route():
    """how this device is online: for the 'a cable is faster' tip"""
    try:
        out = subprocess.run(['ip', 'route', 'show', 'default'], capture_output=True, text=True,
                             timeout=3).stdout.split()
        dev = out[out.index('dev') + 1] if 'dev' in out else ''
    except (OSError, subprocess.SubprocessError, ValueError):
        return ''
    return 'wifi' if dev.startswith('wl') else 'cable' if dev.startswith(('en', 'eth')) else ''


def label(text='', markup=False, big=False, dim=False, wrap=True):
    lb = Gtk.Label(xalign=0, wrap=wrap)
    lb.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if markup or big or dim:
        t = text if markup else GLib.markup_escape_text(text)
        if big:
            t = f'<span size="xx-large" weight="bold">{t}</span>'
        if dim:
            t = f'<span alpha="65%">{t}</span>'
        lb.set_markup(t)
    else:
        lb.set_text(text)
    return lb


def btn(text, cb, primary=False):
    b = Gtk.Button(label=text)
    if primary:
        b.get_style_context().add_class('suggested-action')
    b.connect('clicked', lambda *_: cb())
    return b


class Win(Gtk.Window):
    def __init__(self):
        super().__init__(title='Transfer')
        self.set_default_size(620, 520)
        self.set_icon_name('folder-remote')
        self.connect('destroy', Gtk.main_quit)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=22)
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.add(self.body)
        self.add(sc)
        self.timer = None
        snd, rcv = engine.read_state('sender.json'), engine.read_state('receiver.json')
        if alive(snd.get('pid')) and snd.get('status') != 'stopped':
            self.send_page(start=False)
        elif rcv.get('status') in ('starting', 'receiving', 'reconnecting', 'interrupted', 'received'):
            self.get_progress_page()
        else:
            self.start_page()
        self.show_all()

    def clear(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None
        for c in self.body.get_children():
            self.body.remove(c)

    def put(self, w):
        """the next line of the page"""
        self.body.pack_start(w, False, False, 0)
        return w

    def tip(self):
        if own_route() == 'wifi':
            self.put(label('Tip: connect both devices with a network cable if you can. It is much '
                           'faster and steadier than Wi-Fi. Wi-Fi works too.', dim=True))

    # -- start
    def start_page(self):
        self.clear()
        self.put(label('Set up another device like this one', big=True))
        self.put(label('Your settings, logins, files and the big installers go from one device to '
                       'the other: on the same network, or anywhere through NetBird. Open Transfer '
                       'on both devices.', dim=True))
        self.put(btn('Send this setup to another device', lambda: self.send_page(start=True), primary=True))
        self.put(btn('Get the setup from another device', self.get_page))
        self.tip()
        self.show_all()

    # -- sender
    def send_page(self, start):
        self.clear()
        if start:
            subprocess.Popen([ME, 'send', '--gui-pid', str(os.getpid())], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.put(label('Sending this setup', big=True))
        self.how = self.put(label(f'On the other device: open Transfer, choose "Get the setup", pick '
                                  f'"{engine.device_name()}" and type this code:', dim=True))
        self.code = self.put(label('…', markup=True))
        self.addr = self.put(label('', dim=True))
        self.sbar = self.put(Gtk.ProgressBar(show_text=True, no_show_all=True))
        self.sline = self.put(label('', dim=True))
        row = Gtk.Box(spacing=8)
        row.add(btn('Go on in the background', self.destroy))
        row.add(btn('Stop', self.send_stop))
        self.put(row)
        self.tip()
        self.show_all()
        self.addr.set_text(self.addresses())
        self.timer = GLib.timeout_add(500, self.send_tick)

    def addresses(self):
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

    def send_tick(self):
        st = engine.read_state('sender.json')
        code = st.get('code', '')
        busy = [s for s in st.get('sessions', {}).values()
                if s.get('status') in ('connected', 'paired') and time.time() - s.get('updated', 0) < 30]
        self.how.set_visible(not busy)
        if busy:                            # one at a time: no code while sending
            self.code.set_markup(f"<span size='x-large' weight='bold'>Sending to "
                                 f"{GLib.markup_escape_text(busy[-1].get('peer', '?'))}</span>")
        else:
            self.code.set_markup(f'<span size="300%" weight="bold" letter_spacing="6000">'
                                 f'{code[:3]} {code[3:]}</span>' if code else '…')
        if busy:
            s = busy[-1]
            total, done = s.get('total') or 0, s.get('done') or 0
            self.sbar.show()
            self.sbar.set_fraction(done / total if total else 0)
            self.sbar.set_text(f'{human(done)} of {human(total)}' if total else 'connected')
            self.sline.set_text(f"To {s.get('peer', '?')}, {ROUTE.get(s.get('route'), '')} · "
                                f"{human(s.get('speed') or 0)}/s · "
                                f"{eta(total - done, s.get('speed') or 0)}\n{s.get('current', '')}")
        elif any(s.get('status') == 'done' and time.time() - s.get('updated', 0) < 600
                 for s in st.get('sessions', {}).values()):
            self.sbar.show()
            self.sbar.set_fraction(1)
            self.sbar.set_text('Done: everything was sent')
            self.sline.set_text('')
        elif st.get('status') == 'wrong code':
            self.sline.set_text('Someone typed a wrong code. After 3 wrong tries a new code is made.')
        if not alive(st.get('pid')):
            self.sline.set_text('Not sending any more.')
        return True

    def send_stop(self):
        engine.STATE.mkdir(parents=True, exist_ok=True)
        (engine.STATE / 'sender.stop').touch()
        self.start_page()

    # -- receiver
    def get_page(self):
        self.clear()
        self.put(label('Get the setup from another device', big=True))
        self.put(label('Open Transfer on the other device and choose "Send this setup". It shows up '
                       'here; or type its NetBird name or address.', dim=True))
        self.found = self.put(Gtk.ListBox())
        self.found.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.found.connect('row-selected', lambda lb, r: r and self.host.set_text(r.host))
        row = Gtk.Box(spacing=8)
        self.host = Gtk.Entry(placeholder_text='name or address', hexpand=True)
        row.add(self.host)
        row.add(btn('Search again', self.search))
        self.put(row)
        row = Gtk.Box(spacing=8)
        self.code_in = Gtk.Entry(placeholder_text='the 6-digit code', max_length=7, width_chars=10)
        self.code_in.connect('activate', lambda *_: self.pair())
        row.add(self.code_in)
        row.add(btn('Connect', self.pair, primary=True))
        self.put(row)
        self.msg = self.put(label('', dim=True))
        self.put(btn('Back', self.start_page))
        self.tip()
        self.show_all()
        self.search()

    def search(self):
        self.msg.set_text('Searching the network and NetBird…')

        def work():
            res = engine.discover()
            GLib.idle_add(self.show_found, res)
        threading.Thread(target=work, daemon=True).start()

    def show_found(self, res):
        for c in self.found.get_children():
            self.found.remove(c)
        for f in res:
            r = Gtk.ListBoxRow()
            r.host = f['host']
            r.add(label(f"<b>{GLib.markup_escape_text(f['name'])}</b>  "
                        f"<span alpha='65%'>{GLib.markup_escape_text(ROUTE.get(f['via'], f['via']))} · "
                        f"{GLib.markup_escape_text(f['host'])}</span>", markup=True))
            self.found.add(r)
        self.found.show_all()
        self.msg.set_text('' if res else 'Nothing found yet. Is Transfer sending on the other device? '
                          'You can also type its NetBird name.')
        if len(res) == 1:
            self.found.select_row(self.found.get_row_at_index(0))
        return False

    def pair(self):
        host, code = self.host.get_text().strip(), self.code_in.get_text().replace(' ', '')
        if not host or not code.isdigit() or len(code) != 6:
            self.msg.set_text('Pick the device (or type its name) and type the 6-digit code.')
            return
        self.msg.set_text('Connecting…')

        def work():
            try:
                offer = engine.Receiver().offer(host, code)
                GLib.idle_add(self.choose_page, offer)
            except PermissionError:
                GLib.idle_add(self.msg.set_text, 'That code is not right. Check it on the other device '
                              '(after 3 wrong tries it shows a new one).')
            except (OSError, ValueError, ConnectionError) as e:
                GLib.idle_add(self.msg.set_text, f'Could not reach {host}: {e}')
        threading.Thread(target=work, daemon=True).start()

    def choose_page(self, offer):
        self.clear()
        st = engine.read_state('receiver.json')
        self.put(label(f"Connected to {st.get('sender', '?')}", big=True))
        self.put(label(f"{ROUTE.get(st.get('route'), '').capitalize()}. Choose what comes along:", dim=True))
        self.picks = {}
        for g in offer:
            cb = Gtk.CheckButton(active=g['bytes'] > 0)
            cb.set_sensitive(g['bytes'] > 0)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            box.add(label(f"<b>{GLib.markup_escape_text(g['title'])}</b>  <span alpha='65%'>"
                          f"{g['files']} files · {human(g['bytes'])}</span>", markup=True))
            box.add(label(g['about'], dim=True))
            cb.add(box)
            self.picks[g['id']] = cb
            self.put(cb)
        self.put(label('Nothing changes here until you press "Put in place" at the end; what it '
                       'replaces is kept as a .before-transfer copy.', dim=True))
        self.put(btn('Start', self.get_start, primary=True))
        self.show_all()
        return False

    def get_start(self):
        groups = [g for g, cb in self.picks.items() if cb.get_active()]
        if not groups:
            return
        subprocess.Popen([ME, 'continue', '--groups', ','.join(groups)], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        GLib.timeout_add(400, lambda: self.get_progress_page() and False)

    def get_progress_page(self):
        self.clear()
        self.put(label('Getting the setup', big=True))
        self.gline0 = self.put(label('', dim=True))
        self.gbar = self.put(Gtk.ProgressBar(show_text=True))
        self.gline = self.put(label('', dim=True))
        self.gbtns = self.put(Gtk.Box(spacing=8))
        self.tip()
        self.show_all()
        self.gstate = None
        self.get_tick()
        self.timer = GLib.timeout_add(500, self.get_tick)
        return False

    def get_tick(self):
        st = engine.read_state('receiver.json')
        status = st.get('status', '')
        if status in ('starting', 'receiving', 'reconnecting') and not alive(st.get('pid')):
            status = 'interrupted'
        total, done = st.get('total') or 0, st.get('done') or 0
        self.gbar.set_fraction(min(1, done / total) if total else 0)
        self.gbar.set_text(f'{human(done)} of {human(total)}' if total else '')
        self.gline0.set_text(f"From {st.get('sender', '?')}, {ROUTE.get(st.get('route'), '')}")
        if status == 'receiving':
            self.gline.set_text(f"{human(st.get('speed') or 0)}/s · {eta(total - done, st.get('speed') or 0)}"
                                f"\n{st.get('current', '')}")
        elif status == 'reconnecting':
            self.gline.set_text('The connection dropped: trying again… (it goes on where it stopped)')
        elif status == 'interrupted':
            self.gline.set_text(f"Stopped: {st.get('error', '')}. It goes on where it stopped once the "
                                f"other device sends again (open Transfer there: Send this setup).")
        elif status == 'received':
            n = len(engine.Receiver().conflicts())
            self.gline.set_text('Everything is here. ' + (
                f'{n} of these files replace different ones on this device; those are kept as '
                f'.before-transfer copies.' if n else 'Nothing on this device gets replaced.'))
        elif status == 'applied':
            notes = '; '.join(st.get('notes') or [])
            self.gline.set_text(f"Done: {st.get('moved', 0)} files put in place"
                                + (f" ({notes})" if notes else '') + ". Log out and in once to see all settings.")
        elif status == 'failed':
            self.gline.set_text(f"It did not work: {st.get('error', '')}")
        if status != self.gstate:               # the buttons that fit
            self.gstate = status
            for c in self.gbtns.get_children():
                self.gbtns.remove(c)
            if status in ('starting', 'receiving', 'reconnecting'):
                self.gbtns.add(btn('Go on in the background', self.destroy))
            elif status == 'interrupted':
                self.gbtns.add(btn('Try again', self.get_continue, primary=True))
            elif status == 'received':
                self.gbtns.add(btn('Put in place', self.get_apply, primary=True))
            elif status in ('applied', 'failed'):
                self.gbtns.add(btn('Close', self.destroy))
                self.gbtns.add(btn('Another transfer', self.start_page))
            self.gbtns.show_all()
        return True

    def get_continue(self):
        subprocess.Popen([ME, 'continue'], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def get_apply(self):
        self.gline.set_text('Putting it in place… (the login look asks your password)')
        for c in self.gbtns.get_children():
            c.set_sensitive(False)

        def work():
            engine.Receiver().apply()
        threading.Thread(target=work, daemon=True).start()


def main():
    socket.setdefaulttimeout(None)
    Win()
    Gtk.main()
    return 0
