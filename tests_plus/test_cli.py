"""ic_plus entry point: baseline parity (X1/X2 off), flags, the cli approver over a real pipe,
and the extension's own purity (stdlib + incident_commander only, no environment, no network)."""

import ast
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANNER = "extension: llm=off approver=scripted"
FORBIDDEN_IMPORTS = {"socket", "urllib", "http", "requests", "ssl"}


def run(module: str, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        check=False,
        cwd=ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
    )


def decisions(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("DECISION ")]


class TestBaselineParity(unittest.TestCase):
    def test_run_all_llm_off_has_the_graded_decision_lines(self):
        graded = run("incident_commander", "run", "--all")
        plus = run("ic_plus", "run", "--all", "--llm", "off")
        self.assertEqual(graded.returncode, 0, graded.stderr)
        self.assertEqual(plus.returncode, 0, plus.stderr)
        self.assertGreater(len(decisions(graded.stdout)), 20)
        self.assertEqual(decisions(plus.stdout), decisions(graded.stdout))
        self.assertEqual(plus.stdout.splitlines()[-1], BANNER)

    def test_llm_off_is_the_default(self):
        plus = run("ic_plus", "run", "ALRT-9003")
        self.assertEqual(plus.returncode, 0, plus.stderr)
        self.assertEqual(plus.stdout.splitlines()[-1], BANNER)


class TestFlags(unittest.TestCase):
    def test_llm_is_accepted_before_or_after_the_subcommand(self):
        for argv in (
            ("scenario", "unknown_action", "--llm", "hosted"),
            ("--llm", "local", "scenario", "unknown_action"),
        ):
            with self.subTest(argv=argv):
                self.assertEqual(run("ic_plus", *argv).returncode, 0)
        before = run("ic_plus", "--llm", "off", "scenario", "unknown_action")
        after = run("ic_plus", "scenario", "unknown_action", "--llm", "off")
        self.assertEqual((before.returncode, after.returncode), (0, 0))

    def test_llm_url_and_model_are_accepted_in_either_position(self):
        for argv in (
            ("--llm-url", "http://x/v1", "--model", "m", "scenario", "unknown_action"),
            ("scenario", "unknown_action", "--llm-url", "http://x/v1", "--model", "m"),
        ):
            with self.subTest(argv=argv):
                self.assertEqual(run("ic_plus", *argv).returncode, 0)

    def test_an_unknown_llm_mode_is_a_usage_error(self):
        self.assertEqual(run("ic_plus", "--llm", "bogus", "run", "--all").returncode, 2)

    def test_run_needs_exactly_one_of_alert_or_all(self):
        self.assertEqual(run("ic_plus", "run").returncode, 2)
        self.assertEqual(run("ic_plus", "run", "ALRT-9001", "--all").returncode, 2)

    def test_deadline_needs_the_cli_approver_and_a_positive_value(self):
        self.assertEqual(run("ic_plus", "run", "ALRT-9001", "--deadline", "5").returncode, 2)
        for bad in ("0", "-1"):
            p = run("ic_plus", "run", "ALRT-9001", "--approver", "cli", "--deadline", bad)
            self.assertEqual(p.returncode, 2, bad)

    def test_the_cli_approver_takes_one_alert(self):
        self.assertEqual(run("ic_plus", "run", "--all", "--approver", "cli").returncode, 2)

    def test_unknown_alert_with_the_cli_approver_is_exit_2(self):
        p = run("ic_plus", "run", "ALRT-0000", "--approver", "cli")
        self.assertEqual(p.returncode, 2)
        self.assertIn("unknown alert", p.stderr)


class TestCliApproverEndToEnd(unittest.TestCase):
    def test_typed_approve_is_the_primary_and_executes(self):
        p = run("ic_plus", "run", "ALRT-9001", "--approver", "cli", stdin="approve\n")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(
            "DECISION approval alert=ALRT-9001 escalated=False approved_by=engineer-priya", p.stdout
        )
        self.assertIn(
            "DECISION execute alert=ALRT-9001 action=rollback_deployment status=executed", p.stdout
        )
        self.assertEqual(p.stdout.splitlines()[-1], "extension: llm=off approver=cli")

    def test_closed_stdin_means_no_approval_and_no_execution(self):
        p = run("ic_plus", "run", "ALRT-9001", "--approver", "cli", "--deadline", "0.2", stdin="")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("escalated=True approved_by=none", p.stdout)
        self.assertIn("DECISION handoff alert=ALRT-9001 reason=approval_expired", p.stdout)
        self.assertNotIn("DECISION execute", p.stdout)

    def test_deny_hands_off_without_executing(self):
        p = run("ic_plus", "run", "ALRT-9001", "--approver", "cli", stdin="deny\n")
        self.assertIn("reason=approval_denied", p.stdout)
        self.assertNotIn("DECISION execute", p.stdout)


class TestExtensionPurity(unittest.TestCase):
    def sources(self):
        return sorted((ROOT / "ic_plus").rglob("*.py"))

    def test_imports_are_stdlib_or_the_graded_package_only(self):
        allowed = set(sys.stdlib_module_names) | {"incident_commander", "ic_plus"}
        for path in self.sources():
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    roots = {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    roots = {(node.module or "").split(".")[0]}
                else:
                    continue
                self.assertLessEqual(roots, allowed, path.name)
                if path.name != "llm_client.py":
                    self.assertFalse(roots & FORBIDDEN_IMPORTS, f"{path.name}: network import")
                else:
                    self.assertFalse(
                        roots & {"socket", "requests", "ssl"}, "llm_client: stdlib urllib only"
                    )

    def test_no_process_environment_access(self):
        for path in self.sources():
            text = path.read_text(encoding="utf-8")
            for needle in ("environ", "getenv"):
                self.assertNotIn(needle, text, f"{path.name}: {needle}")

    def test_only_envfile_reads_dotenv(self):
        for path in self.sources():
            if path.name == "envfile.py":
                continue
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r"\.env(?!file)", text), path.name
            )  # .envfile is the module


if __name__ == "__main__":
    unittest.main()
