"""Engines: which engine answers in each place, and whether anything may leave the laptop."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk  # noqa: E402

from .. import ai, services, ui, wording  # noqa: E402


class Page(ui.Page):
    title = 'Engines'

    def build(self):
        self.service = ui.ServiceBar(self, services.AI, 'The AI service is not running', self.shown)
        self.add(self.service)
        self.grid = Gtk.Grid(column_spacing=16, row_spacing=10)
        self.combos, self.claude_combos = {}, {}
        for column, head in ((1, 'Engine'), (2, 'Claude model')):
            self.grid.attach(ui.note(head), column, 0, 1, 1)
        for i, (place, title) in enumerate(wording.PLACES.items(), 1):
            self.combos[place] = ui.combo(wording.CHOICES, 'auto', lambda value, p=place: self.set_place(p, value))
            self.combos[place].set_size_request(150, -1)
            self.claude_combos[place] = ui.combo(wording.claude_options(place), wording.claude_choice({}, place),
                                                 lambda value, p=place: self.set_claude(p, value))
            self.grid.attach(ui.label(title), 0, i, 1, 1)
            self.grid.attach(self.combos[place], 1, i, 1, 1)
            self.grid.attach(self.claude_combos[place], 2, i, 1, 1)
        self.local_only = Gtk.Switch(halign=Gtk.Align.START)
        self.local_only.connect('notify::active', lambda w, _p: self.set_local_only(w.get_active()))
        self.grid.attach(ui.label('Nothing leaves this laptop'), 0, 4, 1, 1)
        self.grid.attach(self.local_only, 1, 4, 1, 1)
        self.add(self.grid)
        self.add(ui.note('Automatic: Claude; when it cannot be reached, Mistral cloud; offline, this laptop.\n'
                         'Lighter Claude models answer faster and use less of your plan.'))
        self.states = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=8)
        self.add(self.states)
        self.filling = False

    def shown(self):
        self.jobs.run(ai.status_or_none, self.show_status)

    def show_status(self, reply):
        self.service.set_visible(reply is None)
        self.grid.set_sensitive(reply is not None)
        ui.clear(self.states)
        if reply is None:
            return
        settings = reply.get('settings') or {}
        self.filling = True
        for place, combo in self.combos.items():
            combo.filling = True
            combo.set_active_id(wording.choice((settings.get('places') or {}).get(place)))
            combo.filling = False
        suggested = reply.get('claude_suggested')
        for place, combo in self.claude_combos.items():
            ui.fill_combo(combo, wording.claude_options(place, suggested), wording.claude_choice(settings, place, suggested))
        self.local_only.set_active(bool(settings.get('local_only')))
        self.filling = False
        for name in wording.ENGINES:
            state = (reply.get('engines') or {}).get(name) or {}
            self.states.add(ui.marked(*wording.engine_state(name, state, settings.get('local_only'))))
        self.states.show_all()

    def set_place(self, place, value):
        self.change({'places': {place: value}}, f'{wording.PLACES[place]} now uses {wording.CHOICES[value]}')

    def set_claude(self, place, value):
        if not self.filling:
            self.change(wording.claude_change(place, value),
                        f'{wording.PLACES[place]} asks Claude {wording.CLAUDE_MODELS[value].split(" (")[0]}')

    def set_local_only(self, on):
        if not self.filling:
            self.change({'local_only': on}, 'Nothing leaves this laptop now' if on else 'Cloud engines may answer again')

    def change(self, settings, said):
        self.jobs.run(lambda: ai.change_error(settings), lambda error: self.after_change(error, said))

    def after_change(self, error, said):
        self.say(error or said, warn=bool(error))
        self.shown()

