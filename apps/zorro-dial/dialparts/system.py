"""System: gauges, switches, power"""
# flake8: noqa: F403,F405 - helpers come from base (and earlier parts)
from .base import *
from .messages import *


# ---- System: gauges, switches, power ----------------------------------------------------
def thinkpad_keys():
    sys.path.insert(0, str(APPS / 'zorro-thinkpad'))
    try:
        from zsettings import keys
        return keys
    except ImportError:
        return None


class System(Part):
    key, title = 'system', 'System'

    def fetch(self):
        bat = Path('/sys/class/power_supply/BAT0')
        try:
            self.bat = int((bat / 'capacity').read_text())
            self.bat_status = (bat / 'status').read_text().strip().lower()
        except (OSError, ValueError):
            self.bat, self.bat_status = None, ''
        wifi = re.search(r'^yes:(\d+)', run('nmcli', '-t', '-f', 'ACTIVE,SIGNAL', 'dev', 'wifi', 'list', '--rescan', 'no'), re.M)
        self.wifi_sig = int(wifi.group(1)) if wifi else None
        self.wifi_on = 'enabled' in run('nmcli', 'radio', 'wifi')

        def cpu():
            v = [int(x) for x in Path('/proc/stat').read_text().split('\n')[0].split()[1:]]
            return sum(v), v[3] + v[4]
        t0, i0 = cpu()
        time.sleep(0.25)
        t1, i1 = cpu()
        self.cpu = 1 - (i1 - i0) / max(1, t1 - t0)
        st = os.statvfs('/')
        self.disk = 1 - st.f_bavail / st.f_blocks
        self.bt_on = 'Powered: yes' in run('bluetoothctl', 'show')
        self.dnd = run('dunstctl', 'is-paused').strip() == 'true'
        soft = []
        for r in Path('/sys/class/rfkill').glob('rfkill*'):
            try:
                soft.append((r / 'soft').read_text().strip() == '1')
            except OSError:
                pass
        k = thinkpad_keys()                  # the airplane switch's own state (see keys.airplane_on)
        self.airplane = k.airplane_on() if k else bool(soft) and all(soft)
        self.ready = True

    def preview(self):
        if getattr(self, 'bat', None) is None:
            return 'SYSTEM', 'System', []
        return 'BATTERY', f'{self.bat}%', [self.bat_status]

    def toggle(self, what):
        if what == 'wifi':
            run('nmcli', 'radio', 'wifi', 'off' if self.wifi_on else 'on')
        elif what == 'bt':
            run('bluetoothctl', 'power', 'off' if self.bt_on else 'on')
        elif what == 'dnd':
            run('dunstctl', 'set-paused', 'toggle')
        elif what == 'airplane':
            k = thinkpad_keys()
            if k:
                k.key_airplane()
        time.sleep(0.6)
        self.fetch()

    def rings(self):
        if not self.ready:
            return [[], [], []]
        g = [tile('lucide:battery-full', f'Battery {self.bat}%' if self.bat is not None else 'Battery',
                  self.bat_status, lambda: spawn('zorro-settings', '--page', 'power:0'),
                  value=(self.bat or 0) / 100),
             tile('lucide:signal', 'Signal' + (f' {self.wifi_sig}%' if self.wifi_sig else ''), 'Wi-Fi',
                  lambda: spawn('zorro-settings', '--page', 'wifi:0'), value=(self.wifi_sig or 0) / 100),
             tile('lucide:activity', f'CPU {self.cpu * 100:.0f}%', '', lambda: spawn('x-terminal-emulator', '-e', 'htop'),
                  value=self.cpu),
             tile('lucide:hard-drive', f'Disk {self.disk * 100:.0f}%', 'used', None, value=self.disk)]
        sw = [tile('lucide:wifi', 'Wi-Fi', 'on' if self.wifi_on else 'off', lambda: self.toggle('wifi'),
                   lit=self.wifi_on, keep=True),
              tile('lucide:bluetooth', 'Bluetooth', 'on' if self.bt_on else 'off', lambda: self.toggle('bt'),
                   lit=self.bt_on, keep=True),
              tile('lucide:radio-tower', 'Mobile', 'LTE', lambda: spawn('zorro-settings', '--page', 'lte:0')),
              tile('lucide:plane', 'Airplane', 'on' if self.airplane else 'off', lambda: self.toggle('airplane'),
                   lit=self.airplane, keep=True),
              tile('lucide:bell', 'Do not disturb', 'on' if self.dnd else 'off', lambda: self.toggle('dnd'),
                   lit=self.dnd, keep=True)]
        pw = [tile('lucide:lock', 'Lock', '', lambda: spawn('loginctl', 'lock-session')),
              tile('lucide:moon', 'Sleep', '', lambda: spawn('systemctl', 'suspend')),
              tile('lucide:log-out', 'Log out', '', lambda: spawn('openbox', '--exit'), confirm=True),
              tile('lucide:rotate-ccw', 'Restart', '', lambda: spawn('systemctl', 'reboot'), confirm=True),
              tile('lucide:power', 'Power off', '', lambda: spawn('systemctl', 'poweroff'), confirm=True),
              tile('lucide:settings', 'Settings', 'Zorro', lambda: spawn('zorro-settings'))]
        return [g, sw, pw]
