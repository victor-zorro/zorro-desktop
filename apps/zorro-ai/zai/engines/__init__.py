"""The engines. Each one has: name, title, host (None = on this laptop), model(),
ready() -> (bool, why) and ask(messages, context, on_text, stop_event) -> the model that answered.
ask() calls on_text(piece) while the answer comes in and stops soon after stop_event is set."""
import threading
from contextlib import contextmanager

EXCERPTS = "Excerpts from the user's own files, chosen for this question:"


class EngineError(Exception):
    """the engine could not answer; the text is for the user"""


@contextmanager
def on_stop(stop_event, action):
    """Run action() once if stop_event is set while the block runs."""
    finished = threading.Event()

    def watch():
        while not finished.is_set():
            if stop_event.wait(0.25):
                if not finished.is_set():
                    action()
                return

    threading.Thread(target=watch, daemon=True).start()
    try:
        yield
    finally:
        finished.set()


def context_text(context):
    if not context:
        return ''
    parts = [EXCERPTS]
    for item in context:
        parts.append(f'--- {item.get("path", "")} ---\n{item.get("text", "")}')
    return '\n\n'.join(parts) + '\n\n'


def in_turns(messages):
    """the conversation as every engine accepts it: no empty texts, user and assistant in
    turns, starting and ending with the user (an unanswered question is left out)"""
    out = []
    for m in messages:
        role = 'assistant' if m.get('role') == 'assistant' else 'user'
        text = str(m.get('content', '')).strip()
        if not text or (role == 'assistant' and not out):
            continue
        if out and out[-1]['role'] == role:
            out[-1] = {'role': role, 'content': text}
        else:
            out.append({'role': role, 'content': text})
    while out and out[-1]['role'] != 'user':
        out.pop()
    return out


def without_local_answers(messages):
    """for a cloud engine: what a model on this laptop answered, and the question it
    answered, stay on the laptop (the place it was asked in may be set to local only)"""
    out = []
    for m in messages:
        if m.get('role') == 'assistant' and m.get('engine') == 'local':
            if out and out[-1].get('role') != 'assistant':
                out.pop()
            continue
        out.append(m)
    return out


def newest_that_fit(messages, room):
    """the newest messages that fit in `room` characters; always the last question"""
    kept, used = [], 0
    for m in reversed(messages):
        used += len(m['content'])
        if kept and used > room:
            break
        kept.append(m)
    kept.reverse()
    while kept and kept[0]['role'] != 'user':
        kept.pop(0)
    return kept


def chat_messages(messages, context):
    """messages for a chat-completions API, the excerpts placed before the last user message"""
    out = [{'role': m.get('role', 'user'), 'content': str(m.get('content', ''))} for m in messages]
    extra = context_text(context)
    if not extra:
        return out
    for m in reversed(out):
        if m['role'] == 'user':
            m['content'] = extra + m['content']
            return out
    return out + [{'role': 'user', 'content': extra}]


def all_engines():
    from .claude import Claude
    from .local import Local
    from .mistral import Mistral
    return {'claude': Claude(), 'mistral': Mistral(), 'local': Local()}
