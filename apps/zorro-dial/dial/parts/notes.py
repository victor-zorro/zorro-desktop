"""Notes: the Obsidian vault, as a tree"""
import json
import os
import re
import socket
import threading
import time
from pathlib import Path
from urllib.parse import quote

from .. import config
from .base import HOME, Part, ago, loading, spawn, tile

TAG = re.compile(r'(?:^|\s)#([A-Za-z][\w/-]{1,40})')
MEANING_ROUNDS = 40                     # searches by meaning in a row, while you type
SEARCH_SOCK = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / 'zorro-search.sock'


def ask_search(text, n=30):
    """zorro-search (by meaning): [{path, title, score, snippet, kind}], [] when it does not run"""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect(str(SEARCH_SOCK))
            s.sendall((json.dumps({'q': text, 'n': n, 'kind': 'note'}) + '\n').encode())
            return json.loads(s.makefile().readline() or '[]')
    except (OSError, ValueError):
        return []


HEADING = re.compile(r'^(#{1,3})\s+(.+?)\s*#*\s*$', re.M)


class Notes(Part):
    """a tree: new note, pinned, recent, your folders (notebooks), tags; a note unfolds into
    its headings. Typing searches every note, title and text."""
    key, title = 'notes', 'Notes'

    def vaults(self):
        """every vault Obsidian knows except those unticked in the app (Accounts → Obsidian);
        the one open in Obsidian first"""
        try:
            from zorro_util import vault_entries         # apps/zorro-fx (on the path: parts/base.py)
            vs = vault_entries()
        except ImportError:
            try:
                vs = list(json.loads((HOME / '.config/obsidian/obsidian.json').read_text()).get('vaults', {}).values())
            except (OSError, ValueError):
                vs = []
            vs.sort(key=lambda v: (not v.get('open'), os.path.basename(v.get('path', '')).lower()))
        hide = config.load_conf()['notes_hide_vaults']
        return [Path(v['path']) for v in vs if os.path.isdir(v.get('path', '')) and v['path'] not in hide]

    def fetch(self):
        self.all = self.vaults()
        self.root = self.all[0] if self.all else None      # new notes go here (the open vault)
        self.notes = []                 # (mtime, path), every chosen vault
        self.text = {}                  # path -> text, for search and tags (read once per opening)
        self.pinned = []
        for root in self.all:
            for dp, dns, fns in os.walk(root):
                dns[:] = [d for d in dns if not d.startswith(('.', '_'))]
                for f in fns:
                    if f.endswith('.md'):
                        p = os.path.join(dp, f)
                        try:
                            self.notes.append((os.path.getmtime(p), p))
                        except OSError:
                            pass
            try:
                bm = json.loads((root / '.obsidian/bookmarks.json').read_text()).get('items', [])
                self.pinned += [str(root / b['path']) for b in bm
                                if b.get('type') == 'file' and (root / b['path']).exists()]
            except (OSError, ValueError, KeyError):
                pass
        self.notes.sort(reverse=True)
        for _, p in self.notes[:5000]:
            try:
                with open(p, encoding='utf-8', errors='replace') as fh:
                    self.text[p] = fh.read(200000)
            except OSError:
                pass
        # made once per opening: the Dialer draws 20 times a second and asks for these each time
        self.lower = {p: (os.path.basename(p).lower(), t.lower()) for p, t in self.text.items()}
        self._roots, self._tags, self._heads, self._found = None, None, {}, {}
        self._roots = self.make_roots()     # here in the thread, not in the first frame
        self.ready = True

    def vault_of(self, p):
        return next((v for v in self.all if p.startswith(str(v) + os.sep)), self.root)

    def new_note(self, vault):
        return lambda: spawn('xdg-open', 'obsidian://new?vault=' + quote(vault.name))

    def uri(self, p, heading=None):
        u = 'obsidian://open?path=' + quote(p)
        return u + ('%23' + quote(heading) if heading else '')

    def note_tile(self, p, sub=None):
        v = self.vault_of(p)
        rel = os.path.relpath(p, v)
        where = os.path.dirname(rel) or (v.name if len(self.all) > 1 else 'vault')
        cache = self.__dict__.setdefault('_heads', {})
        if p not in cache:
            cache[p] = [(len(h), txt.strip()) for h, txt in HEADING.findall(self.text.get(p, ''))][:24]
        heads = cache[p]
        t_ = tile('lucide:file-text', os.path.basename(p)[:-3][:26],
                  sub if sub is not None else where,
                  lambda: spawn('xdg-open', self.uri(p)), id=p)
        if heads:
            t_['kids'] = lambda: [tile('lucide:list', ('  ' * (lv - 1) + h)[:26], f'heading {lv}',
                                       lambda h=h: spawn('xdg-open', self.uri(p, h)), id=f'{p}#{h}')
                                  for lv, h in heads]
        return t_

    def folder_node(self, d, name=None):
        notes = [(m, p) for m, p in self.notes if os.path.dirname(p) == str(d)]
        subs = sorted(x for x in d.iterdir() if x.is_dir() and not x.name.startswith(('.', '_'))) \
            if d.is_dir() else []
        count = sum(1 for _, p in self.notes if p.startswith(str(d) + os.sep))
        return tile('lucide:folder', (name or d.name)[:22], f'{count} notes', None, id=f'dir:{d}',
                    kids=lambda: [self.folder_node(x) for x in subs]
                    + [self.note_tile(p, ago(time.time() - m)) for m, p in notes])

    def tags(self):
        if getattr(self, '_tags', None) is not None:
            return self._tags
        count = {}
        for p, txt in self.text.items():
            fm = re.match(r'^---\n(.*?)\n---', txt, re.S)
            found = set(TAG.findall(txt))
            if fm:                      # frontmatter: tags: [a, b] or a list under tags:
                block = re.search(r'^tags:\s*(.*(?:\n\s*-\s*.*)*)', fm.group(1), re.M)
                if block:
                    found |= {x.strip(' -[]"\'') for x in re.split(r'[,\n]', block.group(1)) if x.strip(' -[]"\'')}
            for tg in found:
                count.setdefault(tg.lower(), []).append(p)
        self._tags = sorted(count.items(), key=lambda kv: -len(kv[1]))
        return self._tags

    def roots(self):
        if not self.ready:
            return loading()
        if getattr(self, '_roots', None) is None:
            self._roots = self.make_roots()
        return self._roots

    def make_roots(self):
        if not self.root:
            return [tile('lucide:file-pen', 'Open Obsidian', 'make a vault, e.g. ~/Notes',
                         lambda: spawn('obsidian'), id='open'),
                    tile('lucide:file-text', 'Evernote move', 'in the Zorro app',
                         lambda: spawn('zorro-settings', '--page', 'ob'), id='steps')]
        now = time.time()
        many = len(self.all) > 1
        if many:
            out = [tile('lucide:file-plus', 'New note', 'pick a vault', None, id='new',
                        kids=lambda: [tile('lucide:file-plus', v.name[:22], 'new note here',
                                           self.new_note(v), id=f'new:{v}') for v in self.all])]
        else:
            out = [tile('lucide:file-plus', 'New note', self.root.name, self.new_note(self.root), id='new')]
        if self.pinned:
            out.append(tile('lucide:star', 'Pinned', f'{len(self.pinned)} notes', None, id='pinned',
                            kids=lambda: [self.note_tile(p, 'pinned') for p in self.pinned]))
        out.append(tile('lucide:rotate-ccw', 'Recent', f'{len(self.notes)} notes', None, id='recent',
                        kids=lambda: [self.note_tile(p, ago(now - m)) for m, p in self.notes[:24]]))
        if many:                        # a vault each; it unfolds into its folders and notes
            for v in self.all:
                node = self.folder_node(v)
                node['icon'], node['id'] = 'lucide:library', f'vault:{v}'
                out.append(node)
        else:
            folders = sorted(x for x in self.root.iterdir() if x.is_dir() and not x.name.startswith(('.', '_')))
            out += [self.folder_node(d) for d in folders]
        tags = self.tags()
        if tags:
            out.append(tile('lucide:list', 'Tags', f'{len(tags)} tags', None, id='tags',
                            kids=lambda: [tile('lucide:list', f'#{tg}'[:22], f'{len(ps)} notes', None,
                                               id=f'tag:{tg}',
                                               kids=lambda ps=ps: [self.note_tile(p) for p in
                                                                   sorted(ps, key=lambda p: -os.path.getmtime(p))])
                                          for tg, ps in tags[:40]]))
        return out

    def search_tiles(self, text):
        """notes whose title or text has every word (titles first, newest first), then the
        notes zorro-search finds by meaning (they come in a moment later)"""
        words = [w.lower() for w in text.split() if w]
        if not words or not getattr(self, 'root', None):
            return []
        meant = self.meaning(text.strip())
        found = self.__dict__.setdefault('_found', {})
        key = (tuple(words), len(meant))            # the meaning hits come in a moment later
        if key in found:
            return found[key]
        lower = getattr(self, 'lower', {})
        hits = []
        for m, p in self.notes:
            name, body = lower.get(p) or (os.path.basename(p).lower(), '')
            if all(w in name or w in body for w in words):
                hits.append((not all(w in name for w in words), -m, p))
        hits.sort()
        exact = [p for _, _, p in hits[:30]]
        known = {p for _, p in self.notes}
        more = [h for h in meant if h['path'] in known and h['path'] not in exact]
        if len(found) > 64:
            found.clear()
        found[key] = [self.note_tile(p) for p in exact] + \
            [self.note_tile(h['path'], '≈ ' + (h['snippet'] or 'meaning')[:40]) for h in more][:max(0, 27 - len(exact))]
        return found[key]

    def meaning(self, text):
        """what zorro-search found for text; asked in a thread (the Dialer redraws every second)"""
        if not hasattr(self, '_meaning'):
            self._meaning, self._want, self._asking = {}, None, False
        if len(text) < 3 or text in self._meaning:
            return self._meaning.get(text, [])
        self._want = text
        if not self._asking:
            self._asking = True

            def work():
                for _ in range(MEANING_ROUNDS):     # what was typed meanwhile: ask that too
                    t = self._want
                    if not t or t in self._meaning:
                        break
                    self._meaning[t] = ask_search(t)
                self._asking = False
            threading.Thread(target=work, daemon=True).start()
        return []

    def search(self, text):
        found = self.search_tiles(text)
        if found and found[0].get('act'):
            found[0]['act']()

    def preview(self):
        if not getattr(self, 'root', None):
            return 'NOTES', 'Obsidian', ['no vault yet']
        vs = f' in {len(self.all)} vaults' if len(self.all) > 1 else ''
        return 'NOTES', str(len(self.notes)), [f'notes{vs} · centre: new note']

    def centre(self):
        if getattr(self, 'root', None):
            return 'new note', self.new_note(self.root)
        return None
