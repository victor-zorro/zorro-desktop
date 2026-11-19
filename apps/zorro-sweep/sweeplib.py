"""Sweep notes, without the window: vaults, notes and their attachments, moving files,
undo, and the meaning of notes (zorro-search's index). Used by zorro-sweep."""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

from gi.repository import GLib

HERE = Path(os.path.realpath(__file__)).parent
HOME = Path.home()
OBSIDIAN_JSON = HOME / '.config/obsidian/obsidian.json'
STATE_DIR = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'zorro-sweep'
INDEX = Path(os.environ.get('XDG_CACHE_HOME', HOME / '.cache')) / 'zorro-search'
ROUND = 10                      # keep this many, then sort them
IMG = re.compile(r'\.(png|jpe?g|gif|webp|bmp|svg)$', re.I)
GAP = '<span size="4000"> </span>'     # an empty line, made small
LINKS = re.compile(r'!?\[\[([^\]|#^]+)|!?\[[^\]]*\]\(<?([^)>]+)>?\)')
sys.path.insert(0, str(HERE.parent / 'zorro-fx'))


# ---- vaults and notes ----------------------------------------------------------------------
try:                                    # shared helpers (apps/zorro-fx/zorro_util.py)
    from zorro_util import vaults
except ImportError:
    def vaults():
        try:
            vs = json.loads((Path.home() / '.config/obsidian/obsidian.json').read_text()).get('vaults', {}).values()
        except (OSError, ValueError):
            return []
        return [Path(v['path']) for v in vs if os.path.isdir(v.get('path', ''))]


def state_file(vault):
    """where a vault's progress is kept: the Obsidian plugin's data.json when the plugin is in the
    vault (shared with Obsidian on the laptop and the phone), else our own state file"""
    for pid in ('sweep-or-keep', 'zorro-sweep'):      # Sweep or Keep (its first name: zorro-sweep)
        plugin = vault / '.obsidian/plugins' / pid
        if (plugin / 'manifest.json').exists():
            return plugin / 'data.json'
    return STATE_DIR / (re.sub(r'[^\w.-]+', '_', vault.name) + '.json')


def read_state(vault):
    f = state_file(vault)
    try:
        st = json.loads(f.read_text())
    except (OSError, ValueError):
        st = {}
    if 'kept' not in st:                        # first time with the plugin: take the old progress
        try:
            st.update(json.loads((STATE_DIR / (re.sub(r'[^\w.-]+', '_', vault.name) + '.json')).read_text()))
        except (OSError, ValueError):
            pass
    return st


def attach_dir(vault):
    try:
        sub = json.loads((vault / '.obsidian/app.json').read_text()).get('attachmentFolderPath', '')
    except (OSError, ValueError):
        sub = ''
    sub = sub.strip('/') if sub and not sub.startswith('.') else ''
    return vault / sub if sub else vault


def front(text):
    """(front matter dict of simple key: value lines, body)"""
    meta = {}
    if text.startswith('---\n'):
        end = text.find('\n---', 4)
        if end > 0:
            for ln in text[4:end].splitlines():
                k, _, v = ln.partition(':')
                if v:
                    meta[k.strip()] = v.strip()
            text = text[end + 4:].lstrip('\n')
    return meta, text


def refs(text):
    """the file names a note links to or embeds (lower case, no folders)"""
    out = set()
    for a, b in LINKS.findall(text):
        name = a or urllib.parse.unquote(b)
        if '://' in name:
            continue
        out.add(Path(name.strip()).name.lower())
    return out


def when(meta, path):
    for k in ('created', 'date'):
        try:
            return datetime.fromisoformat(meta[k][:16]).timestamp()
        except (KeyError, ValueError):
            pass
    return path.stat().st_mtime


def ago(ts):
    days = (time.time() - ts) / 86400
    if days < 1:
        return 'today'
    if days < 60:
        return f'{int(days)} days ago'
    if days < 730:
        return f'{int(days / 30.4)} months ago'
    return f'{int(days / 365.25)} years ago'


def markup(body, limit=7000):
    """a rough Pango rendering of markdown, enough to recognise a note"""
    out = []
    for ln in body[:limit].splitlines():
        ln = re.sub(r'<[^>]+>', '', ln)
        ln = re.sub(r'!\[\[[^\]]*\]\]|!\[[^\]]*\]\([^)]*\)', '', ln)
        if not ln.strip():
            if out and out[-1] != GAP:
                out.append(GAP)
            continue
        e = GLib.markup_escape_text(ln)
        e = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', e)
        e = re.sub(r'\[\[([^\]]+)\]\]', r'<span foreground="#19e6ff">\1</span>', e)
        e = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<span foreground="#19e6ff">\1</span>', e)
        e = re.sub(r'\*\*(.+?)\*\*|__(.+?)__', lambda m: f'<b>{m[1] or m[2]}</b>', e)
        e = re.sub(r'(?<![\w*])\*(?!\s)(.+?)\*(?!\w)', r'<i>\1</i>', e)
        e = re.sub(r'`([^`]+)`', r'<tt>\1</tt>', e)
        e = re.sub(r'^(\s*)[-*+] \[ \] ', r'\1☐ ', e)
        e = re.sub(r'^(\s*)[-*+] \[[xX]\] ', r'\1☑ ', e)
        e = re.sub(r'^(\s*)[-*+] ', r'\1•  ', e)
        h = re.match(r'^(#{1,6}) (.*)', e)
        if h:
            e = f'<span size="{"x-large" if len(h[1]) == 1 else "large"}" weight="bold">{h[2]}</span>'
        if re.fullmatch(r'\s*(-{3,}|\*{3,})\s*', ln):
            e = '<span foreground="#6f7079">────────</span>'
        out.append(e)
    while out and out[-1] == GAP:
        out.pop()
    text = '\n'.join(out).strip()
    if len(body) > limit:
        text += '\n<span foreground="#6f7079">…</span>'
    return text or '<span foreground="#6f7079">(empty note)</span>'


class Vault:
    """the vault being swept: its notes, its pictures and who uses them"""

    def __init__(self, path):
        self.path = path
        self.state_file = state_file(path)
        st = read_state(path)
        self.kept = set(st.get('kept', []))      # names relative to the vault
        self.stays = set(st.get('stays', []))    # kept and sorted: stays where it is
        # this round's kept notes, sorted once there are ROUND of them (older kept notes, from
        # before rounds existed, make up the first round)
        self.batch = st.get('batch', sorted(self.kept - self.stays))
        # a round the Obsidian plugin is playing in a folder ('Folder/note.md'): not ours, kept aside
        self.batch_elsewhere = [b for b in self.batch if '/' in b]
        self.batch = [b for b in self.batch if '/' not in b]
        self.stats = {'deleted': 0, 'moved': 0, **st.get('stats', {})}
        self.files = {}                          # lower-case name: path, for pictures and pdfs
        self.uses = {}                           # lower-case name: set of notes that link to it
        ages = {}
        for p in self.path.rglob('*'):
            rel = p.relative_to(self.path)
            if rel.parts[0].startswith('.') or not p.is_file():
                continue
            if p.suffix.lower() == '.md':
                text = self.read(p)
                for r in refs(text):
                    self.uses.setdefault(r, set()).add(p)
                if p.parent == self.path:        # a note to scan: its date, from the same read
                    ages[p] = when(front(text[:600])[0], p)
            else:
                self.files.setdefault(p.name.lower(), p)
        self.notes = sorted(self.path.glob('*.md'), key=lambda p: ages[p] if p in ages else self.age(p))

    @staticmethod
    def read(p):
        try:
            return p.read_text(errors='replace')
        except OSError:
            return ''

    def age(self, p):
        return when(front(self.read(p)[:600])[0], p)

    def save(self):
        # entries with a folder in them belong to the Obsidian plugin sweeping that folder: kept as is
        live = {p.name for p in self.path.glob('*.md')}
        ok = lambda k: k in live or '/' in k        # noqa: E731
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        try:                                        # the plugin's other keys stay
            st = json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            st = {}
        st.update({'kept': sorted(k for k in self.kept if ok(k)), 'stays': sorted(k for k in self.stays if ok(k)),
                   'batch': [b for b in self.batch if b in live] + self.batch_elsewhere,
                   'stats': self.stats})
        tmp = self.state_file.with_name(self.state_file.name + '.tmp')
        tmp.write_text(json.dumps(st, indent=2, ensure_ascii=False))
        os.replace(tmp, self.state_file)

    def to_scan(self):
        return [p for p in self.notes if p.exists() and p.name not in self.kept]

    def sorted_count(self):
        return self.stats['moved'] + len(self.stays)

    @staticmethod
    def left_in(path):
        """notes still to scan in a vault, from its saved progress"""
        st = read_state(path)
        done = set(st.get('kept', [])) | set(st.get('stays', []))
        return sum(1 for p in path.glob('*.md') if p.name not in done)

    def attachments(self, note, text):
        return [self.files[r] for r in refs(text) if r in self.files and self.files[r].exists()]

    def only_mine(self, note, f):
        return self.uses.get(f.name.lower(), set()) <= {note}

    def forget(self, note, text):
        for r in refs(text):
            self.uses.get(r, set()).discard(note)

    def learn(self, note, text):
        for r in refs(text):
            self.uses.setdefault(r, set()).add(note)


def free_name(path):
    if not path.exists():
        return path
    for i in range(2, 1000):
        p = path.with_name(f'{path.stem} {i}{path.suffix}')
        if not p.exists():
            return p
    raise OSError(f'no free name for {path}')


def move(src, dst, ops):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    ops.append(('mv', src, dst))


def obsidian_open():
    return subprocess.run(['pgrep', '-x', 'obsidian'], capture_output=True).returncode == 0


def set_vault_path(old, new):
    """Obsidian's vault list: point a vault at a new folder (new=None: take it off the list).
    Only while Obsidian is closed: it writes this file itself."""
    d = json.loads(OBSIDIAN_JSON.read_text())
    for k, v in list(d['vaults'].items()):
        if Path(v['path']) == old:
            if new is None:
                del d['vaults'][k]
            else:
                v['path'] = str(new)
    tmp = OBSIDIAN_JSON.with_suffix('.zorro-tmp')
    tmp.write_text(json.dumps(d))
    os.replace(tmp, OBSIDIAN_JSON)


def undo_ops(ops):
    for op in reversed(ops):
        if op[0] == 'mkdir':
            shutil.rmtree(op[1]) if op[1].is_dir() and not any(op[1].iterdir()) else None
        elif op[0] == 'vaultpath':
            set_vault_path(op[2], op[1])
        elif op[0] == 'mv':
            op[1].parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(op[2]), str(op[1]))
        elif op[0] == 'cp':
            op[1].unlink(missing_ok=True)
        elif op[0] == 'write':
            op[1].write_text(op[2])


# ---- the meaning of notes (the search app's index) -------------------------------------------
class Meaning:
    """note vectors from zorro-search's index: a note is the mean of its pieces, a notebook the
    mean of its notes. Without the index there are simply no suggestions."""

    def __init__(self):
        self.ok = False
        try:
            import numpy as np
            self.np = np
            meta = json.loads((INDEX / 'meta.json').read_text())
            vecs = np.load(INDEX / 'vecs.npy').astype(np.float32)
            if len(meta) != len(vecs):
                return
        except Exception:               # noqa: BLE001 - no index, no numpy: no suggestions
            return
        rows = {}
        for i, m in enumerate(meta):
            rows.setdefault(m['p'], []).append(i)
        self.note = {p: self.unit(vecs[ix].mean(0)) for p, ix in rows.items()}
        self.ok = True

    def unit(self, v):
        n = self.np.linalg.norm(v)
        return v / n if n else v

    def of(self, path):
        return self.note.get(str(path)) if self.ok else None

    def centre(self, folder, flat=False):
        if not self.ok:
            return None
        pre = str(folder) + '/'
        vs = [v for p, v in self.note.items() if p.startswith(pre) and (not flat or '/' not in p[len(pre):])]
        return self.unit(self.np.mean(vs, 0)) if vs else None
