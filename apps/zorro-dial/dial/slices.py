"""The apps' slices: their bands, their names (right-click: rename; '+ slice': a new one), and
the apps floating in them."""
import hashlib
import math
import time

from . import config, groups, state


class Slices:
    def draw_slices(self, cr, cx, cy, rings, a0, a1):
        slices = self.conf['slices'][:6]
        self.labels = []                    # (x, y, slice, half width, half height): right-click a name to rename it
        span = (a1 - a0) / len(slices)
        for i, s in enumerate(slices):
            start = a0 + i * span
            self.slice_band(cr, cx, cy, rings, start, span)
            am = math.radians(start + span / 2)
            r_lab = rings[-1][1] + 20 * self.u
            self.slice_name(cr, i, s['name'], cx + math.cos(am) * r_lab, cy + math.sin(am) * r_lab)
            self.slice_apps(cr, cx, cy, i, start)
        self.add_label = None
        if len(slices) < 6:                 # '+': a new slice (up to six)
            am = math.radians(a1 - 3)
            r_lab = rings[-1][1] + 46 * self.u
            ax, ay = cx + math.cos(am) * r_lab, cy + math.sin(am) * r_lab
            ax, ay = self.inside(cr, '+ slice', ax, ay, self.pt(8), bold=False)
            self.add_label = (ax, ay)
            self.text(cr, '+ slice', ax, ay, self.pt(8), bold=False, alpha=0.55, split=0)

    def slice_band(self, cr, cx, cy, rings, start, span):
        for ri, ro in rings:
            b0, b1 = math.radians(start + 0.6), math.radians(start + span - 0.6)
            cr.new_path()
            cr.arc(cx, cy, ro - 2, b0, b1)
            cr.arc_negative(cx, cy, ri + 2, b1, b0)
            cr.close_path()
            cr.set_source_rgba(0.03, 0.03, 0.05, 0.55)
            cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, 0.07)
            cr.set_line_width(1)
            cr.stroke()

    def slice_name(self, cr, i, name, lx, ly):
        if self.renaming == i:          # being renamed: what you type, with a caret
            size = self.pt(10)
            shown = self.rename_text or ' '
            lx, ly = self.inside(cr, shown + '▏', lx, ly, size)
            ly = min(ly, self.geo.height - 30 * self.u)     # room for the line underneath
            w, _h = self.text_ext(cr, shown + '▏', size)
            self.text(cr, shown + ('▏' if int(time.time() * 2) % 2 else ' '), lx, ly, size, split=1.0)
            hx, hy = self.inside(cr, 'Enter: keep · Esc: back', lx, ly + 18 * self.u, self.pt(7), bold=False)
            self.text(cr, 'Enter: keep · Esc: back', hx, hy, self.pt(7), bold=False, alpha=0.5, split=0)
        else:
            size = self.pt(9)
            lx, ly = self.inside(cr, name.upper(), lx, ly, size)
            w, _h = self.text_ext(cr, name.upper(), size)
            self.text(cr, name.upper(), lx, ly, size, split=1.4)
        # right-click there to rename: the name's box, at least as wide as before
        self.labels.append((lx, ly, i, max(70 * self.u, w / 2 + 8 * self.u), 16 * self.u))

    def slice_apps(self, cr, cx, cy, i, start):
        """the slice's apps at their spots in the cloud, each drifting slowly on its own"""
        group = list(self.groups[i])
        spots = self.cloud[i] if i < len(self.cloud) else []
        if len(group) > len(spots):          # never drop apps silently: "+N" shows them all
            extra = len(group) - len(spots) + 1
            group = group[:max(0, len(spots) - 1)] + [{'id': f'__more__{i}', 'name': f'{extra} more',
                                                       'icon': '', 'more': i, 'extra': extra}]
        now = time.monotonic()
        amp, period = state.CLOUD_FLOAT
        for j, (a, (r, ang, size)) in enumerate(zip(group, spots)):
            am = math.radians(start + ang)
            ph = int(hashlib.md5(str(a.get('id')).encode()).hexdigest()[:6], 16) / 0xffffff * 2 * math.pi
            w = 2 * math.pi / (period * (0.8 + 0.4 * ph / (2 * math.pi)))
            dx = math.cos(now * w + ph) * size * amp
            dy = math.sin(now * w * 0.7 + ph * 1.7) * size * amp
            self.draw_app(cr, cx + math.cos(am) * r + dx, cy + math.sin(am) * r + dy, size, a, (i, j))

    def label_at(self, x, y):
        return next((i for lx, ly, i, hw, hh in self.labels
                     if abs(x - lx) < hw and abs(y - ly) < hh), None)

    def start_rename(self, i):
        self.renaming, self.rename_text = i, self.conf['slices'][i]['name']
        self.area.queue_draw()

    def add_slice(self):
        self.conf['slices'] = list(self.conf['slices']) + [{'name': f'Slice {len(self.conf["slices"]) + 1}',
                                                            'categories': []}]
        self.save_slices()
        self.start_rename(len(self.conf['slices']) - 1)
        self.rename_text = ''               # type its name right away (Enter on empty: 'Slice N')

    def finish_rename(self, keep):
        i, new = self.renaming, self.rename_text.strip()[:20]
        self.renaming = None
        if keep and new and i is not None:
            old = self.conf['slices'][i]['name']
            if new != old and new not in [x['name'] for x in self.conf['slices']]:
                self.conf['slices'][i] = {**self.conf['slices'][i], 'name': new}
                order = dict(self.conf.get('order', {}))       # its apps and their order go along
                if old in order:
                    order[new] = order.pop(old)
                self.conf['order'] = order
                self.conf['assign'] = {a: (new if v == old else v) for a, v in self.conf['assign'].items()}
                self.save_slices()
        self.area.queue_draw()

    def save_slices(self):
        config.save_keys(slices=self.conf['slices'], order=self.conf.get('order', {}),
                         assign=self.conf.get('assign', {}))
        self.groups, self.settings = groups.arrange(self.conf, self.all, self.usage)

    def matches(self):
        return groups.matches(self.all, self.usage, self.filter)
