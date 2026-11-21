"""app: Home: what you change often (sound + equaliser, webcam, printer, connections,
power, system info). The gear in the header opens all setup (the other tabs)."""
import json
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

from . import audio, eq, printers, sysinfo, webcam
from .base import run, spawn, sysread
from .power import HELPER, PROFILES, battery_text, tlp_settings
from .ui import Pages, heading, idle, note
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

CSS = b'''
.zcard { background: rgba(255,255,255,0.035); border-radius: 14px;
         border: 1px solid rgba(255,255,255,0.07); padding: 12px; }
.zcard-title { font-weight: bold; font-size: 11pt;
               text-shadow: -1px 0 rgba(255,42,74,0.55), 1px 0 rgba(25,230,255,0.55); }
.zbig { font-size: 20pt; font-weight: bold;
        text-shadow: -1.5px 0 rgba(255,42,74,0.6), 1.5px 0 rgba(25,230,255,0.6); }
.zpill { border-radius: 16px; padding: 3px 11px; background: rgba(255,255,255,0.05);
         border: 1px solid rgba(255,255,255,0.08); }
.zpill.on { background: rgba(25,230,255,0.16); border-color: rgba(25,230,255,0.6); }
.zlink { padding: 2px 6px; }
.zpreview { background: radial-gradient(circle at 40% 40%, #11151c, #05070a); border-radius: 12px; }
levelbar.zbar block.filled { background: linear-gradient(90deg, #ff2a4a, #19e6ff); border-radius: 3px; }
levelbar.zbar block.empty { background: rgba(255,255,255,0.08); border-radius: 3px; }
'''


def gst():
    """GStreamer with a GTK video sink, for the live webcam picture (optional)"""
    try:
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        Gst.init(None)
        return Gst if Gst.ElementFactory.find('gtksink') and Gst.ElementFactory.find('v4l2src') else None
    except (ValueError, ImportError):
        return None


def label(text, cls=None, x=0.0, wrap=False):
    lb = Gtk.Label(label=text, xalign=x, wrap=wrap)
    if cls:
        lb.get_style_context().add_class(cls)
    return lb


def hbox(*widgets, spacing=6):
    b = Gtk.Box(spacing=spacing)
    for w in widgets:
        b.add(w)
    return b


class Wrap(Gtk.Box):
    """buttons in rows of `per`: predictable, unlike a FlowBox inside a narrow card"""
    def __init__(self, per=3):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.per, self.row, self.n = per, None, 0

    def add(self, w):
        if self.n % self.per == 0:
            self.row = Gtk.Box(spacing=6)
            super().add(self.row)
        self.row.add(w)
        self.n += 1


def flow(per=3):
    return Wrap(per)


class HomePages:
    """Home and its own sub-pages (equaliser, webcam) - a mixin of the app window"""

    def home_widget(self):
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, 700)
        self.home = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True, hexpand=True)
        self.home.add_named(self.home_dash(), 'dash')
        self.home.add_named(self.home_eq(), 'eq')
        self.home.add_named(self.home_cam(), 'cam')
        self.home_seen = {}
        idle(self.home_refresh)
        self.timers.append(GLib.timeout_add_seconds(5, self.home_tick))
        return self.home

    def home_tick(self):
        # only while you look at it: not when another window is in front
        if self.is_active() and self.top.get_visible_child_name() == 'home' \
                and self.home.get_visible_child_name() == 'dash':
            self.home_refresh()
        return True

    # -- small widgets
    def pill(self, text, on=False, cb=None):
        b = Gtk.Button(label=text)
        b.get_style_context().add_class('zpill')
        if on:
            b.get_style_context().add_class('on')
        if cb:
            b.connect('clicked', lambda _b: cb())
        return b

    def card(self, title, icon, body, more=None):
        c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        c.get_style_context().add_class('zcard')
        h = Gtk.Box(spacing=8)
        h.add(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.LARGE_TOOLBAR))
        h.add(label(title, 'zcard-title'))
        if more:
            b = Gtk.Button(label=more[0], relief=Gtk.ReliefStyle.NONE)
            b.get_style_context().add_class('zlink')
            b.connect('clicked', lambda _b: more[1]())
            h.pack_end(b, False, False, 0)
        c.add(h)
        c.add(body)
        return c

    def fill(self, box, widgets):
        for w in box.get_children():
            w.destroy()
        for w in widgets:
            box.add(w)
        box.show_all()

    def bg(self, fn, then=None):
        def work():
            try:
                res = fn()
            except Exception as e:      # noqa: BLE001  then() still runs: nothing stays stuck
                print('zorro: background step failed:', e)
                res = None
            if then:
                idle(lambda: then(res) and False)
        threading.Thread(target=work, daemon=True).start()

    # -- the dashboard
    def home_dash(self):
        sw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        g = Gtk.Grid(column_spacing=12, row_spacing=12, margin=14, column_homogeneous=True,
                     valign=Gtk.Align.START)
        self.h_sound = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.h_cam = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.h_print = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.h_conn = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.h_power = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.h_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        cards = [self.card('Sound', 'audio-volume-high-symbolic', self.h_sound,
                           ('Equaliser…', lambda: self.home.set_visible_child_name('eq'))),
                 self.card('Webcam', 'camera-web-symbolic', self.h_cam,
                           ('Settings…', self.cam_open)),
                 self.card('Printer', 'printer-symbolic', self.h_print,
                           ('Printers…', lambda: self.show_page('hw:2'))),
                 self.card('Connections', 'network-wireless-symbolic', self.h_conn,
                           ('Network…', lambda: self.show_page('wifi:0'))),
                 self.card('Battery & power', 'battery-good-symbolic', self.h_power,
                           ('Power…', lambda: self.show_page('power:0'))),
                 self.card('System info', 'computer-symbolic', self.h_info,
                           ('Details…', lambda: self.show_page('sys:0')))]
        for i, c in enumerate(cards):
            g.attach(c, i % 3, i // 3, 1, 1)
        self.cam_card_preview()
        sw.add(g)
        return sw

    def home_refresh(self):
        if getattr(self, 'home_busy', False):
            self.home_again = True      # one more round when this one is done (its facts are older)
            return False                # the last round is still running (netbird can take 8 s)
        self.home_busy = True

        def part(d, fn, *keys):
            """one card's facts; a failing command leaves that card's defaults, not all six"""
            try:
                fn(d)
            except Exception as e:      # noqa: BLE001
                print('zorro: home refresh:', keys, e, file=sys.stderr)

        def sound(d):
            d.update(sinks=audio.devices('sinks'), eq=eq.settings(), eq_running=bool(eq.running()))

        slow = self.__dict__.setdefault('home_slow', {})     # name: (when, facts)

        def every(name, secs, fn, d):
            """facts that are slow to read and seldom change: at most every `secs` seconds"""
            at, facts = slow.get(name, (0, None))
            if facts is None or time.monotonic() - at > secs:
                facts = {}
                fn(facts)
                slow[name] = (time.monotonic(), facts)
            d.update(facts)

        def printer(d):
            def read(f):
                f['printers'] = printers.installed() if printers.available() else None   # 0.3 s
                f['queue'] = len([ln for ln in run('lpstat', '-o').splitlines() if ln.strip()])
            every('printer', 30, read, d)

        def conn(d):
            wifi = re.search(r'^yes:(\d+):(.*)$', run('nmcli', '-t', '-f', 'ACTIVE,SIGNAL,SSID', 'dev', 'wifi',
                                                    'list', '--rescan', 'no'), re.M)   # no Wi-Fi scan
            d['wifi'] = (wifi.group(2), wifi.group(1)) if wifi else None
            d['wifi_on'] = 'enabled' in run('nmcli', 'radio', 'wifi')
            devs = [ln.split(':') for ln in run('nmcli', '-t', '-f', 'DEVICE,TYPE,STATE', 'dev').splitlines()
                    if ln.count(':') >= 2]
            up = ('connected', 'connected (externally)')
            d['cable'] = any(x[1] == 'ethernet' and x[2] in up for x in devs) \
                or bool(re.search(r'default .*dev en', run('ip', 'route')))
            d['mobile'] = any(x[1] == 'gsm' and x[2] in up for x in devs)
            d['bt_on'] = 'Powered: yes' in run('bluetoothctl', 'show')
            d['bt_dev'] = [ln.split(' ', 2)[2] for ln in run('bluetoothctl', 'devices', 'Connected').splitlines()
                           if ln.startswith('Device ')]
            def netbird(f):
                try:
                    nb = json.loads(run('netbird', 'status', '--json', timeout=8) or '{}')
                except ValueError:
                    nb = {}
                f['nb'] = (nb.get('management', {}).get('connected'), nb.get('peers', {}).get('connected', 0),
                           nb.get('peers', {}).get('total', 0)) if nb else None
            every('netbird', 30, netbird, d)
            soft = [sysread(r / 'soft') == '1' for r in Path('/sys/class/rfkill').glob('rfkill*')]
            from .keys import airplane_on
            d['airplane'] = airplane_on() if soft else False

        def power(d):
            d['bat'] = sysread('/sys/class/power_supply/BAT0/capacity')
            d['bat_text'] = battery_text()
            d['profile'] = sysread('/sys/firmware/acpi/platform_profile')
            d['ac'] = sysread('/sys/class/power_supply/AC/online', '1') == '1'

        def info(d):
            d['info'] = sysinfo.collect()

        def gather():
            d = {}
            for fn in (sound, printer, conn, power, info):
                part(d, fn, fn.__name__)
            return d

        def show(d):
            self.home_busy = False
            self.home_show(d)
            if getattr(self, 'home_again', False):
                self.home_again = False
                self.home_refresh()
        self.bg(gather, show)
        return False

    def home_show(self, d):
        for show in (self.show_sound, self.show_printer, self.show_conn, self.show_power, self.show_info):
            try:
                show(d)
            except KeyError:            # its facts could not be read this round: keep the card
                pass
        return True

    # sound
    def real_sinks(self, d):
        return [s for s in d['sinks'] if s['name'] not in (eq.NODE, audio.TOGETHER)]

    def show_sound(self, d):
        e = d['eq']
        on = e['on'] and d['eq_running']
        cur = e['target'] if on else next((s['name'] for s in d['sinks'] if s['default']), '')
        sig = ('sound', tuple(s['name'] for s in self.real_sinks(d)), cur, on)   # not the volume: no rebuild under the mouse
        if self.home_seen.get('sound') == sig:
            self.vol_sync('sinks', d['sinks'])      # the volume itself: move the slider
            return
        self.home_seen['sound'] = sig
        outs = flow(1)
        for s in self.real_sinks(d):
            outs.add(self.pill(('● ' if s['name'] == cur else '') + s['desc'][:28], s['name'] == cur,
                               lambda n=s['name']: self.sound_use(n)))
        vol_dev = next((s for s in d['sinks'] if s['name'] == cur), None)    # also "Together"
        vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 150, 1)
        vol.set_hexpand(True)
        vol.set_value(vol_dev['volume'] if vol_dev else 0)
        vol.connect('format-value', lambda w, v: f'{v:.0f}%')
        vol.connect('value-changed', lambda w: vol_dev and self.au_volume('sinks', vol_dev['name'], w.get_value()))
        if vol_dev:
            self.vol_follow(vol, 'sinks', vol_dev['name'])
        eqrow = flow()
        sw = Gtk.Switch(active=on, valign=Gtk.Align.CENTER)
        sw.connect('notify::active', lambda w, _p: self.eq_turn(w.get_active()))
        eqrow.add(hbox(label('Equaliser'), sw))
        g = eq.gains_for(cur)
        for name, gains in eq.PRESETS.items():
            eqrow.add(self.pill(name, on and g == [float(x) for x in gains],
                                lambda gains=gains: self.eq_preset(gains)))
        self.fill(self.h_sound, [outs, hbox(label('Volume'), vol, spacing=10), eqrow])

    def sound_use(self, name):
        if eq.settings()['on'] and eq.running():
            self.bg(lambda: eq.retarget(name), lambda _r: self.home_refresh())
        else:
            self.bg(lambda: audio.use('sinks', name), lambda _r: self.home_refresh())

    def eq_turn(self, on):
        self.bg(lambda: eq.turn(on), lambda _r: (self.home_refresh(), self.eq_page_fill()))

    def eq_preset(self, gains):
        target = eq.settings()['target'] or run('pactl', 'get-default-sink').strip()
        if target == eq.NODE:
            target = eq.settings()['target']

        def work():
            eq.set_gains(target, gains)
            if not (eq.settings()['on'] and eq.running()):
                eq.turn(True, target)
        self.bg(work, lambda _r: (self.home_refresh(), self.eq_page_fill()))

    # printer
    def show_printer(self, d):
        ps = d['printers']
        sig = ('print', json.dumps(ps, sort_keys=True), d['queue'])
        if self.home_seen.get('print') == sig:
            return
        self.home_seen['print'] = sig
        if ps is None:
            self.fill(self.h_print, [label('Printing is not installed', 'dim-label')])
            return
        if not ps:
            self.fill(self.h_print, [label('No printer yet', 'dim-label'),
                                     hbox(self.pill('Add printer', cb=lambda: self.show_page('hw:2')))])
            return
        p = next((x for x in ps if x['default']), ps[0])
        state = {'idle': 'ready', 'printing': 'printing', 'disabled': 'paused'}.get(p['state'], p['state'])
        q = d['queue']
        self.fill(self.h_print, [
            label(f'{p["name"].replace("_", " ")}  ·  {state}' + ('  ·  default' if p['default'] else '')),
            label('Nothing waiting to print' if not q else f'{q} waiting to print', 'dim-label'),
            hbox(self.pill('Test page', cb=lambda n=p['name']: self.bg(lambda: printers.test_page(n))),
                 self.pill(f'Queue ({q})', cb=lambda: spawn(['xdg-open', 'http://localhost:631/jobs/'])),
                 self.pill('Add printer', cb=lambda: self.show_page('hw:2')))])

    # connections
    def show_conn(self, d):
        sig = ('conn', d['wifi'] and d['wifi'][0], d['wifi_on'], d['cable'], d['bt_on'], tuple(d['bt_dev']),
               d['nb'] and d['nb'][0], d['airplane'], d.get('mobile'))
        wifi = f'Wi-Fi  {d["wifi"][0]} {d["wifi"][1]}%' if d['wifi'] else ('Wi-Fi  on' if d['wifi_on'] else 'Wi-Fi  off')
        if self.home_seen.get('conn') == sig:            # only numbers changed: just the text
            if getattr(self, 'wifi_pill', None):
                self.wifi_pill.set_label(wifi)
            if getattr(self, 'nb_pill', None) and d['nb'] and d['nb'][0]:
                self.nb_pill.set_label(f'NetBird  {d["nb"][1]}/{d["nb"][2]}')
            return
        self.home_seen['conn'] = sig
        f = flow(2)
        self.wifi_pill = self.pill(wifi, d['wifi_on'], lambda: self.conn_do(['nmcli', 'radio', 'wifi',
                                                                  'off' if d['wifi_on'] else 'on']))
        f.add(self.wifi_pill)
        f.add(self.pill('Cable' + ('  connected' if d['cable'] else ''), d['cable'],
                        lambda: self.show_page('eth:0')))
        bt = 'Bluetooth  ' + (', '.join(x[:14] for x in d['bt_dev']) or ('on' if d['bt_on'] else 'off'))
        f.add(self.pill(bt, d['bt_on'], lambda: self.conn_do(['bluetoothctl', 'power',
                                                              'off' if d['bt_on'] else 'on'])))
        f.add(self.pill('Mobile' + ('  connected' if d['mobile'] else ''), d['mobile'],
                        lambda: self.show_page('lte:0')))
        if d['nb']:
            up, n, total = d['nb']
            self.nb_pill = self.pill(f'NetBird  {n}/{total}' if up else 'NetBird  off', bool(up),
                                     lambda: self.conn_do(['netbird', 'down' if up else 'up']))
            f.add(self.nb_pill)
        f.add(self.pill('Airplane', d['airplane'], self.airplane))
        self.fill(self.h_conn, [f])

    def home_fresh(self, *names):
        """after an action: read these slow facts again now (else they are kept 30 s)"""
        for n in names:
            self.__dict__.get('home_slow', {}).pop(n, None)
        GLib.timeout_add(800, lambda: self.home_refresh() and False)

    def conn_do(self, cmd):
        self.bg(lambda: run(*cmd, timeout=30), lambda _r: self.home_fresh('netbird'))

    def airplane(self):
        from .keys import key_airplane
        self.bg(key_airplane, lambda _r: self.home_fresh('netbird'))

    # power
    def show_power(self, d):
        sig = ('power', d['bat'], d['bat_text'], d['profile'], d['ac'])
        if self.home_seen.get('power') == sig:
            return
        self.home_seen['power'] = sig
        rest = d['bat_text'].split(' · ', 1)[-1] if ' · ' in d['bat_text'] else d['bat_text']
        top = hbox(label(f'{d["bat"]}%' if d['bat'] else '?', 'zbig'),
                   label(rest.replace(' · ', '\n'), 'dim-label', wrap=True), spacing=12)
        f = flow()
        for key, name in PROFILES.items():
            f.add(self.pill(name.replace('Battery saver', 'Saver'), d['profile'] == key,
                            lambda k=key: self.set_profile(k, d['ac'])))
        self.fill(self.h_power, [top, f, label('On the charger' if d['ac'] else 'On battery', 'dim-label')])

    def set_profile(self, key, ac):
        """the mode for the power source in use now; the other source and the charge limits stay"""
        if not os.path.exists(HELPER) or not shutil.which('pkexec'):
            self.show_page('power:1')
            return
        t = tlp_settings()
        mode_ac = key if ac else t.get('PLATFORM_PROFILE_ON_AC', 'performance')
        mode_bat = t.get('PLATFORM_PROFILE_ON_BAT', 'low-power') if ac else key
        lo, hi = t.get('START_CHARGE_THRESH_BAT0', '75'), t.get('STOP_CHARGE_THRESH_BAT0', '80')
        self.bg(lambda: run('pkexec', HELPER, 'power', mode_ac, mode_bat, lo, hi, timeout=60),
                lambda _r: self.home_refresh())

    # system info
    def show_info(self, d):
        i = d['info']
        sig = ('info', i['mem_used'] // 2 ** 27, tuple(m['used'] // 2 ** 30 for m in i['mounts']), i['uptime'])
        if self.home_seen.get('info') == sig:
            return
        self.home_seen['info'] = sig
        w = [label(f'{i["cpu"].replace(" with Radeon Graphics", "")} · {i["cores"]} cores / {i["threads"]} threads'),
             label(f'{short_gpu(i["gpu"])} · {i["model"].replace("LENOVO ", "")}', 'dim-label')]
        w.append(self.bar('Memory', i['mem_used'], i['mem_total']))
        for m in i['mounts'][:2]:
            w.append(self.bar('Disk' if m['path'] == '/' else m['path'], m['used'], m['total']))
        w.append(label(f'{i["os"].replace("GNU/Linux ", "")} · kernel {i["kernel"].split("+")[0]} · up {i["uptime"]}',
                       'dim-label'))
        self.fill(self.h_info, w)

    def bar(self, name, used, total):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        b.add(hbox(label(name), label(f'{sysinfo.gb(used)} of {sysinfo.gb(total)}', 'dim-label')))
        lb = Gtk.LevelBar(min_value=0, max_value=1, value=used / total if total else 0)
        lb.get_style_context().add_class('zbar')
        b.add(lb)
        return b

    # -- the equaliser page
    def home_eq(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=16)
        self.eq_top = Gtk.Box(spacing=8)
        box.add(self.eq_top)
        self.eq_bands = Gtk.Box(spacing=18, halign=Gtk.Align.CENTER)
        box.add(self.eq_bands)
        self.eq_bottom = Gtk.Box(spacing=8)
        box.add(self.eq_bottom)
        box.add(note('Ten bands for everything you play, remembered per output: the Douk can '
                     'sound different from the speaker. Built into PipeWire; nothing runs while it is off.'))
        self.eq_page_fill()
        return box

    def eq_page_fill(self):
        s = eq.settings()
        target = s['target'] or run('pactl', 'get-default-sink').strip()
        if target == eq.NODE:
            target = s['target']
        self.eq_target = target
        gains = eq.gains_for(target)
        top = []
        sw = Gtk.Switch(active=s['on'] and bool(eq.running()), valign=Gtk.Align.CENTER)
        sw.connect('notify::active', lambda w, _p: self.eq_turn(w.get_active()))
        top.append(hbox(sw, label('Equaliser on'), spacing=8))
        for name, g in eq.PRESETS.items():
            top.append(self.pill(name, [float(x) for x in g] == gains, lambda g=g: self.eq_preset(g)))
        self.fill(self.eq_top, top)
        bands = []
        self.eq_scales = []
        for lab, g in zip(eq.LABELS, gains):
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            sc = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, -12, 12, 0.5)
            sc.set_inverted(True)
            sc.set_value(g)
            sc.set_size_request(-1, 280)
            sc.set_value_pos(Gtk.PositionType.TOP)
            sc.add_mark(0, Gtk.PositionType.RIGHT, None)
            sc.connect('format-value', lambda w, x: f'{x:+.0f}')
            sc.connect('value-changed', lambda w: self.eq_changed())
            self.eq_scales.append(sc)
            col.add(sc)
            col.add(label(lab, 'dim-label', x=0.5))
            bands.append(col)
        self.fill(self.eq_bands, bands)
        outs = [label('Applies to:')]
        for sk in audio.devices('sinks'):
            if sk['name'] in (eq.NODE, audio.TOGETHER):
                continue
            outs.append(self.pill(sk['desc'][:28], sk['name'] == target,
                                  lambda n=sk['name']: self.bg(lambda: eq.retarget(n),
                                                               lambda _r: self.eq_page_fill())))
        self.fill(self.eq_bottom, outs)

    def eq_changed(self):
        gains = [s.get_value() for s in self.eq_scales]
        target = self.eq_target
        ui.later('eq-save', lambda: ui.in_bg(eq.set_gains, target, gains, finish=True), 150)

    # -- the webcam page
    def cam_card_preview(self):
        area = Gtk.Box()
        area.get_style_context().add_class('zpreview')
        area.set_size_request(-1, 90)
        self.cam_card_area = area
        b = Gtk.Button(label='Camera off · click to preview', relief=Gtk.ReliefStyle.NONE, hexpand=True)
        b.connect('clicked', lambda _b: self.cam_open())
        area.add(b)
        bright = next((c for c in webcam.controls() if c['name'] == 'brightness'), None) \
            if webcam.available() else None
        parts = [area]
        if bright:
            sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, bright['min'], bright['max'], bright['step'])
            sc.set_value(bright['value'])
            sc.set_hexpand(True)
            sc.connect('value-changed', lambda w: webcam.set_soon('brightness', w.get_value()))
            parts.append(hbox(label('Brightness'), sc, spacing=10))
        self.fill(self.h_cam, parts)

    def home_cam(self):
        box = Gtk.Box(spacing=16, margin=16)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.cam_view = Gtk.Box()
        self.cam_view.get_style_context().add_class('zpreview')
        self.cam_view.set_size_request(320, 240)
        left.add(self.cam_view)
        left.add(hbox(self.pill('Reset', cb=lambda: (webcam.reset(), self.cam_fill())),
                      self.pill('Keep these settings', cb=lambda: (webcam.save(), self.cam_msg.set_text(
                          'Kept: applied again after a restart or standby')))))
        self.cam_msg = note()
        left.add(self.cam_msg)
        box.add(left)
        self.cam_ctrls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        box.add(self.cam_ctrls)
        self.cam_pipe = None
        return box

    def cam_open(self):
        self.home.set_visible_child_name('cam')
        self.cam_fill()
        self.cam_start()

    def cam_start(self):
        Gst = gst()
        for c in self.cam_view.get_children():
            c.destroy()
        if not Gst:
            b = Gtk.Button(label='Live picture: open in VLC', hexpand=True, relief=Gtk.ReliefStyle.NONE)
            b.connect('clicked', lambda _b: spawn(['vlc', f'v4l2://{webcam.DEV}']))
            self.cam_view.add(b)
            self.cam_view.show_all()
            return
        try:
            self.cam_pipe = Gst.parse_launch(f'v4l2src device={webcam.DEV} ! videoconvert ! gtksink name=sink')
            widget = self.cam_pipe.get_by_name('sink').props.widget
            widget.set_hexpand(True)
            self.cam_view.add(widget)
            self.cam_view.show_all()
            self.cam_pipe.set_state(Gst.State.PLAYING)
        except GLib.Error as e:
            self.cam_msg.set_text(f'No picture: {e.message}')

    def cam_stop(self):
        if self.cam_pipe:
            Gst = gst()
            self.cam_pipe.set_state(Gst.State.NULL)
            self.cam_pipe = None
        for c in self.cam_view.get_children():
            c.destroy()

    def cam_fill(self):
        rows = []
        for c in webcam.controls() if webcam.available() else []:
            if c['type'] == 'int':
                sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, c['min'], c['max'], max(1, c['step']))
                sc.set_value(c['value'])
                sc.set_hexpand(True)
                sc.set_sensitive(not c['inactive'])
                sc.connect('value-changed', lambda w, n=c['name']: webcam.set_soon(n, w.get_value()))
                w = sc
            elif c['type'] == 'bool':
                w = Gtk.Switch(active=bool(c['value']), halign=Gtk.Align.START)
                w.connect('notify::active', lambda s, _p, n=c['name']: (
                    webcam.set_control(n, s.get_active()), GLib.timeout_add(200, lambda: self.cam_fill() and False)))
            elif c['type'] == 'menu':
                w = Gtk.Box(spacing=6)
                for val, text in c['menu'].items():
                    w.add(self.pill(text.replace(' Mode', '').replace('Aperture Priority', 'Auto'),
                                    val == c['value'],
                                    lambda n=c['name'], v=val: (webcam.set_control(n, v), self.cam_fill())))
            else:
                continue
            lab = label(c['label'])
            lab.set_size_request(150, -1)
            rows.append(hbox(lab, w, spacing=10))
        if not rows:
            rows.append(note('No webcam controls (needs v4l-utils)'))
        self.fill(self.cam_ctrls, rows)

    # -- System info (a setup page under Hardware)
    def sysinfo_page(self):
        box = Pages()
        box.add(heading('This laptop', 'System info'))
        self.sys_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add(self.sys_box)
        b = Gtk.Button(label='Check again', halign=Gtk.Align.START, margin_top=8)
        b.connect('clicked', lambda _b: self.sys_fill())
        box.add(b)
        idle(self.sys_fill)
        return box

    def sys_fill(self):
        def show(i):
            g = Gtk.Grid(column_spacing=16, row_spacing=6)
            rows = [('Model', f'{i["model"]}  ({i["type"]})'), ('BIOS', f'{i["bios"]}  {i["bios_date"]}'),
                    ('Processor', f'{i["cpu"]} · {i["cores"]} cores / {i["threads"]} threads'),
                    ('Graphics', f'{short_gpu(i["gpu"])} · {i["gpu_driver"]}' + (f' · {i["vram"]} video memory' if i['vram'] else '')),
                    ('Screen', i['screen']),
                    ('Memory', f'{sysinfo.gb(i["mem_used"])} used of {sysinfo.gb(i["mem_total"])}'
                               f' · swap {sysinfo.gb(i["swap_used"])} of {sysinfo.gb(i["swap_total"])}')]
            for d in i['disks']:
                rows.append(('Disk', f'{d["model"] or d["name"]} · {sysinfo.gb(d["size"])} · {d["bus"].upper()}'))
            for m in i['mounts']:
                rows.append(('In use', f'{m["path"]}: {sysinfo.gb(m["used"])} of {sysinfo.gb(m["total"])}'))
            rows += [('System', f'{i["os"]} · kernel {i["kernel"]}'), ('Up', i['uptime'])]
            if i['temps']:
                rows.append(('Temperature', ' · '.join(f'{k} {v:.0f}°C' for k, v in i['temps'].items())))
            for r, (k, v) in enumerate(rows):
                g.attach(label(k, 'dim-label'), 0, r, 1, 1)
                lb = label(v, wrap=True)
                lb.set_selectable(True)
                g.attach(lb, 1, r, 1, 1)
            self.fill(self.sys_box, [g])
            return True
        self.bg(sysinfo.collect, show)
        return False


def short_gpu(name):
    m = re.search(r'\[(Radeon[^\]]*)\]', name)
    if m:
        code = re.search(r'\] (\w+) \[', name)
        return f'{m.group(1).split("/")[0].strip()}' + (f' ({code.group(1)})' if code else '')
    return name.replace('Advanced Micro Devices, Inc. ', '').replace('Corporation ', '')
