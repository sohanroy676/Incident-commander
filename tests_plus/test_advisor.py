"""Advisor: numbers-only request, guard in front of every reply, fixed order on any failure."""

import json
import unittest
from itertools import permutations

from ic_plus.advisor import advise, build_facts
from ic_plus.llm_client import LLMClient
from ic_plus.narrator import REJECTED_LINE, UNAVAILABLE_LINE
from incident_commander.fixtures.runbooks import RUNBOOKS
from incident_commander.investigator import EVIDENCE_TOOLS
from incident_commander.retrieval import HybridRanker
from incident_commander.world import SimWorld
from tests_plus.fake_llm import FakeLLM, chat_body, unused_url
from tests_plus.test_advisor_guard import RECORDED, advice
from tests_plus.test_narrator import SECRET, client_for

ALERTS = ("ALRT-9001", "ALRT-9002", "ALRT-9003")


class Sink:
    def __init__(self):
        self.events = []

    def emit(self, kind, **fields):
        self.events.append((kind, fields))


def setup(alert_id="ALRT-9001"):
    alert = SimWorld().alert(alert_id)
    return alert, HybridRanker(tuple(RUNBOOKS.values())).rank(alert.summary)


class TestFacts(unittest.TestCase):
    def test_facts_are_typed_ids_and_numbers_without_text_or_severity(self):
        for alert_id in ALERTS:
            with self.subTest(alert=alert_id):
                alert, candidates = setup(alert_id)
                facts = build_facts(alert, candidates)
                keys = ("alert_id", "service", "metric", "candidates", "allowed_tools")
                self.assertEqual(set(facts), {*keys, "evidence_so_far"})
                text = json.dumps(facts)
                self.assertNotIn(alert.summary, text)
                self.assertNotIn(alert.severity, text)
                self.assertEqual(facts["allowed_tools"], list(EVIDENCE_TOOLS))
                self.assertEqual(len(facts["candidates"]), len(candidates))


class TestAdvise(unittest.TestCase):
    def test_a_good_reply_becomes_the_order_and_is_traced(self):
        alert, candidates = setup()
        wanted = tuple(reversed(EVIDENCE_TOOLS))
        sink = Sink()
        with FakeLLM([(200, chat_body(advice(*wanted)), 0)]) as fake:
            outcome = advise(alert, candidates, client_for(fake), sink)
            sent = fake.requests[0]["body"]
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.order, wanted)
        self.assertIn("order=" + ",".join(wanted), outcome.lines[0])
        self.assertEqual([k for k, _ in sink.events], ["llm_ok"])
        self.assertEqual(sink.events[0][1]["role"], "advisor")
        self.assertNotIn(alert.summary, sent)

    def test_a_partial_reply_is_padded_to_a_permutation(self):
        alert, candidates = setup()
        with FakeLLM([(200, chat_body(advice("get_dependencies")), 0)]) as fake:
            outcome = advise(alert, candidates, client_for(fake))
        self.assertEqual(outcome.order[0], "get_dependencies")
        self.assertEqual(sorted(outcome.order), sorted(EVIDENCE_TOOLS))

    def test_every_recorded_bad_reply_keeps_the_fixed_order_and_is_logged(self):
        alert, candidates = setup()
        for name, item in RECORDED.items():
            if item["expect"] == "pass":
                continue
            sink = Sink()
            with self.subTest(name=name), FakeLLM([(200, chat_body(item["reply"]), 0)]) as fake:
                outcome = advise(alert, candidates, client_for(fake), sink)
            self.assertIn(outcome.status, ("rejected", "unavailable"))
            self.assertEqual(outcome.order, EVIDENCE_TOOLS)
            self.assertTrue({REJECTED_LINE, UNAVAILABLE_LINE} & set(outcome.lines))
            self.assertIn(sink.events[0][0], ("llm_rejected", "llm_unavailable"))
            self.assertNotIn("llm_ok", [k for k, _ in sink.events])

    def test_a_rejected_reply_names_the_reason_and_never_echoes_the_bad_tool(self):
        alert, candidates = setup()
        with FakeLLM([(200, chat_body(advice("get_latency", "restart_service")), 0)]) as fake:
            outcome = advise(alert, candidates, client_for(fake))
        self.assertEqual(outcome.status, "rejected")
        self.assertIn("llm_rejected role=advisor alert=ALRT-9001", outcome.lines[0])
        self.assertEqual(outcome.order, EVIDENCE_TOOLS)

    def test_no_client_http_errors_and_dead_server_keep_the_fixed_order(self):
        alert, candidates = setup()
        sink = Sink()
        self.assertEqual(advise(alert, candidates, None, sink).order, EVIDENCE_TOOLS)
        self.assertEqual(sink.events[0][0], "llm_unavailable")
        for status in (401, 429, 500):
            with self.subTest(status=status), FakeLLM([(status, "no", 0)]) as fake:
                outcome = advise(alert, candidates, client_for(fake))
                self.assertEqual((outcome.status, outcome.order), ("unavailable", EVIDENCE_TOOLS))
        dead = LLMClient(unused_url(), "m", None, timeout_s=2.0)
        self.assertEqual(advise(alert, candidates, dead).status, "unavailable")

    def test_the_outcome_is_always_a_permutation_of_the_allowed_tools(self):
        alert, candidates = setup()
        replies = [advice(*p) for p in permutations(EVIDENCE_TOOLS, 2)] + ["{}", "x", ""]
        for text in replies:
            with self.subTest(text=text), FakeLLM([(200, chat_body(text), 0)]) as fake:
                outcome = advise(alert, candidates, client_for(fake))
                self.assertEqual(sorted(outcome.order), sorted(EVIDENCE_TOOLS))

    def test_the_key_is_a_header_only_and_never_in_lines_or_events(self):
        alert, candidates = setup()
        sink = Sink()
        with FakeLLM([(401, f"bad key {SECRET}", 0)]) as fake:
            outcome = advise(alert, candidates, client_for(fake, key=SECRET), sink)
            self.assertNotIn(SECRET, fake.requests[0]["body"])
        self.assertNotIn(SECRET, " ".join(outcome.lines) + repr(sink.events))


if __name__ == "__main__":
    unittest.main()
