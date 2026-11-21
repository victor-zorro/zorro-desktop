"""System → Hardware → Screens: where the second and third screen sit, and their resolution.
A change shows at once and goes back by itself unless you press Keep (a wrong choice can
leave you without a picture)."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk  # noqa: E402

from . import screens
from .base import update_conf
from .ui import Pages, button, combo, form, heading, in_bg, note

KEEP_SECONDS = 12


class ScreensPages:
    def screens_page(self):
        box = Pages()
        box.add(heading('Screens', 'Screens'))
        self.scr_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.add(self.scr_rows)
        box.add(note('Changes show at once. Press Keep within a few seconds, or the picture goes back.'))
        self.scr_msg = note()
        self.scr_keep = button('Keep', self.screens_keep, primary=True, no_show_all=True)
        bottom = Gtk.Box(spacing=12)
        bottom.add(self.scr_keep)
        bottom.add(self.scr_msg)
        box.footer(bottom)
        self.scr_seen, self.scr_back, self.scr_timer, self.scr_new = None, None, None, {}
        self.when_shown('hardware', self.screens_fill)
        self.timers.append(GLib.timeout_add_seconds(4, self.screens_tick))
        return box

    def screens_tick(self):
        """a screen plugged in or out: show it (only while you look at this menu)"""
        if self.tab_on('hardware') and not self.scr_timer:
            in_bg(lambda: GLib.idle_add(self.screens_fill, screens.read()))
        return True

    def screens_fill(self, now=None):
        now = now or screens.read()
        live = screens.connected(now)
        sig = [(s['name'], s['on'], s['size'], tuple(s['modes'])) for s in live]
        if sig == self.scr_seen:
            return False
        self.scr_seen, self.scr_now = sig, now
        for c in self.scr_rows.get_children():
            c.destroy()
        conf = screens.saved()
        layout = conf.get('layout') if isinstance(conf.get('layout'), dict) else {}
        for s in live:
            self.scr_rows.add(self.screen_row(s, layout.get(s['name'], {})))
        if len(live) > 1:
            names = {s['name']: s['name'] for s in live}
            main = conf.get('main') if conf.get('main') in names else next(
                (s['name'] for s in live if s['primary']), live[0]['name'])
            self.scr_rows.add(form([('Main screen', combo(names, main, lambda v: self.screens_set(main=v)))]))
        else:
            self.scr_rows.add(note('Connect a second screen (HDMI, USB-C or a dock): it shows here.'))
        self.scr_rows.show_all()
        self.scr_keep.hide()
        return False

    def screen_row(self, s, choice):
        title = Gtk.Label(xalign=0)
        kind = 'this device' if s['laptop'] else 'connected'
        title.set_markup(f'<b>{GLib.markup_escape_text(s["name"])}</b>  {kind}'
                         + (f', {s["size"]}' if s['on'] else ', off'))
        where = {'on': 'On', 'off': 'Off (only with another screen on)'} if s['laptop'] else screens.WHERE
        current = choice.get('where') or (('on' if s['laptop'] else 'right') if s['on'] else 'off')
        modes = {'auto': 'Best for this screen', **{m: m.replace('x', ' × ') for m in s['modes'][:12]}}
        rows = [('Where', combo(where, current if current in where else next(iter(where)),
                                lambda v, n=s['name']: self.screens_set(n, where=v))),
                ('Resolution', combo(modes, choice.get('mode') if choice.get('mode') in modes else 'auto',
                                     lambda v, n=s['name']: self.screens_set(n, mode=v)))]
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        col.add(title)
        col.add(form(rows))
        return col

    def screens_set(self, name=None, main=None, **choice):
        """one choice changed: show it now, and wait for Keep"""
        conf = dict(self.scr_new if self.scr_back else screens.saved())    # also what waits for Keep
        layout = dict(conf.get('layout') if isinstance(conf.get('layout'), dict) else {})
        if name:
            layout[name] = {**layout.get(name, {}), **choice}
        new = {'layout': layout, 'main': main or conf.get('main')}
        if not self.scr_back:
            self.scr_back = (screens.restore_args(self.scr_now), conf)
        err = screens.apply(screens.plan(self.scr_now, new))
        if err:
            self.scr_msg.set_text(f'Not possible: {err}')
            return
        self.scr_new = new
        self.scr_left = KEEP_SECONDS
        self.scr_keep.show()
        self.screens_count()
        if not self.scr_timer:
            self.scr_timer = GLib.timeout_add_seconds(1, self.screens_count_down)

    def screens_count(self):
        self.scr_msg.set_text(f'Keep this? Going back in {self.scr_left} s.')

    def screens_count_down(self):
        self.scr_left -= 1
        if self.scr_left > 0:
            self.screens_count()
            return True
        self.scr_timer = None
        err = self.screens_back()
        self.scr_msg.set_text(f'Could not put it back: {err}' if err else 'Put back as it was.')
        self.scr_seen = None
        self.screens_fill()
        return False

    def screens_back(self):
        """undo a change that was not kept (also when the window closes); '' or the error"""
        if self.scr_timer:
            GLib.source_remove(self.scr_timer)
            self.scr_timer = None
        back, self.scr_back = getattr(self, 'scr_back', None), None
        return screens.apply(back[0]) if back else ''

    def screens_keep(self):
        if self.scr_timer:
            GLib.source_remove(self.scr_timer)
            self.scr_timer = None
        self.scr_back = None
        update_conf(None, screens=self.scr_new)
        self.scr_keep.hide()
        self.scr_msg.set_text('Kept: also used the next time you log in.')
        self.scr_seen = None
        self.screens_fill()
