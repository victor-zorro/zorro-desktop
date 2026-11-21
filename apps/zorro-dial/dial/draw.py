"""One frame of the dial: the fan for the kept part, the rim, the hub, the hint line."""
import math
import time

from .look import CYAN, RED, Gdk, cairo, paint
from .parts.base import tile

HINT_APPS = 'type to search · drag to rearrange, onto the clock to remove · hold for more · Esc closes'
HINT_TREE = 'rest on something: it opens in the next ring · Esc: one back'
SEARCHES = {'notes': 'notes', 'music': 'SoundCloud'}


class Draw:
    def paint_back(self, _w, cr):
        cr.save()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        if self.backdrop is not None:
            Gdk.cairo_set_source_pixbuf(cr, self.backdrop, 0, 0)
            cr.paint()
            cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_source_rgba(0, 0, 0, 0.55)
        cr.paint()
        cr.restore()
        return False

    def on_draw(self, _w, cr):
        cx, cy, hub, a0, a1, rings = self.fan()
        outer = rings[-1][1]
        self.slots = []
        chat = self.chat_mode()
        if not chat:
            self.draw_fan(cr, cx, cy, rings, a0, a1)
            self.draw_rim(cr, cx, cy, outer, a0, a1)
        self.draw_hub(cr, cx, cy, hub)
        if self.mode == 'music' and not self.filter:
            self.music_keys(cr, cx, cy, hub)
        if chat:
            self.draw_chat(cr)
        else:
            self.draw_preview(cr)
            self.draw_dragged(cr)
            self.draw_hint(cr, cx, cy, (a0 + a1) / 2, outer)
        if self.menu:
            self.draw_menu(cr)
        return False

    def draw_fan(self, cr, cx, cy, rings, a0, a1):
        """what the rings hold: search results, the kept part's tree, or the apps"""
        if self.filter and self.mode == 'notes':
            found = self.parts['notes'].search_tiles(self.filter)
            rows = [found[:6], found[6:15], found[15:27]] if found else \
                [[], [tile('lucide:search', 'No note has that', self.filter[:24], None)], []]
            self.draw_tiles(cr, cx, cy, rings, a0, a1, rows)
        elif self.filter and self.mode == 'music':
            self.draw_tiles(cr, cx, cy, rings, a0, a1, [[], [tile(
                'lucide:search', f'SoundCloud: {self.filter}'[:30], 'Enter: play', None)], []])
        elif self.filter:
            self.draw_search(cr, cx, cy, rings, a0, a1)
        elif self.mode != 'apps':
            part = self.parts[self.mode]
            if hasattr(part, 'draw_rim'):
                part.draw_rim(self, cr, cx, cy, rings, a0, a1)
            self.draw_tree(cr, cx, cy, rings, a0, a1, part)
        elif self.expanded == 'gear':
            self.draw_search(cr, cx, cy, rings, a0, a1, self.settings)
        elif self.expanded is not None:
            self.draw_search(cr, cx, cy, rings, a0, a1, self.groups[self.expanded])
        else:
            self.draw_slices(cr, cx, cy, rings, a0, a1)

    def draw_rim(self, cr, cx, cy, outer, a0, a1):
        """the chromatic outer rim"""
        for col, dx in ((RED, -1.5), (CYAN, 1.5)):
            cr.save()
            cr.translate(dx, 0)
            cr.new_path()
            cr.arc(cx, cy, outer, math.radians(a0), math.radians(a1))
            cr.set_source_rgba(*col, 0.6)
            cr.set_line_width(1.2)
            cr.stroke()
            cr.restore()

    def draw_dragged(self, cr):
        """the app being dragged, under the mouse; the clock becomes a bin meanwhile"""
        if not self.drag:
            return
        a, x, y = self.drag
        if self.mode == 'apps' and not self.filter and self.expanded is None:
            self.draw_bin(cr, x, y)
        self.disc(cr, x, y, 40 * self.iu, CYAN, 0.12)
        self.chroma_circle(cr, x, y, 40 * self.iu)
        pb = self.icon(a, 44 * self.iu)
        if pb:
            paint(cr, pb, x, y)

    def draw_hint(self, cr, cx, cy, mid, outer):
        """one line outside the fan: what you type, or what you can do here"""
        am = math.radians(mid)
        hx, hy = cx + math.cos(am) * (outer + 115 * self.u), cy + math.sin(am) * (outer + 115 * self.u)
        if self.filter:                 # what you type, in full (the end of it if long)
            shown = self.filter if len(self.filter) <= 48 else '…' + self.filter[-47:]
            line, size = f'search {SEARCHES.get(self.mode, "apps")}:  {shown}', self.pt(11)
            # kept on the screen, measured with the caret's room so it does not jump
            hx, hy = self.hint_at(cr, line + '▏', hx, hy, size, True, cx, cy, am, outer)
            self.text(cr, line + ('▏' if int(time.time() * 2) % 2 else ' '),
                      hx, hy, size, bold=True, alpha=0.95, split=1.0)
            return
        search = f'type: search {SEARCHES[self.mode]} · ' if self.mode in SEARCHES else ''
        line = HINT_APPS if self.mode == 'apps' else search + HINT_TREE
        size = self.pt(9)
        hx, hy = self.hint_at(cr, line, hx, hy, size, False, cx, cy, am, outer)
        self.text(cr, line, hx, hy, size, bold=False, alpha=0.5, split=0)

    def hint_at(self, cr, s, hx, hy, size, bold, cx, cy, am, outer):
        """the hint line's place: out along the fan's middle until no part of it touches the
        rings or the slice names, and on the screen"""
        w, h = self.text_ext(cr, s, size, bold)
        clear = outer + 34 * self.u
        for _ in range(6):
            nx = min(max(cx, hx - w / 2), hx + w / 2)       # its point nearest the clock
            ny = min(max(cy, hy - h / 2), hy + h / 2)
            short = clear - math.hypot(nx - cx, ny - cy)
            if short <= 0.5:
                break
            hx, hy = hx + math.cos(am) * short, hy + math.sin(am) * short
        return self.inside(cr, s, hx, hy, size, bold)
