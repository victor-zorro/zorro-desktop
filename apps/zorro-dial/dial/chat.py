"""The AI part's conversation: what was said, the question under way, the answer coming in."""
import os
import threading

from . import aiclient, chatfile

SHOWN = 20                              # the panel never lays out more messages than this


class Chat:
    def __init__(self, post, file=None, sock=None):
        self.post = post                # runs a function on the GTK thread
        self.file, self.sock = file, sock
        self.messages = []
        self.text = ''                  # the question line being typed
        self.asked = None               # the question under way
        self.answer, self.engine, self.note, self.sent = '', '', '', []
        self.problem = ''               # one calm line: no service, or what the service said
        self.ask = None

    @property
    def busy(self):
        return self.ask is not None

    def open(self):
        """the part opens: read the shared conversation, see whether the service is there"""
        self.messages = chatfile.load(self.file)
        threading.Thread(target=self.check, daemon=True).start()

    def follow(self):
        """Intelligence wrote to the shared conversation meanwhile: show it (one cheap look)"""
        try:
            stamp = os.stat(self.file or chatfile.path()).st_mtime_ns
        except OSError:
            stamp = 0
        if stamp != getattr(self, 'stamp', None) and not self.busy:
            self.stamp = stamp
            self.messages = chatfile.load(self.file)

    def check(self):
        ok = aiclient.available(self.sock)
        self.post(lambda: self.checked(ok))

    def checked(self, ok):
        if not self.busy:
            self.problem = '' if ok else aiclient.NO_SERVICE

    def send(self):
        text = self.text.strip()
        if not text or self.busy:
            return False
        self.messages = chatfile.load(self.file)
        self.asked, self.text = text, ''
        self.answer = self.engine = self.note = self.problem = ''
        self.sent = []
        outgoing = chatfile.for_engine(self.messages + [{'role': 'user', 'content': text}])
        ask = aiclient.Ask(outgoing, lambda ev: self.post(lambda: self.on_event(ask, ev)), self.sock)
        self.ask = ask
        ask.start()
        return True

    def on_event(self, ask, event):
        if ask is not self.ask:
            return                      # an answer that was cancelled meanwhile
        kind = event.get('type')
        if kind == 'start':
            self.engine = str(event.get('engine') or '')
            self.sent = [p for p in event.get('sent') or [] if isinstance(p, str)]
        elif kind == 'text':
            self.answer += str(event.get('delta') or '')
        elif kind == 'note':
            self.note = str(event.get('text') or '')
        elif kind == 'done':
            self.finish(str(event.get('engine') or self.engine))
        elif kind == 'error':
            self.stop(str(event.get('message') or 'The AI service gave no answer.'))

    def finish(self, engine):
        """the answer is complete: question and answer go into the shared file"""
        new = [chatfile.message('user', self.asked),
               chatfile.message('assistant', self.answer, engine=engine, sent=self.sent, note=self.note)]
        try:
            self.messages = chatfile.append(new, self.file)
        except OSError as e:
            self.messages = self.messages + new
            self.problem = f'The chat could not be saved: {e}'
        self.ask = self.asked = None
        self.answer = ''

    def stop(self, problem=''):
        """no answer (an error, or cancelled): the question goes back on its line"""
        self.text = self.text or self.asked or ''
        self.ask = self.asked = None
        self.answer = ''
        self.problem = problem

    def cancel(self):
        if self.ask:
            self.ask.cancel()
            self.stop()

    def new_chat(self):
        self.cancel()
        try:
            chatfile.new_chat(self.file)
            self.problem = ''
        except OSError as e:
            self.problem = f'The chat could not be saved: {e}'
        self.messages = chatfile.load(self.file)

    def blocks(self, view='history'):
        """what the panel shows, oldest first: (kind, text) with kind q, a or meta"""
        messages = self.messages[-SHOWN:]
        if view == 'last':
            last = max((i for i, m in enumerate(messages) if m['role'] == 'user'), default=0)
            messages = [] if self.asked else messages[last:]
        out = []
        for m in messages:
            if m['role'] == 'user':
                out.append(('q', m['content']))
            else:
                out.append(('a', m['content']))
                out.append(('meta', under(m.get('engine'), m.get('note'))))
        if self.asked:
            out.append(('q', self.asked))
            out.append(('a', self.answer or '…'))
            out.append(('meta', under(self.engine, self.note)))
        return [(kind, text) for kind, text in out if text]


def under(engine, note):
    """the dim line under an answer: the engine that answered and, if any, its note"""
    return ' · '.join(str(x) for x in (engine, note) if x)
