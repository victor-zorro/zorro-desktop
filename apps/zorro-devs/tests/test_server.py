import unittest

from helper import ServerCase

from devs import devices, server, store


class Address(unittest.TestCase):
    def test_only_this_device_and_known_networks(self):
        for good in ('127.0.0.1', '::1', '::ffff:127.0.0.1'):
            self.assertTrue(server.private(good), good)
        for bad in ('8.8.8.8', '100.128.0.1', '2a00:1450::1', '::ffff:8.8.8.8', '2002::1', 'laptop', ''):
            self.assertFalse(server.private(bad), bad)

    def test_another_websites_page_is_refused(self):
        net = server.zorro_net
        self.assertFalse(net.host_ok('evil.example:8098'))
        self.assertTrue(net.host_ok('127.0.0.1:8098'))
        self.assertFalse(net.same_site({'Origin': 'http://evil.example', 'Host': '127.0.0.1:8098'}))
        self.assertTrue(net.same_site({'Origin': 'http://127.0.0.1:8098', 'Host': '127.0.0.1:8098'}))


class Api(ServerCase):
    def test_add_list_change(self):
        status, made = self.call('/api/items', {'kind': 'bug', 'title': 'Late clock', 'app': 'Dialer'})
        self.assertEqual((status, made['id'], made['status']), (200, 'dialer-late-clock', 'open'))
        status, listed = self.call('/api/items?kind=bug&app=Dialer')
        self.assertEqual([i['id'] for i in listed['items']], [made['id']])
        self.assertEqual(listed['this'], devices.this_device())
        self.assertEqual(self.call('/api/items?kind=wish')[1]['items'], [])
        status, changed = self.call(f'/api/items/{made["id"]}', {'status': 'done', 'steps': 'look'})
        self.assertEqual((status, changed['status'], changed['steps']), (200, 'done', 'look'))
        self.assertEqual(store.load(made['id'])['status'], 'done')

    def test_set_test(self):
        made = store.create('feature', 'Rings', app='Dialer')
        here = devices.this_device()
        status, item = self.call(f'/api/items/{made["id"]}/test', {'device': here, 'state': 'ok'})
        self.assertEqual(status, 200)
        self.assertEqual(item['tests'][here]['state'], 'ok')
        self.assertEqual(item['tests'][here]['version'], devices.head())
        self.assertFalse(item['tests'][here]['stale'])
        self.assertNotIn('stale', store.load(made['id'])['tests'][here])
        self.assertEqual(self.call(f'/api/items/{made["id"]}/test', {'device': 'unknown', 'state': 'ok'})[0], 400)
        self.assertEqual(self.call(f'/api/items/{made["id"]}/test', {'device': here, 'state': 'yes'})[0], 400)

    def test_apps_and_devices(self):
        store.create('bug', 'One', app='Music')
        store.create('bug', 'Two', app='Dialer')
        store.create('wish', 'Three', app='Dialer')
        apps = self.call('/api/apps?kind=bug')[1]
        self.assertEqual(apps['kinds']['bug'], 2)
        self.assertEqual(apps['apps'], [{'name': 'Dialer', 'count': 1}, {'name': 'Music', 'count': 1}])
        data = self.call('/api/devices')[1]
        self.assertEqual([(d['name'], d['this'], d['untested']) for d in data['devices']],
                         [(devices.this_device(), True, 3)])

    def test_what_is_refused(self):
        made = store.create('bug', 'Fine')
        self.assertEqual(self.call('/api/items', {'kind': 'idea', 'title': 'x'})[0], 400)
        self.assertEqual(self.call('/api/items', {'kind': 'bug', 'title': ''})[0], 400)
        self.assertEqual(self.call('/api/items', {'kind': 'bug', 'title': 'x', 'check': 'rules'})[0], 400)
        self.assertEqual(self.call('/api/items', ['not', 'an', 'object'])[0], 400)
        self.assertEqual(self.call('/api/items', raw=b'{nope')[0], 400)
        self.assertEqual(self.call('/api/items', raw=b'"' + b'x' * 30000 + b'"')[0], 400)
        self.assertEqual(self.call('/api/items', {'kind': 'bug', 'title': 'x'}, kind='text/plain')[0], 400)
        self.assertEqual(self.call('/api/items', {'kind': 'bug', 'title': 'x'}, kind='text/plain;json')[0], 400)
        self.assertEqual(self.call(f'/api/items/{made["id"]}', {'id': 'other'})[0], 400)
        self.assertEqual(self.call('/api/items/..%2F..%2Fdevices', {'status': 'done'})[0], 400)
        self.assertEqual(self.call('/api/items/../devices', {'status': 'done'})[0], 404)
        self.assertEqual(self.call('/api/items/not-there', {'status': 'done'})[0], 404)
        self.assertEqual(self.call('/api/items?kind=idea')[0], 400)
        self.assertEqual(self.call('/api/nothing')[0], 404)
        self.assertEqual(len(store.all_items()), 1)

    def test_page_files_only(self):
        status, page = self.call('/')
        self.assertEqual(status, 200)
        self.assertIn('<title>DEVS</title>', page)
        self.assertNotIn('http://', page.replace('http://www.w3.org', ''))
        self.assertNotIn('https://', page)
        self.assertEqual(self.call('/js/main.js')[0], 200)
        for path in ('/js/../cli.py', '/cli.py', '/js/', '/web/index.html', '/../store.py'):
            self.assertEqual(self.call(path)[0], 404, path)

    def test_other_networks_are_refused(self):
        real = server.private
        server.private = lambda address: False
        self.addCleanup(setattr, server, 'private', real)
        self.assertEqual(self.call('/api/items')[0], 403)
        self.assertEqual(self.call('/api/items', {'kind': 'bug', 'title': 'x'})[0], 403)
        self.assertEqual(self.call('/')[0], 403)
        self.assertEqual(store.all_items(), [])


if __name__ == '__main__':
    unittest.main()
