"""The one conversation the Dialer and Intelligence share: a file both read and append to."""
import json
import os
import tempfile
import time
from pathlib import Path

SEND_LIMIT = 20                         # at most this many messages go to the engine


def path():
    state = os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state'
    return Path(state) / 'zorro-intel' / 'chat.json'


def load(file=None):
    """the messages; [] when there is no file yet or it cannot be read"""
    try:
        data = json.loads(Path(file or path()).read_text())
        found = data.get('messages', [])
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(found, list):
        return []
    return [m for m in found if isinstance(m, dict) and m.get('role') in ('user', 'assistant')
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
    """a message as the file keeps it; more: engine, sent, note"""
    m = {'role': role, 'content': content, 'at': time.strftime('%Y-%m-%dT%H:%M:%S')}
    m.update({k: v for k, v in more.items() if v})
    return m


def append(new, file=None):
    """add messages to what is in the file now (the other app may have written); all of them back"""
    messages = load(file) + list(new)
    write(messages, file)
    return messages


def new_chat(file=None):
    """empty the conversation; the old one moves to chats/<time>.json next to it"""
    file = Path(file or path())
    if load(file):
        chats = file.parent / 'chats'
        chats.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = time.strftime('%Y-%m-%dT%H-%M-%S')
        old = chats / f'{stamp}.json'
        for n in range(1, 100):
            if not old.exists():
                break
            old = chats / f'{stamp}-{n}.json'
        os.replace(file, old)
    write([], file)


def for_engine(messages):
    """what is sent: role and text of the last SEND_LIMIT messages"""
    return [{'role': m['role'], 'content': m['content']} for m in messages[-SEND_LIMIT:]]
