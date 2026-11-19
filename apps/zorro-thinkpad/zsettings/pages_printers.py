"""app: Hardware → Printers (zsettings/printers.py does the work)"""
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
from .ui import KEY_TABLE, MARKS, Pages, device_list, device_row, heading, idle, later, mark, note, radios
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk



class PrinterPages:
    """the printers part of the Hardware tab (a mixin of the app window)"""

    def printers_box(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=6)
        self.pr_list = device_list()
        outer.add(self.pr_list)
        outer.add(heading('On the network'))
        self.pr_found = device_list()
        outer.add(self.pr_found)
        row = Gtk.Box(spacing=8, margin_top=4)
        self.pr_search_btn = Gtk.Button(label='Search')
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
        return device_row(title, detail, acts, icon='printer-symbolic',
                          state='ok' if ok else 'warn')

    def pr_bg(self, busy, fn, then):
        """run fn() in a thread with a message; then(result) on the main loop"""
        self.hw_msg.set_text(busy)

        def work():
            try:
                res = fn()
            except Exception as e:          # noqa: BLE001 - show it, keep the app alive
                res = e
            idle(lambda: then(res) and False)
            idle(lambda: self.__dict__.get('home_slow', {}).pop('printer', None) and False)   # Home too
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
                acts.append(('Forget', lambda n=q['name']: self.pr_bg(
                    f'Forgetting {n}…', lambda: printers.remove(n),
                    lambda _r: (self.hw_msg.set_text(f'{n} forgotten'), self.pr_refresh()))))
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
                acts = [('Add', lambda p=p: self.pr_add(p), True)] if model else []
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
