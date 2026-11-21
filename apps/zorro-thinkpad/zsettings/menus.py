"""Which app holds which menu, and what each menu's submenu shows (RULES.md: app → menu →
submenu → page; at most 7 entries each)."""
from .base import load_conf
from .ui import Group

APPS = {'desktop': 'Desktop', 'system': 'System', 'devs': 'DEVS', 'connect': 'Connect'}
MENUS = {
    'desktop': (('home', 'Home'), ('dialer', 'Dialer'), ('desktop', 'Desktop'), ('windows', 'Windows'),
                ('look', 'Look'), ('login', 'Login'), ('accounts', 'Accounts')),
    'system': (('network', 'Network'), ('audio', 'Audio'), ('power', 'Power'),
               ('hardware', 'Hardware'), ('thinkpad', 'ThinkPad')),
    'devs': (('devs', 'DEVS'),),
    'connect': (('transfer', 'Transfer'), ('newdevice', 'New device'), ('install', 'Install apps')),
}
MENU_APP = {menu: app for app, menus in MENUS.items() for menu, _title in menus}
# a page's address is SECTION:N (e.g. power:1); the section says which menu it is in
SECTION_MENU = {
    'dial': 'dialer', 'wall': 'desktop', 'orb': 'desktop',
    'windows': 'windows', 'text': 'windows', 'lang': 'windows',
    'theme': 'look', 'fx': 'look', 'applook': 'look', 'face': 'look', 'look': 'login',
    'sc': 'accounts', 'ob': 'accounts',
    'wifi': 'network', 'eth': 'network', 'lte': 'network', 'nb': 'network',
    'aout': 'audio', 'ain': 'audio', 'aplay': 'audio', 'atog': 'audio', 'power': 'power',
    'hw': 'hardware', 'pad': 'hardware', 'screens': 'hardware', 'sys': 'hardware',
    'keys': 'thinkpad', 'lights': 'thinkpad',
    'transfer': 'transfer', 'boot': 'newdevice', 'nblink': 'newdevice', 'apps': 'install',
}


class Menus:
    """builds each menu when it is first needed: a Group (submenu + pages) or one widget"""

    def menu_builders(self):
        return {'home': self.home_widget, 'dialer': self.build_dialer, 'desktop': self.build_desktop,
                'windows': self.build_windows, 'look': self.build_look, 'login': self.build_login,
                'accounts': self.build_accounts, 'network': self.build_network,
                'audio': self.build_audio, 'power': self.build_power,
                'hardware': self.build_hardware, 'thinkpad': self.build_thinkpad,
                'devs': self.devs_widget, 'transfer': self.build_transfer,
                'newdevice': self.build_newdevice, 'install': self.build_install}

    # -- Desktop
    def build_dialer(self):
        g = Group()
        g.section('dial', None, self.dial_page())
        return g

    def build_desktop(self):
        g = Group()
        g.section('wall', 'Wallpaper', self.wall_page(), sub=True)
        g.section('orb', 'Info circle', self.fx_page('orb', self.orb_page()), sub=True)
        return g

    def build_windows(self):
        g = Group()
        g.section('windows', None, self.windows_page())
        g.section('text', None, self.text_page())           # Text & colours, Icons
        g.section('lang', None, self.lang_page())           # Spell checking
        return g

    def build_look(self):
        g = Group()
        g.section('theme', None, self.theme_page())
        g.section('fx', 'Overlays', self.fx_page('overlay'), sub=True)
        g.section('applook', 'This app', self.fx_page('app'), sub=True)
        g.section('face', None, self.face_page())
        return g

    def build_login(self):
        g = Group()
        g.section('look', None, self.look_page())
        return g

    def build_accounts(self):
        g = Group()
        sc, ob = self.accounts_pages()
        g.section('sc', None, sc)
        g.section('ob', None, ob)
        return g

    # -- System
    def build_network(self):
        g = Group()
        wifi, eth, nb = self.network_pages()
        g.section('wifi', 'Wi-Fi', wifi)
        g.section('eth', 'Ethernet', eth)
        g.section('lte', 'Mobile (LTE)', self.mobile_page())
        g.section('nb', 'NetBird', nb)
        return g

    def build_audio(self):
        g = Group()
        a_out, a_in, a_play, a_tog = self.audio_pages()
        for name, pages in (('aout', a_out), ('ain', a_in), ('aplay', a_play), ('atog', a_tog)):
            g.section(name, None, pages)
        return g

    def build_power(self):
        g = Group()
        g.section('power', None, self.power_page())
        return g

    def build_hardware(self):
        g = Group()
        g.section('hw', None, self.hw_page())
        g.section('pad', None, self.pad_page())
        g.section('screens', None, self.screens_page())
        g.section('sys', None, self.sysinfo_page())
        return g

    def build_thinkpad(self):
        g = Group()
        g.section('keys', None, self.keys_page())
        g.section('lights', None, self.lights_page())
        self.custom_box.set_visible(load_conf().get('star') == 'custom')
        return g

    # -- Connect
    def build_transfer(self):
        g = Group()
        g.section('transfer', None, self.transfer_page())
        return g

    def build_newdevice(self):
        g = Group()
        g.section('boot', None, self.newdevice_page())
        g.section('nblink', None, self.netbird_link_page())
        return g

    def build_install(self):
        g = Group()
        g.section('apps', None, self.apps_page())
        return g
