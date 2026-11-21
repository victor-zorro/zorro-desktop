"""app: the Look tab (theme presets, login / lock screen)"""
import json
import os
import re
import subprocess
import threading
from pathlib import Path
from .base import HOME, RUNTIME, load_conf, spawn, update_conf, write_atomic
from .look import CBLUR_MODES, CUSTOM_PRESETS, DM_DIR, LOOK_ANIMALS, animal_id, LOOK_BACKGROUNDS, LOOK_DEFAULTS, LOOK_FILE, _look_draft, custom_presets, theme_presets
from .power import LOOK_HELPER

SAVING = threading.Lock()         # one login-look save at a time: the last one asked wins
KEEP_ON_PRESET = ('clock',)     # your own choices a look preset never changes
from . import ui
from .ui import Pages, heading, idle, note
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gdk, Gtk


class LookPages:
    """the Look tab: theme presets and the login / lock screen (a mixin of the app window)"""

    # -- theme presets: one look for login, lock screen and wallpaper
    def theme_page(self):
        box = Pages()
        self.theme_msg = note()
        self.theme_msg.set_hexpand(True)
        current = load_conf().get('theme', 'chromatic-sea')

        def card(pid, p, custom=False):
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            thumb = DM_DIR / 'theme' / 'presets' / f'{pid}.jpg'
            if thumb.exists():
                from gi.repository import GdkPixbuf
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(thumb), 200, 113, True)
                v.add(Gtk.Image.new_from_pixbuf(pb))
            else:
                ph = Gtk.Label(label='your own look', width_request=200, height_request=113)
                ph.get_style_context().add_class('dim-label')
                v.add(ph)
            name = Gtk.Label(xalign=0)
            mark = '  ✓' if pid == current else ''
            name.set_markup(f'<b>{GLib.markup_escape_text(p["name"])}</b>{mark}')
            v.add(name)
            about = note(p.get('about', ''))
            about.set_max_width_chars(26)
            about.set_lines(2)
            about.set_ellipsize(3)
            v.add(about)
            row = Gtk.Box(spacing=6)
            use = Gtk.Button(label='Use this theme')
            use.connect('clicked', lambda b: self.theme_apply(pid, p))
            row.add(use)
            if custom:
                rm = Gtk.Button(label='Delete')
                rm.connect('clicked', lambda b: self.theme_delete(pid))
                row.add(rm)
            v.add(row)
            return v

        def flow(items, custom=False):
            fb = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3,
                             min_children_per_line=3, column_spacing=14, row_spacing=10,
                             homogeneous=True)
            for pid, p in items:
                fb.add(card(pid, p, custom))
            return fb

        box.add(heading('Chromatic sea and other looks', 'Presets'))
        box.add(flow(theme_presets().items()))
        box.add(note('A theme sets the login screen, the lock screen and the wallpaper '
                     'together. Fine-tune it under Login & lock screen.'))

        box.add(heading('Your own presets', 'Your presets'))
        mine = custom_presets()
        if mine:
            box.add(flow(mine.items(), custom=True))
        else:
            box.add(note('None yet.'))
        row = Gtk.Box(spacing=8, margin_top=8)
        self.theme_name = Gtk.Entry(placeholder_text='name, e.g. Night dive', hexpand=True)
        save = Gtk.Button(label='Save the current look as a preset')
        save.connect('clicked', lambda b: self.theme_save())
        row.add(self.theme_name)
        row.add(save)
        box.add(row)
        box.add(note('Saves what Login & lock screen shows now (also unsaved changes).'))
        box.footer(self.theme_msg)
        return box

    def theme_apply(self, pid, p):
        look = {**LOOK_DEFAULTS, **p['look']}
        try:                # the clock is your own choice, not part of a look: keep it
            now = json.loads(Path(LOOK_FILE).read_text())
        except (OSError, ValueError):
            now = {}
        for k in KEEP_ON_PRESET:
            look[k] = now.get(k, LOOK_DEFAULTS[k])
        self.theme_msg.set_text(f'Applying {p["name"]}… (your password, once)')
        ui.drop_later('greeter-look')       # a slider change still waiting: the preset replaces it

        def work():
            try:
                with SAVING:
                    r = subprocess.run(['pkexec', LOOK_HELPER, 'greeter-look', json.dumps(look)],
                                       capture_output=True, text=True, timeout=120)
                ok = r.returncode == 0
                msg = (f'{p["name"]} is on: login, lock screen and wallpaper' if ok else
                       (r.stderr.strip().splitlines() or ['not applied'])[-1])
            except (OSError, subprocess.TimeoutExpired) as e:
                ok, msg = False, f'Could not apply: {e}'
            if ok:
                update_conf(None, theme=pid)
                wall = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'zorro-wall' / 'config.json'
                try:
                    wc = json.loads(wall.read_text())
                except (OSError, ValueError):
                    wc = {}
                wc['follow_login'] = True       # the wallpaper shows the same look
                write_atomic(wall, json.dumps(wc, indent=2) + '\n')
            idle(self.theme_done, msg, ok)
        threading.Thread(target=work, daemon=True).start()

    def theme_done(self, msg, ok):
        if getattr(self, 'dead', False):        # this window was rebuilt meanwhile
            return False
        if ok:                                  # rebuild: Login & lock screen shows the new look
            app = self.get_application()
            self.destroy()
            win = type(self)(app, select='theme:0')
            win.theme_msg.set_text(msg)
            win.present()
        else:
            self.theme_msg.set_text(msg)
        return False

    def theme_save(self):
        name = self.theme_name.get_text().strip()
        if not name:
            self.theme_msg.set_text('Give the preset a name first')
            return
        pid = 'my-' + re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        mine = custom_presets()
        mine[pid] = {'name': name, 'about': 'Saved from Login & lock screen',
                     'look': dict(getattr(self, 'look', LOOK_DEFAULTS))}
        write_atomic(CUSTOM_PRESETS, json.dumps(mine, indent=2) + '\n')
        app = self.get_application()
        self.destroy()
        win = type(self)(app, select='theme:1')
        win.theme_msg.set_text(f'Saved "{name}"')
        win.present()

    def theme_delete(self, pid):
        mine = custom_presets()
        mine.pop(pid, None)
        write_atomic(CUSTOM_PRESETS, json.dumps(mine, indent=2) + '\n')
        app = self.get_application()
        self.destroy()
        type(self)(app, select='theme:1').present()

    # -- login / lock screen look (apps/zorro-dm theme, /etc/zorro-dm/look.json)
    def look_page(self):
        box = Pages()
        try:
            self.look = json.loads(Path(LOOK_FILE).read_text())
        except (OSError, ValueError):
            self.look = {}
        if _look_draft:                     # 'Back to defaults' rebuilt the window
            self.look = dict(_look_draft)
            _look_draft.clear()
        for k, v in LOOK_DEFAULTS.items():
            self.look.setdefault(k, v)
        L = self.look

        self.look_view = None
        try:
            gi.require_version('WebKit2', '4.1')
            from gi.repository import WebKit2
            ucm = WebKit2.UserContentManager()
            ucm.add_script(WebKit2.UserScript.new(
                'window.ZORRO_LOOK = ' + json.dumps(L) + ';',
                WebKit2.UserContentInjectedFrames.TOP_FRAME,
                WebKit2.UserScriptInjectionTime.START, None, None))
            view = WebKit2.WebView.new_with_user_content_manager(ucm)
            st = view.get_settings()
            st.set_enable_webgl(True)
            black = Gdk.RGBA()
            black.parse('black')
            view.set_background_color(black)
            view.connect('context-menu', lambda *a: True)
            view.set_size_request(-1, 210)
            # the WebGL page (a web process) starts when the Look tab is first opened
            self.when_shown('login', lambda v=view: v.load_uri('file://' + str(DM_DIR / 'theme' / 'secondary.html')))
            frame = Gtk.Box(margin_start=18, margin_end=18, margin_top=14)
            view.set_hexpand(True)
            frame.add(view)
            box.header(frame)
            self.look_view = view
        except (ValueError, ImportError):
            box.header(note('Live preview needs gir1.2-webkit2-4.1.'))

        def setv(key, value):
            L[key] = value
            if self.look_view:
                self.look_view.evaluate_javascript(
                    f'window.FX && FX.setLook({json.dumps({key: value})})', -1,
                    None, None, None, None, None)
            self.look_msg.set_text('Saving soon…')
            # saved by itself once you stop changing things (the password is asked once and
            # then remembered for a few minutes), like every other setting in the app
            ui.later('greeter-look', self.look_save, 1500)

        scale = lambda key, lo, hi, step, fmt=None: ui.scale(lo, hi, step, L[key],          # noqa: E731
                                                             lambda v: setv(key, v), fmt)
        colour = lambda key: ui.colour(L[key], lambda v: setv(key, v))                       # noqa: E731
        switch = lambda key: ui.switch(L[key], lambda v: setv(key, v))                       # noqa: E731
        grid = ui.form

        x = lambda v: f'{v:.1f}×'
        bgk = Gtk.ComboBoxText()
        for k, label in LOOK_BACKGROUNDS.items():
            bgk.append(k, label)
        bgk.set_active_id(L['background'])
        bgk.connect('changed', lambda w: setv('background', w.get_active_id()))
        box.add(heading('Iridescent background', 'Background'))
        box.add(grid([('Kind', bgk), ('Brightness', scale('bg_strength', 0, 3, 0.05, x)),
                      ('Flowing speed', scale('bg_speed', 0, 5, 0.05, x)),
                      ('Chromatic aberration', scale('bg_aberration', 0, 4, 0.05, x))]))
        box.add(note('Flowing colour behind the animal; where colours fold, the light '
                     'splits into a rainbow edge. Computed at low resolution: light on the GPU.'))
        animals = Gtk.ComboBoxText()
        for k, label in LOOK_ANIMALS.items():
            animals.append(k, label)
        animals.set_active_id(animal_id(L['animal']))
        animals.connect('changed', lambda w: setv('animal', w.get_active_id()))
        box.add(heading('Endangered sea animal (wireframe)', 'Animal'))
        box.add(grid([('Animal', animals), ('Line colour', colour('line_colour')),
                      ('Line density', scale('density', 0.3, 3, 0.1, x)),
                      ('Size', scale('size', 0.2, 3, 0.05, x)),
                      ('Swim speed', scale('swim_speed', 0.1, 5, 0.1, x))]))
        box.add(heading('Passing by'))
        box.add(grid([('Crossing takes', scale('pass_seconds', 10, 300, 5, lambda v: f'{v:.0f} s')),
                      ('Empty water between', scale('gap_seconds', 0, 300, 5, lambda v: f'{v:.0f} s')),
                      ('Far away, deep down', scale('far', 0, 1, 0.05, lambda v: f'{v * 100:.0f}%'))]))
        box.add(heading('Marine snow', 'Particles'))
        box.add(grid([('Amount', scale('snow_amount', 0, 2000, 10)),
                      ('Speed', scale('snow_speed', 0, 10, 0.1, x)),
                      ('Size', scale('snow_size', 0.2, 6, 0.1, x)),
                      ('Brightness', scale('snow_alpha', 0, 4, 0.1, x)),
                      ('Colour', colour('snow_colour'))]))
        box.add(heading('Old TV', 'TV noise'))
        box.add(grid([('Grain / static', scale('grain', 0, 4, 0.1, x)),
                      ('Scratches', scale('scratches', 0, 4, 0.1, x)),
                      ('Dust and hairs', scale('dust', 0, 4, 0.1, x)),
                      ('Scanlines', scale('scanlines', 0, 3, 0.1, x)),
                      ('Dark corners', scale('vignette', 0, 1.5, 0.05, x)),
                      ('Film flicker', scale('flicker', 0, 4, 0.1, x))]))
        kind = Gtk.ComboBoxText()
        for k, label in CBLUR_MODES.items():
            kind.append(k, label)
        kind.set_active_id(L['cblur_mode'])
        kind.connect('changed', lambda w: setv('cblur_mode', w.get_active_id()))
        box.add(heading('Chromatic blur', 'Chromatic blur'))
        box.add(grid([('Kind', kind), ('Strength', scale('cblur', 0, 4, 0.05, x)),
                      ('Coloured glow', scale('bloom', 0, 4, 0.05, x))]))
        box.add(note('The light splits into its colours and smears, like through a lens.'))
        box.add(heading('Chromatic split and glitches', 'Glitches'))
        box.add(grid([('Colour split', scale('chroma', 0, 8, 0.1, x)),
                      ('Glitches: how often', scale('glitch_rate', 0, 6, 0.1, x)),
                      ('Glitches: how strong', scale('glitch_strength', 0, 3, 0.1, x)),
                      ('Colour bars', switch('bars')),
                      ('CRT switch-on at start', switch('crt'))]))
        box.add(note('0 switches an effect off. Glitches also come with key presses on '
                     'the login screen.'))
        box.add(heading('Clock and date', 'Clock'))
        box.add(grid([('Show the clock', switch('clock'))]))
        box.add(note('Top left on the login and lock screen.'))

        bottom = Gtk.Box(spacing=8)
        test = Gtk.Button(label='Full-screen test',
                          tooltip_text='The real login screen in a window; password: test')
        test.connect('clicked', lambda b: self.look_test())
        reset = Gtk.Button(label='Back to defaults')
        reset.connect('clicked', lambda b: self.look_reset())
        self.look_msg = note()
        self.look_msg.set_hexpand(True)
        for w in (test, reset, self.look_msg):
            bottom.add(w)
        box.footer(bottom)
        return box

    def look_save(self):
        self.look_msg.set_text('Saving…')

        def work():
            try:
                with SAVING:                # the look as it is when its turn comes
                    r = subprocess.run(['pkexec', LOOK_HELPER, 'greeter-look', json.dumps(self.look)],
                                       capture_output=True, text=True, timeout=60)
                msg = ('Saved: shows at the next login / lock' if r.returncode == 0 else
                       'Not saved (password cancelled): change something to try again' if r.returncode in (126, 127) else
                       (r.stderr.strip().splitlines() or ['failed'])[-1])
            except (OSError, subprocess.TimeoutExpired) as e:
                msg = f'Could not save: {e}'
            if not getattr(self, 'dead', False):
                idle(self.look_msg.set_text, msg)
        threading.Thread(target=work).start()       # not a daemon: a save at closing still finishes

    def look_test(self):
        path = RUNTIME / 'zorro-look-test.json'     # private, one file, reused
        write_atomic(path, json.dumps(self.look))
        spawn([str(DM_DIR / 'zorro-greeter'), '--preview', '--look', str(path)])

    def look_reset(self):
        ui.drop_later('greeter-look')
        _look_draft.update(LOOK_DEFAULTS)
        for k in KEEP_ON_PRESET:            # your own choices stay (the clock)
            _look_draft[k] = getattr(self, 'look', {}).get(k, LOOK_DEFAULTS[k])
        app = self.get_application()
        self.destroy()
        win = type(self)(app, select='look:0')
        win.look_msg.set_text('Back to defaults: saving…')
        win.present()
        win.look_save()
