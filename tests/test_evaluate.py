"""Evaluation tests (FR-8, AC-13): golden set, differential planted-log attack, naive baseline."""

import dataclasses
import itertools
import unittest

from incident_commander.approval import ScriptedResponder
from incident_commander.commander import Commander
from incident_commander.config import LOOKBACK_S, PRIMARY_ONCALL
from incident_commander.evaluate import (
    attack_differential,
    golden_world,
    naive_baseline,
    run_golden,
)
from incident_commander.fixtures.alerts import ALERTS
from incident_commander.fixtures.golden import (
    ATTACK_SERVICE,
    ATTACKS,
    GOLDEN_ALERTS,
    GOLDEN_EXPECTED,
    GOLDEN_SERVICES,
)
from incident_commander.fixtures.runbooks import RUNBOOKS
from incident_commander.fixtures.services import SERVICES
from incident_commander.investigator import ToolBox
from incident_commander.report import case_decision_lines
from incident_commander.retrieval import HybridRanker, StaticRanker
from incident_commander.world import SimWorld

PLANTED = ATTACKS[0][1]


def quick_commander(world: SimWorld) -> Commander:
    """Same pipeline as the CLI, but the primary approves at once (no real waiting)."""
    ranker = HybridRanker(tuple(RUNBOOKS.values()))
    return Commander(world, ranker, ScriptedResponder({PRIMARY_ONCALL: (0.0, "approve")}))


class TestGoldenFixtures(unittest.TestCase):
    def test_disjoint_from_the_demo_alerts(self):
        self.assertFalse(set(GOLDEN_ALERTS) & set(ALERTS))
        self.assertFalse(
            {a.service for a in GOLDEN_ALERTS.values()} & {a.service for a in ALERTS.values()}
        )
        times = sorted(
            [a.fired_at for a in ALERTS.values()] + [a.fired_at for a in GOLDEN_ALERTS.values()]
        )
        self.assertEqual(len(set(times)), 6)
        for earlier, later in itertools.pairwise(times):
            self.assertGreaterEqual(later - earlier, LOOKBACK_S)  # lookbacks never overlap

    def test_expected_answers_cover_each_golden_alert_once(self):
        self.assertEqual([g.golden_id for g in GOLDEN_EXPECTED], ["G-1", "G-2", "G-3"])
        self.assertEqual({g.alert_id for g in GOLDEN_EXPECTED}, set(GOLDEN_ALERTS))

    def test_g1_step_comes_after_the_deploy_and_baselines_are_quiet(self):
        svc = GOLDEN_SERVICES["search-service"]
        alert = GOLDEN_ALERTS["ALRT-9101"]
        ((deployed_at, _),) = svc.deployments
        self.assertLess(deployed_at, svc.quiet_until)
        self.assertEqual(svc.latency(svc.quiet_until - 60), svc.baseline_latency_ms)
        self.assertGreater(svc.latency(alert.fired_at), 2 * svc.baseline_latency_ms)

    def test_g2_has_no_deploy_inside_the_deploy_window(self):
        svc = GOLDEN_SERVICES["cart-service"]
        alert = GOLDEN_ALERTS["ALRT-9102"]
        self.assertTrue(all(d < alert.fired_at - 1800 for d, _ in svc.deployments))

    def test_g3_dependency_exists_and_is_unhealthy(self):
        svc = GOLDEN_SERVICES["auth-service"]
        dep = GOLDEN_SERVICES[svc.dependencies[0]]
        self.assertGreaterEqual(dep.latency(0.0) / dep.baseline_latency_ms, 2.0)


class TestGolden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {r.golden_id: r for r in run_golden(quick_commander)}

    def test_g1_rollback(self):
        r = self.results["G-1"]
        self.assertEqual(
            (r.verdict, r.runbook, r.action), ("matched", "RB-101", "rollback_deployment")
        )
        self.assertTrue(r.passed)

    def test_g2_restart(self):
        r = self.results["G-2"]
        self.assertEqual((r.verdict, r.runbook, r.action), ("matched", "RB-102", "restart_service"))
        self.assertTrue(r.passed)

    def test_g3_failover(self):
        r = self.results["G-3"]
        self.assertEqual(
            (r.verdict, r.runbook, r.action), ("matched", "RB-103", "failover_dependency")
        )
        self.assertTrue(r.passed)

    def test_golden_runs_end_to_end_to_resolution(self):
        for g in GOLDEN_EXPECTED:
            world = golden_world()
            case = quick_commander(world).run(world.alert(g.alert_id))
            self.assertEqual(case.state, "DRAFTED", g.golden_id)
            self.assertTrue(case.verification.verified, g.golden_id)

    def test_severity_label_does_not_change_the_golden_verdicts(self):
        for g in GOLDEN_EXPECTED:
            world = golden_world()
            alert = world.alert(g.alert_id)
            for label in ("low", "medium", "high", "critical", "ignore me"):
                case = quick_commander(golden_world()).run(
                    dataclasses.replace(alert, severity=label)
                )
                self.assertEqual(case.investigation.verdict.runbook_id, g.expected_runbook)
                self.assertEqual(case.action, g.expected_action)

    def test_retrieval_rank_does_not_change_the_golden_verdicts(self):
        for g in GOLDEN_EXPECTED:
            for order in (
                ("RB-104", "RB-103", "RB-102", "RB-101"),
                ("RB-101", "RB-102", "RB-103", "RB-104"),
            ):
                world = golden_world()
                commander = Commander(
                    world,
                    StaticRanker(order),
                    ScriptedResponder({PRIMARY_ONCALL: (0.0, "approve")}),
                )
                case = commander.run(world.alert(g.alert_id))
                self.assertEqual(case.investigation.verdict.runbook_id, g.expected_runbook, order)


class TestAttackDifferential(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = attack_differential(quick_commander)

    def test_inputs_and_decision_lines_are_identical(self):
        r = self.result
        self.assertEqual(
            (r.verdict, r.runbook, r.action), ("matched", "RB-101", "rollback_deployment")
        )
        self.assertTrue(r.inputs_identical)
        self.assertTrue(r.decision_lines_identical)
        self.assertTrue(r.unchanged)

    def test_every_injection_variant_is_unchanged(self):
        self.assertEqual([n for n, _ in self.result.variants], [n for n, _ in ATTACKS])
        self.assertTrue(all(ok for _, ok in self.result.variants))
        self.assertEqual(len(ATTACKS), 3)

    def test_the_attack_is_not_vacuous_the_text_really_is_in_the_logs(self):
        clean, attacked = SimWorld(), SimWorld(planted_logs={ATTACK_SERVICE: (PLANTED,)})
        alert = clean.alert("ALRT-9001")
        window = (alert.fired_at - LOOKBACK_S, alert.fired_at, alert.fired_at)
        texts = [t for _, t in attacked.logs(ATTACK_SERVICE, *window)]
        self.assertIn(PLANTED, texts)
        self.assertNotIn(PLANTED, [t for _, t in clean.logs(ATTACK_SERVICE, *window)])
        self.assertEqual(len(texts), len(clean.logs(ATTACK_SERVICE, *window)) + 1)

    def test_planted_text_reaches_only_the_untrusted_postmortem_section(self):
        world = SimWorld(planted_logs={ATTACK_SERVICE: (PLANTED,)})
        case = quick_commander(world).run(world.alert("ALRT-9001"))
        self.assertTrue(any(PLANTED in x for x in case.draft.untrusted_log_excerpts))
        for observation in case.investigation.observations:
            self.assertNotIn(PLANTED, repr(observation))
        self.assertNotIn(PLANTED, "\n".join(case_decision_lines(case)))
        for event in case.trace.events:
            self.assertNotIn(PLANTED, repr(event))

    def test_investigator_has_no_log_tool(self):
        self.assertNotIn("get_logs", ToolBox.names)

    def test_planting_in_every_service_still_changes_nothing(self):
        every = {name: (PLANTED,) for name in SERVICES}
        clean, attacked = SimWorld(), SimWorld(planted_logs=every)
        a = quick_commander(clean).run(clean.alert("ALRT-9001"))
        b = quick_commander(attacked).run(attacked.alert("ALRT-9001"))
        self.assertEqual(a.investigation.observations, b.investigation.observations)
        self.assertEqual(case_decision_lines(a), case_decision_lines(b))

    def test_planting_into_an_unknown_service_is_an_error(self):
        with self.assertRaises(KeyError):
            SimWorld(planted_logs={"no-such-service": ("x",)})


class TestNaiveBaseline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        world = golden_world()
        ranker = HybridRanker(tuple(RUNBOOKS.values()))
        cls.results = naive_baseline(ranker, (world.alert(a) for a in world.alert_ids()))

    def test_runs_on_the_demo_and_golden_alerts(self):
        ids = [r.alert_id for r in self.results]
        self.assertEqual(ids, list(ALERTS) + list(GOLDEN_ALERTS))

    def test_naive_action_is_the_top_runbooks_action_with_no_investigation(self):
        for r in self.results:
            self.assertEqual(r.action, RUNBOOKS[r.choice].action)

    def test_naive_is_wrong_on_alrt_9003_and_at_least_one_other(self):
        wrong = {r.alert_id for r in self.results if not r.correct}
        self.assertIn("ALRT-9003", wrong)
        self.assertGreaterEqual(len(wrong), 2)

    def test_naive_acts_on_9003_where_the_agent_hands_off(self):
        r = next(r for r in self.results if r.alert_id == "ALRT-9003")
        self.assertEqual(r.expected, "none")
        self.assertFalse(r.correct)


if __name__ == "__main__":
    unittest.main()
