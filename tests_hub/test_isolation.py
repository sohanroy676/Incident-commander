"""Dependency direction: the hub imports the graded packages, never the other way round."""

import ast
import re
import subprocess
import sys
import unittest

from .support import ROOT


def python_files(package: str):
    return sorted((ROOT / package).rglob("*.py"))


class TestIsolation(unittest.TestCase):
    def test_graded_and_extension_packages_never_mention_the_hub(self) -> None:
        for package in ("incident_commander", "ic_plus"):
            for path in python_files(package):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(re.search(r"\bic_hub\b", text), f"{path} mentions ic_hub")

    def test_hub_imports_only_stdlib_and_the_project(self) -> None:
        allowed = set(sys.stdlib_module_names) | {"incident_commander", "ic_plus", "ic_hub"}
        for path in python_files("ic_hub"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    roots = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    roots = [(node.module or "").split(".")[0]]
                else:
                    continue
                for root in roots:
                    self.assertIn(root, allowed, f"{path.name} imports {root}")

    def test_hub_reads_no_environment_and_keys(self) -> None:
        for path in python_files("ic_hub"):
            text = path.read_text(encoding="utf-8")
            for needle in ("os.environ", "getenv", ".env", "load_env", "api_key", "LLM_API_KEY"):
                self.assertNotIn(needle, text, f"{path.name} touches {needle}")

    def test_purity_gate_still_passes(self) -> None:
        done = subprocess.run(
            [sys.executable, "-m", "incident_commander.dod", "purity"],
            check=False,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_graded_package_is_unchanged_since_v1_0(self) -> None:
        probe = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", "v1.0^{commit}"],
            check=False,
            cwd=ROOT,
            capture_output=True,
        )
        if probe.returncode != 0:
            self.skipTest("tag v1.0 is not available (shallow clone)")
        diff = subprocess.run(
            ["git", "diff", "v1.0", "--", "incident_commander/"],
            check=False,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(diff.stdout, "")


if __name__ == "__main__":
    unittest.main()
