"""Messages: dunst's history"""
# flake8: noqa: F403,F405 - helpers come from base (and earlier parts)
from .base import *


# ---- Messages: dunst's history ----------------------------------------------------------
APP_ICON = {'signal': 'signal-desktop', 'firefox': 'firefox', 'whatsapp': 'zorro-whatsapp',
            'google': 'zorro-google', 'drive': 'folder-remote', 'zorro': 'preferences-desktop',
            'kitty': 'kitty', 'thunderbird': 'lucide:mail', 'mail': 'lucide:mail',
            'calendar': 'lucide:calendar', 'printer': 'lucide:printer', 'cups': 'lucide:printer',
            'networkmanager': 'lucide:network', 'claude': 'claude-desktop'}


# where a message comes from: web apps all notify as "Firefox", so the site in the text decides
SOURCES = [('Signal', 'signal-desktop', ('signal',), ['signal-desktop']),
           ('WhatsApp', 'zorro-whatsapp', ('whatsapp',), [str(HOME / '.local/bin/whatsapp')]),
           ('Instagram', 'zorro-instagram', ('instagram',), [str(HOME / '.local/bin/instagram')]),
           ('Email', 'lucide:mail', ('mail.google', 'gmail', 'thunderbird', 'mail'),
            [str(HOME / '.local/bin/google-apps')]),
           ('LinkedIn', 'zorro-linkedin', ('linkedin',), [str(HOME / '.local/bin/linkedin')])]


def source_of(m):
    text = ' '.join((m['app'], m['summary'], m['body'])).lower()
    app = m['app'].lower()
    for name, icon, keys, cmd in SOURCES:          # the app's own name first, then the text
        if any(k in app for k in keys):
            return name
    for name, icon, keys, cmd in SOURCES:
        if any(k in text for k in keys if len(k) > 4):
            return name
    return m['app']


class Messages(Part):
    """a tree: All, Signal / WhatsApp / Instagram / Email / LinkedIn (always), other apps, Do not disturb, Clear all; a message unfolds into
    Show again / Go to the app / Copy text / Dismiss"""
    key, title = 'messages', 'Messages'
    tree = True

    def fetch(self):
        self.items = []
        try:
            data = json.loads(run('dunstctl', 'history') or '{}').get('data', [[]])[0]
        except ValueError:
            data = []
        try:
            up = float(Path('/proc/uptime').read_text().split()[0])
        except OSError:
            up = 0
        for n in data:
            v = {k: (x.get('data') if isinstance(x, dict) else x) for k, x in n.items()}
            app = (v.get('appname') or '').strip() or 'Message'
            self.items.append({'id': v.get('id'), 'app': app, 'summary': (v.get('summary') or '').strip(),
                               'body': re.sub(r'<[^>]+>', '', v.get('body') or '').strip(),
                               'age': up - (v.get('timestamp') or 0) / 1e6})
        for m in self.items:
            m['src'] = source_of(m)
        self.dnd = run('dunstctl', 'is-paused').strip() == 'true'
        self.ready = True

    def icon_for(self, app):
        low = app.lower()
        return next((i for k, i in APP_ICON.items() if k in low), 'lucide:bell')

    def go_to(self, app):
        """the app's window to the front, or start it (the web apps' launchers do both)"""
        src = next((s for s in SOURCES if s[0] == app), None)
        if src:
            spawn(*src[3])
        elif subprocess.run(['wmctrl', '-x', '-a', app], capture_output=True, timeout=3).returncode != 0:
            spawn('gtk-launch', app.lower())

    def message_node(self, m):
        text = (m['summary'] + ('\n' + m['body'] if m['body'] else '')).strip()
        src = next((s for s in SOURCES if s[0] == m['src']), None)
        return tile(src[1] if src else self.icon_for(m['app']), (m['summary'] or m['app'])[:24],
                    f'{ago(m["age"])} · {m["body"][:60] or m["app"]}',
                    lambda: spawn('dunstctl', 'history-pop', str(m['id'])), id=f'msg:{m["id"]}',
                    kids=lambda: [
                        tile('lucide:bell', 'Show again', 'with its buttons',
                             lambda: spawn('dunstctl', 'history-pop', str(m['id'])), id=f'pop:{m["id"]}'),
                        tile('lucide:app-window', f'Go to {m["src"]}'[:22], '', lambda: self.go_to(m['src']),
                             id=f'go:{m["id"]}'),
                        tile('lucide:copy', 'Copy text', text[:40],
                             lambda: subprocess.run(['xclip', '-selection', 'clipboard'], input=text, text=True,
                                                    timeout=5),
                             id=f'copy:{m["id"]}'),
                        tile('lucide:trash-2', 'Dismiss', 'remove it', lambda: run('dunstctl', 'history-rm', str(m['id'])),
                             id=f'rm:{m["id"]}', keep=True, refresh=True, up=2)])

    def roots(self):
        if not getattr(self, 'ready', False):
            return [tile('lucide:ellipsis', 'Loading…', '', None, id='loading')]
        out = [tile('lucide:bell', 'All', f'{len(self.items)} messages', None, id='all',
                    kids=lambda: [self.message_node(m) for m in self.items])]
        for name, icon, keys, cmd in SOURCES:          # always there, in this order
            n = sum(1 for m in self.items if m['src'] == name)
            out.append(tile(icon, name, f'{n} new' if n else 'nothing new', lambda c=cmd: spawn(*c),
                            id=f'src:{name}', lit=bool(n),
                            kids=(lambda name=name: [self.message_node(m) for m in self.items
                                                     if m['src'] == name]) if n else None))
        known = {s[0] for s in SOURCES}
        others = []
        for m in self.items:
            if m['src'] not in known and m['src'] not in others:
                others.append(m['src'])
        for app in others:
            n = sum(1 for m in self.items if m['src'] == app)
            out.append(tile(self.icon_for(app), app[:16], f'{n} message' + ('s' if n != 1 else ''), None,
                            id=f'app:{app}', kids=lambda app=app: [self.message_node(m) for m in self.items
                                                                   if m['src'] == app]))
        out.append(tile('lucide:bell', 'Do not disturb', 'on' if self.dnd else 'off',
                        lambda: run('dunstctl', 'set-paused', 'toggle'), id='dnd', lit=self.dnd,
                        keep=True, refresh=True))
        # Clear all: the centre of the circle (one click there, nothing to miss in the ring)
        return out

    def rings(self):
        return [self.roots(), [], []]

    def preview(self):
        n = len(getattr(self, 'items', []))
        last = self.items[0]['summary'][:28] if n else 'nothing new'
        return 'MESSAGES', str(n), [last + (' · do not disturb' if getattr(self, 'dnd', False) else '')]

    def centre(self):
        if getattr(self, 'items', []):
            return 'clear all', lambda: (run('dunstctl', 'history-clear'), self.fetch())
        return None
