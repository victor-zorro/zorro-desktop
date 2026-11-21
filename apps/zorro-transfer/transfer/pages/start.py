"""The first page: send this setup, or get one."""
from .. import net
from .widgets import btn, label


class Start:
    def __init__(self, win):
        self.win = win
        win.put(label('Set up another device like this one', big=True))
        win.put(label('Your settings, logins, files and the big installers go from one device to '
                      'the other: on the same network, or anywhere through NetBird. Open Transfer '
                      'on both devices.', dim=True))
        send = win.put(btn('Send this setup to another device', lambda: win.go('send', True),
                           primary=True))
        get = win.put(btn('Get the setup from another device', lambda: win.go('get')))
        try:
            net.need_psk()
        except net.TooOld as e:
            send.set_sensitive(False)
            get.set_sensitive(False)
            win.put(label(str(e)))
        win.tip()
