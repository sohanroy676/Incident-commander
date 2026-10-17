"""Blast-radius classifier: tiers come from the action alone (AC-03, AC-08)."""

import inspect
import unittest

from incident_commander.blast_radius import classify_remediation
from incident_commander.fixtures.alerts import ALERTS
from incident_commander.fixtures.runbooks import RUNBOOKS


class TestTiers(unittest.TestCase):
    def test_low_tier_actions(self):
        for action in ("restart_service", "scale_out_service"):
            c = classify_remediation(action)
            self.assertEqual((c.tier, c.requires_approval), ("low", False), action)
            self.assertEqual(c.action, action)

    def test_high_tier_actions(self):
        for action in ("rollback_deployment", "failover_dependency"):
            c = classify_remediation(action)
            self.assertEqual((c.tier, c.requires_approval), ("high", True), action)

    def test_reasons_name_the_property(self):
        reasons = classify_remediation("rollback_deployment").reasons
        self.assertIn("not quickly reversible", reasons)
        self.assertIn("changes running code or traffic routing", reasons)
        self.assertTrue(classify_remediation("restart_service").reasons)

    def test_unknown_actions_fail_closed(self):
        for action in ("delete_database", "", "Restart_Service", " restart_service", "rm -rf /"):
            c = classify_remediation(action)
            self.assertEqual((c.tier, c.requires_approval), ("high", True), repr(action))
            self.assertEqual(c.reasons, ("unknown action: fail closed",))


class TestSignature(unittest.TestCase):
    def test_one_parameter_and_no_severity(self):
        params = list(inspect.signature(classify_remediation).parameters)
        self.assertEqual(params, ["action"])
        for name in params:
            self.assertNotIn("sever", name.lower())


class TestSeverityIsNotAnInput(unittest.TestCase):
    def test_equal_severity_different_tiers(self):
        a1, a2 = ALERTS["ALRT-9001"], ALERTS["ALRT-9002"]
        self.assertEqual(a1.severity, a2.severity)
        c1 = classify_remediation(RUNBOOKS["RB-101"].action)
        c2 = classify_remediation(RUNBOOKS["RB-102"].action)
        self.assertEqual((c1.tier, c2.tier), ("high", "low"))


if __name__ == "__main__":
    unittest.main()
