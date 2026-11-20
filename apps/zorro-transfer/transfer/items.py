"""What Transfer can take along: groups of paths in your home folder.

Symbolic links are left out: most of ~/.config links into the zorro-desktop repo, which the
new device gets from its own setup (bootstrap.sh): keybinds, kitty, rofi, Openbox. Only real
files go, and only the choices: what Settings builds from them (compositor, terminal font,
GTK colours, text size, icons) is rebuilt on the new device after "Put in place".

Special paths in a group:
  sys:/etc/…   a system file; travels as system/etc/…, never put into the home folder: the
               step after "Put in place" installs it (with a password)
  gen:wifi     made on the fly: the saved Wi-Fi networks with their passwords (nmcli), as
               generated/wifi.json; the new device adds them to NetworkManager
  gen:accounts made on the fly: the people's accounts (name, full name, groups; no passwords),
               as generated/accounts.json; the new device makes them (with a password)
  a glob       '.local/share/firefox-*': every match
Caches are skipped in the logins and apps groups (they rebuild themselves)."""
import grp
import json
import os
import pwd
import subprocess
from pathlib import Path

HOME = Path.home()
GEN = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'zorro-transfer' / 'generated'

# id -> (title, about, paths relative to home; a folder means everything in it)
GROUPS = {
    'installers': ('Installers', 'The big downloads in ~/Installers (Unreal, DaVinci…): the new '
                   'device installs them without downloading', ['Installers']),
    'desktop': ('Desktop and launcher', 'Dialer layout, slices and usage; all Zorro Settings '
                'choices (text, colours, icons, windows, power, keys, sound); info circle, '
                'wallpaper and login look; languages; default apps; where windows open',
                ['.config/zorro-dial', '.config/zorro-orb', '.config/zorro-thinkpad',
                 '.config/zorro-wall', '.config/zorro-winpos', '.config/zorro-fx',
                 '.config/zorro-music', '.config/zorro-desktop', '.config/zorro-search/config.json',
                 '.local/state/zorro-dial', '.local/state/zorro-winpos',
                 '.config/mimeapps.list', '.config/user-dirs.dirs', '.config/autostart',
                 '.config/dconf/user', '.config/Thunar', '.config/ristretto',
                 'sys:/etc/zorro-dm/look.json']),
    'logins': ('Logins and keys', 'Firefox and the web apps (Google, WhatsApp, Instagram…) with '
               'their logins and saved passwords; SSH keys; the keyring (opens with your old '
               'password); Wi-Fi networks; Google Drive accounts; GitHub login',
               ['.config/mozilla', '.mozilla', '.local/share/firefox-*', '.ssh',
                '.local/share/keyrings', '.config/rclone', '.config/zorro-drive', '.config/gh',
                'gen:wifi']),
    'apps': ('Apps\' settings and data', 'Obsidian (vault list, settings), Claude, LocalSend, '
             'Blender, Godot, darktable, Scribus, MQTTX connections, mpv. Signal is not copied: '
             'link the new device to your phone instead (a copied Signal stops working)',
             ['.config/obsidian', '.config/Claude', '.local/share/org.localsend.localsend_app',
              '.config/blender', '.config/godot', '.config/darktable', '.config/scribus',
              '.config/MQTTX', '.config/mpv']),
    'accounts': ('User accounts', 'You get your full name and groups (admin, printers, video…) '
                 'on the new device; the other people\'s accounts are made there, with a '
                 'password you type there (passwords never travel). Their files are not '
                 'copied: only they can read them', ['gen:accounts']),
}
# processes that must not run on the new device while these groups are put in place (their
# files would be overwritten under them), nor while sending (a half-written copy)
RUNNING = {'logins': ['firefox', 'firefox-esr'],
           'apps': ['obsidian', 'claude', 'localsend_app', 'blender', 'godot', 'darktable',
                    'scribus', 'MQTTX', 'mpv']}
CACHES = {'cache2', 'startupCache', 'Cache', 'Code Cache', 'GPUCache', 'DawnCache',
          'DawnGraphiteCache', 'DawnWebGPUCache', 'GrShaderCache', 'ShaderCache', 'Service Worker',
          'Crashpad', 'crashes', 'minidumps', 'claude-code', 'blob_storage', 'saved-telemetry-pings'}
SKIP_FILES = ('.lock', '.tmp', 'lock', '.parentlock', 'SingletonLock', 'SingletonCookie',
              'SingletonSocket')
# home folders that are not personal files: the repo comes from GitHub, installed programs
# from their installer, Installers is its own group
NOT_FILES = {'zorro-desktop', 'UnrealEngine', 'Installers', 'snap'}
LOOK_HELPER = '/usr/local/libexec/zorro-look-helper'    # installs the login look (password)
ACCOUNTS_HELPER = '/usr/local/libexec/zorro-accounts-helper'   # makes accounts (password)
NO_SHELL = ('/usr/sbin/nologin', '/sbin/nologin', '/bin/false', '/usr/bin/false')


def all_groups():
    """the fixed groups and one per folder in the home folder: {id: (title, about, paths)}"""
    out = dict(GROUPS)
    loose = []
    for p in sorted(HOME.iterdir(), key=lambda p: p.name.lower()):
        if p.name.startswith('.') or p.name in NOT_FILES or p.is_symlink() or os.path.ismount(p):
            continue
        if p.is_dir():
            out[f'files:{p.name}'] = (f'~/{p.name}', 'Personal files', [p.name])
        elif p.is_file():
            loose.append(p.name)
    if loose:
        out['files:*'] = ('Loose files in your home folder', ', '.join(loose[:6]) +
                          ('…' if len(loose) > 6 else ''), loose)
    return out


def files(group):
    """[(path relative to home, size, mtime)] of the real files in a group"""
    groups = all_groups()
    if group not in groups:
        return []
    out = []
    skip_caches = group in ('logins', 'apps')
    for rel in groups[group][2]:
        if rel.startswith('sys:'):
            p = Path(rel[4:])
            if p.is_file() and os.access(p, os.R_OK):
                st = p.stat()
                out.append(('system' + rel[4:], st.st_size, int(st.st_mtime)))
            continue
        if rel.startswith('gen:'):
            p = {'gen:wifi': wifi_export, 'gen:accounts': accounts_export}[rel]()
            if p:
                st = p.stat()
                out.append((f'generated/{p.name}', st.st_size, int(st.st_mtime)))
            continue
        for top in (sorted(HOME.glob(rel)) if '*' in rel else [HOME / rel]):
            if top.is_symlink() or not top.exists() or os.path.ismount(top):
                continue
            if top.is_file():
                st = top.stat()
                out.append((str(top.relative_to(HOME)), st.st_size, int(st.st_mtime)))
                continue
            for d, dirs, names in os.walk(top):
                dirs[:] = sorted(x for x in dirs if not (Path(d) / x).is_symlink()
                                 and not os.path.ismount(Path(d) / x)     # online drives (rclone)
                                 and not (skip_caches and x in CACHES))
                for n in sorted(names):
                    p = Path(d) / n
                    if p.is_symlink() or not p.is_file() or n in SKIP_FILES or n.endswith(SKIP_FILES):
                        continue
                    try:
                        st = p.stat()
                    except OSError:
                        continue
                    out.append((str(p.relative_to(HOME)), st.st_size, int(st.st_mtime)))
    return out


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


def accounts_export():
    """the people's accounts on this device (not system ones): name, full name, groups"""
    people = []
    for u in sorted(pwd.getpwall(), key=lambda u: u.pw_uid):
        if not 1000 <= u.pw_uid < 60000 or u.pw_shell in NO_SHELL:
            continue
        groups = sorted(g.gr_name for g in grp.getgrall() if u.pw_name in g.gr_mem)
        people.append({'name': u.pw_name, 'full': u.pw_gecos.split(',')[0], 'groups': groups,
                       'me': u.pw_uid == os.getuid()})
    return private('accounts.json', json.dumps(people, indent=1)) if people else None


def new_accounts(path):
    """the other people's accounts in a received list that this device does not have yet"""
    try:
        people = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return []
    out = []
    for a in people:
        try:
            pwd.getpwnam(a['name'])
        except KeyError:
            if not a.get('me'):
                out.append(a)
    return out


def accounts_import(path, passwords):
    """you: full name and groups; others: made with the password typed here (passwords:
    {name: password}; without one an account is skipped). Notes for the summary."""
    try:
        people = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return []
    if not Path(ACCOUNTS_HELPER).exists():
        return ['accounts: run the Transfer system install first (sudo apps/zorro-transfer/'
                'install-system.sh)']
    made, skipped, failed, me = [], [], [], ''
    new = {a['name'] for a in new_accounts(path)}
    for a in people:
        if not a.get('me') and a['name'] not in new:
            continue                        # already here: left alone
        pw = '' if a.get('me') else passwords.get(a['name'], '')
        if not a.get('me') and not pw:
            skipped.append(a['name'])
            continue
        data = json.dumps({k: a.get(k) for k in ('name', 'full', 'groups', 'me')})
        try:
            r = subprocess.run(['pkexec', ACCOUNTS_HELPER, 'account', data], input=pw + '\n',
                               capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            r = None
        ok = r is not None and r.returncode == 0
        if a.get('me'):
            me = 'your name and groups set (groups count from the next login)' if ok else \
                 'your groups not set (password cancelled)'
        else:
            (made if ok else failed).append(a['name'])
    notes = [me] if me else []
    if made:
        notes.append('accounts made: ' + ', '.join(made))
    if skipped:
        notes.append('no password, not made: ' + ', '.join(skipped))
    if failed:
        notes.append('not made: ' + ', '.join(failed))
    return notes


def wifi_export():
    """the saved Wi-Fi networks with their passwords, into a private file (0600)"""
    try:
        names = subprocess.run(['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'],
                               capture_output=True, text=True, timeout=10).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return None
    nets = []
    for ln in names:
        name, _, kind = ln.rpartition(':')
        if kind != '802-11-wireless':
            continue
        name = name.replace('\\:', ':')
        try:
            vals = subprocess.run(['nmcli', '-s', '-g', '802-11-wireless.ssid,802-11-wireless-security.key-mgmt,'
                                   '802-11-wireless-security.psk,802-11-wireless.hidden', 'connection', 'show', name],
                                  capture_output=True, text=True, timeout=10).stdout.splitlines()
        except (OSError, subprocess.SubprocessError):
            continue
        if len(vals) >= 4 and vals[0]:
            nets.append({'name': name, 'ssid': vals[0], 'key_mgmt': vals[1], 'psk': vals[2],
                         'hidden': vals[3] == 'yes'})
    return private('wifi.json', json.dumps(nets, indent=1)) if nets else None


def wifi_import(path):
    """add the networks this device does not know yet; the number added"""
    try:
        have = set(subprocess.run(['nmcli', '-t', '-f', 'NAME', 'connection', 'show'], capture_output=True,
                                  text=True, timeout=10).stdout.splitlines())
        nets = json.loads(Path(path).read_text())
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0
    added = 0
    for n in nets:
        if n['name'] in have:
            continue
        cmd = ['nmcli', 'connection', 'add', 'type', 'wifi', 'con-name', n['name'], 'ssid', n['ssid']]
        if n.get('key_mgmt') in ('wpa-psk', 'sae') and n.get('psk'):
            cmd += ['wifi-sec.key-mgmt', n['key_mgmt'], 'wifi-sec.psk', n['psk']]
        elif n.get('key_mgmt'):
            continue                            # enterprise and the like: set up by hand
        if n.get('hidden'):
            cmd += ['802-11-wireless.hidden', 'yes']
        if subprocess.run(cmd, capture_output=True, timeout=20).returncode == 0:
            added += 1
    return added


def running(groups):
    """apps of these groups that run now: their names"""
    want = {p for g in groups for p in RUNNING.get(g, [])}
    seen = set()
    for pid in os.listdir('/proc'):
        if pid.isdigit():
            try:
                comm = Path(f'/proc/{pid}/comm').read_text().strip()
                if comm in want and Path(f'/proc/{pid}').stat().st_uid == os.getuid():
                    seen.add(comm)
            except OSError:
                continue
    return sorted(seen)


def source(rel):
    """where a path of the list lives on this device"""
    if rel.startswith('system/'):
        return Path('/' + rel[len('system/'):])
    if rel.startswith('generated/'):
        return GEN / rel[len('generated/'):]
    return HOME / rel


def safe_rel(rel):
    """a path from the other side: only plain paths inside the home folder"""
    p = Path(rel)
    return not p.is_absolute() and '..' not in p.parts and rel == str(p) and rel not in ('', '.')
