import unittest

from helper import Case, change

from devs import fill, store


class Fill(Case):
    def test_makes_items_from_the_repo(self):
        made, kept = fill.fill()
        self.assertGreater(made, 8)
        items = {i['id']: i for i in store.all_items()}
        rings = items['dialer-three-rings']
        self.assertEqual((rings['kind'], rings['status'], rings['app'], rings['category'], rings['tests']),
                         ('feature', 'done', 'Dialer', 'Launcher', {}))
        self.assertIn('inner ring', rings['text'])
        self.assertEqual(items['dialer-super-opens-the-dialer']['category'], 'Keys')
        self.assertEqual(items['dialer-the-dialer']['text'], 'the Dialer: app launcher around the clock')
        planned = items['desktop-app-switcher-in-the-top-bar']
        self.assertEqual((planned['kind'], planned['status']), ('feature', 'open'))
        decision = items['intelligence-the-ai-reads-only-folders-the-user-chose']
        self.assertEqual(decision['kind'], 'decision')
        self.assertEqual(items['devs-check-build-rules-hold']['check'], 'rules')

    def test_again_changes_nothing(self):
        made, _ = fill.fill()
        again, kept = fill.fill()
        self.assertEqual(again, 0)
        self.assertGreaterEqual(kept, made)
        self.assertEqual(len(store.all_items()), made)

    def test_keeps_what_the_user_changed(self):
        fill.fill()
        store.update('dialer-three-rings', {'title': 'Rings, my words', 'status': 'doing', 'text': 'mine'})
        change(self.repo, 'apps/zorro-dial/README.md', '# zorro-dial\n\n- **Three rings**: a new sentence in the README.\n'
               '- **Four corners**: something new that was built.\n')
        made, _ = fill.fill()
        self.assertEqual(made, 1)
        rings = store.load('dialer-three-rings')
        self.assertEqual((rings['title'], rings['status'], rings['text']), ('Rings, my words', 'doing', 'mine'))
        self.assertIsNotNone(store.load('dialer-four-corners'))


if __name__ == '__main__':
    unittest.main()
