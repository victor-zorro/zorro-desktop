"""What a click does: start an app, run a tile's action, switch part, the hub centre's action."""
import sys
import threading

from . import usage
from .look import Gio, GLib
from .nodes import cache_key, same


class Actions:
    def chat_mode(self):
        """the kept part is a chat (AI): a panel instead of the fan"""
        return bool(getattr(self.parts.get(self.mode), 'chat', False))

    def set_mode(self, mode):
        """keep another part of the hub (or the apps)"""
        if self.chat_mode():
            self.chat.cancel()
        self.mode = mode
        self.expanded, self.filter, self.hover = None, '', None
        if self.chat_mode():
            self.chat_scroll = 0
            self.chat.open()
        self.area.queue_draw()

    def activate(self, a):
        """a click (or Enter) on something in the fan"""
        if 'more' in a:                     # "+N": the whole slice
            self.expanded, self.hover = a['more'], None
        elif a.get('gear'):                 # the gear: all settings apps
            self.expanded, self.hover = 'gear', None
        elif not a.get('tile'):
            self.launch(a)
            return
        elif a.get('act') and a.get('keep'):
            self.keep_open(a)               # a switch: do it, then show the new state
        elif a.get('act'):
            # close first (input free again), then act: a slow command (a clipboard owner that
            # does not answer) can no longer freeze keyboard and mouse.
            # Not a daemon thread: the process waits for it before it ends.
            self.close_dial()
            threading.Thread(target=a['act'], daemon=False).start()
            return
        elif a.get('kids'):                 # nothing to start ("N more"): a click unfolds it
            lv = next((sl[4] for sl in self.slots if same(sl[3], a)), None)
            if lv is not None:
                self.unfold(a, lv)
        self.area.queue_draw()

    def launch(self, a):
        usage.record(a['id'])
        try:
            info = Gio.DesktopAppInfo.new_from_filename(a['path'])
            if info:
                info.launch([], None)
        except GLib.Error as e:
            print(f'zorro-dial: {a["name"]}: {e.message}', file=sys.stderr)
        self.close_dial()

    def keep_open(self, a):
        """run a tile's action in a thread with the dial staying open, then show what changed.
        The part is remembered now: by the time the action is done another may be kept."""
        mode = self.mode
        if a.get('start'):
            a['start']()

        def work():
            try:
                a['act']()
                if a.get('refresh'):
                    self.renew_part(mode)
            except Exception as e:      # noqa: BLE001 - a failed action must not stop the dial
                print(f'zorro-dial: {mode}: {type(e).__name__}: {e}', file=sys.stderr)
            self.on_gtk(lambda: self.after_action(a, mode))
        threading.Thread(target=work, daemon=False).start()     # the process waits for it to finish
        self.area.queue_draw()

    def renew_part(self, key):
        """the part's data changed: read it into a fresh copy and swap that in (in a thread)"""
        part = self.parts.get(key)
        if part is not None:
            self.parts[key] = part.renewed()

    def after_action(self, a, mode):
        path = self.path.get(mode) or []
        if a.get('refresh'):
            self.forget_kids(mode)
            del path[max(0, len(path) - a.get('up', 0)):]       # gone: back up the tree
            first, self.path[mode] = path[:1], []
            if self.mode == mode and first:
                self.reopen(first[0])
        elif path and self.mode == mode:    # a tree: read that branch again (Like -> Unlike)
            self.kids.pop(cache_key(mode, path[-1]), None)
            self.expand(path[-1], len(path) - 1)

    def reopen(self, old):
        """unfold again what was unfolded in the first ring, from the part's fresh data"""
        node = next((t for t in self.parts[self.mode].roots() if same(t, old)), None)
        if node and node.get('kids'):
            self.expand(node, 0)

    def centre_action(self):
        """the hub centre clicked: the kept part's main action"""
        part = self.parts.get(self.mode)
        c = part.centre() if part else None
        if not c:
            return
        if self.chat_mode():
            self.chat_new()
        elif part.key in ('notes', 'files'):
            threading.Thread(target=c[1], daemon=True).start()
            self.close_dial()
        else:
            self.keep_open({'act': c[1], 'refresh': True, 'up': len(self.path.get(self.mode) or [])})

    def player_key(self, what):
        """previous / play-pause / stop / next: do it, then read what plays now"""
        def work():
            try:
                self.parts['music'].control(what)
                self.renew_part('music')
            except Exception as e:      # noqa: BLE001 - a player that went away
                print(f'zorro-dial: music {what}: {e}', file=sys.stderr)
            self.redraw_soon()
        threading.Thread(target=work, daemon=True).start()
