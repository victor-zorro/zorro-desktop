"""shared app widgets"""
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

    def section(self, name, title, pages):
        """title None: no heading of its own, the sub-pages follow the section above"""
        if title:
            head = Gtk.ListBoxRow(selectable=False, activatable=False)
            lb = Gtk.Label(xalign=0, margin_start=12, margin_top=12, margin_bottom=2)
            lb.set_markup(f'<small><b>{GLib.markup_escape_text(title.upper())}</b></small>')
            lb.get_style_context().add_class('dim-label')
            head.add(lb)
            self.side.add(head)
        self.tops.add_named(pages.top, name)
        self.bottoms.add_named(pages.bottom, name)
        for i, (sub, w) in enumerate(pages.parts()):
            pid = f'{name}:{i}'
            self.content.add_named(w, pid)
            row = Gtk.ListBoxRow()
            row.add(Gtk.Label(label=sub, xalign=0, margin_start=22, margin_end=12,
                              margin_top=6, margin_bottom=6))
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
