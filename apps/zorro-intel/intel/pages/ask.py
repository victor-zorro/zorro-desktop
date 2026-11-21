"""Ask: the chat. A question is first searched in your folders; the best excerpts go along."""
import os

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from .. import ai, asking, chat, chatview, config, paths, services, ui, wording  # noqa: E402


class Page(ui.Page):
    title = 'Ask'

    def build(self):
        self.asking, self.live, self.about = None, None, None
        self.messages = []
        self.head.pack_end(ui.button('New chat', self.new_chat), False, False, 0)
        self.service = ui.ServiceBar(self, services.AI, 'The AI service is not running', self.shown)
        self.need_folders = ui.FoldersBar(self.win)
        self.talk = chatview.Conversation()
        self.about_bar = ui.Bar('', 'Clear', lambda: self.ask_about(None))
        self.field = Gtk.Entry(placeholder_text='Ask a question, Enter sends', hexpand=True)
        self.field.connect('activate', lambda _e: self.send())
        self.go = ui.button('Send', self.send_or_stop, main=True)
        row = Gtk.Box(spacing=8)
        row.add(self.field)
        row.add(self.go)
        for w in (self.service, self.need_folders, self.talk, self.about_bar, row):
            self.add(w)
        self.watch_chat()

    def watch_chat(self):
        """re-read the chat when the file changes: a chat started in the Dialer continues here"""
        paths.state_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
        self.monitor = Gio.File.new_for_path(str(paths.chat_file())).monitor_file(Gio.FileMonitorFlags.NONE, None)
        self.reload_timer = 0
        self.monitor.connect('changed', lambda *_a: self.reload_soon())
        self.connect('destroy', lambda _w: self.unwatch())

    def unwatch(self):
        self.monitor.cancel()
        if self.reload_timer:
            GLib.source_remove(self.reload_timer)
            self.reload_timer = 0

    def reload_soon(self):
        if not self.reload_timer:
            self.reload_timer = GLib.timeout_add(150, self.reload_now)

    def reload_now(self):
        self.reload_timer = 0
        self.reload()
        return False

    def shown(self):
        self.jobs.run(lambda: (config.load(), ai.running()), self.show_state)
        self.reload()
        self.field.grab_focus()

    def show_state(self, state):
        cfg, running = state
        self.service.set_visible(not running)
        self.need_folders.set_visible(not cfg['folders'])
        self.can_ask = bool(cfg['folders'])
        self.set_busy(self.asking is not None)

    def reload(self):
        self.jobs.run(chat.load, self.show_messages)

    def show_messages(self, messages):
        self.messages = messages
        self.talk.show_messages(messages, self.live)

    def set_busy(self, busy):
        self.go.set_label('Stop' if busy else 'Send')
        self.field.set_sensitive(getattr(self, 'can_ask', False) and not busy)
        self.go.set_sensitive(getattr(self, 'can_ask', False))

    def ask_about(self, path):
        """the next questions are about this one file (from Search); None: back to searching"""
        self.about = path
        self.about_bar.line.set_text(f'About {os.path.basename(path)} only' if path else '')
        self.about_bar.set_visible(bool(path))
        self.field.grab_focus()

    def send_or_stop(self):
        if self.asking is not None:
            self.asking.cancel()
            self.say('Stopping…')
        else:
            self.send()

    def send(self):
        text = self.field.get_text().strip()
        if not text or self.asking is not None or not getattr(self, 'can_ask', False):
            return
        self.field.set_text('')
        self.say('')
        self.asking = asking.Asking(text, self.about, on_change=lambda: self.jobs.later(self.changed))
        self.live = chatview.AnswerRow()
        chatview.live_row(self.live, self.asking)
        self.set_busy(True)
        self.talk.show_messages(self.messages + [chat.question(text)], self.live)
        self.jobs.run(self.asking.run, self.finished, cancel=self.asking.cancel)

    def changed(self):
        if self.asking is not None and self.live is not None:
            chatview.live_row(self.live, self.asking)

    def finished(self, done):
        answer = done.answer
        self.asking, self.live = None, None
        self.set_busy(False)
        if done.no_service:
            self.say('')
        elif answer.error:
            self.say(wording.plain_error(answer.error), warn=True)
        elif done.cancelled.is_set():
            self.say('Stopped. What had arrived is kept.' if answer.text else 'Stopped')
        else:
            self.say(f'Answered in {answer.seconds} s' if answer.seconds is not None else 'Answered')
        self.service.set_visible(done.no_service)
        self.reload()
        self.field.grab_focus()

    def new_chat(self):
        if self.asking is not None:
            self.asking.cancel()
        self.jobs.run(chat.new_chat, self.started_new)

    def started_new(self, kept):
        self.say('New chat. The old one is kept in chats/' if kept else 'New chat')
        self.reload()
