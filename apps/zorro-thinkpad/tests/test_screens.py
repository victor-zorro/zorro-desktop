"""the Screens page's logic: reading xrandr and the arguments for an arrangement"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zsettings import screens  # noqa: E402

XRANDR = '''Screen 0: minimum 320 x 200, current 4480 x 1440, maximum 16384 x 16384
eDP-1 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis) 309mm x 174mm
   1920x1080     60.01*+  48.00
   1680x1050     60.01
HDMI-A-0 connected 2560x1440+1920+0 (normal left inverted right x axis y axis) 597mm x 336mm
   2560x1440     59.95*+
   1920x1080     60.00
DisplayPort-0 connected (normal left inverted right x axis y axis)
   1920x1200     59.95 +
DisplayPort-1 disconnected (normal left inverted right x axis y axis)
'''


class Screens(unittest.TestCase):
    def setUp(self):
        self.now = screens.parse(XRANDR)

    def test_parse(self):
        names = [(s['name'], s['connected'], s['on'], s['laptop']) for s in self.now]
        self.assertEqual(names, [('eDP-1', True, True, True), ('HDMI-A-0', True, True, False),
                                 ('DisplayPort-0', True, False, False), ('DisplayPort-1', False, False, False)])
        self.assertEqual(self.now[1]['modes'], ['2560x1440', '1920x1080'])

    def test_two_on_the_same_side_line_up(self):
        args = screens.plan(self.now, {'layout': {'HDMI-A-0': {'where': 'right', 'mode': '1920x1080'},
                                                  'DisplayPort-0': {'where': 'right'}}, 'main': 'HDMI-A-0'})
        self.assertEqual(args, ['--output', 'eDP-1', '--auto',
                                '--output', 'HDMI-A-0', '--mode', '1920x1080', '--right-of', 'eDP-1',
                                '--output', 'DisplayPort-0', '--auto', '--right-of', 'HDMI-A-0',
                                '--output', 'HDMI-A-0', '--primary'])

    def test_laptop_off_needs_another_screen_on(self):
        all_off = {'layout': {n: {'where': 'off'} for n in ('eDP-1', 'HDMI-A-0', 'DisplayPort-0')}}
        self.assertEqual(screens.plan(self.now, all_off)[:3], ['--output', 'eDP-1', '--auto'])
        one_on = {'layout': {'eDP-1': {'where': 'off'}, 'HDMI-A-0': {'where': 'left'}}}
        self.assertEqual(screens.plan(self.now, one_on)[:3], ['--output', 'eDP-1', '--off'])

    def test_unknown_mode_falls_back(self):
        args = screens.plan(self.now, {'layout': {'HDMI-A-0': {'mode': '9999x9999'}}})
        self.assertIn('--auto', args[args.index('HDMI-A-0'):args.index('HDMI-A-0') + 2])

    def test_restore_brings_back_what_is_on(self):
        self.assertEqual(screens.restore_args(self.now),
                         ['--output', 'eDP-1', '--mode', '1920x1080', '--pos', '0x0', '--primary',
                          '--output', 'HDMI-A-0', '--mode', '2560x1440', '--pos', '1920x0',
                          '--output', 'DisplayPort-0', '--off'])

    def test_a_desktop_pc_has_an_anchor(self):
        now = screens.parse('DP-1 connected 1920x1080+0+0 (normal)\n   1920x1080 60.00*+\n')
        self.assertTrue(now[0]['laptop'])


if __name__ == '__main__':
    unittest.main()
