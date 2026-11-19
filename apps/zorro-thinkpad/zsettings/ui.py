"""shared app widgets"""
import sys

from .base import APPS

sys.path.insert(0, str(APPS / 'zorro-fx'))
try:                                    # the one palette (apps/zorro-fx/zorro_style.py)
    from zorro_style import MARKS, mark  # noqa: E402,F401
except ImportError:
    MARKS = {'on': ('●', '#19e6ff'), 'ok': ('✓', '#19e6ff'), 'warn': ('⚠', '#ff2a4a'), 'off': ('○', '#6f7079')}

    def mark(state, symbol=None):
        sym, col = MARKS.get(state, MARKS['off'])
        return f'<span foreground="{col}">{symbol or sym}</span>'

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk


# ---- shared widgets of the app: headings, sub-pages, sidebar groups ---

KEY_TABLE = [
    ('F1', 'Sound on / off'), ('F2 / F3', 'Volume down / up (up also unmutes)'),
    ('F4', 'Microphone on / off (the key light shows "off")'),
    ('F5 / F6', 'Screen brightness'), ('F7', 'External screen: extend → mirror → external → laptop'),
    ('F8', 'Airplane mode: all radios off / on'), ('F9', 'Opens this app'),
    ('F10 / F11', 'Mobile data (LTE) on / off'), ('F12 ★', 'Your choice, below'),
    ('Fn + Space', 'Keyboard light off → low → high (remembered)'),
    ('PrtSc', 'Screenshot: drag an area, click a window or Space for the whole screen'),
    ('Fn + PrtSc', 'Screenshot of an area right away'), ('Alt + PrtSc', 'Screenshot of the active window'),
]



def heading(text, page=None):
    """a bold heading; page='Title' also starts a new sub-page (sidebar entry)"""
    lb = Gtk.Label(xalign=0, margin_top=14)
    lb.set_markup(f'<b>{GLib.markup_escape_text(text)}</b>')
    lb.zpage = page
    return lb

def idle(fn, *args):
    """run fn(*args) on the main loop soon. Normal priority: at idle priority the app's own
    particle animation could keep the loop busy and the result would never show"""
    return GLib.idle_add(fn, *args, priority=GLib.PRIORITY_DEFAULT)


def note(text=''):
    lb = Gtk.Label(label=text, xalign=0, wrap=True)
    lb.get_style_context().add_class('dim-label')
    return lb

def page():
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=18)
    sw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
    sw.add(box)
    return sw, box

class Pages:
    """one main section: short sub-pages with a sidebar on the left (no long pages),
    plus an optional header above and footer below that all sub-pages share"""
    def __init__(self):
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                               vexpand=True, hexpand=True)
        self.top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_start=18,
                              margin_end=18, margin_bottom=12)
        self.cur, self.n = None, 0

    def new(self, title):
        sw, box = page()
        box.set_margin_top(6)
        self.stack.add_titled(sw, f'p{self.n}', title)
        self.n += 1
        self.cur = box

    def add(self, w):
        title = getattr(w, 'zpage', None)
        if title:
            self.new(title)
            if w.get_text() == title:
                return                  # the sidebar already says it
        elif self.cur is None:
            self.new('General')
        self.cur.add(w)

    def header(self, w):
        self.top.add(w)

    def footer(self, w):
        self.bottom.add(w)

    def parts(self):
        """[(title, page)] taken out of the builder stack"""
        out = []
        for c in self.stack.get_children():
            out.append((self.stack.child_get_property(c, 'title'), c))
            self.stack.remove(c)
        return out

class Group:
    """one top tab: a sidebar with section headings and their sub-pages; each section
    can have a header (above) and footer (below) shared by its sub-pages"""
    def __init__(self):
        self.content = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                                 vexpand=True, hexpand=True)
        self.tops = Gtk.Stack(vhomogeneous=False, interpolate_size=False)
        self.bottoms = Gtk.Stack(vhomogeneous=False, interpolate_size=False)
        self.side = Gtk.ListBox(selection_mode=Gtk.SelectionMode.BROWSE)
        self.side.get_style_context().add_class('zside')
        self.side.connect('row-selected', self.on_row)
        self.ids = {}

    def heading(self, title):
        """a group heading in the sidebar (capitals) above several sections"""
        head = Gtk.ListBoxRow(selectable=False, activatable=False)
        lb = Gtk.Label(xalign=0, margin_start=12, margin_top=12, margin_bottom=2)
        lb.set_markup(f'<small><b>{GLib.markup_escape_text(title.upper())}</b></small>')
        lb.get_style_context().add_class('dim-label')
        head.add(lb)
        self.side.add(head)

    def section(self, name, title, pages, sub=False):
        """title None: no heading of its own, the sub-pages follow the section above.
        A section with one page of the same name shows just that page, as a top-level row.
        sub: the title is a small sub-heading under a group heading (Group.heading)."""
        parts = list(pages.parts())
        flat = bool(title) and len(parts) == 1 and parts[0][0].lower() == title.lower()
        if flat:
            title = None
        if title and sub:
            head = Gtk.ListBoxRow(selectable=False, activatable=False)
            lb = Gtk.Label(xalign=0, margin_start=16, margin_top=6, margin_bottom=0)
            lb.set_markup(f'<small>{GLib.markup_escape_text(title)}</small>')
            lb.get_style_context().add_class('dim-label')
            head.add(lb)
            self.side.add(head)
        elif title:
            head = Gtk.ListBoxRow(selectable=False, activatable=False)
            lb = Gtk.Label(xalign=0, margin_start=12, margin_top=12, margin_bottom=2)
            lb.set_markup(f'<small><b>{GLib.markup_escape_text(title.upper())}</b></small>')
            lb.get_style_context().add_class('dim-label')
            head.add(lb)
            self.side.add(head)
        self.tops.add_named(pages.top, name)
        self.bottoms.add_named(pages.bottom, name)
        for i, (sub_name, w) in enumerate(parts):
            pid = f'{name}:{i}'
            self.content.add_named(w, pid)
            row = Gtk.ListBoxRow()
            row.add(Gtk.Label(label=sub_name, xalign=0,
                              margin_start=12 if flat and not sub else 26 if title and sub else 22,
                              margin_end=12, margin_top=6, margin_bottom=6))
            row.zid, row.zsec = pid, name
            self.ids[pid] = row
            self.side.add(row)

    def on_row(self, _lb, row):
        if row is None:
            return
        self.content.set_visible_child_name(row.zid)
        self.tops.set_visible_child_name(row.zsec)
        self.bottoms.set_visible_child_name(row.zsec)

    def select(self, pid=None):
        row = self.ids.get(pid) or next(iter(self.ids.values()), None)
        if row:
            self.side.select_row(row)

    def widget(self):
        sw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        sw.set_size_request(190, -1)
        sw.add(self.side)
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        main.add(self.tops)
        main.add(self.content)
        main.add(self.bottoms)
        h = Gtk.Box()
        h.add(sw)
        h.add(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        h.add(main)
        return h

def radios(options, current, on_pick):
    """vertical radio group; options: [(key, label)]"""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    group = None
    for key, label in options:
        rb = Gtk.RadioButton.new_with_label_from_widget(group, label)
        group = group or rb
        rb.set_active(key == current)
        rb.connect('toggled', lambda b, k=key: b.get_active() and on_pick(k))
        box.add(rb)
    return box


_later = {}


def later(key, fn, ms=400):
    """run fn once typing / sliding has rested for ms (one config write, not one per key)"""
    if _later.get(key):
        GLib.source_remove(_later[key][0])
    _later[key] = (GLib.timeout_add(ms, lambda: (_later.pop(key, None), fn()) and False), fn)


def flush_later():
    """the window closes: do what was still waiting now"""
    for key, (tid, fn) in list(_later.items()):
        GLib.source_remove(tid)
        _later.pop(key, None)
        try:
            fn()
        except Exception as e:      # noqa: BLE001
            print('zorro: on close:', e)


def in_bg(fn, *args):
    """a command in a thread, so the window never waits for it (nmcli, pactl, v4l2-ctl)"""
    import threading
    threading.Thread(target=fn, args=args, daemon=True).start()


# ---- form widgets, the same on every page (one spacing, one look) --------------------------
ROW, COL = 8, 12


def form(rows, row_spacing=ROW):
    """label | widget rows in a grid"""
    g = Gtk.Grid(column_spacing=COL, row_spacing=row_spacing)
    for i, (text, w) in enumerate(rows):
        g.attach(Gtk.Label(label=text, xalign=0), 0, i, 1, 1)
        g.attach(w, 1, i, 1, 1)
    return g


def combo(options, current, on_change):
    """options: {id: label}; on_change(id)"""
    c = Gtk.ComboBoxText()
    for k, text in options.items():
        c.append(k, text)
    c.set_active_id(current)
    c.connect('changed', lambda w: on_change(w.get_active_id()))
    return c


def scale(lo, hi, step, value, on_change, fmt=None, digits=None):
    """a horizontal slider, value shown on the right; on_change(value rounded to 2 decimals)"""
    sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, step)
    sc.set_hexpand(True)
    sc.set_digits(digits if digits is not None else (2 if step < 0.1 else 1 if step < 1 else 0))
    sc.set_value(float(value))
    sc.set_value_pos(Gtk.PositionType.RIGHT)
    if fmt:
        sc.connect('format-value', lambda w, v: fmt(v))
    sc.connect('value-changed', lambda w: on_change(round(w.get_value(), 2)))
    return sc


def switch(value, on_change):
    sw = Gtk.Switch(active=bool(value), halign=Gtk.Align.START)
    sw.connect('notify::active', lambda w, _p: on_change(w.get_active()))
    return sw


def colour(value, on_change):
    """a colour button; value and on_change use '#rrggbb'"""
    from gi.repository import Gdk
    b = Gtk.ColorButton(halign=Gtk.Align.START)
    c = Gdk.RGBA()
    c.parse(value)
    b.set_rgba(c)
    b.connect('color-set', lambda w: on_change('#%02x%02x%02x' % tuple(
        round(x * 255) for x in (w.get_rgba().red, w.get_rgba().green, w.get_rgba().blue))))
    return b


# ---- device lists: one row look for Hardware, Printers, Audio and Network ------------------
LIST = 10                               # space between the rows of a device list


def device_list(**kw):
    """the box that holds device_row()s"""
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=LIST, **kw)


def button(label, cb, primary=False, **kw):
    """a button; primary: the one main action (the accent colour)"""
    b = Gtk.Button(label=label, **kw)
    if primary:
        b.get_style_context().add_class('suggested-action')
    b.connect('clicked', lambda _b: cb())
    return b


def device_row(title, detail='', acts=(), icon=None, state=None, sub=False, below=()):
    """one row of a device list:  icon | mark  name / detail / below | actions.
    icon: an icon name (None: no icon). state: a MARKS key ('on', 'ok', 'warn', 'off') shown
    before the name, None for none. sub: a part of the row above (indented, name not bold).
    below: widgets under the detail (a volume slider). acts: (label, cb) buttons,
    (label, cb, True) for the main one, or a ready widget. row.zdetail: the detail label
    (None without a detail), so a caller can update it in place."""
    row = Gtk.Box(spacing=12)
    if icon or sub:
        img = Gtk.Image.new_from_icon_name(icon or 'go-next-symbolic', Gtk.IconSize.DND)
        img.set_pixel_size(32)              # also an app icon that only comes in big sizes
        img.set_opacity(0 if sub else 1)
        row.add(img)
    if sub:
        row.set_margin_start(28)
    txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
    name = GLib.markup_escape_text(title)
    head = Gtk.Label(xalign=0)
    head.set_markup((f'{mark(state)}  ' if state else '') + (name if sub else f'<b>{name}</b>'))
    txt.add(head)
    row.zdetail = None
    if detail:
        row.zdetail = note(detail)
        row.zdetail.set_selectable(True)
        row.zdetail.set_can_focus(False)
        txt.add(row.zdetail)
    for w in below:
        txt.add(w)
    row.add(txt)
    for a in acts:
        if isinstance(a, Gtk.Widget):
            a.set_valign(Gtk.Align.CENTER)
            row.add(a)
        else:
            row.add(button(a[0], a[1], primary=len(a) > 2 and a[2], valign=Gtk.Align.CENTER))
    return row
