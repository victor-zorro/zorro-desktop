"""One side of a transfer in a test: the real command line, with everything that would
touch the real machine swapped for a stand-in. Settings come as JSON in $ZT_TEST."""
import json
import os
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transfer import after, beacon, cli, find, generated, items, net, sender, serve, state  # noqa: E402

CFG = json.loads(os.environ.get('ZT_TEST') or '{}')


def running(_groups):
    """the apps that 'run': the lines of a file the test writes"""
    try:
        return Path(CFG['running']).read_text().split()
    except (OSError, KeyError):
        return []


def lying_file_list(real):
    def file_list(groups):
        return real(groups) + CFG.get('extra_files', [])
    return file_list


def lying_stream(real):
    def stream(self, fh, size, off, rel):
        digest = real(self, fh, size, off, rel)
        return '0' * 64 if rel in CFG.get('bad_big', []) else digest
    return stream


def lying_sha(real):
    left = dict(CFG.get('bad_small', {}))        # {content: how many times to lie}

    def sha(data):
        key = data.decode(errors='replace')
        if left.get(key, 0) > 0:
            left[key] -= 1
            return '0' * 64
        return real(data)
    return sha


def lying_get(real):
    """a sender that announces another size than its list, and then streams without end"""
    def get(self, req):
        if req.get('path') not in CFG.get('lie_size', []):
            return real(self, req)
        net.send_json(self.t, {'ok': True, 'size': 1 << 40, 'offset': 0})
        while True:                         # until the receiver hangs up
            self.t.sendall(b'x' * 65536)
    return get


def fat_batch(self, req):
    """a sender that claims the biggest size for every file of a batch"""
    n = len(req.get('paths') or [])
    net.send_json(self.t, {'sizes': [serve.BATCH_MOST] * n})
    while True:
        self.t.sendall(b'x' * 65536)


class BadDisk:
    """a file that breaks after its first chunk, as a bad spot on a disk does"""

    def __init__(self, fh):
        self.fh, self.reads = fh, 0

    def read(self, n):
        self.reads += 1
        if self.reads > 1:
            raise OSError(5, 'Input/output error')
        return self.fh.read(n)


def failing_disk(real):
    def stream(self, fh, size, off, rel):
        return real(self, BadDisk(fh) if rel in CFG.get('eio', []) else fh, size, off, rel)
    return stream


def patch_wire():
    """who is trusted, and the senders that do not play fair"""
    distrust = set(CFG.get('distrust', []))
    net.trusted = lambda addr: addr not in distrust and addr.startswith('127.')
    serve.file_list = lying_file_list(serve.file_list)
    serve.Serving.stream = failing_disk(lying_stream(serve.Serving.stream))
    serve.Serving.get = lying_get(serve.Serving.get)
    if CFG.get('fat_batch'):
        serve.Serving.batch = fat_batch
    serve.sha = lying_sha(serve.sha)
    for name in ('BATCH_CAP',):
        setattr(serve, name, CFG.get(name, getattr(serve, name)))
    for name in ('FIRST_WAIT', 'MAX_FAILS', 'PEER_FAILS', 'IDLE_EXIT', 'PAIR_TIME', 'MAX_CONNECTIONS'):
        setattr(sender, name, CFG.get(name, getattr(sender, name)))
    if 'session_id' in CFG:
        sender.new_session_id = lambda: CFG['session_id']


def patch():
    items.running = running
    desktop = items.GROUPS['desktop'][2]
    desktop[:] = [r for r in desktop if not r.startswith('sys:')]     # never the real /etc
    items.SETUP_HELPER = CFG.get('helper', '/nonexistent/helper')
    after.SETTINGS = after.ICONS = Path('/nonexistent')
    generated.people = lambda: CFG.get('people', [])
    state.notify = lambda *a: None
    for name in ('RETRY_FOR', 'RETRY_PAUSE', 'APPS_WAIT', 'APPS_POLL'):
        setattr(state, name, CFG.get(name, getattr(state, name)))
    if 'groups_here' in CFG:
        exist, mine = CFG['groups_here']
        generated.groups_here = lambda: (set(exist), set(mine))
    patch_wire()
    find.BROADCASTS = CFG.get('broadcasts', ['127.0.0.1'])    # never the real network
    for name in ('KNOCK_EACH', 'KNOCK_ALL', 'TIMEOUT'):
        setattr(beacon, name, CFG.get(name, getattr(beacon, name)))
    if 'send_cmd' in CFG:
        beacon.send_command = lambda: CFG['send_cmd']
    if 'notify_answer' in CFG:
        os.environ['ZT_NOTIFY_ANSWER'] = CFG['notify_answer']
    if CFG.get('old_python'):
        net.ssl = type('ssl', (), {'SSLContext': object, 'SSLError': ssl.SSLError})


patch()
sys.argv[0] = 'zorro-transfer'
sys.exit(cli.main())
