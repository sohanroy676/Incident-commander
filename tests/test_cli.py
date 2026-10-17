"""CLI and M1 output contract, run as real subprocesses with no environment variables needed."""

import re
import subprocess
import sys
import unittest

from incident_commander.fixtures.alerts import ALERTS
from incident_commander.report import decision, fmt, header


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "incident_commander", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


class TestToolsCommand(unittest.TestCase):
    def test_alrt_9001_matches_the_roadmap_contract(self):
        p = run("tools", "ALRT-9001")
        self.assertEqual(p.returncode, 0, p.stderr)
        out = p.stdout.splitlines()
        self.assertEqual(out[0], "== M1 SIGNAL INGESTION ==")
        self.assertRegex(
            out[1],
            r"^alert=ALRT-9001 service=checkout-service fired_at=\d+ severity_label=high$",
        )
        rows = out[3:]
        self.assertEqual(
            [r.split()[0] for r in rows],
            ["get_latency", "get_error_rate", "get_deployments", "get_dependencies", "get_logs"],
        )
        joined = "\n".join(rows)
        for expected in (
            "median_5m_ms=1440 baseline_ms=180",
            "median_5m=0.011 baseline=0.010 ratio=1.1",
            "count=1 latest=v2.14.0 before_alert_s=720",
            "payment-service(lat=1.0,err=1.0) inventory-service(lat=1.0,err=1.0)",
            "lines=24   (content not shown here: untrusted)",
        ):
            self.assertIn(expected, joined)
        self.assertEqual(len(re.findall(r"\bTrue\b", joined)), 5)  # all five fresh

    def test_log_content_is_never_printed(self):
        for alert_id in ALERTS:
            self.assertNotIn("[INFO]", run("tools", alert_id).stdout)
            self.assertNotIn("[WARN]", run("tools", alert_id).stdout)

    def test_each_alert_runs(self):
        for alert_id in ALERTS:
            p = run("tools", alert_id)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn(f"alert={alert_id}", p.stdout)

    def test_unknown_alert_exits_nonzero_with_message_on_stderr(self):
        p = run("tools", "ALRT-0000")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(p.stdout, "")
        self.assertIn("unknown alert: ALRT-0000", p.stderr)

    def test_output_is_reproducible(self):
        self.assertEqual(run("tools", "ALRT-9002").stdout, run("tools", "ALRT-9002").stdout)

    def test_no_command_is_an_error(self):
        self.assertNotEqual(run().returncode, 0)


class TestLineHelpers(unittest.TestCase):
    def test_header(self):
        self.assertEqual(header(3, "INVESTIGATION"), "== M3 INVESTIGATION ==")

    def test_value_formatting(self):
        self.assertEqual(fmt(True), "True")
        self.assertEqual(fmt([]), "[]")
        self.assertEqual(fmt("already resolved"), '"already resolved"')
        self.assertEqual(fmt(1760000100.0), "1760000100")
        self.assertEqual(fmt(0.3), "0.3")

    def test_decision_line(self):
        self.assertEqual(
            decision("page_check", case="immediate", window_s=0.3, escalated=False),
            "DECISION page_check case=immediate window_s=0.3 escalated=False",
        )


if __name__ == "__main__":
    unittest.main()
