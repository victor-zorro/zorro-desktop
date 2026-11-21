"""Mistral key: store or remove the API key for Mistral's cloud. The key is never shown."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk  # noqa: E402

from .. import keyfile, ui  # noqa: E402

STEPS = ('1. Open console.mistral.ai and make an account.',
         '2. Choose a plan.',
         '3. Open API Keys.',
         '4. Press "Create new key".',
         '5. Copy the key and store it here.')


class Page(ui.Page):
    title = 'Mistral key'

    def build(self):
        self.state = ui.marked('off', 'Looking…')
        self.add(self.state)
        self.field = Gtk.Entry(visibility=False, placeholder_text='Paste the key', hexpand=True,
                               input_purpose=Gtk.InputPurpose.PASSWORD)
        self.field.connect('activate', lambda _e: self.store())
        row = Gtk.Box(spacing=8)
        row.add(self.field)
        row.add(ui.button('Store key', self.store, main=True))
        self.remove = ui.button('Remove key', self.ask_remove)
        row.add(self.remove)
        self.add(row)
        self.add(ui.note('Kept in ~/.config/zorro-ai/mistral.key, readable only by you.'))
        steps = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=12)
        steps.add(ui.label('How to get a key'))
        for step in STEPS:
            steps.add(ui.note(step))
        self.add(steps)

    def shown(self):
        self.jobs.run(keyfile.present, self.show)

    def show(self, present):
        mark, text = ('on', 'A key is stored') if present else ('off', 'No key stored')
        self.state.set_markup(f'{ui.mark(mark)}  {text}')
        self.remove.set_sensitive(present)

    def store(self):
        key = self.field.get_text()
        self.field.set_text('')
        self.jobs.run(lambda: stored(key), self.after)

    def after(self, result):
        present, said, warn = result
        self.show(present)
        self.say(said, warn)

    def ask_remove(self):
        ui.confirm(self.win, 'Remove the Mistral key from this laptop?', 'Remove key',
                   lambda: self.jobs.run(removed, self.after))


def stored(key):
    """(key present, what to say, warning)"""
    try:
        keyfile.store(key)
    except (keyfile.BadKey, OSError) as e:
        return keyfile.present(), str(e), True
    return True, 'Key stored. Mistral cloud can answer now.', False


def removed():
    keyfile.remove()
    return keyfile.present(), 'Key removed', False
