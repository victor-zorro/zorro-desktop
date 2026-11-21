"""The one conversation the Dialer and Intelligence share (plan/SPEC.md): a file both read and
add to, ~/.local/state/zorro-intel/chat.json. Standard library only.

  import sys; sys.path.insert(0, '<repo>/apps/zorro-fx')
  import zorro_chat

Every change happens under a lock file, so two apps writing at the same moment lose nothing.
"""
import fcntl
import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

SEND_LIMIT = 20                         # at most this many messages go to the engine
ROLES = ('user', 'assistant')


def path():
    state = os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state'
    return Path(state) / 'zorro-intel' / 'chat.json'


def chats_dir(file=None):
    return Path(file or path()).parent / 'chats'


@contextmanager
def locked(file=None):
    file = Path(file or path())
    file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(file.parent / '.chat.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield file


def load(file=None):
    """the messages; [] when there is no file yet or it cannot be read"""
    try:
        data = json.loads(Path(file or path()).read_text())
        found = data.get('messages', [])
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(found, list):
        return []
    return [m for m in found if isinstance(m, dict) and m.get('role') in ROLES
            and isinstance(m.get('content'), str)]


def write(messages, file=None):
    """all at once (a temp file, then a rename), readable by the user only"""
    file = Path(file or path())
    file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=file.parent, prefix=f'.{file.name}.')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as fh:
            json.dump({'messages': messages}, fh, indent=1)
            fh.write('\n')
        os.replace(tmp, file)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def message(role, content, **more):
    """a message as the file keeps it; more: engine, sent, model, note, partial"""
    m = {'role': role, 'content': content, 'at': time.strftime('%Y-%m-%dT%H:%M:%S')}
    m.update({k: v for k, v in more.items() if v})
    return m


def append(new, file=None):
    """add messages to what is in the file now; all of them back"""
    with locked(file) as f:
        messages = load(f) + list(new)
        write(messages, f)
    return messages


def append_answer(question, answer, file=None):
    """put an answer right after its question, also when the other app wrote in between
    (the question, stored earlier, moves to the end together with its answer)"""
    with locked(file) as f:
        messages = load(f)
        if question in messages:
            messages.remove(question)
        messages += [question, answer]
        write(messages, f)
    return messages


def new_chat(file=None):
    """empty the conversation; the old one moves to chats/<time>.json. Its path, or None"""
    with locked(file) as f:
        old = None
        if load(f):
            chats = chats_dir(f)
            chats.mkdir(parents=True, exist_ok=True, mode=0o700)
            stamp = time.strftime('%Y-%m-%dT%H-%M-%S')
            old = chats / f'{stamp}.json'
            for n in range(2, 100):
                if not old.exists():
                    break
                old = chats / f'{stamp}-{n}.json'
            os.replace(f, old)
        write([], f)
    return old


def delete_all(file=None):
    """remove the conversation and every older one"""
    with locked(file) as f:
        shutil.rmtree(chats_dir(f), ignore_errors=True)
        f.unlink(missing_ok=True)


def count_old(file=None):
    try:
        return sum(1 for p in chats_dir(file).iterdir() if p.suffix == '.json')
    except OSError:
        return 0


def for_engine(messages, limit=SEND_LIMIT):
    """what is sent: the last `limit` messages as {role, content} (an answer keeps its
    `engine`, so the service can keep what a local model answered away from the cloud).
    Empty texts and questions that never got an answer are left out, except the last one;
    the list starts with a question."""
    kept = []
    for i, m in enumerate(messages):
        last = i + 1 == len(messages)
        if not m['content'].strip():
            continue
        if m['role'] == 'user' and not last and messages[i + 1]['role'] == 'user':
            continue
        out = {'role': m['role'], 'content': m['content']}
        if m['role'] == 'assistant' and m.get('engine'):
            out['engine'] = m['engine']
        kept.append(out)
    kept = kept[-limit:]
    while kept and kept[0]['role'] != 'user':
        kept.pop(0)
    return kept
