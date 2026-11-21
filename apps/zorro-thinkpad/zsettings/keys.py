"""what the Fn keys do"""
import json
import re
import struct
import sys
from pathlib import Path
from .base import APPS, STAR_ACTIONS, STATE, load_conf, osd, run, spawn, write_atomic


# ---- key actions ----------------------------------------------------------------------

def key_sink():
    """the output the keys work on: where sound is playing now (the newest stream that is
    not paused), else the default output. The equaliser is a filter in between: its
    real device is meant, so keys, Settings and the Dialer show the same level."""
    try:
        sinks = {x['index']: x['name'] for x in json.loads(run('pactl', '-f', 'json', 'list', 'sinks') or '[]')}
        playing = [x for x in json.loads(run('pactl', '-f', 'json', 'list', 'sink-inputs') or '[]')
                   if not x.get('corked') and x.get('properties', {}).get('node.name') != 'zorro_eq.out']
    except ValueError:
        sinks, playing = {}, []
    name = sinks.get(max(playing, key=lambda x: x['index'])['sink']) if playing else None
    name = name or run('pactl', 'get-default-sink').strip()
    if name == 'zorro_eq':
        from . import eq
        name = eq.settings().get('target') or name
    return name or '@DEFAULT_SINK@'


def volume(sink=None):
    sink = sink or key_sink()
    try:
        info = next(x for x in json.loads(run('pactl', '-f', 'json', 'list', 'sinks') or '[]')
                    if x['name'] == sink)
        vols = [int(str(c['value_percent']).rstrip('%')) for c in info['volume'].values()]
        return (max(vols) if vols else 0), bool(info['mute'])
    except (ValueError, StopIteration, KeyError):
        return 0, False


def show_volume(sink=None):
    vol, muted = volume(sink)
    if muted:
        osd('audio-volume-muted-symbolic', vol, 'Muted')
    else:
        icon = ('audio-volume-low-symbolic' if vol < 34 else
                'audio-volume-medium-symbolic' if vol < 67 else 'audio-volume-high-symbolic')
        osd(icon, vol)


def key_volume(step):
    sink = key_sink()
    run('pactl', 'set-sink-mute', sink, '0')                 # turning it up means: unmute
    vol, _ = volume(sink)
    # up stops at 100 %, but a level set above it in Settings is never pulled down by "up"
    new = max(0, vol + step) if step < 0 else max(vol, min(100, vol + step))
    run('pactl', 'set-sink-volume', sink, f'{new}%')
    show_volume(sink)


def key_mute():
    sink = key_sink()
    run('pactl', 'set-sink-mute', sink, 'toggle')
    show_volume(sink)


def key_mic_mute():
    run('wpctl', 'set-mute', '@DEFAULT_AUDIO_SOURCE@', 'toggle')
    muted = '[MUTED]' in run('wpctl', 'get-volume', '@DEFAULT_AUDIO_SOURCE@')
    # the F4 LED follows the ALSA capture switch, not PipeWire: keep it in step
    led = Path('/sys/class/leds/platform::micmute/brightness')
    try:
        led.write_text('1' if muted else '0')
    except OSError:
        pass
    osd('microphone-disabled-symbolic' if muted else 'audio-input-microphone-symbolic', None,
        'Microphone off' if muted else 'Microphone on')


def backlight():
    for d in sorted(Path('/sys/class/backlight').glob('*')):
        return d
    return None


def key_brightness(up):
    d = backlight()
    if not d:
        return
    mx = int((d / 'max_brightness').read_text())
    cur = int((d / 'brightness').read_text())
    pct = cur * 100 / mx
    # smaller steps at the dark end, where each step is easy to see
    step = 2 if pct < 10 or (pct <= 10 and not up) else 5 if pct < 30 else 10
    new = max(1, min(100, round(pct + (step if up else -step))))
    try:
        (d / 'brightness').write_text(str(max(1, round(new * mx / 100))))
    except PermissionError:
        if run('brightnessctl', 'set', f'{new}%') == '':
            osd('dialog-warning-symbolic', None, 'Brightness: run apps/zorro-thinkpad/install.sh')
            return
    osd('display-brightness-symbolic', new)


def rfkill_all(block, rtype=0):
    """block/unblock radios through /dev/rfkill (group netdev): rtype 0 = all, 5 = wwan"""
    RFKILL_OP_CHANGE_ALL = 3
    with open('/dev/rfkill', 'wb', buffering=0) as fh:
        fh.write(struct.pack('IBBBB', 0, rtype, RFKILL_OP_CHANGE_ALL, 1 if block else 0, 0))


def radios_soft_blocked(types=None):
    out = []
    for r in Path('/sys/class/rfkill').glob('rfkill*'):
        t = (r / 'type').read_text().strip()
        if types is None or t in types:
            out.append((r / 'soft').read_text().strip() == '1')
    return out


def airplane_on():
    """is airplane mode on? Our own switch decides (remembered until restart); only when it
    was never used, all radios being blocked counts as on. Looking at the radios alone fails:
    NetworkManager may keep Wi-Fi off after airplane mode, and then the key only ever turned
    airplane mode on again."""
    try:
        st = json.loads(STATE.read_text())
    except (OSError, ValueError):
        st = {}
    if 'airplane' in st:
        return bool(st['airplane'])
    states = radios_soft_blocked()
    return bool(states) and all(states)


def key_airplane():
    turn_off = not airplane_on()         # off -> all radios off; on -> all back on
    try:
        rfkill_all(turn_off)
    except OSError as e:
        osd('dialog-warning-symbolic', None, f'Airplane mode: {e.strerror}')
        return
    write_state(airplane=turn_off)
    if not turn_off:                    # NetworkManager keeps its own Wi-Fi / mobile switch
        run('nmcli', 'radio', 'wifi', 'on')
        run('nmcli', 'radio', 'wwan', 'on')
    osd('airplane-mode-symbolic' if turn_off else 'network-wireless-symbolic', None,
        'Airplane mode on — all radios off' if turn_off else 'Airplane mode off')


def key_lte(on):
    try:
        rfkill_all(not on, rtype=5)
    except OSError:
        pass
    run('nmcli', 'radio', 'wwan', 'on' if on else 'off')
    osd('network-cellular-signal-good-symbolic' if on else 'network-cellular-offline-symbolic',
        None, 'Mobile data (LTE) on' if on else 'Mobile data (LTE) off')


def outputs():
    """connected xrandr outputs: [(name, is_internal, active)]"""
    out = []
    for line in run('xrandr', '--query').splitlines():
        m = re.match(r'(\S+) connected', line)
        if m:
            name = m.group(1)
            out.append((name, name.startswith(('eDP', 'LVDS', 'DSI')),
                        bool(re.search(r' \d+x\d+\+\d+\+\d+', line))))
    return out


def key_display():
    outs = outputs()
    internal = next((o[0] for o in outs if o[1]), None)
    external = next((o[0] for o in outs if not o[1]), None)
    if not external or not internal:
        osd('video-display-symbolic', None, 'No external screen connected')
        return
    modes = ['extend', 'mirror', 'external', 'laptop']
    try:
        cur = json.loads(STATE.read_text()).get('display')
    except (OSError, ValueError):
        cur = None
    mode = modes[(modes.index(cur) + 1) % len(modes)] if cur in modes else 'extend'
    if mode == 'extend':
        cmd = ['--output', internal, '--auto', '--primary',
               '--output', external, '--auto', '--right-of', internal]
        text = 'Extend: second screen on the right'
    elif mode == 'mirror':
        cmd = ['--output', internal, '--auto', '--primary',
               '--output', external, '--auto', '--same-as', internal]
        text = 'Mirror: same picture on both'
    elif mode == 'external':
        cmd = ['--output', external, '--auto', '--primary', '--output', internal, '--off']
        text = 'External screen only'
    else:
        cmd = ['--output', internal, '--auto', '--primary', '--output', external, '--off']
        text = 'Laptop screen only'
    run('xrandr', *cmd)
    write_state(display=mode)
    osd('video-display-symbolic', None, text)


def write_state(**kv):
    try:
        st = json.loads(STATE.read_text())
    except (OSError, ValueError):
        st = {}
    st.update(kv)
    write_atomic(STATE, json.dumps(st))


def key_star():
    c = load_conf()
    act = c.get('star', 'screenshot')
    if act == 'custom':
        cmd = c.get('star_command', '').strip()
        if not cmd:
            osd('starred-symbolic', None, 'Star key: choose an action in the Zorro app (F9)')
            return
        spawn(['sh', '-c', cmd])
    else:
        spawn(STAR_ACTIONS.get(act, STAR_ACTIONS['screenshot'])[1])


def key_settings():
    spawn([sys.executable, str(APPS / 'zorro-thinkpad' / 'zorro-thinkpad')])




KEYS = {
    'vol-up': lambda: key_volume(5), 'vol-down': lambda: key_volume(-5), 'mute': key_mute,
    'mic-mute': key_mic_mute,
    'bright-up': lambda: key_brightness(True), 'bright-down': lambda: key_brightness(False),
    'display': key_display, 'airplane': key_airplane,
    'lte-on': lambda: key_lte(True), 'lte-off': lambda: key_lte(False),
    'star': key_star, 'settings': key_settings,
    'screenshot-region': lambda: spawn(['zorro-shot', '--region']),
}
