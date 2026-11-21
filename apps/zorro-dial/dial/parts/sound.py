"""Where the music plays: the laptop's own outputs and the Bluetooth devices ticked in
System → Bluetooth. Switching goes through the Zorro app's own audio code
(apps/zorro-thinkpad/zsettings), so the equaliser and the 'Together' output behave the same."""
import re
import time

from .base import run, tile

try:
    from zsettings import audio, eq
except ImportError:                     # without the Zorro app: plain pactl
    audio = eq = None

CONNECT_LIMIT = 30                      # seconds a device may show as connecting
FAILED_SHOWN = 8                        # seconds 'not reachable' stays on a device
SINK_TRIES = 20                         # half seconds to wait for a connected device's output
CONNECTING = {}                         # address -> since when
FAILED = {}                             # address -> when


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
    target = eq.NODE if eq and eq.running() else name
    for ln in run('pactl', 'list', 'short', 'sink-inputs').splitlines():
        sid = ln.split('\t')[0]
        if sid.isdigit():
            run('pactl', 'move-sink-input', sid, target)


def parse_bt(text):
    """what 'bluetoothctl info' says of a device: its name and whether it is connected"""
    name = re.search(r'^\s*Alias: (.+)$', text, re.M) or re.search(r'^\s*Name: (.+)$', text, re.M)
    return {'name': name.group(1).strip() if name else '', 'connected': 'Connected: yes' in text}


def bt_devices(addresses):
    return {mac: parse_bt(run('bluetoothctl', 'info', mac, timeout=3)) for mac in addresses}


def sink_of(mac, outs):
    key = mac.replace(':', '_').lower()
    return next((d for d in outs if key in d['name'].lower()), None)


def rows(outs, ticked, bt, connecting=None, failed=None, now=None):
    """the picker's rows. state: 'use' (plays here now), 'ready' (one tap: play here),
    'off' (greyed: one tap connects it), 'connecting'"""
    now = time.time() if now is None else now
    own = [d for d in outs if 'bluez' not in d['name'].lower()]
    out = [{'kind': 'own', 'name': 'Laptop' if len(own) == 1 else d['desc'], 'desc': d['desc'],
            'sink': d['name'], 'state': 'use' if d['default'] else 'ready'} for d in own]
    for mac in ticked:
        info = bt.get(mac) or {}
        sink = sink_of(mac, outs)
        if now - (connecting or {}).get(mac, -CONNECT_LIMIT) < CONNECT_LIMIT:
            state = 'connecting'
        elif sink:
            state = 'use' if sink['default'] else 'ready'
        else:
            state = 'off'
        out.append({'kind': 'bt', 'name': info.get('name') or mac, 'mac': mac, 'state': state,
                    'sink': sink['name'] if sink else None,
                    'failed': now - (failed or {}).get(mac, -FAILED_SHOWN) < FAILED_SHOWN})
    return out


def connect(mac):
    """connect a Bluetooth device and play there once its output is there; True when it plays"""
    if mac in CONNECTING:               # a second tap while it connects: the first one goes on
        return False
    CONNECTING[mac] = time.time()
    FAILED.pop(mac, None)
    try:
        run('bluetoothctl', 'power', 'on')
        run('bluetoothctl', 'connect', mac, timeout=15)
        for _ in range(SINK_TRIES):         # the output shows up a moment after the connection
            sink = sink_of(mac, outputs())
            if sink:
                use(sink['name'])
                return True
            time.sleep(0.5)
        FAILED[mac] = time.time()
        return False
    finally:
        CONNECTING.pop(mac, None)


SUBS = {'use': 'plays here', 'ready': 'tap: play here', 'off': 'tap: connect and play',
        'connecting': 'connecting…'}


def look(row):
    state = row['state']
    return {'label': True, 'lit': state == 'use', 'dim': state == 'off', 'busy': state == 'connecting',
            'keep': True, 'refresh': True}


def own_tile(row):
    return tile('lucide:laptop', row['name'][:24], SUBS[row['state']], lambda: use(row['sink']),
                id=f'out:{row["sink"]}', **look(row))


def bt_tile(row):
    mac, state = row['mac'], row['state']
    sub = 'not reachable · tap: try again' if row.get('failed') and state == 'off' else SUBS[state]
    if state == 'connecting':
        return tile('lucide:bluetooth', row['name'][:24], sub, None, id=f'bt:{mac}', **look(row))
    if row['sink']:
        return tile('lucide:bluetooth', row['name'][:24], sub, lambda: use(row['sink']),
                    id=f'bt:{mac}', **look(row))

    def mark():                         # at the tap, so 'connecting…' shows at once
        CONNECTING[mac] = time.time()
    return tile('lucide:bluetooth', row['name'][:24], sub, lambda: connect(mac), id=f'bt:{mac}',
                start=mark, **look(row))


def tiles(outs, ticked, bt):
    return [own_tile(r) if r['kind'] == 'own' else bt_tile(r) for r in rows(outs, ticked, bt, CONNECTING, FAILED)]
