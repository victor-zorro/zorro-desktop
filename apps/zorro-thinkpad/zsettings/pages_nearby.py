"""Connect → Transfer → Nearby: the Zorro devices on this network and among the NetBird peers
(zorro-transfer nearby), each with "Get its setup"; and how this device shows up for them
(the beacon, zorro-beacon.service)."""
import json
import socket
import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib  # noqa: E402

from .base import spawn
from .pages_transfer import ZT, alive, state
from .ui import Pages, device_list, device_row, heading, idle, in_bg, note, scroll_list

ROUTE = {'cable': 'cable', 'wifi': 'Wi-Fi', 'netbird': 'NetBird', 'mobile': 'mobile data',
         'local': 'this device', 'local network': 'local network'}


def nearby():
    """[{name, host, via, sending}] from zorro-transfer nearby, [] when it cannot say"""
    try:
        out = subprocess.run([ZT, 'nearby', '--json', '--wait', '1.5'], capture_output=True,
                             text=True, timeout=20).stdout
        found = json.loads(out or '[]')
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    return [f for f in found if isinstance(f, dict) and isinstance(f.get('name'), str)
            and isinstance(f.get('host'), str)] if isinstance(found, list) else []


def beacon_line():
    """how this device shows up for the others"""
    b = state('beacon.json')
    name = b.get('name') or socket.gethostname()
    if alive(b.get('pid')):
        return f'Others see this device as "{name}".'
    return f'Hidden: the beacon is off. Run apps/zorro-transfer/install.sh to show "{name}".'


class NearbyPages:
    def nearby_page(self):
        box = Pages()
        box.add(heading('Devices nearby', 'Nearby'))
        self.nr_list = device_list()
        box.add(scroll_list(self.nr_list, height=240))
        self.nr_me = note(beacon_line())
        self.nr_me.set_margin_top(8)
        box.add(self.nr_me)
        self.nr_line = note('' if ZT else 'Transfer is missing: run ~/zorro-desktop/install.sh once.')
        box.add(self.nr_line)
        self.nr_seen, self.nr_busy = None, False
        if ZT:
            idle(lambda: self.nr_tick() and False)
            self.timers.append(GLib.timeout_add_seconds(5, self.nr_tick))
        return box

    def nr_tick(self):
        """search again while the Transfer menu is on screen (in a thread)"""
        if getattr(self, 'dead', False) or self.nr_busy or not self.tab_on('transfer'):
            return True
        self.nr_busy = True
        if self.nr_seen is None:
            self.nr_line.set_text('Searching your network and NetBird…')

        def work():
            found = nearby()
            idle(lambda: self.nr_show(found) and False)
        in_bg(work)
        return True

    def nr_show(self, found):
        self.nr_busy = False
        if getattr(self, 'dead', False):
            return
        self.nr_me.set_text(beacon_line())
        self.nr_line.set_text('' if found else 'No other Zorro device found yet.')
        if found == self.nr_seen:
            return
        self.nr_seen = found
        for c in self.nr_list.get_children():
            self.nr_list.remove(c)
        for f in found:
            how = ROUTE.get(f.get('via'), f.get('via') or '')
            ready = 'ready to send' if f.get('sending') else 'not sending yet'
            act = ('Get its setup', lambda h=f['host']: spawn([ZT, '--get', '--from', h]))
            self.nr_list.add(device_row(f['name'], f"{how} · {f['host']} · {ready}", [act],
                                        icon='computer-symbolic',
                                        state='on' if f.get('sending') else 'off'))
        self.nr_list.show_all()
