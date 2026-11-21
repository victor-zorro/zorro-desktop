"""DEVS in the switcher: the catalogue of features, bugs and tests (apps/zorro-devs) is a
web page served from this laptop; here it shows inside the window."""
import shutil
import socket

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk  # noqa: E402

from .base import run, spawn
from .ui import button, in_bg, note

DEVS_PORT = 8098
DEVS_URL = f'http://127.0.0.1:{DEVS_PORT}/'


def devs_running():
    try:
        with socket.create_connection(('127.0.0.1', DEVS_PORT), timeout=1):
            return True
    except OSError:
        return False


class DevsPages:
    def devs_widget(self):
        self.devs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, vexpand=True)
        self.when_shown('devs', self.devs_open)
        return self.devs_box

    def devs_open(self):
        in_bg(lambda: GLib.idle_add(self.devs_show, devs_running()))

    def devs_show(self, running):
        for c in self.devs_box.get_children():
            c.destroy()
        self.devs_box.add(self.devs_view() if running else self.devs_start_box())
        self.devs_box.show_all()
        return False

    def devs_view(self):
        try:
            gi.require_version('WebKit2', '4.1')
            from gi.repository import WebKit2
        except (ValueError, ImportError):
            return self.devs_line('DEVS is running. Showing it here needs gir1.2-webkit2-4.1.',
                                  'Open in the browser', lambda: spawn(['xdg-open', DEVS_URL]))
        view = WebKit2.WebView(hexpand=True, vexpand=True)
        view.load_uri(DEVS_URL)
        return view

    def devs_start_box(self):
        if not shutil.which('zorro-devs'):
            return self.devs_line('DEVS is not installed yet: run ~/zorro-desktop/install.sh once.')
        return self.devs_line('DEVS is not running.', 'Start it', self.devs_start)

    def devs_line(self, text, label=None, cb=None):
        box = Gtk.Box(spacing=12, margin=24, valign=Gtk.Align.START)
        box.add(note(text))
        if label:
            box.add(button(label, cb, primary=True))
        return box

    def devs_start(self):
        def work():
            run('systemctl', '--user', 'start', 'zorro-devs.service', timeout=15)
            GLib.timeout_add(1500, lambda: self.devs_open() and False)
        in_bg(work)
