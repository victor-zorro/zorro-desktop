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


# where a message comes from: web apps all notify as "Firefox", so the site in the text decides
SOURCES = [('Signal', 'signal-desktop', ('signal',), ['signal-desktop']),
           ('WhatsApp', 'zorro-whatsapp', ('whatsapp',), [str(HOME / '.local/bin/whatsapp')]),
           ('Instagram', 'zorro-instagram', ('instagram',), [str(HOME / '.local/bin/instagram')]),
           ('Email', 'lucide:mail', ('mail.google', 'gmail', 'thunderbird', 'mail'),
            [str(HOME / '.local/bin/google-apps')]),
           ('LinkedIn', 'zorro-linkedin', ('linkedin',), [str(HOME / '.local/bin/linkedin')])]


def source_of(m):
    text = ' '.join((m['app'], m['summary'], m['body'])).lower()
    app = m['app'].lower()
    for name, icon, keys, cmd in SOURCES:          # the app's own name first, then the text
        if any(k in app for k in keys):
            return name
    for name, icon, keys, cmd in SOURCES:
        if any(k in text for k in keys if len(k) > 4):
            return name
    return m['app']


class Messages(Part):
    """a tree: All, Signal / WhatsApp / Instagram / Email / LinkedIn (always), other apps, Do not disturb, Clear all; a message unfolds into
    Show again / Go to the app / Copy text / Dismiss"""
    key, title = 'messages', 'Messages'
    tree = True

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
        for m in self.items:
            m['src'] = source_of(m)
        self.dnd = run('dunstctl', 'is-paused').strip() == 'true'
        self.ready = True

    def icon_for(self, app):
        low = app.lower()
        return next((i for k, i in APP_ICON.items() if k in low), 'lucide:bell')

    def go_to(self, app):
        """the app's window to the front, or start it (the web apps' launchers do both)"""
        src = next((s for s in SOURCES if s[0] == app), None)
        if src:
            spawn(*src[3])
        elif subprocess.run(['wmctrl', '-x', '-a', app], capture_output=True).returncode != 0:
            spawn('gtk-launch', app.lower())

    def message_node(self, m):
        text = (m['summary'] + ('\n' + m['body'] if m['body'] else '')).strip()
        src = next((s for s in SOURCES if s[0] == m['src']), None)
        return tile(src[1] if src else self.icon_for(m['app']), (m['summary'] or m['app'])[:24],
                    f'{ago(m["age"])} · {m["body"][:60] or m["app"]}',
                    lambda: spawn('dunstctl', 'history-pop', str(m['id'])), id=f'msg:{m["id"]}',
                    kids=lambda: [
                        tile('lucide:bell', 'Show again', 'with its buttons',
                             lambda: spawn('dunstctl', 'history-pop', str(m['id'])), id=f'pop:{m["id"]}'),
                        tile('lucide:app-window', f'Go to {m["src"]}'[:22], '', lambda: self.go_to(m['src']),
                             id=f'go:{m["id"]}'),
                        tile('lucide:copy', 'Copy text', text[:40],
                             lambda: subprocess.run(['xclip', '-selection', 'clipboard'], input=text, text=True),
                             id=f'copy:{m["id"]}'),
                        tile('lucide:trash-2', 'Dismiss', 'remove it', lambda: run('dunstctl', 'history-rm', str(m['id'])),
                             id=f'rm:{m["id"]}', keep=True, refresh=True, up=2)])

    def roots(self):
        if not getattr(self, 'ready', False):
            return [tile('lucide:ellipsis', 'Loading…', '', None, id='loading')]
        out = [tile('lucide:bell', 'All', f'{len(self.items)} messages', None, id='all',
                    kids=lambda: [self.message_node(m) for m in self.items])]
        for name, icon, keys, cmd in SOURCES:          # always there, in this order
            n = sum(1 for m in self.items if m['src'] == name)
            out.append(tile(icon, name, f'{n} new' if n else 'nothing new', lambda c=cmd: spawn(*c),
                            id=f'src:{name}', lit=bool(n),
                            kids=(lambda name=name: [self.message_node(m) for m in self.items
                                                     if m['src'] == name]) if n else None))
        known = {s[0] for s in SOURCES}
        others = []
        for m in self.items:
            if m['src'] not in known and m['src'] not in others:
                others.append(m['src'])
        for app in others:
            n = sum(1 for m in self.items if m['src'] == app)
            out.append(tile(self.icon_for(app), app[:16], f'{n} message' + ('s' if n != 1 else ''), None,
                            id=f'app:{app}', kids=lambda app=app: [self.message_node(m) for m in self.items
                                                                   if m['src'] == app]))
        out.append(tile('lucide:bell', 'Do not disturb', 'on' if self.dnd else 'off',
                        lambda: run('dunstctl', 'set-paused', 'toggle'), id='dnd', lit=self.dnd,
                        keep=True, refresh=True))
        # Clear all: the centre of the circle (one click there, nothing to miss in the ring)
        return out

    def rings(self):
        return [self.roots(), [], []]

    def preview(self):
        n = len(getattr(self, 'items', []))
        last = self.items[0]['summary'][:28] if n else 'nothing new'
        return 'MESSAGES', str(n), [last + (' · do not disturb' if getattr(self, 'dnd', False) else '')]

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
        k = thinkpad_keys()                  # the airplane switch's own state (see keys.airplane_on)
        self.airplane = k.airplane_on() if k else bool(soft) and all(soft)
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


def folder_tile(path, name=None, icon='lucide:folder', sub=None):
    """a folder that unfolds into its contents (read only when it unfolds) and opens on click"""
    path = Path(path)
    if sub is None:
        try:
            sub = f'{sum(1 for e in os.scandir(path) if not e.name.startswith("."))} items'
        except OSError:
            sub = ''
    return tile(icon, (name or path.name)[:22], sub, lambda: spawn('xdg-open', str(path)),
                id=str(path), kids=lambda: folder_kids(path))


PREVIEW_DIR = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / 'zorro-dial-preview'
IMAGES = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tif', 'tiff', 'svg', 'ico', 'pnm', 'tga'}
CONVERT = {'webp', 'heic', 'heif', 'avif', 'jxl'}
VIDEO = {'mp4', 'mov', 'mkv', 'webm', 'avi', 'mxf', 'm4v', 'mpg', 'mpeg', 'mts', 'braw'}
THUMB = 1280                        # preview pictures are made this wide (the panel scales them)
AUDIO = {'mp3', 'wav', 'flac', 'ogg', 'm4a', 'aac', 'opus', 'aiff'}


def human(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024


def file_preview(path):
    """what the Dialer shows when you rest on a file: {title, meta, image (a file), lines}"""
    p = Path(path)
    try:
        st = p.stat()
    except OSError:
        return {'title': p.name, 'meta': 'gone', 'image': None, 'lines': []}
    ext = p.suffix.lower().lstrip('.')
    out = {'title': p.name, 'meta': f'{human(st.st_size)} · {time.strftime("%-d %b %Y %H:%M", time.localtime(st.st_mtime))}',
           'image': None, 'lines': []}
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    png = PREVIEW_DIR / f'{abs(hash((str(p), st.st_mtime, THUMB)))}.png'

    def probe():
        try:
            return json.loads(run('ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', str(p),
                                  timeout=10) or '{}').get('format', {})
        except ValueError:
            return {}

    def length(fmt):
        d = float(fmt.get('duration') or 0)
        return f'{int(d // 3600)}:{int(d % 3600 // 60):02d}:{int(d % 60):02d}' if d >= 3600 else \
            f'{int(d // 60)}:{int(d % 60):02d}'
    if ext in IMAGES:
        out['image'] = str(p)
    elif ext in CONVERT:
        if png.exists() or subprocess.run(['ffmpeg', '-y', '-v', 'quiet', '-i', str(p), '-frames:v', '1',
                                           '-vf', f'scale={THUMB}:-2', str(png)], timeout=20).returncode == 0:
            out['image'] = str(png)
    elif ext in VIDEO:
        fmt = probe()
        out['meta'] += f' · {length(fmt)}' if fmt.get('duration') else ''
        if png.exists() or subprocess.run(['ffmpegthumbnailer', '-i', str(p), '-o', str(png), '-s', str(THUMB),
                                           '-t', '15%'], capture_output=True, timeout=30).returncode == 0:
            out['image'] = str(png)
    elif ext == 'pdf':
        prefix = png.with_suffix('')
        if not png.exists():
            subprocess.run(['pdftoppm', '-png', '-f', '1', '-l', '1', '-scale-to', str(THUMB), '-singlefile',
                            str(p), str(prefix)], capture_output=True, timeout=30)
        if png.exists():
            out['image'] = str(png)
    elif ext in AUDIO:
        fmt = probe()
        tags = {k.lower(): v for k, v in (fmt.get('tags') or {}).items()}
        out['lines'] = [x for x in (tags.get('title'), tags.get('artist'), tags.get('album')) if x]
        out['meta'] += f' · {length(fmt)}' if fmt.get('duration') else ''
    else:
        try:
            with open(p, 'rb') as fh:
                head = fh.read(12000)
        except OSError:
            head = b''
        if head and b'\0' not in head:
            text = head.decode('utf-8', 'replace').expandtabs(4)
            out['lines'] = [ln.rstrip()[:160] for ln in text.splitlines()[:60]]   # the panel clips
        else:
            out['lines'] = [f'{ext.upper() or "a"} file']
    return out


def folder_kids(path, limit=60):
    """a folder's contents: folders first, then files, newest first; no hidden ones"""
    try:
        entries = [e for e in os.scandir(path) if not e.name.startswith('.')]
    except OSError:
        return []
    dirs = sorted((e for e in entries if e.is_dir(follow_symlinks=True)), key=lambda e: e.name.lower())

    def mtime(e):
        try:
            return e.stat().st_mtime
        except OSError:
            return 0
    files = sorted((e for e in entries if not e.is_dir(follow_symlinks=True)), key=mtime, reverse=True)
    out = [folder_tile(e.path) for e in dirs[:limit]]
    for f in files[:max(0, limit - len(out))]:
        out.append(tile(kind_icon(f.name), f.name[:24], '', lambda p=f.path: spawn('xdg-open', p), id=f.path,
                        preview=lambda p=f.path: file_preview(p)))
    return out


def gvfs_path(uri):
    """a mounted network share as a normal folder (gvfs-fuse), or None when not mounted"""
    u = urlparse(uri)
    base = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'gvfs'
    if u.scheme == 'smb' and base.is_dir():
        parts = [x for x in u.path.split('/') if x]
        if parts:
            p = base / f'smb-share:server={u.hostname},share={parts[0].lower()}'
            for alt in (p, base / f'smb-share:server={u.hostname},share={parts[0]}'):
                if alt.is_dir():
                    return alt.joinpath(*parts[1:])
    return None


class Files(Part):
    """a tree: places in the first ring; rest on a folder and its contents unfold in the next"""
    key, title = 'files', 'Files'
    tree = True

    def fetch(self):
        roots = []
        for icon, name, p in (('lucide:house', 'Home', HOME), ('lucide:folder-down', 'Downloads', HOME / 'Downloads'),
                              ('lucide:file-text', 'Documents', HOME / 'Documents'),
                              ('lucide:images', 'Pictures', HOME / 'Pictures'), ('lucide:cloud', 'Drive', HOME / 'Drive')):
            if p.exists():
                roots.append(folder_tile(p, name, icon))
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
                            lambda p=p: spawn('xdg-open', p), id=p, preview=lambda p=p: file_preview(p))
                       for _, p in recent[:12]]
        roots.append(tile('lucide:rotate-ccw', 'Recent', f'{len(self.recent)} files', None, id='recent',
                          kids=lambda: self.recent))
        nemo = shutil.which('nemo')
        try:
            for line in (HOME / '.config/gtk-3.0/bookmarks').read_text().splitlines():
                uri, _, label = line.partition(' ')
                if uri.startswith(('smb://', 'sftp://', 'dav', 'ftp://', 'nfs://')):
                    local = gvfs_path(uri)
                    t_ = tile('lucide:hard-drive', (label or urlparse(uri).hostname or uri)[:22],
                              'share' if local else 'share · click to connect',
                              lambda u=uri: spawn('nemo', u) if nemo else spawn('xdg-open', u), id=uri)
                    if local:
                        t_['kids'] = lambda p=local: folder_kids(p)
                    roots.append(t_)
                elif uri.startswith('file://') and label:
                    roots.append(folder_tile(unquote(urlparse(uri).path), label, 'lucide:folder-heart'))
        except OSError:
            pass
        media = Path('/media') / os.environ.get('USER', '')
        for m in (sorted(media.iterdir()) if media.is_dir() else []):
            roots.append(folder_tile(m, m.name, 'lucide:usb'))
        roots.append(tile('lucide:network', 'Network', 'browse', lambda: spawn('nemo', 'network:///')
                          if nemo else spawn('xdg-open', 'network:///'), id='network'))
        self.roots_ = roots
        self.ready = True

    def roots(self):
        return getattr(self, 'roots_', [])

    def rings(self):                     # not used for a tree; kept for the Part interface
        return [self.roots(), [], []]

    def preview(self):
        return 'FILES', 'Files', ['rest on a folder: it opens']

    def centre(self):
        return 'open Nemo', lambda: spawn('nemo') if shutil.which('nemo') else spawn('xdg-open', str(HOME))


# ---- Notes: the Obsidian vault, as a tree ---------------------------------------------------
TAG = re.compile(r'(?:^|\s)#([A-Za-z][\w/-]{1,40})')
HEADING = re.compile(r'^(#{1,3})\s+(.+?)\s*#*\s*$', re.M)


class Notes(Part):
    """a tree: new note, pinned, recent, your folders (notebooks), tags; a note unfolds into
    its headings. Typing searches every note, title and text."""
    key, title = 'notes', 'Notes'
    tree = True

    def vaults(self):
        """every vault Obsidian knows except those unticked in the app (Accounts → Obsidian);
        the one open in Obsidian first"""
        try:
            vs = list(json.loads((HOME / '.config/obsidian/obsidian.json').read_text()).get('vaults', {}).values())
        except (OSError, ValueError):
            vs = []
        vs.sort(key=lambda v: (not v.get('open'), os.path.basename(v.get('path', '')).lower()))
        try:
            hide = json.loads((HOME / '.config/zorro-dial/config.json').read_text()).get('notes_hide_vaults', [])
        except (OSError, ValueError):
            hide = []
        return [Path(v['path']) for v in vs if os.path.isdir(v.get('path', '')) and v['path'] not in hide]

    def fetch(self):
        self.all = self.vaults()
        self.root = self.all[0] if self.all else None      # new notes go here (the open vault)
        self.notes = []                 # (mtime, path), every chosen vault
        self.text = {}                  # path -> text, for search and tags (read once per opening)
        self.pinned = []
        for root in self.all:
            for dp, dns, fns in os.walk(root):
                dns[:] = [d for d in dns if not d.startswith(('.', '_'))]
                for f in fns:
                    if f.endswith('.md'):
                        p = os.path.join(dp, f)
                        try:
                            self.notes.append((os.path.getmtime(p), p))
                        except OSError:
                            pass
            try:
                bm = json.loads((root / '.obsidian/bookmarks.json').read_text()).get('items', [])
                self.pinned += [str(root / b['path']) for b in bm
                                if b.get('type') == 'file' and (root / b['path']).exists()]
            except (OSError, ValueError, KeyError):
                pass
        self.notes.sort(reverse=True)
        for _, p in self.notes[:5000]:
            try:
                with open(p, encoding='utf-8', errors='replace') as fh:
                    self.text[p] = fh.read(200000)
            except OSError:
                pass
        self.ready = True

    def vault_of(self, p):
        return next((v for v in self.all if p.startswith(str(v) + os.sep)), self.root)

    def new_note(self, vault):
        return lambda: spawn('xdg-open', 'obsidian://new?vault=' + quote(vault.name))

    def uri(self, p, heading=None):
        u = 'obsidian://open?path=' + quote(p)
        return u + ('%23' + quote(heading) if heading else '')

    def note_tile(self, p, sub=None):
        v = self.vault_of(p)
        rel = os.path.relpath(p, v)
        where = os.path.dirname(rel) or (v.name if len(self.all) > 1 else 'vault')
        heads = [(len(h), txt.strip()) for h, txt in HEADING.findall(self.text.get(p, ''))][:24]
        t_ = tile('lucide:file-text', os.path.basename(p)[:-3][:26],
                  sub if sub is not None else where,
                  lambda: spawn('xdg-open', self.uri(p)), id=p)
        if heads:
            t_['kids'] = lambda: [tile('lucide:list', ('  ' * (lv - 1) + h)[:26], f'heading {lv}',
                                       lambda h=h: spawn('xdg-open', self.uri(p, h)), id=f'{p}#{h}')
                                  for lv, h in heads]
        return t_

    def folder_node(self, d, name=None):
        notes = [(m, p) for m, p in self.notes if os.path.dirname(p) == str(d)]
        subs = sorted(x for x in d.iterdir() if x.is_dir() and not x.name.startswith(('.', '_'))) \
            if d.is_dir() else []
        count = sum(1 for _, p in self.notes if p.startswith(str(d) + os.sep))
        return tile('lucide:folder', (name or d.name)[:22], f'{count} notes', None, id=f'dir:{d}',
                    kids=lambda: [self.folder_node(x) for x in subs]
                    + [self.note_tile(p, ago(time.time() - m)) for m, p in notes])

    def tags(self):
        count = {}
        for p, txt in self.text.items():
            fm = re.match(r'^---\n(.*?)\n---', txt, re.S)
            found = set(TAG.findall(txt))
            if fm:                      # frontmatter: tags: [a, b] or a list under tags:
                block = re.search(r'^tags:\s*(.*(?:\n\s*-\s*.*)*)', fm.group(1), re.M)
                if block:
                    found |= {x.strip(' -[]"\'') for x in re.split(r'[,\n]', block.group(1)) if x.strip(' -[]"\'')}
            for tg in found:
                count.setdefault(tg.lower(), []).append(p)
        return sorted(count.items(), key=lambda kv: -len(kv[1]))

    def roots(self):
        if not getattr(self, 'ready', False):
            return [tile('lucide:ellipsis', 'Loading…', '', None, id='loading')]
        if not self.root:
            return [tile('lucide:file-pen', 'Open Obsidian', 'make a vault, e.g. ~/Notes',
                         lambda: spawn('obsidian'), id='open'),
                    tile('lucide:file-text', 'Evernote move', 'in the Zorro app',
                         lambda: spawn('zorro-settings', '--page', 'ob'), id='steps')]
        now = time.time()
        many = len(self.all) > 1
        if many:
            out = [tile('lucide:file-plus', 'New note', 'pick a vault', None, id='new',
                        kids=lambda: [tile('lucide:file-plus', v.name[:22], 'new note here',
                                           self.new_note(v), id=f'new:{v}') for v in self.all])]
        else:
            out = [tile('lucide:file-plus', 'New note', self.root.name, self.new_note(self.root), id='new')]
        if self.pinned:
            out.append(tile('lucide:star', 'Pinned', f'{len(self.pinned)} notes', None, id='pinned',
                            kids=lambda: [self.note_tile(p, 'pinned') for p in self.pinned]))
        out.append(tile('lucide:rotate-ccw', 'Recent', f'{len(self.notes)} notes', None, id='recent',
                        kids=lambda: [self.note_tile(p, ago(now - m)) for m, p in self.notes[:24]]))
        if many:                        # a vault each; it unfolds into its folders and notes
            for v in self.all:
                node = self.folder_node(v)
                node['icon'], node['id'] = 'lucide:library', f'vault:{v}'
                out.append(node)
        else:
            folders = sorted(x for x in self.root.iterdir() if x.is_dir() and not x.name.startswith(('.', '_')))
            out += [self.folder_node(d) for d in folders]
        tags = self.tags()
        if tags:
            out.append(tile('lucide:list', 'Tags', f'{len(tags)} tags', None, id='tags',
                            kids=lambda: [tile('lucide:list', f'#{tg}'[:22], f'{len(ps)} notes', None,
                                               id=f'tag:{tg}',
                                               kids=lambda ps=ps: [self.note_tile(p) for p in
                                                                   sorted(ps, key=lambda p: -os.path.getmtime(p))])
                                          for tg, ps in tags[:40]]))
        return out

    def rings(self):
        return [self.roots(), [], []]

    def search_tiles(self, text):
        """notes whose title or text has every word, titles first, newest first"""
        words = [w.lower() for w in text.split() if w]
        if not words or not getattr(self, 'root', None):
            return []
        hits = []
        for m, p in self.notes:
            name = os.path.basename(p).lower()
            body = self.text.get(p, '').lower()
            if all(w in name or w in body for w in words):
                hits.append((not all(w in name for w in words), -m, p))
        hits.sort()
        return [self.note_tile(p) for _, _, p in hits[:30]]

    def search(self, text):
        found = self.search_tiles(text)
        if found and found[0].get('act'):
            found[0]['act']()

    def preview(self):
        if not getattr(self, 'root', None):
            return 'NOTES', 'Obsidian', ['no vault yet']
        vs = f' in {len(self.all)} vaults' if len(self.all) > 1 else ''
        return 'NOTES', str(len(self.notes)), [f'notes{vs} · centre: new note']

    def centre(self):
        if getattr(self, 'root', None):
            return 'new note', self.new_note(self.root)
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


def scapi():
    """the SoundCloud API helper next to zorro-music (None when it is missing)"""
    sys.path.insert(0, str(APPS / 'zorro-music'))
    try:
        import scapi as m
        return m
    except ImportError:
        return None


class Music(Part):
    """a tree: your likes, your styles, discover, playlists; tracks unfold into Play / Play
    next / Like. The player's controls sit in the centre of the circle."""
    key, title = 'music', 'Music'
    tree = True

    def fetch(self):
        self.fetch_np()
        self.sc = scapi()
        self.likes, self.lists, self.signed_in = [], [], False
        if self.sc:
            try:
                self.likes = self.sc.likes()
                self.signed_in = bool(self.likes) or bool(self.sc.token())
            except Exception as e:      # noqa: BLE001 - offline or SoundCloud changed: public only
                print(f'zorro-dial: soundcloud: {e}', file=sys.stderr)
        self.liked = {t['id'] for t in self.likes}
        self.ready = True

    # -- the player
    def control(self, what):
        np = self.np or {}
        if np.get('player'):
            mpris_call(np['player'], {'toggle': 'PlayPause', 'play': 'Play', 'pause': 'Pause', 'stop': 'Stop',
                                      'next': 'Next', 'prev': 'Previous'}[what])
        else:
            run(str(MUSIC), what)
        time.sleep(0.4)
        self.fetch_np()

    def fetch_np(self):
        players = mpris_players()
        self.np = None
        for name, props in sorted(players, key=lambda p: (p[1].get('PlaybackStatus') != 'Playing', 'mpv' not in p[0])):
            md = props.get('Metadata') or {}
            if not md.get('xesam:title') and props.get('PlaybackStatus') == 'Stopped':
                continue
            artist = md.get('xesam:artist') or ['']
            self.np = {'player': name, 'title': md.get('xesam:title') or 'Playing',
                       'artist': artist[0] if artist else '', 'playing': props.get('PlaybackStatus') == 'Playing',
                       'pos': (props.get('Position') or 0) / 1e6, 'dur': (md.get('mpris:length') or 0) / 1e6,
                       'app': name.split('.')[3].split('_')[0]}
            break
        self.fetched = time.time()

    def position(self):
        np = self.np or {}
        pos = np.get('pos', 0) + ((time.time() - self.fetched) if np.get('playing') else 0)
        return min(pos, np.get('dur') or pos)

    # -- what to play
    def queue(self, tracks, shuffle=False):
        import random
        urls = [t['url'] for t in tracks if t.get('url')]
        if shuffle:
            random.shuffle(urls)
        if urls:
            spawn(str(MUSIC), 'queue', *urls[:200])

    def track_node(self, t):
        liked = t['id'] in self.liked
        return tile('lucide:music', t['title'][:24], t['artist'][:24],
                    lambda: spawn(str(MUSIC), 'play', t['url']), id=f'track:{t["id"]}',
                    kids=lambda: [tile('lucide:play', 'Play', 'now', lambda: spawn(str(MUSIC), 'play', t['url']),
                                       id=f'play:{t["id"]}'),
                                  tile('lucide:skip-forward', 'Play next', 'after this one',
                                       lambda: spawn(str(MUSIC), 'next-up', t['url']), id=f'next:{t["id"]}'),
                                  tile('lucide:star', 'Unlike' if liked else 'Like', 'on SoundCloud',
                                       lambda: self.like(t, not liked), id=f'like:{t["id"]}', keep=True,
                                       lit=liked)])

    def like(self, t, on):
        if self.sc and self.sc.like(t['id'], on):
            (self.liked.add if on else self.liked.discard)(t['id'])

    def tracks_node(self, icon, name, sub, get, id_):
        return tile(icon, name, sub, None, id=id_, kids=lambda: [self.track_node(x) for x in get()])

    def style_kids(self, style):
        mine = [t for t in self.likes if t['style'] == style]
        artists = {}
        for t in mine:
            artists.setdefault(t['artist'], []).append(t)
        top = sorted(artists.items(), key=lambda kv: -len(kv[1]))[:8]
        out = [tile('lucide:play', f'Play my {style}', f'{len(mine)} likes, shuffled',
                    lambda: self.queue(mine, shuffle=True), id=f'playstyle:{style}'),
               self.tracks_node('lucide:globe', 'Discover', f'new {style}',
                                lambda: self.sc.search('', style=style), f'disc:{style}')]
        if mine and self.sc:
            seed = mine[0]
            out.append(self.tracks_node('lucide:radio-tower', 'More like these', f'like {seed["title"][:16]}',
                                        lambda: self.sc.related(seed['id']), f'rel:{style}'))
        if top:
            out.append(tile('lucide:star', 'Top artists', f'{len(top)} artists', None, id=f'artists:{style}',
                            kids=lambda: [self.tracks_node('lucide:music', a[:20], f'{len(ts)} likes',
                                                           lambda ts=ts: ts, f'artist:{style}:{a}') for a, ts in top]))
        return out + [self.track_node(t) for t in mine[:12]]

    def roots(self):
        if not getattr(self, 'ready', False):
            return [tile('lucide:ellipsis', 'Loading…', '', None, id='loading')]
        out = []
        if self.likes:
            out.append(tile('lucide:star', 'My likes', f'{len(self.likes)} tracks', None, id='likes',
                            kids=lambda: [tile('lucide:play', 'Play all', 'shuffled',
                                               lambda: self.queue(self.likes, shuffle=True), id='likes:shuffle'),
                                          tile('lucide:list', 'Newest first', '',
                                               lambda: self.queue(self.likes), id='likes:newest')]
                            + [self.track_node(t) for t in self.likes[:14]]))
            for style, n in (self.sc.styles(self.likes, 5) if self.sc else []):
                out.append(tile('lucide:music', style.title()[:16], f'{n} likes', None, id=f'style:{style}',
                                kids=lambda s=style: self.style_kids(s)))
        if self.sc:
            pub = [s for s, _ in self.sc.styles(self.likes, 5)] if self.likes else self.sc.PUBLIC_STYLES
            out.append(tile('lucide:globe', 'Discover', 'new in your styles' if self.likes else 'free tracks',
                            None, id='discover',
                            kids=lambda: [self.tracks_node('lucide:globe', s.title()[:16], 'new tracks',
                                                           lambda s=s: self.sc.search('', style=s),
                                                           f'disc:{s}') for s in pub]))
        if self.signed_in and self.sc:
            out.append(tile('lucide:list', 'Playlists', 'yours', None, id='playlists',
                            kids=lambda: [tile('lucide:list', p['title'][:20], f'{p["count"]} tracks',
                                               lambda u=p['url']: spawn(str(MUSIC), 'play', u),
                                               id=f'pl:{p["url"]}') for p in self.sc.playlists()]))
        out.append(tile('lucide:clipboard-paste', 'Play a link', 'from the clipboard', self.play_clipboard,
                        id='paste'))
        return out

    def rings(self):
        return [self.roots(), [], []]

    def play_clipboard(self):
        url = run('xclip', '-o', '-selection', 'clipboard').strip()
        if url.startswith('http'):
            spawn(str(MUSIC), 'play', url)

    def search(self, text):
        spawn(str(MUSIC), 'play', 'search', text)

    def preview(self):
        np = getattr(self, 'np', None)
        if not np:
            return 'MUSIC', 'SoundCloud', ['nothing playing' if self.ready else '…']
        t = int(self.position())
        d = int(np.get('dur') or 0)
        when = f'{t // 60}:{t % 60:02d}' + (f' / {d // 60}:{d % 60:02d}' if d else '')
        return 'NOW PLAYING' if np['playing'] else 'PAUSED', np['title'][:22], [np['artist'][:26], when]

    def draw_rim(self, dial, cr, cx, cy, rings, a0, a1):
        """the playing track as a thin band of particles just outside the fan; played: white"""
        import math
        import random
        np = getattr(self, 'np', None)
        if not np:
            return
        r = rings[-1][1] + 14
        frac = (self.position() / np['dur']) if np.get('dur') else 0
        rnd = random.Random(hash(np['title']))
        n = 170
        for j in range(n):
            a = math.radians(a0 + (a1 - a0) * j / n)
            amp = 0.3 + 0.7 * abs(math.sin(j * 0.23 + rnd.random()) * math.cos(j * 0.051))
            played = j / n <= frac
            for _ in range(int(2 + amp * 4)):
                rr = r + rnd.uniform(-1, 1) * amp * 7
                cr.set_source_rgba(*((0.97, 0.97, 0.97) if played else (0.62, 0.62, 0.64)),
                                   (0.9 if played else 0.28) * rnd.uniform(0.5, 1))
                cr.rectangle(cx + math.cos(a) * rr, cy + math.sin(a) * rr, 1.5, 1.5)
                cr.fill()


PARTS = {p.key: p for p in (Messages(), System(), Files(), Notes(), Music())}
