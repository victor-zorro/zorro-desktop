"""About / privacy: what leaves the laptop with each engine, where the chat is kept."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk  # noqa: E402

from .. import chat, ui  # noqa: E402

LEAVES = (('Claude', 'Your question and the excerpts go to Anthropic, through the claude program.'),
          ('Mistral cloud', 'Your question and the excerpts go to Mistral, with your API key.'),
          ('On this laptop', 'Nothing leaves: the model runs here.'),
          ('Search', 'Always on this laptop. Only files in your folders are shown or sent.'),
          ('The chat', 'Kept in ~/.local/state/zorro-intel/chat.json, shared with the Dialer.\n'
                       'Older chats are in chats/ next to it.'))


class Page(ui.Page):
    title = 'About / privacy'

    def build(self):
        grid = Gtk.Grid(column_spacing=18, row_spacing=12)
        for i, (name, text) in enumerate(LEAVES):
            grid.attach(ui.label(name, yalign=0), 0, i, 1, 1)
            grid.attach(ui.note(text), 1, i, 1, 1)
        self.add(grid)
        self.add(ui.note('Every answer says which engine answered and which files went along.'))
        self.delete = ui.button('Delete all chats', self.ask_delete, halign=Gtk.Align.START, margin_top=8)
        self.add(self.delete)

    def ask_delete(self):
        ui.confirm(self.win, 'Delete this chat and all older chats?', 'Delete all chats',
                   lambda: self.jobs.run(chat.delete_all, lambda _r: self.say('All chats are deleted')))
