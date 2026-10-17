"""Tool contract tests (FR-1, AC-02): typed, read-only, declared freshness, errors contained."""

import inspect
import unittest

from incident_commander import tools
from incident_commander.clocks import DataClock
from incident_commander.config import LOOKBACK_S, TOOL_SPECS
from incident_commander.fixtures.alerts import ALERTS
from incident_commander.tools import (
    get_dependencies,
    get_deployments,
    get_error_rate,
    get_latency,
    get_logs,
)
from incident_commander.types import Observation
from incident_commander.world import SimWorld

A1 = ALERTS["ALRT-9001"]
WINDOW = (A1.fired_at - LOOKBACK_S, A1.fired_at)
WINDOW_TOOLS = (get_latency, get_error_rate, get_deployments, get_logs)


def fresh_clock() -> DataClock:
    return DataClock(A1.fired_at + 5.0)


class TestToolSurface(unittest.TestCase):
    def test_exactly_five_tools_with_specs(self):
        self.assertEqual(
            set(TOOL_SPECS),
            {"get_latency", "get_error_rate", "get_deployments", "get_dependencies", "get_logs"},
        )
        self.assertEqual(sorted(tools.__all__), sorted([*TOOL_SPECS, "TOOL_SPECS"]))

    def test_signatures_take_service_and_time_never_an_incident(self):
        for name in TOOL_SPECS:
            params = list(inspect.signature(getattr(tools, name)).parameters)
            self.assertEqual(params[:3], ["world", "clock", "service"], name)
            for p in params:
                self.assertNotIn("alert", p)
                self.assertNotIn("incident", p)
        self.assertEqual(
            list(inspect.signature(get_dependencies).parameters)[3:], ["at"], "dependencies"
        )

    def test_logs_are_the_only_non_evidence_tool(self):
        self.assertEqual([n for n, s in TOOL_SPECS.items() if not s.evidence], ["get_logs"])


class TestObservations(unittest.TestCase):
    def setUp(self):
        self.world = SimWorld()

    def observe_all(self, world=None, clock=None):
        world = world or self.world
        clock = clock or fresh_clock()
        s, e = WINDOW
        return [
            get_latency(world, clock, A1.service, s, e),
            get_error_rate(world, clock, A1.service, s, e),
            get_deployments(world, clock, A1.service, s, e),
            get_dependencies(world, clock, A1.service, e),
            get_logs(world, clock, A1.service, s, e),
        ]

    def test_typed_and_declare_freshness(self):
        for obs in self.observe_all():
            self.assertIsInstance(obs, Observation)
            self.assertEqual(obs.status, "ok")
            self.assertEqual(obs.max_staleness_s, TOOL_SPECS[obs.tool].max_staleness_s)
            self.assertEqual(obs.age_s, TOOL_SPECS[obs.tool].lag_s)
            self.assertTrue(obs.fresh)
            self.assertIsInstance(obs.data, tuple)

    def test_read_only_two_calls_equal_and_world_unchanged(self):
        before = self.world.snapshot(*WINDOW)
        first = [(o.tool, o.data, o.baseline) for o in self.observe_all()]
        second = [(o.tool, o.data, o.baseline) for o in self.observe_all()]
        self.assertEqual(first, second)
        self.assertEqual(before, self.world.snapshot(*WINDOW))

    def test_every_call_advances_the_data_clock(self):
        clock = fresh_clock()
        start = clock.now()
        self.observe_all(clock=clock)
        self.assertEqual(clock.now(), start + 5 * 2.0)

    def test_nothing_after_as_of_is_returned(self):
        clock = fresh_clock()
        obs = get_latency(self.world, clock, A1.service, A1.fired_at, A1.fired_at + 3600)
        self.assertTrue(all(t <= obs.as_of for t, _ in obs.data))
        self.assertLess(obs.data[-1][0], A1.fired_at + 60)

    def test_known_values_for_alrt_9001(self):
        lat, err, dep, deps, logs = self.observe_all()
        self.assertEqual(lat.baseline, 180.0)
        self.assertEqual(lat.data[-1][1], 1440.0)
        self.assertEqual(err.baseline, 0.010)
        self.assertEqual(dep.data, ((A1.fired_at - 720, "v2.14.0"),))
        self.assertEqual({d for d, _, _ in deps.data}, {"payment-service", "inventory-service"})
        for _, lat_ratio, err_ratio in deps.data:
            self.assertEqual((lat_ratio, err_ratio), (1.0, 1.0))
        self.assertEqual(len(logs.data), 24)


class TestFreshnessBoundary(unittest.TestCase):
    """age_s / fresh flip exactly at max_staleness_s."""

    def test_flips_exactly_at_the_budget(self):
        for name, spec in TOOL_SPECS.items():
            at_budget = SimWorld(tool_lags={name: float(spec.max_staleness_s)})
            over = SimWorld(tool_lags={name: spec.max_staleness_s + 1.0})
            self.assertTrue(self._call(name, at_budget).fresh, f"{name} at budget")
            obs = self._call(name, over)
            self.assertFalse(obs.fresh, f"{name} over budget")
            self.assertEqual(obs.age_s, spec.max_staleness_s + 1.0)
            self.assertEqual(obs.status, "ok")  # stale data is still returned, just flagged

    @staticmethod
    def _call(name, world):
        fn = getattr(tools, name)
        if name == "get_dependencies":
            return fn(world, fresh_clock(), A1.service, A1.fired_at)
        return fn(world, fresh_clock(), A1.service, *WINDOW)


class TestErrorsAreContained(unittest.TestCase):
    def test_unknown_service_gives_status_error(self):
        world = SimWorld()
        for fn in WINDOW_TOOLS:
            obs = fn(world, fresh_clock(), "no-such-service", *WINDOW)
            self.assertEqual(obs.status, "error", fn.__name__)
            self.assertFalse(obs.fresh)
            self.assertEqual(obs.data, ())
            self.assertIn("KeyError", obs.error)
        obs = get_dependencies(world, fresh_clock(), "no-such-service", A1.fired_at)
        self.assertEqual(obs.status, "error")

    def test_a_raising_world_query_gives_status_error(self):
        class Broken(SimWorld):
            def error_points(self, *args, **kwargs):
                raise RuntimeError("metrics backend down")

        obs = get_error_rate(Broken(), fresh_clock(), A1.service, *WINDOW)
        self.assertEqual(obs.status, "error")
        self.assertEqual(obs.error, "RuntimeError: metrics backend down")
        # the clock still advanced: a failed call costs time like any other
        clock = fresh_clock()
        get_error_rate(Broken(), clock, A1.service, *WINDOW)
        self.assertEqual(clock.now(), A1.fired_at + 7.0)


if __name__ == "__main__":
    unittest.main()
