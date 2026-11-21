"""Shared by the parts: running commands, tiles, the Part class.

A part gives the hub a preview (title, big text, lines) and the fan a tree of tiles. A tile:
{'tile': True, 'icon': 'lucide:NAME' or an icon name, 'name', 'sub', 'act': callable, 'id',
'kids': callable (it unfolds), 'preview': callable (a file), 'keep': True to keep the dial
open, 'refresh': True when the act changes the part's data, 'lit' / 'dim' / 'busy' / 'label'
for how it shows}. Data is read in a thread when the dial opens, into a fresh copy of the
part that is swapped in when complete: a part that is drawn never changes.
"""
import os
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
APPS = Path(os.path.realpath(__file__)).parents[3]      # apps/
for _folder in ('zorro-fx', 'zorro-thinkpad', 'zorro-music'):   # code the parts borrow
    if str(APPS / _folder) not in sys.path:
        sys.path.insert(0, str(APPS / _folder))


def run(*cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ''


def spawn(*cmd):
    try:
        subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def tile(icon, name, sub='', act=None, **kw):
    return {'tile': True, 'icon': icon, 'name': name, 'sub': sub, 'act': act, **kw}


def loading():
    return [tile('lucide:ellipsis', 'Loading…', '', None, id='loading')]


def ago(seconds):
    s = max(0, int(seconds))
    if s < 90:
        return 'now'
    if s < 3600:
        return f'{s // 60} min'
    if s < 86400:
        return f'{s // 3600} h'
    return f'{s // 86400} d'


class Part:
    key = title = ''
    tree = True                         # its tiles unfold ring by ring

    def __init__(self):
        self.ready = False
        self.np = None                  # what plays now (Music)
        self.items = []                 # its list (Messages)

    def fetch(self):
        """slow work, in a thread"""
        self.ready = True

    def renewed(self):
        """a fresh copy with the data read again; the dial swaps it in when it is complete"""
        fresh = type(self)()
        fresh.fetch()
        return fresh

    def roots(self):
        return []

    def preview(self):
        return self.title.upper(), self.title, []

    def centre(self):
        """the hub centre clicked while this part is kept: (label shown, callable) or None"""
        return None
