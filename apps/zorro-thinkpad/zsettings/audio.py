"""sound through PipeWire's PulseAudio side (pactl): outputs, inputs, what is playing where,
and 'Together': one output that plays on several devices at once (module-combine-sink)"""
import json

from .base import load_conf, run, update_conf

TOGETHER = 'zorro_together'          # the combined output's node name


def _json(*args):
    try:
        return json.loads(run('pactl', '-f', 'json', *args) or '[]')
    except ValueError:
        return []


def _volume(dev):
    vols = list((dev.get('volume') or {}).values())
    try:
        return int(vols[0]['value_percent'].rstrip('%')) if vols else 0
    except (KeyError, ValueError):
        return 0


def _kind(props):
    bus = props.get('device.bus', '')
    return {'bluetooth': 'Bluetooth', 'usb': 'USB', 'pci': 'built in'}.get(bus, bus or 'virtual')


def devices(kind='sinks'):
    """outputs ('sinks') or inputs ('sources', without monitors):
    [{name, desc, volume, muted, kind, default, together}]"""
    default = run('pactl', 'get-default-sink' if kind == 'sinks' else 'get-default-source').strip()
    out = []
    for d in _json('list', kind):
        name = d.get('name', '')
        if name.endswith('.monitor'):
            continue
        props = d.get('properties') or {}
        out.append({'name': name, 'desc': d.get('description') or name, 'volume': _volume(d),
                    'muted': bool(d.get('mute')), 'kind': _kind(props),
                    'default': name == default, 'together': name == TOGETHER})
    return out


def use(kind, name):
    """the default output / input (WirePlumber remembers it, also for a device that comes back)"""
    run('pactl', 'set-default-sink' if kind == 'sinks' else 'set-default-source', name)


def set_volume(kind, name, pct):
    run('pactl', 'set-sink-volume' if kind == 'sinks' else 'set-source-volume', name, f'{int(pct)}%')


def set_mute(kind, name, on):
    run('pactl', 'set-sink-mute' if kind == 'sinks' else 'set-source-mute', name, '1' if on else '0')


def streams():
    """what is playing now: [{id, app, what, sink, volume}]"""
    sinks = {str(d.get('index')): d.get('name') for d in _json('list', 'sinks')}
    out = []
    for s in _json('list', 'sink-inputs'):
        p = s.get('properties') or {}
        if p.get('media.role') == 'event' or p.get('application.id') == 'org.PulseAudio.pavucontrol' \
                or TOGETHER in (p.get('node.name', '') + p.get('media.name', '')):
            continue                    # Together's own feeds to its devices are not apps
        out.append({'id': s.get('index'), 'app': p.get('application.name') or p.get('node.name', '?'),
                    'what': p.get('media.name', ''), 'sink': sinks.get(str(s.get('sink')), ''),
                    'volume': _volume(s)})
    return out


def move(stream_id, sink):
    run('pactl', 'move-sink-input', str(stream_id), sink)


def together_module():
    """index of our combine module (the JSON list has no index: use the short list)"""
    for line in run('pactl', 'list', 'short', 'modules').splitlines():
        f = line.split('\t')
        if len(f) >= 3 and f[1] == 'module-combine-sink' and f'sink_name={TOGETHER}' in f[2]:
            return f[0]
    return None


def together_set(names):
    """(re)make the Together output from these outputs; [] removes it. Remembered for login."""
    old = together_module()
    if old is not None:
        run('pactl', 'unload-module', str(old))
    update_conf('audio', together=list(names))
    if len(names) < 2:
        return 'Together output removed' if old is not None else ''
    # one word: PipeWire cuts a description at its first space; the app shows the members
    run('pactl', 'load-module', 'module-combine-sink', f'sink_name={TOGETHER}',
        'sink_properties=device.description=Together', 'slaves=' + ','.join(names))
    return 'Together output ready: choose it as output, or for one app under Playing now'


def together_restore():
    """at login (keyd): make the Together output again if it was set up"""
    names = load_conf().get('audio', {}).get('together', [])
    if len(names) >= 2 and together_module() is None:
        together_set(names)
