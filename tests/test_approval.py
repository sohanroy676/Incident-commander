"""Approval gate on the real clock: no patched sleep, lower-bound timing asserts (AC-09)."""

import unittest

from incident_commander.approval import (
    ACKNOWLEDGED,
    ESCALATED,
    PENDING,
    ApprovalGate,
    Page,
    ScriptedResponder,
)
from incident_commander.clocks import ControlClock

PRIYA, DEVON = "engineer-priya", "engineer-devon"


class CountingClock(ControlClock):
    """Observes real sleeps without faking them."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        super().sleep(seconds)


def gate(script, clock=None, **kw):
    clock = clock or ControlClock()
    return clock, ApprovalGate(clock, ScriptedResponder(script), PRIYA, DEVON, 0.3, **kw)


class TestPage(unittest.TestCase):
    def test_immediate_check_is_not_escalated(self):
        clock = ControlClock()
        page = Page("p1", PRIYA, clock.now(), 0.3, DEVON)
        c = page.check(clock.now())
        self.assertFalse(c.escalated)
        self.assertEqual(page.state, PENDING)

    def test_real_sleep_past_the_deadline_escalates(self):
        clock = ControlClock()
        page = Page("p1", PRIYA, clock.now(), 0.3, DEVON)
        t0 = clock.now()
        clock.sleep(0.4)
        c = page.check(clock.now())
        self.assertGreaterEqual(clock.now() - t0, 0.4)
        self.assertLess(clock.now() - t0, 2.0)
        self.assertEqual((c.escalated, c.from_, c.to), (True, PRIYA, DEVON))
        self.assertEqual(page.state, ESCALATED)

    def test_answered_page_is_never_escalated(self):
        clock = ControlClock()
        page = Page("p2", PRIYA, clock.now(), 0.3, DEVON)
        page.acknowledge()
        self.assertEqual(page.state, ACKNOWLEDGED)
        late = page.check(clock.now() + 10)
        self.assertFalse(late.escalated)
        self.assertEqual(late.reason, "already resolved")

    def test_acknowledge_does_not_undo_escalation(self):
        page = Page("p3", PRIYA, 0.0, 0.3, DEVON)
        page.check(1.0)
        page.acknowledge()
        self.assertEqual(page.state, ESCALATED)

    def test_boundary_exactly_at_deadline_escalates(self):
        page = Page("p4", PRIYA, 0.0, 0.3, DEVON)
        self.assertFalse(page.check(0.299).escalated)
        self.assertTrue(page.check(0.3).escalated)


class TestGate(unittest.TestCase):
    def test_primary_approves_in_time(self):
        _, g = gate({PRIYA: (0.05, "approve")})
        out = g.request("rollback_deployment", "checkout-service")
        self.assertEqual((out.status, out.escalated), ("approved", False))
        self.assertEqual(out.token.approved_by, PRIYA)
        self.assertEqual(out.token.action, "rollback_deployment")
        self.assertEqual(out.token.service, "checkout-service")
        self.assertEqual(len(out.pages), 1)

    def test_primary_silent_secondary_approves(self):
        clock, g = gate({PRIYA: (None, ""), DEVON: (0.1, "approve")})
        t0 = clock.now()
        out = g.request("rollback_deployment", "checkout-service")
        elapsed = clock.now() - t0
        self.assertEqual((out.status, out.escalated), ("approved", True))
        self.assertEqual(out.token.approved_by, DEVON)
        self.assertGreaterEqual(elapsed, 0.4)
        self.assertLess(elapsed, 2.0)
        self.assertEqual(len(out.pages), 2)

    def test_both_silent_expires_without_token(self):
        clock, g = gate({})
        t0 = clock.now()
        out = g.request("rollback_deployment", "checkout-service")
        self.assertEqual((out.status, out.token, out.escalated), ("expired", None, True))
        self.assertGreaterEqual(clock.now() - t0, 0.6)
        self.assertLess(clock.now() - t0, 3.0)

    def test_denial_gives_no_token_and_no_escalation(self):
        _, g = gate({PRIYA: (0.0, "deny")})
        out = g.request("rollback_deployment", "checkout-service")
        self.assertEqual((out.status, out.token, out.escalated), ("denied", None, False))

    def test_secondary_denial(self):
        _, g = gate({DEVON: (0.0, "deny")})
        out = g.request("rollback_deployment", "checkout-service")
        self.assertEqual((out.status, out.token, out.escalated), ("denied", None, True))

    def test_primary_answer_after_deadline_does_not_count(self):
        _, g = gate({PRIYA: (0.5, "approve"), DEVON: (None, "")})
        out = g.request("rollback_deployment", "checkout-service")
        self.assertEqual((out.status, out.token), ("expired", None))

    def test_unrecognised_reply_fails_closed(self):
        for reply in ("APPROVE", "yes", "approved", ""):
            _, g = gate({PRIYA: (0.0, reply)})
            out = g.request("rollback_deployment", "checkout-service")
            self.assertIsNone(out.token, reply)
            self.assertEqual(out.status, "denied")

    def test_waits_only_through_clock_sleep(self):
        clock = CountingClock()
        _, g = gate({PRIYA: (None, ""), DEVON: (0.1, "approve")}, clock=clock, tick_s=0.02)
        g.request("rollback_deployment", "checkout-service")
        self.assertGreater(len(clock.sleeps), 5)
        self.assertTrue(all(s == 0.02 for s in clock.sleeps))

    def test_bad_arguments(self):
        r = ScriptedResponder({})
        c = ControlClock()
        with self.assertRaises(ValueError):
            ApprovalGate(c, r, PRIYA, DEVON, 0)
        with self.assertRaises(ValueError):
            ApprovalGate(c, r, PRIYA, DEVON, 0.3, tick_s=0)
        with self.assertRaises(ValueError):
            ApprovalGate(c, r, PRIYA, PRIYA, 0.3)


class TestScriptedResponder(unittest.TestCase):
    def test_answers_only_after_delay(self):
        r = ScriptedResponder({PRIYA: (0.1, "approve"), DEVON: (None, "")})
        self.assertIsNone(r.poll(PRIYA, 0.09))
        self.assertEqual(r.poll(PRIYA, 0.1), "approve")
        self.assertIsNone(r.poll(DEVON, 99))
        self.assertIsNone(r.poll("nobody", 99))


if __name__ == "__main__":
    unittest.main()
