"""Caches per part (D17), reads that hang (D21), parts that are safe before their first read (D20)."""
import unittest
from unittest import mock

import helper  # noqa: F401
from dial import nodes, state
from dial.parts import MODES, PARTS
from dial.parts.base import Part
from dial.parts.music import Music


class CacheKeyTest(unittest.TestCase):
    def test_the_same_id_in_two_parts_is_two_keys(self):
        recent = {'id': 'recent', 'name': 'Recent'}
        self.assertNotEqual(nodes.cache_key('files', recent), nodes.cache_key('notes', recent))
        self.assertEqual(nodes.cache_key('files', recent), nodes.cache_key('files', dict(recent)))

    def test_a_tile_without_an_id_goes_by_its_name(self):
        self.assertEqual(nodes.cache_key('music', {'name': 'Play'}), ('music', 'Play'))

    def test_same(self):
        a = {'id': 'x', 'name': 'X', 'icon': 'i'}
        self.assertTrue(nodes.same(a, dict(a)))
        self.assertFalse(nodes.same(a, {**a, 'name': 'Y'}))
        self.assertFalse(nodes.same(a, None))


class FetchClaimTest(unittest.TestCase):
    def setUp(self):
        state.FETCHING.clear()

    def test_one_read_at_a_time(self):
        ticket = state.claim_fetch('notes', now=100)
        self.assertIsNotNone(ticket)
        self.assertIsNone(state.claim_fetch('notes', now=105))
        self.assertIsNotNone(state.claim_fetch('files', now=105))
        state.release_fetch('notes', ticket)
        self.assertIsNotNone(state.claim_fetch('notes', now=106))

    def test_a_read_that_hangs_gives_way_after_the_limit(self):
        old = state.claim_fetch('files', now=100)
        self.assertIsNone(state.claim_fetch('files', now=100 + state.FETCH_LIMIT - 1))
        new = state.claim_fetch('files', now=100 + state.FETCH_LIMIT)
        self.assertIsNotNone(new)
        self.assertFalse(state.owns_fetch('files', old))            # the old read may not swap its data in
        state.release_fetch('files', old)                           # and does not free the new one's claim
        self.assertTrue(state.owns_fetch('files', new))
        self.assertIsNone(state.claim_fetch('files', now=101 + state.FETCH_LIMIT))


class PartsTest(unittest.TestCase):
    def test_the_six_parts(self):
        self.assertEqual([m[0] for m in MODES], ['apps', 'music', 'notes', 'ai', 'messages', 'files'])
        self.assertEqual(set(PARTS), {m[0] for m in MODES} - {'apps'})

    def test_a_part_that_was_never_read_has_its_defaults(self):
        for part in [Part()] + [type(p)() for p in PARTS.values()]:
            self.assertIsNone(part.np)
            self.assertEqual(part.items, [])
            part.preview()
            part.roots()

    def test_player_buttons_work_before_the_first_read(self):
        with mock.patch('dial.parts.music.run') as run, mock.patch('dial.parts.music.time.sleep'):
            Music().control('toggle')
        self.assertEqual(run.call_args[0][1], 'toggle')

    def test_renewed_is_a_fresh_copy(self):
        class Counted(Part):
            def fetch(self):
                self.items = [1]
                self.ready = True
        old = Counted()
        new = old.renewed()
        self.assertIsNot(new, old)
        self.assertEqual((old.items, old.ready, new.items, new.ready), ([], False, [1], True))


if __name__ == '__main__':
    unittest.main()
