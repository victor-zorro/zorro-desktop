"""Mistral's cloud: the chat-completions API with the key from ~/.config/zorro-ai/mistral.key."""
from .. import paths
from ..chat_stream import stream_chat
from . import EngineError, chat_messages

URL = 'https://api.mistral.ai/v1/chat/completions'
MODEL = 'mistral-small-latest'


class Mistral:
    name, title, host = 'mistral', 'Mistral', 'api.mistral.ai'

    def __init__(self, url=URL, model=MODEL):
        self.url, self._model = url, model

    def model(self):
        return self._model

    def _key(self):
        try:
            return paths.mistral_key_file().read_text().strip()
        except OSError:
            return ''

    def ready(self):
        if not self._key():
            return False, f'has no key yet (put your Mistral API key in {paths.mistral_key_file()})'
        return True, ''

    def ask(self, messages, context, on_text, stop_event):
        key = self._key()
        if not key:
            raise EngineError(f'Mistral {self.ready()[1]}')
        body = {'model': self._model, 'messages': chat_messages(messages, context)}
        last = stream_chat(self.url, body, on_text, stop_event, key=key)
        return last.get('model') or self._model
