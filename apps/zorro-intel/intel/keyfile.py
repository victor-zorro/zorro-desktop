"""The Mistral API key in ~/.config/zorro-ai/mistral.key (0600). The key is never shown or logged."""
from . import files, paths


class BadKey(ValueError):
    pass


def present():
    try:
        return bool(paths.mistral_key_file().read_text().strip())
    except OSError:
        return False


def store(key):
    key = key.strip()
    if not key:
        raise BadKey('Paste the key first')
    if any(c.isspace() for c in key) or not key.isprintable():
        raise BadKey('A key is one word without spaces')
    files.write_atomic(paths.mistral_key_file(), key + '\n', 0o600)


def remove():
    """True when there was a key"""
    try:
        paths.mistral_key_file().unlink()
        return True
    except OSError:
        return False
