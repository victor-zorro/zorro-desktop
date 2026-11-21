"""Where zorro-ai keeps its things. Read from the environment at each call, so tests can move them."""
import os
from pathlib import Path


def _base(var, fallback):
    return Path(os.environ.get(var) or Path.home() / fallback)


def config_dir():
    return _base('XDG_CONFIG_HOME', '.config') / 'zorro-ai'


def data_dir():
    return _base('XDG_DATA_HOME', '.local/share') / 'zorro-ai'


def config_file():
    return config_dir() / 'config.json'


def mistral_key_file():
    return config_dir() / 'mistral.key'


def models_dir():
    return data_dir() / 'models'


def llama_dir():
    return data_dir() / 'llama'


def speeds_file():
    return data_dir() / 'speeds.json'


def socket_path():
    return Path(os.environ.get('XDG_RUNTIME_DIR') or '/tmp') / 'zorro-ai.sock'
