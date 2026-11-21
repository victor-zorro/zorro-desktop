"""The installed apps, from their .desktop files."""
import configparser
import hashlib
import json
import os
from pathlib import Path

HOME = Path.home()
APPS_CACHE = Path(os.environ.get('XDG_CACHE_HOME', HOME / '.cache')) / 'zorro-dial' / 'apps.json'


def app_dirs():
    return [HOME / '.local/share/applications'] + [
        Path(d) / 'applications' for d in
        os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':')]


def apps():
    """installed apps: [{id, name, icon, cats, path}] from the .desktop files. Parsing them
    takes ~60 ms on every Super press; the result is kept until a .desktop file changes
    (only their names and times are looked at, ~1 ms)."""
    dirs = app_dirs()
    files = []
    for d in dirs:
        try:
            files += [(str(f), f.stat().st_mtime_ns) for f in sorted(d.glob('*.desktop'))]
        except OSError:
            continue
    key = hashlib.sha1(json.dumps(files).encode()).hexdigest()
    try:
        cached = json.loads(APPS_CACHE.read_text())
        if cached.get('key') == key:
            return cached['apps']
    except (OSError, ValueError, AttributeError, KeyError):
        pass
    out = read_apps(dirs)
    try:
        APPS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = APPS_CACHE.with_suffix('.tmp')
        tmp.write_text(json.dumps({'key': key, 'apps': out}))
        os.replace(tmp, APPS_CACHE)
    except OSError:
        pass
    return out


def read_app(f):
    """one .desktop file as an app, or None when it is not one to show"""
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        cp.read(f, encoding='utf-8')
        e = cp['Desktop Entry']
    except (configparser.Error, KeyError, UnicodeDecodeError):
        return None
    if e.get('Type') != 'Application' or e.get('NoDisplay', 'false') == 'true' \
            or e.get('Hidden', 'false') == 'true' or not e.get('Exec'):
        return None
    return {'id': f.name, 'name': e.get('Name', f.stem), 'icon': e.get('Icon', ''),
            'cats': [c for c in e.get('Categories', '').split(';') if c],
            'path': str(f), 'keywords': e.get('Keywords', '')}


def read_apps(dirs):
    seen, out = set(), []
    for d in dirs:
        for f in sorted(d.glob('*.desktop')) if d.is_dir() else []:
            if f.name in seen:
                continue
            seen.add(f.name)
            app = read_app(f)
            if app:
                out.append(app)
    return out
