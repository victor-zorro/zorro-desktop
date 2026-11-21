"""The web server: the page, the API and the plan page, for private addresses only
(home network, NetBird, this laptop)."""
import ipaddress
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import api, plan

WEB = Path(__file__).resolve().parent / 'web'
TYPES = {'.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript'}
MAX_BODY = 20000
NETBIRD = ipaddress.ip_network('100.64.0.0/10')


def private(addr):
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    ip = getattr(ip, 'ipv4_mapped', None) or ip
    return ip.is_private or ip.is_loopback or ip in NETBIRD


def web_files():
    """URL path -> file, for exactly the files in web/ (nothing else is ever read)."""
    files = {'/': WEB / 'index.html', '/style.css': WEB / 'style.css'}
    for script in sorted((WEB / 'js').glob('*.js')):
        files[f'/js/{script.name}'] = script
    return files


class Page(BaseHTTPRequestHandler):
    files = web_files()

    def send(self, code, body, kind='application/json'):
        if not isinstance(body, (str, bytes)):
            body = json.dumps(body, ensure_ascii=False)
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
        url = urlsplit(self.path)
        if url.path in self.files:
            file = self.files[url.path]
            return self.send(200, file.read_bytes(), TYPES[file.suffix])
        if url.path == '/plan':
            self.send_response(301)
            self.send_header('Location', '/plan/')
            self.send_header('Content-Length', '0')
            return self.end_headers()
        found = plan.file(url.path)
        if found:
            return self.send(200, *found)
        self.send(*api.get(url.path, parse_qs(url.query)))

    def body(self):
        """The JSON body, or None after answering why it is refused."""
        try:
            size = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            size = -1
        if not 0 <= size <= MAX_BODY:
            self.send(400, {'error': 'too long'})
            return None
        if 'json' not in (self.headers.get('Content-Type') or ''):
            self.send(400, {'error': 'send JSON'})
            return None
        try:
            return json.loads(self.rfile.read(size) or b'{}')
        except ValueError:
            self.send(400, {'error': 'not JSON'})
            return None

    def do_POST(self):
        if not self.allowed():
            return
        body = self.body()
        if body is not None:
            self.send(*api.post(urlsplit(self.path).path, body))

    def log_message(self, *args):
        pass


def make(port, host='0.0.0.0'):
    server = ThreadingHTTPServer((host, port), Page)
    server.daemon_threads = True
    return server
