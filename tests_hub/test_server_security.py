"""Transport-level checks: Host, Origin, token, framing, size, static allowlist, headers."""

import json
import unittest
from pathlib import Path

from ic_hub.schema import MAX_BODY_BYTES
from ic_hub.server import STATIC_DIR

from .support import HubTestCase


class TestTransport(HubTestCase):
    def test_binds_to_loopback_only(self) -> None:
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_index_embeds_the_token_and_sets_security_headers(self) -> None:
        reply = self.call("GET", "/", token=False)
        self.assertEqual(reply.status, 200)
        self.assertIn(self.server.token.encode(), reply.body)
        self.assertNotIn(b"__HUB_TOKEN__", reply.body)
        csp = reply.headers["Content-Security-Policy"]
        self.assertIn("default-src 'none'", csp)
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("unsafe", csp)
        self.assertEqual(reply.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(reply.headers["X-Frame-Options"], "DENY")
        self.assertEqual(reply.headers["Referrer-Policy"], "no-referrer")

    def test_error_responses_carry_the_security_headers_too(self) -> None:
        for reply in (
            self.call("GET", "/api/alerts", token=False),
            self.call("GET", "/nope", token=False),
            self.call("GET", "/", headers={"Host": "evil.example"}, token=False),
        ):
            self.assertIn("Content-Security-Policy", reply.headers)
            self.assertEqual(reply.headers["X-Content-Type-Options"], "nosniff")

    def test_foreign_host_header_is_refused(self) -> None:
        for host in ("evil.example", "evil.example:80", f"localhost:{self.port + 1}", ""):
            with self.subTest(host=host):
                reply = self.call("GET", "/", headers={"Host": host}, token=False)
                self.assertEqual(reply.status, 403)
                reply = self.call("GET", "/api/alerts", headers={"Host": host})
                self.assertEqual(reply.status, 403)

    def test_localhost_name_is_accepted(self) -> None:
        reply = self.call("GET", "/", headers={"Host": f"localhost:{self.port}"}, token=False)
        self.assertEqual(reply.status, 200)

    def test_missing_host_header_is_refused(self) -> None:
        status, _ = self.raw([b"GET / HTTP/1.0"])
        self.assertEqual(status, 403)

    def test_foreign_origin_is_refused_on_get_and_post(self) -> None:
        for origin in ("http://evil.example", "null", f"https://127.0.0.1:{self.port}"):
            with self.subTest(origin=origin):
                self.assertEqual(
                    self.call("GET", "/api/alerts", headers={"Origin": origin}).status, 403
                )
                self.assertEqual(
                    self.call(
                        "POST", "/api/runs", {"alert_id": "ALRT-9003"}, headers={"Origin": origin}
                    ).status,
                    403,
                )

    def test_same_origin_is_accepted(self) -> None:
        reply = self.call("GET", "/api/alerts", headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(reply.status, 200)

    def test_api_needs_the_token(self) -> None:
        self.assertEqual(self.call("GET", "/api/alerts", token=False).status, 403)
        self.assertEqual(
            self.call("GET", "/api/alerts", headers={"X-Hub-Token": "guess"}, token=False).status,
            403,
        )
        self.assertEqual(
            self.call("POST", "/api/runs", {"alert_id": "ALRT-9003"}, token=False).status, 403
        )
        self.assertEqual(self.call("GET", "/api/alerts").status, 200)

    def test_token_is_not_accepted_from_the_query_string(self) -> None:
        reply = self.call("GET", f"/api/alerts?token={self.server.token}", token=False)
        self.assertEqual(reply.status, 403)

    def test_static_files_come_from_an_allowlist(self) -> None:
        for path in (
            "/../README.md",
            "/%2e%2e/README.md",
            "/app.js/../../README.md",
            "/static/index.html",
            "/index.html",
            "/app.js%00.html",
            "//etc/passwd",
            "/..%5cREADME.md",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.call("GET", path, token=False).status, 404)
        self.assertEqual(self.call("GET", "/app.js", token=False).status, 200)
        self.assertEqual(self.call("GET", "/app.css", token=False).status, 200)

    def test_unsupported_methods_are_refused(self) -> None:
        for method in ("PUT", "DELETE", "PATCH", "OPTIONS"):
            with self.subTest(method=method):
                self.assertEqual(self.call(method, "/api/alerts").status, 405)
        self.assertEqual(self.call("POST", "/", {}, token=False).status, 404)
        self.assertEqual(self.call("GET", "/api/unknown").status, 404)


class TestBodies(HubTestCase):
    def test_oversized_body_is_refused_before_it_is_read(self) -> None:
        status, _ = self.raw(
            [
                b"POST /api/uploads HTTP/1.1",
                f"Host: 127.0.0.1:{self.port}".encode(),
                f"X-Hub-Token: {self.server.token}".encode(),
                b"Content-Type: application/json",
                f"Content-Length: {MAX_BODY_BYTES + 1}".encode(),
            ]
        )
        self.assertEqual(status, 413)

    def test_body_at_the_limit_is_read_and_judged_on_content(self) -> None:
        padding = " " * (MAX_BODY_BYTES - 2)
        reply = self.call("POST", "/api/uploads", ("{" + padding + "}").encode())
        self.assertEqual(reply.status, 422)  # parsed fine, rejected by the schema

    def test_missing_or_bad_content_length_is_refused(self) -> None:
        base = [
            b"POST /api/uploads HTTP/1.1",
            f"Host: 127.0.0.1:{self.port}".encode(),
            f"X-Hub-Token: {self.server.token}".encode(),
            b"Content-Type: application/json",
        ]
        self.assertEqual(self.raw(base)[0], 411)
        self.assertEqual(self.raw([*base, b"Content-Length: -5"])[0], 411)
        self.assertEqual(self.raw([*base, b"Content-Length: 1e3"])[0], 411)

    def test_chunked_bodies_are_refused(self) -> None:
        status, _ = self.raw(
            [
                b"POST /api/uploads HTTP/1.1",
                f"Host: 127.0.0.1:{self.port}".encode(),
                f"X-Hub-Token: {self.server.token}".encode(),
                b"Content-Type: application/json",
                b"Transfer-Encoding: chunked",
            ]
        )
        self.assertEqual(status, 411)

    def test_content_type_must_be_json(self) -> None:
        for content_type in ("text/plain", "application/x-www-form-urlencoded", None):
            with self.subTest(content_type=content_type):
                reply = self.call("POST", "/api/uploads", b"{}", content_type=content_type)
                self.assertEqual(reply.status, 415)


class TestStaticSource(unittest.TestCase):
    """The page must never build HTML from server text."""

    def test_page_script_has_no_html_sinks(self) -> None:
        script = Path(STATIC_DIR / "app.js").read_text(encoding="utf-8")
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            self.assertNotIn(sink, script)

    def test_page_has_no_inline_script_or_handlers(self) -> None:
        html = Path(STATIC_DIR / "index.html").read_text(encoding="utf-8")
        self.assertNotRegex(html, r"<script(?![^>]*\bsrc=)")
        self.assertNotRegex(html, r"\son[a-z]+\s*=")

    def test_a_meta_token_is_the_only_secret_in_the_page(self) -> None:
        html = Path(STATIC_DIR / "index.html").read_text(encoding="utf-8")
        self.assertEqual(html.count("__HUB_TOKEN__"), 1)
        self.assertEqual(json.dumps(html).count("__HUB_TOKEN__"), 1)


if __name__ == "__main__":
    unittest.main()
