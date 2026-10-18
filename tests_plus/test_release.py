"""v2.0 release gates X1-X4 in one place, against the saved graded trace and the frozen v1.0 tag."""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEAD_URL = "http://127.0.0.1:9/v1"
FALLBACK = "llm: unavailable, deterministic fallback"


def run(*args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def decisions(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("DECISION ")]


def v1_tag_exists() -> bool:
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "v1.0^{commit}"],
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return probe.returncode == 0


class TestReleaseGates(unittest.TestCase):
    @unittest.skipUnless(v1_tag_exists(), "tag v1.0 is not available (shallow clone)")
    def test_x1_graded_package_is_unchanged_since_v1_0(self):
        diff = subprocess.run(
            ["git", "diff", "--stat", "v1.0", "--", "incident_commander/"],
            check=False,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(diff.returncode, 0, diff.stderr)
        self.assertEqual(diff.stdout.strip(), "")

    def test_x2_llm_down_keeps_the_saved_graded_decisions(self):
        saved = decisions((ROOT / "traces" / "run.txt").read_text(encoding="utf-8"))
        self.assertGreater(len(saved), 20)
        down = run("-m", "ic_plus", "run", "--all", "--llm", "local", "--llm-url", DEAD_URL)
        self.assertEqual(down.returncode, 0, down.stderr)
        self.assertEqual(decisions(down.stdout), saved)
        self.assertIn(FALLBACK, down.stdout)

    def test_x3_evaluate_with_llm_down_changes_no_decision(self):
        out = run("-m", "ic_plus", "evaluate", "--llm", "local", "--llm-url", DEAD_URL)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("decisions_changed=0", out.stdout)

    def test_x4_guard_suite_passes(self):
        out = run("-m", "unittest", "tests_plus.test_llm_guard")
        self.assertEqual(out.returncode, 0, out.stderr)


if __name__ == "__main__":
    unittest.main()
