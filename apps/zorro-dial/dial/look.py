"""The Dialer's look: the palette and font (apps/zorro-fx), text with its red/cyan split,
circles, icons."""
import math
import os
import subprocess

import cairo  # noqa: F401 - the drawing modules take cairo and GTK from here
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango, PangoCairo  # noqa: E402,F401

from . import state  # noqa: E402
from .parts.base import APPS  # noqa: E402  (this also puts apps/zorro-fx on the path)

try:                                    # the one palette (apps/zorro-fx/zorro_style.py)
    from zorro_style import BG, CYAN, DIM, FG, FONT, FONT_SANS, RED  # noqa: F401
except ImportError:
    RED, CYAN, FG = (1.0, 0.165, 0.29), (0.098, 0.902, 1.0), (0.847, 0.847, 0.871)
    BG, DIM = (0.020, 0.027, 0.039), (0.435, 0.439, 0.475)
    FONT, FONT_SANS = 'DejaVu Sans Mono', 'DejaVu Sans'
try:
    import zorro_fx  # noqa: F401
except ImportError:
    zorro_fx = None

LUCIDE = APPS / 'zorro-icons' / 'lucide'


def xft_dpi():
    """Xft.dpi as it is now (xrdb), else what GTK read at start, else 96"""
    try:
        out = subprocess.run(['xrdb', '-query'], capture_output=True, text=True, timeout=2).stdout
        for ln in out.splitlines():
            if ln.startswith('Xft.dpi:'):
                return float(ln.split(':', 1)[1])
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    res = Gdk.Screen.get_default().get_resolution()
    return res if res > 0 else 96.0


def text_layout(cr):
    """a Pango layout at the screen's font DPI (Xft.dpi: the Text size setting in the Zorro
    app); cairo's own default would stay at 96 whatever is set"""
    lay = PangoCairo.create_layout(cr)
    PangoCairo.context_set_resolution(lay.get_context(), state.SCREEN_DPI)
    lay.context_changed()
    return lay


def font(size, bold=False, mono=False):
    return Pango.FontDescription.from_string(f'{FONT if mono else FONT_SANS} {"Bold" if bold else ""} {size}')


def paint(cr, pb, x, y, alpha=1.0):
    """a picture with its middle at (x, y)"""
    Gdk.cairo_set_source_pixbuf(cr, pb, x - pb.get_width() / 2, y - pb.get_height() / 2)
    cr.paint_with_alpha(alpha)


def show_split(cr, lay, x, y, alpha=1.0, split=1.4):
    """a layout with its top left at (x, y), a red and a cyan copy just beside it"""
    for col, dx in ((RED, -split), (CYAN, split)) if split else ():
        cr.move_to(x + dx, y)
        cr.set_source_rgba(*col, 0.5 * alpha)
        PangoCairo.show_layout(cr, lay)
    cr.move_to(x, y)
    cr.set_source_rgba(*FG, alpha)
    PangoCairo.show_layout(cr, lay)


class Look:
    def pt(self, size):
        """a font size for text beside the dial: smaller on a small screen (never under 7 pt),
        never bigger than at 1080 (a big screen has its Text size setting for that)"""
        return max(7, round(size * min(1.0, self.u), 1))

    def text_ext(self, cr, s, size, bold=True):
        """(width, height) of a text in pixels"""
        ext = self.layout(cr, s, size, bold)[1]
        return ext.width, ext.height

    def inside(self, cr, s, x, y, size, bold=True, pad=None):
        """(x, y) moved so that the text centred there stays on the screen"""
        w, h = self.text_ext(cr, s, size, bold)
        pad = 12 * self.u if pad is None else pad
        W, H = self.geo.width, self.geo.height
        return (min(max(x, w / 2 + pad), W - w / 2 - pad),
                min(max(y, h / 2 + pad), H - h / 2 - pad))

    def layout(self, cr, s, size, bold):
        # layouts are kept between frames (20 a second, dozens of labels each)
        key = (s, size, bold)
        hit = self.layouts.get(key)
        if hit:
            lay, ext = hit
            PangoCairo.update_layout(cr, lay)
        else:
            lay = text_layout(cr)
            lay.set_font_description(font(size, bold))
            lay.set_text(s, -1)
            _, ext = lay.get_pixel_extents()
            if len(self.layouts) > 400:
                self.layouts.clear()
            self.layouts[key] = (lay, ext)
        return lay, ext

    def text(self, cr, s, x, y, size, bold=True, alpha=1.0, split=1.4):
        lay, ext = self.layout(cr, s, size, bold)
        show_split(cr, lay, x - ext.width / 2, y - ext.height / 2, alpha, split)

    def chroma_circle(self, cr, cx, cy, r, alpha=0.9, split=1.5):
        for col, dx in ((RED, -split), (CYAN, split)):
            cr.new_path()
            cr.arc(cx + dx, cy, r, 0, 2 * math.pi)
            cr.set_source_rgba(*col, 0.7 * alpha)
            cr.set_line_width(1.2)
            cr.stroke()
        cr.new_path()
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.set_source_rgba(1, 1, 1, 0.2 * alpha)
        cr.set_line_width(1)
        cr.stroke()

    def disc(self, cr, x, y, r, colour, alpha):
        cr.new_path()
        cr.arc(x, y, r, 0, 2 * math.pi)
        cr.set_source_rgba(*colour, alpha)
        cr.fill()

    def panel(self, cr, x, y, w, h):
        """a box beside the dial (file preview, chat): near black, a thin edge, a chromatic top"""
        r = 14 * self.u
        cr.new_path()
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.arc(x + w - r, y + r, r, 1.5 * math.pi, 0)
        cr.arc(x + w - r, y + h - r, r, 0, 0.5 * math.pi)
        cr.arc(x + r, y + h - r, r, 0.5 * math.pi, math.pi)
        cr.close_path()
        cr.set_source_rgba(0.02, 0.02, 0.04, 0.93)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.1)
        cr.set_line_width(1)
        cr.stroke()
        for col, dx in ((RED, -1.2), (CYAN, 1.2)):
            cr.move_to(x + r + dx, y + 0.5)
            cr.line_to(x + w - r + dx, y + 0.5)
            cr.set_source_rgba(*col, 0.6)
            cr.stroke()

    def lucide(self, name, size, alpha=0.75):
        size = max(8, int(round(size)))
        key = ('lucide:' + name, size, alpha)
        if key not in self.icons:
            try:
                svg = (LUCIDE / f'{name}.svg').read_text()
                svg = svg.replace('stroke="currentColor"', f'stroke="#ffffff" stroke-opacity="{alpha}"')
                loader = GdkPixbuf.PixbufLoader.new_with_type('svg')
                loader.set_size(size, size)
                loader.write(svg.encode())
                loader.close()
                self.icons[key] = loader.get_pixbuf()
            except (OSError, GLib.Error):
                self.icons[key] = None
        return self.icons[key]

    def icon(self, a, size):
        size = max(8, int(round(size)))
        if a.get('icon', '').startswith('lucide:'):
            return self.lucide(a['icon'][7:], int(size * 0.8))
        key = (a['icon'], size)
        if key not in self.icons:
            self.icons[key] = self.load_icon(a['icon'], size)
        return self.icons[key]

    def load_icon(self, name, size):
        try:
            if os.path.isabs(name):
                return GdkPixbuf.Pixbuf.new_from_file_at_size(name, size, size)
            if name:
                return self.theme.load_icon(name, size, Gtk.IconLookupFlags.FORCE_SIZE)
        except GLib.Error:
            pass
        try:
            return self.theme.load_icon('application-x-executable', size, Gtk.IconLookupFlags.FORCE_SIZE)
        except GLib.Error:
            return None
