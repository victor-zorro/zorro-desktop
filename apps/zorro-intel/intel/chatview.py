"""The conversation as widgets: questions, answers, and under each answer who answered and the sources."""
import os

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk  # noqa: E402

from . import ui, wording  # noqa: E402

SHOWN = 60          # messages on screen; older ones stay in the file


def question_row(text):
    row = ui.label(text, 'you', wrap=True, selectable=True, margin_top=8)
    row.set_can_focus(False)
    return row


class AnswerRow(Gtk.Box):
    """one answer: the text, a dim line (engine, model, note), the files that were sent"""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.text = ui.label(wrap=True, selectable=True)
        self.text.set_can_focus(False)
        self.by = ui.note()
        self.extra = ui.note()
        self.extra.set_no_show_all(True)
        self.sources = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.sent = None
        for w in (self.text, self.by, self.extra, self.sources):
            self.add(w)

    def set(self, text, by, note=None, sent=(), warn=None):
        self.text.set_text(text)
        self.by.set_text(by)
        self.extra.set_text(warn or note or '')
        self.extra.set_visible(bool(warn or note))
        context = self.extra.get_style_context()
        context.remove_class('dim' if warn else 'warn')
        context.add_class('warn' if warn else 'dim')
        if list(sent) != self.sent:
            self.sent = list(sent)
            ui.clear(self.sources)
            for path in self.sent:
                self.sources.add(source_row(path))
            self.sources.show_all()


def source_row(path):
    """a file that was sent: click opens it"""
    b = ui.button(f'↗ {os.path.basename(path)}', lambda: ui.open_file(path), css='source',
                  halign=Gtk.Align.START, tooltip_text=str(path))
    b.set_relief(Gtk.ReliefStyle.NONE)
    return b


def stored_row(message):
    if message['role'] == 'user':
        return question_row(message['content'])
    row = AnswerRow()
    row.set(message['content'], wording.answered_by(message), message.get('note'), message.get('sent') or ())
    return row


def live_row(row, asking):
    """show an answer that is still coming in"""
    a = asking.answer
    if asking.stage == 'search':
        row.set('', 'Looking in your files…')
    elif not a.engine:
        row.set('', 'Asking…', asking.notes)
    else:
        by = wording.answered_by({'engine': a.engine, 'model': a.model, 'sent': a.sent})
        row.set(a.text, by + ('' if a.done else ' · writing…'), asking.notes, a.sent, warn=a.error)


class Conversation(Gtk.ScrolledWindow):
    """the box the conversation scrolls in; it follows the newest line unless you scrolled up"""

    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, hexpand=True)
        self.set_min_content_height(120)
        self.get_style_context().add_class('zbox')
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=12)
        self.add(self.rows)
        self.follow = True
        adjustment = self.get_vadjustment()
        adjustment.connect('value-changed', self.scrolled)
        adjustment.connect('changed', self.grew)

    def scrolled(self, adj):
        self.follow = adj.get_value() >= adj.get_upper() - adj.get_page_size() - 30

    def grew(self, adj):
        if self.follow:
            adj.set_value(adj.get_upper() - adj.get_page_size())

    def show_messages(self, messages, live=None):
        """the stored messages, then the answer that is being written (an AnswerRow) if any"""
        ui.clear(self.rows)
        if not messages and live is None:
            self.rows.add(ui.note('Ask about your notes and documents. The answer says who answered\n'
                                  'and which files went along.'))
        for message in messages[-SHOWN:]:
            self.rows.add(stored_row(message))
        if live is not None:
            self.rows.add(live)
        self.follow = True
        self.rows.show_all()
