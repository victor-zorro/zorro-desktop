"""The shared chat file: append, the 20-message cap, new chat."""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

import helper  # noqa: F401
from dial import chatfile


class ChatFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.file = Path(self.dir.name) / 'zorro-intel' / 'chat.json'

    def tearDown(self):
        self.dir.cleanup()

    def test_no_file_or_a_broken_one_is_an_empty_chat(self):
        self.assertEqual(chatfile.load(self.file), [])
        self.file.parent.mkdir()
        for content in ('{broken', '[]', '{"messages": 3}', '{"messages": [3, {"role": "x", "content": "y"}]}'):
            self.file.write_text(content)
            self.assertEqual(chatfile.load(self.file), [], content)

    def test_append_keeps_what_is_there_and_is_private(self):
        chatfile.append([chatfile.message('user', 'one')], self.file)
        both = chatfile.append([chatfile.message('assistant', 'two', engine='local', sent=[], note='')], self.file)
        self.assertEqual([m['content'] for m in both], ['one', 'two'])
        on_disk = json.loads(self.file.read_text())['messages']
        self.assertEqual(on_disk, both)
        self.assertEqual(on_disk[1]['engine'], 'local')
        self.assertNotIn('note', on_disk[1])
        self.assertRegex(on_disk[0]['at'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$')
        self.assertEqual(stat.S_IMODE(os.stat(self.file).st_mode), 0o600)
        self.assertEqual(sorted(os.listdir(self.file.parent)), ['.chat.lock', 'chat.json'])     # no temp file left

    def test_append_sees_what_the_other_app_wrote(self):
        chatfile.append([chatfile.message('user', 'mine')], self.file)
        theirs = chatfile.load(self.file) + [chatfile.message('user', 'theirs')]
        chatfile.write(theirs, self.file)
        after = chatfile.append([chatfile.message('user', 'mine again')], self.file)
        self.assertEqual([m['content'] for m in after], ['mine', 'theirs', 'mine again'])

    def test_at_most_twenty_go_to_the_engine(self):
        messages = [chatfile.message('user' if i % 2 == 0 else 'assistant', str(i), engine='e') for i in range(31)]
        out = chatfile.for_engine(messages)
        self.assertEqual(len(out), 19)          # the last 20, starting with a question
        self.assertEqual(out[-1], {'role': 'user', 'content': '30'})
        self.assertEqual((out[0]['role'], out[0]['content']), ('user', '12'))
        self.assertEqual(out[1], {'role': 'assistant', 'content': '13', 'engine': 'e'})

    def test_new_chat_empties_it_and_keeps_the_old_one(self):
        chatfile.append([chatfile.message('user', 'old')], self.file)
        chatfile.new_chat(self.file)
        self.assertEqual(chatfile.load(self.file), [])
        kept = list((self.file.parent / 'chats').glob('*.json'))
        self.assertEqual(len(kept), 1)
        self.assertEqual(json.loads(kept[0].read_text())['messages'][0]['content'], 'old')
        self.assertEqual(stat.S_IMODE(os.stat(kept[0]).st_mode), 0o600)
        chatfile.new_chat(self.file)                                # an empty chat is not kept again
        self.assertEqual(len(list((self.file.parent / 'chats').glob('*.json'))), 1)

    def test_two_new_chats_in_one_second_keep_both(self):
        for text in ('first', 'second'):
            chatfile.append([chatfile.message('user', text)], self.file)
            chatfile.new_chat(self.file)
        self.assertEqual(len(list((self.file.parent / 'chats').glob('*.json'))), 2)


if __name__ == '__main__':
    unittest.main()
