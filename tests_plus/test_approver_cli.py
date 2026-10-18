"""CliResponder through the real ApprovalGate on the real clock (no patched sleep).

Timing asserts are lower bounds only, per the project's timing policy.
"""

import io
import os
import threading
import unittest

from ic_plus.approver_cli import CliResponder
from incident_commander.approval import ApprovalGate
from incident_commander.clocks import ControlClock

PRIYA, DEVON = "engineer-priya", "engineer-devon"
DEADLINE_S = 0.1
TICK_S = 0.01


def gate(responder: CliResponder) -> ApprovalGate:
    return ApprovalGate(ControlClock(), responder, PRIYA, DEVON, DEADLINE_S, TICK_S)


def request(stream, out=None):
    out = out or io.StringIO()
    clock = ControlClock()
    start = clock.now()
    outcome = gate(CliResponder(stream, out, DEADLINE_S)).request("rollback_deployment", "checkout")
    return outcome, clock.now() - start, out.getvalue()


class OpenPipe:
    """A stdin that stays open: a human who has not typed anything yet."""

    def __init__(self):
        read_fd, self._write_fd = os.pipe()
        self.stream = os.fdopen(read_fd, "r")

    def type(self, text: str) -> None:
        os.write(self._write_fd, text.encode())

    def close(self) -> None:
        os.close(self._write_fd)
        self.stream.close()


class TestAnswers(unittest.TestCase):
    def test_answer_in_time_approves_the_primary(self):
        outcome, _, _ = request(io.StringIO("approve\n"))
        self.assertEqual(outcome.status, "approved")
        self.assertFalse(outcome.escalated)
        self.assertEqual(outcome.token.approved_by, PRIYA)

    def test_deny_is_a_denial_and_no_token(self):
        outcome, _, _ = request(io.StringIO("deny\n"))
        self.assertEqual(outcome.status, "denied")
        self.assertIsNone(outcome.token)

    def test_case_and_whitespace_are_ignored(self):
        outcome, _, _ = request(io.StringIO("  ApProVe \r\n"))
        self.assertEqual(outcome.status, "approved")

    def test_noise_never_approves(self):
        for noise in ("yes\n", "approve it\n", "y\n", "\n", "approved\n", "ok\n"):
            with self.subTest(noise=noise):
                outcome, _, _ = request(io.StringIO(noise))
                self.assertEqual(outcome.status, "expired")
                self.assertIsNone(outcome.token)

    def test_noise_before_a_real_answer_is_skipped(self):
        outcome, _, _ = request(io.StringIO("hello\nyes\napprove\n"))
        self.assertEqual(outcome.status, "approved")


class TestDeadline(unittest.TestCase):
    def test_no_answer_escalates_then_expires_after_two_real_deadlines(self):
        pipe = OpenPipe()
        self.addCleanup(pipe.close)
        outcome, elapsed, _ = request(pipe.stream)
        self.assertEqual(outcome.status, "expired")
        self.assertTrue(outcome.escalated)
        self.assertGreaterEqual(elapsed, 2 * DEADLINE_S)

    def test_a_late_answer_goes_to_the_secondary(self):
        pipe = OpenPipe()
        self.addCleanup(pipe.close)
        threading.Timer(DEADLINE_S * 1.5, pipe.type, args=("approve\n",)).start()
        outcome, elapsed, _ = request(pipe.stream)
        self.assertEqual(outcome.status, "approved")
        self.assertTrue(outcome.escalated)
        self.assertEqual(outcome.token.approved_by, DEVON)
        self.assertGreaterEqual(elapsed, DEADLINE_S)

    def test_closed_stdin_is_no_answer_not_a_hang_or_an_approval(self):
        outcome, elapsed, _ = request(io.StringIO(""))
        self.assertEqual(outcome.status, "expired")
        self.assertTrue(outcome.escalated)
        self.assertGreaterEqual(elapsed, 2 * DEADLINE_S)

    def test_a_stream_that_fails_is_no_answer(self):
        class Broken:
            def readline(self):
                raise ValueError("I/O operation on closed file")

        outcome, _, _ = request(Broken())
        self.assertEqual(outcome.status, "expired")


class TestPrompt(unittest.TestCase):
    def test_each_target_is_prompted_once_with_the_deadline(self):
        pipe = OpenPipe()
        self.addCleanup(pipe.close)
        _, _, shown = request(pipe.stream)
        self.assertEqual(shown.count(f"PAGE {PRIYA}:"), 1)
        self.assertEqual(shown.count(f"PAGE {DEVON}:"), 1)
        self.assertIn("(deadline 0.1s)", shown)

    def test_the_answer_is_echoed(self):
        _, _, shown = request(io.StringIO("approve\n"))
        self.assertIn("approve", shown.splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
