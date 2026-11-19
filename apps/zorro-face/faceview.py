#!/usr/bin/python3
"""faceview: the window where zorro-face learns your face, and where it forgets it.

  faceview.py learn    live infrared picture; every view that is learned adds lines to a
                       wireframe of your face (68 points, from the nose outwards). Below: a
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


def triangulate(pts):
    """the wireframe's edges: Delaunay over the 68 points, ordered from the nose tip outwards"""
    import cv2
    x0, y0 = pts.min(0) - 10
    x1, y1 = pts.max(0) + 10
    sub = cv2.Subdiv2D((int(x0), int(y0), int(x1 - x0) + 1, int(y1 - y0) + 1))
    for p in pts:
        sub.insert((float(p[0]), float(p[1])))
    edges = set()
    for t in sub.getTriangleList():
        idx = []
        for k in range(3):
            q = np.array(t[2 * k:2 * k + 2])
            d = np.linalg.norm(pts - q, axis=1)
            if d.min() > 0.5:
                break
            idx.append(int(d.argmin()))
        if len(idx) == 3:
            for a, b in ((0, 1), (1, 2), (2, 0)):
                edges.add(tuple(sorted((idx[a], idx[b]))))
    nose = pts[30]
    return sorted(edges, key=lambda e: np.linalg.norm((pts[e[0]] + pts[e[1]]) / 2 - nose))


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
        self.edges = []
        self.views, self.shapes = [], []
        self.bins = {p: 0 for p in POSES}
        self.base_pitch = None
        self.new_at = 0.0               # when the last view was learned (glow)
        self.text, self.sub = 'starting the camera…', ''
        self.state = 'run'              # run, saving, saved, failed | ready, going, gone
        self.vanish = 0.0

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.area = Gtk.DrawingArea(vexpand=True)
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
                    self.frame = lit[:, ::-1].copy()
                    self.pts = None if pts is None else np.column_stack([lit.shape[1] - 1 - pts[:, 0], pts[:, 1]])
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
                    if not self.edges:
                        self.edges = triangulate(pts)
                    self.views.append(e)
                    self.shapes.append(normalise(pts))
                    self.bins[p] += 1
                    self.new_at = time.time()
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
        if self.base_pitch is None:
            if abs(yaw) > 0.08:
                return None             # the first views: straight on, they set what "level" is
            self.base_pitch = pitch
        dp = pitch - self.base_pitch
        if yaw > 0.1:                   # the camera faces you: your left is its right
            return 'left'
        if yaw < -0.1:
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
            else:
                err = p.stderr.decode(errors='replace').strip().splitlines()
                self.say('Not saved.', err[-1] if err else 'cancelled', 'failed')
        threading.Thread(target=work, daemon=True).start()
        return False

    def keep_mesh(self):
        with self.lock:
            shape = np.mean(self.shapes, 0)
            edges = triangulate(shape * 100 + 200)
        MESH.parent.mkdir(parents=True, exist_ok=True)
        tmp = MESH.with_suffix('.tmp')
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as fh:
            json.dump({'points': shape.round(4).tolist(), 'edges': edges,
                       'strength': strength(self.views, sum(v >= 3 for v in self.bins.values()))[0]}, fh)
        os.replace(tmp, MESH)

    def on_button(self, _b):
        if self.mode == 'learn':
            self.save()
        else:
            self.forget()

    # ---- forgetting ----------------------------------------------------------------------
    def forget_load(self):
        try:
            d = json.loads(MESH.read_text())
            self.shape = np.array(d['points'], np.float32)
            self.edges = [tuple(e) for e in d['edges']]
            self.kept_strength = float(d.get('strength', 0))
        except (OSError, ValueError, KeyError):
            self.shape, self.edges, self.kept_strength = None, [], 0.0
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
            self.say('Taking it apart…', '', 'going')
        threading.Thread(target=work, daemon=True).start()

    # ---- drawing -------------------------------------------------------------------------
    def tick(self):
        if not self.running:
            return False
        if self.state == 'going' and time.time() - self.vanish > 4.2:
            self.state = 'gone'
            self.text, self.sub = 'All your face data is deleted.', 'Nothing of your face is left on this laptop.'
        self.area.queue_draw()
        return True

    def draw(self, w, cr):
        W, H = w.get_allocated_width(), w.get_allocated_height()
        cr.set_source_rgb(*BG)
        cr.paint()
        top, bottom = 70, 120           # text above, strength bar below
        box = (0, top, W, H - top - bottom)
        if self.mode == 'learn':
            self.draw_learn(cr, box)
        else:
            self.draw_forget(cr, box)
        self.draw_text(cr, W, top)
        self.draw_bar(cr, W, H - bottom + 14)

    def draw_learn(self, cr, box):
        bx, by, bw, bh = box
        with self.lock:
            frame, pts, edges = self.frame, self.pts, list(self.edges)
            n, glow = len(self.views), max(0.0, 1 - (time.time() - self.new_at) / 0.8)
        if frame is None:
            return
        fh, fw = frame.shape
        s = min(bw / fw, bh / fh)
        ox, oy = bx + (bw - fw * s) / 2, by + (bh - fh * s) / 2
        rgb = np.dstack([frame, frame, frame, np.full_like(frame, 255)])
        rgb = np.ascontiguousarray(np.clip(rgb * [1.0, 0.9, 0.78, 1], 0, 255).astype(np.uint8))
        surf = cairo.ImageSurface.create_for_data(memoryview(rgb).cast('B'), cairo.FORMAT_RGB24, fw, fh, fw * 4)
        cr.save()
        cr.translate(ox, oy)
        cr.scale(s, s)
        cr.set_source_surface(surf, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint_with_alpha(0.8)
        cr.restore()
        if pts is None:
            return
        P = [(ox + x * s, oy + y * s) for x, y in pts]
        shown = int(len(edges) * min(1.0, n / WANT))
        fresh = int(len(edges) * min(1.0, max(0, n - 1) / WANT))
        cr.set_line_width(1.0)
        for i, (a, b) in enumerate(edges[:shown]):
            hot = glow if i >= fresh else 0.0
            cr.set_source_rgba(LINE[0] + 0.4 * hot, LINE[1], LINE[2], 0.45 + 0.5 * hot)
            cr.move_to(*P[a])
            cr.line_to(*P[b])
            cr.stroke()
        for x, y in P:                  # the 68 points: faint while they are not learned yet
            cr.set_source_rgba(*LINE, 0.25 + 0.6 * min(1.0, n / WANT))
            cr.arc(x, y, 1.6, 0, 2 * math.pi)
            cr.fill()

    def draw_forget(self, cr, box):
        bx, by, bw, bh = box
        if self.shape is None:
            return
        s = min(bw, bh) / 4.2
        cx, cy = bx + bw / 2, by + bh / 2
        breathe = 1 + 0.01 * math.sin(time.time() * 1.5)
        P = [(cx + x * s * breathe, cy + y * s * breathe) for x, y in self.shape]
        k = 1.0
        if self.state == 'going':
            k = max(0.0, 1 - (time.time() - self.vanish) / 3.2)      # edges go, outermost first
        elif self.state == 'gone':
            k = 0.0
        shown = len(self.edges) * k
        cr.set_line_width(1.1)
        for i, (a, b) in enumerate(self.edges):
            if i >= shown:
                break
            fade = min(1.0, shown - i) if i >= shown - 1 else 1.0
            edge_glow = 1.0 if self.state == 'going' and i >= shown - 12 else 0.0
            cr.set_source_rgba(LINE[0] + 0.45 * edge_glow, LINE[1] - 0.3 * edge_glow, LINE[2] - 0.3 * edge_glow,
                               (0.55 + 0.4 * edge_glow) * fade)
            cr.move_to(*P[a])
            cr.line_to(*P[b])
            cr.stroke()
        dots = 1.0 if self.state not in ('going', 'gone') else \
            max(0.0, 1 - (time.time() - self.vanish - 3.0) / 1.0) if self.state == 'going' else 0.0
        for x, y in P:
            cr.set_source_rgba(*LINE, 0.8 * dots)
            cr.arc(x, y, 1.8, 0, 2 * math.pi)
            cr.fill()

    def draw_text(self, cr, W, top):
        cr.select_font_face('monospace', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        for text, size, y, a in ((self.text, 17, 32, 0.95), (self.sub, 11, 54, 0.55)):
            if not text:
                continue
            cr.set_font_size(size)
            ext = cr.text_extents(text)
            cr.set_source_rgba(0.9, 0.95, 1.0, a)
            cr.move_to((W - ext.width) / 2 - ext.x_bearing, y)
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
