"""X3 / AC-23: decisions are identical with the LLM roles on, including adversarial advice."""

import json
import unittest
from itertools import permutations
from unittest import mock

from ic_plus.x3 import ROLES_LINE, X3Row, advised_orders, decisions, run_case
from incident_commander import commander as graded_commander
from incident_commander.clocks import DataClock
from incident_commander.config import DATA_CLOCK_START_OFFSET_S
from incident_commander.evaluate import golden_world
from incident_commander.fixtures.runbooks import RUNBOOKS
from incident_commander.investigator import EVIDENCE_TOOLS, ToolBox, investigate
from incident_commander.retrieval import HybridRanker
from tests_plus.fake_llm import FakeLLM, chat_body
from tests_plus.test_advisor_guard import advice
from tests_plus.test_llm_cli import in_process

ALERT_IDS = golden_world().alert_ids()
NARRATIVE = json.dumps(
    {
        "summary": "The incident was handled.",
        "impact": "Users saw slow responses.",
        "root_cause_text": "A change caused it.",
    }
)
ANSWER = "The agent handled the incident from the evidence."
EVALUATE_ARGS = ("evaluate", "--llm", "local", "--model", "m")
FINAL = ROLES_LINE.format(changed=0)


def verdict_under(alert_id: str, order: tuple[str, ...]):
    world = golden_world()
    alert = world.alert(alert_id)
    clock = DataClock(alert.fired_at + DATA_CLOCK_START_OFFSET_S)
    ranker = HybridRanker(tuple(RUNBOOKS.values()))
    return investigate(alert, ranker, ToolBox(world, clock), tool_order=order).verdict


class TestEveryOrderGivesTheSameVerdict(unittest.TestCase):
    def test_all_24_permutations_on_every_fixture_alert(self):
        self.assertEqual(len(ALERT_IDS), 6)
        for alert_id in ALERT_IDS:
            baseline = verdict_under(alert_id, EVIDENCE_TOOLS)
            for order in permutations(EVIDENCE_TOOLS):
                with self.subTest(alert=alert_id, order=order):
                    self.assertEqual(verdict_under(alert_id, order), baseline)


class TestPipelineUnderAdvice(unittest.TestCase):
    def test_reversed_advice_leaves_every_decision_line_unchanged(self):
        reverse = tuple(reversed(EVIDENCE_TOOLS))
        for alert_id in ALERT_IDS:
            with self.subTest(alert=alert_id):
                same = decisions(run_case(alert_id, {alert_id: reverse})) == decisions(
                    run_case(alert_id)
                )
                self.assertTrue(same)

    def test_the_comparison_can_fail_an_order_with_too_few_tools_changes_decisions(self):
        starved = {"ALRT-9001": ("get_latency",)}
        self.assertNotEqual(
            decisions(run_case("ALRT-9001", starved)), decisions(run_case("ALRT-9001"))
        )

    def test_the_graded_function_is_restored_after_a_run_and_after_an_error(self):
        original = graded_commander.investigate
        with advised_orders({"ALRT-9001": EVIDENCE_TOOLS}):
            self.assertIsNot(graded_commander.investigate, original)
        self.assertIs(graded_commander.investigate, original)
        with self.assertRaises(RuntimeError), advised_orders({}):
            raise RuntimeError("boom")
        self.assertIs(graded_commander.investigate, original)

    def test_unlisted_alerts_keep_the_fixed_order(self):
        seen = []
        real = graded_commander.investigate

        def spy(alert, *args, **kwargs):
            seen.append((alert.alert_id, kwargs["tool_order"]))
            return real(alert, *args, **kwargs)

        other = {"ALRT-9001": tuple(reversed(EVIDENCE_TOOLS))}
        with mock.patch.object(graded_commander, "investigate", spy):
            run_case("ALRT-9003", other)
        self.assertEqual(seen, [("ALRT-9003", EVIDENCE_TOOLS)])


def good_triples(count: int, advisor_reply: str) -> list:
    """Replies in call order per alert: advisor, narrator, explainer."""
    return [
        reply
        for _ in range(count)
        for reply in (
            (200, chat_body(advisor_reply), 0),
            (200, chat_body(NARRATIVE), 0),
            (200, chat_body(ANSWER), 0),
        )
    ]


class TestEvaluateCommand(unittest.TestCase):
    def test_llm_off_is_the_graded_evaluation_and_no_x3_lines(self):
        code, out, _ = in_process("evaluate")
        self.assertEqual(code, 0)
        self.assertIn("DECISION golden_summary passed=3 total=3", out)
        self.assertIn("llm: off", out)
        self.assertNotIn("x3 alert", out)

    def test_good_replies_from_every_role_leave_decisions_unchanged(self):
        reverse = advice(*reversed(EVIDENCE_TOOLS))
        with FakeLLM(good_triples(len(ALERT_IDS), reverse)) as fake:
            code, out, _ = in_process(*EVALUATE_ARGS, "--llm-url", fake.url)
            calls = len(fake.requests)
        self.assertEqual(code, 0, out)
        self.assertEqual(calls, 3 * len(ALERT_IDS))
        self.assertIn("DECISION golden_summary passed=3 total=3", out)
        self.assertIn("unchanged=True", out)
        self.assertEqual(out.count("advisor=ok narrator=ok explainer=ok"), len(ALERT_IDS))
        x3_lines = [line for line in out.splitlines() if line.startswith("x3 alert=")]
        self.assertEqual(len(x3_lines), len(ALERT_IDS))
        self.assertTrue(all(line.endswith("identical=True") for line in x3_lines))
        self.assertIn(FINAL, out)
        self.assertIn(",".join(reversed(EVIDENCE_TOOLS)), out)

    def test_adversarial_advice_is_rejected_and_decisions_are_unchanged(self):
        bad = advice("get_latency", "rollback_deployment")
        with FakeLLM(good_triples(len(ALERT_IDS), bad)) as fake:
            code, out, _ = in_process(*EVALUATE_ARGS, "--llm-url", fake.url)
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("advisor=rejected"), len(ALERT_IDS))
        self.assertIn(FINAL, out)

    def test_a_dead_model_still_proves_x3_through_the_fallbacks(self):
        with FakeLLM([(500, "down", 0)]) as fake:
            code, out, _ = in_process(*EVALUATE_ARGS, "--llm-url", fake.url)
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("advisor=unavailable narrator=unavailable"), len(ALERT_IDS))
        self.assertIn(FINAL, out)

    def test_a_changed_decision_is_counted_and_fails_the_command(self):
        changed = X3Row("ALRT-9001", "ok", "ok", "ok", EVIDENCE_TOOLS, False)
        with mock.patch("ic_plus.__main__.run_x3", return_value=[changed]):
            code, out, _ = in_process(*EVALUATE_ARGS, "--llm-url", "http://127.0.0.1:9/v1")
        self.assertEqual(code, 1)
        self.assertIn(ROLES_LINE.format(changed=1), out)
        self.assertIn("identical=False", out)


if __name__ == "__main__":
    unittest.main()
