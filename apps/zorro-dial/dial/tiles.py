"""Things on the rings: rows of tiles (search results) and apps with their hover ring."""
import math

from .look import CYAN, paint
from .nodes import same
from .rings import fits


class Tiles:
    def draw_tiles(self, cr, cx, cy, rings, a0, a1, rows):
        """three rings of tiles: icon and name"""
        for k, ((ri, ro), row) in enumerate(zip(rings, rows)):
            rm = (ri + ro) / 2
            size = (40, 34, 30)[min(k, 2)] * self.icon_scale() * self.iu
            for j, t in enumerate(row):
                am = math.radians(a0 + (a1 - a0) * (j + 0.5) / len(row))
                x, y = cx + math.cos(am) * rm, cy + math.sin(am) * rm
                self.slots.append((x, y, size * 0.85, t, None, None))
                if same(self.hover, t):
                    self.disc(cr, x, y, size * 0.75, CYAN, 0.1)
                    self.chroma_circle(cr, x, y, size * 0.75, alpha=0.5)
                pb = self.icon(t, size)
                if pb:
                    paint(cr, pb, x, y)
                self.text(cr, t['name'][:18], x, y + size * 0.75 + 10 * self.iu, self.pt(8), bold=False,
                          alpha=0.85, split=0)

    def draw_search(self, cr, cx, cy, rings, a0, a1, items=None):
        found = list(items) if items is not None else self.matches()
        for k, (ri, ro) in enumerate(rings):
            size = self.ring_size(k)
            rm = (ri + ro) / 2
            cnt = fits(rm, a1 - a0, size)
            row, found = found[:cnt], found[cnt:]
            for j, a in enumerate(row):
                am = math.radians(a0 + (a1 - a0) * (j + 0.5) / cnt)
                self.draw_app(cr, cx + math.cos(am) * rm, cy + math.sin(am) * rm, size, a)

    def draw_app(self, cr, x, y, size, a, where=None):
        """one app (or '+N') at (x, y): its icon, its hover ring; remembered for clicks"""
        self.slots.append((x, y, size * 0.75, a) + (tuple(where) if where else (None, None)))
        if self.drag and self.drag[0] is a:              # its place, while it is dragged
            cr.new_path()
            cr.arc(x, y, size * 0.6, 0, 2 * math.pi)
            cr.set_source_rgba(1, 1, 1, 0.12)
            cr.set_line_width(1)
            cr.stroke()
            return
        if same(self.hover, a):
            self.disc(cr, x, y, size * 0.9, CYAN, 0.16)
            self.chroma_circle(cr, x, y, size * 0.9)
        if 'more' in a:
            self.disc(cr, x, y, size * 0.55, (1, 1, 1), 0.08)
            self.chroma_circle(cr, x, y, size * 0.55, alpha=0.6, split=1)
            self.text(cr, f'+{a["extra"]}', x, y, max(8, size / 4), split=1)
            return
        pb = self.icon(a, size)
        if pb:
            paint(cr, pb, x, y)
