"""On this laptop: llama.cpp's llama-server with a downloaded GGUF model. Nothing leaves the laptop."""
import threading
import time

from .. import config, models
from ..chat_stream import stream_chat
from ..install_local import server_binary
from ..local_server import LlamaServer
from . import EngineError, chat_messages, context_text, newest_that_fit

QUEUE_DEADLINE = 300    # seconds to wait for another local answer to finish
ROOM = 9000              # characters of conversation a local model is given (its window is 4096 tokens)


class Local:
    name, title, host = 'local', 'Local', None

    def __init__(self, server=None, turn=None, forced=None):
        self.server = server or LlamaServer()
        self.turn = turn or threading.Lock()        # one local answer at a time
        self.forced = forced

    def use(self, model_id):
        """the same engine, held to one model"""
        return Local(self.server, self.turn, model_id)

    def model(self):
        return models.chosen(config.load(), self.forced) or ''

    def ready(self):
        if not server_binary():
            return False, 'has no llama-server yet (run: zorro-ai install-local)'
        model_id = self.model()
        if not model_id:
            return False, 'has no model yet (run: zorro-ai models, then zorro-ai pull ID)'
        if not models.installed(model_id):
            return False, f'has no {model_id} yet (run: zorro-ai pull {model_id})'
        return True, ''

    def ask(self, messages, context, on_text, stop_event):
        ok, why = self.ready()
        if not ok:
            raise EngineError(f'Local {why}')
        model_id = self.model()
        if not self._my_turn(stop_event):
            if stop_event.is_set():
                return model_id
            raise EngineError('another local answer is still running')
        try:
            up = self.server.ensure(server_binary(), models.model_path(model_id), stop_event)
            if stop_event.is_set():
                return model_id
            if not up:
                raise EngineError(f'llama-server did not load {model_id} (see llama-server.log)')
            self._answer(up, model_id, messages, context, on_text, stop_event)
        finally:
            self.server.released()
            self.turn.release()
        return model_id

    def _my_turn(self, stop_event):
        deadline = time.monotonic() + QUEUE_DEADLINE
        while time.monotonic() < deadline and not stop_event.is_set():
            if self.turn.acquire(timeout=0.5):
                return True
        return False

    def _answer(self, up, model_id, messages, context, on_text, stop_event):
        port, key = up
        said = {'text': [], 'first': None}

        def count(piece):
            said['first'] = said['first'] or time.monotonic()
            said['text'].append(piece)
            on_text(piece)

        url = f'http://127.0.0.1:{port}/v1/chat/completions'
        room = ROOM - len(context_text(context))       # a small model reads only so much
        body = {'model': model_id, 'messages': chat_messages(newest_that_fit(messages, max(room, 0)), context)}
        stream_chat(url, body, count, stop_event, key=key, timeout=600)
        seconds = time.monotonic() - (said['first'] or time.monotonic())
        words = len(''.join(said['text']).split())
        if words >= 30 and seconds > 1 and not stop_event.is_set():
            models.note_speed(model_id, words / seconds)

    def shutdown(self):
        self.server.stop()
