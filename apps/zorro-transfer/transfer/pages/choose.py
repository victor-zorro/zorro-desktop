"""The getting page, second step: choose what comes along, then Start.

"By itself" is on: first the few small files that need the admin password are fetched and
the password is asked, once; then the copy runs as a process of its own."""
from .. import state
from ..receiver import Receiver
from .groups import ask_groups
from .passwords import ask_passwords
from .widgets import GLib, Gtk, ROUTE, background, btn, human, label, spawn

BIG = 5e9                       # personal folders above this are not ticked


def tick_box(title, about):
    cb = Gtk.CheckButton()
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.add(label(title, markup=True))
    box.add(label(about, dim=True))
    cb.add(box)
    return cb


class Choose:
    def __init__(self, win, offer):
        self.win = win
        st = state.read_state('receiver.json')
        sender = st.get('sender', 'the other device')
        win.put(label(f'Connected to {sender}', big=True))
        win.put(label(f"{ROUTE.get(st.get('route'), '').capitalize()}. Choose what comes along:", dim=True))
        if st.get('sender_running'):
            win.put(label(f"On {sender} these are open: {', '.join(st['sender_running'])}. Close "
                          f"them there first for a clean copy of their logins and data.", dim=True))
        self.picks = {}
        self.groups(offer)
        self.auto = win.put(tick_box(
            '<b>Put everything in place by itself</b>',
            'The password is asked once, now; then it runs on its own until it is done '
            '(you can close this window). Off: you press "Put in place" at the end.'))
        self.auto.set_active(True)
        win.put(label('What it replaces on this device is kept as a .before-transfer copy.', dim=True))
        self.start = win.put(btn('Start', self.go, primary=True))
        self.line = win.put(label('', dim=True))

    def groups(self, offer):
        """a tick box per group the sender offers"""
        files_head = False
        for g in offer:
            mine = g['id'].startswith('files:')
            if mine and not files_head:
                files_head = True
                self.win.put(label('<b>Personal files</b>  <span alpha="65%">(folders up to 5 GB are '
                                   'ticked; tick the big ones if you want them too)</span>', markup=True))
            cb = tick_box(f"<b>{GLib.markup_escape_text(g['title'])}</b>  <span alpha='65%'>"
                          f"{g['files']} files · {human(g['bytes'])}</span>", g['about'])
            cb.set_active(g['bytes'] > 0 and not (mine and g['bytes'] > BIG))
            cb.set_sensitive(g['bytes'] > 0)
            self.picks[g['id']] = cb
            self.win.put(cb)

    def failed(self, e):
        self.line.set_text(f'Could not start: {e}. Try Start again.')
        self.start.set_sensitive(True)

    def go(self):
        groups = [g for g, cb in self.picks.items() if cb.get_active()]
        if not groups:
            return
        if not self.auto.get_active():
            Receiver().save(auto=False)
            return self.launch(groups)
        self.start.set_sensitive(False)
        self.line.set_text('Getting ready…')
        background(self, lambda: Receiver().fetch_first(groups),
                   lambda _: self.ready(groups), self.failed)

    def ready(self, groups):
        """the small files are here: passwords for new accounts, your groups, then the admin
        password"""
        r = Receiver()
        people = r.new_accounts()
        passwords = (ask_passwords(self.win, people) or {}) if people else {}
        mine = ask_groups(self.win, r.groups_to_add()) or []
        self.line.set_text('Asking the admin password (login look, accounts)…')

        def root():
            r.root_setup(passwords, mine)
            r.save(auto=True)
        background(self, root, lambda _: self.launch(groups), self.failed)

    def launch(self, groups):
        spawn('continue', '--groups', ','.join(groups))
        GLib.timeout_add(400, lambda: self.win.page is self and self.win.go('progress'))
