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


# ---- Music: whichever player plays (MPRIS), and zorro-music for SoundCloud -------------------
MUSIC = APPS / 'zorro-music' / 'zorro-music'


def mpris_players():
    """[(bus name, props)] of the media players on the session bus"""
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        names = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                              'ListNames', None, None, 0, 1000, None).unpack()[0]
    except Exception:                   # noqa: BLE001 - no bus: no players
        return []
    out = []
    for n in names:
        if not n.startswith('org.mpris.MediaPlayer2.'):
            continue
        try:
            props = bus.call_sync(n, '/org/mpris/MediaPlayer2', 'org.freedesktop.DBus.Properties', 'GetAll',
                                  GLib.Variant('(s)', ('org.mpris.MediaPlayer2.Player',)),
                                  None, 0, 500, None).unpack()[0]
            out.append((n, props))
        except Exception:               # noqa: BLE001 - a player that does not answer
            continue
    return out


def mpris_call(name, method):
    try:
        from gi.repository import Gio
        Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
            name, '/org/mpris/MediaPlayer2', 'org.mpris.MediaPlayer2.Player', method, None, None, 0, 2000, None)
    except Exception:                   # noqa: BLE001
        pass


class Music(Part):
    key, title = 'music', 'Music'

    def fetch(self):
        self.np = None                  # now playing: {player, title, artist, playing, pos, dur}
        players = mpris_players()
        rank = sorted(players, key=lambda p: (p[1].get('PlaybackStatus') != 'Playing',
                                              'mpv' not in p[0], 'firefox' in p[0]))
        for name, props in rank:
            md = props.get('Metadata') or {}
            title = md.get('xesam:title') or ''
            if not title and props.get('PlaybackStatus') == 'Stopped':
                continue
            artist = md.get('xesam:artist') or ['']
            self.np = {'player': name, 'title': title or 'Playing', 'artist': artist[0] if artist else '',
                       'playing': props.get('PlaybackStatus') == 'Playing',
                       'pos': (props.get('Position') or 0) / 1e6, 'dur': (md.get('mpris:length') or 0) / 1e6,
                       'app': name.split('.')[3].split('_')[0]}
            break
        if self.np is None and os.path.exists(MUSIC):          # mpv without mpv-mpris
            try:
                st = json.loads(run(str(MUSIC), 'status') or '{}')
            except ValueError:
                st = {}
            if st.get('running') and not st.get('idle'):
                self.np = {'player': None, 'title': st.get('title') or 'Playing', 'artist': st.get('artist', ''),
                           'playing': st.get('playing'), 'pos': st.get('position') or 0,
                           'dur': st.get('duration') or 0, 'app': 'zorro-music'}
        try:
            self.conf = json.loads((HOME / '.config/zorro-music/config.json').read_text())
        except (OSError, ValueError):
            self.conf = {}
        self.fetched = time.time()
        self.ready = True

    def control(self, what):
        np = self.np or {}
        if np.get('player'):
            mpris_call(np['player'], {'toggle': 'PlayPause', 'play': 'Play', 'pause': 'Pause', 'stop': 'Stop',
                                      'next': 'Next', 'prev': 'Previous'}[what])
        else:
            run(str(MUSIC), what)
        time.sleep(0.4)
        self.fetch()

    def play(self, *args):
        spawn(str(MUSIC), 'play', *args)

    def position(self):
        """seconds, moving on between fetches while playing"""
        np = self.np or {}
        pos = np.get('pos', 0) + ((time.time() - self.fetched) if np.get('playing') else 0)
        return min(pos, np.get('dur') or pos)

    def preview(self):
        np = getattr(self, 'np', None)
        if not np:
            return 'MUSIC', 'SoundCloud', ['nothing playing']
        t = int(self.position())
        d = int(np.get('dur') or 0)
        when = f'{t // 60}:{t % 60:02d}' + (f' / {d // 60}:{d % 60:02d}' if d else '')
        return 'NOW PLAYING' if np['playing'] else 'PAUSED', np['title'][:22], [np['artist'][:26], when]

    def rings(self):
        np = getattr(self, 'np', None)
        playing = bool(np and np['playing'])
        ctl = [tile('lucide:skip-back', 'Previous', '', lambda: self.control('prev'), keep=True),
               tile('lucide:play', 'Play', np['app'] if np else '', lambda: self.control('play'),
                    lit=playing, keep=True),
               tile('lucide:pause', 'Pause', '', lambda: self.control('pause'),
                    lit=bool(np) and not playing, keep=True),
               tile('lucide:square', 'Stop', '', lambda: self.control('stop'), keep=True),
               tile('lucide:skip-forward', 'Next', '', lambda: self.control('next'), keep=True)]
        src = []
        conf = getattr(self, 'conf', {})
        if conf.get('user'):
            src.append(tile('lucide:star', 'My likes', conf['user'], lambda: self.play('likes'), keep=True))
        for f in conf.get('favourites', [])[:4]:
            src.append(tile('lucide:music', f.get('name', '?')[:18], 'favourite',
                            lambda u=f.get('url'): self.play(u), keep=True))
        src.append(tile('lucide:clipboard-paste', 'Play a link', 'from the clipboard', self.play_clipboard, keep=True))
        return [[], ctl, src]

    def play_clipboard(self):
        url = run('xclip', '-o', '-selection', 'clipboard').strip()
        if url.startswith('http'):
            self.play(url)

    def search(self, text):
        self.play('search', text)

    def draw(self, dial, cr, cx, cy, rings, a0, a1):
        """the inner ring: the track as a band of particles; the played part lights up"""
        import math
        import random
        np = getattr(self, 'np', None)
        r0, r1 = rings[0]
        mid, half = (r0 + r1) / 2, (r1 - r0) * 0.42
        frac = (self.position() / np['dur']) if np and np.get('dur') else 0
        rnd = random.Random(hash(np['title']) if np else 7)
        n = 140
        t = time.time()
        for j in range(n):
            a = a0 + 3 + (a1 - a0 - 6) * j / n
            amp = 0.25 + 0.75 * abs(math.sin(j * 0.23 + rnd.random()) * math.cos(j * 0.051 + rnd.random()))
            if np and np.get('playing') and j / n <= frac:
                amp *= 0.85 + 0.15 * math.sin(t * 3 + j)        # breathes while playing
            played = j / n <= frac
            for _ in range(int(3 + amp * 8)):
                rr = mid + rnd.uniform(-1, 1) * amp * half
                x = cx + math.cos(math.radians(a)) * rr
                y = cy + math.sin(math.radians(a)) * rr
                cr.set_source_rgba(*((0.1, 0.9, 1.0) if played else (0.85, 0.85, 0.9)),
                                   (0.85 if played else 0.3) * rnd.uniform(0.5, 1))
                cr.rectangle(x, y, 1.6, 1.6)
                cr.fill()


PARTS = {p.key: p for p in (Messages(), System(), Files(), Notes(), Music())}
