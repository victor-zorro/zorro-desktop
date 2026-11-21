"""A whole transfer between two made-up devices: fetch, check, put in place."""
import json
import os
import stat

from harness import HOST, Case, wait_for

KEY = b'-----BEGIN MADE-UP TEST KEY-----\nnot a real key\n'
WIFI = [{'name': 'Home: 5G', 'uuid': 'u1', 'ssid': 'Home 5G', 'key_mgmt': 'wpa-psk',
         'psk': 'pa:ss\\word 1', 'hidden': False},
        {'name': 'Cafe', 'uuid': 'u2', 'ssid': 'Cafe', 'key_mgmt': '', 'psk': '', 'hidden': True}]
PEOPLE = [{'name': 'zt-me', 'full': 'Me', 'groups': ['sudo', 'video'], 'me': True},
          {'name': 'zt-anna', 'full': 'Anna', 'groups': ['sudo'], 'me': False}]


def mode(p):
    return stat.S_IMODE(p.stat().st_mode)


class FullTransfer(Case):
    sender_cfg = {'people': PEOPLE}

    def fill(self):
        self.big = os.urandom(1_500_000)
        self.old.write('Docs/a.txt', 'new text')
        self.old.write('Docs/sub/big.bin', self.big)
        self.old.write('Docs/run.sh', '#!/bin/sh\n', 0o755)
        self.old.write('Docs/shared.txt', 'x', 0o666)
        self.old.write('.ssh/id_test', KEY, 0o600)
        self.old.write('.ssh/id_test.pub', 'made-up public key', 0o644)
        self.old.nm.write_text(json.dumps(WIFI))
        self.new.write('Docs/a.txt', 'old text')
        self.new.write('Docs/mine.txt', 'stays')
        leftover = self.new.stage / '0123456789abcdef' / '.ssh'
        leftover.mkdir(parents=True)
        (leftover / 'id_old').write_text('left by an abandoned transfer')

    def test_fetch_check_and_put_in_place(self):
        self.fill()
        sender = self.old.send()
        r = self.get('files:Docs,logins,accounts')
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.new.read('receiver.json')
        self.assertEqual(st['status'], 'received')
        self.assertFalse((self.new.stage / '0123456789abcdef').exists(), 'old staging folder kept')
        self.check_stage(st['session'])

        r = self.new.run('apply', text='secret\nsecret\n')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('sudo', r.stdout, 'the new account is shown with its groups')
        self.check_files()
        self.check_wifi()
        asked = json.loads(self.new.helper_log.read_text())
        self.assertEqual(asked['passwords'], {'zt-anna': 'secret'})
        self.assertEqual([a['name'] for a in asked['accounts']], ['zt-me', 'zt-anna'])
        st = self.new.read('receiver.json')
        self.assertEqual((st['status'], st['kept']), ('applied', 0))
        self.assertFalse((self.new.stage / st['session']).exists())
        self.assertEqual(self.old.read('sender.json')['sessions'][st['session']]['status'], 'done')

        self.assertTrue((self.old.state_dir / 'generated/wifi.json').exists())
        sender.terminate()
        sender.wait(10)
        self.assertEqual(self.tree(self.old.state_dir / 'generated'), [], 'passwords left lying')
        self.assertEqual(self.old.read('sender.json')['status'], 'stopped')

    def check_stage(self, session):
        """what waits to be put in place is for this user only"""
        stage = self.new.stage / session
        self.assertEqual((stage / '.ssh/id_test').read_bytes(), KEY)
        for p in [self.new.stage, stage, *stage.rglob('*')]:
            self.assertEqual(mode(p), 0o700 if p.is_dir() else 0o600, p)
        self.assertEqual(mode(self.new.state_dir / 'receiver.json'), 0o600)

    def check_files(self):
        home = self.new.home
        self.assertEqual((home / 'Docs/a.txt').read_text(), 'new text')
        self.assertEqual((home / 'Docs/a.txt.before-transfer').read_text(), 'old text')
        self.assertEqual((home / 'Docs/mine.txt').read_text(), 'stays')
        self.assertEqual((home / 'Docs/sub/big.bin').read_bytes(), self.big)
        self.assertEqual(mode(home / 'Docs/run.sh'), 0o755)
        self.assertEqual(mode(home / 'Docs/shared.txt'), 0o664, 'writable by everyone')
        self.assertEqual((home / '.ssh/id_test').read_bytes(), KEY)
        self.assertEqual(mode(home / '.ssh/id_test'), 0o600)
        self.assertEqual(mode(home / '.ssh'), 0o700)
        self.assertEqual(mode(home / '.ssh/id_test.pub') & 0o077, 0)

    def check_wifi(self):
        nets = {n['name']: n for n in json.loads(self.new.nm.read_text())}
        self.assertEqual(nets['Home: 5G']['psk'], 'pa:ss\\word 1')
        self.assertEqual(nets['Home: 5G']['ssid'], 'Home 5G')
        self.assertTrue(nets['Cafe']['hidden'])
        self.assertNotIn('pa:ss', (self.new.root / 'nm.json.log').read_text(),
                         'the Wi-Fi password was on a command line')


class BySelf(Case):
    """'put in place by itself': waits for apps to be closed, but not for ever"""

    def start(self, **cfg):
        self.new.cfg.update(cfg)
        self.old.write('Docs/a.txt', 'text')
        self.old.send()
        r = self.new.run('get', HOST, '--code', self.old.code())
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.new.read('receiver.json')
        (self.new.state_dir / 'receiver.json').write_text(json.dumps(dict(st, auto=True)))
        (self.new.root / 'running').write_text('firefox\n')
        return self.new.start('continue', '--groups', 'files:Docs')

    def test_goes_on_when_the_app_is_closed(self):
        p = self.start()
        wait_for(lambda: self.new.read('receiver.json').get('status') == 'waiting for apps',
                 what='the wait for apps')
        self.assertEqual(self.new.read('receiver.json')['error'], 'firefox')
        self.assertFalse((self.new.home / 'Docs/a.txt').exists())
        (self.new.root / 'running').write_text('')
        self.assertEqual(p.wait(15), 0)
        self.assertEqual(self.new.read('receiver.json')['status'], 'applied')
        self.assertEqual((self.new.home / 'Docs/a.txt').read_text(), 'text')

    def test_the_wait_has_an_end(self):
        p = self.start(APPS_WAIT=1)
        self.assertEqual(p.wait(15), 1)
        st = self.new.read('receiver.json')
        self.assertEqual((st['status'], st['error']), ('apps open', 'firefox'))
