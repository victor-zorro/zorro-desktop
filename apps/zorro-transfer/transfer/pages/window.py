"""The Transfer window, the same on both devices.

Start: two choices, "Send this setup" and "Get the setup". A transfer only starts from here,
with this window open; once it runs, "Go on in the background" closes the window and the copy
continues (open Transfer again to see it). Both devices show the same progress."""
import socket
import ssl

from .. import state
from .choose import Choose
from .get import Get
from .progress import Progress
from .send import Send
from .start import Start
from .widgets import GLib, Gtk, label, own_route

PAGES = {'start': Start, 'send': Send, 'get': Get, 'choose': Choose, 'progress': Progress}
GETTING = ('starting', 'receiving', 'reconnecting', 'interrupted', 'received', 'apps open',
           'waiting for apps', 'putting in place')


class Win(Gtk.Window):
    def __init__(self, first=None, host=None):
        super().__init__(title='Transfer')
        self.set_default_size(620, 520)
        self.set_icon_name('folder-remote')
        self.connect('destroy', Gtk.main_quit)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=22)
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.add(self.body)
        self.add(sc)
        self.timer = self.page = self.sender = None
        state.write_pid('window.pid')       # the sender watches the window that shows it
        snd, rcv = state.read_state('sender.json'), state.read_state('receiver.json')
        if not hasattr(ssl.SSLContext, 'set_psk_server_callback'):
            self.go('start')                # this Python is too old: the start page says so
        elif state.is_transfer(snd.get('pid')) and snd.get('status') != 'stopped':
            self.go('send', False)
        elif rcv.get('status') in GETTING:
            self.go('progress')
        elif first == '--send':
            self.go('send', True)
        elif first == '--get':
            self.go('get', host)
        else:
            self.go('start')

    def go(self, name, *args):
        """show another page"""
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None
        for c in self.body.get_children():
            self.body.remove(c)
        self.page = PAGES[name](self, *args)
        self.show_all()
        return False

    def put(self, w):
        """the next line of the page"""
        self.body.pack_start(w, False, False, 0)
        return w

    def every(self, ms, tick):
        self.timer = GLib.timeout_add(ms, tick)

    def tip(self):
        if own_route() == 'wifi':
            self.put(label('Tip: connect both devices with a network cable if you can. It is much '
                           'faster and steadier than Wi-Fi. Wi-Fi works too.', dim=True))


def main(first=None, host=None):
    socket.setdefaulttimeout(None)
    Win(first, host)
    Gtk.main()
    return 0
