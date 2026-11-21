"""Ask zorro-ai over its socket (plan/SPEC.md): one JSON line in, JSON lines out; hanging up cancels."""
import json
import socket
import threading

from . import paths

PLACE = 'intel'


class NoService(Exception):
    """zorro-ai does not run"""


class Call:
    """One request. replies() gives the reply objects as they come in; cancel() hangs up."""

    def __init__(self, request, timeout=600):
        self.request, self.timeout = request, timeout
        self.sock = None
        self.cancelled = threading.Event()

    def replies(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(3)
            sock.connect(str(paths.ai_socket()))
        except OSError as e:
            sock.close()
            raise NoService(str(e)) from e
        self.sock = sock
        with sock:
            try:
                sock.settimeout(self.timeout)
                sock.sendall((json.dumps(self.request) + '\n').encode())
                for line in sock.makefile('r', encoding='utf-8'):
                    if self.cancelled.is_set():
                        return
                    yield json.loads(line)
            except (OSError, ValueError) as e:
                if not self.cancelled.is_set():
                    yield {'type': 'error', 'code': 'connection', 'message': f'the answer broke off ({e})'}

    def cancel(self):
        self.cancelled.set()
        if self.sock is not None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class Answer:
    """What the replies of one `ask` add up to."""

    def __init__(self):
        self.text, self.engine, self.model = '', None, None
        self.sent, self.notes = [], []
        self.error, self.done, self.seconds = None, False, None

    def take(self, reply):
        kind = reply.get('type')
        if kind == 'start':
            self.engine, self.model = reply.get('engine'), reply.get('model')
            self.sent = list(reply.get('sent') or [])
        elif kind == 'text':
            self.text += reply.get('delta', '')
        elif kind == 'note':
            self.notes.append(reply.get('text', ''))
        elif kind == 'done':
            self.done = True
            self.engine = reply.get('engine') or self.engine
            self.model = reply.get('model') or self.model
            self.seconds = reply.get('seconds')
        elif kind == 'error':
            self.error = reply.get('message') or reply.get('code') or 'the engine failed'

    @property
    def note(self):
        return '; '.join(n for n in self.notes if n)


def ask_request(messages, context, engine=None):
    return {'op': 'ask', 'place': PLACE, 'messages': messages, 'context': context, 'engine': engine}


def one(request, timeout=30):
    """the single reply of status / models / settings; NoService when zorro-ai does not run"""
    for reply in Call(request, timeout).replies():
        return reply
    return {'type': 'error', 'code': 'connection', 'message': 'no answer from zorro-ai'}


def status():
    return one({'op': 'status'})


def models():
    return one({'op': 'models'}).get('models') or []


def change(settings):
    """write settings through the service; the reply ({type: settings} or {type: error})"""
    return one({'op': 'settings', 'set': settings})


def status_or_none():
    """the status reply, None when zorro-ai does not run or does not answer with one"""
    try:
        reply = status()
    except NoService:
        return None
    return reply if reply.get('type') == 'status' else None


def change_error(settings):
    """None when the service took the change, else what went wrong"""
    try:
        reply = change(settings)
    except NoService:
        return 'The AI service is not running'
    return None if reply.get('type') == 'settings' else reply.get('message', 'not changed')


def running():
    try:
        return one({'op': 'settings'}, 5).get('type') == 'settings'
    except NoService:
        return False
