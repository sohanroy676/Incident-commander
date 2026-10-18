"""X4 / AC-24: advisor replies that are malformed, invented or unsafe are rejected (recorded replies)."""

import json
import unittest
from pathlib import Path

from ic_plus.guard import ADVICE_KEY, guard_advice
from incident_commander.investigator import EVIDENCE_TOOLS

RECORDED = json.loads(
    (Path(__file__).parent / "recorded" / "advisor_replies.json").read_text(encoding="utf-8")
)


def advice(*names: object) -> str:
    return json.dumps({ADVICE_KEY: list(names)})


class TestRecordedReplies(unittest.TestCase):
    def test_every_recorded_reply_is_judged_as_recorded(self):
        for name, item in RECORDED.items():
            with self.subTest(name=name):
                result = guard_advice(item["reply"], EVIDENCE_TOOLS)
                if item["expect"] == "pass":
                    self.assertTrue(result.ok, result.reason)
                    self.assertEqual(sorted(result.data[ADVICE_KEY]), sorted(EVIDENCE_TOOLS))
                else:
                    self.assertFalse(result.ok)
                    self.assertIn(item["expect"], result.reason)
                    self.assertIsNone(result.data)

    def test_the_recording_has_two_passes_and_many_rejections(self):
        verdicts = [item["expect"] == "pass" for item in RECORDED.values()]
        self.assertEqual(sum(verdicts), 2)
        self.assertGreaterEqual(len(verdicts), 15)


class TestOrdering(unittest.TestCase):
    def test_the_allowed_list_is_the_four_evidence_tools_without_logs(self):
        self.assertEqual(len(EVIDENCE_TOOLS), 4)
        self.assertNotIn("get_logs", EVIDENCE_TOOLS)

    def test_a_partial_list_is_padded_in_fixed_order(self):
        result = guard_advice(advice("get_dependencies", "get_latency"), EVIDENCE_TOOLS)
        rest = [t for t in EVIDENCE_TOOLS if t not in ("get_dependencies", "get_latency")]
        self.assertEqual(result.data[ADVICE_KEY], ("get_dependencies", "get_latency", *rest))

    def test_every_permutation_of_the_allowed_tools_is_accepted_unchanged(self):
        from itertools import permutations

        for perm in permutations(EVIDENCE_TOOLS):
            with self.subTest(perm=perm):
                result = guard_advice(advice(*perm), EVIDENCE_TOOLS)
                self.assertEqual(result.data[ADVICE_KEY], perm)


class TestEdges(unittest.TestCase):
    def test_the_allow_list_is_the_caller_s_not_a_global(self):
        self.assertTrue(guard_advice(advice("get_latency"), ("get_latency",)).ok)
        self.assertFalse(guard_advice(advice("get_error_rate"), ("get_latency",)).ok)

    def test_non_string_input_is_rejected_not_raised(self):
        for bad in (None, 5, b"{}", ["x"]):
            with self.subTest(bad=bad):
                self.assertFalse(guard_advice(bad, EVIDENCE_TOOLS).ok)

    def test_json_null_and_scalars_are_rejected(self):
        for bad in ("null", "5", '"text"', "true"):
            with self.subTest(bad=bad):
                self.assertFalse(guard_advice(bad, EVIDENCE_TOOLS).ok)

    def test_unhashable_entries_are_rejected_not_raised(self):
        for bad in ('{"order": [["get_latency"]]}', '{"order": [{"a": 1}]}'):
            with self.subTest(bad=bad):
                self.assertFalse(guard_advice(bad, EVIDENCE_TOOLS).ok)

    def test_nothing_is_ever_executed_the_guard_returns_data_only(self):
        result = guard_advice(advice("get_latency"), EVIDENCE_TOOLS)
        self.assertEqual(sorted(vars(result)), ["data", "ok", "reason"])


if __name__ == "__main__":
    unittest.main()
