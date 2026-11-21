"""The window: the menu on the left, always visible; the chosen page on the right."""
import importlib
import traceback

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import jobs, ui  # noqa: E402
from .cli import PAGES  # noqa: E402

SIZE = (920, 620)
MENU_WIDTH = 190


class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='Intelligence')
        self.set_default_size(*SIZE)
        self.set_icon_name('system-search')
        ui.install_look(self)
        self.jobs = jobs.Jobs(ui.post)
        self.pages = {}
        self.menu = Gtk.ListBox(selection_mode=Gtk.SelectionMode.BROWSE)
        self.menu.get_style_context().add_class('zmenu')
        self.menu.set_size_request(MENU_WIDTH, -1)
        for name, title in PAGES.items():
            row = Gtk.ListBoxRow()
            row.add(ui.label(title))
            row.page = name
            self.menu.add(row)
        self.stack = Gtk.Stack(hexpand=True, vexpand=True)
        box = Gtk.Box()
        box.add(self.menu)
        box.add(self.stack)
        self.add(box)
        self.menu.connect('row-selected', lambda _m, row: row and self.open(row.page))
        self.connect('destroy', lambda _w: self.jobs.close())

    def page(self, name):
        """the page, built the first time it is asked for"""
        if name not in self.pages:
            module = importlib.import_module(f'.pages.{name}', __package__)
            self.pages[name] = module.Page(self)
            self.stack.add_named(self.pages[name], name)
            self.pages[name].show_all()
        return self.pages[name]

    def open(self, name):
        try:
            page = self.page(name)
        except Exception:               # noqa: BLE001 - one broken page must not take the window down
            traceback.print_exc()
            return None
        self.stack.set_visible_child_name(name)
        page.shown()
        return page

    def show_page(self, name):
        """go to a page (also from another page); the page"""
        name = name if name in PAGES else 'ask'
        row = self.menu.get_row_at_index(list(PAGES).index(name))
        if self.menu.get_selected_row() is row:
            return self.open(name)
        self.menu.select_row(row)
        return self.pages.get(name)


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.zorro.intel', flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.add_main_option('page', 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING,
                             'open this page: ' + ' | '.join(PAGES), 'NAME')
        self.window = None

    def do_command_line(self, command_line):
        options = command_line.get_options_dict().end().unpack()
        if self.window is None:
            self.window = Window(self)
            self.window.show_all()
        self.window.show_page(options.get('page') or 'ask')
        self.window.present()
        return 0
