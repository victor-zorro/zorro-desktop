"""app: Theme and Login screen tabs"""
import json
import os
import re
import subprocess
import threading
from pathlib import Path
from .base import HOME, RUNTIME, load_conf, spawn, update_conf, write_atomic
from .look import CBLUR_MODES, CUSTOM_PRESETS, DM_DIR, LOOK_ANIMALS, LOOK_BACKGROUNDS, LOOK_DEFAULTS, LOOK_FILE, _look_draft, custom_presets, theme_presets
from .power import LOOK_HELPER
from .ui import Pages, heading, note
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gdk, Gtk


class LookPages:
    """Theme tab and Login screen tab (a mixin of the app window)"""

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
                     'together. Fine-tune it in the Login screen tab.'))

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
        box.add(note('Saves what the Login screen tab shows now (also unsaved changes).'))
        box.footer(self.theme_msg)
        return box

    def theme_apply(self, pid, p):
        look = {**LOOK_DEFAULTS, **p['look']}
        self.theme_msg.set_text(f'Applying {p["name"]}… (your password, once)')

        def work():
            try:
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
            GLib.idle_add(self.theme_done, msg, ok)
        threading.Thread(target=work, daemon=True).start()

    def theme_done(self, msg, ok):
        if ok:                                  # rebuild: Login screen tab shows the new look
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
        mine[pid] = {'name': name, 'about': 'Saved from the Login screen tab',
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
            view.load_uri('file://' + str(DM_DIR / 'theme' / 'secondary.html'))
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
            self.look_msg.set_text('Not saved yet')

        def scale(key, lo, hi, step, fmt=None):
            sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, step)
            sc.set_hexpand(True)
            sc.set_value(float(L[key]))
            sc.set_value_pos(Gtk.PositionType.RIGHT)
            sc.set_digits(2 if step < 0.1 else 1 if step < 1 else 0)
            if fmt:
                sc.connect('format-value', lambda w, v: fmt(v))
            sc.connect('value-changed', lambda w: setv(key, round(w.get_value(), 2)))
            return sc

        def colour(key):
            b = Gtk.ColorButton(halign=Gtk.Align.START)
            c = Gdk.RGBA()
            c.parse(L[key])
            b.set_rgba(c)
            b.connect('color-set', lambda w: setv(key, '#%02x%02x%02x' % tuple(
                round(x * 255) for x in (w.get_rgba().red, w.get_rgba().green, w.get_rgba().blue))))
            return b

        def switch(key):
            sw = Gtk.Switch(active=bool(L[key]), halign=Gtk.Align.START)
            sw.connect('notify::active', lambda w, _p: setv(key, w.get_active()))
            return sw

        def grid(rows):
            g = Gtk.Grid(column_spacing=12, row_spacing=6)
            for i, (label, w) in enumerate(rows):
                g.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
                g.attach(w, 1, i, 1, 1)
            return g

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
        animals.set_active_id(L['animal'])
        animals.connect('changed', lambda w: setv('animal', w.get_active_id()))
        box.add(heading('Endangered sea animal (wireframe)', 'Animal'))
        box.add(grid([('Animal', animals), ('Line colour', colour('line_colour')),
                      ('Line density', scale('density', 0.3, 3, 0.1, x)),
                      ('Size', scale('size', 0.2, 3, 0.05, x)),
                      ('Swim speed', scale('swim_speed', 0.1, 5, 0.1, x))]))
        box.add(heading('Passing by', 'Passing'))
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

        bottom = Gtk.Box(spacing=8)
        save = Gtk.Button(label='Save for login and lock screen')
        save.get_style_context().add_class('suggested-action')
        save.connect('clicked', lambda b: self.look_save())
        test = Gtk.Button(label='Full-screen test',
                          tooltip_text='The real login screen in a window; password: test')
        test.connect('clicked', lambda b: self.look_test())
        reset = Gtk.Button(label='Back to defaults')
        reset.connect('clicked', lambda b: self.look_reset())
        self.look_msg = note()
        self.look_msg.set_hexpand(True)
        for w in (save, test, reset, self.look_msg):
            bottom.add(w)
        box.footer(bottom)
        return box

    def look_save(self):
        self.look_msg.set_text('Saving…')

        def work():
            try:
                r = subprocess.run(['pkexec', LOOK_HELPER, 'greeter-look', json.dumps(self.look)],
                                   capture_output=True, text=True, timeout=60)
                msg = ('Saved: shows at the next login / lock' if r.returncode == 0 else
                       (r.stderr.strip().splitlines() or ['failed'])[-1])
            except (OSError, subprocess.TimeoutExpired) as e:
                msg = f'Could not save: {e}'
            GLib.idle_add(self.look_msg.set_text, msg)
        threading.Thread(target=work, daemon=True).start()

    def look_test(self):
        path = RUNTIME / 'zorro-look-test.json'     # private, one file, reused
        write_atomic(path, json.dumps(self.look))
        spawn([str(DM_DIR / 'zorro-greeter'), '--preview', '--look', str(path)])

    def look_reset(self):
        _look_draft.update(LOOK_DEFAULTS)
        app = self.get_application()
        self.destroy()
        win = type(self)(app, select='look:0')
        win.look_msg.set_text('Defaults shown: not saved yet')
        win.present()
