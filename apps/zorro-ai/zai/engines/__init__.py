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
