"""Messages: the notification history (dunst), one list, newest first."""
import json
import re
import subprocess
from pathlib import Path

from .base import HOME, Part, ago, loading, run, spawn, tile

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
    for name, _icon, keys, _cmd in SOURCES:        # the app's own name first, then the text
        if any(k in app for k in keys):
            return name
    for name, _icon, keys, _cmd in SOURCES:
        if any(k in text for k in keys if len(k) > 4):
            return name
    return m['app']


def icon_for(app):
    low = app.lower()
    return next((i for k, i in APP_ICON.items() if k in low), 'lucide:bell')


def history(text, uptime):
    """dunst's history (its JSON) as messages, newest first"""
    try:
        data = json.loads(text or '{}').get('data', [[]])[0]
    except (ValueError, AttributeError, IndexError, KeyError, TypeError):
        data = []
    out = []
    for n in data if isinstance(data, list) else []:
        if not isinstance(n, dict):
            continue
        v = {k: (x.get('data') if isinstance(x, dict) else x) for k, x in n.items()}
        m = {'id': v.get('id'), 'app': str(v.get('appname') or '').strip() or 'Message',
             'summary': str(v.get('summary') or '').strip(),
             'body': re.sub(r'<[^>]+>', '', str(v.get('body') or '')).strip()}
        try:
            m['age'] = uptime - float(v.get('timestamp') or 0) / 1e6
        except (TypeError, ValueError):
            m['age'] = 0
        m['src'] = source_of(m)
        out.append(m)
    return sorted(out, key=lambda m: m['age'])


def go_to(app):
    """the app's window to the front, or start it (the web apps' launchers do both)"""
    src = next((s for s in SOURCES if s[0] == app), None)
    if src:
        spawn(*src[3])
        return
    try:
        found = subprocess.run(['wmctrl', '-x', '-a', app], capture_output=True, timeout=3).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        found = False
    if not found:
        spawn('gtk-launch', app.lower())


def copy_text(text):
    try:
        subprocess.run(['xclip', '-selection', 'clipboard'], input=text, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


def message_tile(m):
    """a message: click shows it again, right-click dismisses it; it unfolds into its actions"""
    text = (m['summary'] + ('\n' + m['body'] if m['body'] else '')).strip()
    src = next((s for s in SOURCES if s[0] == m['src']), None)
    mid = str(m['id'])

    def kids():
        return [tile('lucide:bell', 'Show again', 'with its buttons',
                     lambda: spawn('dunstctl', 'history-pop', mid), id=f'pop:{mid}'),
                tile('lucide:app-window', f'Go to {m["src"]}'[:22], '', lambda: go_to(m['src']),
                     id=f'go:{mid}'),
                tile('lucide:copy', 'Copy text', text[:40], lambda: copy_text(text), id=f'copy:{mid}'),
                tile('lucide:trash-2', 'Dismiss', 'remove it', lambda: run('dunstctl', 'history-rm', mid),
                     id=f'rm:{mid}', keep=True, refresh=True, up=2)]
    return tile(src[1] if src else icon_for(m['app']), (m['summary'] or m['app'])[:24],
                f'{ago(m["age"])} · {m["body"][:60] or m["app"]}',
                lambda: spawn('dunstctl', 'history-pop', mid), id=f'msg:{mid}', kids=kids,
                label=True, remove=lambda: run('dunstctl', 'history-rm', mid))


class Messages(Part):
    """one list: Do not disturb, then every message, newest first. A message unfolds into
    Show again / Go to the app / Copy text / Dismiss"""
    key, title = 'messages', 'Messages'

    def fetch(self):
        try:
            up = float(Path('/proc/uptime').read_text().split()[0])
        except (OSError, ValueError):
            up = 0
        self.items = history(run('dunstctl', 'history'), up)
        self.dnd = run('dunstctl', 'is-paused').strip() == 'true'
        dnd = tile('lucide:moon', 'Do not disturb', 'on' if self.dnd else 'off',
                   lambda: run('dunstctl', 'set-paused', 'toggle'), id='dnd', lit=self.dnd,
                   label=True, keep=True, refresh=True)
        self.tiles = [dnd] + ([message_tile(m) for m in self.items] or
                              [tile('lucide:bell', 'Nothing new', 'no messages', None, id='none', label=True)])
        self.ready = True

    def roots(self):
        return self.tiles if self.ready else loading()

    def preview(self):
        n = len(self.items)
        last = self.items[0]['summary'][:28] if n else 'nothing new'
        return 'MESSAGES', str(n), [last + (' · do not disturb' if getattr(self, 'dnd', False) else '')]

    def centre(self):
        if self.items:
            return 'clear all', lambda: run('dunstctl', 'history-clear')
        return None
