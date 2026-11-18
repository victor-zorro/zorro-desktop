"""app: Network tab: Wi-Fi and Ethernet (NetworkManager through libnm), NetBird (its CLI);
the Mobile part is pages_mobile.py"""
import json
import re
import threading

from .base import run, spawn
from .ui import Pages, heading, idle, note
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('NM', '1.0')
from gi.repository import GLib, Gtk, NM  # noqa: E402


def ssid_of(ap):
    b = ap.get_ssid()
    return b.get_data().decode('utf-8', 'replace') if b else ''


def secured(ap):
    return bool(ap.get_flags() & NM.__dict__['80211ApFlags'].PRIVACY or ap.get_wpa_flags()
                or ap.get_rsn_flags())


def sae_only(ap):
    """WPA3-only networks want SAE instead of a WPA2 pre-shared key"""
    f = NM.__dict__['80211ApSecurityFlags']
    rsn = ap.get_rsn_flags()
    return bool(rsn & f.KEY_MGMT_SAE) and not rsn & f.KEY_MGMT_PSK


def bars(strength):
    return '▂▄▆█'[:max(1, min(4, (strength + 24) // 25))]


def ip4(dev):
    cfg = dev.get_ip4_config()
    addrs = cfg.get_addresses() if cfg else []
    return addrs[0].get_address() if addrs else ''


def route_metric(iface):
    m = re.search(rf'default .*dev {re.escape(iface)}\b.*metric (\d+)', run('ip', 'route'))
    return int(m.group(1)) if m else None


class Notes:
    """one message shown in the footer of every Network sub-page"""
    def __init__(self, labels):
        self.labels = labels

    def set_text(self, text):
        for lb in self.labels:
            lb.set_text(text)


class NetworkPages:
    """Network tab: Wi-Fi, Ethernet, NetBird (+ Mobile from MobilePages); a mixin"""

    def net_client(self):
        if not getattr(self, 'nm', None):
            try:
                self.nm = NM.Client.new(None)
            except GLib.Error:
                self.nm = None
        return self.nm

    def net_rows(self, box, rows):
        """replace a list box's rows: [(title, detail, [(label, cb)], mark)]"""
        for c in box.get_children():
            c.destroy()
        for title, detail, acts, mark in rows:
            row = Gtk.Box(spacing=12)
            txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            head = Gtk.Label(xalign=0)
            head.set_markup(f'{mark}  <b>{GLib.markup_escape_text(title)}</b>' if mark else
                            f'<b>{GLib.markup_escape_text(title)}</b>')
            txt.add(head)
            if detail:
                d = note(detail)
                d.set_selectable(True)
                d.set_can_focus(False)
                txt.add(d)
            row.add(txt)
            for label, cb in acts:
                b = Gtk.Button(label=label, valign=Gtk.Align.CENTER)
                b.connect('clicked', lambda _b, cb=cb: cb())
                row.add(b)
            box.add(row)
        box.show_all()

    # -- Wi-Fi
    def wifi_page(self, box):
        box.add(heading('Wi-Fi', 'Wi-Fi'))
        line = Gtk.Box(spacing=12)
        line.add(Gtk.Label(label='Wi-Fi'))
        self.wifi_switch = Gtk.Switch(halign=Gtk.Align.START)
        self.wifi_switch_id = self.wifi_switch.connect('notify::active', self.wifi_toggle)
        line.add(self.wifi_switch)
        scan = Gtk.Button(label='Scan')
        scan.connect('clicked', lambda b: self.wifi_scan())
        line.add(scan)
        adv = Gtk.Button(label='Advanced…')
        adv.connect('clicked', lambda b: spawn(['nm-connection-editor']))
        line.add(adv)
        box.add(line)
        self.wifi_now = note()
        box.add(self.wifi_now)
        self.wifi_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=6)
        box.add(self.wifi_list)

    def wifi_dev(self):
        c = self.net_client()
        return next((d for d in c.get_devices() if isinstance(d, NM.DeviceWifi)), None) if c else None

    def saved_wifi(self):
        out = {}
        for con in self.net_client().get_connections():
            s = con.get_setting_wireless()
            if s and s.get_ssid():
                out[s.get_ssid().get_data().decode('utf-8', 'replace')] = con
        return out

    def wifi_refresh(self):
        c, dev = self.net_client(), self.wifi_dev()
        if not c or not dev:
            self.wifi_now.set_text('No Wi-Fi adapter (or NetworkManager is not running)')
            return
        on = c.wireless_get_enabled()
        self.wifi_switch.handler_block(self.wifi_switch_id)
        self.wifi_switch.set_active(on)
        self.wifi_switch.handler_unblock(self.wifi_switch_id)
        act = dev.get_active_access_point()
        cur = ssid_of(act) if act else ''
        if cur:
            self.wifi_now.set_text(f'Connected to {cur} · signal {act.get_strength()}% · '
                                   f'{ip4(dev) or "no address yet"}')
        else:
            self.wifi_now.set_text('Not connected' if on else 'Wi-Fi is off')
        best = {}
        for ap in dev.get_access_points():
            s = ssid_of(ap)
            if s and (s not in best or ap.get_strength() > best[s].get_strength()):
                best[s] = ap
        saved = self.saved_wifi()
        rows = []
        for s, ap in sorted(best.items(), key=lambda kv: (kv[0] != cur, -kv[1].get_strength()))[:14]:
            lock = '🔒 ' if secured(ap) else ''
            detail = f'{bars(ap.get_strength())} {ap.get_strength()}%  {lock}' + \
                ('saved' if s in saved else ('open network' if not lock else ''))
            acts = []
            if s == cur:
                acts.append(('Disconnect', lambda: dev.disconnect_async(None, self.net_done, 'Disconnected')))
            else:
                acts.append(('Connect', lambda ap=ap, s=s: self.wifi_connect(ap, s)))
            if s in saved:
                acts.append(('Forget', lambda con=saved[s], s=s: con.delete_async(
                    None, self.net_done, f'{s} forgotten')))
            rows.append((s, detail, acts, '<span foreground="#5fd068">●</span>' if s == cur else ''))
        if not rows and on:
            rows.append(('No networks found', 'Click Scan', [], ''))
        self.net_rows(self.wifi_list, rows)

    def net_done(self, obj, res, text):
        """finish an async libnm call and say how it went"""
        try:
            for fin in ('disconnect_finish', 'delete_finish', 'activate_connection_finish',
                        'add_and_activate_connection_finish', 'request_scan_finish'):
                if hasattr(obj, fin):
                    getattr(obj, fin)(res)
                    break
            self.net_msg.set_text(text)
        except GLib.Error as e:
            self.net_msg.set_text(f'Failed: {e.message}')
        GLib.timeout_add(1500, lambda: self.net_refresh() and False)

    def wifi_toggle(self, sw, _p):
        run('nmcli', 'radio', 'wifi', 'on' if sw.get_active() else 'off')
        GLib.timeout_add(1500, lambda: self.net_refresh() and False)

    def wifi_scan(self):
        dev = self.wifi_dev()
        if dev:
            self.net_msg.set_text('Scanning…')
            dev.request_scan_async(None, self.net_done, 'Scan done')

    def wifi_connect(self, ap, ssid):
        c, dev = self.net_client(), self.wifi_dev()
        saved = self.saved_wifi().get(ssid)
        self.net_msg.set_text(f'Connecting to {ssid}…')
        if saved:
            c.activate_connection_async(saved, dev, ap.get_path(), None, self.net_done,
                                        f'Connected to {ssid}')
            return
        if not secured(ap):
            c.add_and_activate_connection_async(None, dev, ap.get_path(), None, self.net_done,
                                                f'Connected to {ssid}')
            return
        pw = self.ask_password(ssid)
        if pw is None:
            self.net_msg.set_text('')
            return
        con = NM.SimpleConnection.new()
        sec = NM.SettingWirelessSecurity.new()
        sec.set_property('key-mgmt', 'sae' if sae_only(ap) else 'wpa-psk')
        sec.set_property('psk', pw)
        con.add_setting(sec)
        c.add_and_activate_connection_async(con, dev, ap.get_path(), None, self.net_done,
                                            f'Connected to {ssid}')

    def ask_password(self, ssid):
        d = Gtk.Dialog(title=f'Wi-Fi password for {ssid}', transient_for=self, modal=True)
        d.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Connect', Gtk.ResponseType.OK)
        d.set_default_response(Gtk.ResponseType.OK)
        e = Gtk.Entry(visibility=False, activates_default=True, margin=12,
                      input_purpose=Gtk.InputPurpose.PASSWORD, width_chars=28)
        show = Gtk.CheckButton(label='Show the password', margin_start=12, margin_bottom=8)
        show.connect('toggled', lambda b: e.set_visibility(b.get_active()))
        d.get_content_area().add(e)
        d.get_content_area().add(show)
        d.show_all()
        ok = d.run() == Gtk.ResponseType.OK
        pw = e.get_text()
        d.destroy()
        return pw if ok and pw else None

    # -- Ethernet
    def eth_page(self, box):
        box.add(heading('Ethernet', 'Ethernet'))
        self.eth_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.add(self.eth_list)
        box.add(note('The cable is used first while it is plugged in (route metric 100; Wi-Fi '
                     '600, mobile data 1500).'))

    def eth_refresh(self):
        c = self.net_client()
        rows = []
        for dev in (c.get_devices() if c else []):
            if not isinstance(dev, NM.DeviceEthernet):
                continue
            iface, st = dev.get_iface(), dev.get_state()
            drv = dev.get_driver() or ''
            if not dev.get_managed():
                rows.append((iface, f'{drv} · not managed by NetworkManager, so it is never '
                             'preferred over Wi-Fi. Fix (at the laptop):\n'
                             f'sudo ifdown {iface}; sudo sed -i -E "/^(allow-hotplug|iface) +{iface}/s/^/# /" '
                             '/etc/network/interfaces; sudo systemctl restart NetworkManager',
                             [], '<span foreground="#ffb84a">⚠</span>'))
                continue
            if st == NM.DeviceState.UNAVAILABLE or not dev.get_carrier():
                rows.append((iface, f'{drv} · no cable', [], '<span foreground="#8a8a92">○</span>'))
                continue
            on = st == NM.DeviceState.ACTIVATED
            speed = dev.get_speed()
            m = route_metric(iface)
            detail = f'{drv} · ' + (f'{ip4(dev)} · {speed} Mbit/s' + (f' · metric {m}' if m else '')
                                    if on else 'cable in, not connected')
            acts = [('Disconnect', lambda d=dev: d.disconnect_async(None, self.net_done, 'Disconnected'))] \
                if on else [('Connect', lambda d=dev: c.activate_connection_async(
                    None, d, None, None, self.net_done, 'Connected'))]
            rows.append((iface, detail, acts, '<span foreground="#5fd068">●</span>' if on else ''))
        self.net_rows(self.eth_list, rows or [('No wired port', '', [], '')])

    # -- NetBird
    def netbird_page(self, box):
        box.add(heading('NetBird', 'NetBird'))
        self.nb_now = Gtk.Label(xalign=0, wrap=True)
        box.add(self.nb_now)
        line = Gtk.Box(spacing=8, margin_top=6)
        for label, cmd in (('On', 'up'), ('Off', 'down')):
            b = Gtk.Button(label=label)
            b.connect('clicked', lambda _b, cmd=cmd: self.nb_cmd(cmd))
            line.add(b)
        box.add(line)
        box.add(heading('Peers'))
        self.nb_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add(self.nb_list)
        box.add(note('Your private network between your own machines. Names ending in '
                     '.netbird.selfhosted go through NetBird, everything else as usual.'))

    def nb_cmd(self, cmd):
        self.net_msg.set_text(f'NetBird {"on" if cmd == "up" else "off"}…')

        def work():
            out = run('netbird', cmd, timeout=40)
            idle(lambda: (self.net_msg.set_text(out.strip().splitlines()[-1] if out.strip()
                                                         else 'Done'), self.nb_refresh()) and False)
        threading.Thread(target=work, daemon=True).start()

    def nb_refresh(self):
        def work():
            try:
                st = json.loads(run('netbird', 'status', '--json', timeout=15) or '{}')
            except ValueError:
                st = {}
            idle(lambda: self.nb_show(st) and False)
        threading.Thread(target=work, daemon=True).start()

    def nb_show(self, st):
        if not st:
            self.nb_now.set_text('NetBird is not running (or not installed)')
            self.net_rows(self.nb_list, [])
            return
        peers = st.get('peers', {})
        up = st.get('management', {}).get('connected')
        self.nb_now.set_text(
            (f'Connected · {st.get("netbirdIp", "")} · {st.get("fqdn", "")}' if up else
             f'Not connected ({st.get("daemonStatus", "?")})')
            + f'\nPeers online: {peers.get("connected", 0)} of {peers.get("total", 0)}')
        rows = []
        for p in sorted(peers.get('details', []),
                        key=lambda p: (p.get('status') != 'Connected', p.get('fqdn', ''))):
            on = p.get('status') == 'Connected'
            name = (p.get('fqdn') or '').split('.')[0] or p.get('netbirdIp', '')
            how = p.get('connectionType', '')
            lat = p.get('latency') or 0
            ms = f' · {lat / 1e6:.0f} ms' if isinstance(lat, (int, float)) and lat else ''
            rows.append((name, f'{p.get("netbirdIp", "")}' + (f' · {how}{ms}' if on else ' · offline'),
                         [], '<span foreground="#5fd068">●</span>' if on else
                         '<span foreground="#8a8a92">○</span>'))
        self.net_rows(self.nb_list, rows[:40])

    # -- refresh while the tab is open
    def net_refresh(self):
        self.wifi_refresh()
        self.eth_refresh()
        return True

    def net_tick(self):
        if self.tab_on('network'):
            self.net_refresh()
            self.nb_tick = getattr(self, 'nb_tick', 0) + 1
            if self.nb_tick % 3 == 1:
                self.nb_refresh()
        return True

    def network_pages(self):
        """(name, title, Pages) for the Network tab's sections"""
        wifi, eth, nb = Pages(), Pages(), Pages()
        labels = [note() for _ in range(3)]
        for pages, lb in zip((wifi, eth, nb), labels):
            pages.footer(lb)
        self.net_msg = Notes(labels)
        self.wifi_page(wifi)
        self.eth_page(eth)
        self.netbird_page(nb)
        idle(lambda: (self.net_refresh(), self.nb_refresh()) and False)
        self.timers.append(GLib.timeout_add_seconds(5, self.net_tick))
        return wifi, eth, nb

