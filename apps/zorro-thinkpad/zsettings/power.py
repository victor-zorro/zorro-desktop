"""TLP settings and battery state"""
import re
from pathlib import Path
from .base import APPS, sysread


# ---- power: TLP settings (written by the root helper) + battery state ---------------------

HELPER = '/usr/local/libexec/zorro-thinkpad-helper'
LOOK_HELPER = '/usr/local/libexec/zorro-look-helper'     # asks a password: writes /etc
BAT = Path('/sys/class/power_supply/BAT0')
PROFILES = {'low-power': 'Battery saver', 'balanced': 'Balanced', 'performance': 'Performance'}
CHARGE_PRESETS = {'long': ('Long battery life: charge to 80% (starts below 75%)', 75, 80),
                  'full': ('Full: charge to 100% (starts below 95%)', 95, 100)}


def tlp_settings():
    """the TLP values in effect: /etc/tlp.conf, then /etc/tlp.d/*.conf in order"""
    vals = {}
    files = [Path('/etc/tlp.conf')] + sorted(Path('/etc/tlp.d').glob('*.conf'))
    for fn in files:
        try:
            for line in fn.read_text().splitlines():
                m = re.match(r'\s*([A-Z0-9_]+)\s*=\s*"?([^"#]*?)"?\s*$', line)
                if m:
                    vals[m.group(1)] = m.group(2)
        except OSError:
            pass
    return vals


def battery_text():
    if not BAT.exists():
        return 'No battery found'
    cap, status = sysread(BAT / 'capacity', '?'), sysread(BAT / 'status', '?')
    now = sysread(BAT / 'energy_full') or sysread(BAT / 'charge_full')
    new = sysread(BAT / 'energy_full_design') or sysread(BAT / 'charge_full_design')
    health = f'{int(now) * 100 // int(new)}%' if now and new else '?'
    cycles = sysread(BAT / 'cycle_count', '?')
    lo = sysread(BAT / 'charge_control_start_threshold', '?')
    hi = sysread(BAT / 'charge_control_end_threshold', '?')
    return (f'{cap}%  ·  {status.lower()}  ·  health {health} of new  ·  {cycles} charge cycles\n'
            f'Charges when below {lo}%, stops at {hi}%')


def load_script(name):
    """one of our app scripts (apps/NAME/NAME) as a module, or None"""
    import importlib.machinery
    import importlib.util
    p = APPS / name / name
    if not p.exists():
        return None
    mod_name = name.replace('-', '_')
    spec = importlib.util.spec_from_loader(mod_name, importlib.machinery.SourceFileLoader(mod_name, str(p)))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_orb():
    """the zorro-orb script as a module (its item list and config), or None"""
    import importlib.machinery
    import importlib.util
    p = APPS / 'zorro-orb' / 'zorro-orb'
    if not p.exists():
        return None
    spec = importlib.util.spec_from_loader('zorro_orb', importlib.machinery.SourceFileLoader('zorro_orb', str(p)))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
