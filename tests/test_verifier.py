"""Verifier: resolved only on fresh post-fix data within 1.10 x baseline (AC-10)."""

import unittest

from incident_commander.clocks import DataClock
from incident_commander.executor import Executor
from incident_commander.fixtures.alerts import ALERTS
from incident_commander.types import ApprovalToken, Execution, Observation
from incident_commander.verifier import NO_FRESH_DATA, NOT_RESOLVED, assess, verify
from incident_commander.world import SimWorld

EXEC_AT = 1000.0


def obs(points, *, baseline=180.0, as_of=1300.0, fresh=True, status="ok"):
    return Observation(
        "get_latency", "svc", EXEC_AT, EXEC_AT + 300, tuple(points), as_of, 60, status,
        3.0, fresh, None, baseline,
    )  # fmt: skip


def run_case(alert_id, outcome):
    world = SimWorld()
    alert = ALERTS[alert_id]
    clock = DataClock(alert.fired_at + 5.0)
    action = "rollback_deployment" if alert_id == "ALRT-9001" else "restart_service"
    ex = Executor(world, clock, outcome)
    token = ApprovalToken(action, alert.service, "engineer-devon", 0.0)
    result = ex.execute(action, alert.service, alert_id, token)
    execution = Execution(result.execution_id, (), action, alert.service, clock.now())
    return verify(world, clock, alert.service, alert.metric, execution)


class TestAssess(unittest.TestCase):
    def test_boundary_198_resolves_and_198_1_reopens(self):
        ok = assess("latency_ms", obs([(1100.0, 198.0)]), EXEC_AT)
        bad = assess("latency_ms", obs([(1100.0, 198.1)]), EXEC_AT)
        self.assertEqual((ok.status, ok.verified), ("resolved", True))
        self.assertEqual((bad.status, bad.verified), ("reopened", False))
        self.assertEqual(bad.reason, NOT_RESOLVED)

    def test_stale_error_empty_or_pre_fix_data_reopens(self):
        points = [(1100.0, 180.0)]
        cases = [
            obs(points, fresh=False),
            obs(points, status="error"),
            obs([]),
            obs(points, as_of=EXEC_AT - 1),
            obs([(EXEC_AT - 60, 180.0)]),  # only pre-fix points
        ]
        for o in cases:
            v = assess("latency_ms", o, EXEC_AT)
            self.assertEqual((v.status, v.verified, v.reason), ("reopened", False, NO_FRESH_DATA))

    def test_missing_baseline_never_resolves(self):
        v = assess("latency_ms", obs([(1100.0, 1.0)], baseline=None), EXEC_AT)
        self.assertFalse(v.verified)


class TestVerifyOnFixtures(unittest.TestCase):
    def test_9002_success_is_resolved_at_195(self):
        v = run_case("ALRT-9002", "success")
        self.assertEqual(
            (v.status, v.verified, v.baseline, v.observed), ("resolved", True, 180.0, 195.0)
        )

    def test_9001_success_is_resolved_at_182(self):
        v = run_case("ALRT-9001", "success")
        self.assertEqual((v.status, v.verified, v.observed), ("resolved", True, 182.0))

    def test_9002_fix_fails_is_reopened_at_3900(self):
        v = run_case("ALRT-9002", "fix_fails")
        self.assertEqual((v.status, v.verified, v.observed), ("reopened", False, 3900.0))
        self.assertEqual(v.reason, "remediation ran but did not resolve the signal")

    def test_unknown_metric_reopens(self):
        world = SimWorld()
        ex = Execution("exec-x", (), "restart_service", "inventory-service", 1.0)
        v = verify(world, DataClock(1.0), "inventory-service", "bogus", ex)
        self.assertEqual((v.status, v.reason), ("reopened", NO_FRESH_DATA))


if __name__ == "__main__":
    unittest.main()
