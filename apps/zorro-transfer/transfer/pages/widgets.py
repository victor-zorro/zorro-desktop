"""Small things every page of the Transfer window uses."""
import os
import subprocess
import sys
import threading

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk, Pango  # noqa: E402

ME = os.path.realpath(sys.argv[0])
ROUTE = {'cable': 'over the cable', 'wifi': 'over Wi-Fi', 'netbird': 'over NetBird (internet)',
         'mobile': 'over mobile data', 'local': 'on this device', 'local network': 'on the local network'}


def num(x):
    """a number from a state file, 0 when it is something else"""
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else 0


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


def own_route():
    """how this device is online: for the 'a cable is faster' tip"""
    try:
        out = subprocess.run(['ip', 'route', 'show', 'default'], capture_output=True, text=True,
                             timeout=3).stdout.split()
        dev = out[out.index('dev') + 1] if 'dev' in out else ''
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
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


def spawn(*args):
    """a zorro-transfer of its own, which lives on when the window closes"""
    return subprocess.Popen([ME, *args], start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def background(page, work, done, failed, must_finish=False):
    """run work() off the screen's thread, then done(result) or failed(error) on it;
    nothing when the window shows another page by then. must_finish: closing the window
    waits for it."""
    def back(fn, arg):
        if page.win.page is page:
            fn(arg)
        return False

    def run():
        try:
            result = work()
        except Exception as e:              # whatever it is, the page must hear of it
            GLib.idle_add(back, failed, e)
        else:
            GLib.idle_add(back, done, result)
    threading.Thread(target=run, daemon=not must_finish).start()
