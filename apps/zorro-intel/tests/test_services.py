"""The zorro-ai client, the search client, one whole question, and the small helpers."""
import sys
import threading
import unittest
from types import SimpleNamespace

from fakes import SandboxCase, hit, wait_until

from intel import ai, asking, chat, config, jobs, pull, search, services, wording


class AIClient(SandboxCase):
    def collect(self, request=None):
        answer = ai.Answer()
        for reply in ai.Call(request or ai.ask_request([{'role': 'user', 'content': 'q'}], [])).replies():
            answer.take(reply)
        return answer

    def test_no_service(self):
        with self.assertRaises(ai.NoService):
            ai.status()
        self.assertFalse(ai.running())

    def test_streaming(self):
        fake = self.fake_ai()
        context = [{'path': '/n/a.md', 'text': 'words'}]
        answer = self.collect(ai.ask_request([{'role': 'user', 'content': 'q'}], context))
        self.assertEqual(answer.text, 'Hello from the fake')
        self.assertTrue(answer.done)
        self.assertEqual((answer.engine, answer.model, answer.sent), ('claude', 'claude-test-exact', ['/n/a.md']))
        self.assertEqual(fake.requests[0]['place'], 'intel')
        self.assertEqual(fake.requests[0]['context'], context)

    def test_note_and_second_start(self):
        self.fake_ai(mode='fallback')
        answer = self.collect()
        self.assertEqual(answer.engine, 'mistral')
        self.assertEqual(answer.model, 'mistral-test-exact')
        self.assertIn('answering with Mistral', answer.note)
        self.assertEqual(answer.text, 'Hello from the fake')

    def test_error(self):
        self.fake_ai(mode='error')
        answer = self.collect()
        self.assertFalse(answer.done)
        self.assertIn('not installed', answer.error)

    def test_cancel_hangs_up(self):
        fake = self.fake_ai(mode='slow')
        call = ai.Call(ai.ask_request([{'role': 'user', 'content': 'q'}], []))
        answer, got = ai.Answer(), threading.Event()

        def read():
            for reply in call.replies():
                answer.take(reply)
                if answer.text:
                    got.set()

        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        self.assertTrue(got.wait(5))
        call.cancel()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(answer.done)
        self.assertIsNone(answer.error)
        self.assertTrue(fake.hung_up.wait(5))

    def test_status_models_settings(self):
        fake = self.fake_ai()
        self.assertTrue(ai.running())
        self.assertEqual(set(ai.status()['engines']), {'claude', 'mistral', 'local'})
        self.assertEqual(len(ai.models()), 3)
        reply = ai.change({'places': {'intel': 'local'}, 'local_only': True})
        self.assertEqual(reply['settings']['places']['intel'], 'local')
        self.assertTrue(fake.settings['local_only'])
        reply = ai.change(wording.claude_change('devs', 'opus'))
        self.assertEqual(reply['settings']['claude_models'], {'dialer': 'haiku', 'intel': 'sonnet', 'devs': 'opus'})
        self.assertEqual(ai.change({'colour': 'blue'})['type'], 'error')


class SearchClient(SandboxCase):
    def test_not_running(self):
        self.assertIsNone(search.ask('anything'))
        self.assertFalse(search.running())

    def test_hits(self):
        fake = self.fake_search([hit('/n/a.md'), hit('/n/b.md'), 'junk', {'title': 'no path'}])
        self.assertTrue(search.running())
        self.assertEqual([h['path'] for h in search.ask('nasi', n=30)], ['/n/a.md', '/n/b.md'])
        self.assertEqual(fake.requests[-1], {'q': 'nasi', 'n': 30})
        self.assertEqual(len(search.ask('nasi', n=1)), 1)


class WholeQuestion(SandboxCase):
    def setUp(self):
        super().setUp()
        self.dir = self.notes('a.md', 'b.md')
        config.add_folder(str(self.dir))
        (self.home / 'out.md').write_text('outside')
        self.hits = [hit(self.dir / 'a.md', 'inside words'), hit(self.home / 'out.md', 'outside words')]

    def test_answer_is_stored_with_engine_and_sources(self):
        fake = self.fake_ai()
        self.fake_search(self.hits)
        done = asking.Asking('what did I write').run()
        self.assertEqual(done.stage, 'end')
        request = fake.requests[0]
        self.assertEqual(request['context'], [{'path': str(self.dir / 'a.md'), 'text': 'inside words'}])
        self.assertEqual(request['messages'], [{'role': 'user', 'content': 'what did I write'}])
        question, answer = chat.load()
        self.assertEqual(question['content'], 'what did I write')
        self.assertEqual((answer['engine'], answer['sent']), ('claude', [str(self.dir / 'a.md')]))
        self.assertNotIn('partial', answer)

    def test_search_down_sends_nothing_and_says_so(self):
        fake = self.fake_ai()
        done = asking.Asking('q').run()
        self.assertEqual(fake.requests[0]['context'], [])
        self.assertIn('Search is not running', done.notes)
        self.assertIn('Search is not running', chat.load()[-1]['note'])

    def test_ai_down(self):
        done = asking.Asking('q').run()
        self.assertTrue(done.no_service)
        self.assertEqual([m['role'] for m in chat.load()], ['user'])

    def test_error_stores_no_answer(self):
        self.fake_ai(mode='error')
        done = asking.Asking('q').run()
        self.assertIn('not installed', done.answer.error)
        self.assertEqual([m['role'] for m in chat.load()], ['user'])

    def test_cancel_stores_what_arrived_as_partial(self):
        fake = self.fake_ai(mode='slow')
        one = asking.Asking('q')
        thread = threading.Thread(target=one.run, daemon=True)
        thread.start()
        self.assertTrue(wait_until(lambda: 'more' in one.answer.text))
        one.cancel()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertTrue(fake.hung_up.wait(5))
        answer = chat.load()[-1]
        self.assertIs(answer['partial'], True)
        self.assertTrue(answer['content'].startswith('Hello from the fake'))

    def test_hangup_without_done_is_partial(self):
        self.fake_ai(mode='hangup')
        done = asking.Asking('q').run()
        self.assertIn('hung up', done.answer.error)
        self.assertIs(chat.load()[-1]['partial'], True)

    def test_about_one_file(self):
        fake = self.fake_ai()
        asking.Asking('summarise', about=str(self.dir / 'b.md')).run()
        self.assertEqual([c['path'] for c in fake.requests[0]['context']], [str(self.dir / 'b.md')])
        asking.Asking('summarise', about=str(self.home / 'out.md')).run()
        self.assertEqual(fake.requests[1]['context'], [])

    def test_at_most_20_messages_go_along(self):
        for i in range(15):
            chat.append(chat.question(f'q{i}'))
            chat.append(chat.answer(f'a{i}', 'claude', []))
        fake = self.fake_ai()
        asking.Asking('newest').run()
        sent = fake.requests[0]['messages']
        self.assertLessEqual(len(sent), 20)
        self.assertEqual(sent[-1]['content'], 'newest')


class Helpers(SandboxCase):
    def test_jobs_post_results_and_stop_on_close(self):
        posted = []
        work = jobs.Jobs(lambda fn, *a: posted.append((fn, a)))
        work.run(lambda: 7, 'done').join(3)
        self.assertEqual(posted, [('done', (7,))])
        release, cancelled = threading.Event(), []
        thread = work.run(lambda: release.wait(5), 'late', cancel=lambda: (cancelled.append(1), release.set()))
        work.close(wait=3)
        self.assertEqual(cancelled, [1])
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(posted), 1)
        self.assertIsNone(work.run(lambda: 1))

    def test_start_service(self):
        calls = []

        def run(args, **kw):
            calls.append(args)
            return SimpleNamespace(returncode=1, stderr='Unit zorro-ai.service not found.\n')
        ok, said = services.start(services.AI, run)
        self.assertEqual(calls, [['systemctl', '--user', 'start', 'zorro-ai.service']])
        self.assertFalse(ok)
        self.assertIn('not found', said)
        self.assertEqual(services.start(services.SEARCH, lambda a, **kw: SimpleNamespace(returncode=0, stderr='')),
                         (True, 'Started'))

    def test_progress_lines(self):
        self.assertEqual(pull.fraction('small-1b:    120.0 MB  40.0%'), 0.4)
        self.assertIsNone(pull.fraction('small-1b downloaded to /x'))
        self.assertEqual(list(pull.lines_of([b'a: 1.0 MB 1.0%\ra: 2.0 MB', b' 2.0%\rdone\n'])),
                         ['a: 1.0 MB 1.0%', 'a: 2.0 MB 2.0%', 'done'])

    def test_pull_run_and_cancel(self):
        script = self.home / 'fake-zorro-ai'
        script.write_text('import sys, time\n'
                          'sys.stderr.write("\\rm: 5.0 MB 50.0%\\n"); sys.stderr.flush()\n'
                          'if sys.argv[1] == "hang": time.sleep(30)\n'
                          'print("m downloaded")\n')
        seen = []
        run = pull.Run([str(script), 'pull', 'm'], seen.append, command=sys.executable)
        self.assertEqual(run.run(), (True, 'm downloaded'))
        self.assertEqual(pull.fraction(seen[0]), 0.5)
        slow = pull.Run([str(script), 'hang'], seen.append, command=sys.executable)
        result = []
        thread = threading.Thread(target=lambda: result.append(slow.run()), daemon=True)
        thread.start()
        self.assertTrue(wait_until(lambda: len(seen) >= 3))
        slow.cancel()
        thread.join(5)
        self.assertEqual(result, [(False, 'Stopped')])

    def test_page_argument(self):
        from intel import cli
        self.assertIsNone(cli.page_of([]))
        self.assertEqual(cli.page_of(['--page', 'models']), 'models')
        self.assertEqual(cli.page_of(['--page=key']), 'key')
        for bad in (['--page'], ['--page', 'nope'], ['ask'], ['--page', 'ask', 'more']):
            with self.assertRaises(ValueError):
                cli.page_of(bad)
        self.assertLessEqual(len(cli.PAGES), 7)

    def test_plain_words(self):
        status = ai_status()
        self.assertEqual(wording.engine_state('claude', status['claude']), ('on', 'Claude: ready'))
        self.assertIn('no key yet', wording.engine_state('mistral', status['mistral'])[1])
        self.assertIn('not installed', wording.engine_state('local', status['local'])[1])
        self.assertIn('nothing leaves', wording.engine_state('claude', status['claude'], local_only=True)[1])
        self.assertTrue(wording.local_engine_missing({'engines': status}))
        self.assertFalse(wording.local_engine_missing({'engines': {'local': {'ready': True, 'why': ''}}}))
        self.assertEqual(wording.choice('local:small-1b'), 'local')
        self.assertEqual(wording.answered_by({'engine': 'local', 'model': 'm', 'partial': True, 'sent': []}),
                         'On this laptop · m · stopped early · no files sent')
        self.assertEqual(wording.score_fraction(0.85), 0.5)
        self.assertEqual(wording.plain_error('Local has no model yet (run: zorro-ai models, then zorro-ai pull ID); Claude is off'),
                         'Local has no model yet; Claude is off')
        self.assertEqual(wording.plain_error('plain'), 'plain')

    def test_claude_model_choices(self):
        options = wording.claude_options('dialer')
        self.assertEqual(list(options), ['haiku', 'sonnet', 'opus', 'default'])
        self.assertEqual([k for k, v in options.items() if 'suggested' in v], ['haiku'])
        self.assertEqual([k for k, v in wording.claude_options('intel').items() if 'suggested' in v], ['sonnet'])
        self.assertEqual([k for k, v in wording.claude_options('intel', {'intel': 'opus'}).items()
                          if 'suggested' in v], ['opus'])
        self.assertEqual(wording.claude_choice({'claude_models': {'intel': 'opus'}}, 'intel'), 'opus')
        self.assertEqual(wording.claude_choice({'claude_models': {'intel': 'gpt'}}, 'intel'), 'sonnet')
        self.assertEqual(wording.claude_choice({}, 'dialer'), 'haiku')
        self.assertEqual(wording.claude_change('dialer', 'default'), {'claude_models': {'dialer': 'default'}})


def ai_status():
    from fakes import ENGINES
    return ENGINES


if __name__ == '__main__':
    unittest.main()
