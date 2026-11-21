"""Local models: download models for the engine on this laptop and choose which one is used."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk  # noqa: E402

from .. import ai, pull, services, ui, wording  # noqa: E402

SMALLEST = '-'
ENGINE = 'the local engine'


class Page(ui.Page):
    title = 'Local models'

    def build(self):
        self.run, self.run_id, self.progress = None, None, None
        self.service = ui.ServiceBar(self, services.AI, 'The AI service is not running', self.shown)
        self.engine = ui.Bar('The local engine (llama.cpp) is not installed yet',
                             'Install the local engine', lambda: self.start(ENGINE, ['install-local']))
        self.rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.charger = ui.combo({SMALLEST: 'Smallest downloaded'}, SMALLEST,
                                lambda v: self.choose('local_model', v))
        self.battery = ui.combo({SMALLEST: 'Smallest downloaded'}, SMALLEST,
                                lambda v: self.choose('local_model_battery', v))
        grid = Gtk.Grid(column_spacing=16, row_spacing=8)
        for i, (text, combo) in enumerate((('On the charger', self.charger), ('On battery', self.battery))):
            grid.attach(ui.label(text), 0, i, 1, 1)
            grid.attach(combo, 1, i, 1, 1)
        for w in (self.service, self.engine, ui.scrolled(self.rows), grid):
            self.add(w)
        self.connect('destroy', lambda _w: self.stop())

    def shown(self):
        self.jobs.run(load, self.show)

    def show(self, loaded):
        self.service.set_visible(loaded is None)
        self.charger.set_sensitive(loaded is not None)
        self.battery.set_sensitive(loaded is not None)
        ui.clear(self.rows)
        self.progress = None
        models, status = loaded or ([], {})
        self.engine.set_visible(wording.local_engine_missing(status))
        self.engine.button.set_sensitive(self.run is None)
        if loaded is None:
            return
        for model in models:
            self.rows.add(self.row(model))
        self.rows.show_all()
        have = {SMALLEST: 'Smallest downloaded', **wording.installed(models)}
        settings = status.get('settings') or {}
        ui.fill_combo(self.charger, have, settings.get('local_model') or SMALLEST)
        ui.fill_combo(self.battery, have, settings.get('local_model_battery') or SMALLEST)

    def row(self, model):
        row = Gtk.ListBoxRow(activatable=False)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        name = ui.label()
        name.set_markup(f'<b>{ui.GLib.markup_escape_text(model["name"])}</b>')
        text.add(name)
        text.add(ui.note(wording.model_line(model)))
        box = Gtk.Box(spacing=12)
        box.add(text)
        box.add(self.action(model))
        row.add(box)
        return row

    def action(self, model):
        """the right side of a row: downloaded, a Download button, or the running download"""
        if model.get('installed'):
            return ui.marked('on', 'Downloaded')
        if self.run_id == model['id']:
            side = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
            self.progress = Gtk.ProgressBar(valign=Gtk.Align.CENTER)
            self.progress.set_size_request(110, -1)
            side.add(self.progress)
            side.add(ui.button('Stop', self.stop))
            return side
        b = ui.button('Download', lambda: self.start(model['id'], ['pull', model['id']]), valign=Gtk.Align.CENTER)
        b.set_sensitive(self.run is None)
        return b

    def start(self, what, args):
        if self.run is not None:
            return
        self.run_id = what
        self.run = pull.Run(args, lambda line: self.jobs.later(self.said, line))
        self.say(f'Getting {what}…')
        self.jobs.run(self.run.run, self.ended, cancel=self.run.cancel)
        self.shown()

    def said(self, line):
        part = pull.fraction(line)
        if part is None:
            self.say(line.strip())
        elif self.progress is not None:
            self.progress.set_fraction(part)
        else:
            self.say(f'Getting {self.run_id}: {part:.0%}')

    def stop(self):
        if self.run is not None:
            self.run.cancel()

    def ended(self, result):
        ok, said = result
        what, self.run, self.run_id = self.run_id, None, None
        self.say(f'{what}: {said}' if not ok else f'{what} is ready', warn=not ok and said != 'Stopped')
        self.shown()

    def choose(self, key, model_id):
        value = None if model_id == SMALLEST else model_id
        self.jobs.run(lambda: ai.change_error({key: value}),
                      lambda error: self.say(error or 'Model choice changed', warn=bool(error)))


def load():
    """(models, status), None when zorro-ai does not run"""
    try:
        return ai.models(), ai.status_or_none() or {}
    except ai.NoService:
        return None
