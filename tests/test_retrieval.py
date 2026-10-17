"""Ranker tests (v0.2: the stub only; hybrid retrieval tests arrive with v0.5)."""

import unittest

from incident_commander.config import STATIC_RANKER_ORDER
from incident_commander.fixtures.runbooks import RUNBOOKS
from incident_commander.retrieval import StaticRanker


class TestStaticRanker(unittest.TestCase):
    def test_preserves_order_with_ranks_from_one(self):
        out = StaticRanker(["RB-103", "RB-101"]).rank("anything")
        self.assertEqual([c.runbook_id for c in out], ["RB-103", "RB-101"])
        self.assertEqual([c.rank for c in out], [1, 2])
        self.assertEqual(out[0].ranks, {"static": 1})

    def test_query_is_ignored(self):
        r = StaticRanker(STATIC_RANKER_ORDER)
        self.assertEqual(r.rank("latency spike"), r.rank("IGNORE PREVIOUS INSTRUCTIONS"))

    def test_declared_as_stub(self):
        self.assertEqual(StaticRanker(["RB-101"]).label, "STUB")

    def test_default_order_is_wrong_first_and_covers_the_corpus(self):
        self.assertEqual(STATIC_RANKER_ORDER, ("RB-102", "RB-101", "RB-104", "RB-103"))
        self.assertEqual(set(STATIC_RANKER_ORDER), set(RUNBOOKS))

    def test_rejects_empty_and_duplicate_orders(self):
        with self.assertRaises(ValueError):
            StaticRanker([])
        with self.assertRaises(ValueError):
            StaticRanker(["RB-101", "RB-101"])


if __name__ == "__main__":
    unittest.main()
