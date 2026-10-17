"""SimWorld.apply_remediation: the only write path, effective after REMEDIATION_DELAY_S."""

import unittest

from incident_commander.fixtures.alerts import ALERTS
from incident_commander.fixtures.services import REMEDIATION_DELAY_S
from incident_commander.world import SimWorld

A1 = ALERTS["ALRT-9001"]
A2 = ALERTS["ALRT-9002"]
AT = A2.fired_at + 10.0  # not on the 60 s grid on purpose


def last_latency(world: SimWorld, service: str, until: float) -> float:
    return world.latency_points(service, until - 600, until, until)[-1][1]


class TestApplyRemediation(unittest.TestCase):
    def test_restart_brings_inventory_to_195_after_the_delay(self):
        w = SimWorld()
        w.apply_remediation("inventory-service", "restart_service", AT)
        self.assertEqual(last_latency(w, "inventory-service", AT + 200), 195.0)

    def test_fix_fails_keeps_latency_high(self):
        w = SimWorld()
        w.apply_remediation("inventory-service", "restart_service", AT, outcome="fix_fails")
        self.assertEqual(last_latency(w, "inventory-service", AT + 200), 3900.0)

    def test_rollback_brings_checkout_to_182(self):
        w = SimWorld()
        w.apply_remediation("checkout-service", "rollback_deployment", A1.fired_at)
        self.assertEqual(last_latency(w, "checkout-service", A1.fired_at + 200), 182.0)

    def test_nothing_changes_before_the_delay(self):
        w = SimWorld()
        before = w.latency_points("inventory-service", AT - 3600, AT + 600, AT + 600)
        w.apply_remediation("inventory-service", "restart_service", AT)
        after = w.latency_points("inventory-service", AT - 3600, AT + 600, AT + 600)
        cut = AT + REMEDIATION_DELAY_S
        self.assertEqual([p for p in after if p[0] < cut], [p for p in before if p[0] < cut])
        self.assertTrue(all(v == 195.0 for t, v in after if t >= cut))

    def test_other_services_and_error_series_are_untouched(self):
        w = SimWorld()
        snap = lambda: (
            w.latency_points("checkout-service", AT - 3600, AT + 300, AT + 300),
            w.error_points("inventory-service", AT - 3600, AT + 300, AT + 300),
        )
        before = snap()
        w.apply_remediation("inventory-service", "restart_service", AT)
        self.assertEqual(snap(), before)

    def test_known_pair_without_an_effect_changes_nothing(self):
        w = SimWorld()
        before = w.latency_points("inventory-service", AT - 3600, AT + 300, AT + 300)
        w.apply_remediation("inventory-service", "scale_out_service", AT)
        self.assertEqual(
            w.latency_points("inventory-service", AT - 3600, AT + 300, AT + 300), before
        )

    def test_bad_inputs_raise(self):
        w = SimWorld()
        with self.assertRaises(ValueError):
            w.apply_remediation("inventory-service", "delete_database", AT)
        with self.assertRaises(ValueError):
            w.apply_remediation("inventory-service", "restart_service", AT, outcome="maybe")
        with self.assertRaises(KeyError):
            w.apply_remediation("no-such-service", "restart_service", AT)

    def test_failed_call_leaves_the_world_unchanged(self):
        w = SimWorld()
        before = w.latency_points("inventory-service", AT - 3600, AT + 300, AT + 300)
        with self.assertRaises(ValueError):
            w.apply_remediation("inventory-service", "restart_service", AT, outcome="maybe")
        self.assertEqual(
            w.latency_points("inventory-service", AT - 3600, AT + 300, AT + 300), before
        )


if __name__ == "__main__":
    unittest.main()
