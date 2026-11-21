import shutil
import subprocess
import unittest

from helper import Case

from devs import paths, store


class Store(Case):
    def test_round_trip(self):
        made = store.create('bug', '  Clock   is late ', app='Dialer', text='two minutes')
        self.assertEqual(made['id'], 'dialer-clock-is-late')
        self.assertEqual(made['title'], 'Clock is late')
        self.assertEqual(store.load(made['id']), made)
        self.assertEqual(set(made), {'id', 'kind', 'title', 'text', 'app', 'category', 'status',
                                     'steps', 'check', 'tests'})
        store.update(made['id'], {'status': 'doing', 'steps': 'look at the clock'})
        store.set_test(made['id'], 'laptop-1', 'ok', 'abc1234')
        item = store.load(made['id'])
        self.assertEqual(item['status'], 'doing')
        self.assertEqual(item['tests']['laptop-1']['state'], 'ok')
        self.assertEqual(item['tests']['laptop-1']['version'], 'abc1234')
        self.assertEqual(list(paths.items_dir().glob('*.tmp')), [])

    def test_list_by_kind_and_app(self):
        store.create('bug', 'One', app='Dialer')
        store.create('wish', 'Two', app='Dialer')
        store.create('bug', 'Three', app='Music')
        self.assertEqual(len(store.all_items()), 3)
        self.assertEqual([i['title'] for i in store.all_items('bug', 'Dialer')], ['One'])
        self.assertEqual(len(store.all_items(app='Dialer')), 2)

    def test_same_title_gets_its_own_id(self):
        first = store.create('wish', 'Same')
        second = store.create('wish', 'Same')
        self.assertEqual((first['id'], second['id']), ('same', 'same-2'))

    def test_bad_ids_are_refused(self):
        for bad in ('../x', 'a/b', 'A', '', 'a.json', '.', '..', 'x' * 81, '-a', 'a b', None, 5, 'a\n'):
            with self.assertRaises(store.Invalid, msg=repr(bad)):
                store.path(bad)
            with self.assertRaises(store.Invalid, msg=repr(bad)):
                store.update(bad, {'status': 'done'})

    def test_bad_fields_are_refused(self):
        item = store.create('bug', 'Fine')
        for fields in ({'status': 'closed'}, {'kind': 'idea'}, {'title': ''}, {'title': 'x' * 121},
                       {'text': 5}, {'id': 'other'}, {'tests': {}}, {'text': 'x' * 4001}, {}):
            with self.assertRaises(store.Invalid, msg=repr(fields)):
                store.update(item['id'], fields)
        with self.assertRaises(store.Invalid):
            store.create('idea', 'No such kind')
        with self.assertRaises(store.Invalid):
            store.set_test(item['id'], '../dev', 'ok', '')
        with self.assertRaises(store.Invalid):
            store.set_test(item['id'], 'laptop', 'maybe', '')
        self.assertIsNone(store.update('not-there', {'status': 'done'}))

    @unittest.skipUnless(shutil.which('git'), 'no git')
    def test_every_change_is_a_commit(self):
        item = store.create('bug', 'Tracked')
        store.update(item['id'], {'status': 'done'})
        log = subprocess.run(['git', 'log', '--format=%s'], cwd=paths.items_dir(), capture_output=True, text=True)
        self.assertEqual(log.stdout.split('\n')[:2], ['tracked: status', 'add tracked'])

    def test_works_without_git(self):
        which = shutil.which
        shutil.which = lambda name: None
        self.addCleanup(setattr, shutil, 'which', which)
        item = store.create('bug', 'No git here')
        self.assertEqual(store.load(item['id'])['title'], 'No git here')
        self.assertFalse((paths.items_dir() / '.git').exists())


if __name__ == '__main__':
    unittest.main()
