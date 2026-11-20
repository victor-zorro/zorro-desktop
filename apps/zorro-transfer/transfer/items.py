"""What Transfer can take along: groups of paths in your home folder.

Symbolic links are left out: most of ~/.config links into the zorro-desktop repo, which the
new device gets from its own setup (bootstrap.sh): keybinds, kitty, rofi, Openbox. Only real
files go, and only the choices: what Settings builds from them (compositor, terminal font,
GTK colours, text size, icons) is rebuilt on the new device after "Put in place".
A path 'sys:/etc/…' is a system file; it travels as system/etc/… and is never put into the
home folder: the step after "Put in place" installs it (with a password)."""
import os
from pathlib import Path

HOME = Path.home()

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
}

LOOK_HELPER = '/usr/local/libexec/zorro-look-helper'    # installs the login look (password)


def files(group):
    """[(path relative to home, size, mtime)] of the real files in a group"""
    out = []
    for rel in GROUPS[group][2]:
        if rel.startswith('sys:'):
            p = Path(rel[4:])
            if p.is_file() and os.access(p, os.R_OK):
                st = p.stat()
                out.append(('system' + rel[4:], st.st_size, int(st.st_mtime)))
            continue
        top = HOME / rel
        if top.is_symlink() or not top.exists():
            continue
        if top.is_file():
            st = top.stat()
            out.append((rel, st.st_size, int(st.st_mtime)))
            continue
        for d, dirs, names in os.walk(top):
            dirs[:] = sorted(x for x in dirs if not (Path(d) / x).is_symlink())
            for n in sorted(names):
                p = Path(d) / n
                if p.is_symlink() or not p.is_file() or n.endswith(('.lock', '.tmp')):
                    continue
                st = p.stat()
                out.append((str(p.relative_to(HOME)), st.st_size, int(st.st_mtime)))
    return out


def source(rel):
    """where a path of the list lives on this device"""
    return Path('/' + rel[len('system/'):]) if rel.startswith('system/') else HOME / rel


def safe_rel(rel):
    """a path from the other side: only plain paths inside the home folder"""
    p = Path(rel)
    return not p.is_absolute() and '..' not in p.parts and rel == str(p) and rel not in ('', '.')
