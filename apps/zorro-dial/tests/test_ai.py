"""The zorro-ai client and the chat built on it, against a fake service that speaks the protocol."""
import tempfile
import threading
import time
import unittest
from pathlib import Path

import helper  # noqa: F401
from dial import aiclient, chat, chatfile
from fake_ai import ANSWER, FakeAi

TEXT = ''.join(e['delta'] for e in ANSWER if e['type'] == 'text')


def wait_for(done, seconds=5):
    end = time.time() + seconds
    while not done() and time.time() < end:
        time.sleep(0.01)
    return done()


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(dir='/tmp')      # short: a socket path has a limit
        self.sock = Path(self.dir.name) / 'ai.sock'
        self.file = Path(self.dir.name) / 'chat.json'
        self.service = None

    def tearDown(self):
        if self.service:
            self.service.stop()
        self.dir.cleanup()

    def serve(self, **kw):
        self.service = FakeAi(self.sock, **kw)
        return self.service


class ClientTest(Base):
    def test_the_answer_streams_in(self):
        service = self.serve()
        events, done = [], threading.Event()

        def on_event(e):
            events.append(e)
            if e['type'] in ('done', 'error'):
                done.set()
        aiclient.Ask([{'role': 'user', 'content': 'hello'}], on_event, self.sock).start()
        self.assertTrue(done.wait(5))
        self.assertEqual(events, ANSWER)
        request = service.requests[0]
        self.assertEqual((request['op'], request['place'], request['context'], request['engine']),
                         ('ask', 'dialer', [], None))
        self.assertEqual(request['messages'], [{'role': 'user', 'content': 'hello'}])

    def test_cancel_closes_the_connection_and_says_no_more(self):
        service = self.serve(delay=0.05)
        events = []
        ask = aiclient.Ask([{'role': 'user', 'content': 'hello'}], events.append, self.sock).start()
        self.assertTrue(wait_for(lambda: any(e['type'] == 'text' for e in events)))
        ask.cancel()
        seen = len(events)
        self.assertTrue(service.hung_up.wait(5))                # the service notices: the answer stops there
        time.sleep(0.1)
        self.assertEqual(len(events), seen)
        self.assertNotIn('done', [e['type'] for e in events])

    def test_no_service(self):
        events = []
        aiclient.Ask([], events.append, self.sock).start()
        self.assertTrue(wait_for(lambda: events))
        self.assertEqual((events[0]['type'], events[0]['code'], events[0]['message']),
                         ('error', 'no_service', aiclient.NO_SERVICE))
        self.assertFalse(aiclient.available(self.sock))

    def test_available_and_an_error_from_the_service(self):
        self.serve(replies=[{'type': 'error', 'code': 'no_engine', 'message': 'No engine is ready.'}])
        self.assertTrue(aiclient.available(self.sock))
        events = []
        aiclient.Ask([], events.append, self.sock).start()
        self.assertTrue(wait_for(lambda: events))
        self.assertEqual(events[0]['code'], 'no_engine')

    def test_a_service_that_stops_early_is_an_error(self):
        self.serve(replies=ANSWER[:3])
        events = []
        aiclient.Ask([], events.append, self.sock).start()
        self.assertTrue(wait_for(lambda: events and events[-1]['type'] == 'error'))
        self.assertEqual(events[-1]['code'], 'lost')


class ChatTest(Base):
    def new_chat(self):
        return chat.Chat(lambda fn: fn(), self.file, self.sock)

    def test_question_and_answer_end_up_in_the_file(self):
        self.serve(delay=0.02)
        c = self.new_chat()
        c.open()
        c.text = '  What is a dial?  '
        self.assertTrue(c.send())
        self.assertFalse(c.send())                              # one answer at a time
        self.assertEqual((c.text, c.asked, c.busy), ('', 'What is a dial?', True))
        self.assertTrue(wait_for(lambda: c.answer))
        self.assertEqual(c.blocks()[0], ('q', 'What is a dial?'))
        self.assertTrue(TEXT.startswith(c.blocks()[1][1]))      # the answer so far
        self.assertTrue(wait_for(lambda: not c.busy))
        saved = chatfile.load(self.file)
        self.assertEqual([(m['role'], m['content']) for m in saved],
                         [('user', 'What is a dial?'), ('assistant', TEXT)])
        self.assertEqual((saved[1]['engine'], saved[1]['note']),
                         ('mistral', 'Claude not reachable: answering with Mistral'))
        self.assertEqual(c.blocks(), [('q', 'What is a dial?'), ('a', TEXT),
                                      ('meta', 'mistral · Claude not reachable: answering with Mistral')])

    def test_only_the_last_twenty_messages_are_sent(self):
        service = self.serve()
        chatfile.write([chatfile.message('user' if i % 2 == 0 else 'assistant', str(i)) for i in range(40)], self.file)
        c = self.new_chat()
        c.open()
        c.text = 'next'
        c.send()
        self.assertTrue(wait_for(lambda: not c.busy))
        asked = [r for r in service.requests if r.get('op') == 'ask'][0]['messages']
        self.assertEqual(len(asked), 20)
        self.assertEqual(asked[-1], {'role': 'user', 'content': 'next'})
        self.assertEqual(len(chatfile.load(self.file)), 42)

    def test_no_service_is_one_calm_line_and_the_question_stays(self):
        c = self.new_chat()
        c.open()
        self.assertTrue(wait_for(lambda: c.problem))
        self.assertEqual(c.problem, aiclient.NO_SERVICE)
        c.text = 'hello?'
        c.send()
        self.assertTrue(wait_for(lambda: not c.busy))
        self.assertEqual((c.problem, c.text, c.blocks()), (aiclient.NO_SERVICE, 'hello?', []))
        self.assertEqual(chatfile.load(self.file), [])

    def test_cancel_puts_the_question_back_and_saves_nothing(self):
        service = self.serve(delay=0.05)
        c = self.new_chat()
        c.text = 'long one'
        c.send()
        self.assertTrue(wait_for(lambda: c.answer))
        c.cancel()
        self.assertEqual((c.busy, c.text, c.answer), (False, 'long one', ''))
        self.assertTrue(service.hung_up.wait(5))
        time.sleep(0.1)
        self.assertEqual(c.blocks(), [])
        self.assertEqual(chatfile.load(self.file), [])

    def test_views(self):
        chatfile.write([chatfile.message('user', 'q1'), chatfile.message('assistant', 'a1', engine='claude'),
                        chatfile.message('user', 'q2'), chatfile.message('assistant', 'a2', engine='local')], self.file)
        c = self.new_chat()
        c.messages = chatfile.load(self.file)
        self.assertEqual([t for _, t in c.blocks('history')], ['q1', 'a1', 'claude', 'q2', 'a2', 'local'])
        self.assertEqual([t for _, t in c.blocks('last')], ['q2', 'a2', 'local'])
        c.asked = 'q3'
        self.assertEqual(c.blocks('last'), [('q', 'q3'), ('a', '…')])

    def test_new_chat(self):
        self.serve()
        chatfile.write([chatfile.message('user', 'old')], self.file)
        c = self.new_chat()
        c.open()
        c.new_chat()
        self.assertEqual((c.messages, c.blocks(), chatfile.load(self.file)), ([], [], []))
        self.assertEqual(len(list((self.file.parent / 'chats').glob('*.json'))), 1)


if __name__ == '__main__':
    unittest.main()
