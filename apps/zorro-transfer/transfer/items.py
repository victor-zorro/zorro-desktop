"""What Transfer can take along: groups of paths in your home folder.

Symbolic links are left out: most of ~/.config links into the zorro-desktop repo, which the
new device gets from its own setup (bootstrap.sh). Only real files go."""
import os
from pathlib import Path

HOME = Path.home()

# id -> (title, about, paths relative to home; a folder means everything in it)
GROUPS = {
    'installers': ('Installers', 'The big downloads in ~/Installers (Unreal, DaVinci…): the new '
                   'device installs them without downloading', ['Installers']),
    'desktop': ('Desktop and launcher', 'Dialer layout and slices, Zorro Settings choices, '
                'info circle, wallpaper and login look, icons, window places',
                ['.config/zorro-dial', '.config/zorro-orb', '.config/zorro-thinkpad',
                 '.config/zorro-wall', '.config/zorro-winpos', '.config/zorro-fx',
                 '.config/zorro-music', '.config/zorro-search/config.json',
                 '.local/state/zorro-dial']),
}


def files(group):
    """[(path relative to home, size, mtime)] of the real files in a group"""
    out = []
    for rel in GROUPS[group][2]:
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
                if p.is_symlink() or not p.is_file():
                    continue
                st = p.stat()
                out.append((str(p.relative_to(HOME)), st.st_size, int(st.st_mtime)))
    return out


def safe_rel(rel):
    """a path from the other side: only plain paths inside the home folder"""
    p = Path(rel)
    return not p.is_absolute() and '..' not in p.parts and rel == str(p) and rel not in ('', '.')
