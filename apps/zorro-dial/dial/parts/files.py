"""Files: places, recent files, shares"""
import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse

from .base import HOME, Part, spawn, tile
from .filepreview import file_preview


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


PLACES = (('lucide:house', 'Home', ''), ('lucide:folder-down', 'Downloads', 'Downloads'),
          ('lucide:file-text', 'Documents', 'Documents'), ('lucide:images', 'Pictures', 'Pictures'),
          ('lucide:cloud', 'Drive', 'Drive'))
SHARES = ('smb://', 'sftp://', 'dav', 'ftp://', 'nfs://')


def recent_tile():
    """the files opened last (the desktop's own list), newest first"""
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
    tiles = [tile(kind_icon(p), os.path.basename(p)[:24], os.path.dirname(p).replace(str(HOME), '~'),
                  lambda p=p: spawn('xdg-open', p), id=p, preview=lambda p=p: file_preview(p))
             for _, p in recent[:12]]
    return tile('lucide:rotate-ccw', 'Recent', f'{len(tiles)} files', None, id='recent',
                kids=lambda: tiles)


def open_place(uri):
    spawn('nemo', uri) if shutil.which('nemo') else spawn('xdg-open', uri)


def bookmark_tiles():
    """the file manager's bookmarks: shares (unfolding when mounted) and folders with a name"""
    out = []
    try:
        lines = (HOME / '.config/gtk-3.0/bookmarks').read_text().splitlines()
    except OSError:
        return out
    for line in lines:
        uri, _, label = line.partition(' ')
        if uri.startswith(SHARES):
            local = gvfs_path(uri)
            t_ = tile('lucide:hard-drive', (label or urlparse(uri).hostname or uri)[:22],
                      'share' if local else 'share · click to connect',
                      lambda u=uri: open_place(u), id=uri)
            if local:
                t_['kids'] = lambda p=local: folder_kids(p)
            out.append(t_)
        elif uri.startswith('file://') and label:
            out.append(folder_tile(unquote(urlparse(uri).path), label, 'lucide:folder-heart'))
    return out


class Files(Part):
    """a tree: places in the first ring; rest on a folder and its contents unfold in the next"""
    key, title = 'files', 'Files'

    def fetch(self):
        roots = [folder_tile(HOME / sub, name, icon) for icon, name, sub in PLACES if (HOME / sub).exists()]
        roots.append(recent_tile())
        roots += bookmark_tiles()
        media = Path('/media') / os.environ.get('USER', '')
        for m in (sorted(media.iterdir()) if media.is_dir() else []):
            roots.append(folder_tile(m, m.name, 'lucide:usb'))
        roots.append(tile('lucide:network', 'Network', 'browse', lambda: open_place('network:///'),
                          id='network'))
        self.places = roots
        self.ready = True

    def roots(self):
        return getattr(self, 'places', [])

    def preview(self):
        return 'FILES', 'Files', ['rest on a folder: it opens']

    def centre(self):
        return 'open Nemo', lambda: spawn('nemo') if shutil.which('nemo') else spawn('xdg-open', str(HOME))
