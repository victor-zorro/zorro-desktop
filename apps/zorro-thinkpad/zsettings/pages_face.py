"""Look → Face unlock: zorro-face (the IR camera) learns your face; the lock screen
and login screen get a face icon that checks your face when pressed. The password always works too."""
import getpass
import json
import os
import subprocess
import sys
import tempfile
import threading

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GdkPixbuf, Gtk  # noqa: E402

from .ui import Pages, heading, idle, note

FACE = '/usr/local/bin/zorro-face'
FACEVIEW = os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', '..',
                                         'zorro-face', 'faceview.py'))
SRC = os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', '..', 'zorro-face')


def face_status():
    try:
        r = subprocess.run([FACE, 'status', getpass.getuser()], capture_output=True, text=True, timeout=10)
        return json.loads(r.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


class FacePages:
    def face_page(self):
        box = Pages()
        box.add(heading('Face unlock', 'Face unlock'))
        box.add(note('The laptop\'s infrared camera (the Windows Hello kind) recognises you. '
                     'It works in the dark, and a photo on a phone does not fool it: the camera '
                     'only counts a face its own infrared light shines on. Your face is kept as '
                     'numbers on this laptop, readable only by root. The password always works too.'))
        self.face_state = note()
        box.add(self.face_state)

        row = Gtk.Box(spacing=8, margin_top=6)
        self.face_learn = Gtk.Button(label='Learn my face')
        self.face_learn.set_tooltip_text('Opens a window: look at the screen and turn your head a little. '
                                         'Learning again (with glasses, or in other light) adds to it '
                                         'and makes it better.')
        self.face_test = Gtk.Button(label='Test')
        self.face_forget = Gtk.Button(label='Delete all my face data')
        self.face_look = Gtk.Button(label='Camera view')
        self.face_look.set_tooltip_text('What the infrared camera sees')
        for b in (self.face_learn, self.face_test, self.face_forget, self.face_look):
            row.add(b)
        box.add(row)
        self.face_out = note()
        box.add(self.face_out)
        self.face_img = Gtk.Image(halign=Gtk.Align.START, margin_top=6)
        box.add(self.face_img)

        box.add(heading('Face icon'))
        box.add(note('A small face icon under the password field: press it and the camera looks '
                     'for you. Nothing scans by itself.'))
        self.face_lock = Gtk.CheckButton(label='On the lock screen')
        self.face_login = Gtk.CheckButton(label='On the login screen (after a restart)')
        box.add(self.face_lock)
        box.add(self.face_login)
        box.add(note('At login your password also opens the keyring, where Firefox, Signal and Drive '
                     'keep their logins. After logging in with your face it stays closed, so the '
                     'first app that needs it asks for the password once.'))

        me = getpass.getuser()
        self.face_learn.connect('clicked', lambda b: self.face_window('learn'))
        self.face_test.connect('clicked', lambda b: self.face_run(['verify', me, '--timeout', '6'],
                                                                   'Look at the camera…'))
        self.face_forget.connect('clicked', lambda b: self.face_window('forget'))
        self.face_look.connect('clicked', lambda b: self.face_snapshot())
        self.face_lock.connect('toggled', lambda c: self.face_set('lock', c))
        self.face_login.connect('toggled', lambda c: self.face_set('login', c))
        self.face_check()
        return box

    def face_check(self):
        def work():
            st = face_status() if os.access(FACE, os.X_OK) else None
            idle(self.face_show, st)
        threading.Thread(target=work, daemon=True).start()

    def face_show(self, st):
        self.face_busy = True              # setting the boxes is not a click
        installed = st is not None and st.get('models')
        if not installed:
            self.face_state.set_text(f'Not installed yet. In a terminal:\n  sudo {os.path.realpath(SRC)}/install.sh')
        elif not st.get('camera'):
            self.face_state.set_text('No infrared camera found.')
        else:
            self.face_state.set_text('Your face is learned.' if st.get('enrolled')
                                     else 'Not learned yet: press "Learn my face" and look at the camera.')
        ok = bool(installed and st.get('camera'))
        for w in (self.face_learn, self.face_look):
            w.set_sensitive(ok)
        for w in (self.face_test, self.face_forget):
            w.set_sensitive(bool(ok and st.get('enrolled')))
        self.face_lock.set_active(bool(st and st.get('lock')))
        self.face_login.set_active(bool(st and st.get('login')))
        for w in (self.face_lock, self.face_login):
            w.set_sensitive(ok)
        self.face_busy = False
        return False

    def face_window(self, mode):
        """faceview: learning shows the wireframe being built, deleting shows it coming apart"""
        self.face_out.set_text('')

        def work():
            subprocess.run([sys.executable, FACEVIEW, mode])
            self.face_check()
        threading.Thread(target=work, daemon=True).start()

    def face_run(self, args, first):
        self.face_out.set_text(first)
        lines = []

        def work():
            p = subprocess.Popen(['pkexec', FACE, *args], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True)
            for ln in p.stdout:
                ln = ln.strip()
                if ln.startswith('progress'):
                    ln = 'Learning… ' + ln.split()[1]
                elif ln == 'looking':
                    ln = 'Looking for you…'
                elif ln.startswith('match'):
                    ln = 'Recognised you ✓'
                elif ln == 'no match':
                    ln = 'Did not recognise you. Learn your face again (also in this light).'
                lines.append(ln)
                idle(lambda t=ln: self.face_out.set_text(t) and False)
            rc = p.wait()
            if rc in (126, 127):
                idle(lambda: self.face_out.set_text('Cancelled.') and False)
            self.face_check()
        threading.Thread(target=work, daemon=True).start()

    def face_set(self, key, cb):
        if getattr(self, 'face_busy', False):
            return

        value = 'on' if cb.get_active() else 'off'

        def work():
            subprocess.run(['pkexec', FACE, 'set', key, value], capture_output=True)
            self.face_check()
        threading.Thread(target=work, daemon=True).start()

    def face_snapshot(self):
        self.face_out.set_text('Taking a picture…')

        def work():
            f = os.path.join(tempfile.gettempdir(), f'zorro-face-{os.getuid()}.png')
            r = subprocess.run([FACE, 'snapshot', f], capture_output=True, text=True, timeout=20)

            def show():
                if r.returncode == 0 and os.path.exists(f):
                    self.face_img.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(f, 400, -1, True))
                    self.face_out.set_text('What the infrared camera sees (lit by its own light).')
                else:
                    self.face_out.set_text((r.stderr or 'No picture.').strip())
                return False
            idle(show)
        threading.Thread(target=work, daemon=True).start()
