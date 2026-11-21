"""The socket protocol with fake engines: round trip, streaming, cancel, settings, status, models."""
import json
import os
import stat
import unittest

from fakes import FakeEngine, SandboxCase, ask_socket, exchange

from zai import paths

ASK = {'op': 'ask', 'place': 'dialer', 'engine': None,
       'messages': [{'role': 'user', 'content': 'hi'}],
       'context': [{'path': '/notes/a.md', 'text': 'alpha'}]}


def three(**claude):
    return {'claude': FakeEngine('claude', host='claude.test', **claude),
            'mistral': FakeEngine('mistral', host='mistral.test'),
            'local': FakeEngine('local')}


class Protocol(SandboxCase):
    def test_socket_is_private(self):
        server = self.serve(three())
        self.assertEqual(stat.S_IMODE(os.stat(server.path).st_mode), 0o600)

    def test_ask_round_trip(self):
        engines = three()
        self.online = {'claude.test'}
        self.serve(engines)
        replies = exchange(ASK)
        self.assertEqual([r['type'] for r in replies], ['start', 'text', 'text', 'done'])
        self.assertEqual(replies[0], {'type': 'start', 'engine': 'claude', 'model': 'haiku',
                                      'sent': ['/notes/a.md']})
        self.assertEqual(''.join(r['delta'] for r in replies if r['type'] == 'text'), 'Hello world')
        self.assertEqual(replies[-1]['engine'], 'claude')
        self.assertIsInstance(replies[-1]['seconds'], float)
        self.assertEqual(engines['claude'].asked[0], (ASK['messages'], ASK['context']))

    def test_text_arrives_while_the_engine_still_runs(self):
        engines = three(endless=True)
        self.online = {'claude.test'}
        self.serve(engines)
        sock, lines = ask_socket(ASK)
        with sock, lines:
            self.assertEqual(json.loads(lines.readline())['type'], 'start')
            self.assertEqual(json.loads(lines.readline()), {'type': 'text', 'delta': 'Hello'})
            self.assertFalse(engines['claude'].stopped.is_set())

    def test_hanging_up_cancels_the_answer(self):
        engines = three(endless=True)
        self.online = {'claude.test'}
        self.serve(engines)
        sock, lines = ask_socket(ASK)
        lines.readline()
        lines.readline()
        lines.close()
        sock.close()
        self.assertTrue(engines['claude'].stopped.wait(3))

    def test_half_close_does_not_cancel(self):
        self.online = {'claude.test'}
        self.serve(three())
        sock, lines = ask_socket(ASK)
        sock.shutdown(1)
        with sock, lines:
            self.assertEqual(json.loads(lines.readlines()[-1])['type'], 'done')

    def test_bad_requests(self):
        self.serve(three())
        self.assertEqual(exchange({'op': 'dance'})[0]['code'], 'bad_request')
        self.assertEqual(exchange({'op': 'ask', 'place': 'moon', 'messages': [{}]})[0]['code'], 'bad_request')
        self.assertEqual(exchange({'op': 'ask', 'messages': []})[0]['code'], 'bad_request')
        sock, lines = ask_socket('not json at all')
        with sock, lines:
            self.assertEqual(json.loads(lines.readline())['code'], 'bad_request')

    def test_engine_error_is_reported(self):
        self.online = {'claude.test'}
        self.serve(three(fail='boom'))
        replies = exchange({**ASK, 'engine': 'claude'})
        self.assertEqual(replies[-1]['type'], 'error')
        self.assertEqual(replies[-1]['code'], 'engine_failed')
        self.assertIn('boom', replies[-1]['message'])

    def test_settings_are_written(self):
        self.serve(three())
        reply = exchange({'op': 'settings', 'set': {'places': {'dialer': 'local'}, 'local_only': True,
                                                    'local_model_battery': 'qwen2.5-0.5b'}})[0]
        self.assertEqual(reply['settings']['places'], {'dialer': 'local', 'intel': 'auto', 'devs': 'claude'})
        on_disk = json.loads(paths.config_file().read_text())
        self.assertEqual(on_disk, reply['settings'])
        self.assertTrue(on_disk['local_only'])
        self.assertEqual(stat.S_IMODE(paths.config_file().stat().st_mode), 0o600)
        self.assertEqual(os.listdir(paths.config_dir()), ['config.json'])
        self.assertTrue(str(paths.config_file()).startswith(str(self.home)))

    def test_bad_settings_change_nothing(self):
        self.serve(three())
        for bad in ({'places': {'moon': 'auto'}}, {'places': {'dialer': 'gpt'}}, {'local_only': 'yes'}, {'x': 1}):
            self.assertEqual(exchange({'op': 'settings', 'set': bad})[0]['code'], 'bad_setting')
        self.assertFalse(paths.config_file().exists())

    def test_status_and_models(self):
        self.online = {'claude.test'}
        self.serve(three())
        status = exchange({'op': 'status'})[0]
        self.assertEqual(status['engines']['claude'], {'ready': True, 'why': '', 'model': 'claude-model'})
        self.assertEqual(status['engines']['mistral']['why'], 'not reachable')
        self.assertEqual(status['settings']['places']['devs'], 'claude')
        models = exchange({'op': 'models'})[0]['models']
        self.assertGreaterEqual(len(models), 5)
        self.assertEqual(set(models[0]), {'id', 'name', 'family', 'size', 'ram', 'good_for', 'installed', 'speed'})
        self.assertFalse(any(m['installed'] for m in models))
        self.assertTrue(any(m['family'] == 'mistral' for m in models))


if __name__ == '__main__':
    unittest.main()
