"""The real engines against fakes: a fake claude program, a fake Mistral server, a fake llama-server."""
import json
import os
import threading
import unittest

from fakes import (FAKE_CLAUDE, FAKE_LLAMA, FakeEngine, FakeMistral, SandboxCase, alive, ask_socket,
                   exchange, read_log, wait_until, write_program)

from zai import config, models, paths
from zai.engines import EngineError
from zai.engines.claude import Claude, prompt_text
from zai.engines.local import Local
from zai.engines.mistral import Mistral
from zai.local_server import LlamaServer

HI = [{'role': 'user', 'content': 'hi'}]
NOTE = [{'path': '/notes/a.md', 'text': 'alpha beta'}]


def collect(engine, messages=HI, context=()):
    pieces = []
    model = engine.ask(messages, list(context), pieces.append, threading.Event())
    return ''.join(pieces), model


class ClaudeEngine(SandboxCase):
    def setUp(self):
        super().setUp()
        self.log = self.home / 'claude.log'
        os.environ['FAKE_LOG'] = str(self.log)
        self.cleanups.append(lambda: os.environ.pop('FAKE_LOG', None))
        self.program = str(write_program(self.home / 'bin' / 'claude', FAKE_CLAUDE))

    def test_ready_looks_on_path(self):
        self.assertFalse(Claude(program='zai-no-such-program').ready()[0])
        os.environ['PATH'] = f'{self.home / "bin"}:{os.environ["PATH"]}'
        self.assertEqual(Claude().ready(), (True, ''))

    def test_stream_is_parsed(self):
        text, model = collect(Claude(self.program), context=NOTE)
        self.assertEqual((text, model), ('OK', 'claude-fake-1'))
        call = read_log(self.log)[0]
        self.assertEqual(call['cwd_files'], [])
        self.assertIn('alpha beta', call['prompt'])
        self.assertIn('/notes/a.md', call['prompt'])
        argv = call['argv']
        self.assertEqual(argv[argv.index('--tools') + 1], '')
        for flag in ('-p', '--verbose', '--include-partial-messages', '--strict-mcp-config', '--system-prompt'):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index('--output-format') + 1], 'stream-json')

    def test_error_result_raises(self):
        with self.assertRaises(EngineError) as raised:
            collect(Claude(self.program), [{'role': 'user', 'content': 'FAIL'}])
        self.assertIn('Not logged in', str(raised.exception))

    def test_conversation_becomes_one_prompt(self):
        system, prompt = prompt_text([{'role': 'system', 'content': 'Be brief.'},
                                      {'role': 'user', 'content': 'one'},
                                      {'role': 'assistant', 'content': 'two'},
                                      {'role': 'user', 'content': 'three'}], NOTE)
        self.assertTrue(system.endswith('Be brief.'))
        self.assertIn('User: one\n\nAssistant: two\n\nUser: three', prompt)

    def test_hanging_up_ends_the_subprocess(self):
        self.online = {'api.anthropic.com'}
        self.serve({'claude': Claude(self.program), 'local': FakeEngine('local')})
        sock, lines = ask_socket({'op': 'ask', 'engine': 'claude',
                                  'messages': [{'role': 'user', 'content': 'SLOW'}]})
        self.assertEqual(json.loads(lines.readline())['type'], 'start')
        self.assertEqual(json.loads(lines.readline()), {'type': 'text', 'delta': 'O'})
        pid = read_log(self.log)[0]['pid']
        self.assertTrue(alive(pid))
        lines.close()
        sock.close()
        self.assertTrue(wait_until(lambda: not alive(pid), 4), 'the claude subprocess still runs')


class MistralEngine(SandboxCase):
    def setUp(self):
        super().setUp()
        self.fake = FakeMistral()
        self.cleanups.append(self.fake.close)
        self.engine = Mistral(url=self.fake.url)

    def key(self, text=FakeMistral.KEY):
        config.write_atomic(paths.mistral_key_file(), text + '\n')

    def test_not_ready_without_a_key(self):
        ok, why = self.engine.ready()
        self.assertFalse(ok)
        self.assertIn('mistral.key', why)
        with self.assertRaises(EngineError):
            collect(self.engine)
        self.assertEqual(self.fake.requests, [])

    def test_stream(self):
        self.key()
        self.assertEqual(self.engine.ready(), (True, ''))
        text, model = collect(self.engine, context=NOTE)
        self.assertEqual((text, model), ('Bonjour', 'mistral-small-2506'))
        sent = self.fake.requests[0]
        self.assertEqual(sent['path'], '/v1/chat/completions')
        self.assertEqual(sent['headers']['Authorization'], f'Bearer {FakeMistral.KEY}')
        self.assertTrue(sent['body']['stream'])
        self.assertEqual(sent['body']['model'], 'mistral-small-latest')
        self.assertIn('alpha beta', sent['body']['messages'][-1]['content'])
        self.assertTrue(sent['body']['messages'][-1]['content'].endswith('hi'))

    def test_refused_key(self):
        self.key('wrong')
        with self.assertRaises(EngineError) as raised:
            collect(self.engine)
        self.assertIn('401', str(raised.exception))

    def test_stop_closes_the_stream(self):
        self.key()
        stop, pieces = threading.Event(), []

        def on_text(piece):
            pieces.append(piece)
            if len(pieces) == 3:
                stop.set()

        self.engine.ask([{'role': 'user', 'content': 'SLOW'}], [], on_text, stop)
        self.assertLess(len(pieces), 40)
        self.assertTrue(self.fake.hung_up.wait(3), 'the HTTP stream stayed open')

    def test_auto_uses_mistral_when_claude_is_away(self):
        self.key()
        self.online = {'api.mistral.ai'}
        self.serve({'claude': Claude('zai-no-such-program'), 'mistral': self.engine, 'local': FakeEngine('local')})
        replies = exchange({'op': 'ask', 'place': 'dialer', 'messages': HI})
        self.assertEqual(replies[0]['type'], 'note')
        self.assertEqual(replies[-1]['engine'], 'mistral')


class LocalEngine(SandboxCase):
    def setUp(self):
        super().setUp()
        self.log = self.home / 'llama.log'
        os.environ['FAKE_LOG'] = str(self.log)
        self.cleanups.append(lambda: os.environ.pop('FAKE_LOG', None))
        self.engine = Local(LlamaServer(idle=0.4))
        self.cleanups.append(self.engine.shutdown)

    def install(self, *model_ids):
        write_program(paths.llama_dir() / 'llama-server', FAKE_LLAMA)
        for model_id in model_ids:
            models.model_path(model_id).parent.mkdir(parents=True, exist_ok=True)
            models.model_path(model_id).write_bytes(b'gguf')

    def test_not_ready_says_what_to_run(self):
        os.environ['PATH'] = str(self.home / 'bin')
        self.assertIn('install-local', self.engine.ready()[1])
        self.install()
        self.assertIn('pull', self.engine.ready()[1])
        config.change({'local_model': 'llama-3.2-1b'})
        self.assertIn('zorro-ai pull llama-3.2-1b', self.engine.ready()[1])

    def test_starts_on_demand_and_stops_when_idle(self):
        self.install('llama-3.2-1b')
        self.assertEqual(read_log(self.log), [])
        self.assertEqual(collect(self.engine), ('from llama-3.2-1b.gguf', 'llama-3.2-1b'))
        self.assertEqual(collect(self.engine)[0], 'from llama-3.2-1b.gguf')
        started = read_log(self.log)
        self.assertEqual(len(started), 1, 'the second question must reuse the running server')
        self.assertTrue(wait_until(lambda: not alive(started[0]['pid']), 4), 'llama-server stayed after the idle time')
        self.assertEqual(collect(self.engine)[0], 'from llama-3.2-1b.gguf')
        self.assertEqual(len(read_log(self.log)), 2)

    def test_another_model_restarts_the_server(self):
        self.install('llama-3.2-1b', 'ministral-3-3b')
        config.change({'local_model': 'ministral-3-3b'})
        self.assertEqual(collect(self.engine), ('from ministral-3-3b.gguf', 'ministral-3-3b'))
        self.assertEqual(collect(self.engine.use('llama-3.2-1b')), ('from llama-3.2-1b.gguf', 'llama-3.2-1b'))
        first, second = read_log(self.log)
        self.assertFalse(alive(first['pid']))
        self.assertTrue(alive(second['pid']))
        self.engine.shutdown()
        self.assertFalse(alive(second['pid']))

    def test_through_the_service_with_a_forced_model(self):
        self.install('llama-3.2-1b', 'qwen2.5-0.5b')
        server = self.serve({'claude': FakeEngine('claude', host='claude.test'), 'local': self.engine})
        replies = exchange({'op': 'ask', 'engine': 'local:llama-3.2-1b', 'messages': HI})
        self.assertEqual(replies[0]['model'], 'llama-3.2-1b')
        self.assertEqual(replies[-1]['type'], 'done')
        pid = read_log(self.log)[0]['pid']
        server.stop()
        self.assertTrue(wait_until(lambda: not alive(pid), 4), 'stopping the service must stop llama-server')


if __name__ == '__main__':
    unittest.main()
