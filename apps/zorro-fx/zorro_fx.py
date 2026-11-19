"""zorro_fx: the lock-screen look for small on-screen overlays (volume/brightness indicator,
screenshot toolbar): a dark box with moving particles, optionally spilling out of the box.

Used by zorro-thinkpad (indicator + the Zorro app), zorro-shot and zorro-orb (they import
it from ../zorro-fx next to their own folder and fall back to a plain dark box without
it). Settings live in ~/.config/zorro-fx/config.json, one set per "profile":
  overlay  the indicator and the screenshot bar
  orb      the round info area on the desktop
  app      the Zorro app window itself
edited in the Zorro app; running windows pick up changes on their next frame.
"""
import json
import math
import os
import random
import time
from pathlib import Path

try:                    # fast path: all particles at once (python3-numpy)
    import numpy as np
except ImportError:     # plain Python: fine for a few hundred particles
    np = None

CONF = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'zorro-fx' / 'config.json'

DEFAULTS = {
    'pattern': 'float',         # see PATTERNS
    'colour': 'snow',           # see COLOURS
    'amount': 6.0,              # particles per 1000 px² of the box (0-60)
    'speed': 1.6,               # 1 = calm
    'size': 1.0,                # particle size factor
    'glow': True,               # soft halo around the nearest particles
    'spill': 0,                 # px the particles drift out of the box onto the screen
    'opacity': 0.0,             # box background: none, only particles (1 = solid black)
    'particle_opacity': 1.0,    # particles
    'bar_opacity': 1.0,         # level bar of the indicator
    'osd_seconds': 1.5,         # how long the indicator stays
}
PROFILES = {
    'overlay': DEFAULTS,
    'orb': dict(DEFAULTS, amount=5.0, speed=1.0),
    'app': dict(DEFAULTS, enabled=False, amount=2.0, speed=0.8, opacity=1.0,
                particle_opacity=0.7, glow=False),
}
PATTERNS = {
    'float': 'Floating around',
    'flock': 'Flock (follows the mouse)',
    'fall': 'Falling (marine snow)',
    'rise': 'Rising (bubbles)',
    'swirl': 'Swirling around the middle',
    'twinkle': 'Twinkling stars',
}
from zorro_style import CYAN, GREY, RED, WHITE  # noqa: E402 - the one palette (zorro_style.py)
COLOURS = {                 # name: (label, colours picked at random per particle)
    'snow': ('Lock screen grey', [GREY]),
    'white': ('White', [WHITE]),
    'cyan': ('Cyan', [CYAN]),
    'red': ('Red', [RED]),
    'mixed': ('Grey with a few cyan and red', [GREY] * 6 + [CYAN, RED]),
}
MAX_PARTICLES = 3000 if np is not None else 1200

_cache = {'mtime': -1, 'file': None}
_preview = {}                   # profile -> settings being edited (the app's live preview)


def _read_file():
    try:
        mtime = CONF.stat().st_mtime
    except OSError:
        mtime = None
    if _cache['file'] is None or mtime != _cache['mtime']:
        try:
            data = json.loads(CONF.read_text())
        except (OSError, ValueError):
            data = {}
        if 'overlay' not in data and any(k in DEFAULTS for k in data):   # old flat file
            data = {'overlay': {k: v for k, v in data.items() if k in DEFAULTS},
                    'app': {'enabled': bool(data.get('app_bg'))}}
        _cache.update(mtime=mtime, file=data)
    return _cache['file']


def settings(profile='overlay'):
    """current settings of a profile; re-reads the file only when it changed"""
    if profile in _preview:
        return _preview[profile]
    base = PROFILES.get(profile, DEFAULTS)
    s = dict(base)
    s.update({k: v for k, v in _read_file().get(profile, {}).items() if k in base})
    return s


def preview(profile, s):
    """show unsaved settings in this process right away (the app's sliders)"""
    _preview[profile] = dict(s)


def save(s, profile='overlay'):
    data = dict(_read_file())
    base = PROFILES.get(profile, DEFAULTS)
    data[profile] = {k: s[k] for k in base if k in s}
    CONF.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONF.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.replace(CONF)
    _cache['file'] = None


def pointer_in(widget):
    """mouse position relative to the widget, or None"""
    from gi.repository import Gdk
    gw = widget.get_window()
    if not gw:
        return None
    try:
        _, px, py = Gdk.Display.get_default().get_default_seat().get_pointer().get_position()[0:3]
    except (AttributeError, TypeError):
        return None
    _, ox, oy = gw.get_origin()
    a = widget.get_allocation()
    return px - ox - (a.x if not widget.get_has_window() else 0), \
        py - oy - (a.y if not widget.get_has_window() else 0)


class Swarm:
    """all particles as numpy arrays: moving and fading thousands of them costs a few
    milliseconds per frame instead of tens"""
    FIELDS = ('x', 'y', 'z', 'a', 'r', 'ph', 'vx', 'vy', 'ox', 'oy')

    def __init__(self):
        self.n = 0
        for f in self.FIELDS:
            setattr(self, f, np.zeros(0))
        self.ci = np.zeros(0, dtype=np.int64)
        self.rng = np.random.default_rng()

    def resize(self, n, ncol, W, H):
        if n < self.n:
            for f in self.FIELDS + ('ci',):
                setattr(self, f, getattr(self, f)[:n])
        elif n > self.n:
            k, rnd = n - self.n, self.rng.random
            new = {'x': rnd(k) * W, 'y': rnd(k) * H, 'z': rnd(k) ** 1.4, 'a': rnd(k) * 6.283,
                   'r': 0.25 + 0.75 * rnd(k) ** 0.7, 'ph': rnd(k) * 6.283, 'vx': np.zeros(k),
                   'vy': np.zeros(k), 'ox': rnd(k) * 2 - 1, 'oy': rnd(k) * 2 - 1}
            for f in self.FIELDS:
                setattr(self, f, np.concatenate([getattr(self, f), new[f]]))
            self.ci = np.concatenate([self.ci, self.rng.integers(0, ncol, k)])
        self.n = n

    def recolour(self, ncol):
        self.ci = self.rng.integers(0, ncol, self.n)

    def move(self, s, W, H, dt, t, pointer):
        pat, sp = s['pattern'], s['speed']
        v = (5 + 16 * self.z) * sp
        if pat == 'flock':
            if pointer and -40 <= pointer[0] <= W + 40 and -40 <= pointer[1] <= H + 40:
                tx, ty = pointer
            else:
                tx = W / 2 + math.cos(t * 0.45 * sp) * W * 0.38
                ty = H / 2 + math.sin(t * 0.7 * sp) * H * 0.35
            gx = tx + self.ox * (12 + W * 0.08) + np.sin(t * 1.3 + self.ph) * 6
            gy = ty + self.oy * (6 + H * 0.18) + np.cos(t * 1.1 + self.ph) * 4
            damp = math.exp(-2.2 * dt)
            self.vx = (self.vx + (gx - self.x) * 3.0 * sp * dt) * damp
            self.vy = (self.vy + (gy - self.y) * 3.0 * sp * dt) * damp
            vmax = 90 * sp * (0.5 + self.z)
            vv = np.hypot(self.vx, self.vy)
            k = np.where(vv > vmax, vmax / np.maximum(vv, 1e-9), 1.0)
            self.vx *= k
            self.vy *= k
            self.x += self.vx * dt
            self.y += self.vy * dt
            return
        if pat == 'swirl':
            rad = self.r * min(W, H) * 0.5 + 4
            self.a += v * dt / rad * np.where(self.ph < 3.14, 1.0, 0.7)
            wob = 1 + 0.08 * np.sin(t * 0.5 + self.ph)
            self.x = W / 2 + np.cos(self.a) * self.r * W * 0.5 * wob
            self.y = H / 2 + np.sin(self.a) * self.r * H * 0.5 * wob
            return
        if pat in ('fall', 'rise'):
            self.y += (v if pat == 'fall' else -v) * dt
            self.x += np.sin(t * 0.8 + self.ph) * 0.35 * v * dt
        else:                                                  # float / twinkle: wander
            if pat == 'twinkle':
                v = v * 0.25
            self.a += (self.rng.random(self.n) - 0.5) * 4 * dt
            self.x += np.cos(self.a) * v * dt
            self.y += np.sin(self.a) * v * dt
        self.x %= W
        self.y = (self.y + 3) % (H + 6) - 3

    def alphas(self, s, W, H, t, spill):
        alpha = (0.22 + 0.7 * self.z) * s['particle_opacity']
        if spill:                                              # the soft, waving cloud
            dx, dy = (self.x - W / 2) / (W / 2), (self.y - H / 2) / (H / 2)
            e, th = np.hypot(dx, dy), np.arctan2(dy, dx)
            edge = (0.92 + 0.07 * np.sin(3 * th + t * 0.35) + 0.05 * np.sin(5 * th - t * 0.6 + 1.3)
                    + 0.03 * np.sin(8 * th + t * 0.9 + 2.1))
            f = np.clip((edge - e) / 0.45, 0, 1)
            alpha = alpha * f * f * (3 - 2 * f)
        if s['pattern'] == 'twinkle':
            alpha = alpha * (0.5 + 0.5 * np.sin(t * (1.2 + 2.5 * self.z) + self.ph))
        return alpha

    def paint(self, cr, s, W, H, t, spill, colours):
        """grouped by colour and brightness, one cairo fill per group. (Painting one big
        image per frame looked cheaper, but X then uploads the whole image every frame.)"""
        alpha = self.alphas(s, W, H, t, spill)
        keep = alpha > 0.01
        if not keep.any():
            return
        x, y, z, ci = self.x[keep], self.y[keep], self.z[keep], self.ci[keep]
        q = np.minimum(11, (alpha[keep] * 12).astype(np.int64))
        rad = (0.6 + 1.3 * z) * s['size']
        key = ci * 12 + q
        order = np.argsort(key, kind='stable')
        key, x, y, rad, z = key[order], x[order], y[order], rad[order], z[order]
        starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
        ends = np.r_[starts[1:], len(key)]
        glow = s['glow']
        for a0, a1 in zip(starts.tolist(), ends.tolist()):
            k = int(key[a0])
            col, qa = colours[(k // 12) % len(colours)], ((k % 12) + 0.5) / 12
            xs, ys, rs = (x[a0:a1] - rad[a0:a1]).tolist(), (y[a0:a1] - rad[a0:a1]).tolist(), \
                (2 * rad[a0:a1]).tolist()
            if glow:
                cr.set_source_rgba(*col, qa * 0.18)
                for xx, yy, dd, zz in zip(xs, ys, rs, z[a0:a1].tolist()):
                    if zz > 0.65:
                        cr.rectangle(xx - dd, yy - dd, dd * 3, dd * 3)
                cr.fill()
            cr.set_source_rgba(*col, qa)
            for xx, yy, dd in zip(xs, ys, rs):
                cr.rectangle(xx, yy, dd, dd)
            cr.fill()


class Snow:
    """Paints the overlay background under a widget's children and animates it while the
    widget is on screen.

    inner: the box itself (the widget is then a margin around it, as wide as the 'spill'
    setting, where particles fade out); None = the widget is the box, no spill.
    backdrop: a GdkPixbuf painted first - a still image of what is behind the overlay, so
    see-through and spill also work without a compositor."""

    def __init__(self, widget, radius=12, fps=30, inner=None, enabled=None,
                 max_parts=MAX_PARTICLES, max_spill=None, profile='overlay'):
        self.widget, self.radius, self.fps, self.inner = widget, radius, fps, inner
        self.enabled, self.max_parts, self.max_spill = enabled, max_parts, max_spill
        self.profile = profile
        self.was_on = None
        self.parts, self.timer = [], None
        self.swarm = Swarm() if np is not None else None
        self.t0 = self.last = time.monotonic()
        self.backdrop = None
        self.backdrop_at = (0, 0)       # where the backdrop image goes in the widget
        self.spill = None
        self.colour = None
        widget.set_app_paintable(True)
        widget.connect('draw', self.draw)
        widget.connect('map', lambda w: self.start())
        widget.connect('unmap', lambda w: self.stop())
        self.update_spill()

    def start(self):
        from gi.repository import GLib
        if not self.timer:
            self.last = time.monotonic()
            on = self.enabled is None or self.enabled()
            self.was_on = on
            # switched off: only look twice a second whether it got switched on again
            self.timer = GLib.timeout_add(1000 // self.fps if on else 500, self.tick)

    def stop(self):
        from gi.repository import GLib
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None

    def set_fps(self, fps):
        """a new pace; 0 holds the particles still (e.g. while the window is in the back)"""
        self.stop()
        if fps > 0:
            self.fps = fps
            if self.widget.get_mapped():
                self.start()

    def tick(self):
        from gi.repository import GLib
        on = self.enabled is None or self.enabled()
        if on != self.was_on:                       # switched: redraw, change the pace
            self.widget.queue_draw()
            self.timer = None
            GLib.idle_add(lambda: self.start() and False)
            return False
        if on:
            self.update_spill()
            self.widget.queue_draw()
        return True

    def update_spill(self):
        if self.inner is None:
            return
        sp = int(settings(self.profile)['spill'])
        if self.max_spill is not None:
            sp = min(sp, self.max_spill)
        if sp != self.spill:
            self.spill = sp
            for side in ('top', 'bottom', 'start', 'end'):
                getattr(self.inner, f'set_margin_{side}')(sp)

    def box_rect(self, W, H):
        if self.inner is None:
            return 0, 0, W, H
        a, b = self.widget.get_allocation(), self.inner.get_allocation()
        return b.x - a.x, b.y - a.y, b.width, b.height

    @staticmethod
    def new_particle(colours, W, H):
        rnd = random.random
        return {'x': rnd() * W, 'y': rnd() * H, 'z': rnd() ** 1.4, 'a': rnd() * 6.283,
                'r': 0.25 + 0.75 * rnd() ** 0.7, 'ph': rnd() * 6.283, 'vx': 0.0, 'vy': 0.0,
                'ox': rnd() * 2 - 1, 'oy': rnd() * 2 - 1, 'c': random.choice(colours)}

    def move(self, s, W, H, dt, t):
        pat, sp = s['pattern'], s['speed']
        sin, cos = math.sin, math.cos
        if pat == 'flock':
            # the flock chases the mouse while it is over the area, else a wandering point
            m = pointer_in(self.widget)
            if m and -40 <= m[0] <= W + 40 and -40 <= m[1] <= H + 40:
                tx, ty = m
            else:
                tx = W / 2 + cos(t * 0.45 * sp) * W * 0.38
                ty = H / 2 + sin(t * 0.7 * sp) * H * 0.35
            spread_x, spread_y = 12 + W * 0.08, 6 + H * 0.18
            pull = 3.0 * sp
            damp = math.exp(-2.2 * dt)
        for p in self.parts:
            v = (5 + 16 * p['z']) * sp                         # px per second
            if pat == 'flock':
                # each bird keeps its own spot in the swarm around the target
                gx = tx + p['ox'] * spread_x + sin(t * 1.3 + p['ph']) * 6
                gy = ty + p['oy'] * spread_y + cos(t * 1.1 + p['ph']) * 4
                p['vx'] = (p['vx'] + (gx - p['x']) * pull * dt) * damp
                p['vy'] = (p['vy'] + (gy - p['y']) * pull * dt) * damp
                vmax = 90 * sp * (0.5 + p['z'])
                vv = math.hypot(p['vx'], p['vy'])
                if vv > vmax:
                    p['vx'], p['vy'] = p['vx'] * vmax / vv, p['vy'] * vmax / vv
                p['x'] += p['vx'] * dt
                p['y'] += p['vy'] * dt
                continue
            if pat == 'fall' or pat == 'rise':
                p['y'] += (v if pat == 'fall' else -v) * dt
                p['x'] += sin(t * 0.8 + p['ph']) * 0.35 * v * dt
            elif pat == 'swirl':
                rad = p['r'] * min(W, H) * 0.5 + 4
                p['a'] += v * dt / rad * (1 if p['ph'] < 3.14 else 0.7)
                wob = 1 + 0.08 * sin(t * 0.5 + p['ph'])
                p['x'] = W / 2 + cos(p['a']) * p['r'] * W * 0.5 * wob
                p['y'] = H / 2 + sin(p['a']) * p['r'] * H * 0.5 * wob
                continue
            else:                                               # float / twinkle: wander
                if pat == 'twinkle':
                    v *= 0.25
                p['a'] += (random.random() - 0.5) * 4 * dt
                p['x'] += cos(p['a']) * v * dt
                p['y'] += sin(p['a']) * v * dt
            p['x'] %= W
            p['y'] = (p['y'] + 3) % (H + 6) - 3

    @staticmethod
    def organic(x, y, W, H, t):
        """how visible a particle is in the spill area: 1 inside a soft blob around the box,
        fading to 0 at its edge. The edge is an ellipse with slow waves, so the cloud has
        an organic, breathing outline instead of a rectangle."""
        dx, dy = (x - W / 2) / (W / 2), (y - H / 2) / (H / 2)
        e = math.hypot(dx, dy)                  # 0 centre .. 1 at the ellipse
        th = math.atan2(dy, dx)
        edge = 0.92 + 0.07 * math.sin(3 * th + t * 0.35) + 0.05 * math.sin(5 * th - t * 0.6 + 1.3) \
            + 0.03 * math.sin(8 * th + t * 0.9 + 2.1)
        f = (edge - e) / 0.45                   # soft fade band
        if f <= 0:
            return 0.0
        return 1.0 if f >= 1 else f * f * (3 - 2 * f)

    def outline(self, cr, x, y, w, h):
        r = min(self.radius, h / 2)
        if r:
            cr.new_sub_path()
            for cx, cy, a0 in ((x + w - r, y + r, -math.pi / 2), (x + w - r, y + h - r, 0),
                               (x + r, y + h - r, math.pi / 2), (x + r, y + r, math.pi)):
                cr.arc(cx, cy, r, a0, a0 + math.pi / 2)
            cr.close_path()
        else:
            cr.rectangle(x, y, w, h)

    def draw(self, w, cr):
        if self.enabled is not None and not self.enabled():
            return False                # switched off: the normal theme background
        s = settings(self.profile)
        a = w.get_allocation()
        W, H = max(1, a.width), max(1, a.height)
        bx, by, bw, bh = self.box_rect(W, H)
        spill = self.spill if self.inner is not None else 0
        now = time.monotonic()
        dt, self.last = min(0.1, now - self.last), now
        t = now - self.t0

        colours = COLOURS.get(s['colour'], COLOURS['snow'])[1]
        # density is per box area; the spill margin gets a share that thins out outwards
        n = bw * bh / 1000 * max(0.0, s['amount'])
        if spill:
            n *= 1 + 0.5 * ((W * H) / max(1, bw * bh) - 1)
        n = min(self.max_parts, int(n))
        if self.swarm is not None:                            # numpy: the fast way
            sw = self.swarm
            sw.resize(n, len(colours), W, H)
            if self.colour != s['colour']:
                self.colour = s['colour']
                sw.recolour(len(colours))
            sw.move(s, W, H, dt, t, pointer_in(self.widget) if s['pattern'] == 'flock' else None)
            self.paint_box(cr, s, bx, by, bw, bh)
            if not spill:
                cr.save()
                self.outline(cr, bx, by, bw, bh)
                cr.clip()
            sw.paint(cr, s, W, H, t, spill, colours)
            if not spill:
                cr.restore()
            self.paint_edge(cr, s, bx, by, bw, bh)
            return False
        if len(self.parts) > n:
            del self.parts[n:]
        while len(self.parts) < n:
            self.parts.append(self.new_particle(colours, W, H))
        if self.colour != s['colour']:                         # colour changed: repaint all
            self.colour = s['colour']
            for p in self.parts:
                p['c'] = random.choice(colours)
        self.move(s, W, H, dt, t)
        self.paint_box(cr, s, bx, by, bw, bh)
        if not spill:                                         # particles stay in the box
            cr.save()
            self.outline(cr, bx, by, bw, bh)
            cr.clip()
        size, glow, twinkle = s['size'], s['glow'], s['pattern'] == 'twinkle'
        pop = s['particle_opacity']
        # group by colour and brightness (12 steps), then fill each group in one go:
        # a dozen cairo fills per frame instead of one per particle
        groups, halos = {}, {}
        organic, hypot, sin = self.organic, math.hypot, math.sin
        for p in self.parts:
            z, x, y = p['z'], p['x'], p['y']
            alpha = (0.22 + 0.7 * z) * pop
            if spill:                                  # one soft cloud, no seam at the box
                alpha *= organic(x, y, W, H, t)
            if twinkle:
                alpha *= 0.5 + 0.5 * sin(t * (1.2 + 2.5 * z) + p['ph'])
            if alpha <= 0.01:
                continue
            q = min(11, int(alpha * 12))
            rad = (0.6 + 1.3 * z) * size
            groups.setdefault((p['c'], q), []).append((x, y, rad))
            if glow and z > 0.65:
                halos.setdefault((p['c'], q), []).append((x, y, rad * 3))
        for (c, q), pts in halos.items():
            cr.set_source_rgba(*c, (q + 0.5) / 12 * 0.18)
            for x, y, r in pts:
                cr.new_sub_path()
                cr.arc(x, y, r, 0, 6.283)
            cr.fill()
        for (c, q), pts in groups.items():
            cr.set_source_rgba(*c, (q + 0.5) / 12)
            for x, y, r in pts:
                if r < 1.5:                            # tiny: a square is cheaper
                    cr.rectangle(x - r, y - r, 2 * r, 2 * r)
                else:
                    cr.new_sub_path()
                    cr.arc(x, y, r, 0, 6.283)
            cr.fill()
        if not spill:
            cr.restore()
        self.paint_edge(cr, s, bx, by, bw, bh)
        return False                    # GTK draws the children on top

    def paint_box(self, cr, s, bx, by, bw, bh):
        """what is behind (still image without compositor) and the dark box"""
        if self.backdrop is not None:
            # turned into a cairo surface once per picture, not on every frame (30 a second)
            if getattr(self, '_bd_src', None) is not self.backdrop:
                from gi.repository import Gdk
                self._bd_src = self.backdrop
                self._bd_surf = Gdk.cairo_surface_create_from_pixbuf(self.backdrop, 1, None)
            cr.set_source_surface(self._bd_surf, *self.backdrop_at)
            cr.paint()
        cr.save()
        self.outline(cr, bx, by, bw, bh)
        cr.set_source_rgba(0, 0, 0, s['opacity'])
        cr.fill()
        cr.restore()

    def paint_edge(self, cr, s, bx, by, bw, bh):
        if s['opacity'] > 0.05:
            self.outline(cr, bx + 0.5, by + 0.5, bw - 1, bh - 1)
            cr.set_source_rgba(1, 1, 1, 0.10 * s['opacity'])  # thin edge
            cr.set_line_width(1)
            cr.stroke()


def bar_css():
    """CSS for the indicator's level bar, following the bar_opacity setting"""
    return (f'.zosd progressbar {{ opacity: {settings("overlay")["bar_opacity"]:.2f}; }}').encode()
