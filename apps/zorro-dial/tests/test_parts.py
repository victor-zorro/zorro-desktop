"""The output picker (with faked pactl / bluetoothctl output), the centre's status line, Messages."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helper  # noqa: F401
from dial import status
from dial.parts import messages, sound

OWN, HEAD, SPEAKER = 'alsa_output.pci.analog-stereo', 'AA:BB:CC:00:00:02', 'AA:BB:CC:00:00:01'
INFO = 'Device {mac} (public)\n\tName: {name}\n\tAlias: {name}\n\tIcon: audio-headphones\n\tConnected: {yes}\n'


class FakeSound:
    """pactl and bluetoothctl as one small world: sinks follow what is connected"""

    def __init__(self, connected=(SPEAKER,), reachable=True):
        self.connected, self.reachable, self.default, self.calls = list(connected), reachable, OWN, []

    def sinks(self):
        return [OWN] + [f'bluez_output.{m.replace(":", "_")}.1' for m in self.connected]

    def run(self, *cmd, timeout=5):
        self.calls.append(cmd)
        if cmd == ('pactl', 'get-default-sink'):
            return self.default + '\n'
        if cmd == ('pactl', 'list', 'short', 'sinks'):
            return ''.join(f'{i}\t{name}\tPipeWire\ts16le\tIDLE\n' for i, name in enumerate(self.sinks()))
        if cmd[:2] == ('pactl', 'set-default-sink'):
            self.default = cmd[2]
        if cmd[:2] == ('bluetoothctl', 'info'):
            names = {SPEAKER: 'Kitchen speaker', HEAD: 'Headphones'}
            if cmd[2] not in names:
                return f'Device {cmd[2]} not available\n'
            return INFO.format(mac=cmd[2], name=names[cmd[2]], yes='yes' if cmd[2] in self.connected else 'no')
        if cmd[:2] == ('bluetoothctl', 'connect') and self.reachable:
            self.connected.append(cmd[2])
        return ''


class PickerTest(unittest.TestCase):
    def setUp(self):
        self.world = FakeSound()
        for name, value in (('run', self.world.run), ('audio', None), ('eq', None)):
            patch = mock.patch.object(sound, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(sound.CONNECTING.clear)
        self.addCleanup(sound.FAILED.clear)

    def rows(self, ticked=(SPEAKER, HEAD), **kw):
        return sound.rows(sound.outputs(), list(ticked), sound.bt_devices(ticked), **kw)

    def test_outputs_from_pactl(self):
        self.assertEqual(sound.outputs(), [
            {'name': OWN, 'desc': OWN, 'default': True},
            {'name': 'bluez_output.AA_BB_CC_00_00_01.1', 'desc': 'bluez_output.AA_BB_CC_00_00_01.1', 'default': False}])

    def test_the_laptop_then_each_ticked_device(self):
        rows = self.rows()
        self.assertEqual([(r['kind'], r['name'], r['state']) for r in rows],
                         [('own', 'Laptop', 'use'), ('bt', 'Kitchen speaker', 'ready'), ('bt', 'Headphones', 'off')])
        self.assertEqual(rows[1]['sink'], 'bluez_output.AA_BB_CC_00_00_01.1')
        self.assertIsNone(rows[2]['sink'])

    def test_nothing_ticked_shows_only_the_laptop(self):
        self.assertEqual([r['kind'] for r in self.rows(ticked=())], ['own'])

    def test_a_device_bluetooth_does_not_know_is_greyed_under_its_address(self):
        unknown = 'AA:BB:CC:00:00:09'
        row = self.rows(ticked=(unknown,))[1]
        self.assertEqual((row['name'], row['state']), (unknown, 'off'))

    def test_the_output_in_use_is_marked(self):
        self.world.default = 'bluez_output.AA_BB_CC_00_00_01.1'
        self.assertEqual([r['state'] for r in self.rows()], ['ready', 'use', 'off'])

    def test_connecting_shows_until_the_time_limit(self):
        since = {HEAD: 1000.0}
        self.assertEqual(self.rows(connecting=since, now=1005.0)[2]['state'], 'connecting')
        self.assertEqual(self.rows(connecting=since, now=1000.0 + sound.CONNECT_LIMIT)[2]['state'], 'off')

    def test_tiles_show_the_state(self):
        outs = sound.outputs()
        tiles = sound.tiles(outs, [SPEAKER, HEAD], sound.bt_devices([SPEAKER, HEAD]))
        self.assertEqual([(t['name'], t['lit'], t['dim'], t['busy']) for t in tiles],
                         [('Laptop', True, False, False), ('Kitchen speaker', False, False, False),
                          ('Headphones', False, True, False)])
        self.assertTrue(all(t['keep'] and t['refresh'] for t in tiles))
        tiles[2]['start']()                                 # the tap: connecting shows at once
        busy = sound.tiles(outs, [SPEAKER, HEAD], sound.bt_devices([SPEAKER, HEAD]))[2]
        self.assertEqual((busy['busy'], busy['dim'], busy['act'], busy['sub']), (True, False, None, 'connecting…'))

    def test_one_tap_on_a_connected_device_plays_there(self):
        tiles = sound.tiles(sound.outputs(), [SPEAKER], sound.bt_devices([SPEAKER]))
        tiles[1]['act']()
        self.assertEqual(self.world.default, 'bluez_output.AA_BB_CC_00_00_01.1')

    def test_one_tap_on_a_greyed_device_connects_and_plays_there(self):
        tiles = sound.tiles(sound.outputs(), [HEAD], sound.bt_devices([HEAD]))
        with mock.patch.object(sound.time, 'sleep'):
            tiles[1]['act']()
        self.assertIn(('bluetoothctl', 'connect', HEAD), self.world.calls)
        self.assertEqual(self.world.default, 'bluez_output.AA_BB_CC_00_00_02.1')
        self.assertEqual((sound.CONNECTING, sound.FAILED), ({}, {}))

    def test_a_device_out_of_reach_gives_up_and_says_so(self):
        self.world.reachable = False
        with mock.patch.object(sound.time, 'sleep') as sleep:
            self.assertFalse(sound.connect(HEAD))
        self.assertEqual(sleep.call_count, sound.SINK_TRIES)
        self.assertEqual(sound.CONNECTING, {})
        row = self.rows(failed=sound.FAILED)[2]
        self.assertEqual((row['state'], row['failed']), ('off', True))
        self.assertIn('not reachable', sound.bt_tile(row)['sub'])


class StatusTest(unittest.TestCase):
    def test_connection(self):
        self.assertEqual(status.connection(''), '')
        self.assertEqual(status.connection('wlan0:wifi:connected:Harbour\\: 5G\nlo:loopback:connected (externally):lo\n'),
                         'Harbour: 5G')
        self.assertEqual(status.connection('wlan0:wifi:connected:Home\neth0:ethernet:connected:Wired 1\n'), 'Cable')
        self.assertEqual(status.connection('wwan0:gsm:connected:Provider\nwlan0:wifi:disconnected:\n'), 'Mobile')
        self.assertEqual(status.connection('wlan0:wifi:unavailable:\neth0:ethernet:unavailable:\n'), 'Offline')

    def test_battery(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(status.battery(d))
            for name, kind, more in (('AC', 'Mains', {}), ('BAT0', 'Battery', {'capacity': '82', 'status': 'Charging'}),
                                     ('hid-mouse', 'Battery', {'capacity': '10', 'status': 'Discharging', 'scope': 'Device'})):
                folder = Path(d) / name
                folder.mkdir()
                for key, value in {'type': kind, **more}.items():
                    (folder / key).write_text(value + '\n')
            self.assertEqual(status.battery(d), (82, 'charging'))
        self.assertEqual(status.battery_text((82, 'charging')), '82% charging')
        self.assertEqual(status.battery_text((40, 'discharging')), '40%')
        self.assertEqual(status.battery_text((100, 'full')), '100% plugged in')
        self.assertEqual(status.battery_text(None), '')


class MessagesTest(unittest.TestCase):
    def test_one_list_newest_first(self):
        def note(i, app, summary, stamp):
            return {'id': {'data': i}, 'appname': {'data': app}, 'summary': {'data': summary},
                    'body': {'data': '<b>text</b>'}, 'timestamp': {'data': stamp}}
        text = json.dumps({'data': [[note(1, 'Firefox', 'old', 10e6), note(3, 'Signal', 'newest', 90e6),
                                     note(2, 'Firefox', 'WhatsApp', 50e6)]]})
        found = messages.history(text, 100)
        self.assertEqual([m['summary'] for m in found], ['newest', 'WhatsApp', 'old'])
        self.assertEqual([m['src'] for m in found], ['Signal', 'WhatsApp', 'Firefox'])
        self.assertEqual(found[0]['body'], 'text')
        self.assertEqual(messages.history('', 100), [])
        self.assertEqual(messages.history('{"data": 5}', 100), [])

    def test_the_part_is_one_list(self):
        world = {('dunstctl', 'history'): json.dumps({'data': [[
            {'id': {'data': 7}, 'appname': {'data': 'Signal'}, 'summary': {'data': 'hi'}, 'body': {'data': ''},
             'timestamp': {'data': 1}}]]}), ('dunstctl', 'is-paused'): 'false\n'}
        with mock.patch.object(messages, 'run', lambda *cmd, **kw: world.get(cmd, '')):
            part = messages.Messages()
            part.fetch()
        self.assertEqual([t['id'] for t in part.roots()], ['dnd', 'msg:7'])
        self.assertTrue(callable(part.roots()[1]['remove']))


if __name__ == '__main__':
    unittest.main()
