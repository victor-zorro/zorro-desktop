"""The getting page, first step: find the sending device and type its code."""
from .. import find
from ..receiver import Receiver, Refused
from .widgets import GLib, Gtk, ROUTE, background, btn, label

WRONG = ('That code is not right. Check it on the other device (it shows a new one after 3 '
         'wrong tries, and each wrong try makes the next one wait longer).')
NOTHING = ('Nothing found yet. Is Transfer sending on the other device? You can also type its '
           'NetBird name.')


class Get:
    def __init__(self, win):
        self.win = win
        win.put(label('Get the setup from another device', big=True))
        win.put(label('Open Transfer on the other device and choose "Send this setup". It shows up '
                      'here; or type its NetBird name or address.', dim=True))
        self.found = win.put(Gtk.ListBox())
        self.found.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.found.connect('row-selected', lambda lb, r: r and self.host.set_text(r.host))
        row = Gtk.Box(spacing=8)
        self.host = Gtk.Entry(placeholder_text='name or address', hexpand=True)
        row.add(self.host)
        row.add(btn('Search again', self.search))
        win.put(row)
        row = Gtk.Box(spacing=8)
        self.code = Gtk.Entry(placeholder_text='the 6-digit code', max_length=7, width_chars=10)
        self.code.connect('activate', lambda *_: self.pair())
        row.add(self.code)
        row.add(btn('Connect', self.pair, primary=True))
        win.put(row)
        self.msg = win.put(label('', dim=True))
        win.put(btn('Back', lambda: win.go('start')))
        win.tip()
        self.search()

    def search(self):
        self.msg.set_text('Searching the network and NetBird…')
        background(self, find.discover, self.show_found,
                   lambda e: self.msg.set_text(f'Could not search: {e}'))

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
        self.msg.set_text('' if res else NOTHING)
        if len(res) == 1:
            self.found.select_row(self.found.get_row_at_index(0))

    def pair(self):
        host, code = self.host.get_text().strip(), self.code.get_text().replace(' ', '')
        if not host or not code.isdigit() or len(code) != 6:
            self.msg.set_text('Pick the device (or type its name) and type the 6-digit code.')
            return
        self.msg.set_text('Connecting…')

        def failed(e):
            if isinstance(e, Refused):
                self.msg.set_text(f'{host} says: {e}')
            elif isinstance(e, PermissionError):
                self.msg.set_text(WRONG)
            else:
                self.msg.set_text(f'Could not connect to {host}: {e}')
        background(self, lambda: Receiver().offer(host, code),
                   lambda offer: self.win.go('choose', offer), failed)
