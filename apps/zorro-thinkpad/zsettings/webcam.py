"""webcam picture settings through V4L2 (v4l2-ctl): read, change, save, restore.

Changing a control does not switch the camera on. The camera forgets its settings after a
restart or standby; saved settings are applied again at login (keyd) and after resume."""
import re
import shutil

from .base import load_conf, run, update_conf

DEV = '/dev/video0'
NAMES = {'brightness': 'Brightness', 'contrast': 'Contrast', 'saturation': 'Saturation',
         'hue': 'Hue', 'gamma': 'Gamma', 'sharpness': 'Sharpness',
         'white_balance_automatic': 'White balance auto',
         'white_balance_temperature': 'Temperature', 'power_line_frequency': 'Mains (flicker)',
         'backlight_compensation': 'Backlight compensation', 'auto_exposure': 'Exposure',
         'exposure_time_absolute': 'Exposure time', 'exposure_dynamic_framerate': 'Slower in the dark',
         'zoom_absolute': 'Zoom', 'focus_absolute': 'Focus', 'focus_automatic_continuous': 'Autofocus'}


def available():
    return bool(shutil.which('v4l2-ctl'))


def controls(dev=DEV):
    """[{name, label, type, min, max, step, default, value, inactive, menu: {n: text}}]"""
    out, cur = [], None
    for line in run('v4l2-ctl', '-d', dev, '--list-ctrls-menus').splitlines():
        m = re.match(r'\s*(\w+) 0x[0-9a-f]+ \((\w+)\)\s*:(.*)', line)
        if m:
            name, kind, rest = m.groups()
            vals = dict(re.findall(r'(\w+)=(-?\d+)', rest))
            cur = {'name': name, 'label': NAMES.get(name, name.replace('_', ' ').capitalize()),
                   'type': kind, 'min': int(vals.get('min', 0)), 'max': int(vals.get('max', 1)),
                   'step': int(vals.get('step', 1)), 'default': int(vals.get('default', 0)),
                   'value': int(vals.get('value', 0)), 'inactive': 'inactive' in rest, 'menu': {}}
            out.append(cur)
            continue
        m = re.match(r'\s+(\d+): (.+)', line)
        if m and cur and cur['type'] == 'menu':
            cur['menu'][int(m.group(1))] = m.group(2).strip()
    return out


def set_control(name, value, dev=DEV):
    run('v4l2-ctl', '-d', dev, '-c', f'{name}={int(value)}')


def save(dev=DEV):
    """remember the current picture settings (the camera forgets them)"""
    vals = {c['name']: c['value'] for c in controls(dev) if not c['inactive']}
    update_conf('webcam', saved=vals)
    return vals


def reset(dev=DEV):
    for c in controls(dev):
        set_control(c['name'], c['default'], dev)
    update_conf('webcam', saved={})


def restore(dev=DEV):
    """at login / after resume: the saved settings again (automatic modes first, so manual
    values that depend on them are accepted)"""
    saved = load_conf().get('webcam', {}).get('saved') or {}
    first = [k for k in saved if k in ('white_balance_automatic', 'auto_exposure')]
    for k in first + [k for k in saved if k not in first]:
        set_control(k, saved[k], dev)
