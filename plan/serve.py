#!/usr/bin/python3
"""The build plan page (index.html), served from the laptop for any screen on the
home network or NetBird: http://<laptop>:8099/

Answers and reactions are kept in ~/.local/state/zorro-plan/answers.json (not in the
repo), where Claude reads them. Only private addresses (home network, NetBird,
this laptop) may open it.

  plan/serve.py            run in the foreground
  systemd-run --user --unit zorro-plan plan/serve.py     run in the background
"""
import json
import os
import re
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import chat

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'apps' / 'zorro-fx'))
import zorro_net  # noqa: E402  (who may use this server: this device, NetBird, the home network)

PORT = int(os.environ.get('ZORRO_PLAN_PORT', '8099'))
HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local' / 'state')) / 'zorro-plan'
ANSWERS = STATE / 'answers.json'
ID = re.compile(r'[a-z0-9-]{1,40}')
LOCK = threading.Lock()
MAX_ANSWERS = 200               # the page has a few dozen questions; nobody fills the disk
FILES = {'/': ('index.html', 'text/html'), '/index.html': ('index.html', 'text/html'),
         '/style.css': ('style.css', 'text/css'), '/page.js': ('page.js', 'text/javascript'),
         '/nav.js': ('nav.js', 'text/javascript'),
         '/review.json': ('review.json', 'application/json'),
         '/chat.js': ('chat.js', 'text/javascript'),
         '/progress.json': ('progress.json', 'application/json')}


def read():
    try:
        return json.loads(ANSWERS.read_text())
    except (OSError, ValueError):
        return {}


def progress():
    """the steps of the run, with the real clock: when the file last changed, and now"""
    file = HERE / 'progress.json'
    data = json.loads(file.read_text())
    data['updated'] = datetime.fromtimestamp(file.stat().st_mtime).strftime('%H:%M')
    data['now'] = datetime.now().strftime('%H:%M')
    return data


class Page(BaseHTTPRequestHandler):
    timeout = 15                        # a request that dribbles in does not keep a thread

    def send(self, code, body, kind='application/json'):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', kind + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def allowed(self):
        """this device, NetBird or the home network, asking for this device by its own name
        (a website cannot pose as it), and no other website's page behind the request"""
        if zorro_net.trusted(self.client_address[0]) and zorro_net.host_ok(self.headers.get('Host')) \
                and zorro_net.same_site(self.headers):
            return True
        self.send(403, 'only for the home network / NetBird', 'text/plain')
        return False

    def body(self, limit):
        """the JSON object a POST carries, or None (and the refusal is sent)"""
        try:
            n = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            n = -1
        if self.headers.get_content_type() != 'application/json' or not 0 < n <= limit:
            self.send(400, 'expected a JSON body', 'text/plain')
            return None
        try:
            data = json.loads(self.rfile.read(n))
        except (ValueError, RecursionError, OSError):
            data = None
        if not isinstance(data, dict):
            self.send(400, 'not JSON', 'text/plain')
            return None
        return data

    def do_GET(self):
        if not self.allowed():
            return
        if self.path == '/progress.json':
            self.send(200, json.dumps(progress()))
        elif self.path in FILES:
            name, kind = FILES[self.path]
            self.send(200, (HERE / name).read_bytes(), kind)
        elif self.path == '/api/answers':
            with LOCK:
                self.send(200, json.dumps(read()))
        elif self.path.startswith('/api/chat/') and self.path[10:] in chat.BRIEFS:
            self.send(200, json.dumps(chat.load(STATE, self.path[10:])))
        else:
            self.send(404, 'not found', 'text/plain')

    def do_POST(self):
        if not self.allowed():
            return
        if self.path.startswith('/api/chat/'):
            return self.post_chat(self.path[10:])
        m = re.fullmatch(r'/api/answers/(.+)', self.path)
        if not m or not ID.fullmatch(m.group(1)):
            return self.send(404, 'not found', 'text/plain')
        v = self.body(20000)
        if v is None:
            return
        try:
            entry = {'pick': [str(x)[:200] for x in v.get('pick', [])][:20],
                     'note': str(v.get('note', ''))[:10000]}
        except TypeError:
            return self.send(400, 'not JSON', 'text/plain')
        entry['at'] = datetime.now().isoformat(timespec='seconds')
        with LOCK:
            data = read()
            if m.group(1) not in data and len(data) >= MAX_ANSWERS:
                return self.send(400, 'too many answers', 'text/plain')
            data[m.group(1)] = entry
            STATE.mkdir(parents=True, exist_ok=True)
            tmp = ANSWERS.with_suffix('.tmp')
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
            tmp.replace(ANSWERS)
        self.send(200, '{"ok": true}')

    def post_chat(self, topic):
        if topic not in chat.BRIEFS:
            return self.send(404, 'not found', 'text/plain')
        v = self.body(20000)
        if v is None:
            return
        text = str(v.get('text', '')).strip()[:8000]
        if not text:
            return self.send(400, 'empty', 'text/plain')
        notes = str(read().get(f'{topic}-notes', {}).get('note', ''))
        ok = chat.ask(STATE, topic, text, notes)
        self.send(200 if ok else 409, json.dumps({'ok': ok}))

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    print(f'zorro-plan: http://0.0.0.0:{PORT}/', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), Page).serve_forever()
