"""X4 / AC-24: malformed, out-of-schema or instruction-like LLM replies are rejected (recorded replies)."""

import json
import unittest
from pathlib import Path

from ic_plus.guard import MAX_FIELD_CHARS, guard_narrative

RECORDED = json.loads(
    (Path(__file__).parent / "recorded" / "narrator_replies.json").read_text(encoding="utf-8")
)

FACTS = {
    "action": "rollback_deployment",
    "alert_id": "ALRT-9001",
    "approval_status": "approved",
    "approved_by": "engineer-devon",
    "baseline_value": 180.0,
    "escalated": True,
    "execution_status": "executed",
    "handoff_reason": None,
    "metric": "latency_ms",
    "observed_value": 182.0,
    "requires_approval": True,
    "rounds": 3,
    "runbook_id": "RB-101",
    "service": "checkout-service",
    "tier": "high",
    "verdict": "matched",
    "verification_status": "resolved",
    "verified": True,
}


def reply(**overrides: object) -> str:
    base = {
        "summary": "ALRT-9001 on checkout-service.",
        "impact": "Slow.",
        "root_cause_text": "A bad deployment.",
    }
    return json.dumps({**base, **overrides})


class TestRecordedReplies(unittest.TestCase):
    def test_every_recorded_reply_is_judged_as_recorded(self):
        for name, item in RECORDED.items():
            with self.subTest(name=name):
                result = guard_narrative(item["reply"], FACTS)
                if item["expect"] == "pass":
                    self.assertTrue(result.ok, result.reason)
                    self.assertEqual(set(result.data), {"summary", "impact", "root_cause_text"})
                else:
                    self.assertFalse(result.ok)
                    self.assertIn(item["expect"], result.reason)
                    self.assertIsNone(result.data)

    def test_the_recording_has_one_pass_and_many_rejections(self):
        verdicts = [item["expect"] == "pass" for item in RECORDED.values()]
        self.assertEqual(sum(verdicts), 1)
        self.assertGreaterEqual(len(verdicts), 15)


class TestEdges(unittest.TestCase):
    def test_a_number_written_without_decimals_matches_the_fact(self):
        self.assertTrue(guard_narrative(reply(impact="Latency was 182 ms against 180."), FACTS).ok)

    def test_a_number_inside_a_word_or_identifier_is_not_free(self):
        self.assertFalse(guard_narrative(reply(impact="It took 4 rounds."), FACTS).ok)
        self.assertFalse(guard_narrative(reply(summary="ALRT-9999 on checkout-service."), FACTS).ok)

    def test_length_limit_per_field(self):
        self.assertTrue(guard_narrative(reply(impact="x" * MAX_FIELD_CHARS), FACTS).ok)
        result = guard_narrative(reply(impact="x" * (MAX_FIELD_CHARS + 1)), FACTS)
        self.assertFalse(result.ok)
        self.assertIn("longer than", result.reason)

    def test_past_tense_postmortem_words_are_not_instructions(self):
        text = "The rollback was executed and approved by engineer-devon; the page was escalated."
        self.assertTrue(guard_narrative(reply(root_cause_text=text), FACTS).ok)

    def test_other_services_and_runbooks_must_come_from_the_facts(self):
        for text in ("inventory-service was slow.", "Runbook RB-102 applied.", "devon and priya."):
            with self.subTest(text=text):
                self.assertFalse(guard_narrative(reply(impact=text), FACTS).ok)

    def test_non_string_input_is_rejected_not_raised(self):
        for bad in (None, 5, b"{}", ["x"]):
            with self.subTest(bad=bad):
                self.assertFalse(guard_narrative(bad, FACTS).ok)

    def test_json_null_and_scalars_are_rejected(self):
        for bad in ("null", "5", '"text"', "true"):
            with self.subTest(bad=bad):
                self.assertFalse(guard_narrative(bad, FACTS).ok)

    def test_nothing_is_ever_executed_the_guard_returns_data_only(self):
        result = guard_narrative(reply(), FACTS)
        self.assertEqual(sorted(vars(result)), ["data", "ok", "reason"])


if __name__ == "__main__":
    unittest.main()
