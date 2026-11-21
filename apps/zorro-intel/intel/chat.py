"""The conversation, shared with the Dialer: ~/.local/state/zorro-intel/chat.json (plan/SPEC.md)."""
import shutil
import time

from . import files, paths

LIMIT = 20          # messages that go to the engine
ROLES = ('user', 'assistant')


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def load():
    data = files.read_json(paths.chat_file(), {})
    messages = data.get('messages') if isinstance(data, dict) else None
    if not isinstance(messages, list):
        return []
    return [m for m in messages
            if isinstance(m, dict) and m.get('role') in ROLES and isinstance(m.get('content'), str)]


def save(messages):
    files.write_json(paths.chat_file(), {'messages': messages})


def append(message):
    messages = load() + [message]
    save(messages)
    return messages


def question(text):
    return {'role': 'user', 'content': text, 'at': now()}


def answer(text, engine, sent, model=None, note=None, partial=False):
    message = {'role': 'assistant', 'content': text, 'at': now(), 'engine': engine, 'sent': list(sent)}
    if model:
        message['model'] = model
    if note:
        message['note'] = note
    if partial:
        message['partial'] = True
    return message


def for_engine(messages, limit=LIMIT):
    """The last `limit` messages as {role, content}. A question that never got an answer is
    left out (except the last one), and the list starts with a question."""
    kept = []
    for i, m in enumerate(messages):
        last = i + 1 == len(messages)
        if not m['content'].strip():
            continue
        if m['role'] == 'user' and not last and messages[i + 1]['role'] == 'user':
            continue
        kept.append({'role': m['role'], 'content': m['content']})
    kept = kept[-limit:]
    while kept and kept[0]['role'] != 'user':
        kept.pop(0)
    return kept


def new_chat():
    """Empty the chat; the old one moves to chats/<time>.json. The archive's path, or None."""
    messages = load()
    kept = None
    if messages:
        stamp = time.strftime('%Y-%m-%dT%H-%M-%S')
        kept = paths.chats_dir() / f'{stamp}.json'
        for n in range(2, 100):
            if not kept.exists():
                break
            kept = paths.chats_dir() / f'{stamp}-{n}.json'
        files.write_json(kept, {'messages': messages})
    save([])
    return kept


def delete_all():
    """Remove the chat and every older chat."""
    shutil.rmtree(paths.chats_dir(), ignore_errors=True)
    try:
        paths.chat_file().unlink()
    except OSError:
        pass


def count_old():
    try:
        return sum(1 for p in paths.chats_dir().iterdir() if p.suffix == '.json')
    except OSError:
        return 0
