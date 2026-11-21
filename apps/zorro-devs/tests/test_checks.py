import unittest

from helper import ServerCase, change

from devs import checks, devices, store


class Checks(ServerCase):
    def test_good_repo(self):
        results = checks.run(['compile', 'shell', 'json', 'units'])
        self.assertEqual({name: r['ok'] for name, r in results.items()},
                         {'compile': True, 'shell': True, 'json': True, 'units': True})
        self.assertEqual(results['json']['version'], devices.head())
        self.assertEqual(checks.results()['shell']['detail'], '1 files')

    def test_broken_files_fail(self):
        change(self.repo, 'bad.json', '{"a": ')
        change(self.repo, 'bad.py', 'def broken(:\n')
        change(self.repo, 'bad.sh', 'if then fi (\n')
        results = checks.run()
        self.assertEqual([name for name, r in results.items() if r['ok']], ['units'])
        self.assertIn('bad.json', results['json']['detail'])
        self.assertIn('bad.py', results['compile']['detail'])
        self.assertIn('missing', results['rules']['detail'])

    def test_result_becomes_the_test_state(self):
        here = devices.this_device()
        item = store.new_item('feature', 'JSON parses', {'check': 'json', 'app': 'DEVS'})
        store.save(item, 'add')
        plain = store.create('feature', 'By hand')
        status, answer = self.call('/api/check', {})
        self.assertEqual(status, 200)
        self.assertTrue(answer['checks']['json']['ok'])
        self.assertEqual(store.load(item['id'])['tests'][here]['state'], 'ok')
        self.assertEqual(store.load(plain['id'])['tests'], {})
        change(self.repo, 'bad.json', 'nope')
        checks.run(['json'])
        self.assertEqual(store.load(item['id'])['tests'][here]['state'], 'fail')
        self.assertFalse(self.call('/api/devices')[1]['checks']['json']['ok'])


if __name__ == '__main__':
    unittest.main()
