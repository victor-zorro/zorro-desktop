"""app window"""
import sys
from .base import load_conf
from .fxshim import Snow, zorro_fx
from .keyd import style_osd
from .pages_desktop import DesktopPages
from .pages_home import HomePages
from .pages_look import LookPages
from .pages_face import FacePages
from .pages_lang import LangPages
from .pages_apps import AppsPages
from .pages_transfer import TransferPages
from .pages_accounts import AccountsPages
from .pages_audio import AudioPages
from .pages_mobile import MobilePages
from .pages_network import NetworkPages
from .pages_bluetooth import BluetoothPages
from .pages_printers import PrinterPages
from .pages_thinkpad import ThinkpadPages
from .ui import Group
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk


# ---- the app window: Home (often used) + the gear: Network, Audio, Power, Hardware, Desktop, Look, Accounts ---

TABS = (('network', 'Network'), ('audio', 'Audio'), ('power', 'Power'), ('hardware', 'Hardware'),
        ('desktop', 'Desktop'), ('login', 'Look'), ('accounts', 'Accounts'))
SECTION_TAB = {'wifi': 'network', 'eth': 'network', 'lte': 'network', 'nb': 'network',
               'aout': 'audio', 'ain': 'audio', 'aplay': 'audio', 'atog': 'audio',
               'power': 'power', 'hw': 'hardware', 'pad': 'hardware', 'keys': 'hardware', 'lights': 'hardware',
               'sys': 'hardware', 'wall': 'desktop', 'dial': 'desktop', 'orb': 'desktop',
               'fx': 'desktop', 'windows': 'desktop', 'text': 'desktop', 'lang': 'desktop',
               'applook': 'desktop', 'apps': 'desktop', 'transfer': 'desktop', 'theme': 'login', 'look': 'login', 'face': 'login',
               'sc': 'accounts', 'ob': 'accounts'}


class Win(HomePages, FacePages, LangPages, AppsPages, TransferPages, AccountsPages, ThinkpadPages, PrinterPages, BluetoothPages, DesktopPages, LookPages, MobilePages, NetworkPages, AudioPages,
          Gtk.ApplicationWindow):
    def __init__(self, app, select=None):
        super().__init__(application=app, title='Zorro')
        self.timers = []
        self.set_default_size(860, 620)
        self.set_icon_name('preferences-desktop')
        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack = stack
        self.first_shown = {}           # tab: [work to do when it is first opened]
        # header: Home shows "Zorro" and the gear; all setup shows the tabs and a way back
        hb = Gtk.HeaderBar(show_close_button=True)
        self.titles = Gtk.Stack()
        t_home = Gtk.Label()
        t_home.set_markup('<b>Zorro</b>')
        self.titles.add_named(t_home, 'home')
        self.titles.add_named(Gtk.StackSwitcher(stack=stack), 'setup')
        hb.set_custom_title(self.titles)
        self.back = Gtk.Button.new_from_icon_name('go-previous-symbolic', Gtk.IconSize.BUTTON)
        self.back.set_tooltip_text('Home')
        self.back.connect('clicked', lambda b: self.show_home())
        hb.pack_start(self.back)
        self.gear = Gtk.Button(label='⚙  All setup', relief=Gtk.ReliefStyle.NONE)
        self.gear.set_tooltip_text('Everything that is set up once: theme, desktop, hardware, power, network')
        self.gear.connect('clicked', lambda b: self.show_setup())
        hb.pack_end(self.gear)
        self.set_titlebar(hb)
        style_osd(self.get_screen())
        self.groups = {}

        # each tab is built when it is first needed (opened, or a link points into it), the
        # rest one by one once the window is on screen: F9 shows Home without waiting for them
        self.tab_builders = {'network': self.build_network, 'audio': self.build_audio,
                             'power': self.build_power, 'hardware': self.build_hardware,
                             'desktop': self.build_desktop, 'login': self.build_look,
                             'accounts': self.build_accounts}
        self.tab_boxes = {}
        for name, title in TABS:
            holder = Gtk.Box(hexpand=True, vexpand=True)
            stack.add_titled(holder, name, title)
            self.tab_boxes[name] = holder
        stack.connect('notify::visible-child-name', lambda st, _p: self.tab_on_screen())
        if select:
            self.tab(SECTION_TAB.get(select.split(':')[0], 'hardware'))

        # the app's own look: particles behind everything (Desktop → This app)
        outer = Gtk.Box()
        stack.set_hexpand(True)
        stack.set_vexpand(True)
        self.top = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True, vexpand=True)
        self.top.add_named(self.home_widget(), 'home')
        self.top.add_named(stack, 'setup')
        outer.add(self.top)
        self.add(outer)
        if zorro_fx:
            self.bg_snow = Snow(outer, radius=0, fps=12, max_parts=1500, profile='app',
                                enabled=lambda: zorro_fx.settings('app')['enabled'])
            # a calm 12 fps while you use the window, still while another window is in front
            self.connect('notify::is-active',
                         lambda w, _p: self.bg_snow.set_fps(12 if w.is_active() else 0))
            css = Gtk.CssProvider()
            css.load_from_data(b'''
                window.zfx-app scrolledwindow, window.zfx-app viewport,
                window.zfx-app stack, window.zfx-app list,
                window.zfx-app list row:not(:selected) { background: none; }''')
            Gtk.StyleContext.add_provider_for_screen(
                self.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.timers.append(GLib.timeout_add(1000, self.follow_app_bg))
        self.show_all()
        if select:
            self.show_page(select)
        else:
            self.show_home()
        self.home.connect('notify::visible-child-name', lambda *a: self.sync_header())
        # slow probes (hardware scan, SoundCloud check, the login preview) wait for their tab
        stack.connect('notify::visible-child-name', lambda *a: self.run_first_shown())
        self.top.connect('notify::visible-child-name', lambda *a: self.run_first_shown())
        self.run_first_shown()
        self.rest_id = GLib.timeout_add(300, self.build_rest)
        self.timers.append(GLib.timeout_add_seconds(5, self.refresh))
        self.connect('destroy', self.on_destroy)

    # -- the tabs, built on demand
    def tab(self, name):
        """this tab's Group, built now if it was not yet"""
        g = self.groups.get(name)
        if g is None and name in self.tab_builders and not getattr(self, 'dead', False):
            g = self.tab_builders.pop(name)()
            self.groups[name] = g
            w = g.widget()
            self.tab_boxes[name].add(w)
            w.show_all()
            g.select(None)
        return g

    def tab_on_screen(self):
        """the tab you now see is built (not while Home is in front)"""
        if getattr(self, 'top', None) and self.top.get_visible_child_name() == 'setup':
            self.tab(self.stack.get_visible_child_name())

    def build_rest(self):
        """one more tab per idle moment, until all are there"""
        self.rest_id = None
        if self.tab_builders and not getattr(self, 'dead', False):
            self.tab(next(iter(self.tab_builders)))
            self.rest_id = GLib.idle_add(self.build_rest)
        return False

    def build_network(self):
        net = Group()                   # Wi-Fi, Ethernet, mobile data, NetBird
        wifi, eth, nb = self.network_pages()
        net.section('wifi', 'Wi-Fi', wifi)
        net.section('eth', 'Ethernet', eth)
        net.section('lte', 'Mobile (LTE)', self.mobile_page())
        net.section('nb', 'NetBird', nb)
        return net

    def build_audio(self):
        snd = Group()                   # outputs, inputs, per app, several at once
        a_out, a_in, a_play, a_tog = self.audio_pages()
        snd.section('aout', None, a_out)              # the tab is called Audio already
        snd.section('ain', None, a_in)
        snd.section('aplay', None, a_play)
        snd.section('atog', None, a_tog)
        return snd

    def build_power(self):
        power = Group()
        power.section('power', None, self.power_page())
        return power

    def build_hardware(self):
        hw = Group()                    # devices, and the ThinkPad's own keys and lights
        hw.section('hw', None, self.hw_page())
        hw.section('pad', None, self.pad_page())
        hw.section('keys', 'ThinkPad', self.keys_page())
        hw.section('lights', None, self.lights_page())
        hw.section('sys', 'System', self.sysinfo_page())
        self.custom_box.set_visible(load_conf().get('star') == 'custom')
        return hw

    def build_desktop(self):
        desk = Group()                  # three groups; each part a small sub-heading
        desk.heading('Desktop')
        desk.section('wall', 'Wallpaper', self.wall_page(), sub=True)
        desk.section('dial', 'Dialer', self.dial_page(), sub=True)
        desk.section('orb', 'Info circle', self.fx_page('orb', self.orb_page()), sub=True)
        desk.heading('Windows & text')
        desk.section('windows', 'Windows', self.windows_page(), sub=True)
        desk.section('text', None, self.text_page())         # Text & colours, Icons
        desk.section('lang', None, self.lang_page())         # Spell checking
        desk.heading('Effects')
        desk.section('fx', 'Overlays', self.fx_page('overlay'), sub=True)
        desk.section('applook', 'This app', self.fx_page('app'), sub=True)
        desk.heading('Apps')
        desk.section('apps', None, self.apps_page())         # Install apps
        desk.section('transfer', None, self.transfer_page())  # Transfer: set up another device
        return desk

    def build_look(self):
        login = Group()                 # Look: the theme presets, then the login / lock screen itself
        login.section('theme', 'Theme', self.theme_page())
        login.section('look', 'Login & lock screen', self.look_page())
        login.section('face', 'Face unlock', self.face_page())
        return login

    def build_accounts(self):
        acc = Group()                   # the logins the desktop borrows: SoundCloud, Obsidian
        sc, ob = self.accounts_pages()
        acc.section('sc', None, sc)
        acc.section('ob', None, ob)
        return acc

    def on_destroy(self, _w):
        """stop this window's timers; write slider changes that were still waiting"""
        from .ui import flush_later
        flush_later()
        self.dead = True                # build_rest / tab: nothing more into this window
        if getattr(self, 'rest_id', None):
            GLib.source_remove(self.rest_id)
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
        """open a sub-page by id, e.g. power:0 (sidebar + top tab), in all setup"""
        if ':' not in pid:
            pid += ':0'
        self.tab(SECTION_TAB.get(pid.split(':')[0], ''))     # built now if it was not yet
        grp = next((n for n, g in self.groups.items() if pid in g.ids), None)
        if grp:
            self.stack.set_visible_child_name(grp)       # first: so only this tab is built
            self.show_setup()
            self.groups[grp].select(pid)

    def show_setup(self):
        self.cam_stop()
        self.top.set_visible_child_name('setup')
        self.tab_on_screen()
        self.sync_header()

    def show_home(self):
        self.cam_stop()
        self.top.set_visible_child_name('home')
        self.home.set_visible_child_name('dash')
        self.home_refresh()
        self.sync_header()

    def sync_header(self):
        on_home = self.top.get_visible_child_name() == 'home'
        dash = on_home and self.home.get_visible_child_name() == 'dash'
        self.titles.set_visible_child_name('home' if on_home else 'setup')
        sub = {'eq': 'Equaliser', 'cam': 'Webcam'}.get(self.home.get_visible_child_name())
        self.titles.get_child_by_name('home').set_markup(f'<b>{sub or "Zorro"}</b>')
        self.back.set_visible(not dash)
        self.gear.set_visible(on_home)
        if on_home and self.home.get_visible_child_name() != 'cam':
            self.cam_stop()

    def when_shown(self, tab, fn):
        """do fn the first time this setup tab is on screen (at once if it already is)"""
        if hasattr(self, 'top') and self.tab_on(tab):
            fn()
        else:
            self.first_shown.setdefault(tab, []).append(fn)

    def run_first_shown(self):
        if self.top.get_visible_child_name() != 'setup':
            return
        for fn in self.first_shown.pop(self.stack.get_visible_child_name(), []):
            fn()

    def tab_on(self, name):
        """is this setup tab on screen (not hidden behind Home)?"""
        return self.top.get_visible_child_name() == 'setup' and self.stack.get_visible_child_name() == name


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
