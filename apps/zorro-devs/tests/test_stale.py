import unittest

from helper import Case, change

from devs import devices, store


class Stale(Case):
    def setUp(self):
        super().setUp()
        self.here = devices.this_device()
        self.item = store.create('feature', 'Rings', app='Dialer')

    def stale(self):
        return devices.with_stale(store.load(self.item['id']))['tests'][self.here]['stale']

    def test_this_device_adds_itself(self):
        self.assertEqual(list(devices.devices()), [self.here])
        devices.add('second-laptop')
        self.assertEqual(sorted(devices.devices()), sorted([self.here, 'second-laptop']))
        with self.assertRaises(store.Invalid):
            devices.add('../x')

    def test_stale_after_the_app_changed(self):
        store.set_test(self.item['id'], self.here, 'ok', devices.head())
        self.assertFalse(self.stale())
        change(self.repo, 'README.md', 'elsewhere\n')
        self.assertFalse(self.stale())
        change(self.repo, 'apps/zorro-dial/dial.py', 'x = 2\n')
        self.assertTrue(self.stale())
        store.set_test(self.item['id'], self.here, 'fail', devices.head())
        self.assertFalse(self.stale())

    def test_untested_and_unknown(self):
        store.set_test(self.item['id'], self.here, 'untested', devices.head())
        change(self.repo, 'apps/zorro-dial/dial.py', 'x = 3\n')
        self.assertFalse(self.stale())
        store.set_test(self.item['id'], self.here, 'ok', '')
        self.assertTrue(self.stale())
        store.set_test(self.item['id'], self.here, 'ok', 'fffffff')
        self.assertTrue(self.stale())
        other = store.create('feature', 'No folder', app='Somewhere')
        store.set_test(other['id'], self.here, 'ok', '')
        self.assertFalse(devices.with_stale(store.load(other['id']))['tests'][self.here]['stale'])

    def test_counts(self):
        store.create('feature', 'Slices', app='Dialer')
        failing = store.create('bug', 'Broken', app='Music')
        store.set_test(self.item['id'], self.here, 'ok', devices.head())
        store.set_test(failing['id'], self.here, 'fail', devices.head())
        change(self.repo, 'apps/zorro-dial/dial.py', 'x = 4\n')
        row = devices.counts(store.all_items())[0]
        self.assertEqual((row['name'], row['this']), (self.here, True))
        self.assertEqual((row['ok'], row['fail'], row['untested'], row['stale']), (0, 1, 1, 1))


if __name__ == '__main__':
    unittest.main()
