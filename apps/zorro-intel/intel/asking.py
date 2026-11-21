"""One question from start to end: store it, find the excerpts, ask zorro-ai, store the answer."""
import threading

from . import ai, chat, config, excerpts

NOT_RUNNING = 'The AI service is not running'


class Asking:
    """run() does the work (in a worker thread); cancel() stops it. on_change() is called
    whenever stage, answer or failure changed."""

    def __init__(self, text, about=None, on_change=lambda: None):
        self.text, self.about, self.on_change = text, about, on_change
        self.answer = ai.Answer()
        self.stage = 'search'               # search -> ask -> end
        self.note = None                    # from our side: why no files went along
        self.no_service = False
        self.cancelled = threading.Event()
        self.call = None

    def cancel(self):
        self.cancelled.set()
        if self.call is not None:
            self.call.cancel()

    def run(self):
        messages = chat.append(chat.question(self.text))
        self.on_change()
        context, self.note = excerpts.gather(self.text, config.load(), self.about)
        if not self.cancelled.is_set():
            self._ask(chat.for_engine(messages), context)
        self._store()
        self.stage = 'end'
        self.on_change()
        return self

    def _ask(self, messages, context):
        self.stage = 'ask'
        self.call = ai.Call(ai.ask_request(messages, context))
        self.on_change()
        if self.cancelled.is_set():
            return
        try:
            for reply in self.call.replies():
                self.answer.take(reply)
                self.on_change()
                if self.answer.done or self.answer.error:
                    break
        except ai.NoService:
            self.no_service = True
            self.answer.error = NOT_RUNNING
        if not (self.answer.done or self.answer.error or self.cancelled.is_set()):
            self.answer.error = 'The AI service hung up before the answer was finished'

    @property
    def notes(self):
        return '; '.join(n for n in (self.note, self.answer.note) if n)

    def _store(self):
        """A finished answer is stored whole; what arrived of a stopped or broken one as partial."""
        a = self.answer
        if not a.text.strip():
            return
        chat.append(chat.answer(a.text, a.engine, a.sent, a.model, self.notes or None,
                                partial=not a.done))
