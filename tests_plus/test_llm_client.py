"""LLMClient against a fake server: success and every failure mode, and key hygiene (AC-24)."""

import json
import time
import unittest

from ic_plus.llm_client import LLMClient
from tests_plus.fake_llm import FakeLLM, chat_body, unused_url

SECRET = "sk-test-SECRET-0123456789"
MESSAGES = [{"role": "user", "content": "hi"}]


class TestSuccess(unittest.TestCase):
    def test_reply_text_and_request_shape(self):
        with FakeLLM([(200, chat_body('{"a": 1}'), 0)]) as fake:
            reply = LLMClient(fake.url, "m1", None, timeout_s=5).chat(MESSAGES)
        self.assertTrue(reply.ok, reply.error)
        self.assertEqual(reply.text, '{"a": 1}')
        request = fake.requests[0]
        self.assertEqual(request["path"], "/v1/chat/completions")
        body = json.loads(request["body"])
        self.assertEqual(body["model"], "m1")
        self.assertEqual(body["messages"], MESSAGES)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertNotIn("Authorization", request["headers"])

    def test_json_mode_can_be_off_and_trailing_slash_is_fine(self):
        with FakeLLM([(200, chat_body("x"), 0)]) as fake:
            reply = LLMClient(fake.url + "/", "m", None, timeout_s=5).chat(
                MESSAGES, json_mode=False
            )
        self.assertTrue(reply.ok)
        self.assertNotIn("response_format", json.loads(fake.requests[0]["body"]))

    def test_key_is_sent_as_bearer_only_when_given(self):
        with FakeLLM([(200, chat_body("x"), 0)]) as fake:
            LLMClient(fake.url, "m", SECRET, timeout_s=5).chat(MESSAGES)
        self.assertEqual(fake.requests[0]["headers"]["Authorization"], f"Bearer {SECRET}")

    def test_user_agent_is_not_the_urllib_default(self):
        with FakeLLM([(200, chat_body("x"), 0)]) as fake:
            LLMClient(fake.url, "m", None, timeout_s=5).chat(MESSAGES)
        headers = {k.lower(): v for k, v in fake.requests[0]["headers"].items()}
        self.assertNotIn("python-urllib", headers["user-agent"].lower())
        self.assertTrue(headers["user-agent"])


class TestNeverRaises(unittest.TestCase):
    def failure(self, replies, timeout_s=5.0, key=None):
        with FakeLLM(replies) as fake:
            reply = LLMClient(fake.url, "m", key, timeout_s=timeout_s).chat(MESSAGES)
        self.assertFalse(reply.ok)
        self.assertEqual(reply.text, "")
        return reply

    def test_http_500(self):
        self.assertIn("http 500", self.failure([(500, "boom", 0)]).error)

    def test_bad_key_401(self):
        self.assertIn("http 401", self.failure([(401, "no", 0)], key=SECRET).error)

    def test_malformed_json(self):
        self.assertEqual(self.failure([(200, "not json{", 0)]).error, "malformed response")

    def test_missing_choices_and_non_string_content(self):
        for body in (
            "{}",
            '{"choices": []}',
            '{"choices": [{"message": {"content": 5}}]}',
            "[]",
            "null",
        ):
            with self.subTest(body=body):
                self.assertEqual(self.failure([(200, body, 0)]).error, "malformed response")

    def test_timeout_takes_at_least_the_timeout(self):
        start = time.monotonic()
        reply = self.failure([(200, chat_body("late"), 1.0)], timeout_s=0.3)
        self.assertGreaterEqual(time.monotonic() - start, 0.25)
        self.assertTrue(reply.error)

    def test_connection_refused(self):
        reply = LLMClient(unused_url(), "m", None, timeout_s=2).chat(MESSAGES)
        self.assertFalse(reply.ok)
        self.assertIn("unreachable", reply.error)

    def test_garbage_url_does_not_raise(self):
        for url in ("not a url", "ftp://x/v1", ""):
            with self.subTest(url=url):
                self.assertFalse(LLMClient(url, "m", None, timeout_s=1).chat(MESSAGES).ok)


class TestKeyHygiene(unittest.TestCase):
    def test_repr_hides_the_key(self):
        self.assertNotIn(SECRET, repr(LLMClient("http://x/v1", "m", SECRET)))

    def test_errors_never_contain_the_key(self):
        bad_urls = [f"http://user:{SECRET}@127.0.0.1:1/v1", unused_url()]
        for url in bad_urls:
            reply = LLMClient(url, "m", SECRET, timeout_s=1).chat(MESSAGES)
            self.assertFalse(reply.ok)
            self.assertNotIn(SECRET, reply.error)
            self.assertNotIn(SECRET, repr(reply))

    def test_scrub_replaces_a_key_echoed_by_the_error(self):
        client = LLMClient("http://x/v1", "m", SECRET)
        self.assertNotIn(SECRET, client._fail(f"upstream said {SECRET}").error)


if __name__ == "__main__":
    unittest.main()
