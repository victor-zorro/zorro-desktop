"""The few widgets every page uses, and the one look (apps/zorro-fx/zorro_style.py)."""
import os
import subprocess
import sys
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import services  # noqa: E402

sys.path.insert(0, str(Path(os.path.realpath(__file__)).parent.parent.parent / 'zorro-fx'))
try:
    from zorro_style import FONT, HEX, mark  # noqa: E402
except ImportError:
    FONT = 'DejaVu Sans Mono'
    HEX = {'BG': '#05070a', 'FG': '#d8d8de', 'DIM': '#6f7079', 'RED': '#ff2a4a', 'CYAN': '#19e6ff'}

    def mark(state, symbol=None):
        sym, col = {'on': ('●', HEX['CYAN']), 'warn': ('⚠', HEX['RED'])}.get(state, ('○', HEX['DIM']))
        return f'<span foreground="{col}">{symbol or sym}</span>'

LINE = 'rgba(255,255,255,.16)'
WRAP = 82           # characters a wrapped line may take: the page's width at the window's size
CSS = f'''
.zintel, .zintel * {{ font-family: "{FONT}"; }}
.zintel, .zintel.background {{ background: {HEX['BG']}; color: {HEX['FG']}; }}
messagedialog.zintel {{ border: 1px solid {LINE}; }}
.zintel scrolledwindow, .zintel viewport, .zintel list,
.zintel list row, .zintel stack {{ background: none; }}
.zintel label {{ color: {HEX['FG']}; }}
.zintel .dim {{ color: {HEX['DIM']}; }}
.zintel .warn {{ color: {HEX['RED']}; }}
.zintel .you {{ color: {HEX['CYAN']}; }}
.zintel .ztitle {{ font-size: 15pt; }}
.zintel .zmenu {{ border-right: 1px solid {LINE}; outline: none; }}
.zintel .zmenu row {{ padding: 9px 16px; }}
.zintel .zmenu row:selected {{ background: rgba(25,230,255,.10); }}
.zintel .zmenu row:selected label {{ color: {HEX['CYAN']}; }}
.zintel .zbox {{ border: 1px solid {LINE}; border-radius: 4px; }}
.zintel .zbox row {{ border-bottom: 1px solid rgba(255,255,255,.07); padding: 8px 10px; }}
.zintel .zbox row:selected {{ background: rgba(25,230,255,.08); }}
.zintel button, .zintel entry, .zintel spinbutton, .zintel combobox button {{
  background: none; border: 1px solid {LINE}; border-radius: 4px; box-shadow: none;
  color: {HEX['FG']}; text-shadow: none; -gtk-icon-shadow: none; }}
.zintel button:hover {{ border-color: {HEX['FG']}; }}
.zintel button.main, .zintel button.main label {{ color: {HEX['CYAN']}; }}
.zintel button.main {{ border-color: {HEX['CYAN']}; }}
.zintel button:disabled, .zintel button:disabled label,
.zintel entry:disabled {{ color: {HEX['DIM']}; border-color: rgba(255,255,255,.08); }}
.zintel button.source {{ border: none; padding: 1px 4px; min-height: 0; }}
.zintel button.source label {{ color: {HEX['DIM']}; }}
.zintel button.source:hover label {{ color: {HEX['CYAN']}; }}
.zintel entry:focus {{ border-color: {HEX['CYAN']}; }}
.zintel switch {{ background: none; border: 1px solid {LINE}; }}
.zintel switch:checked {{ background: {HEX['CYAN']}; }}
.zintel progressbar trough, .zintel levelbar trough {{
  background: rgba(255,255,255,.08); border: none; min-height: 4px; }}
.zintel progressbar progress, .zintel levelbar block.filled {{
  background: {HEX['CYAN']}; border: none; min-height: 4px; }}
.zintel levelbar block.empty {{ background: none; border: none; }}
'''


def install_look(window):
    settings = Gtk.Settings.get_default()
    if settings is not None:
        settings.set_property('gtk-application-prefer-dark-theme', True)
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    window.get_style_context().add_class('zintel')


def post(fn, *args):
    """run fn(*args) once on the main loop"""
    GLib.idle_add(lambda: fn(*args) and False, priority=GLib.PRIORITY_DEFAULT)


def label(text='', css=None, wrap=False, **kw):
    lb = Gtk.Label(label=text, xalign=0, wrap=wrap, **kw)
    if wrap:
        lb.set_line_wrap_mode(2)        # word, then character: long paths wrap too
        lb.set_max_width_chars(WRAP)
    if css:
        lb.get_style_context().add_class(css)
    return lb


def note(text='', **kw):
    return label(text, 'dim', wrap=True, **kw)


def marked(state, text):
    """a line with a status mark in front: ● on, ○ off, ⚠ warning"""
    lb = label(wrap=True)
    lb.set_markup(f'{mark(state)}  {GLib.markup_escape_text(text)}')
    return lb


def button(text, action, main=False, css=None, **kw):
    b = Gtk.Button(label=text, **kw)
    for name in (('main',) if main else ()) + ((css,) if css else ()):
        b.get_style_context().add_class(name)
    b.connect('clicked', lambda _b: action())
    return b


def combo(options, current, on_change):
    """options: {id: label}; on_change(id) when the user picks one"""
    c = Gtk.ComboBoxText()
    c.set_size_request(230, -1)
    fill_combo(c, options, current)
    c.connect('changed', lambda w: getattr(w, 'filling', False) or on_change(w.get_active_id()))
    return c


def fill_combo(c, options, current):
    """new entries without telling on_change"""
    c.filling = True
    c.remove_all()
    for key, text in options.items():
        c.append(key, text)
    c.set_active_id(current if current in options else next(iter(options), None))
    c.filling = False


def scrolled(child, height=120):
    """the one place that may scroll: a list in its own box"""
    sw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, hexpand=True)
    sw.set_min_content_height(height)
    sw.get_style_context().add_class('zbox')
    sw.add(child)
    return sw


def clear(container):
    for child in container.get_children():
        container.remove(child)


def open_file(path):
    try:
        subprocess.Popen(['xdg-open', str(path)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def confirm(window, question, yes, action):
    """ask once before something that cannot be undone"""
    dialog = Gtk.MessageDialog(transient_for=window, modal=True, message_type=Gtk.MessageType.WARNING,
                               text=question)
    dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
    dialog.add_button(yes, Gtk.ResponseType.OK)
    dialog.get_style_context().add_class('zintel')

    def answered(d, response):
        d.destroy()
        if response == Gtk.ResponseType.OK:
            action()
    dialog.connect('response', answered)
    dialog.show_all()
    return dialog


class Page(Gtk.Box):
    """A page: its title (the name in the menu), the content, and one line at the bottom
    that says what happened."""
    title = ''

    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=18, margin_top=14)
        self.win, self.jobs = win, win.jobs
        self.head = Gtk.Box(spacing=10)
        self.head.pack_start(label(self.title, 'ztitle'), True, True, 0)
        self.add(self.head)
        self.status = label('', 'dim', ellipsize=3)
        self.pack_end(self.status, False, False, 0)
        self.build()

    def build(self):
        """add the page's widgets"""

    def shown(self):
        """the page came in front: read what it shows again"""

    def say(self, text, warn=False):
        self.status.set_text(text or '')
        context = self.status.get_style_context()
        context.remove_class('warn' if not warn else 'dim')
        context.add_class('warn' if warn else 'dim')


class Bar(Gtk.Box):
    """one calm line with one button, shown only when needed"""

    def __init__(self, text, button_text, action):
        super().__init__(spacing=12, no_show_all=True)
        self.line = label(text, wrap=True)
        self.line.show()
        self.pack_start(self.line, True, True, 0)
        self.button = button(button_text, action, main=True, valign=Gtk.Align.CENTER)
        self.button.show()
        self.pack_end(self.button, False, False, 0)


class ServiceBar(Bar):
    """'… is not running' with a Start it button"""

    def __init__(self, page, unit, text, on_started):
        super().__init__(text, 'Start it', self.start)
        self.page, self.unit, self.on_started = page, unit, on_started

    def start(self):
        self.button.set_sensitive(False)
        self.page.say('Starting…')
        self.page.jobs.run(lambda: services.start(self.unit), self.started)

    def started(self, result):
        ok, said = result
        self.button.set_sensitive(True)
        self.page.say(said, warn=not ok)
        if ok:
            self.on_started()


class FoldersBar(Bar):
    def __init__(self, win):
        super().__init__('Choose the folders I may read first', 'Folders', lambda: win.show_page('folders'))
