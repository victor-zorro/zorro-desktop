"""Sound output, from the Dialer: the outputs there are, and Bluetooth audio devices that are
paired but not connected. Switching goes through the Zorro app's own audio code
(apps/zorro-thinkpad/zsettings), so the equaliser and the 'Together' output behave the same."""
import re
import subprocess
import sys
import time

from .base import APPS, run, tile

sys.path.insert(0, str(APPS / 'zorro-thinkpad'))
try:
    from zsettings import audio, eq
except ImportError:                     # without the Zorro app: plain pactl
    audio = eq = None

BT_AUDIO = ('audio-headset', 'audio-headphones', 'audio-card', 'audio-speakers')


def outputs():
    """[{name, desc, default}] of the real outputs (not the equaliser's own node)"""
    if audio:
        devs = audio.devices('sinks')
        cur = None
        if eq and eq.settings().get('on') and eq.running():
            cur = eq.settings().get('target')           # with the equaliser on: what it feeds
        out = [d for d in devs if d['name'] != getattr(eq, 'NODE', '')]
        if cur:
            for d in out:
                d['default'] = d['name'] == cur
        return out
    default = run('pactl', 'get-default-sink').strip()
    out = []
    for ln in run('pactl', 'list', 'short', 'sinks').splitlines():
        parts = ln.split('\t')
        if len(parts) > 1:
            out.append({'name': parts[1], 'desc': parts[1], 'default': parts[1] == default})
    return out


def use(name):
    """make this the output (also the running sounds move along)"""
    if eq and eq.settings().get('on') and eq.running():
        eq.retarget(name)
    elif audio:
        audio.use('sinks', name)
    else:
        run('pactl', 'set-default-sink', name)
    for ln in run('pactl', 'list', 'short', 'sink-inputs').splitlines():
        sid = ln.split('\t')[0]
        if sid.isdigit():
            run('pactl', 'move-sink-input', sid, name if not (eq and eq.running()) else eq.NODE)


def bt_audio():
    """paired Bluetooth audio devices: [(mac, name, connected)]"""
    out = []
    for ln in run('bluetoothctl', 'devices', 'Paired').splitlines():
        m = re.match(r'Device (\S+) (.+)', ln)
        if not m:
            continue
        info = run('bluetoothctl', 'info', m.group(1), timeout=3)
        icon = re.search(r'Icon: (\S+)', info)
        if icon and icon.group(1) in BT_AUDIO:
            out.append((m.group(1), m.group(2), 'Connected: yes' in info))
    return out


def connect(mac):
    """connect a Bluetooth device and make it the output once its sink is there"""
    run('bluetoothctl', 'power', 'on')
    run('bluetoothctl', 'connect', mac, timeout=20)
    key = mac.replace(':', '_')
    for _ in range(20):                 # the sink shows up a moment after the connection
        sink = next((d['name'] for d in outputs() if key in d['name']), None)
        if sink:
            use(sink)
            return
        time.sleep(0.5)


def node():
    """the Music part's first tile: the output now, unfolding into every output"""
    outs = outputs()
    cur = next((d for d in outs if d['default']), None)

    def kids():
        tiles = [tile('lucide:volume-2' if d['default'] else 'lucide:speaker', d['desc'][:24],
                      'in use' if d['default'] else 'use this', lambda n=d['name']: use(n),
                      id=f'out:{d["name"]}', lit=d['default'])
                 for d in outputs()]
        have = {d['name'] for d in outputs()}
        for mac, name, conn in bt_audio():
            if conn and any(mac.replace(':', '_') in n for n in have):
                continue                # connected: already in the list above
            tiles.append(tile('lucide:bluetooth', name[:24], 'connect and use',
                              lambda m=mac: connect(m), id=f'bt:{mac}'))
        return tiles
    return tile('lucide:volume-2', 'Sound', (cur['desc'] if cur else 'output')[:26], None,
                id='sound-out', kids=kids)
