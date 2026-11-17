"""the shared overlay look (apps/zorro-fx), with a plain fallback"""
import sys
from .base import APPS


# ---- overlay background: the shared lock-screen look (apps/zorro-fx) -----------------------

sys.path.insert(0, str(APPS / 'zorro-fx'))
try:
    import zorro_fx
    Snow = zorro_fx.Snow
except ImportError:                     # zorro-fx missing: a plain dark box
    zorro_fx = None

    class Snow:
        def __init__(self, widget, radius=12, fps=30, inner=None):
            self.backdrop, self.backdrop_at = None, (0, 0)
            widget.set_app_paintable(True)
            widget.connect('draw', self.draw)

        @staticmethod
        def draw(_w, cr):
            cr.set_source_rgba(0, 0, 0, 0.94)
            cr.paint()
            return False
