"""Which engine answers: auto and its fallback order, a forced engine, nothing leaves this laptop."""
import os
import shutil
import tempfile
import unittest

from fakes import FakeEngine, SandboxCase, exchange

from zai import config, models
from zai.models import chosen, on_battery

ASK = {'op': 'ask', 'place': 'dialer', 'messages': [{'role': 'user', 'content': 'hi'}]}


def engines(**kw):
    return {'claude': FakeEngine('claude', host='claude.test', **kw.get('claude', {})),
            'mistral': FakeEngine('mistral', host='mistral.test', **kw.get('mistral', {})),
            'local': FakeEngine('local', **kw.get('local', {}))}


def summary(replies):
    notes = [r['text'] for r in replies if r['type'] == 'note']
    return replies[-1].get('engine') or replies[-1].get('code'), notes


class Routing(SandboxCase):
    def test_auto_prefers_claude(self):
        self.online = {'claude.test', 'mistral.test'}
        self.serve(engines())
        self.assertEqual(summary(exchange(ASK)), ('claude', []))

    def test_auto_falls_back_to_mistral(self):
        self.online = {'mistral.test'}
        self.serve(engines())
        self.assertEqual(summary(exchange(ASK)), ('mistral', ['Claude not reachable: answering with Mistral']))

    def test_auto_offline_is_local(self):
        self.serve(engines())
        engine, notes = summary(exchange(ASK))
        self.assertEqual(engine, 'local')
        self.assertEqual(notes, ['Claude not reachable; Mistral not reachable: answering with Local'])

    def test_auto_skips_an_engine_that_is_not_set_up(self):
        self.online = {'claude.test', 'mistral.test'}
        self.serve(engines(claude={'ready': False}))
        self.assertEqual(summary(exchange(ASK)), ('mistral', ['Claude is not set up: answering with Mistral']))

    def test_auto_moves_on_when_the_first_engine_fails(self):
        self.online = {'claude.test', 'mistral.test'}
        self.serve(engines(claude={'fail': 'not logged in'}))
        replies = exchange(ASK)
        self.assertEqual([r['engine'] for r in replies if r['type'] == 'start'], ['claude', 'mistral'])
        self.assertEqual(summary(replies), ('mistral', ['Claude failed (not logged in): answering with Mistral']))

    def test_nothing_usable(self):
        self.serve(engines(local={'ready': False}))
        replies = exchange(ASK)
        self.assertEqual(replies[-1]['code'], 'no_engine')
        self.assertIn('Local is not set up', replies[-1]['message'])

    def test_place_setting_and_forced_engine(self):
        self.online = {'claude.test', 'mistral.test'}
        config.change({'places': {'intel': 'mistral'}})
        fake = engines()
        self.serve(fake)
        self.assertEqual(summary(exchange({**ASK, 'place': 'intel'})), ('mistral', []))
        self.assertEqual(summary(exchange({**ASK, 'place': 'intel', 'engine': 'local'})), ('local', []))
        replies = exchange({**ASK, 'engine': 'local:qwen2.5-0.5b'})
        self.assertEqual((replies[0]['engine'], replies[0]['model']), ('local', 'qwen2.5-0.5b'))

    def test_forced_engine_does_not_fall_back(self):
        self.serve(engines())
        self.assertEqual(summary(exchange({**ASK, 'engine': 'claude'})), ('no_engine', []))

    def test_local_only(self):
        self.online = {'claude.test', 'mistral.test'}
        config.change({'local_only': True})
        fake = engines()
        self.serve(fake)
        self.assertEqual(summary(exchange(ASK)), ('local', []))
        engine, notes = summary(exchange({**ASK, 'engine': 'claude'}))
        self.assertEqual(engine, 'local')
        self.assertEqual(notes, ['Claude is off (nothing leaves this laptop): answering with Local'])
        self.assertEqual(fake['claude'].asked + fake['mistral'].asked, [])


class Battery(SandboxCase):
    def power(self, online):
        root = self.home / 'power'
        for name, kind, value in (('AC', 'Mains', online), ('BAT0', 'Battery', None)):
            (root / name).mkdir(parents=True, exist_ok=True)
            (root / name / 'type').write_text(kind + '\n')
            if value is not None:
                (root / name / 'online').write_text(value + '\n')
        return root

    def test_charger_is_read(self):
        self.assertFalse(on_battery(self.power('1')))
        self.assertTrue(on_battery(self.power('0')))
        self.assertFalse(on_battery(self.home / 'no-such-folder'))

    def test_model_follows_the_power_state(self):
        cfg = {'local_model': 'big', 'local_model_battery': 'small'}
        real = models.POWER
        try:
            models.POWER = self.power('1')
            self.assertEqual(chosen(cfg), 'big')
            models.POWER = self.power('0')
            self.assertEqual(chosen(cfg), 'small')
            self.assertEqual(chosen({'local_model': 'big', 'local_model_battery': None}), 'big')
            self.assertEqual(chosen(cfg, forced='other'), 'other')
        finally:
            models.POWER = real

    def test_without_a_setting_the_smallest_downloaded_model(self):
        self.assertIsNone(chosen(config.load()))
        for model_id in ('mistral-7b-instruct', 'llama-3.2-1b'):
            models.model_path(model_id).parent.mkdir(parents=True, exist_ok=True)
            models.model_path(model_id).write_bytes(b'gguf')
        self.assertEqual(chosen(config.load()), 'llama-3.2-1b')


if __name__ == '__main__':
    unittest.main()


class SavedSettings(unittest.TestCase):
    """a damaged settings file never opens the way to the cloud"""

    def setUp(self):
        self.home = tempfile.mkdtemp(dir='/tmp')
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.old = {k: os.environ.get(k) for k in ('XDG_CONFIG_HOME',)}
        os.environ['XDG_CONFIG_HOME'] = self.home
        self.addCleanup(lambda: [os.environ.pop(k) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in self.old.items()])

    def write(self, text):
        path = config.paths.config_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_an_unknown_key_keeps_the_rest(self):
        self.write('{"local_only": true, "new_thing": 1, "places": {"dialer": "local", "attic": "claude"}}')
        cfg = config.load()
        self.assertTrue(cfg['local_only'])
        self.assertEqual(cfg['places']['dialer'], 'local')

    def test_a_broken_file_means_nothing_leaves(self):
        for text in ('{not json', '[]', '{"local_only": "yes"}'):
            self.write(text)
            self.assertTrue(config.load()['local_only'], text)

    def test_no_file_is_the_defaults(self):
        self.assertFalse(config.load()['local_only'])

    def test_a_model_id_must_be_in_the_list(self):
        self.assertFalse(config.valid_engine('local:../../x'))
        self.assertTrue(config.valid_engine('local:qwen2.5-0.5b'))


class WhatIsSent(unittest.TestCase):
    def test_turns(self):
        from zai.engines import in_turns
        talk = [{'role': 'assistant', 'content': 'stray'}, {'role': 'user', 'content': 'a'},
                {'role': 'user', 'content': 'b'}, {'role': 'assistant', 'content': ''},
                {'role': 'assistant', 'content': 'B', 'engine': 'local'}, {'role': 'user', 'content': 'c'}]
        self.assertEqual(in_turns(talk), [{'role': 'user', 'content': 'b'}, {'role': 'assistant', 'content': 'B'},
                                          {'role': 'user', 'content': 'c'}])

    def test_local_answers_stay_on_the_laptop(self):
        from zai.engines import in_turns, without_local_answers
        talk = [{'role': 'user', 'content': 'private?'}, {'role': 'assistant', 'content': 'secret', 'engine': 'local'},
                {'role': 'user', 'content': 'open?'}, {'role': 'assistant', 'content': 'fine', 'engine': 'claude'},
                {'role': 'user', 'content': 'now'}]
        sent = in_turns(without_local_answers(talk))
        self.assertEqual([m['content'] for m in sent], ['open?', 'fine', 'now'])

    def test_a_small_model_gets_the_newest(self):
        from zai.engines import newest_that_fit
        talk = [{'role': 'user', 'content': 'x' * 50}, {'role': 'assistant', 'content': 'y' * 50},
                {'role': 'user', 'content': 'z' * 50}]
        self.assertEqual(len(newest_that_fit(talk, 60)), 1)
        self.assertEqual(len(newest_that_fit(talk, 500)), 3)
        self.assertEqual(len(newest_that_fit(talk, 0)), 1)
