"""keep the screen on during calls and videos (part of keyd)

Two reasons to stay awake:
- an app asks for it: Firefox (video, calls), Signal, Chromium and Electron apps call
  org.freedesktop.ScreenSaver.Inhibit on the session bus. Openbox has nobody answering that
  name, so we do; an inhibit ends with UnInhibit or when the app quits.
- a call is going on: the camera or the microphone is in use (any app, also web calls).
While awake, the X idle timer is reset every 20 s (xset s reset), so the screen saver,
the screen blanking and xss-lock's lock screen do not start.
"""
import threading

from gi.repository import Gio, GLib

from .base import load_conf, run
from .lights import camera_or_mic_in_use

IFACE = '''<node><interface name="org.freedesktop.ScreenSaver">
  <method name="Inhibit"><arg type="s" direction="in"/><arg type="s" direction="in"/>
    <arg type="u" direction="out"/></method>
  <method name="UnInhibit"><arg type="u" direction="in"/></method>
  <method name="SimulateUserActivity"/>
  <method name="GetActive"><arg type="b" direction="out"/></method>
  <method name="GetActiveTime"><arg type="u" direction="out"/></method>
  <method name="GetSessionIdleTime"><arg type="u" direction="out"/></method>
  <method name="SetActive"><arg type="b" direction="in"/><arg type="b" direction="out"/></method>
</interface></node>'''
EVERY = 20                                  # seconds; the screen saver starts after 600


class Awake:
    def __init__(self):
        self.inhibits = {}                  # cookie -> (bus name, app, reason)
        self.watches = {}                   # bus name -> watch id
        self.cookie = 0
        self.call = False
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        info = Gio.DBusNodeInfo.new_for_xml(IFACE).interfaces[0]
        for path in ('/org/freedesktop/ScreenSaver', '/ScreenSaver'):   # apps use either
            self.bus.register_object(path, info, self.on_call, None, None)
        Gio.bus_own_name_on_connection(self.bus, 'org.freedesktop.ScreenSaver',
                                       Gio.BusNameOwnerFlags.NONE, None, None)
        GLib.timeout_add_seconds(EVERY, self.tick)

    def on_call(self, _conn, sender, _path, _iface, method, params, inv):
        if method == 'Inhibit':
            app, reason = params.unpack()
            self.cookie += 1
            self.inhibits[self.cookie] = (sender, app, reason)
            if sender not in self.watches:              # the app quits: its inhibit ends
                self.watches[sender] = Gio.bus_watch_name_on_connection(
                    self.bus, sender, Gio.BusNameWatcherFlags.NONE, None, self.gone)
            self.reset()
            inv.return_value(GLib.Variant('(u)', (self.cookie,)))
        elif method == 'UnInhibit':
            self.inhibits.pop(params.unpack()[0], None)
            inv.return_value(None)
        elif method == 'SimulateUserActivity':
            self.reset()
            inv.return_value(None)
        elif method in ('GetActive', 'SetActive'):
            inv.return_value(GLib.Variant('(b)', (False,)))
        else:                                           # GetActiveTime, GetSessionIdleTime
            inv.return_value(GLib.Variant('(u)', (0,)))

    def gone(self, _conn, name):
        for c in [c for c, v in self.inhibits.items() if v[0] == name]:
            del self.inhibits[c]
        wid = self.watches.pop(name, None)
        if wid:
            Gio.bus_unwatch_name(wid)

    @staticmethod
    def reset():
        run('xset', 's', 'reset')

    def tick(self):
        if self.inhibits or self.call:
            self.reset()
        # the camera / microphone check reads /proc and asks PipeWire: off the main loop
        if load_conf().get('awake_calls', True):
            threading.Thread(target=self.check_call, daemon=True).start()
        else:
            self.call = False
        return True

    def check_call(self):
        self.call = camera_or_mic_in_use()

    def status(self):
        """why the screen stays on right now ('' = it may lock)"""
        if self.call:
            return 'camera or microphone in use'
        return ', '.join(sorted({v[1] for v in self.inhibits.values()}))
