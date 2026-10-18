"""Gate canaries (PHASE5 11.6): plant one defect in a temporary copy and watch the right gate trip.

A gate that cannot fail proves nothing. Each canary copies the package and its tests to a temp
directory, applies exactly one sabotage, and runs the gate the way `dod all` does. The real
sources are never touched.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACKAGE = REPO / "incident_commander"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


class Sandbox:
    """A throwaway copy of the package and the tests, with one sabotage applied."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        shutil.copytree(PACKAGE, self.root / "incident_commander", ignore=IGNORE)
        shutil.copytree(REPO / "tests", self.root / "tests", ignore=IGNORE)

    def sabotage(self, relative: str, old: str, new: str) -> None:
        path = self.root / "incident_commander" / relative
        text = path.read_text(encoding="utf-8")
        assert text.count(old) == 1, f"{relative}: sabotage target must occur exactly once"
        path.write_text(text.replace(old, new), encoding="utf-8")

    def append(self, relative: str, extra: str) -> None:
        path = self.root / "incident_commander" / relative
        path.write_text(path.read_text(encoding="utf-8") + extra, encoding="utf-8")

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def gate(self, module: str) -> subprocess.CompletedProcess[str]:
        return self.run("-m", "unittest", module)

    def close(self) -> None:
        self._tmp.cleanup()


class CanaryCase(unittest.TestCase):
    def sandbox(self) -> Sandbox:
        box = Sandbox()
        self.addCleanup(box.close)
        return box

    def assertTrips(self, proc: subprocess.CompletedProcess[str], marker: str) -> None:
        output = proc.stdout + proc.stderr
        self.assertNotEqual(proc.returncode, 0, f"gate passed despite the sabotage:\n{output}")
        self.assertIn(marker, output)


class TestControl(CanaryCase):
    def test_an_unsabotaged_copy_passes_the_structural_and_purity_gates(self):
        box = self.sandbox()
        self.assertEqual(box.gate("tests.test_invariants").returncode, 0)
        purity = box.run("-m", "incident_commander.dod", "purity")
        self.assertEqual(purity.returncode, 0, purity.stdout)


class TestG1Canary(CanaryCase):
    def test_a_third_party_import_trips_purity(self):
        box = self.sandbox()
        box.append("tools.py", "\nimport requests\n")
        proc = box.run("-m", "incident_commander.dod", "purity")
        self.assertTrips(proc, "forbidden import: requests")

    def test_reading_the_environment_trips_purity(self):
        box = self.sandbox()
        box.append("config.py", "\nimport os\nKEY = os.environ.get('K')\n")
        self.assertTrips(box.run("-m", "incident_commander.dod", "purity"), "environment access")


class TestG2Canaries(CanaryCase):
    def test_a_severity_parameter_on_the_classifier_trips_the_blast_radius_checks(self):
        box = self.sandbox()
        box.sabotage(
            "blast_radius.py",
            "def classify_remediation(action: str)",
            'def classify_remediation(action: str, severity: str = "low")',
        )
        self.assertTrips(box.gate("tests.test_invariants"), "TestBlastRadius")

    def test_an_incident_id_in_a_fixture_trips_the_fixture_checks(self):
        box = self.sandbox()
        box.sabotage("fixtures/services.py", '"v2.14.0"', '"ALRT-9001"')
        self.assertTrips(box.gate("tests.test_invariants"), "TestFixtures")

    def test_a_free_text_parameter_in_a_predicate_trips_the_no_text_checks(self):
        box = self.sandbox()
        box.sabotage(
            "predicates.py",
            "def dependency_unhealthy(data, baseline, fired_at) -> Tri:",
            'def dependency_unhealthy(data, baseline, fired_at, log_text="") -> Tri:',
        )
        self.assertTrips(box.gate("tests.test_invariants"), "TestNoTextInDecisions")

    def test_a_notifier_reachable_from_build_draft_trips_the_postmortem_checks(self):
        box = self.sandbox()
        box.sabotage(
            "postmortem.py",
            "logs: Observation | None, runbook: Runbook | None\n) -> PostmortemDraft:",
            "logs: Observation | None, runbook: Runbook | None, notifier=None\n) -> PostmortemDraft:",
        )
        self.assertTrips(box.gate("tests.test_invariants"), "TestPostmortem")


class TestG3Canaries(CanaryCase):
    def test_a_no_op_sleep_trips_the_real_clock_outcome(self):
        box = self.sandbox()
        box.sabotage(
            "clocks.py",
            "        target = time.monotonic() + seconds\n",
            "        return\n        target = time.monotonic() + seconds\n",
        )
        self.assertTrips(box.gate("tests.test_outcomes"), "TestOutcome3")

    def test_a_verifier_that_always_resolves_trips_the_verified_resolution_outcome(self):
        box = self.sandbox()
        box.sabotage("verifier.py", "if observed <= obs.baseline * tolerance:", "if True:")
        self.assertTrips(box.gate("tests.test_outcomes"), "TestOutcome4")


if __name__ == "__main__":
    unittest.main()
