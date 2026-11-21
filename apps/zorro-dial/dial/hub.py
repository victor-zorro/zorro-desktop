"""The hub: the middle circle in six parts, and its centre (the time, a preview, the player)."""
import math
import time

from . import state
from .look import CYAN, RED, cairo, paint
from .parts import MODES

MUSIC_KEYS = (('skip-back', 'prev', -42), ('play', 'toggle', -14), ('square', 'stop', 14),
              ('skip-forward', 'next', 42))      # x offsets in the unit u
STATUS_FITS = 22                        # letters that fit on one small line under the date


class Hub:
    def hub_at(self, x, y):
        """which part of the hub is under (x, y): a part's key, 'centre', or None"""
        cx, cy, hub, *_ = self.fan()
        dx, dy = x - cx, y - cy
        d2 = dx * dx + dy * dy
        if d2 > (hub - 4) ** 2:
            return None
        if d2 < (hub * 0.5) ** 2:
            return 'centre'
        ang = (math.degrees(math.atan2(dy, dx)) + 120) % 360      # part 0 is centred on top
        return MODES[int(ang // 60) % len(MODES)][0]

    def draw_hub(self, cr, cx, cy, hub):
        """icons on the rim, the kept part lit; the centre shows the hovered app or tile, the
        hovered part's preview, the kept part's, or the time"""
        self.disc(cr, cx, cy, hub - 4, (0, 0, 0), 0.85)
        self.chroma_circle(cr, cx, cy, hub - 4)
        for i, (key, _title, icon) in enumerate(MODES):
            self.hub_part(cr, cx, cy, hub, -120 + i * 60, icon, key == self.mode, key == self.hub_hover)
        self.hub_centre(cr, cx, cy, hub / 120)

    def hub_part(self, cr, cx, cy, hub, a0, icon, lit, hov):
        if lit or hov:
            cr.new_path()
            cr.move_to(cx, cy)
            cr.arc(cx, cy, hub - 6, math.radians(a0 + 1), math.radians(a0 + 59))
            cr.close_path()
            g = cairo.RadialGradient(cx, cy, hub * 0.45, cx, cy, hub)
            g.add_color_stop_rgba(0, *CYAN, 0)
            g.add_color_stop_rgba(1, *CYAN, 0.15 if lit else 0.07)
            cr.set_source(g)
            cr.fill()
        if lit:
            for col, dr in ((RED, -1.2), (CYAN, 1.2)):
                cr.new_path()
                cr.arc(cx, cy, hub - 4 + dr, math.radians(a0 + 4), math.radians(a0 + 56))
                cr.set_source_rgba(*col, 0.9)
                cr.set_line_width(2.2)
                cr.stroke()
        ca, sa = math.cos(math.radians(a0)), math.sin(math.radians(a0))
        cr.move_to(cx + ca * hub * 0.74, cy + sa * hub * 0.74)
        cr.line_to(cx + ca * (hub - 6), cy + sa * (hub - 6))
        cr.set_source_rgba(1, 1, 1, 0.1)
        cr.set_line_width(1)
        cr.stroke()
        am = math.radians(a0 + 30)
        pb = self.lucide(icon, max(14, int(hub / 6.5)), 0.95 if (lit or hov) else 0.4)
        if pb:
            paint(cr, pb, cx + math.cos(am) * hub * 0.83, cy + math.sin(am) * hub * 0.83)

    def hub_centre(self, cr, cx, cy, k):
        if self.hover:                                  # an app or a tile under the mouse
            self.text_block(cr, cx, cy, [(self.hover['name'][:24], 12 * k, True, 1),
                                         (self.hover.get('sub', ''), 9 * k, False, 0.8)])
            return
        show = self.hub_hover if self.hub_hover in self.parts else (
            self.mode if self.mode != 'apps' and self.hub_hover != 'apps' else None)
        if not show or self.filter:
            self.hub_clock(cr, cx, cy, k)
            return
        part = self.parts[show]
        at_centre = 0.9 if self.hub_hover == 'centre' else 0.5
        tree_path = self.path.get(show) if show == self.mode else None
        if tree_path:
            names = [n['name'] for n in tree_path]
            crumbs = ' › '.join(names[-3:])
            self.text_block(cr, cx, cy, [(part.title.upper(), 8 * k, True, 0.55),
                                         (names[-1][:20], 13 * k, True, 1), (crumbs[-30:], 8 * k, False, 0.7),
                                         ('click: open · Esc: back', 8 * k, False, at_centre)])
            return
        title, big, lines = part.preview()
        size = 28 if len(big) <= 5 else 15 if len(big) <= 11 else 11
        block = [(title, 8 * k, True, 0.55), (big, size * k, True, 1)]
        block += [(ln[:26], 9 * k, False, 0.8) for ln in lines[:2] if ln]
        c = part.centre() if show == self.mode else None
        if c:
            block.append((f'click: {c[0]}', 8 * k, False, at_centre))
        self.text_block(cr, cx, cy, block)

    def hub_clock(self, cr, cx, cy, k):
        """the time; under it what you type or the open slice's name, else the date with the
        connection and the battery, small"""
        block = [(time.strftime('%H:%M'), max(14, 26 * k), True, 1)]
        if self.filter:
            label = f'“{self.filter}”' if len(self.filter) <= 20 else f'“…{self.filter[-19:]}”'
        elif self.expanded == 'gear':
            label = 'Settings'
        elif self.expanded is not None:
            label = self.conf['slices'][self.expanded]['name']
        else:
            label = time.strftime('%A %-d %B')
        block.append((label[:23], max(8, 10 * k), False, 0.9))
        if not self.filter and self.expanded is None:
            found = [x for x in (state.STATUS['net'], state.STATUS['power']) if x]
            one = ' · '.join(found)
            for line in ([one] if len(one) <= STATUS_FITS else found):
                block.append((line[:STATUS_FITS], max(7, 8 * k), False, 0.55))
        self.text_block(cr, cx, cy, block)

    def music_keys(self, cr, cx, cy, hub):
        """previous / play-pause / stop / next in the centre of the circle"""
        np = self.parts['music'].np
        y = cy + hub * 0.33
        u = self.u
        for icon, what, dx in MUSIC_KEYS:
            if what == 'toggle' and np and np.get('playing'):
                icon = 'pause'
            hov = self.hub_key == what
            if hov:
                self.disc(cr, cx + dx * u, y, 12 * u, CYAN, 0.18)
            pb = self.lucide(icon, 16 * u, 0.95 if hov else 0.6)
            if pb:
                paint(cr, pb, cx + dx * u, y)

    def music_key_at(self, x, y):
        if self.mode != 'music':
            return None
        cx, cy, hub, *_ = self.fan()
        return next((w for _, w, dx in MUSIC_KEYS
                     if (x - cx - dx * self.u) ** 2 + (y - cy - hub * 0.33) ** 2 <= (13 * self.u) ** 2), None)

    def text_block(self, cr, cx, cy, block):
        heights = [size * 1.8 for _, size, _, _ in block]
        if self.mode == 'music' and not self.filter:
            cy -= 14 * self.u           # room for the player buttons underneath
        y = cy - sum(heights) / 2
        for (s, size, bold, a), h in zip(block, heights):
            self.text(cr, s, cx, y + h / 2, max(7, size), bold=bold, alpha=a, split=1.6 if bold else 0.8)
            y += h
