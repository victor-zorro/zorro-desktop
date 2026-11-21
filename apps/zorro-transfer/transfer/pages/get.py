"""The getting page, first step: pick the sending device (the list fills by itself) and type
its code."""
from ..receiver import Receiver, Refused, WrongCode
from .nearby_list import NearbyList
from .widgets import Gtk, background, btn, label

WRONG = ('That code is not right. Check it on the other device (it shows a new one after 3 '
         'wrong tries, and each wrong try makes the next one wait longer).')
NOTHING = 'Searching your network and NetBird…'


class Get:
    def __init__(self, win, want=None):
        self.win = win
        win.put(label('Get the setup from another device', big=True))
        win.put(label('Your devices nearby show up here by themselves. Or type a name or '
                      'address.', dim=True))
        self.msg = label(NOTHING, dim=True)
        self.near = NearbyList(self, self.picked, self.msg.set_text, want)
        win.put(self.near.box)
        win.put(self.near.ask)
        win.put(self.near.hint)
        self.host = win.put(Gtk.Entry(placeholder_text='name or address', text=want or ''))
        self.host.connect('changed', self.typed)
        row = Gtk.Box(spacing=8)
        self.code = Gtk.Entry(placeholder_text='the 6-digit code', max_length=7, width_chars=10)
        self.code.connect('activate', lambda *_: self.pair())
        row.add(self.code)
        row.add(btn('Connect', self.pair, primary=True))
        win.put(row)
        win.put(self.msg)
        win.put(btn('Back', lambda: win.go('start')))
        win.tip()

    def picked(self, host, ready):
        self.host.set_text(host)
        self.msg.set_text('')
        if ready:
            self.code.grab_focus()

    def typed(self, _entry):
        """a name typed by hand: no device of the list is picked any more"""
        chosen = self.near.chosen
        if chosen and self.host.get_text().strip() != chosen['host']:
            self.near.list.unselect_all()

    def pair(self):
        host, code = self.host.get_text().strip(), self.code.get_text().replace(' ', '')
        if not host or not code.isdigit() or len(code) != 6:
            self.msg.set_text('Pick the device (or type its name) and type the 6-digit code.')
            return
        self.msg.set_text('Connecting…')

        def failed(e):
            if isinstance(e, Refused):
                self.msg.set_text(f'{host} says: {e}')
            elif isinstance(e, WrongCode):
                self.msg.set_text(WRONG)
            elif isinstance(e, ConnectionRefusedError):
                self.msg.set_text(f'{host} is not sending yet: choose Send there first.')
            else:
                self.msg.set_text(f'Could not connect to {host}: {e}')
        background(self, lambda: Receiver().offer(host, code),
                   lambda offer: self.win.go('choose', offer), failed)
