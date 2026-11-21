"""Devices nearby: the beacon answers who it is and nothing else, the getting side finds the
other device (and never itself), and a knock shows one notification there, no more."""
import json
import socket
import struct
import sys
import time
import unittest

from unittest import mock

from harness import HOST, Case, wait_for
from transfer import beacon, net

ABOUT = {'name', 'magic', 'sending'}


def network(home):
    """a made-up picture of the network for zorro_net: a home LAN (or a cafe) and NetBird"""
    import ipaddress
    nets = [('wlp1s0', ipaddress.ip_network('192.168.1.0/24')),
            ('wt0', ipaddress.ip_network('100.64.0.0/16'))]
    return mock.patch.object(net.zorro_net, 'look', return_value={'nets': nets, 'home': home})


class Rules(unittest.TestCase):
    def test_only_trusted_peers(self):
        with network(home=True):
            for addr in ('127.0.0.1', '192.168.1.5', '100.64.1.1', '::1', '::ffff:192.168.1.5'):
                self.assertTrue(net.trusted(addr), addr)
            for addr in ('8.8.8.8', '10.1.2.3', '100.128.0.1', '2a00:1450::1', 'nonsense', ''):
                self.assertFalse(net.trusted(addr), addr)
        with network(home=False):               # a cafe: only this device and NetBird
            self.assertFalse(net.trusted('192.168.1.5'))
            self.assertTrue(net.trusted('100.64.1.1'))
            self.assertTrue(net.trusted('127.0.0.1'))

    def test_a_public_peer_gets_no_answer(self):
        b = beacon.Beacon()
        with network(home=True):
            self.assertIsNone(b.reply({'op': 'probe'}, '8.8.8.8'))
            self.assertIsNone(b.reply({'op': 'knock', 'name': 'x'}, '8.8.8.8'))

    def test_only_the_two_requests(self):
        b = beacon.Beacon()
        for req in (['op'], {'op': 'pair'}, {'op': 'probe', 'more': 1}, {'op': 'knock'},
                    {'op': 'knock', 'name': ''}, {'op': 'knock', 'name': 5},
                    {'op': 'knock', 'name': 'x', 'code': '1'}):
            self.assertIsNone(b.reply(req, '127.0.0.1'), req)

    def test_knocks_are_limited(self):
        opened = [-1]
        k = beacon.Knocks(seen=lambda: opened[0])
        self.assertTrue(k.allow('a', 0))
        self.assertFalse(k.allow('a', 30), 'the same device within a minute')
        self.assertTrue(k.allow('b', 31))
        self.assertTrue(k.allow('c', 32))
        self.assertFalse(k.allow('d', 33), 'more than three a minute')
        opened[0] = 60                          # three unanswered: quiet until Transfer opens
        self.assertTrue(k.allow('a', 61))

    def test_unanswered_knocks_make_it_quiet(self):
        opened = [-1]
        k = beacon.Knocks(seen=lambda: opened[0])
        for i, t in enumerate((0, 100, 200)):
            self.assertTrue(k.allow(f'pc{i}', t))
        self.assertFalse(k.allow('pc0', 300), 'three nobody acted on: quiet')
        self.assertFalse(k.allow('pc9', 1000), 'also for others')
        self.assertTrue(k.allow('pc0', 200 + beacon.QUIET_FOR + 1), 'an hour later')
        self.assertTrue(k.allow('pc1', 4000))
        self.assertTrue(k.allow('pc2', 4100))
        self.assertFalse(k.allow('pc3', 4200))
        opened[0] = 4250                        # the user opened Transfer
        self.assertTrue(k.allow('pc3', 4300))

    def test_knocks_spread_out_stay_allowed(self):
        k = beacon.Knocks(seen=lambda: -1)
        for t in range(0, 6000, 700):           # one every 12 minutes: never three in 10
            self.assertTrue(k.allow('pc', t), t)

    def test_names_are_cleaned(self):
        self.assertEqual(beacon.clean_name(' PC\n\x1b[31m '), 'PC[31m')
        self.assertEqual(len(beacon.clean_name('x' * 500)), 64)
        self.assertEqual(beacon.clean_name(['PC']), '')


class WithBeacon(Case):
    def start_beacon(self, side=None):
        side = side or self.old
        p = side.start('beacon')
        wait_for(lambda: side.read('beacon.json').get('pid') == p.pid or p.poll() is not None,
                 what='the beacon')
        self.assertIsNone(p.poll(), p.poll() is not None and p.stderr.read())
        return p

    def udp(self, data):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
            u.settimeout(1)
            u.sendto(data, (HOST, self.port + 1))
            try:
                return json.loads(u.recvfrom(1024)[0])
            except socket.timeout:
                return None

    def tcp(self, raw, wait=5):
        """raw bytes to the beacon's TCP port: its answer, None when it closes without one"""
        with socket.create_connection((HOST, self.port + 2), timeout=wait) as s:
            s.sendall(raw)
            try:
                return json.loads(net.recv_frame(s, limit=1024))
            except ConnectionError:
                return None

    @staticmethod
    def frame(obj):
        data = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        return struct.pack('>I', len(data)) + data

    def nearby(self, side):
        r = side.run('nearby', '--json', '--wait', '0.6')
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)


class Beacon(WithBeacon):
    sender_cfg = {'TIMEOUT': 2}

    def test_who_it_is_and_whether_it_sends(self):
        self.start_beacon()
        for ask in (lambda: self.udp(net.WHO), lambda: self.tcp(self.frame({'op': 'probe'}))):
            r = ask()
            self.assertEqual(set(r), ABOUT)
            self.assertEqual((r['name'], r['magic'], r['sending']), ('old', 'zorro-transfer/2', False))
        self.old.send()
        self.assertTrue(self.udp(net.WHO)['sending'])
        self.assertTrue(self.tcp(self.frame({'op': 'probe'}))['sending'])

    def test_wrong_requests_get_nothing(self):
        self.start_beacon()
        for data in (b'hello', net.WHO + b'?', b'x' * 600, json.dumps({'op': 'probe'}).encode()):
            self.assertIsNone(self.udp(data), data)
        for raw in (self.frame(b'not json'), self.frame([1, 2]), self.frame({'op': 'pair'}),
                    self.frame({'op': 'probe', 'x': 'y' * 600}), struct.pack('>I', 1 << 20) + b'{',
                    self.frame({'op': 'probe'})[:6]):
            self.assertIsNone(self.tcp(raw), raw[:20])
        self.assertEqual(set(self.tcp(self.frame({'op': 'probe'}))), ABOUT, 'still answers')

    def test_a_few_connections_at_a_time(self):
        self.start_beacon()
        idle = [socket.create_connection((HOST, self.port + 2)) for _ in range(beacon.MAX_CONNECTIONS)]
        time.sleep(0.2)
        self.assertIsNone(self.tcp(self.frame({'op': 'probe'}), wait=0.3), 'one too many')
        for s in idle:
            s.close()
        wait_for(lambda: self.tcp(self.frame({'op': 'probe'})), what='a free slot')


class Nearby(WithBeacon):
    def test_finds_the_other_device_and_never_itself(self):
        self.start_beacon()
        found = self.nearby(self.new)
        self.assertEqual(found, [{'name': 'old', 'sending': False, 'host': HOST, 'via': 'local'}])
        self.assertEqual(self.nearby(self.old), [], 'its own beacon is not listed')
        self.old.send()
        self.assertTrue(self.nearby(self.new)[0]['sending'])

    def test_netbird_peers_are_asked_too(self):
        self.start_beacon()
        self.new.netbird.write_text(json.dumps({'peers': {'details': [
            {'netbirdIp': f'{HOST}/32', 'fqdn': 'old.netbird.example', 'status': 'Connected'},
            {'netbirdIp': '127.0.0.9', 'fqdn': 'away.netbird.example', 'status': 'Idle'}]}}))
        self.new.cfg['broadcasts'] = []
        self.assertEqual(self.nearby(self.new),
                         [{'name': 'old', 'sending': False, 'host': HOST, 'via': 'netbird'}])
        del self.new.cfg['broadcasts']
        found = self.nearby(self.new)
        self.assertEqual([(f['name'], f['via']) for f in found], [('old', 'local')], 'once')

    def test_a_whole_transfer_with_the_device_found(self):
        self.start_beacon()
        self.old.write('Docs/a.txt', 'found and fetched')
        self.old.send()
        host = self.nearby(self.new)[0]['host']
        r = self.new.run('get', host, '--code', self.old.code(), '--groups', 'files:Docs')
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.new.read('receiver.json')
        self.assertEqual(st['status'], 'received')
        self.assertEqual((self.new.stage / st['session'] / 'Docs/a.txt').read_text(),
                         'found and fetched')


class Knock(WithBeacon):
    def setUp(self):
        super().setUp()
        self.opened = self.root / 'opened'
        self.old.cfg['send_cmd'] = [sys.executable, '-c',
                                    'import sys; open(sys.argv[1], "a").write("x")', str(self.opened)]

    def shown(self):
        try:
            return self.old.notified.read_text().splitlines()
        except OSError:
            return []

    def test_one_notification_and_nothing_sent(self):
        self.start_beacon()
        r = self.new.run('knock', HOST)
        self.assertEqual(r.returncode, 0, r.stderr)
        wait_for(self.shown, what='the notification')
        self.assertIn("new wants this device's setup", self.shown()[0])
        self.assertIn('--action=send=Send', self.shown()[0])
        r = self.new.run('knock', HOST)
        self.assertEqual(r.returncode, 1)
        self.assertIn('already asked', r.stderr)
        time.sleep(0.5)
        self.assertEqual(len(self.shown()), 1, 'a second knock within a minute is not shown')
        self.assertFalse(self.opened.exists(), 'nothing was chosen, nothing opened')
        self.assertEqual(self.old.read('sender.json'), {}, 'nothing sent, nothing paired')
        self.assertFalse(self.new.stage.exists())

    def test_the_send_button_opens_transfer(self):
        self.old.cfg['notify_answer'] = 'send'
        self.start_beacon()
        self.assertEqual(self.new.run('knock', HOST).returncode, 0)
        wait_for(lambda: self.opened.exists(), what='Transfer to open')
        self.assertEqual(self.old.read('sender.json'), {}, 'opening is all it does')
