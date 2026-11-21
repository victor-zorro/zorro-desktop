"""The Claude model per place: suggestions, settings, the --model flag, forced model, concurrency."""
import json
import os
import threading
import unittest

from fakes import FAKE_CLAUDE, SandboxCase, exchange, read_log, write_program

from zai import config, paths
from zai.engines.claude import Claude

SUGGESTED = {'dialer': 'haiku', 'intel': 'sonnet', 'devs': 'sonnet'}


def ask(place, text='hi', **more):
    return {'op': 'ask', 'place': place, 'engine': 'claude', 'messages': [{'role': 'user', 'content': text}], **more}


class Settings(SandboxCase):
    def test_defaults_are_the_suggestions(self):
        self.assertEqual(config.load()['claude_models'], SUGGESTED)
        self.assertEqual(config.SUGGESTED_CLAUDE, SUGGESTED)

    def test_a_bad_value_falls_back_for_that_place_only(self):
        paths.config_file().parent.mkdir(parents=True, exist_ok=True)
        paths.config_file().write_text(json.dumps({'claude_models': {'dialer': 'gpt', 'intel': 'opus', 'moon': 'opus'}}))
        self.assertEqual(config.load()['claude_models'], {**SUGGESTED, 'intel': 'opus'})
        paths.config_file().write_text(json.dumps({'claude_models': 'opus', 'local_only': False}))
        self.assertEqual(config.load()['claude_models'], SUGGESTED)

    def test_unreadable_file_still_means_local_only(self):
        paths.config_file().parent.mkdir(parents=True, exist_ok=True)
        paths.config_file().write_text('{broken')
        cfg = config.load()
        self.assertTrue(cfg['local_only'])
        self.assertEqual(cfg['claude_models'], SUGGESTED)

    def test_settings_op_writes_one_place(self):
        self.serve({'claude': Claude('x')})
        reply = exchange({'op': 'settings', 'set': {'claude_models': {'devs': 'opus'}}})[0]
        self.assertEqual(reply['settings']['claude_models'], {**SUGGESTED, 'devs': 'opus'})
        self.assertEqual(json.loads(paths.config_file().read_text())['claude_models']['devs'], 'opus')
        for bad in ({'claude_models': {'devs': 'gpt'}}, {'claude_models': {'moon': 'opus'}}, {'claude_models': 'opus'}):
            self.assertEqual(exchange({'op': 'settings', 'set': bad})[0]['code'], 'bad_setting')

    def test_status_carries_choices_and_suggestions(self):
        self.serve({'claude': Claude('zai-no-such-program')})
        status = exchange({'op': 'status'})[0]
        self.assertEqual(status['settings']['claude_models'], SUGGESTED)
        self.assertEqual(status['claude_suggested'], SUGGESTED)


class Flag(SandboxCase):
    def setUp(self):
        super().setUp()
        self.log = self.home / 'claude.log'
        os.environ['FAKE_LOG'] = str(self.log)
        self.cleanups.append(lambda: os.environ.pop('FAKE_LOG', None))
        self.online = {'api.anthropic.com'}
        self.serve({'claude': Claude(str(write_program(self.home / 'bin' / 'claude', FAKE_CLAUDE)))})

    def flag(self, replies):
        argv = read_log(self.log)[-1]['argv']
        return argv[argv.index('--model') + 1] if '--model' in argv else None

    def test_each_place_gets_its_model(self):
        for place, expect in (('dialer', 'haiku'), ('intel', 'sonnet'), ('devs', 'sonnet')):
            replies = exchange(ask(place))
            self.assertEqual(self.flag(replies), expect)
            self.assertEqual(replies[0]['model'], f'claude {expect}')
            self.assertEqual(replies[0]['engine'], 'claude')
            self.assertEqual(replies[-1]['model'], 'claude-fake-1')

    def test_default_adds_nothing(self):
        exchange({'op': 'settings', 'set': {'claude_models': {'dialer': 'default'}}})
        replies = exchange(ask('dialer'))
        self.assertIsNone(self.flag(replies))
        self.assertEqual(replies[0]['model'], 'claude')

    def test_a_forced_model_wins(self):
        self.assertEqual(self.flag(exchange(ask('dialer', model='opus'))), 'opus')
        self.assertIsNone(self.flag(exchange(ask('dialer', model='default'))))
        self.assertEqual(exchange(ask('dialer', model='gpt'))[0]['code'], 'bad_request')

    def test_concurrent_answers_do_not_mix(self):
        results = {}

        def run(place):
            results[place] = exchange(ask(place, f'SLOW {place}'))

        threads = [threading.Thread(target=run, args=(p,)) for p in ('dialer', 'intel')]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        seen = {c['prompt'].split()[-1]: c['argv'][c['argv'].index('--model') + 1] for c in read_log(self.log)
                if 'SLOW' in c['prompt']}
        self.assertEqual(seen, {'dialer': 'haiku', 'intel': 'sonnet'})
        self.assertEqual({p: r[0]['model'] for p, r in results.items()},
                         {'dialer': 'claude haiku', 'intel': 'claude sonnet'})


if __name__ == '__main__':
    unittest.main()
