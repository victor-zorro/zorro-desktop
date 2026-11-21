"""The hub's parts, one module each, in the order they sit on the circle."""
from .ai import Ai
from .files import Files
from .messages import Messages
from .music import Music
from .notes import Notes

MODES = [('apps', 'Apps', 'layout-grid'), ('music', 'Music', 'music'),
         ('notes', 'Notes', 'file-pen'), ('ai', 'AI', 'sparkles'),
         ('messages', 'Messages', 'bell'), ('files', 'Files', 'folder')]
PARTS = {p.key: p for p in (Music(), Notes(), Ai(), Messages(), Files())}
