"""Files Transfer makes on the fly, because what they hold is not a file in the home folder:
the saved Wi-Fi networks (with their passwords) and the list of people's accounts. They are
written for this user only, in the state folder, and removed when sending stops."""
import grp
import json
import os
import pwd
import re
import subprocess
from pathlib import Path

from . import state

GEN = state.STATE / 'generated'
ACCOUNT = re.compile(r'[a-z_][a-z0-9_-]{0,31}')
NO_SHELL = ('/usr/sbin/nologin', '/sbin/nologin', '/bin/false', '/usr/bin/false')
WIFI_FIELDS = ('802-11-wireless.ssid,802-11-wireless-security.key-mgmt,'
               '802-11-wireless-security.psk,802-11-wireless.hidden')


def private(name, data):
    """a generated file only this user can read; the same content keeps the same file
    (and its time), so an interrupted transfer continues"""
    GEN.mkdir(parents=True, exist_ok=True)
    os.chmod(GEN, 0o700)
    p = GEN / name
    if not p.exists() or p.read_text() != data:
        with open(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f:
            f.write(data)
    return p


def remove():
    """the Wi-Fi passwords and the accounts list: not left lying"""
    for name in ('wifi.json', 'accounts.json'):
        (GEN / name).unlink(missing_ok=True)


def people():
    """the people's accounts on this device (not system ones): name, full name, groups"""
    out = []
    for u in sorted(pwd.getpwall(), key=lambda u: u.pw_uid):
        if not 1000 <= u.pw_uid < 60000 or u.pw_shell in NO_SHELL:
            continue
        groups = sorted(g.gr_name for g in grp.getgrall() if u.pw_name in g.gr_mem)
        out.append({'name': u.pw_name, 'full': u.pw_gecos.split(',')[0], 'groups': groups,
                    'me': u.pw_uid == os.getuid()})
    return out


def accounts_export():
    found = people()
    return private('accounts.json', json.dumps(found, indent=1)) if found else None


def known(name):
    try:
        pwd.getpwnam(name)
        return True
    except KeyError:
        return False


def checked(people):
    """a received list of accounts: only the well-formed ones"""
    out = []
    for a in people if isinstance(people, list) else []:
        if not isinstance(a, dict) or not isinstance(a.get('name'), str):
            continue
        groups = a.get('groups')
        if not ACCOUNT.fullmatch(a['name']) or not isinstance(groups, list):
            continue
        out.append({'name': a['name'], 'full': str(a.get('full') or '')[:200],
                    'groups': [g for g in groups if isinstance(g, str) and ACCOUNT.fullmatch(g)],
                    'me': a.get('me') is True})
    return out


def read_accounts(path):
    """a received accounts list, checked; [] when there is none"""
    try:
        return checked(json.loads(Path(path).read_text()))
    except (OSError, ValueError):
        return []


def new_accounts(path):
    """the other people's accounts in a received list that this device does not have yet"""
    return [a for a in read_accounts(path) if not a['me'] and not known(a['name'])]


def nmcli(*args, text=None):
    """nmcli's output lines, values as they are (no escaping); None when it did not run"""
    try:
        r = subprocess.run(['nmcli', '-e', 'no', *args], input=text, capture_output=True,
                           text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.splitlines()


def wifi_export():
    """the saved Wi-Fi networks with their passwords, into a private file (0600)"""
    nets = []
    for ln in nmcli('-t', '-f', 'TYPE,UUID,NAME', 'connection', 'show') or []:
        kind, _, rest = ln.partition(':')
        uuid, _, name = rest.partition(':')
        if kind != '802-11-wireless' or not name:
            continue
        vals = nmcli('-s', '-g', WIFI_FIELDS, 'connection', 'show', uuid) or []
        if len(vals) >= 4 and vals[0]:
            nets.append({'name': name, 'ssid': vals[0], 'key_mgmt': vals[1], 'psk': vals[2],
                         'hidden': vals[3] == 'yes'})
    return private('wifi.json', json.dumps(nets, indent=1)) if nets else None


def plain(value):
    """a value the nmcli editor takes as typed: one line, no blanks at the ends"""
    return isinstance(value, str) and value != '' and value == value.strip() \
        and '\n' not in value and '\r' not in value


def wifi_script(n):
    """what to type into 'nmcli connection edit' for one network; None: set it up by hand"""
    if not isinstance(n, dict) or not plain(n.get('name')) or not plain(n.get('ssid')):
        return None
    lines = [f"set 802-11-wireless.ssid {n['ssid']}"]
    if n.get('key_mgmt') in ('wpa-psk', 'sae'):
        if not plain(n.get('psk')):
            return None
        lines += [f"set 802-11-wireless-security.key-mgmt {n['key_mgmt']}",
                  f"set 802-11-wireless-security.psk {n['psk']}"]
    elif n.get('key_mgmt'):
        return None                         # enterprise and the like
    if n.get('hidden'):
        lines.append('set 802-11-wireless.hidden yes')
    # 'yes' answers the editor's question about connecting at once, when it asks
    return '\n'.join(lines + ['save persistent', 'yes', 'quit']) + '\n'


def wifi_names():
    return set(nmcli('-t', '-f', 'NAME', 'connection', 'show') or [])


def wifi_import(path):
    """add the networks this device does not know yet; the number added.
    The password goes to nmcli on its input, never on its command line (others could see it)."""
    try:
        nets = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return 0
    have, added = wifi_names(), 0
    for n in nets if isinstance(nets, list) else []:
        script = wifi_script(n)
        if not script or n['name'] in have:
            continue
        nmcli('connection', 'edit', 'type', 'wifi', 'con-name', n['name'], text=script)
        if n['name'] in wifi_names():
            added += 1
            have.add(n['name'])
    return added


MAKERS = {'gen:wifi': wifi_export, 'gen:accounts': accounts_export}
