"""The sender's door: who may connect, how long a pairing may take, how many wrong codes one
device may type, and what it does with messages that are too big, too deep or not numbers."""
import json
import socket
import struct
import time

from harness import HOST, Case, Peer, wait_for
from transfer import net

OTHER = '127.0.0.2'             # a second device: another address on this machine


def probe(port, source=HOST):
    """the sender's answer to a probe, None when it closed without one"""
    sock = Peer(port, source).connect()
    try:
        net.send_json(sock, {'op': 'probe'})
        return net.recv_json(sock)
    except (OSError, ValueError):
        return None
    finally:
        sock.close()


def closed_within(sock, seconds, drip=None):
    """seconds until the other side closed (a byte of drip sent now and then), None if not"""
    start = time.monotonic()
    sock.settimeout(0.3)
    while time.monotonic() - start < seconds:
        if drip:
            try:
                sock.sendall(drip)
            except OSError:
                return time.monotonic() - start
        try:
            if sock.recv(4096) == b'':
                return time.monotonic() - start
        except socket.timeout:
            continue
        except OSError:
            return time.monotonic() - start
    return None


class PairingTime(Case):
    sender_cfg = {'PAIR_TIME': 1.5, 'FIRST_WAIT': 0.01}

    def test_a_slow_pairing_is_cut_off_as_a_whole(self):
        self.old.send()
        sock, hi = Peer(self.port, OTHER).hello({'op': 'pair'})
        self.assertTrue(hi['ok'])
        took = closed_within(sock, 8, drip=b'\0')
        sock.close()
        self.assertIsNotNone(took, 'a byte now and then kept the pairing open')
        self.assertLess(took, 4)
        t, reply = Peer(self.port).pair(self.old.code())
        self.assertIsNotNone(t, reply)
        t.close()


class OneDeviceLockedOut(Case):
    sender_cfg = {'PEER_FAILS': 2, 'FIRST_WAIT': 0.01}

    def test_others_can_still_pair(self):
        self.old.send()
        guesser = Peer(self.port, OTHER)
        for n in range(2):
            wait_for(guesser.wrong_code, what=f'wrong try {n + 1}')
        wait_for(lambda: self.old.read('sender.json').get('fails') == 2, what='the count')
        t, reply = guesser.pair(self.old.code())
        self.assertIsNone(t)
        self.assertIn('too many wrong codes from this device', reply['error'])
        st = self.old.read('sender.json')
        self.assertEqual(st['status'], 'wrong code', 'pairing stays on for the others')
        t, reply = Peer(self.port).pair(self.old.code())
        self.assertIsNotNone(t, reply)
        t.close()


class Door(Case):
    sender_cfg = {'MAX_CONNECTIONS': 3, 'distrust': [OTHER]}

    def test_an_untrusted_address_is_closed_at_once(self):
        self.old.send()
        self.assertIsNone(probe(self.port, OTHER))
        sock = socket.create_connection((HOST, self.port), source_address=(OTHER, 0))
        self.assertIsNotNone(closed_within(sock, 2), 'left open')
        sock.close()
        self.assertEqual(probe(self.port)['name'], 'old')

    def test_an_oversize_hello_is_dropped(self):
        self.old.send()
        sock = socket.create_connection((HOST, self.port))
        sock.sendall(struct.pack('>I', 1 << 20) + b'{"op": "probe"' + b' ' * 5000)
        self.assertIsNotNone(closed_within(sock, 5), 'no answer, closed')
        sock.close()
        self.assertEqual(probe(self.port)['name'], 'old')

    def test_a_few_connections_at_a_time(self):
        self.old.send()
        idle = [socket.create_connection((HOST, self.port)) for _ in range(3)]
        time.sleep(0.3)
        self.assertIsNone(probe(self.port), 'one too many')
        for s in idle:
            s.close()
        wait_for(lambda: probe(self.port), what='a free slot')

    def test_deep_json_is_a_bad_peer_not_a_crash(self):
        sender = self.old.send()
        deep = b'[' * 200_000 + b']' * 200_000
        for frame in (deep[:4000], b'{"op": ' + b'[' * 2000 + b']' * 2000 + b'}'):
            sock = socket.create_connection((HOST, self.port))
            sock.sendall(struct.pack('>I', len(frame)) + frame)
            self.assertIsNotNone(closed_within(sock, 5))
            sock.close()
        t, _ = Peer(self.port).pair(self.old.code())
        net.send_frame(t, deep)
        self.assertIsNotNone(closed_within(t, 5))
        t.close()
        self.assertIsNone(sender.poll())
        self.assertEqual(probe(self.port)['name'], 'old')


class SessionList(Case):
    sender_cfg = {'RETRY_FOR': 1}

    def test_old_sessions_go_at_every_save(self):
        self.old.write('Docs/a.txt', 'x')
        self.old.send()
        peer = Peer(self.port)
        t, first = peer.pair(self.old.code())
        t.close()
        time.sleep(1.2)
        t, second = peer.pair(self.old.code())
        peer.ask(t, op='manifest', groups=['files:Docs'])
        sessions = self.old.read('sender.json')['sessions']
        self.assertEqual(list(sessions), [second['session']])
        self.assertTrue(peer.ask(t, op='finished')['ok'])
        t.close()
        done = self.old.read('sender.json')['sessions'][second['session']]
        self.assertEqual(done['status'], 'done')
        self.assertNotIn('secret', done, 'a finished transfer keeps no secret')

    def test_numbers_from_the_receiver_stay_numbers(self):
        self.old.write('Docs/a.txt', 'x')
        self.old.send()
        peer = Peer(self.port)
        t, s = peer.pair(self.old.code())
        net.send_json(t, {'op': 'progress', 'done': float('inf'), 'speed': float('nan'),
                          'total': 1e300, 'current': 'x'})
        wait_for(lambda: self.old.read('sender.json')['sessions'][s['session']].get('current'),
                 what='the progress')
        t.close()
        text = (self.old.state_dir / 'sender.json').read_text()
        self.assertNotIn('Infinity', text)
        self.assertNotIn('NaN', text)
        got = json.loads(text)['sessions'][s['session']]
        self.assertEqual((got['done'], got['speed'], got['total']), (0, 0, 0))
