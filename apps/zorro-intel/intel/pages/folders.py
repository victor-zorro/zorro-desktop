"""Folders: the only folders the AI may read, and how many excerpts go along with a question."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk  # noqa: E402

from .. import config, folders, ui  # noqa: E402


class Page(ui.Page):
    title = 'Folders'

    def build(self):
        self.add(ui.note('Only files inside these folders are shown in Search or sent with a question.'))
        self.rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.add(ui.scrolled(self.rows))
        self.count = Gtk.SpinButton.new_with_range(0, config.MAX_EXCERPTS, 1)
        self.count.connect('value-changed', lambda w: self.set_count(w.get_value_as_int()))
        self.filling = False
        row = Gtk.Box(spacing=12)
        row.add(ui.button('Add folder', self.pick, main=True))
        row.pack_end(self.count, False, False, 0)
        row.pack_end(ui.label('Excerpts per question'), False, False, 0)
        self.add(row)
        self.add(ui.note('Search reads your Obsidian vaults and Documents today.\n'
                         'A folder outside those gives no results yet.'))

    def shown(self):
        self.jobs.run(config.load, self.show)

    def show(self, cfg):
        ui.clear(self.rows)
        for folder in cfg['folders']:
            self.rows.add(self.row(folder))
        if not cfg['folders']:
            empty = Gtk.ListBoxRow(activatable=False)
            empty.add(ui.note('No folders yet: the AI reads nothing.'))
            self.rows.add(empty)
        self.rows.show_all()
        self.filling = True
        self.count.set_value(cfg['excerpts'])
        self.filling = False

    def row(self, folder):
        row = Gtk.ListBoxRow(activatable=False)
        box = Gtk.Box(spacing=12)
        box.pack_start(ui.label(folders.short(folder), ellipsize=1, tooltip_text=folder), True, True, 0)
        box.pack_end(ui.button('Remove', lambda: self.change(lambda: config.remove_folder(folder),
                                                           f'{folders.short(folder)} is no longer read')),
                     False, False, 0)
        row.add(box)
        return row

    def pick(self):
        self.chooser = Gtk.FileChooserNative.new('Add folder', self.win, Gtk.FileChooserAction.SELECT_FOLDER,
                                                 'Add', 'Cancel')
        self.chooser.connect('response', self.picked)
        self.chooser.show()

    def picked(self, chooser, response):
        folder = chooser.get_filename() if response == Gtk.ResponseType.ACCEPT else None
        chooser.destroy()
        self.chooser = None
        if folder:
            self.change(lambda: config.add_folder(folder), f'{folders.short(folder)} may be read now')

    def set_count(self, count):
        if not self.filling:
            words = 'No excerpts go along' if count == 0 else f'Up to {count} excerpts go along'
            self.change(lambda: config.set_excerpts(count), words)

    def change(self, work, said):
        self.jobs.run(work, lambda cfg: (self.show(cfg), self.say(said)))
