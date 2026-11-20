"""Desktop → Install apps: the extra apps (extras/apps.json) to add after the minimal setup.
Tick the ones you want, then Install selected. Each install is extras/<id>/install.sh, run
through `zorro-apps install`; it asks your password itself when it needs root."""
import json
import os
import re
import shutil
import subprocess
import threading
import time

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk  # noqa: E402

from .base import HOME, spawn
from .ui import Pages, button, device_list, device_row, heading, idle, in_bg, note

ZAPPS = shutil.which('zorro-apps', path=f'{HOME}/.local/bin:{os.environ.get("PATH", "")}')


def catalog():
    try:
        return json.loads(subprocess.run([ZAPPS, '--json'], capture_output=True, text=True, timeout=10).stdout)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        return []


class AppsPages:
    def apps_page(self):
        box = Pages()
        box.add(heading('Install apps', 'Install apps'))
        box.add(note('Apps that are not part of the basic setup. Tick the ones you want and press '
                     'Install selected. Some ask for your password while they install.'))
        self.apps_list = device_list(margin_top=8)
        box.add(self.apps_list)
        row = Gtk.Box(spacing=8, margin_top=10)
        self.apps_btn = button('Install selected', self.apps_install, primary=True)
        row.add(self.apps_btn)
        box.add(row)
        self.apps_bar = Gtk.ProgressBar(show_text=True, no_show_all=True, margin_top=8)
        box.add(self.apps_bar)
        self.apps_out = note()
        self.apps_out.set_selectable(True)
        box.add(self.apps_out)
        if not ZAPPS:
            self.apps_out.set_text('zorro-apps is missing: run ~/zorro-desktop/install.sh once.')
        self.apps_checks = {}
        self.apps_fill()
        return box

    def apps_fill(self):
        for c in self.apps_list.get_children():
            self.apps_list.remove(c)
        self.apps_checks = {}
        self.apps_info = {a['id']: a for a in catalog()}
        for a in self.apps_info.values():
            detail = f"{a['about']} · {a['size']}"
            acts = []
            if a['is_installed']:
                detail += ' · installed'
            else:
                if a.get('how') == 'manual':
                    detail += (f" · found: {os.path.basename(a['found'])}" if a.get('found')
                               else ' · download it first, then tick it')
                    acts.append(('Download page', lambda u=a['download']: spawn(['xdg-open', u])))
                cb = Gtk.CheckButton(label='Install')
                self.apps_checks[a['id']] = cb
                acts.append(cb)
            icon = a.get('icon') if Gtk.IconTheme.get_default().has_icon(a.get('icon') or '') else 'applications-games' if 'engine' in a['about'].lower() else 'package-x-generic'
            self.apps_list.add(device_row(a['name'], detail, acts, icon=icon,
                                          state='ok' if a['is_installed'] else None))
        self.apps_list.show_all()
        self.apps_btn.set_sensitive(bool(self.apps_checks))
        return False

    def apps_pick_file(self, a):
        """a manual app: its download (found in Installers or Downloads, or chosen here); None: cancelled"""
        if a.get('found'):
            return a['found']
        dlg = Gtk.FileChooserDialog(title=f"The {a['name']} download", transient_for=self,
                                    action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Use this file', Gtk.ResponseType.OK)
        dlg.set_current_folder(str(HOME / 'Downloads'))
        f = Gtk.FileFilter()
        f.set_name(a.get('file', '*'))
        f.add_pattern(a.get('file', '*'))
        dlg.add_filter(f)
        path = dlg.get_filename() if dlg.run() == Gtk.ResponseType.OK else None
        dlg.destroy()
        return path

    def apps_install(self):
        todo = []
        for aid, cb in self.apps_checks.items():
            if not cb.get_active():
                continue
            a = self.apps_info[aid]
            arg = []
            if a.get('how') == 'manual':
                path = self.apps_pick_file(a)
                if not path:
                    continue
                arg = [path]
            todo.append((a, arg))
        if not todo:
            self.apps_out.set_text('Tick at least one app.')
            return
        self.apps_btn.set_sensitive(False)

        def show(text, frac=None):
            """the line under the button, and the bar: a fraction, or None to pulse"""
            def ui_():
                self.apps_out.set_text(text)
                self.apps_bar.show()
                if frac is None:
                    self.apps_bar.pulse()
                    self.apps_bar.set_text('')
                else:
                    self.apps_bar.set_fraction(frac)
                    self.apps_bar.set_text(f'{frac * 100:.0f} %')
                return False
            idle(ui_)

        def work():
            done = []
            for a, arg in todo:
                name, start = a['name'], time.monotonic()
                state = {'step': 'starting…', 'frac': None, 'last': ''}

                def tick():
                    t = int(time.monotonic() - start)
                    show(f"{name}: {state['step']}  ·  {t // 60}:{t % 60:02d}", state['frac'])

                stop = threading.Event()

                def ticker():                     # the time keeps running: you see it is busy
                    while not stop.wait(1):
                        tick()
                threading.Thread(target=ticker, daemon=True).start()
                tick()
                try:
                    p = subprocess.Popen([ZAPPS, 'install', a['id'], *arg], stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                         start_new_session=True)    # goes on if Settings closes
                    buf = b''
                    while True:                   # curl's bar redraws with \r, so split on both
                        chunk = os.read(p.stdout.fileno(), 4096)
                        if not chunk:
                            break
                        buf += chunk
                        parts = re.split(rb'[\r\n]', buf)
                        buf = parts.pop()
                        for raw in parts:
                            ln = raw.decode(errors='replace').strip()
                            pct = re.search(r'(\d{1,3}(?:[.,]\d)?)\s*%', ln)
                            if ln.startswith(('==>', '!!')):
                                state['last'] = state['step'] = ln.lstrip('=>! ')
                                state['frac'] = None
                            elif pct and (re.fullmatch(r'[#\s]*\d{1,3}(?:[.,]\d)?\s*%', ln) or ln.startswith('unpacking')):
                                state['frac'] = min(1.0, float(pct.group(1).replace(',', '.')) / 100)
                            elif ln and not pct:       # apt and friends: their last line
                                state['step'] = ln[:80]
                            tick()
                    rc = p.wait()
                except OSError as e:
                    rc, state['last'] = 1, str(e)
                stop.set()
                done.append(f"{name}: " + ('installed' if rc == 0 else
                                           'cancelled' if rc in (126, 127) else f"not installed ({state['last']})"))
            idle(lambda: (self.apps_out.set_text('\n'.join(done)), self.apps_bar.hide(), self.apps_fill()) and False)

        in_bg(work)
