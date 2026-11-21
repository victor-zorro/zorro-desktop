"""The panel beside the dial when you rest on a file: picture or first lines, name, size, date."""
import threading

from .look import FG, GdkPixbuf, GLib, Pango, PangoCairo, font, paint, text_layout
from .nodes import cache_key


def scaled(file, width, height):
    """the picture at the panel's size; decoded here, in the preview's thread, never while drawing"""
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_scale(file, max(1, int(width)), max(1, int(height)), True)
    except GLib.Error:
        return None


class Preview:
    def preview_box(self):
        """(x, y, width, height) of the panel: beside the fan, on the screen"""
        cx, cy, _hub, _a0, _a1, rings = self.fan()
        outer = rings[-1][1]
        sw, sh, u = self.geo.width, self.geo.height, self.u
        W = int(max(280 * u, min(self.conf['preview_size'] * u, sw - 32 * u)))    # pixels at 1080
        H = int(min(W * 0.78, sh - 32 * u))
        x = cx - outer - W - 40 * u if cx > sw / 2 else cx + outer + 40 * u
        x = max(16 * u, min(sw - W - 16 * u, x))
        y = max(16 * u, min(sh - H - 16 * u, cy - H + 40 * u if cy > sh / 2 else cy - 40 * u))
        return x, y, W, H

    def show_preview(self, node):
        self.preview, self.dwell = node, None
        key = cache_key(self.mode, node)
        if key not in self.previews:
            self.previews[key] = None
            _x, _y, W, H = self.preview_box()
            room = (W - 28 * self.u, H - 80 * self.u)
            threading.Thread(target=self.make_preview, args=(key, node, room), daemon=True).start()
        self.area.queue_draw()

    def make_preview(self, key, node, room):
        try:
            data = node['preview']()
            if data.get('image'):
                data['picture'] = scaled(data['image'], *room)
        except Exception as e:  # noqa: BLE001 - a broken file: say so
            data = {'title': node['name'], 'meta': '', 'image': None, 'lines': [str(e)[:70]]}
        self.previews[key] = data
        self.redraw_soon()

    def draw_preview(self, cr):
        if not self.preview:
            return
        data = self.previews.get(cache_key(self.mode, self.preview))
        x, y, W, H = self.preview_box()
        u = self.u
        p = 14 * u                          # the inner margin
        self.panel(cr, x, y, W, H)
        if data is None:
            self.text(cr, 'making the preview…', x + W / 2, y + H / 2, self.pt(10), bold=False, alpha=0.6, split=0)
            return
        area_h = H - 70 * u
        if data.get('picture'):
            paint(cr, data['picture'], x + W / 2, y + p + (area_h - 10 * u) / 2)
        elif data.get('lines'):
            lay = text_layout(cr)
            lay.set_font_description(Pango.FontDescription.from_string(
                f'DejaVu Sans Mono {max(7, min(12, round(W / 52)))}'))
            lay.set_width(int((W - 2 * p) * Pango.SCALE))
            lay.set_ellipsize(Pango.EllipsizeMode.END)
            lay.set_text('\n'.join(data['lines']), -1)
            cr.save()
            cr.rectangle(x + p, y + p, W - 2 * p, area_h - 8 * u)
            cr.clip()
            cr.move_to(x + p, y + p)
            cr.set_source_rgba(*FG, 0.85)
            PangoCairo.show_layout(cr, lay)
            cr.restore()
        self.preview_foot(cr, data, x + p, y + H, W - 2 * p)

    def preview_foot(self, cr, data, x, bottom, width):
        """under a thin line: the file's name, then its size and date"""
        u = self.u
        cr.move_to(x, bottom - 50 * u)
        cr.line_to(x + width, bottom - 50 * u)
        cr.set_source_rgba(1, 1, 1, 0.08)
        cr.stroke()
        lay = text_layout(cr)
        lay.set_font_description(font(self.pt(10), bold=True))
        lay.set_width(int(width * Pango.SCALE))
        lay.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        lay.set_text(data.get('title', ''), -1)
        cr.move_to(x, bottom - 42 * u)
        cr.set_source_rgba(*FG, 1)
        PangoCairo.show_layout(cr, lay)
        lay = text_layout(cr)
        lay.set_font_description(font(self.pt(8)))
        lay.set_text(data.get('meta', ''), -1)
        cr.move_to(x, bottom - 22 * u)
        cr.set_source_rgba(*FG, 0.6)
        PangoCairo.show_layout(cr, lay)
