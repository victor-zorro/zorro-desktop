"""Shared by the tests: private XDG folders, a small repo of its own, a server on a free port."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devs import devices, server  # noqa: E402

GIT = ['git', '-c', 'user.name=test', '-c', 'user.email=test@localhost', '-c', 'commit.gpgsign=false']
CLAUDE = '''# test
## Layout
  - `apps/zorro-dial/` — the Dialer: app launcher around the clock
'''
README = '''# zorro-dial: the Dialer

The launcher.

- **Three rings**: the apps you start most sit on the inner ring.
- Type to search all apps, Enter starts the first match.

## Keys

| Key | Does |
|---|---|
| Super | opens the Dialer |
'''
SPEC = '''# Build spec

The switcher in the top bar: Desktop, System, DEVS, Connect.

## AI decisions

- The AI reads only folders the user chose. Every answer says which engine answered.
'''
FILES = {'CLAUDE.md': CLAUDE, 'apps/zorro-dial/README.md': README, 'plan/SPEC.md': SPEC,
         'plan/index.html': '<!doctype html><title>plan</title>', 'plan/serve.py': 'secret = 1\n',
         'apps/zorro-dial/dial.py': 'x = 1\n', 'tools/ok.sh': 'echo ok\n', 'data.json': '{"a": 1}\n'}


def git(repo, *args):
    subprocess.run(GIT + list(args), cwd=repo, check=True, capture_output=True)


def change(repo, name, text, message='change'):
    """Write a file in the test repo and commit it."""
    file = Path(repo) / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text)
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', message)
    devices.CACHE.clear()


class Case(unittest.TestCase):
    """Every test gets empty data folders and a fresh little repo."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.repo = root / 'repo'
        self.repo.mkdir()
        git(self.repo, 'init', '-q')
        for name, text in FILES.items():
            (self.repo / name).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / name).write_text(text)
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-q', '-m', 'start')
        env = {'XDG_DATA_HOME': str(root / 'data'), 'XDG_STATE_HOME': str(root / 'state'),
               'ZORRO_DEVS_REPO': str(self.repo)}
        old = {name: os.environ.get(name) for name in env}
        os.environ.update(env)
        self.addCleanup(self.restore, old)
        devices.CACHE.clear()
        devices.ANCESTORS.clear()

    def restore(self, old):
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class ServerCase(Case):
    def setUp(self):
        super().setUp()
        self.web = server.make(0, '127.0.0.1')
        self.base = f'http://127.0.0.1:{self.web.server_address[1]}'
        thread = threading.Thread(target=self.web.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.stop, thread)

    def stop(self, thread):
        self.web.shutdown()
        self.web.server_close()
        thread.join(5)

    def call(self, path, body=None, raw=None, kind='application/json'):
        """(status, parsed JSON or text) of a GET, or of a POST when a body is given."""
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        request = urllib.request.Request(self.base + path, data=data, headers={'Content-Type': kind})
        try:
            with urllib.request.urlopen(request, timeout=10) as answer:
                status, text = answer.status, answer.read().decode()
        except urllib.error.HTTPError as err:
            status, text = err.code, err.read().decode()
        try:
            return status, json.loads(text)
        except ValueError:
            return status, text
