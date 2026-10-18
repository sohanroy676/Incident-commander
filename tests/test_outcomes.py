"""G3 outcomes (AC-07 to AC-12): the exact values the brief promises, through the shipped pipeline.

Each class is one Outcome. The pipeline is the real one (hybrid ranker, scripted on-call
responder, real clock): nothing here patches sleep, and timing asserts are lower bounds only.
"""

import time
import unittest

from incident_commander.approval import ApprovalGate, ScriptedResponder
from incident_commander.clocks import ControlClock
from incident_commander.commander import Commander
from incident_commander.config import APPROVAL_DEADLINE_S, APPROVAL_TICK_S
from incident_commander.fixtures.runbooks import RUNBOOKS
from incident_commander.postmortem import OutboxNotifier
from incident_commander.retrieval import HybridRanker
from incident_commander.world import SimWorld

PRIYA, DEVON = "engineer-priya", "engineer-devon"
REOPEN_REASON = "remediation ran but did not resolve the signal"


def make(world: SimWorld | None = None) -> tuple[SimWorld, Commander]:
    """Priya never answers; Devon approves 0.1 s after being paged."""
    world = world or SimWorld()
    ranker = HybridRanker(tuple(RUNBOOKS.values()))
    return world, Commander(world, ranker, ScriptedResponder({DEVON: (0.1, "approve")}))


def new_page():
    gate = ApprovalGate(
        ControlClock(), ScriptedResponder({}), PRIYA, DEVON, APPROVAL_DEADLINE_S, APPROVAL_TICK_S
    )
    return gate.new_page(PRIYA, DEVON)


def run_case(alert_id: str, **kw):
    world, cmd = make()
    return cmd, cmd.run(world.alert(alert_id), **kw)


def kinds(case) -> list[str]:
    return [e.kind for e in case.trace.events]


class TestOutcome1(unittest.TestCase):
    """AC-07: ALRT-9003 exhausts the round budget and hands off with no match."""

    def test_alrt_9003_uses_four_rounds_and_finds_no_match(self):
        _, case = run_case("ALRT-9003")
        v = case.investigation.verdict
        self.assertEqual(v.kind, "no_confident_match")
        self.assertEqual((v.runbook_id, v.rounds, v.reason), (None, 4, "all_refuted"))
        self.assertEqual(len(case.investigation.rounds), 4)

    def test_alrt_9003_hands_off_and_never_executes_or_pages(self):
        _, case = run_case("ALRT-9003")
        self.assertEqual(case.handoff_reason, "no_confident_match")
        self.assertIsNone(case.execution)
        for kind in ("EXECUTE", "PAGE", "ESCALATE"):
            self.assertNotIn(kind, kinds(case))

    def test_the_other_two_alerts_match_in_three_rounds(self):
        for alert_id, runbook in (("ALRT-9001", "RB-101"), ("ALRT-9002", "RB-102")):
            _, case = run_case(alert_id)
            v = case.investigation.verdict
            self.assertEqual((v.kind, v.runbook_id, v.rounds), ("matched", runbook, 3), alert_id)


class TestOutcome2(unittest.TestCase):
    """AC-08: equal severity, different tiers: the action decides, not the alert."""

    def test_9001_is_high_tier_with_approval_and_9002_is_low_without(self):
        _, c1 = run_case("ALRT-9001")
        _, c2 = run_case("ALRT-9002")
        self.assertEqual(c1.alert.severity, c2.alert.severity)
        self.assertEqual(
            (c1.classification.action, c1.classification.tier, c1.classification.requires_approval),
            ("rollback_deployment", "high", True),
        )
        self.assertEqual(
            (c2.classification.action, c2.classification.tier, c2.classification.requires_approval),
            ("restart_service", "low", False),
        )

    def test_the_low_tier_fix_is_never_paged_and_the_high_tier_fix_is(self):
        _, c1 = run_case("ALRT-9001")
        _, c2 = run_case("ALRT-9002")
        self.assertIn("PAGE", kinds(c1))
        self.assertNotIn("PAGE", kinds(c2))
        self.assertIsNone(c2.token)


class TestOutcome3(unittest.TestCase):
    """AC-09: a real 0.3 s window, escalation after a real 0.4 s sleep, priya to devon."""

    def test_page_is_not_escalated_immediately_but_is_after_a_real_sleep(self):
        clock = ControlClock()
        page = new_page()
        self.assertFalse(page.check(clock.now()).escalated)
        t0 = time.monotonic()
        clock.sleep(0.4)
        elapsed = time.monotonic() - t0
        check = page.check(clock.now())
        self.assertGreaterEqual(elapsed, 0.4)
        self.assertEqual((check.escalated, check.from_, check.to), (True, PRIYA, DEVON))

    def test_an_answered_page_is_not_escalated_and_says_why(self):
        clock = ControlClock()
        page = new_page()
        page.acknowledge()
        clock.sleep(0.4)
        check = page.check(clock.now())
        self.assertFalse(check.escalated)
        self.assertEqual(check.reason, "already resolved")

    def test_the_full_case_waits_out_the_window_then_devon_approves(self):
        world, cmd = make()
        t0 = time.monotonic()
        case = cmd.run(world.alert("ALRT-9001"))
        elapsed = time.monotonic() - t0
        self.assertGreaterEqual(elapsed, APPROVAL_DEADLINE_S)
        self.assertTrue(case.approval.escalated)
        self.assertEqual(case.token.approved_by, DEVON)
        self.assertLess(kinds(case).index("ESCALATE"), kinds(case).index("EXECUTE"))


class TestOutcome4(unittest.TestCase):
    """AC-10: 195 ms against a 180 ms baseline resolves; 3900 ms reopens with the exact reason."""

    def test_9002_resolves_at_195_ms(self):
        _, case = run_case("ALRT-9002")
        v = case.verification
        self.assertEqual((v.status, v.verified), ("resolved", True))
        self.assertEqual((v.baseline, v.observed), (180.0, 195.0))

    def test_9002_fix_fails_reopens_at_3900_ms_and_does_not_fix_twice(self):
        _, case = run_case("ALRT-9002", fix_outcome="fix_fails")
        v = case.verification
        self.assertEqual((v.status, v.verified), ("reopened", False))
        self.assertEqual((v.baseline, v.observed), (180.0, 3900.0))
        self.assertEqual(v.reason, REOPEN_REASON)
        self.assertEqual(case.handoff_reason, "reopened")
        self.assertEqual(kinds(case).count("EXECUTE"), 1)


class TestOutcome5(unittest.TestCase):
    """AC-11: a retry is idempotent: already_executed, same execution_id, one real execution."""

    def test_retry_returns_already_executed_with_the_same_id(self):
        cmd, case = run_case("ALRT-9002")
        retry = cmd.retry_execution(case)
        self.assertEqual(case.execution.status, "executed")
        self.assertEqual(retry.status, "already_executed")
        self.assertEqual(retry.execution_id, case.execution.execution_id)
        executes = [dict(e.fields)["status"] for e in case.trace.events if e.kind == "EXECUTE"]
        self.assertEqual(executes, ["executed", "already_executed"])

    def test_many_retries_never_change_the_id(self):
        cmd, case = run_case("ALRT-9002")
        ids = {cmd.retry_execution(case).execution_id for _ in range(5)}
        self.assertEqual(ids, {case.execution.execution_id})


class TestOutcome6(unittest.TestCase):
    """AC-12: the postmortem is a draft, built from the trace, until publish() is called."""

    def test_draft_is_unpublished_and_notifies_nobody(self):
        for alert_id in ("ALRT-9001", "ALRT-9002", "ALRT-9003"):
            _, case = run_case(alert_id)
            self.assertEqual(case.draft.notified, [], alert_id)
            self.assertIs(case.draft.published, False, alert_id)

    def test_timeline_is_the_case_trace_in_order(self):
        _, case = run_case("ALRT-9002")
        expected = kinds(case)[:-2]  # minus STATE->DRAFTED and DRAFT
        self.assertEqual([line.split()[1] for line in case.draft.timeline], expected)

    def test_only_an_explicit_publish_notifies_and_only_once(self):
        cmd, case = run_case("ALRT-9001")
        outbox = OutboxNotifier()
        self.assertEqual(outbox.sent, [])
        published = cmd.publish(case, outbox)
        self.assertIs(published.published, True)
        self.assertEqual(published.notified, ["oncall-channel"])
        self.assertEqual(len(outbox.sent), 1)


if __name__ == "__main__":
    unittest.main()
