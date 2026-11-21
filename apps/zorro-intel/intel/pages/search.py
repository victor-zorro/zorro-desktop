"""Search: find notes and documents by meaning, without the AI."""
import os

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk  # noqa: E402

from .. import config, folders, search, services, ui, wording  # noqa: E402


class Page(ui.Page):
    title = 'Search'

    def build(self):
        self.service = ui.ServiceBar(self, services.SEARCH, 'The search service is not running', self.shown)
        self.need_folders = ui.FoldersBar(self.win)
        self.field = Gtk.SearchEntry(placeholder_text='Search by meaning, Enter searches')
        self.field.connect('activate', lambda _e: self.find())
        self.results = Gtk.ListBox(selection_mode=Gtk.SelectionMode.BROWSE, activate_on_single_click=True)
        self.results.connect('row-activated', lambda _l, row: ui.open_file(row.hit['path']))
        for w in (self.service, self.need_folders, self.field, ui.scrolled(self.results)):
            self.add(w)

    def shown(self):
        self.jobs.run(lambda: (config.load(), search.running()), self.show_state)
        self.field.grab_focus()

    def show_state(self, state):
        cfg, running = state
        self.service.set_visible(not running)
        self.need_folders.set_visible(not cfg['folders'])

    def find(self):
        text = self.field.get_text().strip()
        if not text:
            return
        self.say('Searching…')
        self.jobs.run(lambda: found(text), self.show_results)

    def show_results(self, result):
        hits, total = result
        ui.clear(self.results)
        self.service.set_visible(hits is None)
        if hits is None:
            self.say('')
            return
        for hit in hits:
            self.results.add(self.row(hit))
        self.results.show_all()
        hidden = total - len(hits)
        outside = f', {hidden} more outside your folders' if hidden else ''
        self.say(f'{len(hits)} found{outside}' if hits or hidden else 'Nothing found')

    def row(self, hit):
        row = Gtk.ListBoxRow()
        row.hit = hit
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        name = ui.label(ellipsize=3)
        name.set_markup(f'<b>{ui.GLib.markup_escape_text(str(hit.get("title") or ""))}</b>')
        text.add(name)
        text.add(ui.label(folders.short(os.path.dirname(hit['path'])), 'dim', ellipsize=1))
        text.add(ui.label(str(hit.get('snippet') or '')[:300], lines=2, wrap=True, ellipsize=3))
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER)
        bar = Gtk.LevelBar(min_value=0, max_value=1, value=wording.score_fraction(hit.get('score')),
                           tooltip_text=f'match {hit.get("score")}')
        bar.set_size_request(110, 4)
        side.add(bar)
        side.add(ui.button('Ask about this', lambda: self.ask_about(hit)))
        box = Gtk.Box(spacing=12)
        box.add(text)
        box.add(side)
        row.add(box)
        return row

    def ask_about(self, hit):
        page = self.win.show_page('ask')
        if page is not None:
            page.ask_about(hit['path'])


def found(text):
    """(hits inside the chosen folders or None when the service is down, how many the service gave)"""
    hits = search.ask(text)
    if hits is None:
        return None, 0
    return folders.allowed(hits, config.load()['folders']), len(hits)
