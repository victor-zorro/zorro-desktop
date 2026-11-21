"""The devices that test, and whether a test is stale (made before the app last changed)."""
import re
import socket
import subprocess
import time

from . import paths, store

# App name -> its folders in the repo. The order is the order of the submenu.
APP_FOLDERS = {
    'Dialer': ['apps/zorro-dial'],
    'Desktop': ['apps/zorro-shot', 'apps/zorro-icons', 'apps/zorro-wall', 'apps/zorro-orb',
                'apps/zorro-winpos', 'apps/zorro-fx'],
    'System': ['apps/zorro-thinkpad'],
    'Connect': ['apps/zorro-thinkpad', 'extras'],
    'DEVS': ['apps/zorro-devs'],
    'Intelligence': ['apps/zorro-search', 'apps/zorro-intel', 'apps/zorro-ai'],
    'Login': ['apps/zorro-dm', 'apps/zorro-face'],
    'Music': ['apps/zorro-music'],
    'Drive': ['apps/zorro-drive'],
    'Transfer': ['apps/zorro-transfer'],
    'Sweep': ['apps/zorro-sweep'],
}
KEEP = 60           # seconds a git answer about the repo is kept
CACHE = {}
ANCESTORS = {}


def this_device():
    name = re.sub(r'[^A-Za-z0-9._-]', '-', socket.gethostname()).strip('-.')[:64]
    return name if store.DEVICE.fullmatch(name) else 'this-device'


def devices():
    """All known devices; this one adds itself the first time."""
    file = paths.data_dir() / 'devices.json'
    with store.LOCK:
        known = paths.read_json(file, {})
        if not isinstance(known, dict):
            known = {}
        if this_device() not in known:
            known[this_device()] = {'added': paths.now()}
            paths.write_json(file, known)
    return known


def add(name):
    if not isinstance(name, str) or not store.DEVICE.fullmatch(name):
        raise store.Invalid('device: not a device name')
    with store.LOCK:
        known = devices()
        if name not in known:
            known[name] = {'added': paths.now()}
            paths.write_json(paths.data_dir() / 'devices.json', known)
    return known


def repo_git(*args):
    try:
        done = subprocess.run(['git', *args], cwd=paths.repo(), capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done


def cached(key, find):
    hit = CACHE.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    value = find()
    CACHE[key] = (time.monotonic() + KEEP, value)
    return value


def head():
    """The repo's current commit: the version a test made now belongs to."""
    def find():
        done = repo_git('rev-parse', '--short', 'HEAD')
        return done.stdout.strip() if done and done.returncode == 0 else ''
    return cached('head', find)


def last_change(app):
    """The last commit that touched the app's folders, '' when unknown."""
    folders = APP_FOLDERS.get(app)
    if not folders:
        return ''

    def find():
        done = repo_git('log', '-1', '--format=%h', '--', *folders)
        return done.stdout.strip() if done and done.returncode == 0 else ''
    return cached(('last', app), find)


def older(version, change):
    """True when the commit `change` is not part of the history of `version`."""
    if not re.fullmatch(r'[0-9a-f]{4,40}', version or ''):
        return True
    key = (version, change)
    if key not in ANCESTORS:
        if len(ANCESTORS) > 2000:
            ANCESTORS.clear()
        done = repo_git('merge-base', '--is-ancestor', change, version)
        if done is None:
            return False
        ANCESTORS[key] = done.returncode != 0
    return ANCESTORS[key]


def is_stale(app, test):
    if test.get('state') not in ('ok', 'fail'):
        return False
    change = last_change(app)
    return bool(change) and older(test.get('version', ''), change)


def with_stale(item):
    """A copy of the item for the page: every test says whether it is stale."""
    tests = {}
    for device, test in (item.get('tests') or {}).items():
        if isinstance(test, dict):
            tests[device] = dict(test, stale=is_stale(item.get('app', ''), test))
    return dict(item, tests=tests)


def counts(items):
    """Per device: how many items are ok, fail, untested and stale."""
    out = {}
    for name in devices():
        row = {'name': name, 'this': name == this_device(), 'ok': 0, 'fail': 0, 'untested': 0, 'stale': 0}
        for item in items:
            test = (item.get('tests') or {}).get(name) or {}
            state = test.get('state') if test.get('state') in ('ok', 'fail') else 'untested'
            row['stale' if is_stale(item.get('app', ''), test) else state] += 1
        out[name] = row
    return sorted(out.values(), key=lambda row: (not row['this'], row['name']))
