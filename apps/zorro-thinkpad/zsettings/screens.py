"""the screens: what is connected (xrandr), and putting the second and third screen where
you want them. No GTK here, so it can be tested without a screen."""
import re
import subprocess

from .base import load_conf, run

WHERE = {'right': 'Right of the laptop', 'left': 'Left of the laptop', 'above': 'Above the laptop',
         'below': 'Below the laptop', 'same': 'Same picture', 'off': 'Off'}
SIDE = {'right': '--right-of', 'left': '--left-of', 'above': '--above', 'below': '--below'}
HEAD = re.compile(r'^(\S+) (connected|disconnected)( primary)?(?: (\d+)x(\d+)\+(-?\d+)\+(-?\d+))?'
                  r'(?: (left|right|inverted))?')
MODE_NOW = re.compile(r'^\s+(\d+x\d+)\s.*\*')
MODE = re.compile(r'^\s+(\d+x\d+)\s+(.*)$')


def parse(text):
    """xrandr's listing → [{name, connected, primary, on, size, pos, modes, laptop}]"""
    out = []
    for line in text.splitlines():
        m = HEAD.match(line)
        if m:
            name = m.group(1)
            out.append({'name': name, 'connected': m.group(2) == 'connected', 'primary': bool(m.group(3)),
                        'on': m.group(4) is not None, 'modes': [],
                        'size': f'{m.group(4)}x{m.group(5)}' if m.group(4) else '',
                        'pos': (int(m.group(6)), int(m.group(7))) if m.group(4) else (0, 0),
                        'turned': m.group(8) or 'normal', 'mode': '',
                        'laptop': name.startswith(('eDP', 'LVDS', 'DSI'))})
            continue
        now = MODE_NOW.match(line)
        if now and out:
            out[-1]['mode'] = now.group(1)      # the real mode: a turned screen's size is swapped
        m = MODE.match(line)
        if m and out and m.group(1) not in out[-1]['modes']:
            out[-1]['modes'].append(m.group(1))
    live = [s for s in out if s['connected']]
    if live and not any(s['laptop'] for s in live):
        live[0]['laptop'] = True        # a desktop PC: its first screen is the one the others sit around
    return out


def read():
    return parse(run('xrandr', '--current'))


def connected(screens):
    return [s for s in screens if s['connected']]


def saved():
    conf = load_conf().get('screens')
    return conf if isinstance(conf, dict) else {}


def plan(screens, conf):
    """the xrandr arguments for these screens and choices: {name: {where, mode}}, main"""
    live = connected(screens)
    laptop = next((s for s in live if s['laptop']), None)
    if not laptop:
        return []
    choices = conf.get('layout') if isinstance(conf.get('layout'), dict) else {}
    args, last = [], {}
    others = [s for s in live if s is not laptop]
    laptop_off = choices.get(laptop['name'], {}).get('where') == 'off' and any(
        where_of(s, choices) != 'off' for s in others)
    args += ['--output', laptop['name']] + (['--off'] if laptop_off else mode_args(laptop, choices))
    for s in others:
        where = where_of(s, choices)
        args += ['--output', s['name']]
        if where == 'off':
            args.append('--off')
            continue
        args += mode_args(s, choices)
        if laptop_off:
            args += ['--pos', '0x0'] if not last else ['--right-of', last['any']]
            last['any'] = s['name']
        elif where == 'same':
            args += ['--same-as', laptop['name']]
        else:       # two on the same side: the second goes beyond the first
            args += [SIDE.get(where, '--right-of'), last.get(where, laptop['name'])]
            last[where] = s['name']
    for s in screens:
        if not s['connected'] and s['on']:
            args += ['--output', s['name'], '--off']      # unplugged: free its place
    main = conf.get('main')
    if main in [s['name'] for s in live] and not (laptop_off and main == laptop['name']):
        args += ['--output', main, '--primary']
    return args


def where_of(screen, choices):
    """your choice for this screen; without one it stays as it is (off stays off)"""
    return choices.get(screen['name'], {}).get('where') or ('right' if screen['on'] else 'off')


def mode_args(screen, choices):
    mode = choices.get(screen['name'], {}).get('mode')
    return ['--mode', mode] if mode in screen['modes'] else ['--auto']


def restore_args(screens):
    """the arguments that bring back the picture as it is now (for 'Put it back')"""
    args = []
    for s in connected(screens):
        args += ['--output', s['name']]
        args += ['--mode', s['mode'] or s['size'], '--rotate', s['turned'],
                 '--pos', f'{s["pos"][0]}x{s["pos"][1]}'] if s['on'] else ['--off']
        if s['primary']:
            args.append('--primary')
    return args


def apply(args):
    """run xrandr with these arguments; '' or the error"""
    if not args:
        return ''
    try:
        r = subprocess.run(['xrandr', *args], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as e:
        return str(e)
    return '' if r.returncode == 0 else (r.stderr.strip().splitlines() or ['xrandr failed'])[-1]


def apply_saved():
    """at login, and when a screen is plugged in: the saved arrangement, if there is one"""
    conf = saved()
    return apply(plan(read(), conf)) if conf.get('layout') else ''
