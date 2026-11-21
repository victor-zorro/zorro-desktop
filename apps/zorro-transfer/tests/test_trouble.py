"""Transfers that go wrong on the way: a cut connection, a damaged copy, a sender whose
checksums do not match, a file the sender cannot read."""
import os
import unittest

from harness import HOST, Case, Proxy

SIZE = 2_000_000


class CutConnection(Case):
    def setUp(self):
        super().setUp()
        self.big = os.urandom(SIZE)
        self.old.write('Docs/big.bin', self.big)
        self.old.write('Docs/small.txt', 'small')
        self.old.send()
        self.proxy = Proxy(self.port)
        self.addCleanup(self.proxy.close)
        self.new.port = self.proxy.port
        r = self.new.run('get', HOST, '--code', self.old.code())
        self.assertEqual(r.returncode, 0, r.stderr)

    def placed(self):
        r = self.new.run('apply')
        self.assertEqual(r.returncode, 0, r.stderr)
        return (self.new.home / 'Docs/big.bin').read_bytes()

    def test_goes_on_where_it_stopped(self):
        self.proxy.cut_after, self.proxy.down = SIZE // 2, 0
        r = self.new.run('continue', '--groups', 'files:Docs')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.proxy.cuts, 1)
        self.assertLess(self.proxy.down, SIZE * 1.3, 'the first half was fetched twice')
        self.assertEqual(self.placed(), self.big)

    def test_a_damaged_half_is_fetched_again(self):
        self.new.cfg.update(RETRY_FOR=0.2, RETRY_PAUSE=0.5)
        self.proxy.cut_after = SIZE // 2
        r = self.new.run('continue', '--groups', 'files:Docs')
        self.assertEqual(r.returncode, 1)
        st = self.new.read('receiver.json')
        self.assertEqual(st['status'], 'interrupted')
        part = self.new.stage / st['session'] / 'Docs/big.bin.part'
        half = part.read_bytes()
        self.assertGreater(len(half), SIZE // 4)
        part.write_bytes(b'damaged!' + half[8:])
        r = self.new.run('continue')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.new.read('receiver.json').get('failed'), [])
        self.assertEqual(self.placed(), self.big)

    def test_gives_up_when_nothing_arrives(self):
        self.new.cfg.update(RETRY_FOR=1, RETRY_PAUSE=0.2)
        self.old.stop()
        r = self.new.run('continue', '--groups', 'files:Docs', timeout=20)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.new.read('receiver.json')['status'], 'interrupted')

    def test_continue_when_everything_is_here(self):
        self.assertEqual(self.new.run('continue', '--groups', 'files:Docs').returncode, 0)
        self.old.stop()
        self.assertEqual(self.new.run('continue', timeout=20).returncode, 0)
        self.assertEqual(self.new.read('receiver.json')['status'], 'received')
        self.assertEqual(self.placed(), self.big)


class WrongChecksums(Case):
    sender_cfg = {'bad_big': ['Docs/bad.bin'], 'bad_small': {'flaky': 1}}

    def test_refetched_then_noted(self):
        good = os.urandom(700_000)
        self.old.write('Docs/bad.bin', os.urandom(700_000))
        self.old.write('Docs/good.bin', good)
        self.old.write('Docs/flaky.txt', 'flaky')
        self.old.write('Docs/plain.txt', 'plain')
        self.old.send()
        r = self.get('files:Docs')
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.new.read('receiver.json')
        self.assertEqual(len(st['failed']), 1)
        self.assertIn('Docs/bad.bin', st['failed'][0])
        r = self.new.run('apply')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('1 file not received', r.stdout)
        docs = self.new.home / 'Docs'
        self.assertEqual(self.tree(docs), ['flaky.txt', 'good.bin', 'plain.txt'])
        self.assertEqual((docs / 'flaky.txt').read_text(), 'flaky')
        self.assertEqual((docs / 'good.bin').read_bytes(), good)


@unittest.skipIf(os.geteuid() == 0, 'root can read every file')
class UnreadableFile(Case):
    def test_skipped_and_the_transfer_ends(self):
        self.old.write('Docs/a.txt', 'a')
        self.old.write('Docs/locked.txt', 'small', 0o000)
        self.old.write('Docs/locked.bin', os.urandom(600_000), 0o000)
        self.old.write('Docs/z.txt', 'z')
        self.old.send()
        r = self.get('files:Docs', timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.new.read('receiver.json')
        self.assertEqual(st['status'], 'received')
        self.assertEqual(sorted(line.split(':')[0] for line in st['failed']),
                         ['Docs/locked.bin', 'Docs/locked.txt'])
        self.new.run('apply')
        self.assertEqual(self.tree(self.new.home / 'Docs'), ['a.txt', 'z.txt'])
