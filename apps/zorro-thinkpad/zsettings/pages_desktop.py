"""app: Desktop tab"""
import json
import os
import shutil
import threading
from pathlib import Path
from .base import APPS, HOME, load_conf, osd, run, spawn, update_conf, write_atomic
from .fxshim import Snow, zorro_fx
from .look import LOOK_ANIMALS, LOOK_BACKGROUNDS, WALL_DEFAULTS
from .power import load_orb, load_script
from .ui import Pages, heading, idle, note, radios
from .windows import TITLE_SIZES, apply_windows, win_conf
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gdk, Gtk


class DesktopPages:
    """Desktop tab: info circle, overlays, windows, text, launcher, wallpaper (a mixin of the app window)"""

    # -- overlays (shared zorro-fx settings, live preview)
    def orb_page(self):
        """the round info area (apps/zorro-orb): what it shows, size and place"""
        box = Pages()
        orb = load_orb()
        if not orb:
            box.add(note('apps/zorro-orb is missing.'))
            return box
        c = orb.load_conf()
        items = {k: v[0] for k, v in orb.ITEMS.items()}

        pending = {}

        def flush():
            cur = orb.load_conf()
            cur.update(pending)
            pending.clear()
            write_atomic(orb.CONF, json.dumps(cur, indent=2) + '\n')
            self.orb_save_id = None
            return False

        def save(**kv):                     # sliders: write once they rest (0.3 s)
            pending.update(kv)
            if getattr(self, 'orb_save_id', None):
                GLib.source_remove(self.orb_save_id)
            self.orb_save_id = GLib.timeout_add(300, flush)

        def combo(current, on_change, options):
            cb = Gtk.ComboBoxText()
            for k, label in options.items():
                cb.append(k, label)
            cb.set_active_id(current)
            cb.connect('changed', lambda w: on_change(w.get_active_id()))
            return cb

        box.add(heading('What the circle shows', 'Info & zones'))
        g = Gtk.Grid(column_spacing=12, row_spacing=6)
        g.attach(Gtk.Label(label='Resting (no mouse)', xalign=0), 0, 0, 1, 1)
        g.attach(combo(c['rest'], lambda v: save(rest=v),
                       {k: v for k, v in items.items() if k != 'none'}), 1, 0, 1, 1)
        for i, (z, zname) in enumerate(orb.ZONE_NAMES.items(), 1):
            g.attach(Gtk.Label(label=f'{zname} quarter', xalign=0), 0, i, 1, 1)
            g.attach(combo(c['zones'].get(z, 'none'),
                           lambda v, z=z: save(zones={**orb.load_conf()['zones'], z: v}),
                           items), 1, i, 1, 1)
        box.add(g)
        box.add(note('The quarters are invisible: move the mouse over one and the circle '
                     'shows its information; click to open the matching app.'))

        box.add(heading('Size and place', 'Size & place'))
        g = Gtk.Grid(column_spacing=12, row_spacing=6)
        size = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 140, 420, 10)
        size.set_hexpand(True)
        size.set_value(c['size'])
        size.set_value_pos(Gtk.PositionType.RIGHT)
        size.connect('format-value', lambda w, v: f'{v:.0f} px')
        size.connect('value-changed', lambda w: save(size=int(w.get_value())))
        margin = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 200, 2)
        margin.set_value(c['margin'])
        margin.set_value_pos(Gtk.PositionType.RIGHT)
        margin.connect('format-value', lambda w, v: f'{v:.0f} px')
        margin.connect('value-changed', lambda w: save(margin=int(w.get_value())))
        corners = {'bottom-right': 'Bottom right', 'bottom-left': 'Bottom left',
                   'top-right': 'Top right', 'top-left': 'Top left'}
        colour = Gtk.ColorButton()
        rgba = Gdk.RGBA()
        rgba.parse(c.get('text_colour', '#d8d8de'))
        colour.set_rgba(rgba)
        colour.connect('color-set', lambda w: save(text_colour=w.get_rgba().to_string()))
        for i, (label, w) in enumerate((
                ('Diameter', size), ('Corner', combo(c['corner'], lambda v: save(corner=v), corners)),
                ('Distance from the edges', margin), ('Text colour', colour))):
            g.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
            g.attach(w, 1, i, 1, 1)
        box.add(g)
        box.add(note('Changes show on the desktop within a second.'))
        return box

    def fx_page(self, profile, box=None):
        """look settings of one zorro-fx profile (overlay / orb / app)"""
        box = box or Pages()
        if not zorro_fx:
            box.add(note('apps/zorro-fx is missing: plain dark backgrounds.'))
            return box
        s = dict(zorro_fx.settings(profile))
        self.fx = getattr(self, 'fx', {})
        self.fx[profile] = s
        self.fx_save_ids = getattr(self, 'fx_save_ids', {})
        set_ = lambda key, value: self.fx_set(profile, key, value)

        if profile == 'overlay':            # preview of the indicator, on every sub-page
            prev = Gtk.Box(spacing=14)
            prev.get_style_context().add_class('zosd')
            icon = Gtk.Image.new_from_icon_name('audio-volume-medium-symbolic',
                                                Gtk.IconSize.DIALOG)
            icon.set_pixel_size(28)
            pbar = Gtk.ProgressBar(valign=Gtk.Align.CENTER, fraction=0.6)
            pbar.set_size_request(200, -1)
            prev.add(icon)
            prev.add(pbar)
            prev.add(Gtk.Label(label='60%'))
            outer = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
            outer.add(prev)
            Snow(outer, radius=14, inner=prev, max_spill=12, profile=profile)
            frame = Gtk.Box(vexpand=False, margin_start=18, margin_end=18, margin_top=14)
            frame.set_app_paintable(True)
            frame.connect('draw', self.fx_checker)
            inner = Gtk.Box(margin=8)
            inner.set_center_widget(outer)
            frame.add(inner)
            box.header(frame)

        def combo(key, options):
            c = Gtk.ComboBoxText()
            for k, label in options.items():
                c.append(k, label)
            c.set_active_id(s[key])
            c.connect('changed', lambda w: set_(key, w.get_active_id()))
            return c

        def scale(key, lo, hi, step, digits=1, fmt=None):
            sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, step)
            sc.set_hexpand(True)
            sc.set_digits(digits)
            sc.set_value(s[key])
            sc.set_value_pos(Gtk.PositionType.RIGHT)
            if fmt:
                sc.connect('format-value', lambda w, v: fmt(v))
            sc.connect('value-changed', lambda w: set_(key, round(w.get_value(), 2)))
            return sc

        def switch(key):
            sw = Gtk.Switch(active=s[key], halign=Gtk.Align.START)
            sw.connect('notify::active', lambda w, _p: set_(key, w.get_active()))
            return sw

        def grid(part):
            g = Gtk.Grid(column_spacing=12, row_spacing=6)
            for i, (label, w) in enumerate(part):
                g.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
                g.attach(w, 1, i, 1, 1)
            return g

        pct = lambda v: f'{v * 100:.0f}%'
        particles = [
            ('Pattern', combo('pattern', zorro_fx.PATTERNS)),
            ('Colour', combo('colour', {k: v[0] for k, v in zorro_fx.COLOURS.items()})),
            ('Amount', scale('amount', 0, 60, 1)),
            ('Speed', scale('speed', 0.1, 5, 0.1)),
            ('Particle size', scale('size', 0.4, 3, 0.1)),
            ('Glow', switch('glow')),
        ]
        looks = [('Background', scale('opacity', 0, 1, 0.01, 2, pct)),
                 ('Particles', scale('particle_opacity', 0, 1, 0.01, 2, pct))]
        if profile != 'app':
            looks.insert(0, ('Spill onto the screen',
                             scale('spill', 0, 300, 5, 0, lambda v: f'{v:.0f} px')))
        if profile == 'overlay':
            looks.append(('Level bar', scale('bar_opacity', 0, 1, 0.01, 2, pct)))
            looks.append(('Indicator stays',
                          scale('osd_seconds', 0.5, 5, 0.25, 2, lambda v: f'{v:.2g} s')))
        if profile == 'app':
            box.add(heading('Particle background', 'Background'))
            box.add(grid([('Use it', switch('enabled'))]))
            box.add(note('Gives this window the same black background with moving '
                         'particles. Background = how dark, Particles = how visible.'))
            box.add(grid(looks))
            box.add(heading('Particles', 'Particles'))
        else:
            box.add(heading('Particles', 'Particles'))
        box.add(grid(particles))
        if profile != 'app':
            box.add(note('Flock: move the mouse over it and the swarm follows.'))
            box.add(heading('Box and transparency', 'Transparency'))
            box.add(grid(looks))
            box.add(note('How visible each part is: 0% = invisible, 100% = solid. '
                         'Without a compositor, what shows through is a still image of '
                         'the screen.'))
        bottom = Gtk.Box(spacing=8)
        if profile == 'overlay':
            show = Gtk.Button(label='Show on screen',
                              tooltip_text='The real indicator, bottom centre')
            show.connect('clicked', lambda b: osd('audio-volume-medium-symbolic', 60))
            bottom.add(show)
        reset = Gtk.Button(label='Back to defaults')
        reset.connect('clicked', lambda b: self.fx_reset(profile))
        bottom.add(reset)
        box.footer(bottom)
        return box

    def follow_app_bg(self):
        ctx = self.get_style_context()
        on = zorro_fx.settings('app')['enabled']
        if on != ctx.has_class('zfx-app'):
            (ctx.add_class if on else ctx.remove_class)('zfx-app')
        return True

    def fx_checker(self, w, cr):
        a = w.get_allocation()
        cr.rectangle(0, 0, a.width, a.height)
        cr.clip()
        cr.set_source_rgb(0.80, 0.80, 0.83)
        cr.paint()
        cr.set_source_rgb(0.62, 0.62, 0.66)
        for y in range(0, a.height, 16):
            for x in range(0, a.width, 16):
                if (x // 16 + y // 16) % 2:
                    cr.rectangle(x, y, 16, 16)
        cr.fill()
        return False

    def fx_set(self, profile, key, value):
        self.fx[profile][key] = value
        zorro_fx.preview(profile, self.fx[profile])      # this window follows at once
        if self.fx_save_ids.get(profile):
            GLib.source_remove(self.fx_save_ids[profile])
        self.fx_save_ids[profile] = GLib.timeout_add(300, self.fx_save, profile)

    def fx_save(self, profile):
        self.fx_save_ids[profile] = None
        zorro_fx.save(self.fx[profile], profile)
        return False

    def fx_reset(self, profile):
        tid = self.fx_save_ids.get(profile)
        if tid:                             # a waiting save must not undo the reset
            GLib.source_remove(tid)
            self.fx_save_ids[profile] = None
        zorro_fx.save(zorro_fx.PROFILES[profile], profile)
        zorro_fx._preview.pop(profile, None)
        sec = {'overlay': 'fx:0', 'app': 'applook:0', 'orb': 'orb:2'}[profile]
        app = self.get_application()
        self.destroy()                  # rebuild with the default values
        type(self)(app, select=sec).present()

    # -- hardware
    HW_GROUPS = {'Webcam': 'Camera & sound', 'Microphone': 'Camera & sound',
                 'Speakers': 'Camera & sound', 'Sound output': 'Camera & sound',
                 'Sound input': 'Camera & sound', 'Bluetooth': 'Bluetooth',
                 'Wi-Fi': 'Network', 'Mobile data (LTE)': 'Network'}

    # -- text and colours: GTK apps, terminal, window theme, info circle
    def text_page(self):
        box = Pages()
        c = win_conf()

        def setv(key, value):
            c[key] = value
            update_conf('windows', **{key: value})
            if key == 'text':           # the info circle's text too
                orb = load_orb()
                if orb:
                    cur = orb.load_conf()
                    cur['text_colour'] = value
                    write_atomic(orb.CONF, json.dumps(cur, indent=2) + '\n')
            if self.win_apply_id:
                GLib.source_remove(self.win_apply_id)
            self.win_apply_id = GLib.timeout_add(600, self.windows_apply)

        fams = sorted({l.split(',')[0].strip() for l in run('fc-list', ':', 'family').splitlines()
                       if l.strip() and 'Emoji' not in l})
        font = Gtk.ComboBoxText()
        for fam in fams:
            font.append(fam, fam)
        font.set_active_id(c['font'])
        font.connect('changed', lambda w: setv('font', w.get_active_id()))

        def spin(key, lo, hi):
            sp = Gtk.SpinButton.new_with_range(lo, hi, 0.5)
            sp.set_value(float(c[key]))
            sp.set_halign(Gtk.Align.START)
            sp.connect('value-changed', lambda w: setv(key, round(w.get_value(), 1)))
            return sp

        def colour(key):
            b = Gtk.ColorButton(halign=Gtk.Align.START)
            rgba = Gdk.RGBA()
            rgba.parse(c[key])
            b.set_rgba(rgba)
            b.connect('color-set', lambda w: setv(key, '#%02x%02x%02x' % tuple(
                round(v * 255) for v in (w.get_rgba().red, w.get_rgba().green, w.get_rgba().blue))))
            return b

        icon_op = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.3, 1, 0.02)
        icon_op.set_hexpand(True)
        icon_op.set_value(float(load_conf().get('icon_opacity', 0.5)))
        icon_op.set_value_pos(Gtk.PositionType.RIGHT)
        icon_op.connect('format-value', lambda w, v: f'{v * 100:.0f}%')
        build = APPS / 'zorro-icons' / 'build-icons'
        self.icon_build_id = None

        style = Gtk.ComboBoxText()
        for k, v in (('official', 'Official app icons, black and white'),
                     ('lucide', 'White Lucide line icons')):
            style.append(k, v)
        style.set_active_id(load_conf().get('icon_style', 'official'))

        def icons_changed(_w):
            update_conf(None, icon_opacity=round(icon_op.get_value(), 2),
                        icon_style=style.get_active_id() or 'official')
            if self.icon_build_id:
                GLib.source_remove(self.icon_build_id)
            self.icon_build_id = GLib.timeout_add(700, lambda: (
                spawn([str(build), '--opacity', str(round(icon_op.get_value(), 2)),
                       '--style', style.get_active_id() or 'official']),
                setattr(self, 'icon_build_id', None)) and False)
        style.connect('changed', icons_changed)
        icon_op.connect('value-changed', icons_changed)
        g = Gtk.Grid(column_spacing=12, row_spacing=8)
        for i, (label, w) in enumerate((('App icons', style), ('Icons: visibility', icon_op),
                                        ('Font', font), ('Size in apps', spin('font_size', 6, 20)),
                                        ('Size in the terminal', spin('term_size', 6, 24)),
                                        ('Text colour', colour('text')),
                                        ('Accent colour', colour('accent')))):
            g.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
            g.attach(w, 1, i, 1, 1)
        box.add(heading('Screen font and colours', 'Text & colours'))
        box.add(g)
        box.add(note('Used by GTK apps (windows opened from now on), the terminal (right '
                     'away), the window title bars and menus (accent) and the info circle '
                     '(text). Chromatic sea: text #d8d8de, accent cyan #19e6ff.'))
        return box

    # -- windows: title bars, compositor, kitty
    def windows_page(self):
        box = Pages()
        c = win_conf()
        self.win_c = c
        self.win_apply_id = None

        def setv(key, value):
            c[key] = value
            update_conf('windows', **{key: value})
            if self.win_apply_id:
                GLib.source_remove(self.win_apply_id)
            self.win_apply_id = GLib.timeout_add(400, self.windows_apply)

        def grid(rows):
            g = Gtk.Grid(column_spacing=12, row_spacing=8)
            for i, (label, w) in enumerate(rows):
                g.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
                g.attach(w, 1, i, 1, 1)
            return g

        box.add(heading('Window title bars', 'Title bars'))
        box.add(radios([(k, v[0]) for k, v in TITLE_SIZES.items()], c['titlebar'],
                       lambda k: setv('titlebar', k)))
        box.add(note('Our own dark Openbox theme "Zorro": the bar and its buttons '
                     '(minimise, maximise, close) grow together. Close turns red '
                     'under the mouse.'))

        box.add(heading('Transparency', 'Transparency'))
        comp = Gtk.Switch(active=c['compositor'], halign=Gtk.Align.START)
        comp.connect('notify::active', lambda w, _p: setv('compositor', w.get_active()))
        op = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.4, 1, 0.02)
        op.set_hexpand(True)
        op.set_value(c['kitty_opacity'])
        op.set_value_pos(Gtk.PositionType.RIGHT)
        op.connect('format-value', lambda w, v: f'{v * 100:.0f}%')
        op.connect('value-changed', lambda w: setv('kitty_opacity', round(w.get_value(), 2)))
        blur = Gtk.Switch(active=c['kitty_blur'], halign=Gtk.Align.START)
        blur.connect('notify::active', lambda w, _p: setv('kitty_blur', w.get_active()))
        box.add(grid([('Compositor (picom)', comp), ('Terminal (kitty) opacity', op),
                      ('Blur behind the terminal', blur)]))
        box.add(note('Real transparency needs the compositor. It also makes the '
                     'indicator and info circle truly see-through. Off = everything '
                     'solid, a little less battery.'))
        self.win_msg = note()
        if not shutil.which('picom'):
            self.win_msg.set_text('picom is not installed yet: sudo apt install picom')
        box.footer(self.win_msg)
        return box

    def windows_apply(self):
        """one worker at a time; changes made meanwhile cause one more run after it"""
        self.win_apply_id = None
        self.win_msg.set_text('Applying…')
        if getattr(self, 'win_busy', False):
            self.win_again = True
            return False
        self.win_busy, self.win_again = True, False

        def work():
            while True:
                try:
                    apply_windows()
                except Exception as e:      # noqa: BLE001 - shown to the user
                    idle(self.win_msg.set_text, f'Failed: {e}')
                if not self.win_again:
                    break
                self.win_again = False
            self.win_busy = False
            idle(self.win_msg.set_text, 'Applied' if shutil.which('picom') or
                          not self.win_c['compositor'] else
                          'Title bars applied; transparency needs: sudo apt install picom')
        threading.Thread(target=work, daemon=True).start()
        return False

    # -- the dial launcher (apps/zorro-dial)
    def dial_page(self):
        box = Pages()
        dial = load_script('zorro-dial')
        if not dial:
            box.add(note('apps/zorro-dial is missing.'))
            return box
        c = dial.load_conf()

        def save(order=None):
            # the dial writes the dragged order itself: keep what it wrote meanwhile
            now = dial.load_conf()
            c['order'] = now.get('order', {}) if order is None else order
            c['notes_hide_vaults'] = now.get('notes_hide_vaults', [])     # set in Accounts → Obsidian
            write_atomic(dial.CONF, json.dumps(c, indent=2) + '\n')

        box.add(heading('Where the dialer opens', 'Place'))
        place = Gtk.ComboBoxText(halign=Gtk.Align.START)
        place.append('orb', 'Fanning out from the clock (info circle)')
        place.append('centre', 'A full circle in the middle of the screen')
        place.set_active_id(c.get('anchor', 'orb'))
        place.connect('changed', lambda w: (c.__setitem__('anchor', w.get_active_id()), save()))
        box.add(place)
        box.add(note('From the clock, the rings fan into the screen: the apps you use most '
                     'sit right next to the clock, the outer rings hold more.'))
        box.add(heading('Slices (up to six)', 'Slices'))
        g = Gtk.Grid(column_spacing=10, row_spacing=6)
        g.attach(Gtk.Label(label='Name', xalign=0), 0, 0, 1, 1)
        g.attach(Gtk.Label(label='App categories (comma separated)', xalign=0), 1, 0, 1, 1)
        rows = (c['slices'] + [{'name': '', 'categories': []}] * 6)[:6]
        entries = []

        def changed(_w):
            c['slices'] = [{'name': n.get_text().strip(),
                            'categories': [x.strip() for x in k.get_text().split(',') if x.strip()]}
                           for n, k in entries if n.get_text().strip()] or c['slices']
            save()
        for i, s in enumerate(rows):
            name = Gtk.Entry(text=s['name'], width_chars=9, placeholder_text='(unused)')
            cats = Gtk.Entry(text=', '.join(s['categories']), hexpand=True)
            name.connect('changed', changed)
            cats.connect('changed', changed)
            entries.append((name, cats))
            g.attach(name, 0, i + 1, 1, 1)
            g.attach(cats, 1, i + 1, 1, 1)
        box.add(g)
        box.add(note('An app goes to the slice you chose for it (Apps), else to the first '
                     'slice whose categories match its .desktop file, else the last slice.'))

        box.add(heading('Which slice each app is in', 'Apps'))
        grid = Gtk.Grid(column_spacing=10, row_spacing=4)
        for i, a in enumerate(sorted(dial.apps(), key=lambda a: a['name'].lower())[:40]):
            cb = Gtk.ComboBoxText()
            cb.append('', 'automatic')
            for s in c['slices']:
                cb.append(s['name'], s['name'])
            cb.set_active_id(c.get('assign', {}).get(a['id'], ''))

            def pick(w, app=a['id']):
                v = w.get_active_id()
                if v:
                    c.setdefault('assign', {})[app] = v
                else:
                    c.setdefault('assign', {}).pop(app, None)
                save()
            cb.connect('changed', pick)
            grid.attach(Gtk.Label(label=a['name'], xalign=0, ellipsize=3, max_width_chars=24),
                        (i % 2) * 2, i // 2, 1, 1)
            grid.attach(cb, (i % 2) * 2 + 1, i // 2, 1, 1)
        box.add(grid)

        box.add(heading('Rings', 'Rings'))
        g = Gtk.Grid(column_spacing=10, row_spacing=8)
        for k, label in enumerate(('Inner ring (most used)', 'Middle ring', 'Outer ring')):
            sp = Gtk.SpinButton.new_with_range(1, 10, 1)
            sp.set_value(c['ring_slots'][k])
            sp.connect('value-changed', lambda w, k=k: (c['ring_slots'].__setitem__(k, int(w.get_value())), save()))
            g.attach(Gtk.Label(label=f'{label}: apps per slice', xalign=0), 0, k, 1, 1)
            g.attach(sp, 1, k, 1, 1)
        box.add(g)
        box.add(heading('File previews', 'Previews'))
        size = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 300, 1100, 20)
        size.set_value(c.get('preview_size', 460))
        size.set_hexpand(True)
        size.set_size_request(380, -1)
        size.set_halign(Gtk.Align.START)
        size.connect('format-value', lambda _s, v: f'{int(v)} × {int(v * 0.78)}')
        for v, label in ((360, 'small'), (460, 'normal'), (700, 'large'), (1000, 'huge')):
            size.add_mark(v, Gtk.PositionType.BOTTOM, label)

        def resized(w):
            c['preview_size'] = int(w.get_value())
            save()
        size.connect('value-changed', resized)
        box.add(size)
        box.add(note('How big the picture, first page or text shows when you rest on a file in '
                     'the Dialer\'s Files part. Takes effect the next time the Dialer opens.'))

        forget = Gtk.Button(label='Forget which apps I use', halign=Gtk.Align.START, margin_top=8)
        forget.connect('clicked', lambda b: (dial.USAGE.unlink(missing_ok=True),
                                             self.dial_msg.set_text('Usage forgotten')))
        box.add(forget)
        reset = Gtk.Button(label='Reset arrangement (back to most used first)',
                           halign=Gtk.Align.START)
        reset.connect('clicked', lambda b: (save(order={}),
                                            self.dial_msg.set_text('Arrangement reset')))
        box.add(reset)
        box.add(note('Drag an app in the dial to move it: within its slice, or onto another '
                     'slice. Apps you never moved follow after, most used inward.'))
        box.add(note('Open the dial with a tap on Super (xcape) or Super+Space; '
                     'rofi stays on Super+Shift+Space.'))
        self.dial_msg = note()
        box.footer(self.dial_msg)
        return box

    # -- living wallpaper (apps/zorro-wall)
    def wall_page(self):
        box = Pages()
        conf = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'zorro-wall' / 'config.json'
        try:
            c = json.loads(conf.read_text())
        except (OSError, ValueError):
            c = {}
        c = {**WALL_DEFAULTS, **c}
        c['look'] = {**{'animal': 'whale', 'background': 'deep'}, **c.get('look', {})}

        def save(**kv):
            c.update(kv)
            write_atomic(conf, json.dumps(c, indent=2) + '\n')
            if kv.get('enabled') and not run('pgrep', '-f', 'bin/zorro-wall$').strip():
                spawn([str(APPS / 'zorro-wall' / 'zorro-wall')])

        def grid(rows):
            g = Gtk.Grid(column_spacing=12, row_spacing=8)
            for i, (label, w) in enumerate(rows):
                g.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
                g.attach(w, 1, i, 1, 1)
            return g

        def switch(key, on_change=None):
            sw = Gtk.Switch(active=bool(c[key]), halign=Gtk.Align.START)
            sw.connect('notify::active', lambda w, _p: (save(**{key: w.get_active()}),
                                                       on_change and on_change(w.get_active())))
            return sw

        def scale(key, lo, hi, step, fmt):
            sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, step)
            sc.set_hexpand(True)
            sc.set_value(float(c[key]))
            sc.set_value_pos(Gtk.PositionType.RIGHT)
            sc.connect('format-value', lambda w, v: fmt(v))
            sc.connect('value-changed', lambda w: save(**{key: round(w.get_value(), 2)}))
            return sc

        def combo(key, options):
            cb = Gtk.ComboBoxText()
            for k, label in options.items():
                cb.append(k, label)
            cb.set_active_id(c['look'].get(key))
            cb.connect('changed', lambda w: save(look={**c['look'], key: w.get_active_id()}))
            return cb

        box.add(heading('Living wallpaper', 'Wallpaper'))
        own = grid([('Animal', combo('animal', LOOK_ANIMALS)),
                    ('Background', combo('background', LOOK_BACKGROUNDS))])
        own.set_sensitive(not c['follow_login'])
        box.add(grid([('On', switch('enabled')),
                      ('Same look as the login screen',
                       switch('follow_login', lambda on: own.set_sensitive(not on)))]))
        box.add(own)
        box.add(note('The login engine as the desktop: the iridescent background with the '
                     'wireframe animal and marine snow, with the TV effects toned down.'))
        box.add(heading('Power', 'Power'))
        box.add(grid([('Frames per second on the charger', scale('fps_ac', 2, 30, 1, lambda v: f'{v:.0f}')),
                      ('Frames per second on battery', scale('fps_battery', 1, 20, 1, lambda v: f'{v:.0f}')),
                      ('Calm frame rate', scale('fps_calm', 1, 24, 1, lambda v: f'{v:.0f}')),
                      ('Resolution', scale('render_scale', 0.25, 1, 0.05, lambda v: f'{v * 100:.0f}%'))]))
        box.add(note('Smart frame rate: full speed only while something moves fast (the animal '
                     'crossing, a glitch, the fade-in); the calm rate while the water is empty. '
                     'Measured on this T14: every frame costs about the same, the effects are '
                     'nearly free. 24 fps ≈ 15% GPU + 20% of one CPU core, 8 fps about a third. '
                     'It stops drawing while windows cover the desktop.'))
        return box
