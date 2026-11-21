"""The JSON API: each route takes plain values and returns (status code, answer)."""
import re
import threading
import time

from . import checks, devices, plan, store

ITEM = re.compile(r'/api/items/([^/]+)')
ITEM_TEST = re.compile(r'/api/items/([^/]+)/test')
ANSWER = re.compile(r'/plan/api/answers/([^/]+)')
CHECKING = threading.Lock()
CHECK_GAP = 60                  # seconds between two runs of the automatic checks
LAST_CHECK = {"at": -CHECK_GAP}
MISSING = (404, {'error': 'not found'})


def one(query, name):
    return (query.get(name) or [''])[0][:80]


def list_items(query):
    kind, app = one(query, 'kind'), query.get('app')
    if kind and kind not in store.KINDS:
        return 400, {'error': 'kind: not a kind'}
    items = store.all_items(kind or None, app[0][:80] if app else None)
    this = devices.this_device()
    names = sorted(devices.devices(), key=lambda name: (name != this, name))
    return 200, {'items': [devices.with_stale(i) for i in items], 'devices': names, 'this': this}


def list_apps(query):
    """Every app in the data, in the fixed order, with its count for one kind."""
    kind = one(query, 'kind')
    items = store.all_items()
    names = {i.get('app', '') for i in items}
    order = [a for a in devices.APP_FOLDERS if a in names] + sorted(names - set(devices.APP_FOLDERS))
    kinds = {k: sum(1 for i in items if i.get('kind') == k) for k in store.KINDS}
    apps = [{'name': a, 'count': sum(1 for i in items if i.get('app', '') == a and i.get('kind') == kind)}
            for a in order]
    return 200, {'kinds': kinds, 'apps': apps}


def list_devices(query):
    return 200, {'this': devices.this_device(), 'devices': devices.counts(store.all_items()),
                 'checks': checks.results(), 'names': list(checks.CHECKS)}


def create_item(body):
    fields = {k: v for k, v in body.items() if k not in ('kind', 'title')}
    if 'check' in fields or 'status' in fields:
        raise store.Invalid('only kind, title, app, category, text, steps')
    return 200, store.create(body.get('kind'), body.get('title'), **fields)


def update_item(item_id, body):
    store.path(item_id)
    if 'check' in body:
        raise store.Invalid('check: not a field')
    item = store.update(item_id, body)
    return (200, devices.with_stale(item)) if item else MISSING


def test_item(item_id, body):
    store.path(item_id)
    device = body.get('device')
    if device not in devices.devices():
        raise store.Invalid('device: not a known device')
    item = store.set_test(item_id, device, body.get('state'), devices.head())
    return (200, devices.with_stale(item)) if item else MISSING


def run_checks():
    if not CHECKING.acquire(blocking=False):
        return 409, {'error': 'the checks are already running'}
    try:
        if time.monotonic() - LAST_CHECK['at'] < CHECK_GAP:
            return 429, {'error': 'the checks just ran: wait a minute'}
        LAST_CHECK['at'] = time.monotonic()
        return 200, {'checks': checks.run()}
    finally:
        CHECKING.release()


GET = {'/api/items': list_items, '/api/apps': list_apps, '/api/devices': list_devices,
       '/plan/api/answers': lambda query: (200, plan.answers())}


def get(path, query):
    route = GET.get(path)
    return route(query) if route else MISSING


def post(path, body):
    """Routes a POST. A body that is refused becomes a 400 with the reason."""
    if not isinstance(body, dict):
        return 400, {'error': 'not a JSON object'}
    try:
        if path == '/api/items':
            return create_item(body)
        if path == '/api/check':
            return run_checks()
        for pattern, route in ((ITEM_TEST, test_item), (ITEM, update_item)):
            found = pattern.fullmatch(path)
            if found:
                return route(found.group(1), body)
        found = ANSWER.fullmatch(path)
        if found:
            plan.save_answer(found.group(1), body)
            return 200, {'ok': True}
    except store.Invalid as err:
        return 400, {'error': str(err)}
    return MISSING
