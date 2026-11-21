"""The settings file is checked before use: a broken one never stops the Dialer (D22)."""
import json
import tempfile
import unittest
from pathlib import Path

import helper  # noqa: F401
from dial import config, groups

APPS = [{'id': 'a.desktop', 'name': 'A', 'icon': '', 'cats': ['Office'], 'path': '', 'keywords': ''},
        {'id': 'b.desktop', 'name': 'B', 'icon': '', 'cats': ['Settings'], 'path': '', 'keywords': ''}]


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.file = Path(self.dir.name) / 'config.json'

    def tearDown(self):
        self.dir.cleanup()

    def load(self, content):
        self.file.write_text(content if isinstance(content, str) else json.dumps(content))
        return config.load_conf(self.file)

    def test_missing_file_gives_the_defaults(self):
        self.assertEqual(config.load_conf(self.file), config.DEFAULTS)

    def test_not_an_object_gives_the_defaults(self):
        for content in ('[]', '"text"', '3', 'null', '{broken'):
            self.assertEqual(self.load(content), config.DEFAULTS, content)

    def test_empty_or_broken_slices_keep_the_default_slices(self):
        for slices in ([], {}, 'Work', [3, None], [{'categories': ['Office']}], [{'name': ''}]):
            self.assertEqual(self.load({'slices': slices})['slices'], config.DEFAULTS['slices'], slices)

    def test_usable_slices_are_kept_and_mended(self):
        c = self.load({'slices': [{'name': 'One', 'categories': 'Office'}, 7, {'name': 'Two', 'categories': ['X']}]})
        self.assertEqual(c['slices'], [{'name': 'One', 'categories': []}, {'name': 'Two', 'categories': ['X']}])

    def test_wrong_types_keep_the_default(self):
        c = self.load({'size': 'big', 'icon_size': None, 'ring_slots': [], 'hide': 'x', 'order': [],
                       'anchor': 4, 'preview_size': '460', 'notes_hide_vaults': {}, 'ai_view': 'all',
                       'assign': ['a']})
        self.assertEqual(c, config.DEFAULTS)

    def test_good_values_are_used(self):
        c = self.load({'size': 1.3, 'anchor': 'centre', 'ai_view': 'last', 'hide': ['x.desktop'],
                       'assign': {'a.desktop': 'Media'}, 'unknown': 1})
        self.assertEqual((c['size'], c['anchor'], c['ai_view'], c['hide']), (1.3, 'centre', 'last', ['x.desktop']))
        self.assertEqual(c['assign']['a.desktop'], 'Media')
        self.assertEqual(c['assign']['kitty.desktop'], 'Tools')     # the defaults stay under them
        self.assertNotIn('unknown', c)

    def test_every_loaded_config_can_be_arranged(self):
        for content in ('[]', {'slices': []}, {'slices': [{'name': 'Only'}]}, {'order': {'Work': 'x'}}):
            c = self.load(content)
            found, settings = groups.arrange(c, APPS, {})
            self.assertEqual(len(found), len(c['slices'][:6]))
            self.assertEqual(sum(len(g) for g in found), 2)         # the app and the gear
            self.assertEqual([a['id'] for a in settings], ['b.desktop'])

    def test_music_outputs(self):
        self.assertEqual(config.music_outputs(self.file), [])       # no file
        self.file.write_text('{"other": 1}')
        self.assertEqual(config.music_outputs(self.file), [])       # no key
        self.file.write_text('{"music_outputs": "AA:BB:CC:00:00:01"}')
        self.assertEqual(config.music_outputs(self.file), [])       # not a list
        self.file.write_text('{"music_outputs": ["aa:bb:cc:00:00:01", 5, "nonsense", "AA:BB:CC:00:00:01"]}')
        self.assertEqual(config.music_outputs(self.file), ['AA:BB:CC:00:00:01'])


if __name__ == '__main__':
    unittest.main()
