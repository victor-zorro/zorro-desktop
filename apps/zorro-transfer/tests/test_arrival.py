"""What arrives: a sender that lies about sizes or sends without end, names that are long or
look like the receiver's own temporary files, a file that cannot be written here, a disk
that breaks in the middle of a file, very many files, and messages nobody can parse."""
import json
import os
import socket
import threading
import time

from harness import HOST, Case, Peer
from transfer import check, fetch, net

DEEP = b'[' * 200_000 + b']' * 200_000


def entry(path, size):
    return {'group': 'files:Docs', 'path': path, 'size': size, 'mtime': 1, 'mode': 0o644}


class LyingSize(Case):
    sender_cfg = {'lie_size': ['Docs/big.bin']}

    def test_a_size_that_is_not_the_listed_one_fails_the_file(self):
        self.old.write('Docs/big.bin', os.urandom(700_000))
        self.old.write('Docs/ok.txt', 'ok')
        self.old.send()
        start = time.monotonic()
        r = self.get('files:Docs', timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(time.monotonic() - start, 30)
        st = self.new.read('receiver.json')
        self.assertEqual(st['failed'], [f'Docs/big.bin: {fetch.CHANGED}'])
        self.assertEqual((self.new.stage / st['session'] / 'Docs/ok.txt').read_text(), 'ok')


class FatBatch(Case):
    sender_cfg = {'fat_batch': True}

    def test_a_batch_bigger_than_allowed_stops_at_once(self):
        for i in range(20):
            self.old.write(f'Docs/{i}.txt', 'small')
        self.old.send()
        r = self.get('files:Docs', timeout=30)
        self.assertEqual(r.returncode, 1)
        st = self.new.read('receiver.json')
        self.assertEqual(st['status'], 'failed')
        self.assertIn('batch', st['error'])


class NoRoom(Case):
    sender_cfg = {'extra_files': [entry('Docs/huge.bin', 4 * 10 ** 12)]}

    def test_said_before_anything_is_fetched(self):
        self.old.write('Docs/a.txt', 'a')
        self.old.send()
        r = self.get('files:Docs', timeout=30)
        self.assertEqual(r.returncode, 1)
        st = self.new.read('receiver.json')
        self.assertEqual(st['status'], 'failed')
        self.assertIn('not enough room', st['error'])
        self.assertFalse((self.new.stage / st['session'] / 'Docs').exists())

    def test_sizes_have_bounds(self):
        with self.assertRaises(check.BadPeer):
            check.manifest([entry('Docs/a', 10 ** 15)], ['files:Docs'])
        many = [entry(f'Docs/{i}', check.MOST_FILE) for i in range(5)]
        with self.assertRaises(check.BadPeer):
            check.manifest(many, ['files:Docs'])
        self.assertEqual(len(check.manifest(many[:4], ['files:Docs'])[0]), 4)


class Names(Case):
    LONG = 'Docs/' + 'n' * 255

    def test_long_names_and_look_alikes_arrive(self):
        big = os.urandom(600_000)
        files = {self.LONG: b'long', 'Docs/X': b'x', 'Docs/X.part': b'part', 'Docs/X.meta': b'meta',
                 'Docs/Y': big, 'Docs/Y.part': b'p', 'Docs/Y.meta': b'm'}
        for rel, data in files.items():
            self.old.write(rel, data)
        self.old.send()
        r = self.get('files:Docs')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.new.read('receiver.json')['failed'], [])
        r = self.new.run('apply')
        self.assertEqual(r.returncode, 0, r.stderr)
        for rel, data in files.items():
            self.assertEqual((self.new.home / rel).read_bytes(), data, rel)

    def test_a_file_that_cannot_be_written_here_does_not_stop_the_rest(self):
        for rel in ('Docs/a.txt', 'Docs/sub/x.txt', 'Docs/z.txt'):
            self.old.write(rel, rel)
        self.old.write('Docs/big.bin', os.urandom(600_000))
        self.old.send()
        r = self.new.run('get', HOST, '--code', self.old.code())
        self.assertEqual(r.returncode, 0, r.stderr)
        stage = self.new.stage / self.new.read('receiver.json')['session']
        (stage / 'Docs/a.txt/inside').mkdir(parents=True)        # a folder where a file goes
        (stage / 'Docs/big.bin/inside').mkdir(parents=True)
        (stage / 'Docs/sub').write_text('a file where a folder goes')
        r = self.new.run('continue', '--groups', 'files:Docs', timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.new.read('receiver.json')
        self.assertEqual(sorted(line.split(':')[0] for line in st['failed']),
                         ['Docs/a.txt', 'Docs/big.bin', 'Docs/sub/x.txt'])
        self.assertEqual((stage / 'Docs/z.txt').read_text(), 'Docs/z.txt')


class ManyFiles(Case):
    def test_the_state_file_stays_small(self):
        for i in range(3000):
            self.old.write(f'Docs/d{i % 30}/note {i}.md', f'note {i}')
        self.old.send()
        r = self.get('files:Docs', timeout=90)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.new.files()), 3000)
        self.assertLess((self.new.state_dir / 'receiver.json').stat().st_size, 8000)
        self.assertEqual(self.new.read('receiver.json')['files_count'], 3000)


class BadDisk(Case):
    sender_cfg = {'eio': ['Docs/bad.bin']}

    def test_a_read_error_in_the_middle_fails_that_file_only(self):
        self.old.write('Docs/bad.bin', os.urandom(3_000_000))
        self.old.write('Docs/ok.txt', 'ok')
        self.old.send()
        start = time.monotonic()
        r = self.get('files:Docs', timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(time.monotonic() - start, 20)
        st = self.new.read('receiver.json')
        self.assertEqual(st['failed'], [f'Docs/bad.bin: {fetch.UNREADABLE}'])
        self.assertEqual((self.new.stage / st['session'] / 'Docs/ok.txt').read_text(), 'ok')


class Batches(Case):
    sender_cfg = {'BATCH_CAP': 5_000_000}

    def test_the_sender_caps_a_batch(self):
        two = os.urandom(2_000_000)
        for i in range(4):
            self.old.write(f'Docs/{i}.bin', two)
        self.old.send()
        peer = Peer(self.port)
        t, _ = peer.pair(self.old.code())
        self.addCleanup(t.close)
        peer.ask(t, op='manifest', groups=['files:Docs'])
        for paths, want in ((['Docs/0.bin'] * 1000, [len(two)] + [-1] * 999),
                            ([f'Docs/{i}.bin' for i in range(4)], [len(two)] * 2 + [-1] * 2)):
            net.send_json(t, {'op': 'batch', 'paths': paths, 'done': 0})
            sizes = net.recv_json(t)['sizes']
            self.assertEqual(sizes, want)
            self.assertEqual(net.recv_exact(t, sum(n for n in sizes if n > 0))[:len(two)], two)
            self.assertEqual(len(net.recv_json(t)['sha256']), len(paths))


class SmallBatches(Case):
    sender_cfg = {'BATCH_CAP': 1_000_000}

    def test_what_did_not_fit_comes_alone(self):
        notes = {f'Docs/{i}.md': os.urandom(300_000) for i in range(12)}
        for rel, data in notes.items():
            self.old.write(rel, data)
        self.old.send()
        r = self.get('files:Docs')
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.new.read('receiver.json')
        self.assertEqual(st['failed'], [])
        for rel, data in notes.items():
            self.assertEqual((self.new.stage / st['session'] / rel).read_bytes(), data)


class Garbled(Case):
    """a 'sender' that answers with JSON nested too deep to read"""

    def fake(self, paired):
        srv = socket.create_server((HOST, 0))
        self.addCleanup(srv.close)

        def serve():
            conn, _ = srv.accept()
            with conn:
                net.recv_json(conn)
                if not paired:
                    return net.send_frame(conn, DEEP[:4000])     # within the size limit
                net.send_json(conn, {'ok': True, 'name': 'fake'})
                t = net.secure(conn, bytes.fromhex('ab' * 32), server=True)
                with t:
                    net.recv_json(t)
                    net.send_frame(t, DEEP)
                    time.sleep(1)
        threading.Thread(target=serve, daemon=True).start()
        return srv.getsockname()[1]

    def test_while_pairing(self):
        self.new.port = self.fake(paired=False)
        r = self.new.run('get', HOST, '--code', '123456', timeout=30)
        self.assertEqual(r.returncode, 1)
        self.assertIn('does not understand', r.stderr)
        self.assertNotIn('Traceback', r.stderr)

    def test_in_the_background_fetch(self):
        port = self.fake(paired=True)
        self.new.state_dir.mkdir(parents=True)
        (self.new.state_dir / 'receiver.json').write_text(json.dumps({
            'session': '0123456789abcdef', 'secret': 'ab' * 32, 'host': HOST, 'port': port,
            'status': 'interrupted', 'groups': ['files:Docs']}))
        r = self.new.run('continue', timeout=30)
        self.assertEqual(r.returncode, 1)
        st = self.new.read('receiver.json')
        self.assertEqual(st['status'], 'failed')
        self.assertIn('does not understand', st['error'])
