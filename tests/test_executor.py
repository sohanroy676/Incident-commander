"""Executor: exactly-once effects and the approval-token requirement (AC-11, AC-19)."""

import re
import unittest

from incident_commander.clocks import DataClock
from incident_commander.executor import (
    ApprovalRequired,
    Executor,
    execution_id_for,
)
from incident_commander.fixtures.alerts import ALERTS
from incident_commander.types import ApprovalToken
from incident_commander.world import SimWorld

FIRED = ALERTS["ALRT-9001"].fired_at


class CountingWorld(SimWorld):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple] = []

    def apply_remediation(self, service, action, at, outcome="success"):
        super().apply_remediation(service, action, at, outcome)
        self.calls.append((service, action))


def make():
    world = CountingWorld()
    return world, Executor(world, DataClock(FIRED + 5.0))


def token(action="rollback_deployment", service="checkout-service"):
    return ApprovalToken(action, service, "engineer-devon", 1.0)


class TestIdempotency(unittest.TestCase):
    def test_first_executes_retry_returns_same_id(self):
        world, ex = make()
        first = ex.execute("restart_service", "inventory-service", "ALRT-9002", None)
        retry = ex.execute("restart_service", "inventory-service", "ALRT-9002", None)
        self.assertEqual(first.status, "executed")
        self.assertEqual(retry.status, "already_executed")
        self.assertEqual(first.execution_id, retry.execution_id)
        self.assertRegex(first.execution_id, r"^exec-[0-9a-f]{10}$")
        self.assertEqual(len(world.calls), 1)

    def test_retry_of_high_tier_needs_no_second_token(self):
        world, ex = make()
        a = ex.execute("rollback_deployment", "checkout-service", "ALRT-9001", token())
        b = ex.execute("rollback_deployment", "checkout-service", "ALRT-9001", None)
        self.assertEqual((a.status, b.status), ("executed", "already_executed"))
        self.assertEqual(a.execution_id, b.execution_id)
        self.assertEqual(len(world.calls), 1)

    def test_different_case_is_a_new_execution(self):
        world, ex = make()
        a = ex.execute("restart_service", "inventory-service", "CASE-1", None)
        b = ex.execute("restart_service", "inventory-service", "CASE-2", None)
        self.assertEqual((a.status, b.status), ("executed", "executed"))
        self.assertNotEqual(a.execution_id, b.execution_id)
        self.assertEqual(len(world.calls), 2)

    def test_id_is_deterministic_across_executors(self):
        a = make()[1].execute("restart_service", "inventory-service", "ALRT-9002", None)
        b = make()[1].execute("restart_service", "inventory-service", "ALRT-9002", None)
        self.assertEqual(a.execution_id, b.execution_id)

    def test_execution_id_for(self):
        key = ("c", "restart_service", "s")
        self.assertEqual(execution_id_for(key), execution_id_for(key))
        self.assertNotEqual(execution_id_for(key), execution_id_for(("c2", "restart_service", "s")))
        self.assertTrue(re.fullmatch(r"exec-[0-9a-f]{10}", execution_id_for(key)))


class TestApprovalRequired(unittest.TestCase):
    def assert_blocked(self, tok):
        world, ex = make()
        with self.assertRaises(ApprovalRequired):
            ex.execute("rollback_deployment", "checkout-service", "ALRT-9001", tok)
        self.assertEqual(world.calls, [])
        # a blocked attempt stores nothing: a valid token still executes afterwards
        ok = ex.execute("rollback_deployment", "checkout-service", "ALRT-9001", token())
        self.assertEqual(ok.status, "executed")

    def test_missing_token(self):
        self.assert_blocked(None)

    def test_token_for_another_action(self):
        self.assert_blocked(token(action="failover_dependency"))

    def test_token_for_another_service(self):
        self.assert_blocked(token(service="inventory-service"))

    def test_low_tier_needs_no_token(self):
        _, ex = make()
        r = ex.execute("scale_out_service", "inventory-service", "c", None)
        self.assertEqual(r.status, "executed")

    def test_unknown_action_is_treated_as_high_tier(self):
        _, ex = make()
        with self.assertRaises(ApprovalRequired):
            ex.execute("delete_database", "inventory-service", "c", None)


class TestFailures(unittest.TestCase):
    def test_unknown_service_fails_and_is_not_stored(self):
        _world, ex = make()
        r = ex.execute("restart_service", "no-such-service", "c", None)
        self.assertEqual((r.status, r.execution_id), ("failed", None))
        self.assertIn("KeyError", r.error)
        again = ex.execute("restart_service", "no-such-service", "c", None)
        self.assertEqual(again.status, "failed")  # retried, not "already_executed"

    def test_unknown_action_with_matching_token_fails(self):
        world, ex = make()
        r = ex.execute(
            "delete_database",
            "inventory-service",
            "c",
            token("delete_database", "inventory-service"),
        )
        self.assertEqual(r.status, "failed")
        self.assertIn("ValueError", r.error)
        self.assertEqual(world.calls, [])

    def test_failed_attempt_can_be_retried_successfully(self):
        world, ex = make()
        original = world.apply_remediation
        state = {"fail": True}

        def flaky(service, action, at, outcome="success"):
            if state["fail"]:
                raise ValueError("transient")
            return original(service, action, at, outcome)

        world.apply_remediation = flaky
        self.assertEqual(
            ex.execute("restart_service", "inventory-service", "c", None).status, "failed"
        )
        state["fail"] = False
        self.assertEqual(
            ex.execute("restart_service", "inventory-service", "c", None).status, "executed"
        )


if __name__ == "__main__":
    unittest.main()
