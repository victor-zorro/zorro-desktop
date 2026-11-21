"""The conversation, shared with the Dialer: ~/.local/state/zorro-intel/chat.json (plan/SPEC.md)."""
import sys
import time
from pathlib import Path

from . import paths

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'zorro-fx'))
import zorro_chat  # noqa: E402  (the code shared with the Dialer)

LIMIT = 20          # messages that go to the engine


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def load():
    return zorro_chat.load(paths.chat_file())


def save(messages):
    zorro_chat.write(messages, paths.chat_file())


def append(message):
    return zorro_chat.append([message], paths.chat_file())


def append_answer(question_message, answer_message):
    return zorro_chat.append_answer(question_message, answer_message, paths.chat_file())


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
    return zorro_chat.for_engine(messages, limit)


def new_chat():
    """Empty the chat; the old one moves to chats/<time>.json. The archive's path, or None."""
    return zorro_chat.new_chat(paths.chat_file())


def delete_all():
    """Remove the chat and every older chat."""
    zorro_chat.delete_all(paths.chat_file())


def count_old():
    return zorro_chat.count_old(paths.chat_file())
