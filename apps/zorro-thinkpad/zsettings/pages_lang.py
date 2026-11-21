"""Desktop → Languages: spell checking in several languages at once (mixed in one sentence)"""
import os
import subprocess
import threading

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk  # noqa: E402

from . import lang
from .ui import Pages, heading, idle, note


class LangPages:
    def lang_page(self):
        box = Pages()
        box.add(heading('Spell checking', 'Spell checking'))
        box.add(note('Tick the languages you write in. They are checked all at the same time, so a '
                     'sentence that mixes Dutch and English gets no red lines, and a real typo in '
                     'either still does. For Firefox (also WhatsApp and Google), and Obsidian.'))
        grid = Gtk.Grid(column_spacing=16, row_spacing=4, margin_top=8)
        self.lang_checks = {}
        self.lang_state = {}
        on = set(lang.chosen())
        for i, (code, (name, _, _)) in enumerate(lang.LANGS.items()):
            cb = Gtk.CheckButton(label=name)
            cb.set_active(code in on)
            st = note()
            grid.attach(cb, 0, i, 1, 1)
            grid.attach(st, 1, i, 1, 1)
            self.lang_checks[code], self.lang_state[code] = cb, st
        grid.zlist = True               # one list of languages
        box.add(grid)
        row = Gtk.Box(spacing=8, margin_top=10)
        self.lang_btn = Gtk.Button(label='Apply')
        self.lang_btn.set_tooltip_text('Adds the dictionaries you ticked and removes the others '
                                       '(asks your password), then sets Firefox and Obsidian')
        self.lang_btn.connect('clicked', lambda b: self.lang_apply())
        row.add(self.lang_btn)
        box.add(row)
        self.lang_out = note()
        box.add(self.lang_out)
        if not os.access(lang.HELPER, os.X_OK):
            box.add(note('To add dictionaries the app needs its helper once, in a terminal:\n'
                         '  sudo ~/zorro-desktop/apps/zorro-thinkpad/install.sh'))
        box.add(note('Firefox picks up the change when it restarts. Obsidian is set while it is '
                     'closed; or in Obsidian: Settings → Editor → Spellcheck languages.'))
        self.lang_show()
        return box

    def lang_show(self):
        for code, st in self.lang_state.items():
            st.set_text('dictionary installed' if lang.installed(code) else '')
        return False

    def lang_apply(self):
        codes = [c for c, cb in self.lang_checks.items() if cb.get_active()]
        if not codes:
            self.lang_out.set_text('Tick at least one language.')
            return
        lang.choose(codes)
        self.lang_btn.set_sensitive(False)
        self.lang_out.set_text('Working…')

        def work():
            need = any(not lang.installed(c) for c in codes) or \
                any(lang.installed(c) for c in lang.LANGS if c not in codes)
            lines = []
            if need and os.access(lang.HELPER, os.X_OK):
                p = subprocess.Popen(['pkexec', lang.HELPER, 'dicts', *codes], stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True)
                for ln in p.stdout:
                    if ln.startswith(('installing', 'removing', 'E:')):
                        lines.append(ln.strip())
                        idle(lambda t=ln.strip(): self.lang_out.set_text(t) and False)
                if p.wait() in (126, 127):
                    lines.append('Dictionaries not changed (cancelled).')
            msg = lang.apply(codes)

            def done():
                self.lang_out.set_text('\n'.join(lines[-2:] + [msg]))
                self.lang_btn.set_sensitive(True)
                self.lang_show()
                return False
            idle(done)
        threading.Thread(target=work, daemon=True).start()
