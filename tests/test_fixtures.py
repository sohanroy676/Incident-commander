"""Fixture sanity (AC-04): keyed by service + timestamp, cause before effect, honest baselines."""

import itertools
import statistics
import unittest

from incident_commander.config import LOOKBACK_S, SAMPLE_INTERVAL_S
from incident_commander.fixtures.alerts import ALERTS
from incident_commander.fixtures.services import SERVICES
from incident_commander.world import SimWorld

A1, A2, A3 = (ALERTS[i] for i in ("ALRT-9001", "ALRT-9002", "ALRT-9003"))


class TestKeying(unittest.TestCase):
    def test_incident_ids_exist_only_in_the_alert_table(self):
        ids = set(ALERTS)
        self.assertEqual(ids, {"ALRT-9001", "ALRT-9002", "ALRT-9003"})
        for name in SERVICES:
            self.assertNotIn(name, ids)
            for _, text in SimWorld().logs(name, 0, 1e12, 1e12):
                self.assertFalse(any(i in text for i in ids), name)

    def test_every_alert_points_at_a_known_service(self):
        for a in ALERTS.values():
            self.assertIn(a.service, SERVICES)

    def test_alerts_sit_on_the_sampling_grid(self):
        for a in ALERTS.values():
            self.assertEqual(a.fired_at % SAMPLE_INTERVAL_S, 0)

    def test_series_are_sampled_every_60s_with_real_timestamps(self):
        pts = SimWorld().latency_points(A1.service, A1.fired_at - LOOKBACK_S, A1.fired_at, 1e12)
        self.assertEqual(len(pts), LOOKBACK_S // SAMPLE_INTERVAL_S + 1)
        self.assertEqual({b - a for (a, _), (b, _) in itertools.pairwise(pts)}, {60.0})

    def test_generators_are_deterministic(self):
        w1, w2 = SimWorld(), SimWorld()
        window = (A2.fired_at - LOOKBACK_S, A2.fired_at)
        self.assertEqual(w1.snapshot(*window), w2.snapshot(*window))


class TestCauseBeforeEffect(unittest.TestCase):
    def test_alrt_9001_latency_step_starts_after_the_deploy(self):
        world = SimWorld()
        ((deployed_at, _),) = world.deployments(A1.service, 0, A1.fired_at, A1.fired_at)
        pts = world.latency_points(A1.service, A1.fired_at - LOOKBACK_S, A1.fired_at, A1.fired_at)
        base = SERVICES[A1.service].baseline_latency_ms
        step_at = next(t for t, v in pts if v > base)
        self.assertGreater(step_at, deployed_at)
        self.assertEqual(deployed_at, A1.fired_at - 720)
        self.assertEqual(step_at, A1.fired_at - 660)  # ~11 min before the alert
        self.assertEqual(max(v for _, v in pts) / base, 8.0)

    def test_alrt_9002_last_deploy_is_in_lookback_but_outside_the_window(self):
        world = SimWorld()
        ((deployed_at, _),) = world.deployments(
            A2.service, A2.fired_at - LOOKBACK_S, A2.fired_at, 1e12
        )
        age = A2.fired_at - deployed_at
        self.assertEqual(age, 18000)
        self.assertLess(age, LOOKBACK_S)
        self.assertGreater(age, 1800)

    def test_alrt_9002_climbs_gradually_to_6x(self):
        world = SimWorld()
        pts = world.latency_points(A2.service, A2.fired_at - LOOKBACK_S, A2.fired_at, 1e12)
        values = [v for _, v in pts]
        self.assertEqual(values[0], 180.0)
        self.assertEqual(values[-1], 1080.0)
        jumps = [b - a for a, b in itertools.pairwise(values)]
        self.assertLess(max(jumps), 0.5 * values[-1])  # no single step
        self.assertTrue(all(j >= 0 for j in jumps))

    def test_alrt_9003_has_errors_up_latency_flat_and_no_deploy(self):
        world = SimWorld()
        s, e = A3.fired_at - LOOKBACK_S, A3.fired_at
        err = world.error_points(A3.service, s, e, e)
        lat = world.latency_points(A3.service, s, e, e)
        base_err = SERVICES[A3.service].baseline_error_rate
        self.assertAlmostEqual(err[-1][1] / base_err, 5.0)
        self.assertLessEqual(max(v for _, v in lat) / 180.0, 1.25)
        self.assertEqual(world.deployments(A3.service, s, e, e), ())


class TestBaselines(unittest.TestCase):
    def test_declared_latency_baseline_is_the_quiet_period_median(self):
        world = SimWorld()
        # services with a distinct quiet period; ramp and flat-offset services are checked below
        for alert in (A1,):
            svc = SERVICES[alert.service]
            pts = world.latency_points(svc.name, alert.fired_at - LOOKBACK_S, alert.fired_at, 1e12)
            quiet = [v for t, v in pts if t < svc.quiet_until]
            self.assertGreater(len(quiet), 100)
            self.assertEqual(statistics.median(quiet), svc.baseline_latency_ms)

    def test_ramp_starts_at_baseline(self):
        pts = SimWorld().latency_points(A2.service, A2.fired_at - LOOKBACK_S, A2.fired_at, 1e12)
        self.assertEqual(pts[0][1], SERVICES[A2.service].baseline_latency_ms)

    def test_healthy_series_stay_within_the_normal_band(self):
        # PHASE5 8 gives "approximately" values for some quiet series; they must stay normal.
        world = SimWorld()
        for name, svc in SERVICES.items():
            for t, v in world.latency_points(name, svc.anchor - LOOKBACK_S, svc.anchor, 1e12):
                if t < svc.quiet_until:
                    self.assertLessEqual(v / svc.baseline_latency_ms, 1.25, name)
            for _, v in world.error_points(name, svc.anchor - 3600, svc.anchor - 1300, 1e12):
                self.assertLessEqual(v / svc.baseline_error_rate, 2.0, name)

    def test_dependency_services_are_healthy_for_the_alert_that_names_them(self):
        world = SimWorld()
        for alert in (A1, A3):
            for dep, lat, err in world.dependency_ratios(alert.service, alert.fired_at, 1e12):
                self.assertEqual((lat, err), (1.0, 1.0), dep)


class TestLogs(unittest.TestCase):
    def test_each_service_has_20_to_30_plain_lines(self):
        world = SimWorld()
        for name, svc in SERVICES.items():
            lines = world.logs(name, svc.anchor - LOOKBACK_S, svc.anchor, 1e12)
            self.assertTrue(20 <= len(lines) <= 30, name)
            for _, text in lines:
                self.assertTrue(text.startswith(("[INFO]", "[WARN]")), text)


if __name__ == "__main__":
    unittest.main()
