"""Ranker tests: the stub, BM25, RRF and the hybrid ranker."""

import math
import unittest

from incident_commander import config
from incident_commander.config import STATIC_RANKER_ORDER
from incident_commander.fixtures.alerts import ALERTS
from incident_commander.fixtures.runbooks import RUNBOOKS
from incident_commander.retrieval import HybridRanker, StaticRanker, bm25_scores, rrf, tokenize
from incident_commander.types import Runbook


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


class TestBm25(unittest.TestCase):
    def test_matches_hand_computed_tiny_corpus(self):
        docs = [["a", "b"], ["a", "c", "c"]]
        scores = bm25_scores(["b"], docs, k1=1.5, b=0.75)
        # N=2, df(b)=1 -> idf=ln(1+1.5/1.5)=ln2; avg_len=2.5; doc0: tf=1, len 2
        norm = 1 + 1.5 * (0.25 + 0.75 * 2 / 2.5)
        self.assertAlmostEqual(scores[0], math.log(2) * 1 * 2.5 / norm)
        self.assertEqual(scores[1], 0.0)

    def test_empty_query_and_empty_corpus(self):
        self.assertEqual(bm25_scores([], [["a"]]), [0.0])
        self.assertEqual(bm25_scores(["a"], []), [])

    def test_unknown_term_scores_zero_and_idf_never_negative(self):
        docs = [["a"], ["a"], ["a"]]  # term in every document: classic negative-IDF trap
        self.assertEqual(bm25_scores(["zzz"], docs), [0.0, 0.0, 0.0])
        self.assertTrue(all(x > 0 for x in bm25_scores(["a"], docs)))

    def test_tokenize_lowercases_words(self):
        self.assertEqual(tokenize("Checkout, LATENCY-spike!"), ["checkout", "latency", "spike"])


class TestRrf(unittest.TestCase):
    def test_worked_example_k60(self):
        out = rrf([["x", "y"], ["y", "x"], ["x"]], k=60)
        self.assertAlmostEqual(out["x"], 1 / 61 + 1 / 62 + 1 / 61)
        self.assertAlmostEqual(out["y"], 1 / 62 + 1 / 61)

    def test_item_in_one_list_only_and_empty(self):
        self.assertEqual(rrf([]), {})
        self.assertAlmostEqual(rrf([["a", "b"]])["b"], 1 / 62)


def _runbook(rid, text):
    return Runbook(rid, rid, text, ("sig_" + rid,), "restart_service")


class TestHybridRanker(unittest.TestCase):
    def setUp(self):
        self.ranker = HybridRanker(tuple(RUNBOOKS.values()))

    def rank(self, alert_id):
        return self.ranker.rank(ALERTS[alert_id].summary)

    def test_label_and_candidate_shape(self):
        out = self.rank("ALRT-9001")
        self.assertEqual(HybridRanker.label, "HYBRID")
        self.assertEqual([c.rank for c in out], [1, 2, 3, 4])
        self.assertEqual(sorted(c.runbook_id for c in out), sorted(RUNBOOKS))
        self.assertEqual(set(out[0].ranks), {"bm25", "char"})

    def test_deterministic(self):
        self.assertEqual(self.rank("ALRT-9001"), self.rank("ALRT-9001"))
        again = HybridRanker(tuple(RUNBOOKS.values()))
        self.assertEqual(again.rank("x"), self.ranker.rank("x"))

    def test_ac16_rb101_and_rb102_top_two_with_small_margin(self):
        for alert_id in ("ALRT-9001", "ALRT-9002"):
            out = self.rank(alert_id)
            self.assertEqual({c.runbook_id for c in out[:2]}, {"RB-101", "RB-102"})
            self.assertLess(HybridRanker.margin(out), config.SMALL_MARGIN)

    def test_rb104_ranks_first_for_alrt_9003(self):
        self.assertEqual(self.rank("ALRT-9003")[0].runbook_id, "RB-104")

    def test_margin_is_gap_between_first_two(self):
        out = self.rank("ALRT-9001")
        self.assertAlmostEqual(HybridRanker.margin(out), out[0].fused_score - out[1].fused_score)
        self.assertEqual(HybridRanker.margin(out[:1]), 0.0)
        self.assertEqual(HybridRanker.margin([]), 0.0)

    def test_signatures_are_not_indexed(self):
        a = HybridRanker((_runbook("A", "disk full"), _runbook("B", "cpu hot")))
        c = HybridRanker(
            (
                Runbook("A", "A", "disk full", ("cpu", "hot"), "restart_service"),
                Runbook("B", "B", "cpu hot", ("disk", "full"), "restart_service"),
            )
        )
        self.assertEqual(a.rank("disk full"), c.rank("disk full"))
        self.assertEqual(c.rank("disk full")[0].runbook_id, "A")

    def test_query_changes_the_order(self):
        top = {self.ranker.rank(q)[0].runbook_id for q in ("memory leak heap", "upstream timeouts")}
        self.assertEqual(top, {"RB-102", "RB-103"})

    def test_hostile_queries_do_not_crash(self):
        for query in ("", "   ", "zzzzqqq", "é中文", "a" * 10000):
            out = self.ranker.rank(query)
            self.assertEqual([c.rank for c in out], [1, 2, 3, 4])

    def test_zero_score_ties_keep_corpus_order(self):
        out = self.ranker.rank("")
        self.assertEqual([c.runbook_id for c in out], list(RUNBOOKS))

    def test_rejects_empty_and_duplicate_runbooks(self):
        with self.assertRaises(ValueError):
            HybridRanker(())
        with self.assertRaises(ValueError):
            HybridRanker((_runbook("A", "x y"), _runbook("A", "z w")))
