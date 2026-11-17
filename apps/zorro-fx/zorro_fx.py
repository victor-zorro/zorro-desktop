"""zorro_fx: the lock-screen look for small on-screen overlays (volume/brightness indicator,
screenshot toolbar): a dark box with moving particles.

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
    'pattern': 'float',     # see PATTERNS
    'colour': 'snow',       # see COLOURS
    'amount': 6.0,          # particles per 1000 px² of overlay (0-60)
    'speed': 1.6,           # 1 = calm
    'size': 1.0,            # particle size factor
    'glow': True,           # soft halo around the nearest particles
    'opacity': 0.94,        # overlay background: 1 = solid black
    'bar_opacity': 1.0,     # level bar of the indicator
    'osd_seconds': 1.5,     # how long the indicator stays
}
PATTERNS = {
    'float': 'Floating around',
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


class Snow:
    """Paints the overlay background under a widget's children and animates it while the
    widget is on screen. `backdrop` (a GdkPixbuf) is painted first: a still image of what
    is behind the overlay, so a see-through background also works without a compositor."""

    def __init__(self, widget, radius=12, fps=30):
        self.widget, self.radius, self.fps = widget, radius, fps
        self.parts, self.timer = [], None
        self.t0 = self.last = time.monotonic()
        self.backdrop = None
        widget.set_app_paintable(True)
        widget.connect('draw', self.draw)
        widget.connect('map', lambda w: self.start())
        widget.connect('unmap', lambda w: self.stop())

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
        self.widget.queue_draw()
        return True

    @staticmethod
    def new_particle(colours):
        rnd = random.random
        return {'x': rnd(), 'y': rnd(), 'z': rnd() ** 1.4, 'a': rnd() * 6.283,
                'r': 0.25 + 0.75 * rnd() ** 0.7, 'ph': rnd() * 6.283,
                'c': random.choice(colours)}

    def move(self, s, W, H, dt, t):
        pat, sp = s['pattern'], s['speed']
        sin, cos = math.sin, math.cos
        for p in self.parts:
            v = (5 + 16 * p['z']) * sp                         # px per second
            if pat == 'fall' or pat == 'rise':
                p['y'] += (v if pat == 'fall' else -v) * dt / H
                p['x'] += sin(t * 0.8 + p['ph']) * 0.35 * v * dt / W
            elif pat == 'swirl':
                rad = p['r'] * min(W, H) * 0.5 + 4
                p['a'] += v * dt / rad * (1 if p['ph'] < 3.14 else 0.7)
                wob = 1 + 0.08 * sin(t * 0.5 + p['ph'])
                p['x'] = 0.5 + cos(p['a']) * p['r'] * 0.5 * wob
                p['y'] = 0.5 + sin(p['a']) * p['r'] * 0.5 * wob
                continue
            else:                                               # float / twinkle: wander
                if pat == 'twinkle':
                    v *= 0.25
                p['a'] += (random.random() - 0.5) * 4 * dt
                p['x'] += cos(p['a']) * v * dt / W
                p['y'] += sin(p['a']) * v * dt / H
            p['x'] %= 1.0
            p['y'] = (p['y'] + 0.05) % 1.1 - 0.05

    def outline(self, cr, W, H):
        r = min(self.radius, H / 2)
        if r:
            cr.new_sub_path()
            for cx, cy, a0 in ((W - r, r, -math.pi / 2), (W - r, H - r, 0),
                               (r, H - r, math.pi / 2), (r, r, math.pi)):
                cr.arc(cx, cy, r, a0, a0 + math.pi / 2)
            cr.close_path()
        else:
            cr.rectangle(0, 0, W, H)

    def draw(self, w, cr):
        s = settings()
        a = w.get_allocation()
        W, H = max(1, a.width), max(1, a.height)
        now = time.monotonic()
        dt, self.last = min(0.1, now - self.last), now
        t = now - self.t0

        colours = COLOURS.get(s['colour'], COLOURS['snow'])[1]
        n = int(W * H / 1000 * max(0.0, s['amount']))
        if len(self.parts) > n:
            del self.parts[n:]
        while len(self.parts) < n:
            self.parts.append(self.new_particle(colours))
        if getattr(self, 'colour', None) != s['colour']:       # colour changed: repaint all
            self.colour = s['colour']
            for p in self.parts:
                p['c'] = random.choice(colours)
        self.move(s, W, H, dt, t)

        cr.save()
        self.outline(cr, W, H)
        cr.clip()
        if self.backdrop is not None and s['opacity'] < 1:
            from gi.repository import Gdk
            Gdk.cairo_set_source_pixbuf(cr, self.backdrop, 0, 0)
            cr.paint()
        cr.set_source_rgba(0, 0, 0, s['opacity'])
        cr.paint()
        size, glow, twinkle = s['size'], s['glow'], s['pattern'] == 'twinkle'
        for p in self.parts:
            z = p['z']
            alpha = 0.22 + 0.7 * z
            if twinkle:
                alpha *= 0.5 + 0.5 * math.sin(t * (1.2 + 2.5 * z) + p['ph'])
            x, y, rad = p['x'] * W, p['y'] * H, (0.6 + 1.3 * z) * size
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
        cr.restore()
        self.outline(cr, W, H)
        cr.set_source_rgba(1, 1, 1, 0.10)                       # thin edge
        cr.set_line_width(1)
        cr.stroke()
        return False                    # GTK draws the children on top


def bar_css():
    """CSS for the indicator's level bar, following the bar_opacity setting"""
    return (f'.zosd progressbar {{ opacity: {settings()["bar_opacity"]:.2f}; }}').encode()
