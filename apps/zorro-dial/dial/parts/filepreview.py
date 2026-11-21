"""What the Dialer shows when you rest on a file: a picture or its first lines."""
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from .base import run

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


def probe(p):
    try:
        return json.loads(run('ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', str(p),
                              timeout=10) or '{}').get('format', {})
    except (ValueError, AttributeError):
        return {}


def length(fmt):
    d = float(fmt.get('duration') or 0)
    return f'{int(d // 3600)}:{int(d % 3600 // 60):02d}:{int(d % 60):02d}' if d >= 3600 else \
        f'{int(d // 60)}:{int(d % 60):02d}'


def made(png, cmd, timeout):
    """the picture file, made by cmd unless it is there already; None when that failed"""
    if png.exists():
        return str(png)
    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return str(png) if png.exists() else None


def picture(p, ext, png):
    """a picture of the file (itself, or one made of it), or None"""
    if ext in IMAGES:
        return str(p)
    if ext in CONVERT:
        return made(png, ['ffmpeg', '-y', '-v', 'quiet', '-i', str(p), '-frames:v', '1',
                          '-vf', f'scale={THUMB}:-2', str(png)], 20)
    if ext in VIDEO:
        return made(png, ['ffmpegthumbnailer', '-i', str(p), '-o', str(png), '-s', str(THUMB),
                          '-t', '15%'], 30)
    if ext == 'pdf':
        return made(png, ['pdftoppm', '-png', '-f', '1', '-l', '1', '-scale-to', str(THUMB), '-singlefile',
                          str(p), str(png.with_suffix(''))], 30)
    return None


def first_lines(p, ext):
    try:
        with open(p, 'rb') as fh:
            head = fh.read(12000)
    except OSError:
        head = b''
    if head and b'\0' not in head:
        text = head.decode('utf-8', 'replace').expandtabs(4)
        return [ln.rstrip()[:160] for ln in text.splitlines()[:60]]   # the panel clips
    return [f'{ext.upper() or "a"} file']


def file_preview(path):
    """{title, meta, image (a file), lines} of a file"""
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
    if ext in VIDEO or ext in AUDIO:
        fmt = probe(p)
        out['meta'] += f' · {length(fmt)}' if fmt.get('duration') else ''
        if ext in AUDIO:
            tags = {k.lower(): v for k, v in (fmt.get('tags') or {}).items()}
            out['lines'] = [x for x in (tags.get('title'), tags.get('artist'), tags.get('album')) if x]
            return out
    out['image'] = picture(p, ext, png)
    if not out['image'] and ext not in IMAGES | CONVERT | VIDEO | {'pdf'}:
        out['lines'] = first_lines(p, ext)
    return out
