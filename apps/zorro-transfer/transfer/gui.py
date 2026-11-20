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
    def __init__(self, first=None):
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
        elif rcv.get('status') in ('starting', 'receiving', 'reconnecting', 'interrupted', 'received', 'apps open',
                                   'waiting for apps', 'putting in place'):
            self.get_progress_page()
        elif first == '--send':
            self.send_page(start=True)
        elif first == '--get':
            self.get_page()
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
        if st.get('sender_running'):
            self.put(label(f"On {st.get('sender', 'the other device')} these are open: "
                           f"{', '.join(st['sender_running'])}. Close them there first for a clean copy "
                           f"of their logins and data.", dim=True))
        self.picks = {}
        files_head = False
        for g in offer:
            if g['id'].startswith('files:') and not files_head:
                files_head = True
                self.put(label('<b>Personal files</b>  <span alpha="65%">(folders up to 5 GB are '
                               'ticked; tick the big ones if you want them too)</span>', markup=True))
            big = g['id'].startswith('files:') and g['bytes'] > 5e9
            cb = Gtk.CheckButton(active=g['bytes'] > 0 and not big)
            cb.set_sensitive(g['bytes'] > 0)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            box.add(label(f"<b>{GLib.markup_escape_text(g['title'])}</b>  <span alpha='65%'>"
                          f"{g['files']} files · {human(g['bytes'])}</span>", markup=True))
            box.add(label(g['about'], dim=True))
            cb.add(box)
            self.picks[g['id']] = cb
            self.put(cb)
        self.auto = Gtk.CheckButton(active=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add(label('<b>Put everything in place by itself</b>', markup=True))
        box.add(label('The password is asked once, now; then it runs on its own until it is done '
                      '(you can close this window). Off: you press "Put in place" at the end.', dim=True))
        self.auto.add(box)
        self.put(self.auto)
        self.put(label('What it replaces on this device is kept as a .before-transfer copy.', dim=True))
        self.start_btn = self.put(btn('Start', self.get_start, primary=True))
        self.start_line = self.put(label('', dim=True))
        self.show_all()
        return False

    def get_start(self):
        groups = [g for g, cb in self.picks.items() if cb.get_active()]
        if not groups:
            return
        if not self.auto.get_active():
            engine.Receiver().save(auto=False)
            return self.launch(groups)
        # by itself: first the few small files that need the password, then the password, once
        self.start_btn.set_sensitive(False)
        self.start_line.set_text('Getting ready…')

        def first():
            r = engine.Receiver()
            try:
                r.fetch_first(groups)
            except (OSError, ConnectionError, ValueError, PermissionError) as e:
                GLib.idle_add(self.start_line.set_text, f'Could not start: {e}. Try Start again.')
                GLib.idle_add(self.start_btn.set_sensitive, True)
                return
            GLib.idle_add(self.get_ready, groups)
        threading.Thread(target=first, daemon=True).start()

    def get_ready(self, groups):
        r = engine.Receiver()
        passwords = {}
        people = r.new_accounts()
        if people:
            passwords = self.ask_passwords(people) or {}
        self.start_line.set_text('Asking the admin password (login look, accounts)…')

        def root():
            r.root_setup(passwords)
            r.save(auto=True)
            GLib.idle_add(self.launch, groups)
        threading.Thread(target=root, daemon=True).start()
        return False

    def launch(self, groups):
        subprocess.Popen([ME, 'continue', '--groups', ','.join(groups)], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        GLib.timeout_add(400, lambda: self.get_progress_page() and False)
        return False

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
        running = alive(st.get('pid'))
        if status in ('starting', 'receiving', 'reconnecting') and not running:
            status = 'interrupted'
        if status in ('received', 'waiting for apps'):
            if st.get('auto') and running:
                status = 'putting in place' if status == 'received' else status
            elif status == 'waiting for apps':
                status = 'apps open'
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
        elif status == 'putting in place':
            self.gline.set_text('Everything is here; putting it in place…')
        elif status == 'waiting for apps':
            self.gline.set_text(f"Everything is here. It goes into place by itself once these are "
                                f"closed: {st.get('error', '')}")
        elif status == 'apps open':
            self.gline.set_text(f"Close these first, then press Put in place again: {st.get('error', '')}")
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
            if status in ('starting', 'receiving', 'reconnecting', 'putting in place', 'waiting for apps'):
                self.gbtns.add(btn('Go on in the background', self.destroy))
            elif status == 'interrupted':
                self.gbtns.add(btn('Try again', self.get_continue, primary=True))
            elif status in ('received', 'apps open'):
                self.gbtns.add(btn('Put in place', self.get_apply, primary=True))
            elif status in ('applied', 'failed'):
                self.gbtns.add(btn('Close', self.destroy))
                self.gbtns.add(btn('Another transfer', self.start_page))
            self.gbtns.show_all()
        return True

    def get_continue(self):
        subprocess.Popen([ME, 'continue'], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def ask_passwords(self, people):
        """a password for each new account, typed here; {name: password} or None (cancel)"""
        d = Gtk.Dialog(title='New accounts', transient_for=self, modal=True)
        d.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Make the accounts', Gtk.ResponseType.OK)
        box = d.get_content_area()
        box.set_border_width(16)
        box.set_spacing(8)
        lab = Gtk.Label(xalign=0, wrap=True, max_width_chars=50)
        lab.set_text('These people had an account on the other device. Choose a password for '
                     'each (tell them; they can change it later). Leave it empty to skip one.')
        box.add(lab)
        grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        entries = {}
        for i, a in enumerate(people):
            grid.attach(Gtk.Label(label=f"{a['full'] or a['name']} ({a['name']})", xalign=0), 0, i, 1, 1)
            pair = []
            for j, hint in enumerate(('password', 'again')):
                e = Gtk.Entry(visibility=False, placeholder_text=hint, activates_default=True)
                grid.attach(e, 1 + j, i, 1, 1)
                pair.append(e)
            entries[a['name']] = pair
        box.add(grid)
        warn = Gtk.Label(xalign=0)
        box.add(warn)
        d.set_default_response(Gtk.ResponseType.OK)
        d.show_all()
        while True:
            if d.run() != Gtk.ResponseType.OK:
                d.destroy()
                return None
            out = {n: p[0].get_text() for n, p in entries.items()}
            bad = [n for n, p in entries.items() if p[0].get_text() != p[1].get_text()]
            if not bad:
                d.destroy()
                return out
            warn.set_markup(f'<b>The two passwords differ for {", ".join(bad)}</b>')

    def get_apply(self):
        passwords = {}
        people = engine.Receiver().new_accounts()
        if people:
            passwords = self.ask_passwords(people)
            if passwords is None:
                return
        self.gline.set_text('Putting it in place… (the login look and accounts ask your password)')
        for c in self.gbtns.get_children():
            c.set_sensitive(False)

        def work():
            r = engine.Receiver()
            try:
                r.apply(passwords)
            except PermissionError as e:
                r.save(status='apps open', error=str(e))
            self.gstate = None              # the buttons again on the next look
        threading.Thread(target=work, daemon=True).start()


def main(first=None):
    socket.setdefaulttimeout(None)
    Win(first)
    Gtk.main()
    return 0
