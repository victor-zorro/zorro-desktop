"""background part: indicator window, evdev keys, keyboard light"""
import json
import os
import socket
import struct
import sys
import time
from pathlib import Path
from .base import EVDEV_KEYS, EXTRA_BUTTONS, KBD_LED, SOCK, update_conf
from .fxshim import Snow, zorro_fx
from .keys import KEYS
from .lights import apply_lights, dot_loop


# ---- keyd: indicator window + evdev keys + keyboard light ---------------------------------

OSD_CSS = b'''
    .zosd { background: none; padding: 12px 18px; }      /* Snow paints the black */
    .zosd label { color: #d8d8de; font-size: 12pt;           /* chromatic split, like the */
                  text-shadow: -1.2px 0 rgba(255,42,74,0.65),  /* login screen's lens        */
                               1.2px 0 rgba(25,230,255,0.65); }
    .zosd image { color: #d8d8de;
                  -gtk-icon-shadow: -1.2px 0 rgba(255,42,74,0.6), 1.2px 0 rgba(25,230,255,0.6); }
    .zosd progressbar trough { min-height: 6px; border-radius: 3px;
                               background: rgba(255,255,255,0.18); border: none; }
    .zosd progressbar progress { min-height: 6px; border-radius: 3px;
                                 background: #d8d8de; border: none;
                                 box-shadow: -1.5px 0 rgba(255,42,74,0.7), 1.5px 0 rgba(25,230,255,0.7); }
'''


_styled = set()


def style_osd(screen):
    """indicator look; the level bar's opacity follows the zorro-fx setting (live).
    Once per screen: a rebuilt app window must not add providers and timers again."""
    from gi.repository import GLib, Gtk
    if hash(screen) in _styled:
        return
    _styled.add(hash(screen))
    css = Gtk.CssProvider()
    css.load_from_data(OSD_CSS)
    Gtk.StyleContext.add_provider_for_screen(screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    if not zorro_fx:
        return
    bar = Gtk.CssProvider()
    Gtk.StyleContext.add_provider_for_screen(screen, bar, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
    last = [None]

    def update():
        data = zorro_fx.bar_css()
        if data != last[0]:
            last[0] = data
            bar.load_from_data(data)
        return True
    update()
    GLib.timeout_add(500, update)


def find_event_device(name):
    for ev in sorted(Path('/sys/class/input').glob('event*')):
        try:
            if (ev / 'device' / 'name').read_text().strip() == name:
                return Path('/dev/input') / ev.name
        except OSError:
            pass
    return None


def cmd_keyd():
    import threading
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Gdk', '3.0')
    from gi.repository import Gdk, GLib, Gtk

    # one keyd per session: a live socket means another one runs
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(str(SOCK))
        sys.exit('zorro-thinkpad keyd: already running')
    except (ConnectionRefusedError, FileNotFoundError):
        pass
    try:
        SOCK.unlink()
    except FileNotFoundError:
        pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    srv.bind(str(SOCK))
    os.chmod(SOCK, 0o600)

    style_osd(Gdk.Screen.get_default())

    class Indicator(Gtk.Window):
        """the box at the bottom centre; the window around it is the 'spill' margin where
        particles drift out. Clicks go through it. Without a compositor the window shows a
        still image of the screen behind it (taken just before it appears)."""
        def __init__(self):
            super().__init__(type=Gtk.WindowType.POPUP)
            screen = self.get_screen()
            self.composited = bool(screen.is_composited() and screen.get_rgba_visual())
            if self.composited:
                self.set_visual(screen.get_rgba_visual())
                self.set_app_paintable(True)
                self.connect('draw', self.clear_bg)
            self.set_accept_focus(False)
            outer = Gtk.Box()
            box = Gtk.Box(spacing=14, hexpand=True, vexpand=True)
            box.get_style_context().add_class('zosd')
            outer.add(box)
            self.snow = Snow(outer, radius=14, inner=box)
            self.icon = Gtk.Image()
            self.icon.set_pixel_size(28)
            box.add(self.icon)
            self.bar = Gtk.ProgressBar(valign=Gtk.Align.CENTER, hexpand=True)
            self.bar.set_size_request(200, -1)
            box.add(self.bar)
            self.label = Gtk.Label(xalign=0)
            box.add(self.label)
            self.add(outer)
            outer.show_all()
            self.hide_id = None
            self.geom = None
            self.connect('realize', self.click_through)

        @staticmethod
        def click_through(w):
            import cairo
            w.get_window().input_shape_combine_region(cairo.Region(), 0, 0)

        def clear_bg(self, _w, cr):
            cr.set_operator(0)          # CLEAR: transparent around the box
            cr.paint()
            cr.set_operator(2)          # OVER
            return False

        def show_level(self, icon, value, text):
            self.icon.set_from_icon_name(icon or 'dialog-information-symbolic', Gtk.IconSize.DIALOG)
            self.icon.set_pixel_size(28)
            if value is None:
                self.bar.hide()
                self.label.set_text(text)
            else:
                self.bar.show()
                self.bar.set_fraction(max(0, min(100, value)) / 100)
                self.label.set_text(text or f'{value}%')
                self.label.set_width_chars(5 if not text else -1)
            s = zorro_fx.settings() if zorro_fx else {}
            if not self.composited:
                # no compositor: no particle cloud; the window is cut to the icon, bar and
                # number below, so only slivers of the screen snapshot can show
                s = dict(s, spill=0)
                self.snow.max_spill = 0
            self.snow.update_spill() if zorro_fx else None
            spill = int(s.get('spill', 0))
            self.resize(1, 1)
            _, nat = self.get_preferred_size()
            disp = Gdk.Display.get_default()
            mon = disp.get_primary_monitor() or disp.get_monitor(0)
            g = mon.get_geometry()
            x = g.x + (g.width - nat.width) // 2
            y = g.y + g.height - (nat.height - 2 * spill) - 90 - spill
            geom = (x, y, nat.width, nat.height)
            if not self.composited and geom != self.geom:
                if self.get_visible():
                    self.hide()             # take the picture without ourselves in it
                    while Gtk.events_pending():
                        Gtk.main_iteration_do(False)
                self.snow.backdrop, self.snow.backdrop_at = self.grab_behind(*geom)
            self.geom = geom
            self.move(x, y)
            self.show()
            if not self.composited:
                GLib.idle_add(self.cut_to_content)
            if self.hide_id:
                GLib.source_remove(self.hide_id)
            self.hide_id = GLib.timeout_add(int(s.get('osd_seconds', 1.5) * 1000), self.done)

        def cut_to_content(self):
            """X shape: only the icon, the level bar and the text stay visible"""
            import cairo
            gw = self.get_window()
            if not gw:
                return False
            reg = cairo.Region()
            for wdg in (self.icon, self.bar, self.label):
                if wdg.get_visible():
                    a = wdg.get_allocation()
                    reg.union(cairo.RectangleInt(a.x - 3, a.y - 3, a.width + 6, a.height + 6))
            gw.shape_combine_region(reg, 0, 0)
            return False

        @staticmethod
        def grab_behind(x, y, w, h):
            """the screen under (x, y, w, h), clipped to the screen; (pixbuf, offset)"""
            root = Gdk.get_default_root_window()
            rw, rh = root.get_width(), root.get_height()
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(rw, x + w), min(rh, y + h)
            if x1 <= x0 or y1 <= y0:
                return None, (0, 0)
            return Gdk.pixbuf_get_from_window(root, x0, y0, x1 - x0, y1 - y0), (x0 - x, y0 - y)

        def done(self):
            self.hide()
            self.hide_id = None
            self.geom = None                # next time: a fresh picture of the screen
            return False

    # the window's drawing mode (real or faked transparency) is fixed when it is made:
    # make a new one whenever a compositor (picom) starts or stops
    ind = {'w': Indicator()}

    def on_composited(_screen):
        old, ind['w'] = ind['w'], Indicator()
        old.destroy()
    Gdk.Screen.get_default().connect('composited-changed', on_composited)

    def show(icon, value, text):
        try:
            if value is not None:
                value = max(0, min(100, int(value)))
            ind['w'].show_level(icon if isinstance(icon, str) else None, value, str(text or ''))
        except Exception as e:                  # noqa: BLE001 - the indicator must survive
            print(f'zorro-thinkpad keyd: indicator: {type(e).__name__}: {e}', file=sys.stderr)

    def on_msg(fd, _cond):
        try:
            m = json.loads(srv.recv(4096))
            if isinstance(m, dict):
                show(m.get('icon'), m.get('value'), m.get('text', ''))
        except (OSError, ValueError, TypeError):
            pass
        return True                             # keep listening, whatever happened
    GLib.io_add_watch(srv.fileno(), GLib.IO_IN, on_msg)

    # keys that X cannot deliver: read the ThinkPad Extra Buttons device directly
    def evdev_reader():
        fmt = 'llHHi'
        size = struct.calcsize(fmt)
        warned = False
        while True:
            dev = find_event_device(EXTRA_BUTTONS)
            try:
                with open(dev, 'rb', buffering=0) as fh:
                    warned = False
                    while True:
                        data = fh.read(size)
                        if len(data) < size:
                            break
                        _, _, typ, code, val = struct.unpack(fmt, data)
                        if typ == 1 and val == 1 and code in EVDEV_KEYS:
                            name = EVDEV_KEYS[code]
                            threading.Thread(target=KEYS[name], daemon=True).start()
            except (OSError, TypeError) as e:
                if not warned:
                    print(f'zorro-thinkpad keyd: cannot read {dev}: {e} '
                          '(run apps/zorro-thinkpad/install.sh)', file=sys.stderr)
                    warned = True
                    time.sleep(2)               # after resume the device returns quickly
                else:
                    time.sleep(15)
    threading.Thread(target=evdev_reader, daemon=True).start()
    threading.Thread(target=dot_loop, daemon=True).start()

    # Fn+Space: the firmware changes the keyboard light and pokes brightness_hw_changed
    hw = KBD_LED / 'brightness_hw_changed'
    if hw.exists():
        fh = open(hw)
        try:
            fh.read()
        except OSError:             # ENODATA until Fn+Space is first pressed after boot
            pass

        def on_kbd(_fd, _cond):
            try:
                fh.seek(0)
                lvl = int(fh.read().strip() or 0)
                mx = int((KBD_LED / 'max_brightness').read_text()) or 2
                words = {0: 'Keyboard light off', 1: 'Keyboard light low', 2: 'Keyboard light high'}
                update_conf('lights', kbd=lvl)      # remembered for login and resume
                show('keyboard-brightness-symbolic', round(lvl * 100 / mx) if lvl else None,
                     words.get(lvl, f'Keyboard light {lvl}'))
            except Exception as e:                  # noqa: BLE001 - keep watching Fn+Space
                print(f'zorro-thinkpad keyd: keyboard light: {e}', file=sys.stderr)
            return True
        GLib.io_add_watch(fh.fileno(), GLib.IO_PRI | GLib.IO_ERR, on_kbd)

    # saved light settings: now, and again after every resume (firmware resets the LEDs)
    from gi.repository import Gio
    apply_lights()

    def on_sleep(_conn, _sender, _path, _iface, _signal, params):
        if not params.unpack()[0]:                      # False = just woke up
            GLib.timeout_add(1500, lambda: apply_lights() and False)
    try:
        Gio.bus_get_sync(Gio.BusType.SYSTEM, None).signal_subscribe(
            'org.freedesktop.login1', 'org.freedesktop.login1.Manager', 'PrepareForSleep',
            '/org/freedesktop/login1', None, Gio.DBusSignalFlags.NONE, on_sleep)
    except GLib.Error as e:
        print(f'zorro-thinkpad keyd: no resume signal: {e.message}', file=sys.stderr)

    # the 'Together' sound output, if set up in the Audio tab (PipeWire needs a moment)
    from .audio import together_restore
    threading.Timer(8, together_restore).start()

    # no screen saver or lock during calls and videos (zsettings/awake.py)
    try:
        from .awake import Awake
        Awake()                 # its D-Bus object and timer keep it alive
    except GLib.Error as e:
        print(f'zorro-thinkpad keyd: screen-saver inhibit unavailable: {e.message}', file=sys.stderr)

    Gtk.main()
