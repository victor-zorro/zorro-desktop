"""What the sender allows: guessing the code, coming back to a session, asking for more
than was first asked for; and when it stops."""
import subprocess
import sys
import time
from unittest import mock

from harness import Case, Peer, wait_for
from transfer import generated, net


class Guessing(Case):
    def setUp(self):
        super().setUp()
        self.old.write('Docs/a.txt', 'text')
        self.peer = Peer(self.port)

    def status(self):
        return self.old.read('sender.json').get('status')

    def test_a_wrong_code_makes_the_next_try_wait(self):
        self.old.cfg['FIRST_WAIT'] = 1.5
        self.old.send()
        self.assertTrue(self.peer.wrong_code())
        wait_for(lambda: self.status() == 'wrong code', what='the wrong code to be noticed')
        t, reply = self.peer.pair(self.old.code())
        self.assertIsNone(t)
        self.assertIn('wait', reply['error'])
        time.sleep(1.6)
        t, reply = self.peer.pair(self.old.code())
        self.assertIsNotNone(t, reply)
        t.close()

    def test_one_pairing_at_a_time(self):
        self.old.send()
        first, hi = self.peer.hello({'op': 'pair'})
        self.assertTrue(hi['ok'])
        t, reply = self.peer.pair(self.old.code())
        self.assertIsNone(t)
        self.assertIn('another device is pairing', reply['error'])
        first.close()

    def test_too_many_wrong_codes_switch_pairing_off(self):
        self.old.cfg.update(FIRST_WAIT=0.01, MAX_FAILS=4)
        sender = self.old.send()
        first = self.old.code()
        for n in range(4):
            wait_for(lambda: self.peer.wrong_code(), what=f'wrong try {n + 1}')
            wait_for(lambda: self.old.read('sender.json').get('fails') == n + 1, what='the count')
        st = self.old.read('sender.json')
        self.assertEqual((st['status'], st['code']), ('locked', ''))
        self.assertIn('Too many wrong codes', st['why'])
        t, reply = self.peer.pair(first)
        self.assertIsNone(t)
        self.assertIn('too many wrong codes', reply['error'])

        (self.old.state_dir / 'sender.unlock').write_text(str(sender.pid))
        wait_for(lambda: self.old.code(), what='a new code')
        self.assertNotEqual(self.old.code(), first)
        t, reply = self.peer.pair(self.old.code())
        self.assertIsNotNone(t, reply)
        t.close()


class Sessions(Case):
    def setUp(self):
        super().setUp()
        self.old.write('Docs/a.txt', 'text')
        self.old.write('Pics/b.txt', 'text')
        self.peer = Peer(self.port)

    def paired(self):
        self.old.send()
        t, s = self.peer.pair(self.old.code())
        self.assertIsNotNone(t, s)
        return t, s

    def test_a_session_is_pinned_to_its_first_groups(self):
        t, _ = self.paired()
        r = self.peer.ask(t, op='manifest', groups=['files:Docs'])
        self.assertEqual([f['path'] for f in r['files']], ['Docs/a.txt'])
        r = self.peer.ask(t, op='manifest', groups=['files:Docs', 'files:Pics'])
        self.assertFalse(r['ok'])
        self.assertFalse(self.peer.ask(t, op='get', path='Pics/b.txt', offset=0)['ok'])
        self.assertTrue(self.peer.ask(t, op='manifest', groups=['files:Docs'])['ok'])
        t.close()

    def test_coming_back_works_until_it_is_done(self):
        t, s = self.paired()
        self.peer.ask(t, op='manifest', groups=['files:Docs'])
        t.close()
        t = self.peer.resume(s['session'], s['secret'])
        self.assertIsNotNone(t)
        self.assertFalse(self.peer.ask(t, op='manifest', groups=['files:Pics'])['ok'], 'pin forgotten')
        self.assertTrue(self.peer.ask(t, op='finished')['ok'])
        t.close()
        self.assertIsNone(self.peer.resume(s['session'], s['secret']))

    def test_an_old_session_cannot_come_back(self):
        self.old.cfg['RETRY_FOR'] = 1
        t, s = self.paired()
        t.close()
        time.sleep(1.3)
        self.assertIsNone(self.peer.resume(s['session'], s['secret']))

    def test_saved_sessions_are_dropped_at_the_next_start(self):
        self.old.cfg['RETRY_FOR'] = 1
        t, s = self.paired()
        t.close()
        self.old.stop()
        time.sleep(1.1)
        self.old.send()
        self.assertEqual(self.old.read('sender.json')['sessions'], {})


def window():
    """a process that looks like a Transfer window to the sender"""
    return subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)',
                             'zorro-transfer-window'])


class Stopping(Case):
    def test_an_old_stop_file_does_not_stop_the_next_sender(self):
        self.old.state_dir.mkdir(parents=True)
        (self.old.state_dir / 'sender.stop').write_text('1')
        sender = self.old.send()
        time.sleep(1.5)
        self.assertIsNone(sender.poll(), 'the sender stopped')
        self.assertFalse((self.old.state_dir / 'sender.stop').exists())
        (self.old.state_dir / 'sender.stop').write_text(str(sender.pid))
        self.assertEqual(sender.wait(10), 0)
        self.assertEqual(self.old.read('sender.json')['status'], 'stopped')

    def test_the_sender_follows_a_reopened_window(self):
        self.old.cfg['IDLE_EXIT'] = 0.5
        first, second = window(), window()
        self.addCleanup(lambda: [p.kill() for p in (first, second)] and [p.wait() for p in (first, second)])
        sender = self.old.send('--gui-pid', str(first.pid))
        (self.old.state_dir / 'window.pid').write_text(str(second.pid))
        first.kill()
        first.wait()
        time.sleep(2.5)
        self.assertIsNone(sender.poll(), 'the sender left although a window shows it')
        second.kill()
        second.wait()
        self.assertEqual(sender.wait(10), 0)


class OldPython(Case):
    def test_said_plainly(self):
        self.old.cfg['old_python'] = True
        r = self.old.run('send', timeout=20)
        self.assertEqual(r.returncode, 1)
        self.assertIn('needs Python 3.13', r.stderr)
        self.assertNotIn('Traceback', r.stderr)
        with mock.patch.object(net.ssl, 'SSLContext', object), self.assertRaises(net.TooOld):
            net.need_psk()


class Wifi(Case):
    def test_only_values_the_editor_takes_as_typed(self):
        ok = {'name': 'a', 'ssid': 'my net', 'key_mgmt': 'wpa-psk', 'psk': 'p:a\\ss'}
        self.assertIn('set 802-11-wireless-security.psk p:a\\ss\n', generated.wifi_script(ok))
        for change in ({'psk': ' edge'}, {'psk': 'two\nlines'}, {'ssid': 'x\nsave'}, {'psk': ''},
                       {'key_mgmt': 'wpa-eap'}, {'name': ''}):
            self.assertIsNone(generated.wifi_script(dict(ok, **change)), change)

    def test_accounts_are_checked(self):
        people = generated.checked([{'name': 'anna', 'full': 'Anna', 'groups': ['sudo', 5, 'x y']},
                                    {'name': 'root; rm', 'groups': []}, 'x', {'name': 'bob'}])
        self.assertEqual(people, [{'name': 'anna', 'full': 'Anna', 'groups': ['sudo'], 'me': False}])
