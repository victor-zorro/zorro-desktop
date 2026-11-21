"""The hub centre's small line under the time: the connection and the battery."""
import re
import subprocess
from pathlib import Path

POWER = Path('/sys/class/power_supply')
MOBILE = ('gsm', 'cdma', 'wwan')


def nmcli_devices():
    try:
        return subprocess.run(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device'],
                              capture_output=True, text=True, timeout=4).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ''


def connection(text):
    """'Cable', the Wi-Fi's name, 'Mobile' or 'Offline' from nmcli's device list; '' when
    nmcli said nothing (not installed)"""
    if not text.strip():
        return ''
    found = {}
    for line in text.splitlines():
        cols = [c.replace('\\:', ':') for c in re.split(r'(?<!\\):', line)]
        if len(cols) < 4 or cols[2] != 'connected':
            continue
        device, kind, name = cols[0], cols[1], cols[3]
        if kind in MOBILE or device.startswith('ww'):
            found.setdefault('mobile', 'Mobile')
        elif kind == 'ethernet':
            found.setdefault('cable', 'Cable')
        elif kind == 'wifi':
            found.setdefault('wifi', name or 'Wi-Fi')
    return found.get('cable') or found.get('wifi') or found.get('mobile') or 'Offline'


def battery(root=POWER):
    """(percent, status) of the laptop's battery, or None without one"""
    for d in sorted(Path(root).glob('*')):
        try:
            if (d / 'type').read_text().strip() != 'Battery':
                continue
            if (d / 'scope').is_file() and (d / 'scope').read_text().strip() == 'Device':
                continue                # a mouse's or headset's own battery
            return int((d / 'capacity').read_text()), (d / 'status').read_text().strip().lower()
        except (OSError, ValueError):
            continue
    return None


def battery_text(bat):
    if not bat:
        return ''
    percent, status = bat
    if status == 'charging':
        return f'{percent}% charging'
    if status in ('full', 'not charging'):
        return f'{percent}% plugged in'
    return f'{percent}%'


def read():
    """(connection, battery) as short texts; slow (nmcli): call it in a thread"""
    name = connection(nmcli_devices())
    return (name if len(name) <= 20 else name[:19] + '…'), battery_text(battery())
