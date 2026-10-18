"""Commander: every path through the state machine, trace discipline, no text in decisions."""

import inspect
import unittest
from typing import ClassVar

from incident_commander.approval import ScriptedResponder
from incident_commander.blast_radius import classify_remediation
from incident_commander.clocks import ControlClock, DataClock
from incident_commander.commander import (
    TRANSITIONS,
    Commander,
    IllegalTransition,
    Trace,
)
from incident_commander.config import STATIC_RANKER_ORDER
from incident_commander.postmortem import OutboxNotifier, build_draft
from incident_commander.retrieval import StaticRanker
from incident_commander.verifier import assess, verify
from incident_commander.world import SimWorld

DEVON_APPROVES = {"engineer-devon": (0.1, "approve")}


def make(script, world=None):
    world = world or SimWorld()
    return world, Commander(world, StaticRanker(STATIC_RANKER_ORDER), ScriptedResponder(script))


def kinds(case):
    return [e.kind for e in case.trace.events]


def states(case):
    return [dict(e.fields)["to"] for e in case.trace.events if e.kind == "STATE"]


class TestPaths(unittest.TestCase):
    def test_matched_low_risk_resolves_without_paging(self):
        world, cmd = make({})
        case = cmd.run(world.alert("ALRT-9002"))
        self.assertFalse(case.classification.requires_approval)
        self.assertNotIn("PAGE", kinds(case))
        self.assertEqual(case.verification.status, "resolved")
        self.assertEqual(
            states(case),
            [
                "INVESTIGATING",
                "MATCHED",
                "CLASSIFIED",
                "EXECUTING",
                "VERIFYING",
                "RESOLVED",
                "DRAFTED",
            ],
        )

    def test_matched_high_risk_escalates_to_devon(self):
        world, cmd = make(DEVON_APPROVES)
        case = cmd.run(world.alert("ALRT-9001"))
        self.assertTrue(case.approval.escalated)
        self.assertEqual(case.token.approved_by, "engineer-devon")
        self.assertIn("ESCALATE", kinds(case))
        self.assertEqual(case.verification.observed, 182.0)
        self.assertIn("AWAITING_APPROVAL", states(case))

    def test_no_match_hands_off_without_executing(self):
        world, cmd = make({})
        case = cmd.run(world.alert("ALRT-9003"))
        self.assertEqual(case.handoff_reason, "no_confident_match")
        self.assertIsNone(case.execution)
        self.assertNotIn("EXECUTE", kinds(case))
        self.assertEqual(states(case)[-3:], ["NO_MATCH", "HANDOFF", "DRAFTED"])
        self.assertFalse(case.draft.published)

    def test_approval_expired_hands_off_and_never_executes(self):
        world, cmd = make({})
        case = cmd.run(world.alert("ALRT-9001"))
        self.assertEqual(case.handoff_reason, "approval_expired")
        self.assertIsNone(case.execution)
        self.assertEqual(case.state, "DRAFTED")

    def test_approval_denied_hands_off_and_never_executes(self):
        world, cmd = make({"engineer-priya": (0.0, "deny")})
        case = cmd.run(world.alert("ALRT-9001"))
        self.assertEqual(case.handoff_reason, "approval_denied")
        self.assertIsNone(case.execution)

    def test_execution_failure_hands_off_without_verifying(self):
        class Broken(SimWorld):
            def apply_remediation(self, service, action, at, outcome="success"):
                raise ValueError("boom")

        world, cmd = make({}, Broken())
        case = cmd.run(world.alert("ALRT-9002"))
        self.assertEqual(case.execution.status, "failed")
        self.assertEqual(case.handoff_reason, "execution_failed")
        self.assertIsNone(case.verification)

    def test_fix_fails_reopens_then_hands_off_with_no_second_fix(self):
        world, cmd = make({})
        case = cmd.run(world.alert("ALRT-9002"), fix_outcome="fix_fails")
        self.assertEqual(case.verification.status, "reopened")
        self.assertEqual(case.verification.observed, 3900.0)
        self.assertEqual(case.handoff_reason, "reopened")
        self.assertEqual(kinds(case).count("EXECUTE"), 1)
        self.assertIn("REOPENED", states(case))

    def test_unknown_fix_outcome_is_rejected(self):
        world, cmd = make({})
        with self.assertRaises(ValueError):
            cmd.run(world.alert("ALRT-9002"), fix_outcome="bogus")

    def test_retry_returns_same_execution_id(self):
        world, cmd = make({})
        case = cmd.run(world.alert("ALRT-9002"))
        retry = cmd.retry_execution(case)
        self.assertEqual(retry.status, "already_executed")
        self.assertEqual(retry.execution_id, case.execution.execution_id)

    def test_retry_without_execution_is_illegal(self):
        world, cmd = make({})
        case = cmd.run(world.alert("ALRT-9003"))
        with self.assertRaises(IllegalTransition):
            cmd.retry_execution(case)


class TestPublishAndTransitions(unittest.TestCase):
    def test_publish_is_explicit_and_only_once(self):
        world, cmd = make({})
        case = cmd.run(world.alert("ALRT-9003"))
        outbox = OutboxNotifier()
        self.assertEqual(outbox.sent, [])
        draft = cmd.publish(case, outbox)
        self.assertTrue(draft.published)
        self.assertEqual(case.state, "PUBLISHED")
        self.assertEqual(len(outbox.sent), 1)
        with self.assertRaises(IllegalTransition):
            cmd.publish(case, outbox)
        self.assertEqual(len(outbox.sent), 1)

    def test_illegal_transition_raises_and_leaves_state(self):
        world, cmd = make({})
        case = cmd.run(world.alert("ALRT-9003"))
        with self.assertRaises(IllegalTransition):
            cmd._move(case, "EXECUTING")
        self.assertEqual(case.state, "DRAFTED")

    def test_every_path_reaches_drafted_before_published(self):
        self.assertEqual(TRANSITIONS["DRAFTED"], frozenset({"PUBLISHED"}))
        self.assertNotIn("PUBLISHED", TRANSITIONS["HANDOFF"] | TRANSITIONS["RESOLVED"])

    def test_execution_only_follows_classification_or_approval(self):
        entering = {s for s, to in TRANSITIONS.items() if "EXECUTING" in to}
        self.assertEqual(entering, {"CLASSIFIED", "AWAITING_APPROVAL"})


class TestTrace(unittest.TestCase):
    def test_events_are_a_snapshot_and_sequence_is_monotonic(self):
        trace = Trace(DataClock(0.0), ControlClock())
        trace.emit("A", x=1)
        snapshot = trace.events
        trace.emit("B")
        self.assertEqual(len(snapshot), 1)
        self.assertEqual([e.seq for e in trace.events], [1, 2])

    def test_events_are_immutable(self):
        trace = Trace(DataClock(0.0), ControlClock())
        trace.emit("A", x=1)
        with self.assertRaises(AttributeError):
            trace.events[0].kind = "B"

    def test_draft_is_built_from_the_case_trace(self):
        world, cmd = make({})
        case = cmd.run(world.alert("ALRT-9003"))
        self.assertEqual(case.trace.events[0].kind, "ALERT_RECEIVED")
        before_draft = case.trace.events[:-2]  # minus STATE->DRAFTED and DRAFT
        self.assertEqual(case.draft, build_draft(before_draft, case.logs, None))


class TestNoTextInDecisions(unittest.TestCase):
    FORBIDDEN: ClassVar[set[str]] = {
        "summary",
        "text",
        "log",
        "logs",
        "message",
        "severity",
        "severity_label",
        "alert",
    }

    def test_decision_functions_take_no_text_or_severity(self):
        for fn in (classify_remediation, verify, assess):
            params = set(inspect.signature(fn).parameters)
            self.assertFalse(params & self.FORBIDDEN, f"{fn.__name__}: {params & self.FORBIDDEN}")

    def test_investigation_never_reads_logs(self):
        world, cmd = make({})
        case = cmd.run(world.alert("ALRT-9003"))
        tools = {o.tool for o in case.investigation.observations}
        self.assertNotIn("get_logs", tools)
        self.assertEqual(case.logs.tool, "get_logs")


if __name__ == "__main__":
    unittest.main()
