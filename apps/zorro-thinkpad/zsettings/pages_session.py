"""System → Power → Lock & power off: lock, sleep, log out, restart, power off. The last
three ask once: press the button a second time to go on."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk  # noqa: E402

from .base import spawn
from .ui import Pages, button, heading, note

ACTIONS = (('Lock', ['loginctl', 'lock-session'], False),
           ('Sleep', ['systemctl', 'suspend'], False),
           ('Log out', ['openbox', '--exit'], True),
           ('Restart', ['systemctl', 'reboot'], True),
           ('Power off', ['systemctl', 'poweroff'], True))
ASK_SECONDS = 6


class SessionPages:
    def session_page(self):
        box = Pages()
        box.add(heading('Lock and power off', 'Lock & power off'))
        row = Gtk.Box(spacing=8, margin_top=6)
        self.session_buttons = {}
        for label, cmd, ask in ACTIONS:
            b = button(label, lambda l=label, c=cmd, a=ask: self.session_do(l, c, a))
            self.session_buttons[label] = b
            row.add(b)
        box.add(row)
        self.session_msg = note('Log out, Restart and Power off close everything that is open.')
        box.add(self.session_msg)
        self.session_asked = None
        return box

    def session_do(self, label, cmd, ask):
        if ask and self.session_asked != label:
            self.session_asked = label
            self.session_msg.set_text(f'{label}? Press {label} again within {ASK_SECONDS} seconds.')
            self.timers.append(GLib.timeout_add_seconds(ASK_SECONDS, self.session_forget, label))
            return
        self.session_asked = None
        spawn(cmd)

    def session_forget(self, label):
        if self.session_asked == label:
            self.session_asked = None
            self.session_msg.set_text('Log out, Restart and Power off close everything that is open.')
        return False
