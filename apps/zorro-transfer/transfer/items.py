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
Caches are skipped in the logins and apps groups (they rebuild themselves).

The new device checks every path it is offered against its own copy of these groups
(belongs): a sender cannot slip in a path that the chosen groups do not cover."""
import fnmatch
import os
from pathlib import Path

from . import generated, state

HOME = state.HOME
GEN = generated.GEN

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
RESERVED = {'system', 'generated'}     # how sys: and gen: paths travel: not home folders
NOT_FILES = {'zorro-desktop', 'UnrealEngine', 'Installers', 'snap'} | RESERVED
SETUP_HELPER = '/usr/local/libexec/zorro-transfer-helper'   # login look + accounts (password)
# never sent, never accepted: who may log in to this device is decided here
NEVER = ('.ssh/authorized_keys', '.ssh/authorized_keys2')
# folders with keys and logins: for this user only on the new device (files 0600, or 0700
# when runnable; folders 0700): everything in the logins group and apps' logins
PRIVATE = tuple(r for r in GROUPS['logins'][2] if not r.startswith('gen:')) + (
    '.gnupg', '.config/Claude', '.config/MQTTX')
# what runs by itself at login: listed before it is put in place
STARTERS = ('.config/autostart', '.config/systemd/user', '.config/environment.d',
            '.config/openbox/autostart', '.local/bin', 'bin', '.profile', '.bashrc',
            '.bash_profile', '.bash_login', '.bash_logout', '.zshrc', '.zprofile', '.zshenv',
            '.xprofile', '.xsessionrc', '.xinitrc', '.pam_environment')


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


def entry(rel, p):
    """one line of the list: (path as it travels, size, mtime, mode), None when unreadable"""
    try:
        st = p.stat()
    except OSError:
        return None
    return rel, st.st_size, max(0, int(st.st_mtime)), st.st_mode & 0o777


def walk(top, skip_caches):
    """the real files under a folder of the home folder"""
    for d, dirs, names in os.walk(top):
        dirs[:] = sorted(x for x in dirs if not (Path(d) / x).is_symlink()
                         and not os.path.ismount(Path(d) / x)     # online drives (rclone)
                         and not (skip_caches and x in CACHES))
        for n in sorted(names):
            p = Path(d) / n
            if p.is_symlink() or not p.is_file() or n in SKIP_FILES or n.endswith(SKIP_FILES):
                continue
            if str(p.relative_to(HOME)) not in NEVER:
                yield entry(str(p.relative_to(HOME)), p)


def special(rel):
    """a sys: or gen: path of a group"""
    if rel.startswith('sys:'):
        p = Path(rel[4:])
        return entry('system' + rel[4:], p) if p.is_file() and os.access(p, os.R_OK) else None
    p = generated.MAKERS[rel]()
    return entry(f'generated/{p.name}', p) if p else None


def files(group):
    """[(path relative to home, size, mtime, mode)] of the real files in a group"""
    groups = all_groups()
    if group not in groups:
        return []
    out = []
    skip_caches = group in ('logins', 'apps')
    for rel in groups[group][2]:
        if rel.startswith(('sys:', 'gen:')):
            out.append(special(rel))
            continue
        for top in (sorted(HOME.glob(rel)) if '*' in rel else [HOME / rel]):
            if top.is_symlink() or not top.exists() or os.path.ismount(top):
                continue
            if top.is_file():
                out.append(entry(str(top.relative_to(HOME)), top))
            else:
                out.extend(walk(top, skip_caches))
    return [f for f in out if f]


def under(rel, root):
    """is a path the root itself or inside it? The root may hold a * (one folder name)"""
    parts = Path(rel).parts
    head = '/'.join(parts[:len(Path(root).parts)])
    return fnmatch.fnmatchcase(head, root) if '*' in root else head == root


def roots(group):
    """the paths a group may bring, as this device sees them (its own list, not the sender's)"""
    if group in GROUPS:
        return GROUPS[group][2]
    name = group[len('files:'):] if group.startswith('files:') else ''
    plain = name and '/' not in name and not name.startswith('.') and name not in NOT_FILES
    return [name] if plain else []


def belongs(group, rel):
    """may a path from the other device come along as part of this group?"""
    if not safe_rel(rel) or rel in NEVER:
        return False
    first = Path(rel).parts[0]
    for root in roots(group):
        if root.startswith('sys:'):
            hit = rel == 'system' + root[4:]
        elif root.startswith('gen:'):
            hit = rel == f'generated/{root[4:]}.json'
        elif first in RESERVED:
            hit = False
        elif root == '*':                   # loose files in the home folder
            hit = '/' not in rel and not rel.startswith('.') and rel not in NOT_FILES
        else:
            hit = under(rel, root)
        if hit:
            return True
    return False


def is_private(rel):
    """a path that holds keys or logins: for this user's eyes only"""
    return any(under(rel, root) for root in PRIVATE)


def final_mode(rel, mode):
    """the permissions a received file gets: the sender's, but never setuid, setgid or
    writable by everyone; private paths only for this user (0600, runnable 0700)"""
    if is_private(rel):
        return 0o700 if mode & 0o100 else 0o600
    return (mode & 0o775) | 0o400


def starts_by_itself(rel):
    """a file that runs at login without being asked: autostart, user services, the shell's
    start-up files, programs on the PATH"""
    return any(under(rel, root) for root in STARTERS)


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
    if '\0' in rel or '\n' in rel:
        return False
    return not p.is_absolute() and '..' not in p.parts and rel == str(p) and rel not in ('', '.')
