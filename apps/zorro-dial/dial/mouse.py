"""The mouse: hover, rest (unfold), click, drag."""
import math
import time

from .look import Gdk, GLib
from .nodes import same


def is_app(a):
    """a real app (or the gear), not a tile or '+N'"""
    return bool(not a.get('tile') and a.get('id') and (not a['id'].startswith('__') or a.get('gear')))


class Mouse:
    def hit(self, x, y, slot=False):
        s = next((s for s in self.slots if (x - s[0]) ** 2 + (y - s[1]) ** 2 <= s[2] * s[2]), None)
        return s if slot else (s[3] if s else None)

    def plain_apps(self):
        """the apps as slices: nothing typed, no slice opened"""
        return self.mode == 'apps' and not self.filter and self.expanded is None

    def on_motion(self, _w, ev):
        if self.menu:
            k = self.menu_at(ev.x, ev.y)
            if k != self.menu['hover']:
                self.menu['hover'] = k
                self.area.queue_draw()
            return
        if self.press and not self.drag and self.plain_apps() and 'more' not in self.press[0]:
            a, px, py = self.press
            if (ev.x - px) ** 2 + (ev.y - py) ** 2 > 12 ** 2:
                self.hold_stop()
                self.drag = (a, ev.x, ev.y)
        if self.drag:
            self.drag = (self.drag[0], ev.x, ev.y)
            target = self.hit(ev.x, ev.y)
            self.hover = target if target is not self.drag[0] else None
            self.area.queue_draw()
            return
        slot = self.hit(ev.x, ev.y, slot=True)
        h = slot[3] if slot else None
        z = self.hub_at(ev.x, ev.y)
        key = self.music_key_at(ev.x, ev.y)
        if not same(h, self.hover) or z != self.hub_hover or key != self.hub_key:
            self.hover, self.hub_hover, self.hub_key = h, z, key
            if z in self.parts:
                self.start_fetch(self.parts[z])
            self.area.queue_draw()
        if self.preview and not same(h, self.preview):
            self.preview = None             # moved on: the preview goes
            self.area.queue_draw()
        self.rest_on(h, slot, ev.state & Gdk.ModifierType.MOD4_MASK)

    def rest_on(self, h, slot, at_once):
        """the mouse is on h: after a moment (or at once, with Super held) it unfolds"""
        part = self.parts.get(self.mode)
        if h and (h.get('kids') or h.get('preview')) and part is not None and part.tree:
            lv = slot[4]
            path = self.path.get(self.mode, [])
            done = same(self.preview, h) if not h.get('kids') else (lv < len(path) and same(path[lv], h))
            if done:
                return
            if at_once:
                self.unfold(h, lv)
            elif not (self.dwell and same(self.dwell[0], h)):
                self.dwell = (h, lv, time.time())
                if not self.dwell_id:
                    self.dwell_id = GLib.timeout_add(30, self.dwell_tick)
        elif self.dwell and not same(h, self.dwell[0]):
            self.dwell = None

    def on_release(self, _w, ev):
        self.hold_stop()
        press, drag = self.press, self.drag
        self.press = self.drag = None
        if ev.button != 1 or not press:
            return
        if not drag:                        # a click: start the app
            if same(self.hit(ev.x, ev.y), press[0]):
                self.activate(press[0])
            return
        if self.over_bin(ev.x, ev.y):
            self.hide_app(drag[0])
        else:
            self.drop(drag[0], ev.x, ev.y)
        self.area.queue_draw()

    def on_click(self, _w, ev):
        if self.menu:                       # a row of the hold menu, or anywhere else: close it
            k = self.menu_at(ev.x, ev.y)
            rows, self.menu = self.menu['rows'], None
            if k is not None:
                rows[k][1]()
            self.area.queue_draw()
            return
        if self.chat_mode() and self.chat_click(ev):
            return
        a = self.hit(ev.x, ev.y)
        z = self.hub_at(ev.x, ev.y)
        if self.plain_apps() and self.click_names(ev):
            return
        if a:
            self.click_on(a, ev)
        elif z and ev.button == 1:
            self.click_hub(z, ev)
        else:
            self.click_outside(ev)

    def click_names(self, ev):
        """the slice names: right-click renames, '+ slice' adds one; True when that was it"""
        lab = self.label_at(ev.x, ev.y)
        if lab is not None and ev.button == 3:
            self.start_rename(lab)
            return True
        if ev.button == 1 and self.add_label and abs(ev.x - self.add_label[0]) < 50 * self.u \
                and abs(ev.y - self.add_label[1]) < 14 * self.u:
            self.add_slice()
            return True
        if self.renaming is not None:       # clicked elsewhere: keep what was typed
            self.finish_rename(True)
        return False

    def click_on(self, a, ev):
        """a click on an app or a tile"""
        if ev.button == 3 and self.mode == 'apps' and is_app(a) and not self.filter:
            self.hide_app(a)                # right-click an app: out of the launcher
            self.area.queue_draw()
        elif ev.button == 3 and a.get('remove'):    # right-click a message: dismiss it
            self.keep_open({'act': a['remove'], 'refresh': True, 'up': 2})
        elif ev.button == 1:
            self.press = (a, ev.x, ev.y)    # start on release; moving it drags instead
            if self.mode == 'apps' and not self.filter and is_app(a) and 'more' not in a:
                self.hold_start(self.press)  # held still: its menu

    def click_hub(self, z, ev):
        key = self.music_key_at(ev.x, ev.y) if z == 'centre' else None
        if key:
            self.player_key(key)
        elif z == 'centre' and self.path.get(self.mode) and self.path[self.mode][-1].get('act'):
            self.path[self.mode][-1]['act']()           # open where you are in the tree
            self.close_dial()
        elif z == 'centre':
            self.centre_action()
        else:                               # a part of the circle: it stays (again: back to apps)
            self.set_mode('apps' if z == self.mode else z)

    def click_outside(self, ev):
        """outside the dial: close"""
        cx, cy, _hub, a0, a1, rings = self.fan()
        dx, dy = ev.x - cx, ev.y - cy
        ang = math.degrees(math.atan2(dy, dx)) % 360
        inside_angle = any(a0 <= ang + k <= a1 for k in (0, 360, -360))
        if dx * dx + dy * dy > rings[-1][1] ** 2 or not inside_angle:
            self.close_dial()

    def on_scroll(self, _w, ev):
        if self.chat_mode():
            self.chat_wheel(ev)
        return True
