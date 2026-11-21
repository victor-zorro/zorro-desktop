"""The AI part on screen: a panel beside the hub with the conversation and the question line."""
import time

from .keys import ENTER, typed
from .look import DIM, FG, Gdk, Pango, PangoCairo, font, show_split, text_layout

STYLES = {'q': (10, True, FG, 1.0), 'a': (10, False, FG, 0.88), 'meta': (8, False, DIM, 1.0)}
GAPS = {'q': 6, 'a': 4, 'meta': 18}     # room under a question, an answer, its dim line (unit u)
EMPTY = 'Ask anything: the answer comes here.'
HINT = 'Enter: ask · Esc: back · wheel: older · centre of the circle: new chat'
HINT_BUSY = 'answering… · Esc: stop'
LONGEST = 4000                          # letters in one question


class ChatView:
    def chat_box(self):
        """(x, y, width, height) of the panel: beside the hub, where the fan would be"""
        cx, cy, hub, *_ = self.fan()
        sw, sh, u = self.geo.width, self.geo.height, self.u
        W, H = min(600 * u, sw - 32 * u), min(640 * u, sh - 32 * u)
        if abs(cx - sw / 2) < 2:            # a dial in the middle: the panel to its right
            x, y = cx + hub + 28 * u, cy - H / 2
        else:
            x = cx - hub - 28 * u - W if cx > sw / 2 else cx + hub + 28 * u
            y = cy + hub - H if cy > sh / 2 else cy - hub
        return max(16 * u, min(sw - W - 16 * u, x)), max(16 * u, min(sh - H - 16 * u, y)), W, H

    def draw_chat(self, cr):
        x, y, W, H = self.chat_box()
        u, p = self.u, 18 * self.u
        left, width = x + p, W - 2 * p
        self.panel(cr, x, y, W, H)
        tw, _h = self.text_ext(cr, 'AI', self.pt(9))
        self.text(cr, 'AI', left + tw / 2, y + 20 * u, self.pt(9), alpha=0.6, split=1.0)
        nw, _h = self.text_ext(cr, 'New chat', self.pt(8), False)
        self.chat_new_at = (x + W - p - nw - 8 * u, y + 4 * u, x + W - p + 8 * u, y + 36 * u)
        self.text(cr, 'New chat', x + W - p - nw / 2, y + 20 * u, self.pt(8), bold=False, alpha=0.6, split=0)
        top, bottom = y + 40 * u, y + H - 80 * u
        self.chat_rule(cr, left, width, top)
        self.chat_body(cr, left, top + 8 * u, width, bottom - top - 12 * u)
        if self.chat.problem:
            self.chat_line(cr, self.chat.problem, left, bottom, width, 'meta')
        self.chat_rule(cr, left, width, bottom + 22 * u)
        caret = '▏' if int(time.time() * 2) % 2 else ' '
        if self.chat.text:
            self.chat_line(cr, f'›  {self.chat.text}{caret}', left, bottom + 30 * u, width, 'q')
        elif not self.chat.busy:
            self.chat_line(cr, f'›  {caret}type a question', left, bottom + 30 * u, width, 'meta')
        self.chat_line(cr, HINT_BUSY if self.chat.busy else HINT, left, y + H - 24 * u, width, 'meta')

    def chat_rule(self, cr, x, width, y):
        cr.move_to(x, y)
        cr.line_to(x + width, y)
        cr.set_source_rgba(1, 1, 1, 0.08)
        cr.set_line_width(1)
        cr.stroke()

    def chat_layout(self, cr, kind, text, width, wrap=True):
        """a block of the conversation laid out at the panel's width (kept between frames)"""
        key = (kind, text, int(width), wrap)
        hit = self.chat_layouts.get(key)
        if hit:
            PangoCairo.update_layout(cr, hit[0])
            return hit
        size, bold, _colour, _alpha = STYLES[kind]
        lay = text_layout(cr)
        lay.set_font_description(font(self.pt(size), bold))
        lay.set_width(int(width * Pango.SCALE))
        if wrap:
            lay.set_wrap(Pango.WrapMode.WORD_CHAR)
        else:
            lay.set_ellipsize(Pango.EllipsizeMode.START)
        lay.set_text(text, -1)
        if len(self.chat_layouts) > 80:
            self.chat_layouts.clear()
        self.chat_layouts[key] = (lay, lay.get_pixel_size()[1])
        return self.chat_layouts[key]

    def chat_show(self, cr, kind, lay, x, y):
        _size, bold, colour, alpha = STYLES[kind]
        if bold:
            show_split(cr, lay, x, y, alpha, 1.0)
            return
        cr.move_to(x, y)
        cr.set_source_rgba(*colour, alpha)
        PangoCairo.show_layout(cr, lay)

    def chat_line(self, cr, text, x, y, width, kind):
        """one line that never wraps: the start of it gives way when it is too long"""
        lay, _h = self.chat_layout(cr, kind, text, width, wrap=False)
        self.chat_show(cr, kind, lay, x, y)

    def chat_body(self, cr, x, y, width, height):
        """the conversation, the newest at the bottom; what does not fit scrolls away upward"""
        view = self.conf.get('ai_view', 'history')
        laid = [(kind, *self.chat_layout(cr, kind, text, width)) for kind, text in self.chat.blocks(view)]
        if not laid:
            self.chat_line(cr, EMPTY, x, y + 4 * self.u, width, 'meta')
            return
        total = sum(h + GAPS[kind] * self.u for kind, _lay, h in laid)
        self.chat_scroll = max(0, min(self.chat_scroll, total - height))
        cr.save()
        cr.rectangle(x - 4, y, width + 8, height)
        cr.clip()
        at = y + height + self.chat_scroll if total > height else y + total
        for kind, lay, h in reversed(laid):
            at -= h + GAPS[kind] * self.u
            if at + h < y:
                break
            if at < y + height:
                self.chat_show(cr, kind, lay, x, at)
        cr.restore()

    # -- input
    def chat_key(self, k, ev):
        c = self.chat
        if k == 'Escape':
            if c.busy:
                c.cancel()
            elif c.text:
                c.text = ''
            else:
                self.set_mode('apps')
        elif k in ENTER:
            if c.send():
                self.chat_scroll = 0
        elif k == 'BackSpace':
            c.text = c.text[:-1]
        elif k in ('Page_Up', 'Page_Down'):
            self.chat_scroll += (1 if k == 'Page_Up' else -1) * 300 * self.u
        elif not ev.state & Gdk.ModifierType.CONTROL_MASK and len(c.text) < LONGEST:
            c.text += typed(ev)

    def chat_click(self, ev):
        """a click in the panel stays in the panel; True when it was"""
        x, y, W, H = self.chat_box()
        if not (x <= ev.x <= x + W and y <= ev.y <= y + H):
            return False
        x0, y0, x1, y1 = self.chat_new_at or (0, 0, 0, 0)
        if ev.button == 1 and x0 <= ev.x <= x1 and y0 <= ev.y <= y1:
            self.chat_new()
        return True

    def chat_wheel(self, ev):
        step = 60 * self.u
        if ev.direction == Gdk.ScrollDirection.UP:
            self.chat_scroll += step
        elif ev.direction == Gdk.ScrollDirection.DOWN:
            self.chat_scroll -= step
        elif ev.direction == Gdk.ScrollDirection.SMOOTH:
            self.chat_scroll -= ev.get_scroll_deltas()[2] * step
        self.area.queue_draw()

    def chat_new(self):
        """New chat: the old conversation is put away, the panel is empty"""
        self.chat.new_chat()
        self.chat_scroll = 0
        self.area.queue_draw()
