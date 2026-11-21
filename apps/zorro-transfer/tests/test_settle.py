"""Putting in place and around it: the groups your account joins, files that start by
themselves, logins for your eyes only, old staging folders, one pairing while a transfer
runs, devices with the same name, and a sender without its Send page."""
import fcntl
import importlib.machinery
import importlib.util
import io
import json
import os
import stat
import subprocess
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

from harness import HERE, HOST, Case
from test_sender import window
from transfer import find

ME = [{'name': 'zt-me', 'full': 'Me', 'groups': ['sudo', 'video', 'audio'], 'me': True}]


def mode(p):
    return stat.S_IMODE(p.stat().st_mode)


def load_helper():
    """the root helper as a module (it is a script without .py); it sets PATH: put back"""
    path = os.environ.get('PATH')
    loader = importlib.machinery.SourceFileLoader('zt_helper', str(HERE.parent / 'zorro-transfer-helper'))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader('zt_helper', loader))
    loader.exec_module(module)
    os.environ['PATH'] = path
    return module


class Helper(unittest.TestCase):
    """the root helper adds your account only to the groups the request confirms"""

    def setup(self, req):
        helper, calls = load_helper(), []

        def run(cmd, **_kw):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, b'', b'')
        out = io.StringIO()
        with mock.patch.object(helper.subprocess, 'run', run), \
                mock.patch.dict(os.environ, PKEXEC_UID=str(os.getuid())), \
                mock.patch('sys.stdin', io.StringIO(json.dumps(req))), redirect_stdout(out):
            helper.setup()
        return [c for c in calls if c[0] == 'usermod'], json.loads(out.getvalue())

    def test_only_confirmed_groups(self):
        req = {'look': None, 'accounts': ME, 'passwords': {}, 'my_groups': ['video', 'input']}
        usermod, out = self.setup(req)
        self.assertEqual([c for c in usermod if '-aG' in c][0][2], 'video')
        self.assertTrue(out['me'])

    def test_nothing_confirmed_nothing_added(self):
        usermod, _ = self.setup({'look': None, 'accounts': ME, 'passwords': {}})
        self.assertEqual([c for c in usermod if '-aG' in c], [])


class YourGroups(Case):
    sender_cfg = {'people': ME}
    receiver_cfg = {'groups_here': [['sudo', 'video', 'audio'], ['audio']]}

    def received(self):
        self.old.write('Docs/a.txt', 'a')
        self.old.send()
        self.assertEqual(self.get('accounts,files:Docs').returncode, 0)

    def test_shown_and_powerful_ones_asked(self):
        self.received()
        r = self.new.run('apply', text='n\n')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('joins these groups: sudo, video', r.stdout)
        self.assertEqual(json.loads(self.new.helper_log.read_text())['my_groups'], ['video'])

    def test_a_yes_adds_it(self):
        self.received()
        self.assertEqual(self.new.run('apply', text='y\n').returncode, 0)
        self.assertEqual(json.loads(self.new.helper_log.read_text())['my_groups'], ['sudo', 'video'])


class Starters(Case):
    sender_cfg = {'extra_files': [{'group': 'logins', 'path': '.ssh/authorized_keys', 'size': 4,
                                   'mtime': 1, 'mode': 0o600}]}

    def test_login_keys_never_and_starters_listed(self):
        self.old.write('.ssh/authorized_keys', 'ssh-ed25519 made-up', 0o600)
        self.old.write('.ssh/id_test', 'made-up key', 0o600)
        self.old.write('.config/autostart/thing.desktop', '[Desktop Entry]\nExec=thing\n')
        self.old.write('bin/tool', '#!/bin/sh\n', 0o755)
        self.old.send()
        r = self.get('logins,desktop,files:bin')
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.new.read('receiver.json')
        self.assertEqual(st['refused'], 1)
        self.assertNotIn('.ssh/authorized_keys', [f['path'] for f in self.new.files()])
        self.assertFalse((self.new.stage / st['session'] / '.ssh/authorized_keys').exists())
        r = self.new.run('apply')
        self.assertEqual(r.returncode, 0, r.stderr)
        line = '2 received files start by themselves at login: .config/autostart/thing.desktop, bin/tool'
        self.assertIn(line, r.stdout)
        self.assertIn(line, self.new.read('receiver.json')['notes'])
        self.assertFalse((self.new.home / '.ssh/authorized_keys').exists())
        self.assertTrue((self.new.home / '.ssh/id_test').exists())


class OwnerOnly(Case):
    def test_everything_of_the_logins_group(self):
        self.old.write('.config/zorro-drive/accounts.json', '{}', 0o644)
        self.old.write('.config/zorro-drive/sub/run.sh', '#!/bin/sh\n', 0o755)
        self.old.write('.config/gh/hosts.yml', 'made-up', 0o664)
        (self.new.home / '.config/zorro-drive').mkdir(parents=True)
        os.chmod(self.new.home / '.config/zorro-drive', 0o755)
        self.old.send()
        self.assertEqual(self.get('logins').returncode, 0)
        self.assertEqual(self.new.run('apply').returncode, 0)
        home = self.new.home / '.config'
        self.assertEqual(mode(home / 'zorro-drive/accounts.json'), 0o600)
        self.assertEqual(mode(home / 'zorro-drive/sub/run.sh'), 0o700)
        self.assertEqual(mode(home / 'gh/hosts.yml'), 0o600)
        for folder in ('zorro-drive', 'zorro-drive/sub', 'gh'):
            self.assertEqual(mode(home / folder), 0o700, folder)


class OldStages(Case):
    def test_a_week_old_staging_folder_goes(self):
        week = time.time() - 8 * 24 * 3600
        current = '0123456789abcdef'
        for name, when in (('aaaaaaaaaaaaaaaa', week), ('aaaaaaaaaaaaaaaa.parts', week),
                           ('bbbbbbbbbbbbbbbb', time.time() - 24 * 3600), (current, week)):
            (self.new.stage / name / 'Docs').mkdir(parents=True)
            os.utime(self.new.stage / name, (when, when))
        self.new.state_dir.mkdir(parents=True)
        (self.new.state_dir / 'receiver.json').write_text(json.dumps({
            'session': current, 'secret': 'ab' * 32, 'host': HOST, 'status': 'received',
            'updated': time.time()}))
        self.assertEqual(self.new.run('continue', timeout=20).returncode, 0)
        self.assertEqual(sorted(p.name for p in self.new.stage.iterdir()),
                         [current, 'bbbbbbbbbbbbbbbb'])


class PairingWhileBusy(Case):
    def test_refused_and_the_running_transfer_kept(self):
        self.old.write('Docs/a.txt', 'a')
        self.old.send()
        self.assertEqual(self.get('files:Docs').returncode, 0)
        before = self.new.read('receiver.json')
        stage = self.new.stage / before['session']
        with open(self.new.state_dir / 'receiver.lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)        # as a running fetch holds it
            r = self.new.run('get', HOST, '--code', self.old.code(), timeout=20)
        self.assertEqual(r.returncode, 1)
        self.assertIn('already running', r.stderr)
        self.assertEqual((stage / 'Docs/a.txt').read_text(), 'a')
        self.assertEqual(self.new.read('receiver.json'), before)


class SameName(unittest.TestCase):
    def test_both_are_listed_with_their_addresses(self):
        seen = [{'name': 'laptop', 'host': '192.168.1.5', 'via': 'netbird', 'sending': False},
                {'name': 'laptop', 'host': '192.168.1.5', 'via': 'wifi', 'sending': False},
                {'name': 'laptop', 'host': '192.168.1.66', 'via': 'wifi', 'sending': True}]
        with mock.patch.object(find.state, 'device_name', return_value='this-one'):
            got = find.best(seen)
        self.assertEqual([(f['host'], f['via']) for f in got],
                         [('192.168.1.5', 'wifi'), ('192.168.1.66', 'wifi')])


class NoSendPage(Case):
    sender_cfg = {'IDLE_EXIT': 0.5}

    def test_another_window_does_not_keep_the_sender(self):
        other = window()                    # a Transfer window, but not on the Send page
        self.addCleanup(lambda: other.kill() or other.wait())
        sender = self.old.send('--gui-pid', str(other.pid))
        self.assertEqual(sender.wait(10), 0)
        self.assertIsNone(other.poll())
