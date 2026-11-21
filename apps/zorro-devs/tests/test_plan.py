import json
import unittest

from helper import ServerCase

from devs import paths


class Plan(ServerCase):
    def test_answers(self):
        self.assertEqual(self.call('/plan/api/answers'), (200, {}))
        status, _ = self.call('/plan/api/answers/ai-read', {'pick': ['Notes', 5], 'note': 'only these'})
        self.assertEqual(status, 200)
        saved = json.loads(paths.plan_answers().read_text())
        self.assertEqual(paths.plan_answers().parent.name, 'zorro-plan')
        self.assertEqual((saved['ai-read']['pick'], saved['ai-read']['note']), (['Notes', '5'], 'only these'))
        self.assertIn('at', saved['ai-read'])
        self.call('/plan/api/answers/names', {'pick': [], 'note': ''})
        self.assertEqual(sorted(self.call('/plan/api/answers')[1]), ['ai-read', 'names'])

    def test_bad_answers(self):
        self.assertEqual(self.call('/plan/api/answers/Not_An_Id', {'pick': []})[0], 400)
        self.assertEqual(self.call('/plan/api/answers/q', {'pick': 'text'})[0], 400)
        self.assertEqual(self.call('/plan/api/answers/q', raw=b'[1]')[0], 400)
        self.assertEqual(self.call('/plan/api/answers/q', {'note': 'x' * 30000})[0], 400)
        self.assertFalse(paths.plan_answers().exists())

    def test_plan_page_files(self):
        status, page = self.call('/plan/')
        self.assertEqual((status, page), (200, '<!doctype html><title>plan</title>'))
        self.assertEqual(self.call('/plan/index.html')[0], 200)
        for path in ('/plan/serve.py', '/plan/SPEC.md', '/plan/../CLAUDE.md', '/plan/missing.js'):
            self.assertEqual(self.call(path)[0], 404, path)


if __name__ == '__main__':
    unittest.main()
