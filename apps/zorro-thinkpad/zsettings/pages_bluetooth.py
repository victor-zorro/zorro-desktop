"""app: Hardware → Bluetooth: power, scan, pair, connect (bluetoothctl)"""
# flake8: noqa: F401 - the same imports as pages_thinkpad
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
    fd = p.stdout.fileno()

    def send(cmd):
        p.stdin.write(cmd + '\n')
        p.stdin.flush()

    buf, ready = [''], []               # read by hand: select() cannot see Python's own buffer

    def next_line(wait):
        """the next full line of output; '' when none came within `wait`; None at the end"""
        if not ready and select.select([fd], [], [], wait)[0]:
            data = os.read(fd, 4096)
            if not data:
                return None
            *full, buf[0] = (buf[0] + data.decode(errors='replace')).split('\n')
            ready.extend(full)
        return ready.pop(0) + '\n' if ready else ''

    def wait_for(words, secs):
        end = time.time() + secs
        while time.time() < end:
            line = next_line(0.5)
            if line is None:
                break
            if line:
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


class BluetoothPages:
    """the Bluetooth actions of the Hardware tab (a mixin of the app window)"""

    def bt_power(self, on):
        self.hw_do('…', lambda: run('bluetoothctl', 'power', 'on' if on else 'off') and None)

    def bt_music(self, mac, on):
        """tick: this sound device is a one-tap output in the Dialer's Music part"""
        now = [m for m in (load_conf().get('music_outputs') or []) if m != mac]
        update_conf(None, music_outputs=now + [mac] if on else now)
        self.hw_msg.set_text('Shows in the Dialer under Music' if on else 'Taken out of Music')

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
            return (f'{len(found)} device(s) found. Put a device in pairing mode and search '
                    'again if yours is missing.') if found else \
                'Nothing found. Put the device in pairing mode and search again.'
        self.hw_do('Searching for Bluetooth devices (12 s)… put your device in pairing mode', fn)

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
