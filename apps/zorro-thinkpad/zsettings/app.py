"""app window"""
import sys
from .base import load_conf
from .fxshim import Snow, zorro_fx
from .keyd import style_osd
from .pages_desktop import DesktopPages
from .pages_home import HomePages
from .pages_look import LookPages
from .pages_face import FacePages
from .pages_accounts import AccountsPages
from .pages_audio import AudioPages
from .pages_mobile import MobilePages
from .pages_network import NetworkPages
from .pages_thinkpad import ThinkpadPages
from .ui import Group
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk


# ---- the app window: Home (often used) + the gear: Theme, Desktop, Login screen, Hardware, Audio, Power, Network ---

class Win(HomePages, FacePages, AccountsPages, ThinkpadPages, DesktopPages, LookPages, MobilePages, NetworkPages, AudioPages,
          Gtk.ApplicationWindow):
    def __init__(self, app, select=None):
        super().__init__(application=app, title='Zorro')
        self.timers = []
        self.set_default_size(860, 620)
        self.set_icon_name('preferences-desktop')
        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack = stack
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

        hw = Group()                    # devices, and the ThinkPad's own keys and lights
        hw.section('hw', 'Hardware', self.hw_page())
        hw.section('keys', 'ThinkPad', self.keys_page())
        hw.section('lights', None, self.lights_page())
        hw.section('sys', 'System', self.sysinfo_page())
        snd = Group()                   # outputs, inputs, per app, several at once
        a_out, a_in, a_play, a_tog = self.audio_pages()
        snd.section('aout', 'Audio', a_out)
        snd.section('ain', None, a_in)
        snd.section('aplay', None, a_play)
        snd.section('atog', None, a_tog)
        power = Group()
        power.section('power', 'Power', self.power_page())
        acc = Group()                   # the logins the desktop borrows: SoundCloud, Obsidian
        sc, ob = self.accounts_pages()
        acc.section('sc', 'Accounts', sc)
        acc.section('ob', None, ob)
        net = Group()                   # Wi-Fi, Ethernet, mobile data, NetBird
        wifi, eth, nb = self.network_pages()
        net.section('wifi', 'Wi-Fi', wifi)
        net.section('eth', 'Ethernet', eth)
        net.section('lte', 'Mobile (LTE)', self.mobile_page())
        net.section('nb', 'NetBird', nb)
        desk = Group()
        desk.section('wall', 'Wallpaper', self.wall_page())
        desk.section('dial', 'Dialer', self.dial_page())
        desk.section('orb', 'Info circle', self.fx_page('orb', self.orb_page()))
        desk.section('fx', 'Overlays', self.fx_page('overlay'))
        desk.section('windows', 'Windows', self.windows_page())
        desk.section('text', 'Text & colours', self.text_page())
        desk.section('applook', 'This app', self.fx_page('app'))
        login = Group()
        login.section('look', 'Login & lock screen', self.look_page())
        login.section('face', 'Face unlock', self.face_page())
        theme = Group()
        theme.section('theme', 'Theme', self.theme_page())
        for name, title, g in (('theme', 'Theme', theme), ('desktop', 'Desktop', desk),
                               ('login', 'Login screen', login), ('hardware', 'Hardware', hw),
                               ('audio', 'Audio', snd), ('power', 'Power', power),
                               ('network', 'Network', net), ('accounts', 'Accounts', acc)):
            stack.add_titled(g.widget(), name, title)
            self.groups[name] = g
            g.select(select)

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
        if select:
            self.show_page(select)
        else:
            self.show_home()
        self.home.connect('notify::visible-child-name', lambda *a: self.sync_header())
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
        """open a sub-page by id, e.g. power:0 (sidebar + top tab), in all setup"""
        grp = next((n for n, g in self.groups.items() if pid in g.ids), None)
        if grp:
            self.show_setup()
            self.stack.set_visible_child_name(grp)
            self.groups[grp].select(pid)

    def show_setup(self):
        self.cam_stop()
        self.top.set_visible_child_name('setup')
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
