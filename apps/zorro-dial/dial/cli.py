"""zorro-dial: show the dial (or close it), or stay loaded as the daemon."""
import os
import signal
import sys
import traceback

from . import state
from .look import GLib, Gtk
from .running import DAEMON_PID, PIDFILE, remove_pid, toggle_running
from .window import Dial


def toggle():
    """a Super press: a fresh dial, or close the one that is open. Whatever goes wrong, the
    daemon stays and the next press works again."""
    try:
        if state.OPEN:
            state.OPEN[0].close_dial()
        else:
            state.OPEN.append(Dial())
    except Exception:                   # noqa: BLE001 - say it in the log, keep the handler
        traceback.print_exc()
        drop_open()
    return True


def drop_open():
    """after a failure: no dial counts as open, and none stays on the screen"""
    stuck, state.OPEN[:] = list(state.OPEN), []
    for dial in stuck:
        try:
            dial.closed = True
            dial.destroy()
        except Exception:               # noqa: BLE001 - it is going away either way
            traceback.print_exc()


def daemon():
    """stay loaded (GTK, the parts, the app list); SIGUSR1 (a Super press) shows a fresh dial,
    or closes the one that is open"""
    state.RESIDENT = True
    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGUSR1, toggle)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: Gtk.main_quit() or False)
    DAEMON_PID.write_text(str(os.getpid()))     # only now: a Super press finds a handler
    try:
        Gtk.main()
    finally:
        remove_pid(DAEMON_PID)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ['--daemon']:
        return daemon()
    if toggle_running():
        return None
    PIDFILE.write_text(str(os.getpid()))
    signal.signal(signal.SIGTERM, lambda *a: GLib.idle_add(Gtk.main_quit))
    try:
        Dial()
        Gtk.main()
    finally:
        remove_pid(PIDFILE)
    return None
