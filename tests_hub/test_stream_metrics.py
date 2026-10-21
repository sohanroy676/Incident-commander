"""v2.3 metrics strip and the approval stream (server-sent events read with fetch)."""

from __future__ import annotations

import http.client
import json
import time
import unittest
from pathlib import Path
from unittest import mock

from ic_hub import server as hub_server
from ic_hub.server import MAX_STREAMS, STATIC_DIR

from .support import HubTestCase
from .test_intake import PATH, alert, payload


class TestMetrics(HubTestCase):
    def test_counters_start_at_zero(self) -> None:
        m = self.call("GET", "/api/metrics").json()
        self.assertEqual((m["runs_started"], m["runs_done"], m["runs_running"]), (0, 0, 0))
        self.assertEqual((m["states"], m["approvals"], m["mean_run_s"]), ({}, {}, None))

    def test_a_finished_run_is_counted(self) -> None:
        self.run_to_end("ALRT-9003")
        m = self.call("GET", "/api/metrics").json()
        self.assertEqual((m["runs_started"], m["runs_done"], m["runs_failed"]), (1, 1, 0))
        self.assertEqual(sum(m["states"].values()), 1)
        self.assertGreaterEqual(m["mean_run_s"], 0)  # a fast run can round to 0.0

    def test_approval_answers_are_counted_by_outcome(self) -> None:
        run_id = self.start_run("ALRT-9001", mode="web", deadline_s=10)
        pending = self.wait_pending(run_id, "engineer-priya")
        url = f"/api/runs/{run_id}/approval"
        self.call("POST", url, {"nonce": pending["nonce"], "decision": "maybe"})
        self.call("POST", url, {"nonce": pending["nonce"], "decision": "approve"})
        self.call("POST", url, {"nonce": pending["nonce"], "decision": "approve"})  # replay
        self.wait_for(run_id)
        m = self.call("GET", "/api/metrics").json()
        # the replay is "stale" or a 409 once the run has ended, depending on timing
        self.assertEqual((m["approvals"]["accepted"], m["approvals"]["bad_decision"]), (1, 1))

    def test_only_numbers_and_fixed_names_come_back(self) -> None:
        marker = "UNIQUE-MARKER-TEXT"
        labels = {"service": "notification-service", "note": marker}
        self.call("POST", PATH, payload(alert(labels=labels, annotations={"summary": marker})))
        self.run_to_end("ALRT-9003")
        reply = self.call("GET", "/api/metrics")
        self.assertNotIn(marker.encode(), reply.body)
        m = reply.json()
        self.assertEqual(m["intake_alerts"], 1)
        for key in ("runs_started", "runs_running", "runs_done", "runs_failed", "uploads"):
            self.assertIsInstance(m[key], int)

    def test_guards_apply(self) -> None:
        self.assertEqual(self.call("GET", "/api/metrics", token=False).status, 403)
        self.assertEqual(
            self.call("GET", "/api/metrics", headers={"Host": "evil.test"}).status, 403
        )
        self.assertEqual(self.call("POST", "/api/metrics", {}).status, 404)


class Stream:
    """A raw streaming reader: http.client keeps the body open until the server closes it."""

    def __init__(self, case: HubTestCase, run_id: str, **headers: str) -> None:
        self.conn = http.client.HTTPConnection("127.0.0.1", case.port, timeout=15)
        hdrs = {"X-Hub-Token": case.server.token, **headers}
        self.conn.request("GET", f"/api/runs/{run_id}/stream", headers=hdrs)
        self.resp = self.conn.getresponse()

    def blocks(self):
        """Yield (event, data) pairs until the stream closes."""
        event, data = "message", []
        while True:
            line = self.resp.fp.readline()
            if not line:
                return
            text = line.decode().rstrip("\r\n")
            if text == "":
                if data:
                    yield event, "\n".join(data)
                event, data = "message", []
            elif text.startswith("event: "):
                event = text[7:]
            elif text.startswith("data: "):
                data.append(text[6:])

    def close(self) -> None:
        self.conn.close()


class TestStream(HubTestCase):
    def test_stream_follows_a_web_run_to_the_end(self) -> None:
        run_id = self.start_run("ALRT-9001", mode="web", deadline_s=0.5)
        stream = Stream(self, run_id)
        self.addCleanup(stream.close)
        self.assertEqual(stream.resp.status, 200)
        self.assertTrue(stream.resp.getheader("Content-Type").startswith("text/event-stream"))
        self.assertIsNone(stream.resp.getheader("Content-Length"))
        self.assertIn("default-src 'none'", stream.resp.getheader("Content-Security-Policy"))
        self.assertEqual(stream.resp.getheader("Cache-Control"), "no-store")
        events = list(stream.blocks())
        views = [json.loads(d) for e, d in events if e == "message"]
        self.assertTrue(any(v["pending"] for v in views), "an approval card never showed")
        targets = {v["pending"]["target"] for v in views if v["pending"]}
        self.assertIn("engineer-priya", targets)
        self.assertEqual(views[-1]["status"], "done")
        self.assertEqual(events[-1][0], "end")
        self.assertEqual(json.loads(events[-1][1])["reason"], "finished")

    def test_stream_carries_only_status_pending_and_error(self) -> None:
        run_id = self.start_run("ALRT-9003")
        stream = Stream(self, run_id)
        self.addCleanup(stream.close)
        for event, data in stream.blocks():
            if event == "message":
                self.assertEqual(set(json.loads(data)), {"status", "pending", "error"})

    def test_a_nonce_read_from_the_stream_works_once(self) -> None:
        run_id = self.start_run("ALRT-9001", mode="web", deadline_s=10)
        stream = Stream(self, run_id)
        self.addCleanup(stream.close)
        nonce = None
        for event, data in stream.blocks():
            view = json.loads(data) if event == "message" else {}
            if view.get("pending"):
                nonce = view["pending"]["nonce"]
                break
        self.assertIsNotNone(nonce)
        url = f"/api/runs/{run_id}/approval"
        first = self.call("POST", url, {"nonce": nonce, "decision": "approve"})
        self.assertEqual((first.status, first.json()["outcome"]), (200, "accepted"))
        replay = self.call("POST", url, {"nonce": nonce, "decision": "approve"})
        self.assertEqual(replay.status, 409)  # stale, or the run already ended
        self.wait_for(run_id)

    def test_guards_apply_before_any_stream_starts(self) -> None:
        run_id = self.start_run("ALRT-9003")
        path = f"/api/runs/{run_id}/stream"
        self.assertEqual(self.call("GET", path, token=False).status, 403)
        self.assertEqual(self.call("GET", path, headers={"Host": "evil.test"}).status, 403)
        self.assertEqual(self.call("GET", path, headers={"Origin": "http://evil.test"}).status, 403)
        # a token in the query string is not a token
        self.assertEqual(
            self.call("GET", f"{path}?token={self.server.token}", token=False).status, 403
        )
        self.assertEqual(self.call("POST", path, {}).status, 404)

    def test_unknown_and_malformed_run_ids(self) -> None:
        for run_id in ("0" * 16, "../../etc/passwd", "ZZZZZZZZZZZZZZZZ", "0" * 17):
            with self.subTest(run_id=run_id):
                self.assertEqual(self.call("GET", f"/api/runs/{run_id}/stream").status, 404)

    def test_open_streams_are_capped_and_freed(self) -> None:
        run_id = self.start_run("ALRT-9001", mode="web", deadline_s=5)
        self.wait_pending(run_id)
        streams = [Stream(self, run_id) for _ in range(MAX_STREAMS)]
        self.assertTrue(all(s.resp.status == 200 for s in streams))
        over = self.call("GET", f"/api/runs/{run_id}/stream")
        self.assertEqual(over.status, 429)
        for s in streams:
            s.close()
        deadline = time.monotonic() + 10
        while self.server._streams and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(self.server._streams, 0)
        again = Stream(self, run_id)
        self.addCleanup(again.close)
        self.assertEqual(again.resp.status, 200)

    def test_a_stream_ends_at_its_time_limit(self) -> None:
        run_id = self.start_run("ALRT-9001", mode="web", deadline_s=10)
        self.wait_pending(run_id)
        with mock.patch.object(hub_server, "STREAM_MAX_S", 0.4):
            stream = Stream(self, run_id)
            self.addCleanup(stream.close)
            events = list(stream.blocks())
        self.assertEqual(events[-1][0], "end")
        self.assertEqual(json.loads(events[-1][1])["reason"], "timeout")
        self.call(  # let the run finish quickly
            "POST",
            f"/api/runs/{run_id}/approval",
            {
                "nonce": self.call("GET", f"/api/runs/{run_id}").json()["pending"]["nonce"],
                "decision": "deny",
            },
        )


class TestPageSource(unittest.TestCase):
    """Static checks on the page: the stream goes through fetch, theme and a11y hooks exist."""

    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")

    def test_stream_uses_fetch_with_the_token_header_not_event_source(self) -> None:
        self.assertNotIn("EventSource", self.js)
        self.assertIn('/stream`, { headers: { "X-Hub-Token": TOKEN } }', self.js)
        self.assertNotIn("token=", self.js)

    def test_storage_access_is_guarded(self) -> None:
        for call in ("localStorage.getItem", "localStorage.setItem"):
            at = self.js.index(call)
            self.assertIn("try {", self.js[max(0, at - 120) : at])

    def test_theme_has_a_manual_override_beside_the_system_setting(self) -> None:
        self.assertIn('[data-theme="dark"]', self.css)
        self.assertIn('[data-theme="light"]', self.css)
        self.assertIn("prefers-color-scheme: dark", self.css)
        self.assertIn('id="theme-btn"', self.html)

    def test_accessibility_hooks(self) -> None:
        self.assertIn('href="#main"', self.html)
        self.assertIn('id="main"', self.html)
        self.assertIn('id="metrics"', self.html)
        self.assertRegex(self.html, r'id="metrics"[^>]*aria-live="polite"')
        self.assertRegex(self.html, r'<textarea id="am-json"[^>]*aria-label=')
        self.assertIn("focus-visible", self.css)
        self.assertIn('lang="en"', self.html)

    def test_every_form_control_has_a_name(self) -> None:
        import re

        for control in re.findall(r"<(?:input|select|textarea)\b[^>]*>", self.html):
            ident = re.search(r'id="([^"]+)"', control)
            self.assertIsNotNone(ident, control)
            labelled = "aria-label=" in control or f'for="{ident.group(1)}"' in self.html
            # controls inside a <label> are named by it
            at = self.html.index(control)
            inside = self.html.rfind("<label", 0, at) > self.html.rfind("</label>", 0, at)
            self.assertTrue(labelled or inside, control)

    def test_approval_shortcuts_need_shift(self) -> None:
        self.assertIn('event.key === "A" && asking', self.js)
        self.assertIn('event.key === "D" && asking', self.js)
        self.assertNotIn('event.key === "a"', self.js)
        self.assertIn('matches("input, textarea, select")', self.js)

    def test_playwright_is_not_a_dependency(self) -> None:
        root = Path(__file__).resolve().parent.parent
        for name in ("requirements.txt", "requirements-dev.txt"):
            self.assertNotIn("playwright", (root / name).read_text(encoding="utf-8").lower())
        ci = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8").lower()
        self.assertNotIn("playwright", ci)


if __name__ == "__main__":
    unittest.main()
