"""the window: four apps (Desktop, System, DEVS, Connect) behind one switcher in the top bar;
each app has its menus in the title, each menu a submenu on the left and its pages"""
import sys
from .fxshim import Snow, zorro_fx
from .keyd import style_osd
from .menus import APPS, MENU_APP, MENUS, SECTION_MENU, Menus
from .pages_desktop import DesktopPages
from .pages_home import HomePages
from .pages_look import LookPages
from .pages_face import FacePages
from .pages_lang import LangPages
from .pages_apps import AppsPages
from .pages_transfer import TransferPages
from .pages_connect import ConnectPages
from .pages_nearby import NearbyPages
from .pages_devs import DevsPages
from .pages_screens import ScreensPages
from .pages_session import SessionPages
from .pages_accounts import AccountsPages
from .pages_audio import AudioPages
from .pages_mobile import MobilePages
from .pages_network import NetworkPages
from .pages_bluetooth import BluetoothPages
from .pages_printers import PrinterPages
from .pages_thinkpad import ThinkpadPages
from .ui import Group, flush_later
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk

PAGES = (Menus, HomePages, FacePages, LangPages, AppsPages, TransferPages, ConnectPages, NearbyPages, DevsPages,
         ScreensPages, SessionPages, AccountsPages, ThinkpadPages, PrinterPages, BluetoothPages, DesktopPages,
         LookPages, MobilePages, NetworkPages, AudioPages)


class Win(*PAGES, Gtk.ApplicationWindow):
    def __init__(self, app, select=None, show='desktop'):
        super().__init__(application=app, title='Zorro')
        self.timers = []
        self.set_default_size(980, 660)
        self.set_icon_name('preferences-desktop')
        self.first_shown = {}           # menu: [work to do when it is first on screen]
        self.groups, self.menu_boxes = {}, {}
        self.builders = self.menu_builders()
        self.apps = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True, vexpand=True)
        self.stacks = {}
        for name in APPS:
            self.stacks[name] = self.app_stack(name)
            self.apps.add_named(self.stacks[name], name)
        self.set_titlebar(self.header())
        style_osd(self.get_screen())
        outer = Gtk.Box()
        outer.add(self.apps)
        self.add(outer)
        self.app_look(outer)
        self.show_all()
        self.back.hide()
        self.apps.connect('notify::visible-child-name', lambda *a: self.on_screen())
        if select:
            self.show_page(select)
        else:
            self.show_app(show)
        self.rest_id = GLib.timeout_add(300, self.build_rest)
        self.timers.append(GLib.timeout_add_seconds(5, self.refresh))
        self.connect('destroy', self.on_destroy)

    def app_stack(self, name):
        """one app: its menus, each built when it is first needed"""
        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True, vexpand=True)
        for menu, title in MENUS[name]:
            holder = Gtk.Box(hexpand=True, vexpand=True)
            stack.add_titled(holder, menu, title)
            self.menu_boxes[menu] = holder
        stack.connect('notify::visible-child-name', lambda *a: self.on_screen())
        return stack

    def header(self):
        hb = Gtk.HeaderBar(show_close_button=True)
        self.back = Gtk.Button.new_from_icon_name('go-previous-symbolic', Gtk.IconSize.BUTTON)
        self.back.set_tooltip_text('Back to Home')
        self.back.connect('clicked', lambda b: self.show_home())
        hb.pack_start(self.back)
        box = Gtk.Box()
        box.get_style_context().add_class('linked')
        self.app_buttons = {}
        for name, title in APPS.items():
            b = Gtk.ToggleButton(label=title)
            b.connect('clicked', lambda w, n=name: w.get_active() and self.show_app(n))
            self.app_buttons[name] = b
            box.add(b)
        hb.pack_start(box)
        self.switcher = Gtk.StackSwitcher()
        hb.set_custom_title(self.switcher)
        return hb

    def app_look(self, outer):
        """the app's own look: particles behind everything (Look → This app)"""
        if not zorro_fx:
            return
        self.bg_snow = Snow(outer, radius=0, fps=12, max_parts=1500, profile='app',
                            enabled=lambda: zorro_fx.settings('app')['enabled'])
        # a calm 12 fps while you use the window, still while another window is in front
        self.connect('notify::is-active', lambda w, _p: self.bg_snow.set_fps(12 if w.is_active() else 0))
        css = Gtk.CssProvider()
        css.load_from_data(b'''
            window.zfx-app scrolledwindow, window.zfx-app viewport,
            window.zfx-app stack, window.zfx-app list,
            window.zfx-app list row:not(:selected) { background: none; }''')
        Gtk.StyleContext.add_provider_for_screen(self.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.timers.append(GLib.timeout_add(1000, self.follow_app_bg))

    # -- where you are
    def app_now(self):
        return self.apps.get_visible_child_name()

    def menu_now(self):
        stack = self.stacks.get(self.app_now())
        return stack.get_visible_child_name() if stack else None

    def tab_on(self, menu):
        """is this menu the one on screen?"""
        return self.menu_now() == menu

    def show_app(self, name):
        self.apps.set_visible_child_name(name)
        self.switcher.set_stack(self.stacks[name])
        self.switcher.set_visible(len(MENUS[name]) > 1)
        for n, b in self.app_buttons.items():
            if b.get_active() != (n == name):
                b.set_active(n == name)
        self.on_screen()

    def on_screen(self):
        """the menu you now see: built, its waiting work done, the header in step"""
        menu = self.menu_now()
        if not menu:
            return
        self.menu(menu)
        for fn in self.first_shown.pop(menu, []):
            fn()
        self.sync_header()

    def sync_header(self):
        home = self.tab_on('home')
        sub = hasattr(self, 'home') and self.home.get_visible_child_name()
        self.back.set_visible(bool(home and sub and sub != 'dash'))
        if not (home and sub == 'cam'):
            self.cam_stop()

    def show_home(self):
        self.show_app('desktop')
        self.stacks['desktop'].set_visible_child_name('home')
        self.home.set_visible_child_name('dash')
        self.home_refresh()
        self.sync_header()

    def show_page(self, pid):
        """open a page by its address, e.g. power:1 or just power"""
        if ':' not in pid:
            pid += ':0'
        name = pid.split(':')[0]
        menu = SECTION_MENU.get(name) or (name if name in MENU_APP else None)   # also: home, devs, a menu
        if not menu:
            return self.show_app('desktop')
        self.show_app(MENU_APP[menu])
        self.stacks[MENU_APP[menu]].set_visible_child_name(menu)
        group = self.menu(menu)
        if isinstance(group, Group):
            group.select(pid)

    def when_shown(self, menu, fn):
        """do fn the first time this menu is on screen (at once if it already is)"""
        if hasattr(self, 'switcher') and self.tab_on(menu):
            fn()
        else:
            self.first_shown.setdefault(menu, []).append(fn)

    # -- the menus, built on demand
    def menu(self, name):
        """this menu's Group (or widget), built now if it was not yet"""
        if name not in self.groups and name in self.builders and not getattr(self, 'dead', False):
            built = self.builders.pop(name)()
            self.groups[name] = built
            w = built.widget() if isinstance(built, Group) else built
            self.menu_boxes[name].add(w)
            w.show_all()
            if isinstance(built, Group):
                built.select(None)
            if name == 'home':
                self.home.connect('notify::visible-child-name', lambda *a: self.sync_header())
        return self.groups.get(name)

    def build_rest(self):
        """one more menu per idle moment, until all are there (DEVS waits until you open it)"""
        self.rest_id = None
        rest = [m for m in self.builders if m != 'devs']
        if rest and not getattr(self, 'dead', False):
            self.menu(rest[0])
            self.rest_id = GLib.idle_add(self.build_rest)
        return False

    def on_destroy(self, _w):
        """stop this window's timers; write slider changes that were still waiting"""
        flush_later()
        if getattr(self, 'scr_back', None):
            self.screens_back()         # a screen change you did not keep goes back now
        self.dead = True                # build_rest / menu: nothing more into this window
        if getattr(self, 'rest_id', None):
            GLib.source_remove(self.rest_id)
        for tid in self.timers:
            GLib.source_remove(tid)
        self.timers = []
        for profile, tid in list(getattr(self, 'fx_save_ids', {}).items()):
            if tid:
                GLib.source_remove(tid)
                self.fx_save(profile)


def arg(args, name):
    return args[args.index(name) + 1] if name in args[:-1] else None


def cmd_app(argv=()):
    """zorro-settings [--app desktop|system|devs|connect] [--page SECTION:N]"""
    from gi.repository import Gio
    app = Gtk.Application(application_id='org.zorro.settings',
                          flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)

    def on_command_line(a, cmdline):
        """runs in the first instance, also for a second 'zorro-settings --page X'"""
        args = cmdline.get_arguments()[1:]
        page, show = arg(args, '--page'), arg(args, '--app')
        show = show if show in APPS else None
        win = a.get_active_window() or Win(a, select=page, show=show or 'desktop')
        if page:
            win.show_page(page)
        elif show:
            win.show_app(show)
        win.present()
        return 0
    app.connect('command-line', on_command_line)
    app.run(sys.argv[:1] + list(argv))
