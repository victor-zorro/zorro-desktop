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


def bt_session(mac, timeout=40):
    """pair, trust and connect in one bluetoothctl session with a pairing agent (one-shot
    commands have no agent, and the adapter must be pairable, else BlueZ refuses quietly).
    Returns ('connected' | 'paired' | 'failed', output)."""
    p = subprocess.Popen(['bluetoothctl'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, bufsize=1)
    out = []
    import select

    def send(cmd):
        p.stdin.write(cmd + '\n')
        p.stdin.flush()

    def wait_for(words, secs):
        end = time.time() + secs
        while time.time() < end:
            r, _, _ = select.select([p.stdout], [], [], 0.5)
            if r:
                line = p.stdout.readline()
                if not line:
                    break
                out.append(line)
                for w in words:
                    if w in line:
                        return w
        return None
    state = 'failed'
    try:
        for cmd in ('agent NoInputNoOutput', 'default-agent', 'pairable on'):
            send(cmd)
            time.sleep(0.3)
        send(f'pair {mac}')
        r = wait_for(['Pairing successful', 'AlreadyExists', 'Failed to pair', 'not available'], 25)
        if r in ('Pairing successful', 'AlreadyExists'):
            state = 'paired'
            send(f'trust {mac}')
            time.sleep(0.5)
            send(f'connect {mac}')
            if wait_for(['Connection successful', 'Failed to connect'], 15) == 'Connection successful':
                state = 'connected'
        send('quit')
        p.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        p.kill()
    return state, ''.join(out)



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

    # -- printers (zsettings/printers.py)
    def printers_box(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=6)
        self.pr_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.add(self.pr_list)
        outer.add(heading('On the network'))
        self.pr_found = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.add(self.pr_found)
        row = Gtk.Box(spacing=8, margin_top=4)
        self.pr_search_btn = Gtk.Button(label='Search the network')
        self.pr_search_btn.connect('clicked', lambda b: self.pr_search())
        row.add(self.pr_search_btn)
        self.pr_addr = Gtk.Entry(placeholder_text='or an address, e.g. 192.168.66.5',
                                 width_chars=26)
        self.pr_addr.connect('activate', lambda e: self.pr_by_address())
        row.add(self.pr_addr)
        b = Gtk.Button(label='Add')
        b.connect('clicked', lambda b: self.pr_by_address())
        row.add(b)
        outer.add(row)
        outer.add(note('Printers that announce themselves (Bonjour / AirPrint) are also added '
                       'by themselves while they are on (cups-browsed). The driver is chosen '
                       'for you: driverless when the printer can, else the matching open-source '
                       'driver.'))
        if not printers.available():
            outer.set_sensitive(False)
            outer.add(note('Printing is not installed: sudo apt install cups'))
        else:
            self.pr_refresh()
        return outer

    def pr_row(self, title, detail, acts, ok=True):
        row = Gtk.Box(spacing=12)
        row.add(Gtk.Image.new_from_icon_name('printer-symbolic', Gtk.IconSize.DND))
        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        head = Gtk.Label(xalign=0)
        sign = mark('ok') if ok else mark('warn')
        head.set_markup(f'{sign}  <b>{GLib.markup_escape_text(title)}</b>')
        txt.add(head)
        d = note(detail)
        d.set_selectable(True)
        d.set_can_focus(False)
        txt.add(d)
        row.add(txt)
        for label, cb in acts:
            b = Gtk.Button(label=label, valign=Gtk.Align.CENTER)
            b.connect('clicked', lambda _b, cb=cb: cb())
            row.add(b)
        return row

    def pr_bg(self, busy, fn, then):
        """run fn() in a thread with a message; then(result) on the main loop"""
        self.hw_msg.set_text(busy)

        def work():
            try:
                res = fn()
            except Exception as e:          # noqa: BLE001 - show it, keep the app alive
                res = e
            idle(lambda: then(res) and False)
        threading.Thread(target=work, daemon=True).start()

    def pr_refresh(self):
        def show(items):
            for c in self.pr_list.get_children():
                c.destroy()
            if isinstance(items, Exception) or not items:
                self.pr_list.add(note('No printer added yet.'))
            for q in items if isinstance(items, list) else []:
                where = re.sub(r'\?.*$', '', printers.unquote(q['uri'].split('://')[-1]))
                acts = [('Test page', lambda n=q['name']: self.pr_bg(
                            'Sending a test page…', lambda: printers.test_page(n),
                            lambda m: self.hw_msg.set_text(m)))]
                if not q['default']:
                    acts.append(('Default', lambda n=q['name']: (printers.set_default(n),
                                                                 self.pr_refresh())))
                acts.append(('Remove', lambda n=q['name']: self.pr_bg(
                    f'Removing {n}…', lambda: printers.remove(n),
                    lambda _r: (self.hw_msg.set_text(f'{n} removed'), self.pr_refresh()))))
                self.pr_list.add(self.pr_row(
                    q['name'] + ('  (default)' if q['default'] else ''),
                    f'{q["state"]} · {where}', acts, ok=q['state'] != 'disabled'))
            self.pr_list.show_all()
            return True
        self.pr_bg('', printers.installed, show)

    def pr_search(self):
        self.pr_search_btn.set_sensitive(False)

        def find():
            return [(p, printers.driver_for(p)) for p in printers.discover()]

        def show(found):
            self.pr_search_btn.set_sensitive(True)
            for c in self.pr_found.get_children():
                c.destroy()
            if isinstance(found, Exception):
                self.hw_msg.set_text(f'Search failed: {found}')
                return True
            for p, (model, desc) in found:
                where = re.sub(r'\?.*$', '', printers.unquote(p['uri'].split('://')[-1]))
                acts = [('Add', lambda p=p: self.pr_add(p))] if model else []
                self.pr_found.add(self.pr_row(p['model'] or where, f'{where}\n{desc}', acts,
                                              ok=bool(model)))
            if not found:
                self.pr_found.add(note('No new printers found. Is it switched on?'))
            self.pr_found.show_all()
            self.hw_msg.set_text(f'{len(found)} printer(s) found' if found else '')
            return True
        self.pr_bg('Searching the network (about 10 s)…', find, show)

    def pr_add(self, p):
        def done(res):
            ok, msg = res if isinstance(res, tuple) else (False, str(res))
            self.hw_msg.set_text(msg)
            if ok:
                self.pr_refresh()
                self.pr_search()
            return True
        self.pr_bg(f'Adding {p.get("model") or p["uri"]}…', lambda: printers.add(p), done)

    def pr_by_address(self):
        host = self.pr_addr.get_text()

        def done(res):
            p, err = res if isinstance(res, tuple) else (None, str(res))
            if not p:
                self.hw_msg.set_text(err)
            else:
                self.pr_add(p)
            return True
        self.pr_bg(f'Looking for a printer at {host}…', lambda: printers.probe_address(host), done)

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

    def bt_power(self, on):
        self.hw_do('…', lambda: run('bluetoothctl', 'power', 'on' if on else 'off') and None)

    def bt_cmd(self, cmd, mac):
        words = {'connect': 'Connecting', 'disconnect': 'Disconnecting', 'remove': 'Forgetting'}

        def fn():
            out = run('bluetoothctl', '--timeout', '15', cmd, mac, timeout=25)
            ok = re.search(r'successful|Successful|removed', out)
            return None if ok else (out.strip().splitlines() or ['failed'])[-1]
        self.hw_do(f'{words[cmd]} {mac}…', fn, 'Done')

    def bt_scan(self):
        def fn():
            paired = {l.split(' ', 2)[1] for l in run('bluetoothctl', 'devices', 'Paired').splitlines()
                      if l.startswith('Device ')}
            subprocess.run(['bluetoothctl', '--timeout', '12', 'scan', 'on'],
                           capture_output=True, timeout=30)
            found = []
            for l in run('bluetoothctl', 'devices').splitlines():
                p = l.split(' ', 2)
                if len(p) == 3 and p[1] not in paired and not re.fullmatch(r'[0-9A-F-]{17}', p[2]):
                    found.append((p[1], p[2]))
            self.bt_found = found
            return (f'{len(found)} device(s) found. Put a device in pairing mode and scan '
                    'again if yours is missing.') if found else \
                'Nothing found. Put the device in pairing mode and scan again.'
        self.hw_do('Scanning for Bluetooth devices (12 s)… put your device in pairing mode', fn)

    def bt_pair(self, mac):
        def fn():
            ok, log = bt_session(mac)
            self.bt_found = [d for d in self.bt_found if d[0] != mac]
            if ok == 'connected':
                return 'Paired and connected'
            if ok == 'paired':
                if 'profile-unavailable' in log or 'NotAvailable' in log:
                    return ('Paired, but no audio connection: Bluetooth audio is not installed. '
                            'Run  sudo apt install libspa-0.2-bluetooth  then Connect.')
                return 'Paired; connecting failed: switch the device on and click Connect'
            last = [ln for ln in log.splitlines() if 'Failed' in ln or 'not available' in ln]
            return 'Pairing failed: ' + (last[-1].strip() if last else
                                         'no answer. Put the device in pairing mode and try again.')
        self.hw_do(f'Pairing with {mac}… (the device must be in pairing mode)', fn)

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
