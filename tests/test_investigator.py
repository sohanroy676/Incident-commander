"""Investigator tests: Outcome 1 (AC-07), planner rules, staleness (AC-18), order independence (AC-17)."""

import dataclasses
import itertools
import unittest

from incident_commander.clocks import DataClock
from incident_commander.config import STATIC_RANKER_ORDER
from incident_commander.fixtures.alerts import ALERTS
from incident_commander.fixtures.runbooks import RUNBOOKS
from incident_commander.fixtures.services import SERVICES
from incident_commander.investigator import (
    EVIDENCE_TOOLS,
    Hypothesis,
    ToolBox,
    investigate,
    next_tool,
)
from incident_commander.retrieval import StaticRanker
from incident_commander.types import Runbook
from incident_commander.world import SimWorld

EXPECTED = {
    "ALRT-9001": ("matched", "RB-101", 3, None),
    "ALRT-9002": ("matched", "RB-102", 3, None),
    "ALRT-9003": ("no_confident_match", None, 4, "all_refuted"),
}


def run(alert_id, world=None, order=STATIC_RANKER_ORDER, tool_order=EVIDENCE_TOOLS, **kw):
    world = world or SimWorld()
    alert = world.alert(alert_id)
    box = kw.pop("toolbox", None) or ToolBox(world, DataClock(alert.fired_at + 5.0))
    return investigate(alert, StaticRanker(order), box, tool_order=tool_order, **kw)


def as_tuple(result):
    v = result.verdict
    return v.kind, v.runbook_id, v.rounds, v.reason


class RecordingTrace:
    def __init__(self):
        self.events = []

    def emit(self, kind, **fields):
        self.events.append((kind, fields))


class TestOutcome1(unittest.TestCase):
    def test_alrt_9003_exhausts_the_budget_with_no_match(self):
        r = run("ALRT-9003")
        self.assertEqual(as_tuple(r), EXPECTED["ALRT-9003"])
        self.assertEqual(len(r.rounds), 4)

    def test_9001_and_9002_match_in_three_rounds_despite_the_wrong_first_stub(self):
        self.assertEqual(STATIC_RANKER_ORDER[0], "RB-102")
        self.assertEqual(as_tuple(run("ALRT-9001")), EXPECTED["ALRT-9001"])
        self.assertEqual(as_tuple(run("ALRT-9002")), EXPECTED["ALRT-9002"])

    def test_tool_sequence_and_modes(self):
        got = {a: [(r.tool, r.mode) for r in run(a).rounds] for a in EXPECTED}
        coverage = [
            ("get_latency", "coverage"),
            ("get_error_rate", "coverage"),
            ("get_deployments", "coverage"),
        ]
        self.assertEqual(got["ALRT-9001"], coverage)
        self.assertEqual(got["ALRT-9002"], coverage)
        self.assertEqual(got["ALRT-9003"], [*coverage, ("get_dependencies", "exploratory")])

    def test_exploratory_only_when_every_hypothesis_is_refuted(self):
        for alert_id in EXPECTED:
            r = run(alert_id)
            for rec in r.rounds:
                if rec.mode == "exploratory":
                    self.assertEqual(alert_id, "ALRT-9003")
                    self.assertTrue(all(h.status == "refuted" for h in r.hypotheses.values()))

    def test_trace_events_for_9001(self):
        trace = RecordingTrace()
        run("ALRT-9001", trace=trace)
        kinds = [k for k, _ in trace.events]
        self.assertEqual(kinds, ["ROUND", "HYPOTHESES"] * 3)
        first = trace.events[0][1]
        self.assertEqual(first["latency_elevated"], "TRUE")
        self.assertEqual(first["latency_normal"], "FALSE")
        self.assertEqual(
            trace.events[1][1],
            {"RB-101": "open", "RB-102": "refuted", "RB-103": "open", "RB-104": "refuted"},
        )
        self.assertEqual(trace.events[-1][1]["RB-101"], "confirmed")

    def test_budget_is_never_exceeded(self):
        for budget in (1, 2, 3):
            r = run("ALRT-9003", budget=budget)
            self.assertLessEqual(len(r.rounds), budget)
            self.assertEqual(r.verdict.kind, "no_confident_match")
            self.assertEqual(r.verdict.rounds, len(r.rounds))

    def test_budget_too_small_for_a_match_is_insufficient_evidence(self):
        r = run("ALRT-9001", budget=2)
        self.assertEqual(as_tuple(r), ("no_confident_match", None, 2, "insufficient_evidence"))


def hyp(rid, undetermined, status="open"):
    return Hypothesis(rid, tuple(undetermined), status, tuple(undetermined))


class TestNextTool(unittest.TestCase):
    ORDER = EVIDENCE_TOOLS

    def test_coverage_first_picks_the_tool_answering_most_hypotheses(self):
        hs = {
            "RB-101": hyp("RB-101", ["error_normal", "deploy_in_window"]),
            "RB-103": hyp("RB-103", ["error_elevated"]),
            "RB-104": hyp("RB-104", ["error_elevated", "deploy_in_window"]),
        }
        ranks = {"RB-101": 1, "RB-103": 2, "RB-104": 3}
        # error_rate answers 3 hypotheses, deployments 2
        self.assertEqual(next_tool(hs, set(), ranks, self.ORDER), ("get_error_rate", "coverage"))

    def test_tie_break_one_is_best_retrieval_rank(self):
        hs = {
            "RB-101": hyp("RB-101", ["deploy_in_window"]),
            "RB-103": hyp("RB-103", ["dependency_unhealthy"]),
        }
        low_first = next_tool(hs, set(), {"RB-101": 1, "RB-103": 2}, self.ORDER)
        high_first = next_tool(hs, set(), {"RB-101": 2, "RB-103": 1}, self.ORDER)
        self.assertEqual(low_first, ("get_deployments", "coverage"))
        self.assertEqual(high_first, ("get_dependencies", "coverage"))

    def test_tie_break_two_is_fixed_tool_order(self):
        hs = {"RB-101": hyp("RB-101", ["deploy_in_window", "error_normal"])}
        self.assertEqual(
            next_tool(hs, set(), {"RB-101": 1}, self.ORDER), ("get_error_rate", "coverage")
        )
        reversed_order = tuple(reversed(self.ORDER))
        self.assertEqual(
            next_tool(hs, set(), {"RB-101": 1}, reversed_order), ("get_deployments", "coverage")
        )

    def test_called_tools_are_skipped(self):
        hs = {"RB-101": hyp("RB-101", ["error_normal", "deploy_in_window"])}
        self.assertEqual(
            next_tool(hs, {"get_error_rate"}, {"RB-101": 1}, self.ORDER),
            ("get_deployments", "coverage"),
        )

    def test_refuted_hypotheses_do_not_count(self):
        hs = {
            "RB-101": hyp("RB-101", ["deploy_in_window"]),
            "RB-103": hyp("RB-103", ["dependency_unhealthy"], status="refuted"),
        }
        self.assertEqual(
            next_tool(hs, set(), {"RB-101": 2, "RB-103": 1}, self.ORDER),
            ("get_deployments", "coverage"),
        )

    def test_exploratory_when_nothing_is_undetermined(self):
        hs = {"RB-101": hyp("RB-101", [], status="refuted")}
        self.assertEqual(
            next_tool(hs, {"get_latency"}, {"RB-101": 1}, self.ORDER),
            ("get_error_rate", "exploratory"),
        )

    def test_none_when_every_tool_was_called(self):
        hs = {"RB-101": hyp("RB-101", [], status="refuted")}
        self.assertIsNone(next_tool(hs, set(self.ORDER), {"RB-101": 1}, self.ORDER))


class TestAmbiguity(unittest.TestCase):
    def test_two_confirmed_hypotheses_is_no_confident_match(self):
        twins = {
            rid: Runbook(rid, rid, "x", ("latency_elevated",), "restart_service")
            for rid in ("RB-A", "RB-B")
        }
        r = run("ALRT-9001", runbooks=twins, order=("RB-A", "RB-B"))
        self.assertEqual(as_tuple(r), ("no_confident_match", None, 1, "ambiguous_match"))


class FakeStaleOnce(ToolBox):
    """First call of one tool comes back stale; the refetch is fresh."""

    def __init__(self, world, clock, tool):
        super().__init__(world, clock)
        self._tool, self._seen = tool, 0

    def call(self, tool, service, fired_at):
        obs = super().call(tool, service, fired_at)
        if tool == self._tool:
            self._seen += 1
            if self._seen == 1:
                return dataclasses.replace(obs, fresh=False)
        return obs


class TestStaleness(unittest.TestCase):
    def stale_world(self):
        return SimWorld(tool_lags={"get_deployments": 900.0})  # budget is 300 s

    def test_stale_costs_one_refetch_and_never_yields_a_match(self):
        for alert_id in EXPECTED:
            r = run(alert_id, world=self.stale_world())
            self.assertNotEqual(r.verdict.kind, "matched", alert_id)
            deploys = [x for x in r.rounds if x.tool == "get_deployments"]
            if alert_id != "ALRT-9003":  # 9003 refutes everything before it needs deployments
                self.assertEqual([x.mode for x in deploys], ["coverage", "refetch"], alert_id)
                self.assertTrue(all(not x.fresh for x in deploys))
                self.assertEqual(r.verdict.reason, "insufficient_evidence", alert_id)

    def test_stale_predicates_are_unknown(self):
        r = run("ALRT-9001", world=self.stale_world())
        deploys = [x for x in r.rounds if x.tool == "get_deployments"]
        for x in deploys:
            self.assertTrue(all(v.name == "UNKNOWN" for v in x.values.values()))
        self.assertEqual(r.hypotheses["RB-101"].status, "open")

    def test_refetch_is_a_round_and_counts_against_the_budget(self):
        r = run("ALRT-9001", world=self.stale_world())
        self.assertEqual(len(r.rounds), 4)
        self.assertLessEqual(r.verdict.rounds, 4)

    def test_refetch_can_recover_a_fresh_answer(self):
        world = SimWorld()
        alert = world.alert("ALRT-9001")
        box = FakeStaleOnce(world, DataClock(alert.fired_at + 5.0), "get_deployments")
        r = run("ALRT-9001", world=world, toolbox=box)
        self.assertEqual(as_tuple(r), ("matched", "RB-101", 4, None))
        self.assertEqual(r.rounds[-1].mode, "refetch")

    def test_no_refetch_when_the_budget_is_spent(self):
        world = SimWorld()
        alert = world.alert("ALRT-9001")
        box = FakeStaleOnce(world, DataClock(alert.fired_at + 5.0), "get_latency")
        r = run("ALRT-9001", world=world, toolbox=box, budget=1)
        self.assertEqual(len(r.rounds), 1)
        self.assertEqual(r.verdict.kind, "no_confident_match")

    def test_fresh_data_is_not_refetched(self):
        self.assertTrue(all(x.mode != "refetch" for x in run("ALRT-9001").rounds))


class TestToolError(unittest.TestCase):
    def broken_world(self):
        broken = dataclasses.replace(SERVICES["checkout-service"], error_rate=self._boom)
        return SimWorld(services={**SERVICES, "checkout-service": broken})

    @staticmethod
    def _boom(t):
        raise RuntimeError("metrics backend down")

    def test_error_leaves_predicates_unknown_and_the_verdict_insufficient(self):
        r = run("ALRT-9001", world=self.broken_world())
        errored = [o for o in r.observations if o.status == "error"]
        self.assertEqual(len(errored), 1)
        self.assertEqual(errored[0].tool, "get_error_rate")
        self.assertEqual(r.verdict.kind, "no_confident_match")
        self.assertEqual(r.verdict.reason, "insufficient_evidence")
        rec = next(x for x in r.rounds if x.tool == "get_error_rate")
        self.assertTrue(all(v.name == "UNKNOWN" for v in rec.values.values()))

    def test_an_errored_tool_is_not_retried(self):
        r = run("ALRT-9001", world=self.broken_world())
        self.assertEqual([x.tool for x in r.rounds].count("get_error_rate"), 1)
        self.assertTrue(all(x.mode != "refetch" for x in r.rounds))


class TestOrderIndependence(unittest.TestCase):
    """AC-17: permuting tie-breaks never changes a verdict on any fixture."""

    def test_every_ranker_and_tool_order_gives_the_same_verdict(self):
        world = SimWorld()
        checked = 0
        for alert_id, (kind, runbook, _, reason) in EXPECTED.items():
            for order in itertools.permutations(RUNBOOKS):
                for tool_order in itertools.permutations(EVIDENCE_TOOLS):
                    r = run(alert_id, world=world, order=order, tool_order=tool_order)
                    got = (r.verdict.kind, r.verdict.runbook_id, r.verdict.reason)
                    self.assertEqual(got, (kind, runbook, reason), (alert_id, order, tool_order))
                    self.assertLessEqual(len(r.rounds), 4)
                    checked += 1
        self.assertEqual(checked, 3 * 24 * 24)


class TestToolBox(unittest.TestCase):
    def test_no_get_logs(self):
        box = ToolBox(SimWorld(), DataClock(0.0))
        self.assertEqual(
            box.names, ("get_latency", "get_error_rate", "get_deployments", "get_dependencies")
        )
        self.assertNotIn("get_logs", box.names)
        with self.assertRaises(KeyError):
            box.call("get_logs", "checkout-service", ALERTS["ALRT-9001"].fired_at)

    def test_investigation_never_reads_logs(self):
        for alert_id in EXPECTED:
            r = run(alert_id)
            self.assertNotIn("get_logs", {o.tool for o in r.observations})


class TestRankerContract(unittest.TestCase):
    def test_unknown_runbook_id_from_the_ranker_is_rejected(self):
        with self.assertRaises(ValueError):
            run("ALRT-9001", order=("RB-101", "RB-999"))

    def test_partial_ranker_still_works(self):
        r = run("ALRT-9001", order=("RB-103",))
        self.assertEqual(as_tuple(r), EXPECTED["ALRT-9001"])


if __name__ == "__main__":
    unittest.main()
