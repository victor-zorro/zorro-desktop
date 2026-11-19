"""Files: places, recent files, shares"""
# flake8: noqa: F403,F405 - helpers come from base (and earlier parts)
from .base import *
from .messages import *
from .system import *


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


def prune_previews(keep=50):
    """the cache lives in RAM ($XDG_RUNTIME_DIR): only the last `keep` pictures stay"""
    try:
        old = sorted(PREVIEW_DIR.glob('*.png'), key=lambda f: f.stat().st_mtime)
    except OSError:
        return
    for f in old[:max(0, len(old) - keep + 1)]:
        try:
            f.unlink()
        except OSError:
            pass


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
    # a stable name (Python's hash() changes per run), so the next Dialer finds it again
    png = PREVIEW_DIR / (hashlib.sha1(f'{p}|{st.st_mtime}|{THUMB}'.encode()).hexdigest() + '.png')
    if not png.exists():
        prune_previews()

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
