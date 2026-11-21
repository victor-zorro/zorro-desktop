"""The Dialer's window: one full-screen dial per opening, built from its drawing and input parts."""
import sys
import threading

from . import applist, chat, config, groups, parts, state, status, usage
from .actions import Actions
from .arrange import Arrange
from .chatview import ChatView
from .draw import Draw
from .hub import Hub
from .keys import Keys
from .look import Gdk, GLib, Gtk, Look, xft_dpi, zorro_fx
from .mouse import Mouse
from .preview import Preview
from .rings import Rings
from .slices import Slices
from .tiles import Tiles
from .tree import Tree


class Dial(Look, Rings, Draw, Hub, Tree, Preview, Tiles, Slices, Arrange, Mouse, Keys, Actions, ChatView,
           Gtk.Window):
    def __init__(self):
        state.SCREEN_DPI = xft_dpi()        # the Text size setting, read per opening: the
        super().__init__(type=Gtk.WindowType.POPUP)     # daemon lives longer than one setting
        self.set_up_state()
        self.set_up_screen()
        self.set_up_area()
        self.groups, self.settings = groups.arrange(self.conf, self.all, self.usage)
        self.show_all()
        GLib.idle_add(self.grab)
        # the clock once a second; the icons' drift comes with the particles' redraws (20 a
        # second), or with a timer of its own when there are no particles
        self.tick_id = (GLib.timeout_add(66, self.float_tick) if not self.snow else
                        GLib.timeout_add_seconds(1, lambda: self.area.queue_draw() or True))
        # the parts' data (notes, messages…) is read once the dial is on screen, so it does
        # not hold up the first frame; hovering a part reads it at once
        GLib.timeout_add(150, self.fetch_all)

    def set_up_state(self):
        self.conf = config.load_conf()
        self.usage = usage.load_usage()
        self.all = applist.apps()
        self.closed = False
        self.filter = ''
        self.hover = None
        self.slots = []                 # (x, y, r, app, slice, position) placed this frame
        self.press = None               # (app, x, y) while the mouse button is down on an app
        self.drag = None                # (app, x, y) while an app is being dragged
        self.hold_id = None             # timer: an app held still for a moment opens its menu
        self.menu = None                # {'rows': [(label, fn)], 'x', 'y', 'rects', 'hover'}
        self.expanded = None            # a full slice shown across the dial ("+N" clicked)
        self.renaming, self.rename_text = None, ""   # a slice name being typed (right-click it)
        self.labels, self.add_label = [], None
        # the hub: six parts. Hover one: its preview; click: it stays and fills the fan
        self.mode = 'apps'              # Super always opens on the apps
        self.hub_hover = None           # a part's key, 'centre', or None
        self.hub_key = None             # a player button in the hub centre (music)
        self.parts = parts.PARTS
        self.path = {}                  # per tree part: the unfolded nodes, level by level
        self.kids = {}                  # (part, node id) -> its children (None while loading)
        self.dwell = None               # (node, level, since): resting on something that unfolds
        self.dwell_id = None
        self.preview = None             # the file whose preview is shown
        self.previews = {}              # (part, file) -> preview data (None while it is made)
        self.fetching = set()           # what was read in this opening
        self.chat = chat.Chat(self.on_gtk)      # the AI part's conversation
        self.chat_scroll, self.chat_new_at = 0, None
        self.icons, self.layouts, self.clouds, self.chat_layouts = {}, {}, {}, {}
        self.cloud, self.orb, self.ticks, self.snow = [], None, 0, None
        self.theme = Gtk.IconTheme.get_default()

    def set_up_screen(self):
        disp = Gdk.Display.get_default()
        if self.conf.get('anchor') == 'orb':       # the info circle lives on the primary screen
            mon = disp.get_primary_monitor() or disp.get_monitor(0)
        else:
            mon = disp.get_monitor_at_point(*self.pointer()) or disp.get_primary_monitor() or disp.get_monitor(0)
        g = self.geo = mon.get_geometry()
        # one unit for every size and distance: 1 on a 1920x1080 screen, 0.71 on 1366x768,
        # so the dial looks the same on every screen (times the Size settings where they apply)
        self.u = min(g.width, g.height) / 1080
        self.iu = self.u                # the icons' unit: u, less where the rings had to shrink
        scr = self.get_screen()
        self.composited = bool(scr.is_composited() and scr.get_rgba_visual())
        if self.composited:
            self.set_visual(scr.get_rgba_visual())
            self.backdrop = None
        else:                           # no compositor: a still image of the screen behind
            root = Gdk.get_default_root_window()
            self.backdrop = Gdk.pixbuf_get_from_window(root, g.x, g.y, g.width, g.height)
        self.set_app_paintable(True)
        self.move(g.x, g.y)
        self.resize(g.width, g.height)

    def set_up_area(self):
        self.connect('draw', self.paint_back)     # 1. the screen behind, dimmed
        self.area = Gtk.DrawingArea()
        self.area.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON_PRESS_MASK
                             | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.SCROLL_MASK)
        if zorro_fx:                    # 2. particles from the overlay look, around the dial
            self.snow = zorro_fx.Snow(self.area, radius=0, profile='overlay', fps=20, max_parts=900)
            self.snow.paint_edge = lambda *a: None
            self.snow.paint_box = lambda *a: None
        self.area.connect('draw', self.on_draw)   # 3. the dial
        self.area.connect('motion-notify-event', self.on_motion)
        self.area.connect('button-press-event', self.on_click)
        self.area.connect('button-release-event', self.on_release)
        self.area.connect('scroll-event', self.on_scroll)
        self.add(self.area)
        self.connect('key-press-event', self.on_key)

    @staticmethod
    def pointer():
        try:
            _, x, y = Gdk.Display.get_default().get_default_seat().get_pointer().get_position()[0:3]
            return x, y
        except (AttributeError, TypeError):
            return 0, 0

    def grab(self, tries=20):
        """keyboard and mouse to the dial; Openbox may still hold the key that started us, so
        try again a little later (without blocking the main loop: no sleep here)"""
        if self.closed or self.get_window() is None:
            return False
        seat = Gdk.Display.get_default().get_default_seat()
        if seat.grab(self.get_window(), Gdk.SeatCapabilities.ALL, True,
                     None, None, None) != Gdk.GrabStatus.SUCCESS and tries > 1:
            GLib.timeout_add(50, lambda: self.grab(tries - 1))
        return False

    # -- from other threads to the GTK thread
    def on_gtk(self, fn):
        """run fn on the GTK thread and redraw, unless the dial closed meanwhile"""
        def work():
            if not self.closed:
                fn()
                self.area.queue_draw()
            return False
        GLib.idle_add(work)

    def redraw_soon(self):
        self.on_gtk(lambda: None)

    # -- the parts' data
    def fetch_all(self):
        if not self.closed:
            for part in list(self.parts.values()):
                self.start_fetch(part)
            self.start_status()
        return False

    def start_fetch(self, part):
        """once per opening, and never twice at the same time (the daemon keeps the parts
        between openings: a second Super press must not start a second read of Notes)"""
        if part.key in self.fetching:
            return
        ticket = state.claim_fetch(part.key)
        if ticket is None:
            return
        self.fetching.add(part.key)
        threading.Thread(target=self.fetch_part, args=(part, ticket), daemon=True).start()

    def fetch_part(self, part, ticket):
        """read the part's data into a fresh copy and swap it in when complete, so the dial
        never draws a half-filled part (the old one stays until then)"""
        try:
            fresh = type(part)()
            fresh.fetch()
            if state.owns_fetch(part.key, ticket):
                self.parts[part.key] = fresh
        except Exception as e:          # noqa: BLE001 - one broken part must not stop the dial
            print(f'zorro-dial: {part.key}: {e}', file=sys.stderr)
        finally:
            state.release_fetch(part.key, ticket)
        redraw_open(self)

    def start_status(self):
        """the centre's connection and battery line"""
        ticket = state.claim_fetch('status')
        if ticket is None:
            return

        def work():
            try:
                state.STATUS['net'], state.STATUS['power'] = status.read()
            finally:
                state.release_fetch('status', ticket)
            redraw_open(self)
        threading.Thread(target=work, daemon=True).start()

    def close_dial(self):
        self.closed = True
        self.chat.cancel()
        self.hold_stop()
        Gdk.Display.get_default().get_default_seat().ungrab()
        if not state.RESIDENT:
            Gtk.main_quit()
            return
        for name in ('tick_id', 'dwell_id'):    # zorro-dial --daemon: this window goes, the process stays
            if getattr(self, name, None):
                GLib.source_remove(getattr(self, name))
                setattr(self, name, None)
        state.OPEN[:] = []
        self.destroy()


def redraw_open(dial):
    """a read is done: redraw the dial that asked and the one that is open now"""
    def work():
        for d in {dial, *state.OPEN}:
            if not d.closed:
                d.area.queue_draw()
        return False
    GLib.idle_add(work)
