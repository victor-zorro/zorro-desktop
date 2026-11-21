"""A sender that does not play fair must not get a file outside what was asked for."""
import fcntl
import json
import os

from harness import HOST, Case
from transfer import check, items


def entry(group, path, size=4):
    return {'group': group, 'path': path, 'size': size, 'mtime': 1, 'mode': 0o644}


class SessionIds(Case):
    def refused(self, sid):
        self.old.cfg['session_id'] = sid
        self.old.write('Docs/a.txt', 'text')
        self.old.send()
        before = self.tree(self.root)
        r = self.get('files:Docs', timeout=30)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('session', self.new.read('receiver.json'))
        new = set(self.tree(self.root)) - set(before) - {'new/state'}
        self.assertTrue(all(p.startswith(('new/state/', 'old/state/')) for p in new), new)

    def test_a_path_upwards(self):
        self.refused('../..')

    def test_an_absolute_path(self):
        self.refused(str(self.root / 'new/home'))

    def test_not_hex(self):
        self.refused('0123456789abcdeg')

    def test_a_saved_bad_session_is_not_used(self):
        victim = self.new.home / 'victim'
        self.new.write('victim/keep.txt', 'keep')
        self.new.state_dir.mkdir(parents=True)
        (self.new.state_dir / 'receiver.json').write_text(json.dumps({
            'session': str(victim), 'secret': 'ab' * 32, 'host': HOST, 'status': 'received',
            'groups': ['files:Docs'], 'files': [entry('files:Docs', 'Docs/x')]}))
        for command in ('apply', 'continue'):
            r = self.new.run(command, timeout=20)
            self.assertEqual(r.returncode, 1, command)
            self.assertEqual((victim / 'keep.txt').read_text(), 'keep')


class Manifest(Case):
    sender_cfg = {'extra_files': [entry('files:Docs', '.bashrc'),
                                  entry('logins', '.ssh/authorized_keys'),
                                  entry('files:Docs', 'Docs/../evil.txt'),
                                  entry('files:Docs', '/tmp/evil.txt')]}

    def test_paths_that_were_not_asked_for_are_refused(self):
        self.old.write('Docs/a.txt', 'text')
        self.old.write('.bashrc', 'evil')
        self.old.write('.ssh/authorized_keys', 'evil')
        self.old.write('evil.txt', 'evil')
        self.old.send()
        r = self.get('files:Docs')
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.new.read('receiver.json')
        self.assertEqual([f['path'] for f in self.new.files()], ['Docs/a.txt'])
        self.assertEqual(st['refused'], 4)
        self.assertEqual(self.tree(self.new.stage / st['session']), ['Docs', 'Docs/a.txt'])
        r = self.new.run('apply')
        self.assertIn('4 files refused', r.stdout)
        self.assertEqual(self.tree(self.new.home), ['Docs', 'Docs/a.txt'])

    def test_a_tampered_saved_list_is_checked_again(self):
        self.old.write('Docs/a.txt', 'text')
        self.old.send()
        self.get('files:Docs')
        st = self.new.read('receiver.json')
        stage = self.new.stage / st['session']
        (stage / '.bashrc').write_text('evil')
        files = self.new.files() + [entry('files:Docs', '.bashrc')]
        (self.new.state_dir / 'receiver-files.json').write_text(json.dumps(files))
        self.new.run('apply')
        self.assertFalse((self.new.home / '.bashrc').exists())


class BadShape(Case):
    sender_cfg = {'extra_files': [{'group': 'files:Docs', 'path': 'Docs/x', 'size': 1, 'mode': 'rw'}]}

    def test_a_malformed_list_fails_at_once(self):
        self.old.write('Docs/a.txt', 'text')
        self.old.send()
        r = self.get('files:Docs', timeout=20)
        self.assertEqual(r.returncode, 1)
        st = self.new.read('receiver.json')
        self.assertEqual(st['status'], 'failed')
        self.assertIn('file list', st['error'])


class Links(Case):
    def test_a_folder_behind_a_link_is_left_alone(self):
        repo = self.root / 'repo'
        repo.mkdir()
        (repo / 'theirs.txt').write_text('from the repo')
        (self.new.home / 'Docs').mkdir()
        os.symlink(repo, self.new.home / 'Docs/linked')
        os.symlink(repo / 'theirs.txt', self.new.home / 'Docs/link.txt')
        self.old.write('Docs/linked/x.txt', 'x')
        self.old.write('Docs/linked/theirs.txt', 'changed')
        self.old.write('Docs/link.txt', 'changed')
        self.old.write('Docs/ok.txt', 'ok')
        self.old.send()
        self.assertEqual(self.get('files:Docs').returncode, 0)
        r = self.new.run('apply')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.tree(repo), ['theirs.txt'])
        self.assertEqual((repo / 'theirs.txt').read_text(), 'from the repo')
        self.assertEqual((self.new.home / 'Docs/ok.txt').read_text(), 'ok')
        st = self.new.read('receiver.json')
        self.assertEqual((st['moved'], st['kept']), (1, 3))


class OneAtATime(Case):
    def test_a_second_fetch_is_refused(self):
        self.old.write('Docs/a.txt', 'text')
        self.old.send()
        self.assertEqual(self.new.run('get', HOST, '--code', self.old.code()).returncode, 0)
        before = self.new.read('receiver.json')
        with open(self.new.state_dir / 'receiver.lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)        # as a running fetch holds it
            for command in (['continue', '--groups', 'files:Docs'], ['apply']):
                r = self.new.run(*command, timeout=20)
                self.assertEqual(r.returncode, 1)
                self.assertIn('already running', r.stderr)
            self.assertEqual(self.new.read('receiver.json'), before)
        self.assertEqual(self.new.run('continue', '--groups', 'files:Docs').returncode, 0)


class Rules(Case):
    """the checks themselves, without a transfer"""

    def test_modes(self):
        self.assertEqual(items.final_mode('Docs/a', 0o4777), 0o775)
        self.assertEqual(items.final_mode('Docs/a', 0o2666), 0o664)
        self.assertEqual(items.final_mode('Docs/a', 0o000), 0o400)
        self.assertEqual(items.final_mode('.ssh/id', 0o644), 0o600)
        self.assertEqual(items.final_mode('.local/share/keyrings/x', 0o755), 0o700)

    def test_belongs(self):
        yes = [('files:Docs', 'Docs/a/b'), ('logins', '.ssh/id'), ('files:*', 'notes.txt'),
               ('logins', '.local/share/firefox-web/x'), ('logins', 'generated/wifi.json'),
               ('desktop', 'system/etc/zorro-dm/look.json'), ('accounts', 'generated/accounts.json')]
        no = [('files:Docs', 'Docs2/a'), ('files:Docs', '.ssh/id'), ('files:*', '.bashrc'),
              ('files:*', 'Docs/a'), ('files:.ssh', '.ssh/id'), ('files:zorro-desktop', 'zorro-desktop/x'),
              ('logins', 'system/etc/passwd'), ('files:system', 'system/etc/passwd'),
              ('desktop', 'generated/wifi.json'), ('logins', '.local/share/firefox'),
              ('files:Docs', 'Docs/../x'), ('files:a/b', 'a/b/c'), ('nothing', 'Docs/a')]
        for group, path in yes:
            self.assertTrue(items.belongs(group, path), (group, path))
        for group, path in no:
            self.assertFalse(items.belongs(group, path), (group, path))

    def test_session(self):
        good = {'session': '0123456789abcdef', 'secret': 'ab' * 32}
        self.assertEqual(check.session(good), (good['session'], good['secret']))
        for bad in ({'session': '../..', 'secret': 'ab' * 32}, {'session': '0123456789abcdef'},
                    {'session': '0123456789ABCDEF', 'secret': 'ab' * 32}, [], None,
                    {'session': '0123456789abcdef', 'secret': 'ab' * 31},
                    {'session': '0123456789abcdef\n', 'secret': 'ab' * 32}):
            with self.assertRaises(check.BadPeer):
                check.session(bad)

    def test_offer_and_list_shapes(self):
        for bad in ({}, {'groups': [{'id': 'a'}]}, {'groups': 'x'},
                    {'groups': [{'id': 'a', 'title': 't', 'about': '', 'files': '1', 'bytes': 2}]}):
            with self.assertRaises(check.BadPeer):
                check.offer(bad)
        for bad in (None, [5], [{'group': 'g', 'path': 'p', 'size': -1, 'mtime': 0, 'mode': 0}],
                    [{'group': 'g', 'path': 'p', 'size': 1, 'mtime': 0}]):
            with self.assertRaises(check.BadPeer):
                check.manifest(bad, ['g'])
