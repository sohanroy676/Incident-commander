"""G1 purity gate (AC-01), G5 trace checker (AC-14) and G6 repro (AC-15)."""

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import incident_commander
from incident_commander import dod

PKG = Path(incident_commander.__file__).resolve().parent


class TestPurity(unittest.TestCase):
    def scan_with(self, extra_source: str):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "incident_commander"
            shutil.copytree(PKG, copy, ignore=shutil.ignore_patterns("__pycache__"))
            (copy / "planted.py").write_text(extra_source, encoding="utf-8")
            return dod.scan(copy)[1]

    def test_real_package_passes(self):
        scanned, violations = dod.scan(PKG)
        self.assertEqual(violations, [])
        self.assertGreaterEqual(scanned, 10)

    def test_cli_prints_pass_and_returns_zero(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = dod.main(["purity"])
        self.assertEqual(rc, 0)
        self.assertIn("G1 purity: PASS", buf.getvalue())

    def test_third_party_import_fails(self):
        v = self.scan_with("import requests\n")
        self.assertEqual([x.message for x in v], ["forbidden import: requests"])

    def test_unlisted_third_party_import_fails(self):
        v = self.scan_with("import yaml\n")
        self.assertEqual(len(v), 1)
        self.assertIn("outside stdlib", v[0].message)

    def test_direct_numpy_and_network_modules_fail(self):
        for mod in ("numpy", "socket", "urllib.request", "http.client"):
            with self.subTest(mod=mod):
                self.assertEqual(len(self.scan_with(f"import {mod}\n")), 1)

    def test_from_import_of_forbidden_module_fails(self):
        self.assertEqual(len(self.scan_with("from urllib import request\n")), 1)

    def test_importing_ic_plus_fails(self):
        for src in ("import ic_plus\n", "from ic_plus import guard\n", "x = ic_plus.thing\n"):
            with self.subTest(src=src):
                self.assertTrue(self.scan_with(src), src)

    def test_environment_access_fails(self):
        for src in (
            "import os\nx = os.environ['K']\n",
            "import os\nx = os.getenv('K')\n",
            "from os import environ\n",
            "from os import getenv\n",
        ):
            with self.subTest(src=src):
                self.assertTrue(self.scan_with(src), src)

    def test_stdlib_sklearn_and_relative_imports_pass(self):
        src = "import json\nfrom sklearn.feature_extraction.text import TfidfVectorizer\nfrom . import types\n"
        self.assertEqual(self.scan_with(src), [])

    def test_cli_fails_with_nonzero_exit_on_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "bad.py").write_text("import requests\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = dod.main(["purity", "--root", tmp])
        self.assertEqual(rc, 1)
        self.assertIn("G1 purity: FAIL", buf.getvalue())


EXECUTE = "DECISION execute alert=ALRT-9002 action=restart_service status={} execution_id={}"
EXTRA = (
    (
        "DECISION attack alert=ALRT-9001 verdict=matched runbook=RB-101"
        " action=rollback_deployment unchanged=True"
    ),
    "DECISION postmortem alert=ALRT-9001 notified=[] published=False",
    EXECUTE.format("executed", "exec-aaa"),
    EXECUTE.format("already_executed", "exec-aaa"),
)


def good_trace() -> str:
    lines = [*dod.HEADERS, *dod.REQUIRED_LINES, *EXTRA]
    return "\n".join(lines) + "\n"


class TestTraceGate(unittest.TestCase):
    def test_good_trace_has_no_problems(self):
        self.assertEqual(dod.check_trace(good_trace()), [])

    def test_missing_header_is_rejected(self):
        text = good_trace().replace("== M4 BLAST-RADIUS CLASSIFICATION ==\n", "")
        self.assertTrue(any("M4" in p for p in dod.check_trace(text)))

    def test_duplicate_and_reordered_headers_are_rejected(self):
        dup = good_trace() + dod.HEADERS[0] + "\n"
        self.assertTrue(any("M1" in p for p in dod.check_trace(dup)))
        swapped = list(dod.HEADERS)
        swapped[0], swapped[1] = swapped[1], swapped[0]
        text = "\n".join([*swapped, *dod.REQUIRED_LINES, *EXTRA]) + "\n"
        self.assertTrue(any("out of order" in p for p in dod.check_trace(text)))

    def test_each_missing_or_altered_decision_line_is_rejected(self):
        for line in dod.REQUIRED_LINES:
            with self.subTest(line=line):
                missing = good_trace().replace(line + "\n", "")
                self.assertTrue(dod.check_trace(missing))
                altered = good_trace().replace(line, line + "0")
                self.assertTrue(dod.check_trace(altered))

    def test_attack_changed_or_published_postmortem_is_rejected(self):
        text = good_trace().replace("unchanged=True", "unchanged=False")
        self.assertTrue(any("attack" in p for p in dod.check_trace(text)))
        text = good_trace().replace("published=False", "published=True")
        self.assertTrue(any("postmortem" in p for p in dod.check_trace(text)))

    def test_retry_must_reuse_the_execution_id(self):
        text = good_trace().replace(
            EXECUTE.format("already_executed", "exec-aaa"),
            EXECUTE.format("already_executed", "exec-bbb"),
        )
        self.assertTrue(any("execution_id" in p for p in dod.check_trace(text)))
        twice = good_trace().replace("already_executed", "executed")
        self.assertTrue(any("already_executed" in p for p in dod.check_trace(twice)))

    def test_empty_trace_fails(self):
        self.assertTrue(dod.check_trace(""))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.txt"
            bad = Path(tmp) / "bad.txt"
            good.write_text(good_trace(), encoding="utf-8")
            bad.write_text("nothing\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(dod.main(["trace", str(good)]), 0)
                self.assertEqual(dod.main(["trace", str(bad)]), 1)
        self.assertIn("G5 trace: PASS", buf.getvalue())
        self.assertIn("G5 trace: FAIL", buf.getvalue())


class TestNormalise(unittest.TestCase):
    def test_strips_timestamps_and_elapsed_only(self):
        text = "[t+7.12s] ROUND n=1 elapsed_s=0.31 x=1\nDECISION a b=1\n[t+10s] PAGE\n"
        self.assertEqual(dod.normalise(text), ["ROUND n=1 x=1", "DECISION a b=1", "PAGE"])

    def test_keeps_values_that_look_like_time_inside_a_line(self):
        line = "DECISION verify observed_ms=3900 window_s=0.3"
        self.assertEqual(dod.normalise(line), [line])


class TestRealRun(unittest.TestCase):
    """Two real, fresh runs of `run --all`: the shipped trace satisfies G5 and repeats (G6)."""

    def test_real_trace_passes_g5_and_repeats_for_g6(self):
        first = dod.run_all_once()
        self.assertEqual(first.returncode, 0)
        self.assertEqual(dod.check_trace(first.stdout), [])
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(dod.repro(first.stdout), 0)
        self.assertIn("G6 repro: PASS", buf.getvalue())

    def test_repro_detects_a_changed_decision(self):
        first = dod.run_all_once().stdout.replace("rounds=3", "rounds=9", 1)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(dod.repro(first), 1)
        self.assertIn("G6 repro: FAIL", buf.getvalue())

    def test_repro_rejects_empty_output(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(dod.repro(""), 1)


if __name__ == "__main__":
    unittest.main()
