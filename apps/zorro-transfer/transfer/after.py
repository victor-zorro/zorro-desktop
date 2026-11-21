"""The steps after the files are in place: login look and accounts (one admin password,
zorro-transfer-helper), Wi-Fi networks, and what Settings builds from the choices.
Each step gives notes for the user; a step that fails becomes a note, the others still run."""
import json
import subprocess
from pathlib import Path

from . import generated, items

SETTINGS = Path.home() / '.local/bin/zorro-settings'
ICONS = Path(__file__).resolve().parents[2] / 'zorro-icons' / 'build-icons'
NO_HELPER = ('login look and accounts: first run  sudo ~/zorro-desktop/apps/zorro-transfer/'
             'install-system.sh  then "Put in place" again')


def root_request(stage, answers):
    """what the helper is asked to do: the login look and the accounts, as received; your own
    account joins only the groups you confirmed (my_groups)"""
    req = {'look': None, 'accounts': [], 'passwords': answers.get('passwords') or {},
           'my_groups': [g for g in answers.get('groups') or [] if isinstance(g, str)]}
    try:
        look = json.loads((stage / 'system/etc/zorro-dm/look.json').read_text())
        req['look'] = look if isinstance(look, dict) else None
    except (OSError, ValueError):
        pass
    req['accounts'] = generated.read_accounts(stage / 'generated/accounts.json')
    return req


def root_notes(out):
    """the helper's answer in words"""
    notes = []
    if out.get('look') is not None:
        notes.append('login look saved' if out['look'] else 'login look not saved')
    if out.get('me') is not None:
        notes.append('your name and groups set (groups count from the next login)'
                     if out['me'] else 'your groups not set')
    for key, text in (('made', 'accounts made'), ('skipped', 'no password, not made'),
                      ('failed', 'not made')):
        if out.get(key):
            notes.append(f'{text}: ' + ', '.join(map(str, out[key])))
    return notes


def root_setup(rcv, stage, answers):
    """login look and accounts with one admin password; the notes (also saved).
    answers: {'passwords': {account: password}, 'groups': [the groups you confirmed]}"""
    req = root_request(stage, answers)
    notes = []
    if req['look'] is None and not req['accounts']:
        pass
    elif not Path(items.SETUP_HELPER).exists():
        notes.append(NO_HELPER)
    else:
        try:
            r = subprocess.run(['pkexec', items.SETUP_HELPER, 'setup'], input=json.dumps(req),
                               capture_output=True, text=True, timeout=300)
            out = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else None
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            out = None
        if isinstance(out, dict):
            notes += root_notes(out)
        else:
            notes.append('login look and accounts not set (password cancelled)')
    rcv.save(root_done=True, root_notes=notes)
    return notes


def root_step(rcv, stage, answers):
    if rcv.st.get('root_done'):             # done at the start (put in place by itself)
        return rcv.st.get('root_notes') or []
    return root_setup(rcv, stage, answers)


def wifi_step(_rcv, stage, _answers):
    wifi = stage / 'generated/wifi.json'
    if not wifi.exists():
        return []
    n = generated.wifi_import(wifi)
    return [f'{n} Wi-Fi network{"s" if n != 1 else ""} added' if n
            else 'Wi-Fi networks were known already']


def settings_step(rcv, _stage, _answers):
    """theme, compositor, terminal, GTK colours, text size: rebuilt from the choices"""
    if 'desktop' not in (rcv.st.get('groups') or []) or not SETTINGS.exists():
        return []
    r = subprocess.run([str(SETTINGS), '--apply-windows'], capture_output=True, timeout=120)
    return ['settings applied' if r.returncode == 0 else 'settings: open Zorro Settings once']


def icons_step(rcv, _stage, _answers):
    if 'desktop' not in (rcv.st.get('groups') or []) or not ICONS.exists():
        return []
    subprocess.run([str(ICONS)], capture_output=True, timeout=300)
    return ['icons rebuilt']


STEPS = (('login look and accounts', root_step), ('Wi-Fi networks', wifi_step),
         ('settings', settings_step), ('icons', icons_step))


def steps(rcv, stage, answers):
    notes = []
    for name, step in STEPS:
        try:
            notes += step(rcv, stage, answers)
        except Exception as e:              # one step failing must not stop the others
            notes.append(f'{name}: did not work ({e})')
    return notes
