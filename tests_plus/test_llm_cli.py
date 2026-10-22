"""--llm local|hosted end to end: X2 (unavailable half), AC-22, and key hygiene in real runs."""

import contextlib
import io
import json
import unittest
from unittest import mock

from ic_plus.__main__ import main
from ic_plus.narrator import UNAVAILABLE_LINE
from tests_plus.fake_llm import FakeLLM, chat_body, unused_url
from tests_plus.test_cli import decisions, run
from tests_plus.test_llm_guard import FACTS  # noqa: F401  (facts of ALRT-9001, used by recordings)
from tests_plus.test_narrator import RECORDED, SECRET


def in_process(*argv: str, env: dict | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with (
        mock.patch("ic_plus.__main__.load_env", return_value=env or {}),
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
    ):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestUnavailableX2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.off = run("ic_plus", "run", "--all", "--llm", "off")
        cls.down = run(
            "ic_plus", "run", "--all", "--llm", "local", "--llm-url", unused_url(), "--model", "m"
        )

    def test_both_complete_and_every_decision_line_equals_the_baseline(self):
        self.assertEqual(self.off.returncode, 0, self.off.stderr)
        self.assertEqual(self.down.returncode, 0, self.down.stderr)
        self.assertEqual(decisions(self.down.stdout), decisions(self.off.stdout))
        self.assertGreater(len(decisions(self.down.stdout)), 20)

    def test_the_fallback_notice_is_printed_per_alert_and_the_banner_is_last(self):
        lines = self.down.stdout.splitlines()
        self.assertEqual(lines.count(UNAVAILABLE_LINE), 3)
        self.assertEqual(lines[-1], "extension: llm=local approver=scripted")
        self.assertNotIn(UNAVAILABLE_LINE, self.off.stdout)
        self.assertEqual(self.off.stdout.splitlines()[-1], "extension: llm=off approver=scripted")

    def test_no_server_and_no_model_configured_also_falls_back(self):
        # in-process with an empty dotenv: a developer's real .env must not leak into the test
        code, out, err = in_process(
            "run", "ALRT-9001", "--llm", "local", "--llm-url", unused_url(), env={}
        )
        self.assertEqual(code, 0, err)
        self.assertIn(UNAVAILABLE_LINE, out)
        self.assertIn("missing model", err)


class TestWithAServer(unittest.TestCase):
    def test_a_good_reply_prints_status_and_narrative_and_decisions_stay_equal(self):
        baseline = run("ic_plus", "run", "ALRT-9001", "--llm", "off")
        with FakeLLM([(200, chat_body(RECORDED["good"]["reply"]), 0)]) as fake:
            p = run(
                "ic_plus",
                "run",
                "ALRT-9001",
                "--llm",
                "local",
                "--llm-url",
                fake.url,
                "--model",
                "fake-model",
            )
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("llm: ok role=narrator model=fake-model guard=pass", p.stdout)
        self.assertIn('postmortem narrative: "AI-drafted narrative (not authoritative): ', p.stdout)
        self.assertEqual(decisions(p.stdout), decisions(baseline.stdout))
        self.assertEqual(len(fake.requests), 1)

    def test_a_bad_reply_is_rejected_logged_and_decisions_stay_equal(self):
        baseline = run("ic_plus", "run", "ALRT-9001", "--llm", "off")
        bad = RECORDED["ignore_previous"]["reply"]
        with FakeLLM([(200, chat_body(bad), 0)]) as fake:
            p = run(
                "ic_plus",
                "run",
                "ALRT-9001",
                "--llm",
                "local",
                "--llm-url",
                fake.url,
                "--model",
                "m",
            )
        self.assertIn("llm_rejected role=narrator alert=ALRT-9001", p.stdout)
        self.assertIn("llm: rejected, deterministic fallback", p.stdout)
        self.assertNotIn("postmortem narrative", p.stdout)
        self.assertEqual(decisions(p.stdout), decisions(baseline.stdout))

    def test_after_the_first_failure_the_remaining_alerts_skip_the_server(self):
        with FakeLLM([(500, "boom", 0)]) as fake:
            code, out, _ = in_process(
                "run", "--all", "--llm", "local", "--llm-url", fake.url, "--model", "m"
            )
        self.assertEqual(code, 0)
        self.assertEqual(out.count(UNAVAILABLE_LINE), 3)
        self.assertEqual(len(fake.requests), 1)

    def test_the_cli_approver_path_also_narrates(self):
        # Typed "approve" is answered by priya, so the recorded devon narrative is rightly rejected.
        reply = json.dumps(
            {
                "summary": "ALRT-9001 on checkout-service.",
                "impact": "Slow.",
                "root_cause_text": "Bad deploy.",
            }
        )
        with FakeLLM([(200, chat_body(reply), 0)]) as fake:
            p = run(
                "ic_plus", "run", "ALRT-9001", "--approver", "cli", "--llm", "local",
                "--llm-url", fake.url, "--model", "fake-model", stdin="approve\n",
            )  # fmt: skip
        self.assertIn("llm: ok role=narrator", p.stdout)
        self.assertEqual(p.stdout.splitlines()[-1], "extension: llm=local approver=cli")


class TestKeysInRealRuns(unittest.TestCase):
    def test_hosted_sends_the_env_key_and_never_prints_it(self):
        env = {"LLM_API_KEY": SECRET}
        with FakeLLM([(200, chat_body(RECORDED["good"]["reply"]), 0)]) as fake:
            code, out, err = in_process(
                "run",
                "ALRT-9001",
                "--llm",
                "hosted",
                "--llm-url",
                fake.url,
                "--model",
                "m",
                env=env,
            )
        self.assertEqual(code, 0)
        self.assertEqual(fake.requests[0]["headers"]["Authorization"], f"Bearer {SECRET}")
        self.assertNotIn(SECRET, out + err)

    def test_hosted_failure_output_does_not_contain_the_key(self):
        env = {"LLM_API_KEY": SECRET, "LLM_BASE_URL": unused_url(), "LLM_MODEL": "m"}
        code, out, err = in_process("run", "ALRT-9001", "--llm", "hosted", env=env)
        self.assertEqual(code, 0)
        self.assertIn(UNAVAILABLE_LINE, out)
        self.assertNotIn(SECRET, out + err)

    def test_hosted_without_a_key_makes_no_request_and_falls_back(self):
        with FakeLLM([(200, chat_body("{}"), 0)]) as fake:
            code, out, err = in_process(
                "run", "ALRT-9001", "--llm", "hosted", "--llm-url", fake.url, "--model", "m", env={}
            )
        self.assertEqual((code, fake.requests), (0, []))
        self.assertIn(UNAVAILABLE_LINE, out)
        self.assertIn("missing key", err)

    def test_local_never_sends_the_hosted_key(self):
        env = {"LLM_API_KEY": SECRET}
        with FakeLLM([(200, chat_body("{}"), 0)]) as fake:
            in_process(
                "run", "ALRT-9001", "--llm", "local", "--llm-url", fake.url, "--model", "m", env=env
            )
        self.assertNotIn("Authorization", fake.requests[0]["headers"])

    def test_flags_beat_the_env_file(self):
        env = {"LLM_BASE_URL": unused_url(), "LLM_MODEL": "from-env"}
        with FakeLLM([(200, chat_body(RECORDED["good"]["reply"]), 0)]) as fake:
            _, out, _ = in_process(
                "run",
                "ALRT-9001",
                "--llm",
                "local",
                "--llm-url",
                fake.url,
                "--model",
                "from-flag",
                env=env,
            )
        self.assertIn("model=from-flag", out)

    def test_the_env_file_supplies_url_and_model_when_flags_are_absent(self):
        with FakeLLM([(200, chat_body(RECORDED["good"]["reply"]), 0)]) as fake:
            env = {"LLM_BASE_URL": fake.url, "LLM_MODEL": "from-env"}
            _, out, _ = in_process("run", "ALRT-9001", "--llm", "local", env=env)
        self.assertIn("model=from-env", out)

    def test_an_unknown_alert_with_llm_on_is_still_exit_2_without_narration(self):
        code, out, _ = in_process("run", "ALRT-0000", "--llm", "local", "--model", "m")
        self.assertEqual(code, 2)
        self.assertNotIn("narrator", out)


if __name__ == "__main__":
    unittest.main()
