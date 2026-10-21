"""v3.3 predicates (ADR-0006): error shapes and dependency_healthy, plus the guarantee that the
built-in runbooks do not use them, so no built-in decision can depend on them."""

import unittest

from incident_commander.fixtures.runbooks import RUNBOOKS
from incident_commander.predicates import PREDICATES
from tests.test_predicates import BASE_ERR, F, T, U, check, series

NEW = ("error_step_change", "error_gradual_trend", "dependency_healthy")


def err_step(at_index=300, low=BASE_ERR, high=0.05):
    return series(lambda i, n: high if i >= at_index else low)


def err_ramp(low=BASE_ERR, high=0.06):
    return series(lambda i, n: low + (high - low) * i / (n - 1))


class TestRegistry(unittest.TestCase):
    def test_new_predicates_are_registered_on_the_right_tools(self):
        self.assertEqual(PREDICATES["error_step_change"].tool, "get_error_rate")
        self.assertEqual(PREDICATES["error_gradual_trend"].tool, "get_error_rate")
        self.assertEqual(PREDICATES["dependency_healthy"].tool, "get_dependencies")

    def test_no_builtin_runbook_uses_them(self):
        used = {p for rb in RUNBOOKS.values() for p in rb.signature}
        self.assertFalse(used & set(NEW))


class TestErrorShapes(unittest.TestCase):
    def check(self, pred, data, baseline=BASE_ERR):
        return check(pred, data, baseline)

    def test_step_after_quiet_is_true(self):
        self.assertEqual(self.check("error_step_change", err_step()), T)

    def test_step_is_not_a_trend(self):
        self.assertEqual(self.check("error_gradual_trend", err_step()), F)

    def test_ramp_is_a_trend_and_not_a_step(self):
        self.assertEqual(self.check("error_gradual_trend", err_ramp()), T)
        self.assertEqual(self.check("error_step_change", err_ramp()), F)

    def test_flat_is_neither(self):
        flat = series(lambda i, n: BASE_ERR)
        self.assertEqual(self.check("error_step_change", flat), F)
        self.assertEqual(self.check("error_gradual_trend", flat), F)

    def test_step_from_an_already_elevated_level_is_false(self):
        # quiet means within the error-normal ratio of baseline; a noisy prefix is not a clean step
        noisy = series(lambda i, n: 0.06 if i >= 300 else (0.025 if i >= 50 else BASE_ERR))
        self.assertEqual(self.check("error_step_change", noisy), F)

    def test_downward_step_is_not_a_step_change(self):
        down = series(lambda i, n: BASE_ERR if i >= 300 else 0.05)
        self.assertEqual(self.check("error_step_change", down), F)

    def test_too_little_data_or_no_baseline_is_unknown(self):
        self.assertEqual(self.check("error_step_change", ()), U)
        self.assertEqual(self.check("error_step_change", err_step(), baseline=None), U)
        self.assertEqual(self.check("error_step_change", err_step(), baseline=0), U)
        self.assertEqual(self.check("error_gradual_trend", err_ramp()[:2]), U)


class TestDependencyHealthy(unittest.TestCase):
    def test_complement_of_unhealthy_on_every_threshold_edge(self):
        for lat, err in ((2.0, 1.0), (1.0, 3.0), (1.99, 2.99), (1.0, 1.0), (9.0, 9.0)):
            data = (("a", lat, err),)
            unhealthy = check("dependency_unhealthy", data)
            healthy = check("dependency_healthy", data)
            self.assertNotEqual(unhealthy, healthy, (lat, err))
            self.assertIn(healthy, (T, F))

    def test_one_bad_dependency_makes_it_false(self):
        data = (("a", 1.0, 1.0), ("b", 5.1, 4.0))
        self.assertEqual(check("dependency_healthy", data), F)

    def test_no_dependencies_is_true(self):
        self.assertEqual(check("dependency_healthy", ()), T)


if __name__ == "__main__":
    unittest.main()
