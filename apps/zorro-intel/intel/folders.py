"""The folder rule: only files inside the folders the user chose are shown or sent."""
import os


def real(path):
    return os.path.realpath(os.path.expanduser(str(path)))


def inside(path, folders):
    """True when path, with symlinks followed, lies in one of the folders"""
    if not path:
        return False
    target = real(path)
    for folder in folders:
        root = real(folder).rstrip(os.sep) + os.sep
        if target.startswith(root):
            return True
    return False


def allowed(hits, folders):
    """the search hits whose file lies in a chosen folder"""
    return [h for h in hits if isinstance(h, dict) and inside(h.get('path'), folders)]


def short(path):
    """the path with the home folder written as ~"""
    home = os.path.expanduser('~')
    path = str(path)
    return '~' + path[len(home):] if path == home or path.startswith(home + os.sep) else path
