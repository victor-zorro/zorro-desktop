"""zorro_fx: the lock-screen look for small on-screen overlays (volume/brightness indicator,
screenshot toolbar): a dark box with moving particles, optionally spilling out of the box.

Used by zorro-thinkpad and zorro-shot (they import it from ../zorro-fx next to their own
folder and fall back to a plain dark box without it). Settings are shared in
~/.config/zorro-fx/config.json and edited in the ThinkPad app, page "Overlays"; running
overlays pick up changes on their next frame.
"""
import json
import math
import os
import random
import time
from pathlib import Path

CONF = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'zorro-fx' / 'config.json'

DEFAULTS = {
    'pattern': 'float',         # see PATTERNS
    'colour': 'snow',           # see COLOURS
    'amount': 6.0,              # particles per 1000 px² of the box (0-60)
    'speed': 1.6,               # 1 = calm
    'size': 1.0,                # particle size factor
    'glow': True,               # soft halo around the nearest particles
    'spill': 0,                 # px the particles drift out of the box onto the screen
    'opacity': 0.94,            # box background, 0 = invisible, 1 = solid black
    'particle_opacity': 1.0,    # particles
    'bar_opacity': 1.0,         # level bar of the indicator
    'osd_seconds': 1.5,         # how long the indicator stays
    'app_bg': False,            # the ThinkPad app window gets the same background
}
PATTERNS = {
    'float': 'Floating around',
    'flock': 'Flock (follows the mouse)',
    'fall': 'Falling (marine snow)',
    'rise': 'Rising (bubbles)',
    'swirl': 'Swirling around the middle',
    'twinkle': 'Twinkling stars',
}
GREY, CYAN, RED, WHITE = (0.60, 0.60, 0.63), (0.10, 0.90, 1.0), (1.0, 0.16, 0.29), (0.94, 0.94, 0.96)
COLOURS = {                 # name: (label, colours picked at random per particle)
    'snow': ('Lock screen grey', [GREY]),
    'white': ('White', [WHITE]),
    'cyan': ('Cyan', [CYAN]),
    'red': ('Red', [RED]),
    'mixed': ('Grey with a few cyan and red', [GREY] * 6 + [CYAN, RED]),
}
MAX_PARTICLES = 3000

_cache = {'mtime': -1, 'data': None}


def settings():
    """current settings; re-read only when the file changed (cheap to call every frame)"""
    try:
        mtime = CONF.stat().st_mtime
    except OSError:
        mtime = None
    if _cache['data'] is None or mtime != _cache['mtime']:
        s = dict(DEFAULTS)
        try:
            s.update({k: v for k, v in json.loads(CONF.read_text()).items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass
        _cache.update(mtime=mtime, data=s)
    return _cache['data']


def save(s):
    CONF.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONF.with_suffix('.tmp')
    tmp.write_text(json.dumps({k: s[k] for k in DEFAULTS if k in s}, indent=2) + '\n')
    tmp.replace(CONF)


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


class Snow:
    """Paints the overlay background under a widget's children and animates it while the
    widget is on screen.

    inner: the box itself (the widget is then a margin around it, as wide as the 'spill'
    setting, where particles fade out); None = the widget is the box, no spill.
    backdrop: a GdkPixbuf painted first - a still image of what is behind the overlay, so
    see-through and spill also work without a compositor."""

    def __init__(self, widget, radius=12, fps=30, inner=None, enabled=None,
                 max_parts=MAX_PARTICLES, max_spill=None):
        self.widget, self.radius, self.fps, self.inner = widget, radius, fps, inner
        self.enabled, self.max_parts, self.max_spill = enabled, max_parts, max_spill
        self.was_on = None
        self.parts, self.timer = [], None
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
            self.timer = GLib.timeout_add(1000 // self.fps, self.tick)

    def stop(self):
        from gi.repository import GLib
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None

    def tick(self):
        on = self.enabled is None or self.enabled()
        if on or on != self.was_on:                 # off: one last redraw, then idle
            self.update_spill()
            self.widget.queue_draw()
        self.was_on = on
        return True

    def update_spill(self):
        if self.inner is None:
            return
        sp = int(settings()['spill'])
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
        s = settings()
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
        if len(self.parts) > n:
            del self.parts[n:]
        while len(self.parts) < n:
            self.parts.append(self.new_particle(colours, W, H))
        if self.colour != s['colour']:                         # colour changed: repaint all
            self.colour = s['colour']
            for p in self.parts:
                p['c'] = random.choice(colours)
        self.move(s, W, H, dt, t)

        if self.backdrop is not None:
            from gi.repository import Gdk
            Gdk.cairo_set_source_pixbuf(cr, self.backdrop, *self.backdrop_at)
            cr.paint()
        cr.save()
        self.outline(cr, bx, by, bw, bh)
        cr.set_source_rgba(0, 0, 0, s['opacity'])
        cr.fill()
        cr.restore()
        if not spill:                                         # particles stay in the box
            cr.save()
            self.outline(cr, bx, by, bw, bh)
            cr.clip()
        size, glow, twinkle = s['size'], s['glow'], s['pattern'] == 'twinkle'
        pop = s['particle_opacity']
        for p in self.parts:
            z, x, y = p['z'], p['x'], p['y']
            alpha = (0.22 + 0.7 * z) * pop
            if spill:                                         # fade out away from the box
                dx = max(bx - x, 0, x - bx - bw)
                dy = max(by - y, 0, y - by - bh)
                if dx or dy:
                    alpha *= max(0.0, 1 - math.hypot(dx, dy) / spill)
            if twinkle:
                alpha *= 0.5 + 0.5 * math.sin(t * (1.2 + 2.5 * z) + p['ph'])
            if alpha <= 0.01:
                continue
            rad = (0.6 + 1.3 * z) * size
            if glow and z > 0.65:
                cr.set_source_rgba(*p['c'], alpha * 0.18)
                cr.arc(x, y, rad * 3, 0, 6.283)
                cr.fill()
            cr.set_source_rgba(*p['c'], alpha)
            if rad < 1.5:                               # tiny: a square is cheaper
                cr.rectangle(x - rad, y - rad, 2 * rad, 2 * rad)
            else:
                cr.arc(x, y, rad, 0, 6.283)
            cr.fill()
        if not spill:
            cr.restore()
        if s['opacity'] > 0.05:
            self.outline(cr, bx + 0.5, by + 0.5, bw - 1, bh - 1)
            cr.set_source_rgba(1, 1, 1, 0.10 * s['opacity'])  # thin edge
            cr.set_line_width(1)
            cr.stroke()
        return False                    # GTK draws the children on top


def bar_css():
    """CSS for the indicator's level bar, following the bar_opacity setting"""
    return (f'.zosd progressbar {{ opacity: {settings()["bar_opacity"]:.2f}; }}').encode()
