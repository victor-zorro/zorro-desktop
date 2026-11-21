"""The chat file and the key file."""
import json
import os
import stat
import unittest

from fakes import SandboxCase

from intel import chat, keyfile, paths


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


class Chat(SandboxCase):
    def test_append_and_shape(self):
        chat.append(chat.question('hi'))
        chat.append(chat.answer('hello', 'claude', ['/n/a.md'], model='m1', note='a note'))
        data = json.loads(paths.chat_file().read_text())
        first, second = data['messages']
        self.assertEqual((first['role'], first['content']), ('user', 'hi'))
        self.assertRegex(first['at'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$')
        self.assertEqual(second, {'role': 'assistant', 'content': 'hello', 'at': second['at'], 'engine': 'claude',
                                  'sent': ['/n/a.md'], 'model': 'm1', 'note': 'a note'})
        self.assertEqual(mode(paths.chat_file()), 0o600)
        self.assertEqual(os.listdir(paths.state_dir()), ['chat.json'])

    def test_partial(self):
        chat.append(chat.answer('half an ans', 'local', [], partial=True))
        self.assertIs(chat.load()[0]['partial'], True)
        self.assertNotIn('partial', chat.answer('whole', 'local', []))

    def test_load_survives_a_broken_file(self):
        self.assertEqual(chat.load(), [])
        paths.state_dir().mkdir(parents=True)
        paths.chat_file().write_text('{"messages": [{"role": "user"}, 7, {"role": "user", "content": "ok"}]')
        self.assertEqual(chat.load(), [])
        paths.chat_file().write_text('{"messages": [{"role": "user"}, 7, {"role": "user", "content": "ok"}]}')
        self.assertEqual([m['content'] for m in chat.load()], ['ok'])

    def test_cap_of_20(self):
        messages = []
        for i in range(30):
            messages += [chat.question(f'q{i}'), chat.answer(f'a{i}', 'claude', [])]
        messages.append(chat.question('last'))
        out = chat.for_engine(messages)
        self.assertLessEqual(len(out), 20)
        self.assertEqual(out[-1], {'role': 'user', 'content': 'last'})
        self.assertEqual(out[0]['role'], 'user')
        self.assertEqual(set(out[0]), {'role', 'content'})

    def test_unanswered_questions_are_left_out(self):
        messages = [chat.question('never answered'), chat.question('q'), chat.answer('a', 'claude', []),
                    chat.answer('', 'claude', [], partial=True), chat.question('now')]
        self.assertEqual([m['content'] for m in chat.for_engine(messages)], ['q', 'a', 'now'])

    def test_new_chat_keeps_the_old_one(self):
        self.assertIsNone(chat.new_chat())
        chat.append(chat.question('one'))
        kept = chat.new_chat()
        self.assertEqual(chat.load(), [])
        self.assertEqual(kept.parent, paths.chats_dir())
        self.assertEqual(json.loads(kept.read_text())['messages'][0]['content'], 'one')
        self.assertEqual(mode(kept), 0o600)
        chat.append(chat.question('two'))
        second = chat.new_chat()
        self.assertNotEqual(second, kept)
        self.assertEqual(chat.count_old(), 2)

    def test_delete_all(self):
        chat.append(chat.question('one'))
        chat.new_chat()
        chat.append(chat.question('two'))
        chat.delete_all()
        self.assertEqual(chat.load(), [])
        self.assertFalse(paths.chat_file().exists())
        self.assertEqual(chat.count_old(), 0)
        chat.delete_all()


class Key(SandboxCase):
    def test_store(self):
        self.assertFalse(keyfile.present())
        keyfile.store('  test-key-not-real\n')
        self.assertTrue(keyfile.present())
        self.assertEqual(paths.mistral_key_file().read_text(), 'test-key-not-real\n')
        self.assertEqual(mode(paths.mistral_key_file()), 0o600)
        self.assertEqual(paths.mistral_key_file().parent.name, 'zorro-ai')

    def test_atomic_replace_leaves_no_temp_file(self):
        keyfile.store('first-key')
        keyfile.store('second-key')
        self.assertEqual(paths.mistral_key_file().read_text(), 'second-key\n')
        self.assertEqual(os.listdir(paths.mistral_key_file().parent), ['mistral.key'])
        self.assertEqual(mode(paths.mistral_key_file()), 0o600)

    def test_bad_keys(self):
        for bad in ('', '   ', 'two words', 'line\nbreak'):
            with self.assertRaises(keyfile.BadKey):
                keyfile.store(bad)
        self.assertFalse(keyfile.present())

    def test_remove(self):
        keyfile.store('test-key-not-real')
        self.assertTrue(keyfile.remove())
        self.assertFalse(keyfile.present())
        self.assertFalse(keyfile.remove())

    def test_empty_file_is_no_key(self):
        paths.mistral_key_file().parent.mkdir(parents=True)
        paths.mistral_key_file().write_text('\n')
        self.assertFalse(keyfile.present())


if __name__ == '__main__':
    unittest.main()
