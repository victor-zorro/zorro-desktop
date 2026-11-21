"""Trees: each level of a part in the next ring, unfolding where the mouse rests."""
import math
import sys
import threading
import time

from .look import CYAN, RED, paint
from .nodes import cache_key, node_key, same
from .parts.base import tile

DWELL = 0.4                             # seconds of rest before something unfolds


class Tree:
    def tree_levels(self, part):
        levels = [part.roots()]
        for n in self.path.get(part.key, []):
            kids = self.kids.get(cache_key(part.key, n))
            levels.append([tile('lucide:ellipsis', 'opening…', '', None, id='__loading')]
                          if kids is None else kids)
        return levels

    def expand(self, node, level):
        """unfold node: its children (read in a thread) show in the next ring"""
        path = self.path.setdefault(self.mode, [])
        del path[level:]
        path.append(node)
        key = cache_key(self.mode, node)
        if key not in self.kids:
            self.kids[key] = None
            threading.Thread(target=self.read_kids, args=(key, node), daemon=True).start()
        self.dwell = None
        self.area.queue_draw()

    def read_kids(self, key, node):
        try:
            kids = node['kids']()
        except Exception as e:  # noqa: BLE001 - say what went wrong, not an empty ring
            print(f'zorro-dial: {node.get("name")}: {type(e).__name__}: {e}', file=sys.stderr)
            kids = [tile('lucide:triangle-alert', 'Could not load',
                         str(e)[:40] or type(e).__name__, None, id=f'__err:{key[1]}')]
        self.kids[key] = kids
        self.redraw_soon()

    def forget_kids(self, part_key):
        """the part's data changed: what was unfolded is read again when it is next shown"""
        for key in [k for k in self.kids if k[0] == part_key]:
            del self.kids[key]

    def unfold(self, node, level):
        """a folder opens in the next ring; a file shows its preview"""
        if node.get('kids'):
            self.expand(node, level)
        elif node.get('preview'):
            self.show_preview(node)

    def dwell_tick(self):
        if not self.dwell or not same(self.hover, self.dwell[0]):
            self.dwell, self.dwell_id = None, None
            self.area.queue_draw()
            return False
        if time.time() - self.dwell[2] >= DWELL:
            self.dwell_id = None
            self.unfold(self.dwell[0], self.dwell[1])
            return False
        self.area.queue_draw()
        return True

    def capped(self, part, items, cap, lv):
        """at most cap tiles; the rest never dropped silently: "N more" unfolds them"""
        items = list(items)
        if len(items) <= cap:
            return items
        path = self.path.get(part.key, [])
        parent = path[lv - 1] if lv > 0 else None
        rest = items[cap - 1:]
        where = node_key(parent) if parent else part.key
        return items[:cap - 1] + [tile(
            'lucide:ellipsis', f'{len(rest)} more', 'rest here: the others',
            parent and parent.get('act'), id=f'__more{lv}:{where}:{len(rest)}',
            kids=lambda r=rest: r)]

    def draw_tree(self, cr, cx, cy, rings, a0, a1, part):
        levels = self.tree_levels(part)
        path = self.path.get(part.key, [])
        start = max(0, len(levels) - 3)           # deeper than three: the tree moves inward
        parent_angle, parent_r = None, None
        for k, items in enumerate(levels[start:start + 3]):
            lv = start + k
            ri, ro = rings[k]
            rm = (ri + ro) / 2
            # names in the first ring only where icons repeat (a row of the same folder icon:
            # the notebooks); unique icons speak for themselves, their name shows on hover
            icons = [t.get('icon') for t in items]
            twins = {i for i in icons if icons.count(i) > 1}
            named = k > 0 or bool(twins) or any(t.get('label') for t in items)
            step = math.degrees((74 if k > 0 else 58 if named else 44) * self.icon_scale() * self.iu / rm)
            items = self.capped(part, items, max(2, int((a1 - a0 - 4) / step)), lv)
            n = max(1, len(items))
            s0, s1 = a0, a1
            if parent_angle is not None:
                w = min(a1 - a0 - 4, n * step)
                s0 = max(a0 + 2, min(a1 - 2 - w, parent_angle - w / 2))
                s1 = s0 + w
                self.draw_band(cr, cx, cy, ri, ro, s0, s1, parent_angle, parent_r)
            next_angle = None
            for j, t in enumerate(items):
                a = s0 + (s1 - s0) * (j + 0.5) / n
                x, y = cx + math.cos(math.radians(a)) * rm, cy + math.sin(math.radians(a)) * rm
                is_open = lv < len(path) and same(path[lv], t)
                if is_open:
                    next_angle = a
                self.draw_node(cr, x, y, t, k, lv, is_open, t.get('icon') in twins)
            parent_angle, parent_r = next_angle, rm

    def draw_band(self, cr, cx, cy, ri, ro, s0, s1, parent_angle, parent_r):
        """the band the children sit in, and a thin chromatic line from their parent"""
        cr.new_path()
        cr.arc(cx, cy, ro - 2, math.radians(s0 - 2), math.radians(s1 + 2))
        cr.arc_negative(cx, cy, ri + 2, math.radians(s1 + 2), math.radians(s0 - 2))
        cr.close_path()
        cr.set_source_rgba(0.03, 0.03, 0.05, 0.62)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.07)
        cr.set_line_width(1)
        cr.stroke()
        pa = math.radians(parent_angle)
        for col, dx in ((RED, -0.8), (CYAN, 0.8)):
            r0, r1 = parent_r + 26 * self.iu, ri + 4 * self.iu
            cr.move_to(cx + math.cos(pa) * r0 + dx, cy + math.sin(pa) * r0)
            cr.line_to(cx + math.cos(pa) * r1 + dx, cy + math.sin(pa) * r1)
            cr.set_source_rgba(*col, 0.35)
            cr.set_line_width(1)
            cr.stroke()

    def draw_node(self, cr, x, y, t, k, lv, is_open, twin):
        """one tile of a tree in ring k: lit when open or in use, greyed when 'dim'"""
        size = (30, 27, 25)[k] * self.icon_scale() * self.iu
        self.slots.append((x, y, size * 0.9, t, lv, None))
        hov = same(self.hover, t)
        lit = is_open or t.get('lit')
        if lit or hov:
            self.disc(cr, x, y, size * 0.85, CYAN, 0.16 if lit else 0.09)
            self.chroma_circle(cr, x, y, size * 0.85, alpha=0.8 if lit else 0.5)
        if t.get('busy'):                                   # under way: an arc going round
            self.draw_arc(cr, x, y, size, time.time() % 1.5 / 1.5 * 2 * math.pi, 1.6)
        elif self.dwell and same(self.dwell[0], t):         # the unfold timer
            f = min(1.0, (time.time() - self.dwell[2]) / DWELL)
            self.draw_arc(cr, x, y, size, -math.pi / 2, 2 * math.pi * f)
        pb = self.icon(t, size)
        if pb:
            paint(cr, pb, x, y - 3 * self.iu, 0.3 if t.get('dim') else 1.0)
        if t.get('kids'):              # a chevron: it unfolds (files show a preview instead)
            ch = self.lucide('chevron-right', 10 * self.iu, 0.4)
            if ch:
                paint(cr, ch, x + size * 0.55 + ch.get_width() / 2, y - size * 0.75 + ch.get_height() / 2)
        if k > 0 or is_open or hov or twin or t.get('label'):
            cut = 8 if k == 0 else 13          # short in the first ring, where they sit closest
            name = t['name'] if (is_open or hov) else \
                (t['name'][:cut] + '…' if len(t['name']) > cut + 1 else t['name'])
            if t.get('busy'):
                name = 'connecting…'
            self.text(cr, name[:22], x, y + size * 0.7 + 8 * self.iu, self.pt(8), bold=is_open or hov,
                      alpha=0.4 if t.get('dim') and not hov else 0.9, split=0.8 if is_open else 0)

    def draw_arc(self, cr, x, y, size, start, length):
        for col, dx in ((RED, -1), (CYAN, 1)):
            cr.new_path()
            cr.arc(x + dx, y, size * 0.85 + 5 * self.iu, start, start + length)
            cr.set_source_rgba(*col, 0.9)
            cr.set_line_width(2.2)
            cr.stroke()
