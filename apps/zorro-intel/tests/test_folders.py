"""The folder rule and the excerpts that go along with a question."""
import os
import unittest

from fakes import SandboxCase, hit

from intel import config, excerpts, folders


class Inside(SandboxCase):
    def setUp(self):
        super().setUp()
        self.notes_dir = self.notes('a.md', 'b.md')
        self.other = self.home / 'notes2'
        self.other.mkdir()
        (self.other / 'secret.md').write_text('secret words')

    def test_inside_and_outside(self):
        chosen = [str(self.notes_dir)]
        self.assertTrue(folders.inside(self.notes_dir / 'a.md', chosen))
        self.assertTrue(folders.inside(self.notes_dir / 'deep' / 'c.md', chosen))
        self.assertFalse(folders.inside(self.home / 'elsewhere.md', chosen))
        self.assertFalse(folders.inside(self.notes_dir, chosen))
        self.assertFalse(folders.inside('', chosen))
        self.assertFalse(folders.inside(self.notes_dir / 'a.md', []))

    def test_prefix_trick(self):
        self.assertFalse(folders.inside(self.other / 'secret.md', [str(self.notes_dir)]))
        self.assertFalse(folders.inside(str(self.notes_dir) + '2/secret.md', [str(self.notes_dir) + '/']))

    def test_dotdot_escape(self):
        sneaky = f'{self.notes_dir}/../notes2/secret.md'
        self.assertFalse(folders.inside(sneaky, [str(self.notes_dir)]))

    def test_symlink_escape(self):
        os.symlink(self.other / 'secret.md', self.notes_dir / 'link.md')
        os.symlink(self.other, self.notes_dir / 'linked-folder')
        chosen = [str(self.notes_dir)]
        self.assertFalse(folders.inside(self.notes_dir / 'link.md', chosen))
        self.assertFalse(folders.inside(self.notes_dir / 'linked-folder' / 'secret.md', chosen))

    def test_chosen_folder_is_a_symlink(self):
        os.symlink(self.notes_dir, self.home / 'shortcut')
        self.assertTrue(folders.inside(self.notes_dir / 'a.md', [str(self.home / 'shortcut')]))
        self.assertTrue(folders.inside(self.home / 'shortcut' / 'a.md', [str(self.notes_dir)]))

    def test_allowed_filters_hits(self):
        hits = [hit(self.notes_dir / 'a.md'), hit(self.other / 'secret.md'), {'title': 'no path'}, 'junk']
        kept = folders.allowed(hits, [str(self.notes_dir)])
        self.assertEqual([h['path'] for h in kept], [str(self.notes_dir / 'a.md')])

    def test_short(self):
        self.assertEqual(folders.short(self.home / 'notes'), '~/notes')
        self.assertEqual(folders.short('/srv/x'), '/srv/x')


class Settings(SandboxCase):
    def test_first_run_is_empty(self):
        self.assertEqual(config.load(), {'folders': [], 'excerpts': 4})

    def test_add_remove(self):
        folder = self.notes('a.md')
        config.add_folder(str(folder))
        config.add_folder(str(folder) + '/')
        self.assertEqual(config.load()['folders'], [str(folder)])
        config.remove_folder(str(folder))
        self.assertEqual(config.load()['folders'], [])

    def test_excerpts_are_held_to_0_8(self):
        self.assertEqual(config.set_excerpts(99)['excerpts'], 8)
        self.assertEqual(config.set_excerpts(-3)['excerpts'], 0)
        self.assertEqual(config.load()['excerpts'], 0)

    def test_broken_file(self):
        from intel import paths
        paths.config_file().parent.mkdir(parents=True)
        paths.config_file().write_text('{"folders": "nope", "excerpts": "many"}')
        self.assertEqual(config.load(), {'folders': [], 'excerpts': 4})


class Context(SandboxCase):
    def setUp(self):
        super().setUp()
        self.dir = self.notes('a.md', 'b.md', 'c.md')
        self.chosen = [str(self.dir)]
        self.hits = [hit(self.dir / 'a.md', 'A' * 100), hit(self.home / 'out.md', 'OUT'),
                     hit(self.dir / 'b.md', 'B' * 100), hit(self.dir / 'c.md', 'C' * 100)]

    def test_count_and_filter(self):
        context = excerpts.build(self.hits, self.chosen, 2)
        self.assertEqual([c['path'] for c in context], [str(self.dir / 'a.md'), str(self.dir / 'b.md')])
        self.assertEqual(excerpts.build(self.hits, self.chosen, 0), [])
        self.assertEqual(excerpts.build(self.hits, [], 4), [])

    def test_caps(self):
        context = excerpts.build(self.hits, self.chosen, 8, total=150, each=90)
        self.assertEqual([len(c['text']) for c in context], [90, 60])
        self.assertLessEqual(sum(len(c['text']) for c in context), 150)

    def test_empty_snippets_are_skipped(self):
        context = excerpts.build([hit(self.dir / 'a.md', '  '), hit(self.dir / 'b.md', 'text')], self.chosen, 4)
        self.assertEqual([c['text'] for c in context], ['text'])

    def test_one_file(self):
        context = excerpts.of_file(self.dir / 'a.md', self.chosen, limit=10)
        self.assertEqual(context, [{'path': str(self.dir / 'a.md'), 'text': '# a.md\nwor'}])
        (self.home / 'out.md').write_text('outside')
        self.assertEqual(excerpts.of_file(self.home / 'out.md', self.chosen), [])
        self.assertEqual(excerpts.of_file(self.dir / 'missing.md', self.chosen), [])

    def test_gather(self):
        cfg = {'folders': self.chosen, 'excerpts': 2}
        context, note = excerpts.gather('q', cfg, find=lambda q: self.hits)
        self.assertEqual(len(context), 2)
        self.assertIsNone(note)
        self.assertEqual(excerpts.gather('q', cfg, find=lambda q: None), ([], excerpts.NO_SEARCH))
        asked = []
        self.assertEqual(excerpts.gather('q', {'folders': [], 'excerpts': 4}, find=asked.append), ([], None))
        self.assertEqual(excerpts.gather('q', {'folders': self.chosen, 'excerpts': 0}, find=asked.append), ([], None))
        self.assertEqual(asked, [])

    def test_gather_about_a_file(self):
        cfg = {'folders': self.chosen, 'excerpts': 4}
        context, note = excerpts.gather('q', cfg, about=str(self.dir / 'b.md'))
        self.assertEqual([c['path'] for c in context], [str(self.dir / 'b.md')])
        context, note = excerpts.gather('q', cfg, about=str(self.home / 'out.md'))
        self.assertEqual(context, [])
        self.assertIn('no files sent', note)


if __name__ == '__main__':
    unittest.main()
