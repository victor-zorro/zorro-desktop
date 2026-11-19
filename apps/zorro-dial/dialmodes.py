"""zorro-dial's parts: what the fan shows when a part of the hub is kept.

Each part gives the hub a preview (title, big text, lines) and the fan three rings of
tiles. A tile: {'tile': True, 'icon': 'lucide:NAME' or an icon name, 'name', 'sub',
'act': callable, 'lit': bool, 'value': 0..1 (a ring around the icon), 'confirm': True
for actions that need a second click, 'keep': True to keep the dial open}.
Data is fetched in a thread when the dial opens; nothing runs while it is closed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
# flake8: noqa: E402,F401,F403 - the names other code uses as dialmodes.<name>
from dialparts.base import *
from dialparts.messages import *
from dialparts.system import *
from dialparts.files import *
from dialparts.notes import *
from dialparts.music import *
from dialparts.base import ago, run, spawn, tile, APPS, HOME, MODES

PARTS = {p.key: p for p in (Messages(), System(), Files(), Notes(), Music())}
