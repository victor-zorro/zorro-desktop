"""app window"""
import sys
from .base import load_conf
from .fxshim import Snow, zorro_fx
from .keyd import style_osd
from .pages_desktop import DesktopPages
from .pages_look import LookPages
from .pages_mobile import MobilePages
from .pages_network import NetworkPages
from .pages_thinkpad import ThinkpadPages
from .ui import Group
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk


# ---- the app window: top tabs: Theme, Desktop, Login screen, Hardware, Power, Network ---

class Win(ThinkpadPages, DesktopPages, LookPages, MobilePages, NetworkPages,
          Gtk.ApplicationWindow):
    def __init__(self, app, select=None):
        super().__init__(application=app, title='Zorro')
        self.timers = []
        self.set_default_size(860, 620)
        self.set_icon_name('preferences-desktop')
        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack = stack
        hb = Gtk.HeaderBar(show_close_button=True)
        hb.set_custom_title(Gtk.StackSwitcher(stack=stack))
        self.set_titlebar(hb)
        style_osd(self.get_screen())
        self.groups = {}

        hw = Group()                    # devices, and the ThinkPad's own keys and lights
        hw.section('hw', 'Hardware', self.hw_page())
        hw.section('keys', 'ThinkPad', self.keys_page())
        hw.section('lights', None, self.lights_page())
        power = Group()
        power.section('power', 'Power', self.power_page())
        net = Group()                   # Wi-Fi, Ethernet, mobile data, NetBird
        wifi, eth, nb = self.network_pages()
        net.section('wifi', 'Wi-Fi', wifi)
        net.section('eth', 'Ethernet', eth)
        net.section('lte', 'Mobile (LTE)', self.mobile_page())
        net.section('nb', 'NetBird', nb)
        desk = Group()
        desk.section('wall', 'Wallpaper', self.wall_page())
        desk.section('dial', 'Launcher', self.dial_page())
        desk.section('orb', 'Info circle', self.fx_page('orb', self.orb_page()))
        desk.section('fx', 'Overlays', self.fx_page('overlay'))
        desk.section('windows', 'Windows', self.windows_page())
        desk.section('text', 'Text & colours', self.text_page())
        desk.section('applook', 'This app', self.fx_page('app'))
        login = Group()
        login.section('look', 'Login & lock screen', self.look_page())
        theme = Group()
        theme.section('theme', 'Theme', self.theme_page())
        for name, title, g in (('theme', 'Theme', theme), ('desktop', 'Desktop', desk),
                               ('login', 'Login screen', login), ('hardware', 'Hardware', hw),
                               ('power', 'Power', power), ('network', 'Network', net)):
            stack.add_titled(g.widget(), name, title)
            self.groups[name] = g
            g.select(select)

        # the app's own look: particles behind everything (Desktop → This app)
        outer = Gtk.Box()
        stack.set_hexpand(True)
        stack.set_vexpand(True)
        outer.add(stack)
        self.add(outer)
        if zorro_fx:
            self.bg_snow = Snow(outer, radius=0, fps=24, max_parts=1500, profile='app',
                                enabled=lambda: zorro_fx.settings('app')['enabled'])
            css = Gtk.CssProvider()
            css.load_from_data(b'''
                window.zfx-app scrolledwindow, window.zfx-app viewport,
                window.zfx-app stack, window.zfx-app list,
                window.zfx-app list row:not(:selected) { background: none; }''')
            Gtk.StyleContext.add_provider_for_screen(
                self.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.timers.append(GLib.timeout_add(300, self.follow_app_bg))
        self.show_all()
        self.show_page(select)
        self.custom_box.set_visible(load_conf().get('star') == 'custom')
        self.timers.append(GLib.timeout_add_seconds(5, self.refresh))
        self.connect('destroy', self.on_destroy)

    def on_destroy(self, _w):
        """stop this window's timers; write slider changes that were still waiting"""
        for tid in self.timers:
            GLib.source_remove(tid)
        self.timers = []
        for profile, tid in list(getattr(self, 'fx_save_ids', {}).items()):
            if tid:
                GLib.source_remove(tid)
                self.fx_save(profile)
        for name in ('orb_save_id', 'win_apply_id'):
            tid = getattr(self, name, None)
            if tid:
                GLib.source_remove(tid)
                setattr(self, name, None)

    def show_page(self, pid):
        """open a sub-page by id, e.g. power:0 (sidebar + top tab)"""
        grp = next((n for n, g in self.groups.items() if pid in g.ids), None)
        if grp:
            self.stack.set_visible_child_name(grp)
            self.groups[grp].select(pid)


def cmd_app(select=None):
    from gi.repository import Gio
    app = Gtk.Application(application_id='org.zorro.settings',
                          flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)

    def on_command_line(a, cmdline):
        """runs in the first instance, also for a second 'zorro-settings --page X'"""
        args = cmdline.get_arguments()[1:]
        page = args[args.index('--page') + 1] if '--page' in args[:-1] else None
        win = a.get_active_window() or Win(a, select=page)
        if page:
            win.show_page(page)
        win.present()
        return 0
    app.connect('command-line', on_command_line)
    app.run(sys.argv[:1] + (['--page', select] if select else []))
