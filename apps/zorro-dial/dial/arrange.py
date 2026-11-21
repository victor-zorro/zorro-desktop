"""Rearranging the apps: drag to another place or onto the bin, or hold one for its menu."""
import math

from . import config
from .look import BG, CYAN, RED, GLib, paint


class Arrange:
    def slice_names(self):
        return [s['name'] for s in self.conf['slices'][:6]]

    def slice_at(self, x, y):
        """index of the slice under (x, y), or None outside the fan"""
        cx, cy, hub, a0, a1, rings = self.fan()
        dx, dy = x - cx, y - cy
        if not hub ** 2 <= dx * dx + dy * dy <= (rings[-1][1] + 30 * self.u) ** 2:
            return None
        rel = (math.degrees(math.atan2(dy, dx)) - a0) % 360
        n = len(self.conf['slices'][:6])
        return min(n - 1, int(rel / ((a1 - a0) / n))) if rel <= a1 - a0 else None

    # -- the bin: drop an app on it and it leaves the launcher (typing still finds it)
    def bin_at(self):
        """the bin sits on the Dialer's clock while you drag: close to every app"""
        return self.fan()[:2]

    def bin_r(self):
        return max(48 * self.u, self.fan()[2] * 0.75)

    def over_bin(self, x, y):
        bx, by = self.bin_at()
        return (x - bx) ** 2 + (y - by) ** 2 <= self.bin_r() ** 2

    def draw_bin(self, cr, x, y):
        """while an app is dragged: the clock becomes a bin"""
        bx, by = self.bin_at()
        u, r = self.u, self.bin_r()
        hot = self.over_bin(x, y)
        self.disc(cr, bx, by, r, BG, 0.95)          # covers the clock
        self.disc(cr, bx, by, r, RED, 0.45 if hot else 0.0)
        self.chroma_circle(cr, bx, by, r, alpha=0.9 if hot else 0.5)
        pb = self.lucide('trash-2', 34 * u, 0.95 if hot else 0.7)
        if pb:
            paint(cr, pb, bx, by - 8 * u)
        say = 'out of the launcher' if hot else 'drop here to remove'
        self.text(cr, say, bx, by + 26 * u, self.pt(8), bold=hot, alpha=0.95 if hot else 0.6, split=0)

    def hide_app(self, a):
        """the app leaves the slices (Zorro app → Desktop → Dialer → Apps brings it back)"""
        for g in self.groups:
            if a in g:
                g.remove(a)
        if a in self.settings:              # one of the apps behind the gear
            self.settings.remove(a)
        hide = list(self.conf.get('hide', []))
        if a['id'] not in hide:
            hide.append(a['id'])
        self.conf['hide'] = hide
        config.save_keys(hide=hide)

    def drop(self, a, x, y):
        """put the dragged app before the app it was dropped on, or at the end of the slice"""
        slot = self.hit(x, y, slot=True)
        if slot and slot[4] is not None:
            gi, pos = slot[4], slot[5]
        else:
            gi = self.slice_at(x, y)
            if gi is None:
                return                      # dropped outside: nothing changes
            pos = len(self.groups[gi])
        src = next((i for i, g in enumerate(self.groups) if a in g), None)
        if src is None:
            return
        old = self.groups[src].index(a)
        self.groups[src].remove(a)
        if src == gi and old < pos:
            pos -= 1
        self.groups[gi].insert(pos, a)
        self.save_moved(a, src, gi)

    def move_to(self, a, gi):
        """the app to the end of another slice (like dragging it there)"""
        src = next((i for i, g in enumerate(self.groups) if a in g), None)
        if src is None or src == gi:
            return
        self.groups[src].remove(a)
        self.groups[gi].append(a)
        self.save_moved(a, src, gi)

    def save_moved(self, a, src, gi):
        names = self.slice_names()
        order = dict(self.conf.get('order', {}))
        for i in {src, gi}:
            order[names[i]] = [b['id'] for b in self.groups[i]]
        assign = {a['id']: names[gi]} if gi != src else {}
        self.conf['order'] = order
        self.conf['assign'].update(assign)
        config.save_arrangement(order, assign)

    # -- hold an app still for a moment: a small menu (no right-click needed)
    def hold_start(self, press):
        self.hold_stop()
        self.hold_id = GLib.timeout_add(650, self.on_hold, press)

    def hold_stop(self):
        if self.hold_id:
            GLib.source_remove(self.hold_id)
            self.hold_id = None

    def on_hold(self, press):
        self.hold_id = None
        if self.closed or self.press is not press or self.drag:
            return False
        self.press = None                   # the release that follows doesn't start it
        a, x, y = press
        here = next((i for i, g in enumerate(self.groups) if a in g), None)
        rows = [('Remove from the launcher', lambda: self.hide_app(a))]
        rows += [(f'Move to {n}', lambda gi=gi: self.move_to(a, gi)) for gi, n in enumerate(self.slice_names())
                 if here is not None and gi != here and gi < len(self.groups)]
        rows.append(('Cancel', lambda: None))
        self.menu = {'rows': rows, 'x': x, 'y': y, 'rects': [], 'hover': None, 'name': a.get('name', '')}
        self.area.queue_draw()
        return False

    def draw_menu(self, cr):
        m = self.menu
        u, size = self.u, self.pt(10)
        exts = [self.text_ext(cr, lab, size, False) for lab, _ in m['rows']]
        tw, _th = self.text_ext(cr, m['name'], size, True)
        w = max([e[0] for e in exts] + [tw]) + 40 * u
        rh = 34 * u
        h = rh * (len(m['rows']) + 1) + 8 * u
        x = min(max(m['x'] + 24 * u, 12 * u), self.geo.width - w - 12 * u)
        y = min(max(m['y'] - rh, 12 * u), self.geo.height - h - 12 * u)
        cr.new_path()
        cr.rectangle(x, y, w, h)
        cr.set_source_rgba(*BG, 0.94)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.18)
        cr.set_line_width(1)
        cr.stroke()
        self.text(cr, m['name'], x + w / 2, y + rh / 2 + 4 * u, size, bold=True, alpha=0.9, split=0.8)
        m['rects'] = []
        for k, (lab, _fn) in enumerate(m['rows']):
            ry = y + rh * (k + 1) + 4 * u
            m['rects'].append((x, ry, w, rh))
            if m['hover'] == k:
                cr.rectangle(x + 1, ry, w - 2, rh)
                cr.set_source_rgba(*(RED if k == 0 else CYAN), 0.18)
                cr.fill()
            self.text(cr, lab, x + w / 2, ry + rh / 2, size, bold=False,
                      alpha=0.95 if m['hover'] == k else 0.7, split=0)

    def menu_at(self, x, y):
        for k, (rx, ry, rw, rh) in enumerate((self.menu or {}).get('rects', [])):
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return k
        return None
