"""One side of a transfer in a test: the real command line, with everything that would
touch the real machine swapped for a stand-in. Settings come as JSON in $ZT_TEST."""
import json
import os
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transfer import after, cli, generated, items, net, sender, serve, state  # noqa: E402

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


def patch():
    items.running = running
    items.SETUP_HELPER = CFG.get('helper', '/nonexistent/helper')
    after.SETTINGS = after.ICONS = Path('/nonexistent')
    generated.people = lambda: CFG.get('people', [])
    state.notify = lambda *a: None
    for name in ('RETRY_FOR', 'RETRY_PAUSE', 'APPS_WAIT', 'APPS_POLL'):
        setattr(state, name, CFG.get(name, getattr(state, name)))
    for name in ('FIRST_WAIT', 'MAX_FAILS', 'IDLE_EXIT'):
        setattr(sender, name, CFG.get(name, getattr(sender, name)))
    if 'session_id' in CFG:
        sender.new_session_id = lambda: CFG['session_id']
    serve.file_list = lying_file_list(serve.file_list)
    serve.Serving.stream = lying_stream(serve.Serving.stream)
    serve.sha = lying_sha(serve.sha)
    if CFG.get('old_python'):
        net.ssl = type('ssl', (), {'SSLContext': object, 'SSLError': ssl.SSLError})


patch()
sys.argv[0] = 'zorro-transfer'
sys.exit(cli.main())
