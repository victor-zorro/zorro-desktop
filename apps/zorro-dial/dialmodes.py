"""zorro-dial's parts: what the fan shows when a part of the hub is kept.

Each part gives the hub a preview (title, big text, lines) and the fan three rings of
tiles. A tile: {'tile': True, 'icon': 'lucide:NAME' or an icon name, 'name', 'sub',
'act': callable, 'lit': bool, 'value': 0..1 (a ring around the icon), 'confirm': True
for actions that need a second click, 'keep': True to keep the dial open}.
Data is fetched in a thread when the dial opens; nothing runs while it is closed.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

HOME = Path.home()
APPS = Path(os.path.realpath(__file__)).parent.parent
MODES = [('apps', 'Apps', 'layout-grid'), ('music', 'Music', 'music'),
         ('notes', 'Notes', 'file-pen'), ('messages', 'Messages', 'bell'),
         ('system', 'System', 'gauge'), ('files', 'Files', 'folder')]


def run(*cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ''


def spawn(*cmd):
    try:
        subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def tile(icon, name, sub='', act=None, **kw):
    return {'tile': True, 'icon': icon, 'name': name, 'sub': sub, 'act': act, **kw}


def ago(seconds):
    s = max(0, int(seconds))
    if s < 90:
        return 'now'
    if s < 3600:
        return f'{s // 60} min'
    if s < 86400:
        return f'{s // 3600} h'
    return f'{s // 86400} d'


class Part:
    key = title = ''

    def __init__(self):
        self.ready = False

    def fetch(self):
        """slow work, in a thread"""
        self.ready = True

    def preview(self):
        return self.title.upper(), self.title, []

    def rings(self):
        return [[], [], []]

    def centre(self):
        """the hub centre clicked while this part is kept: (label shown, callable) or None"""
        return None


# ---- Messages: dunst's history ----------------------------------------------------------
APP_ICON = {'signal': 'signal-desktop', 'firefox': 'firefox', 'whatsapp': 'zorro-whatsapp',
            'google': 'zorro-google', 'drive': 'folder-remote', 'zorro': 'preferences-desktop',
            'kitty': 'kitty', 'thunderbird': 'lucide:mail', 'mail': 'lucide:mail',
            'calendar': 'lucide:calendar', 'printer': 'lucide:printer', 'cups': 'lucide:printer',
            'networkmanager': 'lucide:network', 'claude': 'claude-desktop'}


class Messages(Part):
    key, title = 'messages', 'Messages'

    def fetch(self):
        self.items = []
        try:
            data = json.loads(run('dunstctl', 'history') or '{}').get('data', [[]])[0]
        except ValueError:
            data = []
        try:
            up = float(Path('/proc/uptime').read_text().split()[0])
        except OSError:
            up = 0
        for n in data:
            v = {k: (x.get('data') if isinstance(x, dict) else x) for k, x in n.items()}
            app = (v.get('appname') or '').strip() or 'Message'
            self.items.append({'id': v.get('id'), 'app': app, 'summary': (v.get('summary') or '').strip(),
                               'body': re.sub(r'<[^>]+>', '', v.get('body') or '').strip(),
                               'age': up - (v.get('timestamp') or 0) / 1e6})
        self.ready = True

    def icon_for(self, app):
        low = app.lower()
        return next((i for k, i in APP_ICON.items() if k in low), 'lucide:bell')

    def preview(self):
        n = len(getattr(self, 'items', []))
        last = self.items[0]['summary'][:28] if n else 'nothing new'
        return 'MESSAGES', str(n), [last]

    def rings(self):
        out = []
        for m in getattr(self, 'items', [])[:9]:
            out.append(tile(self.icon_for(m['app']), m['summary'] or m['app'],
                            f'{m["app"]} · {ago(m["age"])}' + (f' · {m["body"][:40]}' if m['body'] else ''),
                            lambda m=m: spawn('dunstctl', 'history-pop', str(m['id'])),
                            remove=lambda m=m: run('dunstctl', 'history-rm', str(m['id']))))
        return [out[:2], out[2:5], out[5:9]]

    def centre(self):
        if getattr(self, 'items', []):
            return 'clear all', lambda: (run('dunstctl', 'history-clear'), self.fetch())
        return None


# ---- System: gauges, switches, power ----------------------------------------------------
def thinkpad_keys():
    sys.path.insert(0, str(APPS / 'zorro-thinkpad'))
    try:
        from zsettings import keys
        return keys
    except ImportError:
        return None


class System(Part):
    key, title = 'system', 'System'

    def fetch(self):
        bat = Path('/sys/class/power_supply/BAT0')
        try:
            self.bat = int((bat / 'capacity').read_text())
            self.bat_status = (bat / 'status').read_text().strip().lower()
        except (OSError, ValueError):
            self.bat, self.bat_status = None, ''
        wifi = re.search(r'^yes:(\d+)', run('nmcli', '-t', '-f', 'ACTIVE,SIGNAL', 'dev', 'wifi'), re.M)
        self.wifi_sig = int(wifi.group(1)) if wifi else None
        self.wifi_on = 'enabled' in run('nmcli', 'radio', 'wifi')

        def cpu():
            v = [int(x) for x in Path('/proc/stat').read_text().split('\n')[0].split()[1:]]
            return sum(v), v[3] + v[4]
        t0, i0 = cpu()
        time.sleep(0.25)
        t1, i1 = cpu()
        self.cpu = 1 - (i1 - i0) / max(1, t1 - t0)
        st = os.statvfs('/')
        self.disk = 1 - st.f_bavail / st.f_blocks
        self.bt_on = 'Powered: yes' in run('bluetoothctl', 'show')
        self.dnd = run('dunstctl', 'is-paused').strip() == 'true'
        soft = []
        for r in Path('/sys/class/rfkill').glob('rfkill*'):
            try:
                soft.append((r / 'soft').read_text().strip() == '1')
            except OSError:
                pass
        self.airplane = bool(soft) and all(soft)
        self.ready = True

    def preview(self):
        if getattr(self, 'bat', None) is None:
            return 'SYSTEM', 'System', []
        return 'BATTERY', f'{self.bat}%', [self.bat_status]

    def toggle(self, what):
        if what == 'wifi':
            run('nmcli', 'radio', 'wifi', 'off' if self.wifi_on else 'on')
        elif what == 'bt':
            run('bluetoothctl', 'power', 'off' if self.bt_on else 'on')
        elif what == 'dnd':
            run('dunstctl', 'set-paused', 'toggle')
        elif what == 'airplane':
            k = thinkpad_keys()
            if k:
                k.key_airplane()
        time.sleep(0.6)
        self.fetch()

    def rings(self):
        if not self.ready:
            return [[], [], []]
        g = [tile('lucide:battery-full', f'Battery {self.bat}%' if self.bat is not None else 'Battery',
                  self.bat_status, lambda: spawn('zorro-settings', '--page', 'power:0'),
                  value=(self.bat or 0) / 100),
             tile('lucide:wifi', 'Wi-Fi' + (f' {self.wifi_sig}%' if self.wifi_sig else ''), '',
                  lambda: spawn('zorro-settings', '--page', 'wifi:0'), value=(self.wifi_sig or 0) / 100),
             tile('lucide:activity', f'CPU {self.cpu * 100:.0f}%', '', lambda: spawn('x-terminal-emulator', '-e', 'htop'),
                  value=self.cpu),
             tile('lucide:hard-drive', f'Disk {self.disk * 100:.0f}%', 'used', None, value=self.disk)]
        sw = [tile('lucide:wifi', 'Wi-Fi', 'on' if self.wifi_on else 'off', lambda: self.toggle('wifi'),
                   lit=self.wifi_on, keep=True),
              tile('lucide:bluetooth', 'Bluetooth', 'on' if self.bt_on else 'off', lambda: self.toggle('bt'),
                   lit=self.bt_on, keep=True),
              tile('lucide:radio-tower', 'Mobile', 'LTE', lambda: spawn('zorro-settings', '--page', 'lte:0')),
              tile('lucide:plane', 'Airplane', 'on' if self.airplane else 'off', lambda: self.toggle('airplane'),
                   lit=self.airplane, keep=True),
              tile('lucide:bell', 'Do not disturb', 'on' if self.dnd else 'off', lambda: self.toggle('dnd'),
                   lit=self.dnd, keep=True)]
        pw = [tile('lucide:lock', 'Lock', '', lambda: spawn('loginctl', 'lock-session')),
              tile('lucide:power', 'Sleep', '', lambda: spawn('systemctl', 'suspend')),
              tile('lucide:log-out', 'Log out', '', lambda: spawn('openbox', '--exit'), confirm=True),
              tile('lucide:rotate-ccw', 'Restart', '', lambda: spawn('systemctl', 'reboot'), confirm=True),
              tile('lucide:power', 'Power off', '', lambda: spawn('systemctl', 'poweroff'), confirm=True),
              tile('lucide:settings', 'Settings', 'Zorro', lambda: spawn('zorro-settings'))]
        return [g, sw, pw]


# ---- Files: places, recent files, shares --------------------------------------------------
def kind_icon(path):
    ext = path.rsplit('.', 1)[-1].lower() if '.' in path else ''
    if ext in ('png', 'jpg', 'jpeg', 'gif', 'webp', 'heic', 'tif', 'tiff', 'bmp', 'svg'):
        return 'lucide:file-image'
    if ext in ('mp4', 'mov', 'mkv', 'webm', 'avi', 'mxf', 'braw'):
        return 'lucide:file-video'
    if ext in ('mp3', 'wav', 'flac', 'ogg', 'm4a', 'aac'):
        return 'lucide:file-audio'
    if ext in ('py', 'js', 'sh', 'json', 'html', 'css', 'c', 'rs', 'go'):
        return 'lucide:file-code'
    return 'lucide:file-text'


class Files(Part):
    key, title = 'files', 'Files'

    def fetch(self):
        def open_dir(p):
            return lambda: spawn('xdg-open', str(p))
        places = [('lucide:house', 'Home', HOME), ('lucide:folder-down', 'Downloads', HOME / 'Downloads'),
                  ('lucide:file-text', 'Documents', HOME / 'Documents'),
                  ('lucide:images', 'Pictures', HOME / 'Pictures'), ('lucide:cloud', 'Drive', HOME / 'Drive')]
        self.places = [tile(i, n, '', open_dir(p)) for i, n, p in places if p.exists()]
        recent = []
        try:
            root = ET.parse(HOME / '.local/share/recently-used.xbel').getroot()
            for b in root.iter('bookmark'):
                href = b.get('href', '')
                if href.startswith('file://'):
                    p = unquote(urlparse(href).path)
                    if os.path.isfile(p):
                        recent.append((b.get('modified', ''), p))
        except (OSError, ET.ParseError):
            pass
        recent.sort(reverse=True)
        self.recent = [tile(kind_icon(p), os.path.basename(p)[:24], os.path.dirname(p).replace(str(HOME), '~'),
                            lambda p=p: spawn('xdg-open', p)) for _, p in recent[:5]]
        shares = []
        try:
            for line in (HOME / '.config/gtk-3.0/bookmarks').read_text().splitlines():
                uri, _, label = line.partition(' ')
                if uri.startswith(('smb://', 'sftp://', 'dav', 'ftp://', 'nfs://')):
                    shares.append(tile('lucide:network', label or uri.split('//')[1][:22], uri.split('://')[0],
                                       lambda u=uri: spawn('nemo', u) if shutil.which('nemo') else spawn('xdg-open', u)))
                elif uri.startswith('file://') and label:
                    shares.append(tile('lucide:folder-heart', label, 'bookmark',
                                       lambda u=uri: spawn('xdg-open', unquote(urlparse(u).path))))
        except OSError:
            pass
        media = Path('/media') / os.environ.get('USER', '')
        for m in (sorted(media.iterdir()) if media.is_dir() else []):
            shares.append(tile('lucide:usb', m.name[:22], 'USB', lambda m=m: spawn('xdg-open', str(m))))
        shares.append(tile('lucide:network', 'Network', 'browse', lambda: spawn('nemo', 'network:///')
                           if shutil.which('nemo') else spawn('xdg-open', 'network:///')))
        self.shares = shares[:5]
        self.ready = True

    def preview(self):
        n = len(getattr(self, 'recent', []))
        return 'FILES', 'Files', [f'{n} recent' if n else 'places and shares']

    def rings(self):
        return [getattr(self, 'places', []), getattr(self, 'recent', []), getattr(self, 'shares', [])]

    def centre(self):
        return 'open Nemo', lambda: spawn('nemo') if shutil.which('nemo') else spawn('xdg-open', str(HOME))


# ---- Notes: the Obsidian vault -----------------------------------------------------------
class Notes(Part):
    key, title = 'notes', 'Notes'

    def vault(self):
        try:
            vs = json.loads((HOME / '.config/obsidian/obsidian.json').read_text()).get('vaults', {})
        except (OSError, ValueError):
            return None
        best = next((v for v in vs.values() if v.get('open')), None) or next(iter(vs.values()), None)
        return Path(best['path']) if best and os.path.isdir(best.get('path', '')) else None

    def fetch(self):
        self.root = self.vault()
        self.notes, self.pinned = [], []
        if self.root:
            for dp, dns, fns in os.walk(self.root):
                dns[:] = [d for d in dns if not d.startswith('.')]
                for f in fns:
                    if f.endswith('.md'):
                        p = os.path.join(dp, f)
                        try:
                            self.notes.append((os.path.getmtime(p), p))
                        except OSError:
                            pass
            self.notes.sort(reverse=True)
            try:
                bm = json.loads((self.root / '.obsidian/bookmarks.json').read_text()).get('items', [])
                self.pinned = [str(self.root / b['path']) for b in bm if b.get('type') == 'file'][:3]
            except (OSError, ValueError, KeyError):
                self.pinned = []
        self.ready = True

    def open_note(self, p):
        return lambda: spawn('xdg-open', 'obsidian://open?path=' + quote(p))

    def note_tile(self, p, sub):
        rel = os.path.relpath(p, self.root)
        return tile('lucide:file-text', os.path.basename(p)[:-3][:24], sub or os.path.dirname(rel), self.open_note(p))

    def preview(self):
        if not getattr(self, 'root', None):
            return 'NOTES', 'Obsidian', ['not set up yet']
        return 'NOTES', str(len(self.notes)), ['notes · click: new']

    def rings(self):
        if not getattr(self, 'root', None):
            return [[tile('lucide:file-pen', 'Set up Obsidian', 'extras/evernote-to-obsidian',
                          lambda: spawn('xdg-open', str(APPS.parent / 'extras/evernote-to-obsidian/README.md')))],
                    [], []]
        now = time.time()
        pins = [self.note_tile(p, 'pinned') for p in self.pinned]
        recent = [self.note_tile(p, ago(now - t)) for t, p in self.notes if p not in self.pinned][:9]
        return [pins + recent[:max(0, 2 - len(pins))], recent[max(0, 2 - len(pins)):][:3],
                recent[max(0, 2 - len(pins)) + 3:][:4]]

    def centre(self):
        if getattr(self, 'root', None):
            return 'new note', lambda: spawn('xdg-open', 'obsidian://new?vault=' + quote(self.root.name))
        return None


# ---- Music: the SoundCloud player comes next ----------------------------------------------
class Music(Part):
    key, title = 'music', 'Music'

    def preview(self):
        return 'MUSIC', 'SoundCloud', ['coming next']

    def rings(self):
        return [[tile('lucide:music', 'SoundCloud', 'the player is the next step', None)], [], []]


PARTS = {p.key: p for p in (Messages(), System(), Files(), Notes(), Music())}
