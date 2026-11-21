"""First fill, part one: what exists. Features from CLAUDE.md's app list and each
app's README (its bullets and key tables), as done and untested."""
import re

from . import devices, paths, store
from .fill_md import blocks, bullet_title, first_clause, plain, shorten

# The part of its app each folder is: the category when the README has no section.
PART = {
    'zorro-dial': 'Launcher', 'zorro-dm': 'Login screen', 'zorro-face': 'Face unlock',
    'zorro-drive': 'Sync', 'zorro-thinkpad': 'Settings', 'zorro-shot': 'Screenshot',
    'zorro-icons': 'Icons', 'zorro-wall': 'Wallpaper', 'zorro-orb': 'Info circle',
    'zorro-winpos': 'Windows', 'zorro-fx': 'Overlays', 'zorro-music': 'Player',
    'zorro-search': 'Search', 'zorro-sweep': 'Sweep notes', 'zorro-transfer': 'Transfer',
    'zorro-devs': 'Catalogue',
}
LAYOUT_LINE = re.compile(r'\s*- `apps/(zorro-[a-z]+)/` — (.+)')
PER_README = 20
SHORTEST = 25       # a bullet shorter than this says too little to be a feature


def app_of(folder):
    for app, folders in devices.APP_FOLDERS.items():
        if f'apps/{folder}' in folders:
            return app
    return ''


def feature(folder, category, title, text):
    app = app_of(folder)
    fields = {'app': app, 'category': shorten(first_clause(category), 40), 'text': text[:1500], 'status': 'done'}
    return store.new_item('feature', title, fields)


def overview_items(repo):
    """One item per app from the layout list in CLAUDE.md."""
    try:
        lines = (repo / 'CLAUDE.md').read_text().splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        found = LAYOUT_LINE.match(line)
        if found and found.group(1) in PART:
            folder, text = found.group(1), plain(found.group(2))
            out.append(feature(folder, PART[folder], first_clause(text), text))
    return out


def row_text(cells, most=9):
    cells = [plain(c) for c in cells if c.strip()][:most]
    return ': '.join([cells[0], ', '.join(cells[1:])]) if len(cells) > 1 else ''


def named(folder, title):
    """A one-word title says too little: put the part of the app in front."""
    return title if ' ' in title else f'{PART[folder]}: {title}'


def readme_rows(text):
    """(section, title, text) for each bullet and each row of a Key or File table."""
    section, table, bullets, rows = '', '', [], []
    for kind, value in blocks(text):
        if kind == 'h1':
            section = ''
        elif kind == 'heading':
            section = value
        elif kind == 'header':
            table = value[0]
        elif kind == 'bullet' and len(plain(value)) >= SHORTEST:
            bullets.append((section, bullet_title(value), plain(value)))
        elif kind == 'row' and table in ('Key', 'File') and row_text(value):
            rows.append((table, section, shorten(row_text(value, 2)), row_text(value)))
    wanted = ('Key', 'File') if len(bullets) < 3 else ('Key',)
    return bullets + [row[1:] for row in rows if row[0] in wanted]


def readme_items(repo, folder):
    try:
        text = (repo / 'apps' / folder / 'README.md').read_text()
    except OSError:
        return []
    out = []
    for section, title, sentence in readme_rows(text)[:PER_README]:
        out.append(feature(folder, section or PART[folder], named(folder, title), sentence))
    return out


def items():
    repo = paths.repo()
    out = overview_items(repo)
    for folder in PART:
        out += readme_items(repo, folder)
    return out
