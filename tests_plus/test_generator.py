"""Seeded scenario generator (item 39): determinism, coverage, severity independence, reporting."""

import contextlib
import dataclasses
import io
import random
import unittest

from ic_plus.__main__ import main
from ic_plus.generator import (
    CLASSES,
    NONE,
    GeneratedResult,
    build_scenario,
    confusion,
    format_report,
    generate,
    run_scenario,
)
from incident_commander.fixtures.alerts import ALERTS
from incident_commander.fixtures.golden import GOLDEN_ALERTS


def _sample(s):
    """Parameters that make a world: alert plus each service's sampled signal."""
    out = [s.label, s.alert]
    for name, spec in sorted(s.services.items()):
        t = s.alert.fired_at - 100.0
        out.append((name, spec.latency(t), spec.error_rate(t), spec.deployments))
    return out


class TestGeneration(unittest.TestCase):
    def test_same_seed_same_worlds(self):
        self.assertEqual(
            [_sample(s) for s in generate(7, 10)], [_sample(s) for s in generate(7, 10)]
        )

    def test_different_seeds_differ(self):
        self.assertNotEqual(
            [_sample(s) for s in generate(1, 5)], [_sample(s) for s in generate(2, 5)]
        )

    def test_every_class_appears_and_expected_matches_the_table(self):
        scenarios = generate(0, 5)
        self.assertEqual({s.label for s in scenarios}, set(CLASSES))
        for s in scenarios:
            self.assertEqual(s.expected, CLASSES[s.label])

    def test_alert_ids_and_services_never_collide_with_fixtures(self):
        scenarios = generate(0, 50)
        ids = [s.alert.alert_id for s in scenarios]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertFalse(set(ids) & (set(ALERTS) | set(GOLDEN_ALERTS)))
        times = [s.alert.fired_at for s in scenarios]
        self.assertEqual(len(set(times)), len(times))

    def test_unknown_class_is_rejected(self):
        with self.assertRaises(ValueError):
            build_scenario(random.Random(0), 0, "cosmic_rays")

    def test_zero_scenarios_is_empty(self):
        self.assertEqual(generate(0, 0), [])


class TestPipelineOnGenerated(unittest.TestCase):
    def test_pipeline_agrees_with_the_label_over_several_seeds(self):
        results = [run_scenario(s) for seed in (0, 1, 2) for s in generate(seed, 10)]
        bad = [(r.scenario.label, r.predicted) for r in results if not r.ok]
        self.assertEqual(bad, [])
        counts = confusion(results)
        self.assertTrue(all(exp == pred for (exp, pred), n in counts.items() if n))

    def test_severity_never_changes_the_decision(self):
        for s in generate(4, 5):
            predicted = {
                run_scenario(
                    dataclasses.replace(s, alert=dataclasses.replace(s.alert, severity=sev))
                ).predicted
                for sev in ("low", "medium", "high", "critical")
            }
            self.assertEqual(predicted, {s.expected}, s.label)

    def test_no_fault_hands_off_without_a_runbook(self):
        s = next(x for x in generate(0, 5) if x.label == "no_fault")
        self.assertEqual(run_scenario(s).predicted, NONE)


class TestReport(unittest.TestCase):
    def test_report_flags_a_mismatch_and_counts_it(self):
        s = generate(0, 1)[0]
        wrong = GeneratedResult(s, "RB-104")
        lines = format_report(0, [wrong])
        self.assertIn("agree=0/1", lines)
        self.assertTrue(
            any(line.startswith("mismatch ") and "predicted=RB-104" in line for line in lines)
        )
        self.assertIn("not real-world accuracy", lines[0])

    def test_cli_prints_matrix_and_exits_zero(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["generate", "--seed", "1", "--count", "5"])
        self.assertEqual(code, 0)
        self.assertIn("agree=5/5", out.getvalue())

    def test_cli_rejects_bad_counts(self):
        for count in ("0", "-3", "201"):
            with (
                self.subTest(count=count),
                self.assertRaises(SystemExit) as ctx,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                main(["generate", "--count", count])
            self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
