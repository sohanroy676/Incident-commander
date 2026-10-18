"""CLI and M1 output contract, run as real subprocesses with no environment variables needed."""

import re
import subprocess
import sys
import time
import unittest

from incident_commander.fixtures.alerts import ALERTS
from incident_commander.report import decision, fmt, header, trace_line


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


DECISIONS = {
    "ALRT-9001": "DECISION verdict alert=ALRT-9001 verdict=matched runbook=RB-101 rounds=3",
    "ALRT-9002": "DECISION verdict alert=ALRT-9002 verdict=matched runbook=RB-102 rounds=3",
    "ALRT-9003": "DECISION verdict alert=ALRT-9003 verdict=no_confident_match "
    "runbook=none rounds=4 reason=all_refuted",
}


def strip_timestamps(text: str) -> str:
    return re.sub(r"\[t\+\d+\.\d\ds\]", "[t]", text)


class TestInvestigateCommand(unittest.TestCase):
    def test_decision_lines_match_the_roadmap(self):
        for alert_id, expected in DECISIONS.items():
            p = run("investigate", alert_id)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(p.stdout.splitlines()[-1], expected)

    def test_header_and_stub_declaration(self):
        out = run("investigate", "ALRT-9001").stdout.splitlines()
        self.assertEqual(out[0], "== M3 INVESTIGATION ==")
        self.assertTrue(
            out[1].startswith("alert=ALRT-9001 ranker=STUB order=RB-102,RB-101,RB-104,RB-103")
        )

    def test_9001_round_lines(self):
        out = run("investigate", "ALRT-9001").stdout.splitlines()
        rounds = [line.split("] ", 1)[1] for line in out if "ROUND" in line]
        self.assertEqual(
            [r.split()[2] for r in rounds],
            ["tool=get_latency", "tool=get_error_rate", "tool=get_deployments"],
        )
        self.assertIn("mode=exploratory", run("investigate", "ALRT-9003").stdout)

    def test_logs_and_log_text_never_appear(self):
        for alert_id in DECISIONS:
            out = run("investigate", alert_id).stdout
            self.assertNotIn("get_logs", out)
            self.assertNotIn("[INFO]", out)

    def test_output_is_reproducible_apart_from_real_timestamps(self):
        self.assertEqual(
            strip_timestamps(run("investigate", "ALRT-9002").stdout),
            strip_timestamps(run("investigate", "ALRT-9002").stdout),
        )

    def test_unknown_alert_exits_nonzero_with_message_on_stderr(self):
        p = run("investigate", "ALRT-0000")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(p.stdout, "")
        self.assertIn("unknown alert: ALRT-0000", p.stderr)


GATES_DECISIONS = [
    (
        "DECISION classify alert=ALRT-9001 severity_label=high action=rollback_deployment "
        "tier=high requires_approval=True"
    ),
    (
        "DECISION classify alert=ALRT-9002 severity_label=high action=restart_service "
        "tier=low requires_approval=False"
    ),
    "DECISION page_check case=immediate window_s=0.3 escalated=False",
    (
        "DECISION page_check case=after_sleep window_s=0.3 escalated=True "
        "from=engineer-priya to=engineer-devon"
    ),
    'DECISION page_check case=answered_in_time escalated=False reason="already resolved"',
]


class TestGatesCommand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t0 = time.monotonic()
        cls.p = run("gates")
        cls.elapsed = time.monotonic() - t0
        cls.out = cls.p.stdout.splitlines()

    def test_succeeds_and_really_sleeps(self):
        self.assertEqual(self.p.returncode, 0, self.p.stderr)
        self.assertGreaterEqual(self.elapsed, 0.4)

    def test_headers_in_order(self):
        headers = [line for line in self.out if line.startswith("==")]
        self.assertEqual(
            headers,
            [
                "== M4 BLAST-RADIUS CLASSIFICATION ==",
                "== M5 TIME-BOXED APPROVAL ==",
                "== EXECUTION (idempotency demo) ==",
            ],
        )

    def test_decision_lines_match_the_roadmap(self):
        decisions = [
            line for line in self.out if line.startswith("DECISION") and "execute" not in line
        ]
        self.assertEqual(decisions, GATES_DECISIONS)

    def test_trace_lines(self):
        self.assertRegex(
            self.out[4], r"^\[t\+\d+\.\d\ds\] PAGE target=engineer-priya window_s=0.3$"
        )
        self.assertTrue(any(re.search(r"SLEEP real_seconds=0\.4$", line) for line in self.out))

    def test_execute_then_retry_share_one_id(self):
        ex = [line for line in self.out if line.startswith("DECISION execute")]
        pattern = (
            r"^DECISION execute alert=ALRT-9002 action=restart_service status=%s "
            r"execution_id=(exec-[0-9a-f]{10})$"
        )
        first = re.match(pattern % "executed", ex[0])
        retry = re.match(pattern % "already_executed", ex[1])
        self.assertTrue(first and retry, ex)
        self.assertEqual(first.group(1), retry.group(1))
        self.assertEqual(len(ex), 2)

    def test_reproducible_apart_from_real_timestamps(self):
        self.assertEqual(strip_timestamps(self.p.stdout), strip_timestamps(run("gates").stdout))


class TestLineHelpers(unittest.TestCase):
    def test_header(self):
        self.assertEqual(header(3, "INVESTIGATION"), "== M3 INVESTIGATION ==")

    def test_value_formatting(self):
        self.assertEqual(fmt(True), "True")
        self.assertEqual(fmt([]), "[]")
        self.assertEqual(fmt("already resolved"), '"already resolved"')
        self.assertEqual(fmt(1760000100.0), "1760000100")
        self.assertEqual(fmt(0.3), "0.3")

    def test_trace_line(self):
        self.assertEqual(
            trace_line(0.0, "ROUND", n=1, fresh=True), "[t+0.00s] ROUND n=1 fresh=True"
        )
        self.assertEqual(trace_line(1.234, "DONE"), "[t+1.23s] DONE")

    def test_decision_line(self):
        self.assertEqual(
            decision("page_check", case="immediate", window_s=0.3, escalated=False),
            "DECISION page_check case=immediate window_s=0.3 escalated=False",
        )


if __name__ == "__main__":
    unittest.main()


RUN_HEADERS = [
    "== M1 SIGNAL INGESTION ==",
    "== M2 RUNBOOK GROUNDING ==",
    "== M3 INVESTIGATION ==",
    "== M4 BLAST-RADIUS CLASSIFICATION ==",
    "== M5 TIME-BOXED APPROVAL ==",
    "== M6 VERIFIED RESOLUTION ==",
    "== M7 POSTMORTEM DRAFT ==",
    "== M8 EVALUATION ==",
]
EXEC_ID = r"exec-[0-9a-f]{10}"
RUN_ALL_DECISIONS = [
    r"DECISION verdict alert=ALRT-9001 verdict=matched runbook=RB-101 rounds=3",
    r"DECISION verdict alert=ALRT-9002 verdict=matched runbook=RB-102 rounds=3",
    r"DECISION verdict alert=ALRT-9003 verdict=no_confident_match runbook=none rounds=4 reason=all_refuted",
    r"DECISION classify alert=ALRT-9001 severity_label=high action=rollback_deployment tier=high requires_approval=True",
    r"DECISION classify alert=ALRT-9002 severity_label=high action=restart_service tier=low requires_approval=False",
    r"DECISION page_check case=immediate window_s=0.3 escalated=False",
    r"DECISION page_check case=after_sleep window_s=0.3 escalated=True from=engineer-priya to=engineer-devon",
    r'DECISION page_check case=answered_in_time escalated=False reason="already resolved"',
    r"DECISION approval alert=ALRT-9001 escalated=True approved_by=engineer-devon",
    rf"DECISION execute alert=ALRT-9001 action=rollback_deployment status=executed execution_id={EXEC_ID}",
    r"DECISION verify alert=ALRT-9001 status=resolved verified=True baseline_ms=180 observed_ms=182",
    rf"DECISION execute alert=ALRT-9002 action=restart_service status=executed execution_id={EXEC_ID}",
    rf"DECISION execute alert=ALRT-9002 action=restart_service status=already_executed execution_id={EXEC_ID}",
    r"DECISION verify alert=ALRT-9002 status=resolved verified=True baseline_ms=180 observed_ms=195",
    r"DECISION handoff alert=ALRT-9003 reason=no_confident_match",
    r'DECISION verify alert=ALRT-9002 variant=fix_fails status=reopened verified=False baseline_ms=180 observed_ms=3900 reason="remediation ran but did not resolve the signal"',
    r"DECISION postmortem alert=ALRT-9001 notified=\[\] published=False",
    r"DECISION publish alert=ALRT-9001 published=True notified=\['oncall-channel'\]",
]


class TestRunAll(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first = run("run", "--all")
        cls.second = run("run", "--all")

    def test_exits_zero_with_eight_headers_once_each_in_order(self):
        self.assertEqual(self.first.returncode, 0, self.first.stderr)
        headers = [
            ln.split("  ")[0] for ln in self.first.stdout.splitlines() if ln.startswith("== M")
        ]
        self.assertEqual(headers, RUN_HEADERS)

    def test_every_contract_decision_line_is_present_in_order(self):
        lines = self.first.stdout.splitlines()
        at = 0
        for pattern in RUN_ALL_DECISIONS:
            hit = next((i for i in range(at, len(lines)) if re.fullmatch(pattern, lines[i])), None)
            self.assertIsNotNone(hit, f"missing or out of order: {pattern}")
            at = hit

    def test_retry_shares_the_execution_id(self):
        ids = re.findall(
            r"alert=ALRT-9002 action=restart_service status=\w+ execution_id=(\S+)",
            self.first.stdout,
        )
        self.assertEqual(len(ids), 2)
        self.assertEqual(ids[0], ids[1])

    def test_m2_prints_hybrid_scores_and_m8_is_a_placeholder(self):
        out = self.first.stdout
        self.assertIn("ranker=HYBRID", out)
        self.assertNotIn("ranker=STUB", out)
        self.assertIn("runbook  bm25_rank char_rank fused_score", out)
        self.assertEqual(out.count("top2_margin="), 3)
        self.assertIn("== M8 EVALUATION ==  not implemented in v0.4", self.first.stdout)

    def test_decision_lines_are_identical_and_output_matches_apart_from_timestamps(self):
        def decisions(text):
            return [ln for ln in text.splitlines() if ln.startswith("DECISION")]

        self.assertEqual(decisions(self.first.stdout), decisions(self.second.stdout))
        self.assertEqual(strip_timestamps(self.first.stdout), strip_timestamps(self.second.stdout))

    def test_log_text_is_never_printed(self):
        self.assertNotIn("[INFO]", self.first.stdout)
        self.assertNotIn("[WARN]", self.first.stdout)

    def test_approval_really_waits_for_the_escalation(self):
        t0 = time.monotonic()
        run("run", "ALRT-9001")
        self.assertGreaterEqual(time.monotonic() - t0, 0.4)  # 0.3 s primary window + 0.1 s devon


class TestRunSingle(unittest.TestCase):
    def test_single_alert_runs(self):
        p = run("run", "ALRT-9003")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("DECISION handoff alert=ALRT-9003 reason=no_confident_match", p.stdout)
        self.assertNotIn("variant=fix_fails", p.stdout)

    def test_unknown_alert_exits_two_with_stderr_message(self):
        p = run("run", "ALRT-0000")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(p.stdout, "")
        self.assertIn("unknown alert: ALRT-0000", p.stderr)

    def test_needs_an_alert_or_all_but_not_both(self):
        self.assertNotEqual(run("run").returncode, 0)
        self.assertNotEqual(run("run", "ALRT-9001", "--all").returncode, 0)
