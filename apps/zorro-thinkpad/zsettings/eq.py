"""the equaliser: 10 bands in front of one sound output, with PipeWire's own filter-chain.

A small extra PipeWire process (pipewire -c zorro-eq.conf) offers an output called
"Equaliser"; it filters and passes the sound on to the real device (the target). Sliders
change the bands live (pw-cli set-param); the gains are remembered per target device.
While on, "Equaliser" is the default output; off, the device itself is.
"""
import json
import os
import signal
import subprocess
import time
from pathlib import Path

from .base import CONF, load_conf, run, update_conf

BANDS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
LABELS = ['31', '62', '125', '250', '500', '1k', '2k', '4k', '8k', '16k']
PRESETS = {
    'Flat': [0] * 10,
    'Bass': [6, 5, 4, 2, 0, 0, 0, 0, 0, 0],
    'Voice': [-4, -3, -1, 1, 3, 4, 4, 3, 1, 0],
    'Treble': [0, 0, 0, 0, 0, 1, 2, 4, 5, 6],
    'Warm': [3, 3, 2, 1, 0, -1, -1, 0, 1, 1],
}
NODE = 'zorro_eq'
CFG = CONF.parent / 'zorro-eq.conf'
PIDFILE = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / 'zorro-eq.pid'


def settings():
    s = load_conf().get('eq', {})
    return {'on': s.get('on', False), 'target': s.get('target', ''),
            'gains': s.get('gains', {}), 'preset': s.get('preset', {})}


def gains_for(target):
    g = settings()['gains'].get(target)
    return [float(x) for x in g] if isinstance(g, list) and len(g) == 10 else [0.0] * 10


def config(target, gains):
    nodes = '\n'.join(
        f'          {{ type = builtin name = eq_{i} label = bq_peaking '
        f'control = {{ "Freq" = {f:.1f} "Q" = 1.0 "Gain" = {g:.2f} }} }}'
        for i, (f, g) in enumerate(zip(BANDS, gains)))
    links = '\n'.join(f'          {{ output = "eq_{i}:Out" input = "eq_{i + 1}:In" }}'
                      for i in range(len(BANDS) - 1))
    return f'''# made by the Zorro app (Audio > Equaliser); rewritten on every change
context.properties = {{ log.level = 0 }}
context.spa-libs = {{
  audio.convert.* = audioconvert/libspa-audioconvert
  support.*       = support/libspa-support
}}
context.modules = [
  {{ name = libpipewire-module-rt flags = [ ifexists nofail ] }}
  {{ name = libpipewire-module-protocol-native }}
  {{ name = libpipewire-module-client-node }}
  {{ name = libpipewire-module-adapter }}
  {{ name = libpipewire-module-filter-chain
    args = {{
      node.description = "Equaliser"
      media.name       = "Equaliser"
      filter.graph = {{
        nodes = [
{nodes}
        ]
        links = [
{links}
        ]
      }}
      audio.channels = 2
      audio.position = [ FL FR ]
      capture.props = {{ node.name = "{NODE}" media.class = Audio/Sink }}
      playback.props = {{ node.name = "{NODE}.out" node.passive = true
                         target.object = "{target}" stream.dont-remix = true }}
    }}
  }}
]
'''


def running():
    try:
        pid = int(PIDFILE.read_text())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def stop():
    pid = running()
    if pid:
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            time.sleep(0.1)
            if not running():
                break
    PIDFILE.unlink(missing_ok=True)


_node = {'pid': None, 'id': None}


def node_id():
    """the equaliser's PipeWire node; looked up once per equaliser process (pw-dump is ~290 KB
    of JSON, and a slider move asks for it every step)"""
    pid = PIDFILE.read_text().strip() if PIDFILE.exists() else None
    if pid and _node['pid'] == pid and _node['id'] is not None:
        return _node['id']
    for o in json.loads(run('pw-dump', timeout=5) or '[]'):
        p = (o.get('info') or {}).get('props') or {}
        if o.get('type') == 'PipeWire:Interface:Node' and p.get('node.name') == NODE:
            _node.update(pid=pid, id=o['id'])
            return o['id']
    return None


def start(target):
    """(re)start the equaliser in front of this output and make it the default"""
    stop()
    CFG.parent.mkdir(parents=True, exist_ok=True)
    CFG.write_text(config(target, gains_for(target)))
    p = subprocess.Popen(['pipewire', '-c', str(CFG)], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    PIDFILE.write_text(str(p.pid))
    for _ in range(40):                    # the node shows up within a second
        time.sleep(0.1)
        if NODE in run('pactl', 'list', 'short', 'sinks') and node_id() is not None:
            run('pactl', 'set-default-sink', NODE)
            return True
    return False


def set_gains(target, gains, live=True):
    """remember the gains for this device and, when the equaliser runs, apply them now"""
    s = settings()
    s['gains'][target] = [round(float(g), 1) for g in gains]
    update_conf('eq', gains=s['gains'])
    if live and running():
        params = ' '.join(f'"eq_{i}:Gain" {g:.2f}' for i, g in enumerate(gains))
        for _try in range(2):
            nid = node_id()
            if nid is None:
                break
            r = subprocess.run(['pw-cli', 'set-param', str(nid), 'Props', f'{{ params = [ {params} ] }}'],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and 'Error' not in r.stdout + r.stderr:
                break
            _node['id'] = None              # PipeWire restarted: look the node up again
        CFG.write_text(config(target, gains))


def turn(on, target=None):
    """the switch: on in front of target (or the remembered one); off back to that device"""
    s = settings()
    target = target or s['target'] or run('pactl', 'get-default-sink').strip()
    if target == NODE:
        target = s['target']
    update_conf('eq', on=bool(on), target=target)
    if on:
        return start(target)
    stop()
    if target:
        run('pactl', 'set-default-sink', target)
    return True


def retarget(target):
    """another output chosen while the equaliser is on: follow it"""
    update_conf('eq', target=target)
    if settings()['on']:
        return start(target)
    run('pactl', 'set-default-sink', target)
    return True


def restore():
    """at login (keyd): start it again when it was on"""
    s = settings()
    if s['on'] and s['target'] and not running():
        start(s['target'])
