"""The items: one JSON file each, in a folder that is its own git repo."""
import re
import shutil
import subprocess
import threading

from . import paths

KINDS = ('feature', 'bug', 'wish', 'backlog', 'decision')
STATUSES = ('open', 'doing', 'done')
STATES = ('ok', 'fail', 'untested')
ID = re.compile(r'[a-z0-9][a-z0-9-]{0,79}')
DEVICE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
CHECK = re.compile(r'[a-z]{0,20}')
LIMITS = {'title': 120, 'text': 4000, 'steps': 4000, 'app': 40, 'category': 40}
ONE_LINE = ('title', 'app', 'category')
LOCK = threading.RLock()
GIT = ['git', '-c', 'user.name=zorro-devs', '-c', 'user.email=zorro-devs@localhost',
       '-c', 'commit.gpgsign=false']


class Invalid(ValueError):
    """A field the store refuses; the message says which and why."""


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:80].strip('-')


def clean(fields):
    """The given fields, checked: allowed names, types, lengths and values."""
    out = {}
    for name, value in fields.items():
        if name in LIMITS:
            out[name] = clean_text(name, value)
        elif name == 'kind':
            out[name] = one_of(name, value, KINDS)
        elif name == 'status':
            out[name] = one_of(name, value, STATUSES)
        elif name == 'check':
            if not isinstance(value, str) or not CHECK.fullmatch(value):
                raise Invalid('check: not a check name')
            out[name] = value
        else:
            raise Invalid(f'{name}: not a field')
    if out.get('title') == '':
        raise Invalid('title: empty')
    return out


def clean_text(name, value):
    if not isinstance(value, str):
        raise Invalid(f'{name}: not text')
    value = value.replace('\r', '').strip()
    if name in ONE_LINE:
        value = ' '.join(value.split())
    if len(value) > LIMITS[name]:
        raise Invalid(f'{name}: longer than {LIMITS[name]}')
    return value


def one_of(name, value, allowed):
    if value not in allowed:
        raise Invalid(f'{name}: one of {", ".join(allowed)}')
    return value


def path(item_id):
    if not isinstance(item_id, str) or not ID.fullmatch(item_id):
        raise Invalid('id: only a-z, 0-9 and -')
    return paths.items_dir() / f'{item_id}.json'


def load(item_id):
    item = paths.read_json(path(item_id), None)
    return item if isinstance(item, dict) and item.get('id') == item_id else None


def all_items(kind=None, app=None):
    out = []
    for file in sorted(paths.items_dir().glob('*.json')):
        item = load(file.stem) if ID.fullmatch(file.stem) else None
        if not item:
            continue
        if kind and item.get('kind') != kind:
            continue
        if app is not None and item.get('app', '') != app:
            continue
        out.append(item)
    return out


def git(*args):
    """Run git in the items folder. No git, or git failing, never stops the store."""
    if not shutil.which('git'):
        return False
    try:
        done = subprocess.run(GIT + list(args), cwd=paths.items_dir(), capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def commit(message):
    with LOCK:
        folder = paths.items_dir()
        folder.mkdir(parents=True, exist_ok=True)
        if not (folder / '.git').exists():
            git('init', '-q')
        git('add', '-A')
        git('commit', '-q', '-m', message[:72])


def save(item, message, commit_now=True):
    with LOCK:
        paths.write_json(path(item['id']), item)
        if commit_now:
            commit(message)
    return item


def free_id(base):
    base = base or 'item'
    if not path(base).exists():
        return base
    for n in range(2, 1000):
        candidate = f'{base[:75]}-{n}'
        if not path(candidate).exists():
            return candidate
    raise Invalid('id: too many items with this title')


def new_item(kind, title, fields, item_id=None):
    """A complete item, not yet saved."""
    values = clean(dict(fields, kind=kind, title=title))
    item = {'id': item_id or slug(f'{values.get("app", "")}-{values["title"]}'),
            'kind': values['kind'], 'title': values['title'], 'text': '', 'app': '',
            'category': '', 'status': 'open', 'steps': '', 'check': '', 'tests': {}}
    item.update(values)
    return item


def create(kind, title, **fields):
    with LOCK:
        item = new_item(kind, title, fields)
        item['id'] = free_id(item['id'])
        return save(item, f'add {item["id"]}')


def update(item_id, fields):
    with LOCK:
        item = load(item_id)
        if not item:
            return None
        values = clean(fields)
        if not values:
            raise Invalid('nothing to change')
        item.update(values)
        return save(item, f'{item_id}: {", ".join(sorted(values))}')


def set_test(item_id, device, state, version, commit_now=True):
    if not isinstance(device, str) or not DEVICE.fullmatch(device):
        raise Invalid('device: not a device name')
    one_of('state', state, STATES)
    with LOCK:
        item = load(item_id)
        if not item:
            return None
        item.setdefault('tests', {})[device] = {'state': state, 'at': paths.now(), 'version': version}
        return save(item, f'{item_id}: {state} on {device}', commit_now)
