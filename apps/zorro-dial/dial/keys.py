"""The keyboard: typing searches (or asks the AI), Enter starts, Esc goes one step back."""
from .look import Gdk

ENTER = ('Return', 'KP_Enter')


def typed(ev):
    """the letter this key press types, or ''"""
    code = Gdk.keyval_to_unicode(ev.keyval)
    ch = chr(code) if code else ''
    return ch if ch.isprintable() else ''


class Keys:
    def on_key(self, _w, ev):
        k = Gdk.keyval_name(ev.keyval) or ''
        if self.menu:                       # the hold menu: Esc closes it, other keys too
            self.menu = None
        elif self.renaming is not None:     # typing a slice's new name
            self.rename_key(k, ev)
        elif k.startswith('Super') or ev.state & Gdk.ModifierType.MOD4_MASK:
            return True                     # holding Super unfolds; its xcape Super+Space is not typing
        elif self.chat_mode():
            self.chat_key(k, ev)
        elif k == 'Escape':
            self.step_back()
            return True
        elif k in ENTER:
            self.enter()
            return True
        elif k == 'BackSpace':
            self.filter = self.filter[:-1]
            self.hover = None
        else:
            ch = typed(ev)
            if not ch or ev.state & Gdk.ModifierType.CONTROL_MASK:
                return True
            self.filter += ch
            self.hover = None
        self.area.queue_draw()
        return True

    def rename_key(self, k, ev):
        if k in ENTER:
            self.finish_rename(True)
        elif k == 'Escape':
            self.finish_rename(False)
        elif k == 'BackSpace':
            self.rename_text = self.rename_text[:-1]
        elif len(self.rename_text) < 20:
            self.rename_text += typed(ev)

    def step_back(self):
        """Esc: what was typed goes, else one level up the tree, else back to the apps, else close"""
        if self.filter:
            self.filter = ''
        elif self.mode != 'apps' and self.path.get(self.mode):
            self.path[self.mode].pop()
        elif self.mode != 'apps':
            self.set_mode('apps')
        elif self.expanded is not None:
            self.expanded = None
        else:
            self.close_dial()
            return
        self.area.queue_draw()

    def enter(self):
        if self.mode in ('music', 'notes') and self.filter:
            self.parts[self.mode].search(self.filter)
            if self.mode == 'notes':
                self.close_dial()           # the note opens in Obsidian
                return
            self.filter = ''
            self.area.queue_draw()
            return
        found = self.matches() if self.filter else []
        a = self.hover or (found[0] if found else None)
        if a:
            self.activate(a)
