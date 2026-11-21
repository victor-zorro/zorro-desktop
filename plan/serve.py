#!/usr/bin/python3
"""The build plan page (index.html), served from the laptop for any screen on the
home network or NetBird: http://<laptop>:8099/

Answers and reactions are kept in ~/.local/state/zorro-plan/answers.json (not in the
repo), where Claude reads them. Only private addresses (home network, NetBird,
this laptop) may open it.

  plan/serve.py            run in the foreground
  systemd-run --user --unit zorro-plan plan/serve.py     run in the background
"""
import ipaddress
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.environ.get('ZORRO_PLAN_PORT', '8099'))
HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local' / 'state')) / 'zorro-plan'
ANSWERS = STATE / 'answers.json'
ID = re.compile(r'[a-z0-9-]{1,40}')
LOCK = threading.Lock()
FILES = {'/': ('index.html', 'text/html'), '/index.html': ('index.html', 'text/html'),
         '/style.css': ('style.css', 'text/css'), '/page.js': ('page.js', 'text/javascript')}


def read():
    try:
        return json.loads(ANSWERS.read_text())
    except (OSError, ValueError):
        return {}


def private(addr):
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    ip = getattr(ip, 'ipv4_mapped', None) or ip
    return ip.is_private or ip.is_loopback or ip in ipaddress.ip_network('100.64.0.0/10')


class Page(BaseHTTPRequestHandler):
    def send(self, code, body, kind='application/json'):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', kind + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def allowed(self):
        if private(self.client_address[0]):
            return True
        self.send(403, 'only for the home network / NetBird', 'text/plain')
        return False

    def do_GET(self):
        if not self.allowed():
            return
        if self.path in FILES:
            name, kind = FILES[self.path]
            self.send(200, (HERE / name).read_bytes(), kind)
        elif self.path == '/api/answers':
            with LOCK:
                self.send(200, json.dumps(read()))
        else:
            self.send(404, 'not found', 'text/plain')

    def do_POST(self):
        if not self.allowed():
            return
        m = re.fullmatch(r'/api/answers/(.+)', self.path)
        if not m or not ID.fullmatch(m.group(1)):
            return self.send(404, 'not found', 'text/plain')
        n = int(self.headers.get('Content-Length') or 0)
        if not 0 < n <= 20000:
            return self.send(400, 'too long', 'text/plain')
        try:
            v = json.loads(self.rfile.read(n))
            entry = {'pick': [str(x)[:200] for x in v.get('pick', [])][:20],
                     'note': str(v.get('note', ''))[:10000]}
        except (ValueError, AttributeError, TypeError):
            return self.send(400, 'not JSON', 'text/plain')
        from datetime import datetime
        entry['at'] = datetime.now().isoformat(timespec='seconds')
        with LOCK:
            data = read()
            data[m.group(1)] = entry
            STATE.mkdir(parents=True, exist_ok=True)
            tmp = ANSWERS.with_suffix('.tmp')
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
            tmp.replace(ANSWERS)
        self.send(200, '{"ok": true}')

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    print(f'zorro-plan: http://0.0.0.0:{PORT}/', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), Page).serve_forever()
