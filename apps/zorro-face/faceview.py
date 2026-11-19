#!/usr/bin/python3
"""faceview: the window where zorro-face learns your face, and where it forgets it.

  faceview.py learn    your face as a wireframe head over the theme's particles (no camera
                       picture): it follows your head, and every view that is learned adds
                       lines, from the nose outwards, with a glitch. Below: a
                       strength bar. At the end the views go to root through pkexec
                       (zorro-face save), which asks your password.
  faceview.py forget   your wireframe comes apart line by line, then every bit of face data is
                       deleted (the views root keeps, and the wireframe kept here).

The camera is read as you (it belongs to the logged-in user); only the final numbers go to root.
The wireframe shape (no picture) is kept in ~/.local/share/zorro-face/mesh.json, only for this
window, and goes with "Delete all my face data".
"""
import getpass
import io
import json
import math
import os
import subprocess
import sys
import threading
import time
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

import cairo
import gi
import numpy as np

gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk  # noqa: E402

HERE = Path(os.path.realpath(__file__)).parent
MESH = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'zorro-face' / 'mesh.json'
FACE = '/usr/local/bin/zorro-face'


def as_root(*args):
    """zorro-face through pkexec (asks your password); in a test (ZORRO_FACE_DATA) it runs directly"""
    if 'ZORRO_FACE_DATA' in os.environ:
        return [str(HERE / 'zorro-face'), *args]
    return ['pkexec', FACE, *args]
WANT = 24                       # views to learn
POSES = ['straight', 'left', 'right', 'up', 'down']
HINT = {'straight': 'look straight at the screen', 'left': 'turn your head a little to the left',
        'right': 'turn your head a little to the right', 'up': 'tilt your head up a little',
        'down': 'tilt your head down a little'}
STRANGER, SAME = 0.25, 0.80     # SFace: a stranger scores about this, you yourself about this
BG = (0.02, 0.025, 0.035)
LINE = (0.55, 0.85, 1.0)        # cyan-white wireframe


def zf():
    """zorro-face as a module (its camera and face code)"""
    path = str(HERE / 'zorro-face')
    spec = spec_from_loader('zorro_face', SourceFileLoader('zorro_face', path))
    m = module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


FEATURES = [list(range(0, 17)), list(range(17, 22)), list(range(22, 27)), list(range(27, 31)),
            list(range(31, 36)) + [30, 31], list(range(36, 42)) + [36], list(range(42, 48)) + [42],
            list(range(48, 60)) + [48], list(range(60, 68)) + [60]]
LATS, MERS = 13, 11             # the curved lines across and down the face


def _bez(a, c, b, n):
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 2 * a + 2 * (1 - t) * t * c + t ** 2 * b


def head_mesh(pts):
    """a wireframe head over the 68 points: the features (jaw, brows, nose, eyes, lips) and a
    grid of curved lines across and down, over a forehead dome. Returns (features, grid):
    features [polyline], grid [(order, a, b)] - order 0 at the nose, growing outwards"""
    pts = np.asarray(pts, np.float64)
    left, right, chin = pts[0], pts[16], pts[8]
    c = (left + right) / 2
    rx = right - left
    a = np.linalg.norm(rx) / 2 or 1
    rx = rx / (2 * a)
    down = np.array([-rx[1], rx[0]])
    if np.dot(chin - c, down) < 0:
        down = -down
    loc = lambda q: np.array([np.dot(q - c, rx), np.dot(q - c, down)])           # noqa: E731
    back = lambda x, y: c + rx * x + down * y                                    # noqa: E731
    P = np.array([loc(q) for q in pts])
    # top of the forehead dome: from the face's height (the jaw width shrinks when you turn)
    top = min(-0.8 * a, P[17:27, 1].min() - 0.55 * (P[8][1] - P[27][1]))
    dome = [np.array([a * math.cos(t), top * math.sin(t)]) for t in np.linspace(0, math.pi, 15)]
    outline_r = sorted([d for d in dome if d[0] >= 0] + [P[i] for i in range(8, 17)], key=lambda q: q[1])
    outline_l = sorted([d for d in dome if d[0] <= 0] + [P[i] for i in range(0, 9)], key=lambda q: q[1])
    mid = [np.array([0.0, top])] + [P[i] for i in (27, 28, 29, 30, 33, 51, 57, 8)]
    mid = sorted(mid, key=lambda q: q[1])

    def at(line, y):
        ys = np.array([q[1] for q in line])
        xs = np.array([q[0] for q in line])
        return float(np.interp(y, ys, xs))

    ytop, ybot = top * 0.96, P[8][1] * 0.97
    nose_y = P[30][1]
    lat_pts = []
    for i in range(LATS):
        y = ytop + (ybot - ytop) * i / (LATS - 1)
        L = np.array([at(outline_l, y), y])
        R = np.array([at(outline_r, y), y])
        M = np.array([at(mid, y), y + 0.10 * a * min(1.0, i / 3)])   # sags a little: a round head
        ctrl = 2 * M - (L + R) / 2
        lat_pts.append(_bez(L, ctrl, R, MERS))
    ni = int(np.argmin([abs(row[0][1] - nose_y) for row in lat_pts]))
    jc = (MERS - 1) / 2
    grid = []
    for i, row in enumerate(lat_pts):
        for j in range(MERS):
            q = back(*row[j])
            if j + 1 < MERS:
                grid.append((math.hypot(i - ni, j + 0.5 - jc), q, back(*row[j + 1])))
            if i + 1 < LATS:
                grid.append((math.hypot(i + 0.5 - ni, j - jc), q, back(*lat_pts[i + 1][j])))
    grid.sort(key=lambda g: g[0])
    feats = [[tuple(pts[k]) for k in f] for f in FEATURES]
    return feats, grid


def normalise(pts):
    """the shape without where and how big: centred, eye distance 1"""
    c = pts.mean(0)
    eye = np.linalg.norm(pts[45] - pts[36]) or 1
    return (pts - c) / eye


def pose(pts):
    eyes = (pts[36] + pts[45]) / 2
    d = np.linalg.norm(pts[45] - pts[36]) or 1
    return (pts[30][0] - eyes[0]) / d, (pts[30][1] - eyes[1]) / d     # yaw, pitch-ish


def strength(views, filled):
    """0..1 and the three parts: how alike your views are (so how far above a stranger, who
    scores about 0.25), how many head angles, how many views"""
    if len(views) < 2:
        return 0.0, 0.0, 0.0, 0.0
    v = np.array(views)
    s = v @ v.T
    same = float((s.sum() - len(v)) / (len(v) * (len(v) - 1)))
    apart = min(1.0, max(0.0, (same - STRANGER) / (SAME - STRANGER)))
    cover = filled / len(POSES)
    count = min(1.0, len(views) / WANT)
    # alike views from one angle prove little: angles and number weigh in on everything
    return apart * (0.3 + 0.7 * cover) * (0.4 + 0.6 * count), apart, cover, count


def word(x):
    return 'weak' if x < 0.35 else 'fair' if x < 0.6 else 'good' if x < 0.8 else 'strong'


class View(Gtk.Window):
    def __init__(self, mode):
        super().__init__(title='Face unlock')
        self.mode = mode
        self.set_default_size(880, 660)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect('destroy', self.bye)
        self.lock = threading.Lock()
        self.running = True
        self.frame = None               # last lit IR picture (uint8 H x W)
        self.pts = None                 # 68 points on it, when a face is seen
        self.views, self.shapes = [], []
        self.bins = {p: 0 for p in POSES}
        self.base_yaw = self.base_pitch = None
        self.new_at = 0.0               # when the last view was learned (glow)
        self.text, self.sub = 'starting the camera…', ''
        self.state = 'run'              # run, saving, saved, failed | ready, going, gone
        self.vanish = 0.0
        self.smooth = None              # the points, smoothed (the landmark finder jitters)
        self.burst_at, self.burst_k = 0.0, 0.0
        self.next_burst = time.time() + 3

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.area = Gtk.DrawingArea(vexpand=True)
        self.area.connect('draw', self.draw_bg)
        self.snow = None
        try:                            # the theme's particles (apps/zorro-fx)
            sys.path.insert(0, str(HERE.parent / 'zorro-fx'))
            import zorro_fx
            self.snow = zorro_fx.Snow(self.area, radius=0, profile='overlay')
        except Exception:               # noqa: BLE001 - without it: just dark
            pass
        self.area.connect('draw', self.draw)
        box.add(self.area)
        bar = Gtk.Box(spacing=8, margin=12, halign=Gtk.Align.END)
        self.btn = Gtk.Button(label='Done' if mode == 'learn' else 'Delete all my face data')
        self.btn.connect('clicked', self.on_button)
        close = Gtk.Button(label='Close')
        close.connect('clicked', lambda b: self.destroy())
        bar.add(close)
        bar.add(self.btn)
        box.add(bar)
        self.add(box)
        css = Gtk.CssProvider()
        css.load_from_data(b'window, box { background: #05070a; } button { min-width: 90px; }')
        self.get_style_context().add_provider_for_screen(self.get_screen(), css, 800)
        self.show_all()

        if mode == 'learn':
            self.btn.set_sensitive(False)
            threading.Thread(target=self.learn, daemon=True).start()
        else:
            self.forget_load()
        GLib.timeout_add(33, self.tick)

    # ---- learning ------------------------------------------------------------------------
    def learn(self):
        try:
            import cv2
            m = zf()
            dev = m.find_camera()
            if not dev:
                return self.say('No infrared camera found.', '', 'failed')
            m.emitter(dev)
            faces = m.Faces()
            self.say('loading the face points…')
            mark = cv2.face.createFacemarkLBF()
            mark.loadModel(f'{m.SHARE}/lbfmodel.yaml')
            cam = m.Camera(dev)
        except Exception as e:          # noqa: BLE001 - shown in the window
            return self.say('Could not start.', str(e)[:120], 'failed')
        last = 0.0
        self.say(HINT['straight'])
        try:
            for lit, dark in cam.pairs():
                if not self.running or self.state != 'run':
                    break
                e, why = faces.look(lit, dark)
                pts = None
                if e is not None or why == 'not lit':
                    x, y, w, h = (int(v) for v in faces.last[:4])
                    ok, lm = mark.fit(lit, np.array([[x, y, w, h]], np.int32))
                    if ok:
                        pts = lm[0][0].astype(np.float32)
                with self.lock:             # shown as a mirror, like looking into one
                    self.frame = True
                    if pts is not None:
                        pts = np.column_stack([lit.shape[1] - 1 - pts[:, 0], pts[:, 1]])
                        self.smooth = pts if self.smooth is None else 0.55 * self.smooth + 0.45 * pts
                    self.pts = pts
                if why == 'too far':
                    self.say('come a little closer')
                elif why == 'not lit':
                    self.say('not lit by the camera\'s own light', 'a photo or a screen does not count')
                if e is None or pts is None or time.time() - last < 0.3:
                    continue
                p = self.which_pose(pts)
                if p is None or self.bins[p] >= 6:
                    self.say(HINT[self.next_pose()])
                    continue
                last = time.time()
                with self.lock:
                    self.views.append(e)
                    self.shapes.append(normalise(pts))
                    self.bins[p] += 1
                    self.new_at = time.time()
                    self.burst(0.7)
                n = len(self.views)
                if n >= 8:
                    GLib.idle_add(self.btn.set_sensitive, True)
                if n >= WANT or (n >= 15 and all(self.bins[q] >= 3 for q in POSES)):
                    break
                self.say(HINT[self.next_pose()], f'{n} of {WANT} views learned')
        finally:
            cam.close()
        if self.running and self.state == 'run':
            if len(self.views) >= 8:
                GLib.idle_add(self.save)
            else:
                self.say('Not enough views.', 'Come closer and look at the screen, then try again.', 'failed')

    def which_pose(self, pts):
        yaw, pitch = pose(pts)
        if self.base_pitch is None:     # the first view sets "straight" (the camera may see
            self.base_yaw, self.base_pitch = yaw, pitch     # you a little from the side)
        dy, dp = yaw - self.base_yaw, pitch - self.base_pitch
        if dy > 0.1:                    # the camera faces you: your left is its right
            return 'left'
        if dy < -0.1:
            return 'right'
        if dp < -0.07:
            return 'up'
        if dp > 0.07:
            return 'down'
        return 'straight'

    def next_pose(self):
        need = [p for p in POSES if self.bins[p] < 3]
        return need[0] if need else 'straight'

    def say(self, text, sub=None, state=None):
        def do():
            self.text = text
            if sub is not None:
                self.sub = sub
            if state:
                self.state = state
            return False
        GLib.idle_add(do)

    def save(self):
        if self.state != 'run':
            return False
        self.state = 'saving'
        self.btn.set_sensitive(False)
        self.text, self.sub = 'saving…', 'your password, so it can be kept where only root can read it'
        buf = io.BytesIO()
        np.save(buf, np.array(self.views[-96:], np.float32))

        def work():
            p = subprocess.run(as_root('save', getpass.getuser()), input=buf.getvalue(),
                               capture_output=True)
            if p.returncode == 0:
                self.keep_mesh()
                self.say('Learned ✓', f'{len(self.views)} views. The face icon now unlocks with your face.',
                         'saved')
                GLib.idle_add(self.finish)
            else:
                err = p.stderr.decode(errors='replace').strip().splitlines()
                self.say('Not saved.', err[-1] if err else 'cancelled', 'failed')
        threading.Thread(target=work, daemon=True).start()
        return False

    def finish(self):
        """saved: a last burst, then the window closes by itself"""
        self.burst(1.0)
        self.btn.set_label('Close')
        self.btn.set_sensitive(True)
        GLib.timeout_add(3500, lambda: self.destroy() or False)
        return False

    def burst(self, k):
        self.burst_at, self.burst_k = time.time(), k

    def keep_mesh(self):
        with self.lock:
            shape = np.mean(self.shapes, 0)
        MESH.parent.mkdir(parents=True, exist_ok=True)
        tmp = MESH.with_suffix('.tmp')
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as fh:
            json.dump({'points': shape.round(4).tolist(),
                       'strength': strength(self.views, sum(v >= 3 for v in self.bins.values()))[0]}, fh)
        os.replace(tmp, MESH)

    def on_button(self, _b):
        if self.state in ('saved', 'failed', 'gone'):
            self.destroy()
        elif self.mode == 'learn':
            self.save()
        else:
            self.forget()

    # ---- forgetting ----------------------------------------------------------------------
    def forget_load(self):
        try:
            d = json.loads(MESH.read_text())
            self.shape = np.array(d['points'], np.float32)
            self.kept_strength = float(d.get('strength', 0))
        except (OSError, ValueError, KeyError):
            self.shape, self.kept_strength = None, 0.0
        self.state = 'ready'
        self.text = 'This is what face unlock knows of you.'
        self.sub = ('Delete it all: the views root keeps, and this wireframe. The face icon goes away; '
                    'the password stays.')

    def forget(self):
        self.btn.set_sensitive(False)
        self.text, self.sub = 'deleting…', 'your password, to delete what root keeps'

        def work():
            p = subprocess.run(as_root('remove', getpass.getuser()), capture_output=True)
            if p.returncode != 0:
                self.say('Not deleted.', 'cancelled', 'ready')
                GLib.idle_add(self.btn.set_sensitive, True)
                return
            MESH.unlink(missing_ok=True)
            self.vanish = time.time()
            self.burst(1.0)
            self.say('Taking it apart…', '', 'going')
        threading.Thread(target=work, daemon=True).start()

    # ---- drawing -------------------------------------------------------------------------
    def tick(self):
        if not self.running:
            return False
        if self.state == 'going' and time.time() - self.vanish > 4.2:
            self.state = 'gone'
            self.text, self.sub = 'All your face data is deleted.', 'Nothing of your face is left on this laptop.'
            self.btn.set_label('Close')
            self.btn.set_sensitive(True)
            self.burst(0.8)
        if time.time() > self.next_burst:   # now and then a small glitch, like the login screen
            self.burst(0.35)
            self.next_burst = time.time() + 4 + 5 * (hash(time.time()) % 100) / 100
        self.area.queue_draw()
        return True

    def draw_bg(self, w, cr):
        cr.set_source_rgb(*BG)
        cr.paint()
        return False

    def glitch(self):
        """(0..1) how hard it glitches right now"""
        dt = time.time() - self.burst_at
        return self.burst_k * max(0.0, 1 - dt / 0.35) if dt < 0.35 else 0.0

    def draw(self, w, cr):
        W, H = w.get_allocated_width(), w.get_allocated_height()
        top, bottom = 70, 120           # text above, strength bar below
        box = (0, top, W, H - top - bottom)
        g = self.glitch()
        if self.mode == 'learn':
            with self.lock:
                pts = None if self.smooth is None else self.smooth.copy()
                n = len(self.views)
                fresh = max(0.0, 1 - (time.time() - self.new_at) / 0.9)
                seen = self.pts is not None
            frac = min(1.0, n / WANT)
            if pts is not None:
                self.paint_head(cr, box, normalise(pts), frac, fresh, g, 1.0 if seen else 0.45)
        elif self.shape is not None:
            k, dots = 1.0, 1.0
            if self.state == 'going':
                el = time.time() - self.vanish
                k = max(0.0, 1 - el / 3.2)
                dots = max(0.0, 1 - (el - 3.0) / 1.0)
            elif self.state == 'gone':
                k = dots = 0.0
            self.paint_head(cr, box, self.shape, k, 0.0, g, dots, going=self.state == 'going')
        self.draw_text(cr, W, top, g)
        self.draw_bar(cr, W, H - bottom + 14)

    def paint_head(self, cr, box, shape, frac, fresh, g, dots, going=False):
        """the wireframe head, centred: the first `frac` of it (from the nose outwards)"""
        bx, by, bw, bh = box
        s = min(bw, bh) / 4.6
        cx, cy = bx + bw / 2, by + bh / 2 + s * 0.35
        pts = np.column_stack([cx + shape[:, 0] * s, cy + shape[:, 1] * s])
        feats, grid = head_mesh(pts)
        shown = int(len(grid) * frac)
        fshown = int(len(feats) * min(1.0, frac * 3))           # the features come first
        slice_y = by + bh * ((time.time() * 7.3) % 1.0)
        passes = [((1.0, 0.16, 0.29), -4 * g, 0.55 * g), ((0.10, 0.90, 1.0), 4 * g, 0.55 * g),
                  (LINE, 0, 1.0)] if g > 0.02 else [(LINE, 0, 1.0)]
        for col, dx, alpha in passes:
            cr.save()
            cr.translate(dx, 0)
            cr.set_line_width(0.9)
            for idx, (_, p, q) in enumerate(grid[:shown]):
                hot = fresh if idx >= shown - max(6, len(grid) // WANT) else 0.0
                if going and idx >= shown - 10:
                    hot = 1.0
                ox = 10 * g if g > 0.02 and abs((p[1] + q[1]) / 2 - slice_y) < 18 else 0
                cr.set_source_rgba(*(col if not hot else (1.0, 0.45 + 0.5 * (not going), 0.5 + 0.5 * (not going))),
                                   alpha * (0.32 + 0.6 * hot))
                cr.move_to(p[0] + ox, p[1])
                cr.line_to(q[0] + ox, q[1])
                cr.stroke()
            cr.set_line_width(1.4)
            for f in feats[:fshown] if not going else feats[:int(len(feats) * frac)]:
                cr.set_source_rgba(*col, alpha * 0.85)
                cr.move_to(*f[0])
                for x, y in f[1:]:
                    cr.line_to(x, y)
                cr.stroke()
            cr.restore()
        for x, y in pts:
            cr.set_source_rgba(*LINE, 0.7 * dots * (0.4 + 0.6 * frac if not going else 1))
            cr.arc(x, y, 1.5, 0, 2 * math.pi)
            cr.fill()

    def draw_text(self, cr, W, top, g=0.0):
        cr.select_font_face('monospace', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        for text, size, y, a in ((self.text, 17, 32, 0.95), (self.sub, 11, 54, 0.55)):
            if not text:
                continue
            cr.set_font_size(size)
            ext = cr.text_extents(text)
            x = (W - ext.width) / 2 - ext.x_bearing
            if g > 0.02:                # the theme's red/cyan split
                for col, dx in (((1.0, 0.16, 0.29), -2 * g - 1), ((0.10, 0.90, 1.0), 2 * g + 1)):
                    cr.set_source_rgba(*col, a * 0.7)
                    cr.move_to(x + dx, y)
                    cr.show_text(text)
            cr.set_source_rgba(0.9, 0.95, 1.0, a)
            cr.move_to(x, y)
            cr.show_text(text)

    def draw_bar(self, cr, W, y):
        if self.mode == 'learn':
            with self.lock:
                x, apart, cover, count = strength(self.views, sum(v >= 3 for v in self.bins.values()))
            detail = (f'how unique: {int(apart * 100)}%   angles: {int(cover * len(POSES))}/{len(POSES)}   '
                      f'views: {len(self.views)}/{WANT}')
        else:
            x = self.kept_strength if self.state not in ('going', 'gone') else \
                self.kept_strength * max(0.0, 1 - (time.time() - self.vanish) / 3.2) if self.state == 'going' else 0
            detail = 'what is learned now'
        bw, bh = min(560, W - 80), 8
        bx = (W - bw) / 2
        cr.set_source_rgba(1, 1, 1, 0.08)
        cr.rectangle(bx, y, bw, bh)
        cr.fill()
        g = cairo.LinearGradient(bx, 0, bx + bw, 0)
        g.add_color_stop_rgb(0.0, 0.85, 0.25, 0.3)
        g.add_color_stop_rgb(0.45, 0.9, 0.75, 0.3)
        g.add_color_stop_rgb(1.0, 0.35, 0.9, 0.75)
        cr.set_source(g)
        cr.rectangle(bx, y, bw * x, bh)
        cr.fill()
        cr.set_font_size(11)
        label = f'STRENGTH  {word(x).upper()}' if x > 0 else 'STRENGTH  —'
        cr.set_source_rgba(0.9, 0.95, 1.0, 0.85)
        cr.move_to(bx, y - 8)
        cr.show_text(label)
        cr.set_source_rgba(0.9, 0.95, 1.0, 0.45)
        cr.move_to(bx, y + bh + 18)
        cr.show_text(detail)

    def bye(self, *_):
        self.running = False
        Gtk.main_quit()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode not in ('learn', 'forget'):
        print(__doc__.strip())
        return 1
    View(mode)
    Gtk.main()
    return 0


if __name__ == '__main__':
    sys.exit(main())
