"""app: the ThinkPad pages (keys, lights), Hardware and Power"""
import os
import re
import shutil
import subprocess
import threading
import time
from .base import KBD_LED, RUNTIME, STAR_ACTIONS, load_conf, run, spawn, sysread, update_conf
from .hardware import SOUNDS, hardware_rows
from .keys import key_star
from .lights import BAT_LOW, DOT_LED, DOT_MODES, KBD_LEVELS, MORSE_TEXT, MORSE_UNIT, OVERRIDES, OVERRIDE_MODES, POWER_LED, set_kbd, set_led
from . import printers
from .power import CHARGE_PRESETS, HELPER, PROFILES, battery_text, tlp_settings
from .ui import KEY_TABLE, MARKS, Pages, heading, idle, later, mark, note, radios
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk


# which section of Hardware a device row goes in (the rest: Other devices)
HW_GROUPS = {'Webcam': 'Camera & sound', 'Microphone': 'Camera & sound', 'Bluetooth': 'Bluetooth'}

class ThinkpadPages:
    """keys and lights pages, the Hardware tab, the Power tab (a mixin of the app window)"""

    # -- keys
    def keys_page(self):
        box = Pages()
        box.add(heading('Fn keys', 'Fn keys'))
        grid = Gtk.Grid(column_spacing=18, row_spacing=4)
        for i, (k, what) in enumerate(KEY_TABLE):
            kl = Gtk.Label(xalign=0)
            kl.set_markup(f'<tt>{GLib.markup_escape_text(k)}</tt>')
            grid.attach(kl, 0, i, 1, 1)
            grid.attach(Gtk.Label(label=what, xalign=0, wrap=True), 1, i, 1, 1)
        box.add(grid)

        box.add(heading('Star key (F12 ★)', 'Star key ★'))
        c = load_conf()
        combo = Gtk.ComboBoxText()
        for k, (label, _) in STAR_ACTIONS.items():
            combo.append(k, label)
        combo.set_active_id(c.get('star', 'screenshot'))
        combo.connect('changed', self.on_star)
        box.add(combo)
        self.custom_box = Gtk.Box(spacing=6, no_show_all=True)
        self.custom = Gtk.Entry(hexpand=True, text=c.get('star_command', ''),
                                placeholder_text='command, e.g.  firefox https://example.org')
        self.custom.connect('changed', lambda e: later('star', lambda: update_conf(None, star_command=e.get_text())))
        test = Gtk.Button(label='Try')
        test.connect('clicked', lambda b: key_star())
        self.custom_box.add(self.custom)
        self.custom_box.add(test)
        self.custom.show()
        test.show()
        box.add(self.custom_box)
        box.add(note('Takes effect right away.'))
        return box

    def on_star(self, combo):
        act = combo.get_active_id()
        update_conf(None, star=act)
        self.custom_box.set_visible(act == 'custom')

    # -- power
    def power_page(self):
        box = Pages()
        tlp = tlp_settings()
        box.add(heading('Battery', 'Battery'))
        self.bat_label = Gtk.Label(label=battery_text(), xalign=0)
        box.add(self.bat_label)
        self.profile_label = note()
        box.add(self.profile_label)
        full = Gtk.Button(label='Charge to 100% once', halign=Gtk.Align.START, margin_top=12,
                          tooltip_text='Until the charger is unplugged, then back to the '
                                       'charge limit (handy before a trip)')
        full.connect('clicked', lambda b: self.helper(['fullcharge'], 'Charging to 100% '
                                                      'until you unplug'))
        box.add(full)

        box.add(heading('Power mode', 'Mode & charging'))
        grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        self.prof = {}
        for i, (key, label) in enumerate((('AC', 'On the charger'), ('BAT', 'On battery'))):
            combo = Gtk.ComboBoxText()
            for p, plabel in PROFILES.items():
                combo.append(p, plabel)
            combo.set_active_id(tlp.get(f'PLATFORM_PROFILE_ON_{key}', 'balanced'))
            if combo.get_active_id() is None:
                combo.set_active_id('balanced')
            self.prof[key] = combo
            grid.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
            grid.attach(combo, 1, i, 1, 1)
        box.add(grid)
        box.add(note('Battery saver: slower, cooler and quieter. Performance: fastest, '
                     'fan more often.'))

        box.add(heading('Charging'))
        lo = tlp.get('START_CHARGE_THRESH_BAT0', '75')
        self.charge = 'full' if lo in ('0', '95', '96') else 'long'
        box.add(radios([(k, v[0]) for k, v in CHARGE_PRESETS.items()], self.charge,
                       lambda k: setattr(self, 'charge', k)))
        box.add(note('Keeping a battery below 80% most of the time makes it last years longer.'))

        row = Gtk.Box(spacing=6, margin_top=12)
        apply = Gtk.Button(label='Apply')
        apply.get_style_context().add_class('suggested-action')
        apply.connect('clicked', self.on_power_apply)
        row.add(apply)
        box.add(row)

        box.add(heading('Screen stays on', 'Screen on'))
        calls = Gtk.Switch(halign=Gtk.Align.START,
                           active=load_conf().get('awake_calls', True))
        calls.connect('notify::active',
                      lambda w, _p: update_conf(None, awake_calls=w.get_active()))
        line = Gtk.Box(spacing=12)
        line.add(Gtk.Label(label='During calls: while the camera or microphone is in use'))
        line.add(calls)
        box.add(line)
        box.add(note('Apps that play video or hold a call (Firefox, Signal, …) also ask the '
                     'screen to stay on; that always works. Otherwise the screen locks after '
                     '10 minutes without input.'))
        self.power_msg = note()
        box.footer(self.power_msg)
        if not os.path.exists(HELPER) or not shutil.which('pkexec'):
            self.power_msg.set_text('Not installed yet: run  sudo apt install pkexec  and  '
                                    'sudo apps/zorro-thinkpad/install.sh')
        self.refresh()
        return box

    def on_power_apply(self, _b):
        _, lo, hi = CHARGE_PRESETS[self.charge]
        self.helper(['power', self.prof['AC'].get_active_id(),
                     self.prof['BAT'].get_active_id(), str(lo), str(hi)], 'Saved')

    def helper(self, args, ok_text):
        self.power_msg.set_text('Working…')

        def work():
            try:
                r = subprocess.run(['pkexec', HELPER, *args], capture_output=True,
                                   text=True, timeout=60)
                msg = ok_text if r.returncode == 0 else \
                    (r.stderr.strip().splitlines() or [f'failed ({r.returncode})'])[-1]
            except (OSError, subprocess.TimeoutExpired) as e:
                msg = f'Could not run the helper: {e}'
            idle(self.helper_done, msg)
        threading.Thread(target=work, daemon=True).start()

    def helper_done(self, msg):
        self.power_msg.set_text(msg)
        self.refresh()
        return False

    def refresh(self):
        if not hasattr(self, 'bat_label'):
            return True                 # the Power tab is not built yet
        self.bat_label.set_text(battery_text())
        prof = sysread('/sys/firmware/acpi/platform_profile', '?')
        src = 'battery' if sysread('/sys/class/power_supply/AC/online', '1') == '0' else 'charger'
        self.profile_label.set_text(f'Now on the {src}, mode: {PROFILES.get(prof, prof)}')
        return True

    def hw_page(self):
        box = Pages()
        self.hw_lists = {}
        self.hw_msg = note()                # also used by the printers part, built in the loop
        for group in ('Camera & sound', 'Bluetooth', 'Printers', 'Other devices'):
            box.add(heading(group, group))
            if group == 'Printers':
                box.add(self.printers_box())
                continue
            lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=6)
            box.add(lst)
            self.hw_lists[group] = lst
        bottom = Gtk.Box(spacing=8)
        self.hw_msg.set_hexpand(True)
        bottom.add(self.hw_msg)
        again = Gtk.Button(label='Check again', valign=Gtk.Align.CENTER)
        again.connect('clicked', lambda b: self.hw_refresh())
        bottom.add(again)
        box.footer(bottom)
        self.bt_found = []
        self.hw_busy = False
        self.when_shown('hardware', self.hw_refresh)     # lsusb, v4l2-ctl, bluetoothctl…
        return box

    def hw_refresh(self):
        if self.hw_busy:
            return
        self.hw_busy = True

        def work():
            rows = hardware_rows(self)
            idle(self.hw_show, rows)
        threading.Thread(target=work, daemon=True).start()

    def hw_show(self, rows):
        self.hw_busy = False
        for lst in self.hw_lists.values():
            for c in lst.get_children():
                c.destroy()
        group = 'Other devices'
        marks = {k: MARKS[k] for k in ('ok', 'warn', 'off')}
        for icon, title, state, detail, acts in rows:
            row = Gtk.Box(spacing=12)
            img = Gtk.Image.new_from_icon_name(icon or 'go-next-symbolic', Gtk.IconSize.DND)
            img.set_opacity(1 if icon else 0)
            row.add(img)
            txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            m, col = marks[state]
            head = Gtk.Label(xalign=0)
            head.set_markup(f'<span foreground="{col}">{m}</span>  '
                            f'<b>{GLib.markup_escape_text(title.strip())}</b>'
                            if icon else f'<span foreground="{col}">{m}</span>  '
                            f'{GLib.markup_escape_text(title.strip())}')
            txt.add(head)
            d = note(detail.replace('    ', ''))
            d.set_selectable(True)
            d.set_can_focus(False)
            txt.add(d)
            row.add(txt)
            for label, cb in acts:
                b = Gtk.Button(label=label, valign=Gtk.Align.CENTER)
                b.connect('clicked', lambda _b, cb=cb: cb())
                row.add(b)
            if not icon:
                row.set_margin_start(28)    # a Bluetooth device under its adapter
            else:
                group = HW_GROUPS.get(title.strip(), 'Other devices')
            self.hw_lists.get(group, self.hw_lists['Other devices']).add(row)
        for lst in self.hw_lists.values():
            lst.show_all()
        return False

    def hw_do(self, busy_text, fn, done_text=None):
        """run fn() in a thread, show progress, then check the hardware again"""
        self.hw_msg.set_text(busy_text)

        def work():
            try:
                res = fn()
            except Exception as e:          # noqa: BLE001 - shown to the user
                res = f'Failed: {e}'
            idle(lambda: (self.hw_msg.set_text(res or done_text or ''),
                                   self.hw_refresh()) and False)
        threading.Thread(target=work, daemon=True).start()

    # actions used by hardware_rows()
    def webcam(self, dev):
        spawn(['vlc', '--no-video-title-show', f'v4l2://{dev}'])
        self.hw_msg.set_text('Webcam preview opens in VLC. Close it when done '
                             '(the camera light goes on while it runs).')

    def mic_toggle(self):
        self.hw_do('…', lambda: run('wpctl', 'set-mute', '@DEFAULT_AUDIO_SOURCE@', 'toggle')
                   and None)

    def mic_test(self):
        def fn():
            import tempfile
            fd, wav = tempfile.mkstemp(suffix='.wav', prefix='zorro-mic-', dir=RUNTIME)
            os.close(fd)
            idle(self.hw_msg.set_text, '● Recording 3 seconds: say something…')
            p = subprocess.Popen(['pw-record', wav], stderr=subprocess.DEVNULL)
            time.sleep(3)
            p.terminate()
            p.wait()
            idle(self.hw_msg.set_text, '▶ Playing it back…')
            run('pw-play', wav, timeout=8)
            try:
                os.unlink(wav)
            except OSError:
                pass
            return 'Microphone test done: did you hear yourself?'
        self.hw_do('…', fn)

    def speaker_test(self):
        def fn():
            for side in ('left', 'right'):
                run('pw-play', str(SOUNDS / f'audio-channel-front-{side}.oga'))
            return 'You should have heard "front left" from the left and "front right" from the right.'
        self.hw_do('▶ Playing a voice on the left, then on the right…', fn)


    # -- lights
    def lights_page(self):
        box = Pages()
        li = load_conf().get('lights', {})
        self.light_msg = note()

        def pick(led, key):
            def cb(mode):
                err = set_led(led, mode)
                update_conf('lights', **{key: mode})
                self.light_msg.set_text(err or '')
            return cb

        box.add(heading('Red dot on the lid: normally', 'Red dot'))
        box.add(radios([(k, v[0]) for k, v in DOT_MODES.items()], li.get('dot', 'on'),
                       pick(DOT_LED, 'dot')))
        box.add(note('In standby the dot still blinks slowly (the firmware does that).'))
        li_text = li.get('morse_text', MORSE_TEXT)
        mrow = Gtk.Box(spacing=8)
        mrow.add(Gtk.Label(label='Morse text'))
        mtext = Gtk.Entry(text=li_text, hexpand=True,
                          placeholder_text='a word or sentence, e.g.  ZORRO WAS HERE')
        # written once you stop typing (the dot restarts its Morse on every change)
        mtext.connect('changed', lambda e: later('morse', lambda: update_conf('lights', morse_text=e.get_text())))
        mrow.add(mtext)
        box.add(mrow)
        srow = Gtk.Box(spacing=8)
        srow.add(Gtk.Label(label='Morse speed'))
        unit = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.05, 0.5, 0.01)
        unit.set_hexpand(True)
        unit.set_inverted(True)                      # right = faster (shorter dot)
        unit.set_value(float(li.get('morse_unit', MORSE_UNIT)))
        unit.connect('format-value', lambda w, v: f'dot {v * 1000:.0f} ms')
        unit.set_value_pos(Gtk.PositionType.RIGHT)
        unit.connect('value-changed',
                     lambda w: update_conf('lights', morse_unit=round(w.get_value(), 3)))
        srow.add(unit)
        box.add(srow)
        box.add(note('Letters, digits and . , ? ! / - @ : = + & are blinked; other '
                     'characters are skipped. The text repeats with a 3 second pause.'))

        box.add(heading('Red dot: activity overrides', 'Dot overrides'))
        ov = li.get('overrides', {})
        grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        for i, (key, label) in enumerate(OVERRIDES):
            c = Gtk.ComboBoxText()
            for k, lab in OVERRIDE_MODES:
                c.append(k, lab)
            c.set_active_id(ov.get(key, 'none'))
            c.connect('changed', lambda w, k=key: update_conf(
                'lights', overrides={**load_conf().get('lights', {}).get('overrides', {}),
                                     k: w.get_active_id()}))
            grid.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
            grid.attach(c, 1, i, 1, 1)
        low = Gtk.SpinButton.new_with_range(5, 50, 1)
        low.set_value(int(li.get('bat_low_pct', BAT_LOW)))
        low.connect('value-changed', lambda w: update_conf('lights', bat_low_pct=int(w.get_value())))
        lrow = Gtk.Box(spacing=6)
        lrow.add(Gtk.Label(label='Battery low means below'))
        lrow.add(low)
        lrow.add(Gtk.Label(label='%'))
        grid.attach(lrow, 0, len(OVERRIDES), 2, 1)
        box.add(grid)
        box.add(note('While one of these is happening the dot shows its pattern instead of '
                     'the normal one; the highest one in the list wins. Morse uses the '
                     'text above.'))

        box.add(heading('Power button light', 'Other lights'))
        box.add(radios([('on', 'On'), ('off', 'Off')], li.get('power', 'on'),
                       pick(POWER_LED, 'power')))

        box.add(heading('Keyboard light'))
        try:
            cur = int(sysread(KBD_LED / 'brightness', '0'))
        except ValueError:
            cur = 0

        def kbd(level):
            self.light_msg.set_text(set_kbd(level) or '')
            update_conf('lights', kbd=level)
        box.add(radios(list(KBD_LEVELS.items()), cur, kbd))
        box.add(note('Fn + Space changes it too. The level is kept after standby and restart.'))
        box.footer(self.light_msg)
        return box
