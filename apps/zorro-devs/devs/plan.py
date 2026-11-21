"""The plan page inside DEVS: its files, and the answers it saves.

Same answers file and the same shape as plan/serve.py, so both servers can run."""
import re

from . import paths, store

ID = re.compile(r'[a-z0-9-]{1,40}')
NAME = re.compile(r'/plan/([a-z0-9-]{1,40}\.(html|css|js|json))')
TYPES = {'html': 'text/html', 'css': 'text/css', 'js': 'text/javascript', 'json': 'application/json'}


def file(path):
    """(bytes, content type) for a page file that sits directly in plan/, or None."""
    found = NAME.fullmatch('/plan/index.html' if path == '/plan/' else path)
    if not found:
        return None
    source = paths.repo() / 'plan' / found.group(1)
    if source.is_symlink() or not source.is_file():
        return None
    try:
        return source.read_bytes(), TYPES[found.group(2)]
    except OSError:
        return None


def answers():
    data = paths.read_json(paths.plan_answers(), {})
    return data if isinstance(data, dict) else {}


def save_answer(answer_id, body):
    """Store one answer; raises store.Invalid when it is not a proper answer."""
    if not ID.fullmatch(answer_id):
        raise store.Invalid('not an answer id')
    if not isinstance(body, dict) or not isinstance(body.get('pick', []), list):
        raise store.Invalid('not an answer')
    entry = {'pick': [str(x)[:200] for x in body.get('pick', [])][:20],
             'note': str(body.get('note', ''))[:10000], 'at': paths.now()}
    with store.LOCK:
        data = answers()
        data[answer_id] = entry
        paths.write_json(paths.plan_answers(), data)
    return entry
