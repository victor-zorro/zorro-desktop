"""The devices nearby on the getting page: the list fills by itself and is searched again
every few seconds while the page is open. A device that is not sending can be asked to
(a knock: it shows a notification there); its row turns ready once it sends."""
from .. import find
from .widgets import GLib, Gtk, ROUTE, background, btn, label

EVERY = 4000                    # ms between two searches
ASKED = 'Then choose Send there and type its code here.'
NOTHING = 'No device found yet. You can type its name or address.'


def row_text(f):
    how = ROUTE.get(f['via'], f['via'])
    ready = 'ready to send' if f['sending'] else 'not sending yet'
    esc = GLib.markup_escape_text
    return (f"<b>{esc(f['name'])}</b>  <span alpha='65%'>{esc(how)} · {esc(f['host'])}</span>\n"
            f"<span alpha='{100 if f['sending'] else 65}%'>{ready}</span>")


class NearbyList:
    """page: the page it sits on (its .win shows it); picked(host, ready); say(text)"""

    def __init__(self, page, picked, say, want=None):
        self.page, self.picked, self.say, self.want = page, picked, say, want
        self.devices, self.chosen, self.busy = None, None, False
        self.list = Gtk.ListBox()
        self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list.connect('row-selected', self.on_row)
        self.box = Gtk.ScrolledWindow(min_content_height=120, max_content_height=200,
                                      propagate_natural_height=True)
        self.box.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.box.add(self.list)
        self.ask = btn('Ask it to send', self.knock)
        self.hint = label(ASKED, dim=True)
        for w in (self.ask, self.hint):
            w.set_no_show_all(True)
        page.win.every(EVERY, self.tick)
        GLib.idle_add(lambda: self.tick() and False)    # once the page is on screen

    def tick(self):
        """search again (in a thread); the timer ends when the page is gone"""
        if self.page.win.page is not self.page:
            return False
        if not self.busy:
            self.busy = True
            background(self.page, find.discover, self.show, self.failed)
        return True

    def failed(self, e):
        self.busy = False
        self.say(f'Could not search: {e}')

    def show(self, devices):
        self.busy = False
        if devices == self.devices:
            return
        self.devices = devices
        self.say('' if devices else NOTHING)
        keep = self.chosen['host'] if self.chosen else self.want
        for c in self.list.get_children():
            self.list.remove(c)
        for f in devices:
            r = Gtk.ListBoxRow()
            r.device = f
            r.add(label(row_text(f), markup=True))
            self.list.add(r)
            if f['host'] == keep:
                self.list.select_row(r)
        self.list.show_all()
        if len(devices) == 1 and not self.list.get_selected_row():
            self.list.select_row(self.list.get_row_at_index(0))
        if not self.list.get_selected_row():
            self.on_row(self.list, None)

    def on_row(self, _lb, row):
        self.chosen = row.device if row else None
        waiting = bool(self.chosen and not self.chosen['sending'])
        self.ask.set_visible(waiting)
        self.hint.set_visible(waiting)
        if self.chosen:
            self.want = None
            self.picked(self.chosen['host'], self.chosen['sending'])

    def knock(self):
        f = self.chosen
        if not f:
            return
        self.say(f"Asking {f['name']}…")

        def done(r):
            self.say(f"{f['name']} shows a notification now." if r.get('ok') else
                     f"{f['name']}: {r.get('error') or 'no answer'}")
        background(self.page, lambda: find.knock(f['host']), done,
                   lambda e: self.say(f'Could not ask: {e}'))
