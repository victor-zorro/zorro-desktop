"""Where Intelligence keeps its things. Read from the environment at each call, so tests can move them."""
import os
from pathlib import Path


def _base(var, fallback):
    return Path(os.environ.get(var) or Path.home() / fallback)


def config_file():
    return _base('XDG_CONFIG_HOME', '.config') / 'zorro-intel' / 'config.json'


def state_dir():
    return _base('XDG_STATE_HOME', '.local/state') / 'zorro-intel'


def chat_file():
    return state_dir() / 'chat.json'


def chats_dir():
    return state_dir() / 'chats'


def mistral_key_file():
    return _base('XDG_CONFIG_HOME', '.config') / 'zorro-ai' / 'mistral.key'


def _runtime():
    return Path(os.environ.get('XDG_RUNTIME_DIR') or '/tmp')


def ai_socket():
    return _runtime() / 'zorro-ai.sock'


def search_socket():
    return _runtime() / 'zorro-search.sock'
