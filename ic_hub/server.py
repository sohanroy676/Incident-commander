"""The hub's HTTP server: stdlib `http.server`, bound to 127.0.0.1, JSON API plus three static files.

Checks on every request: Host header (DNS rebinding), Origin when present, a per-start token on
/api/*, a size cap and Content-Type on bodies. Static files come from a fixed allowlist, never a
path built from the request. Every response carries a strict CSP.
"""

from __future__ import annotations

import dataclasses
import hmac
import json
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from incident_commander.postmortem import render

from .runner import ClientFactory, Conflict, Hub, NotFound, Run, TooManyRuns
from .schema import (
    MAX_BODY_BYTES,
    ValidationError,
    parse_diff_request,
    parse_json,
    validate_evaluate_request,
    validate_explain_request,
    validate_run_request,
)
from .store import Store

HOST = "127.0.0.1"
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
}
TOKEN_HEADER = "X-Hub-Token"
TOKEN_PLACEHOLDER = "__HUB_TOKEN__"
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
_RUN_ID = re.compile(r"^[0-9a-f]{16}$")
_HISTORY_PATH = re.compile(r"^/api/history/([0-9a-f]{16})$")
_RUN_PATH = re.compile(r"^/api/runs/([0-9a-f]{16})(?:/([a-z.]+))?$")
MAX_STREAMS = 4  # open approval streams at once; each holds one thread
STREAM_MAX_S = 60.0  # a stream ends after this long and the page reconnects
STREAM_TICK_S = 0.1
STREAM_HEARTBEAT_S = 5.0


def _sse(data: str, event: str | None = None) -> bytes:
    head = f"event: {event}\n" if event else ""
    return f"{head}data: {data}\n\n".encode()


class HubServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        port: int = 0,
        client_factory: ClientFactory | None = None,
        store: Store | None = None,
    ) -> None:
        super().__init__((HOST, port), _Handler)
        self.hub = Hub(client_factory, store) if client_factory else Hub(store=store)
        self.token = secrets.token_urlsafe(24)
        self.allowed_hosts = frozenset({f"127.0.0.1:{self.port}", f"localhost:{self.port}"})
        self.allowed_origins = frozenset(f"http://{h}" for h in self.allowed_hosts)
        self._streams = 0
        self._streams_lock = threading.Lock()

    def open_stream(self) -> bool:
        with self._streams_lock:
            if self._streams >= MAX_STREAMS:
                return False
            self._streams += 1
            return True

    def close_stream(self) -> None:
        with self._streams_lock:
            self._streams -= 1

    @property
    def port(self) -> int:
        return self.server_address[1]


class _Handler(BaseHTTPRequestHandler):
    server: HubServer
    server_version = "ic_hub"
    sys_version = ""
    timeout = 10  # a stalled client cannot hold a thread

    def log_message(self, format: str, *args: object) -> None:
        return  # quiet: nothing in a URL or header is worth logging

    # -- plumbing -----------------------------------------------------------

    def _send(
        self, status: int, body: bytes, content_type: str, extra: dict[str, str] | None = None
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _security_headers(self) -> None:
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")

    def _stream(self, run: Run) -> None:
        """Server-sent events with the run's status and pending approval, until it ends.

        Same guards as every /api route (the page reads it with fetch so the token header applies).
        Bounded: a cap on open streams, a lifetime, and a write that fails ends the thread.
        """
        if not self.server.open_stream():
            raise TooManyRuns("too many open streams")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Connection", "close")
            self._security_headers()
            self.end_headers()
            self.close_connection = True
            deadline = time.monotonic() + STREAM_MAX_S
            last = None
            last_sent = time.monotonic()
            while True:
                view = run.stream_view()
                text = json.dumps(view, allow_nan=False)
                now = time.monotonic()
                if text != last:
                    self.wfile.write(_sse(text))
                    last, last_sent = text, now
                elif now - last_sent >= STREAM_HEARTBEAT_S:
                    self.wfile.write(b": ping\n\n")
                    last_sent = now
                if view["status"] != "running":
                    self.wfile.write(_sse('{"reason": "finished"}', "end"))
                    return
                if now >= deadline:
                    self.wfile.write(_sse('{"reason": "timeout"}', "end"))
                    return
                time.sleep(STREAM_TICK_S)
        except OSError:
            return  # the client went away or stopped reading
        finally:
            self.server.close_stream()

    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, allow_nan=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, message: str, fields: dict[str, str] | None = None) -> None:
        self._json(status, {"error": message, "fields": fields or {}})

    def _guard(self, api: bool) -> bool:
        """Host, Origin and token checks. Sends the error and returns False when one fails."""
        if self.headers.get("Host") not in self.server.allowed_hosts:
            self._error(403, "bad Host header")
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in self.server.allowed_origins:
            self._error(403, "bad Origin header")
            return False
        if api:
            token = self.headers.get(TOKEN_HEADER, "")
            if not hmac.compare_digest(token.encode("utf-8"), self.server.token.encode("utf-8")):
                self._error(403, "missing or wrong token")
                return False
        return True

    def _body(self) -> object | None:
        """The parsed JSON body, or None after sending an error."""
        if self.headers.get("Transfer-Encoding") is not None:
            self._error(411, "Content-Length is required; chunked bodies are not accepted")
            return None
        length = self.headers.get("Content-Length")
        if length is None or not length.isascii() or not length.isdigit():
            self._error(411, "Content-Length is required")
            return None
        if int(length) > MAX_BODY_BYTES:
            self._error(413, f"body larger than {MAX_BODY_BYTES} bytes")
            self.close_connection = True
            return None
        if self.headers.get_content_type() != "application/json":
            self._error(415, "Content-Type must be application/json")
            return None
        data = self.rfile.read(int(length))
        try:
            return parse_json(data)
        except ValidationError as exc:
            self._error(400, "invalid JSON", exc.fields)
            return None

    def _dispatch(self, method: str) -> None:
        path = urlsplit(self.path).path
        api = path.startswith("/api/")
        if not self._guard(api):
            return
        try:
            if api:
                self._api(method, path)
            elif method == "GET" and path in STATIC_FILES:
                self._static(path)
            else:
                self._error(404, "not found")
        except ValidationError as exc:
            self._error(422, "validation failed", exc.fields)
        except NotFound as exc:
            self._error(404, str(exc))
        except TooManyRuns as exc:
            self._error(429, str(exc))
        except Conflict as exc:
            self._error(409, str(exc))

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def _method_not_allowed(self) -> None:
        self._error(405, "method not allowed")

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _method_not_allowed

    def _static(self, path: str) -> None:
        name, content_type = STATIC_FILES[path]
        body = (STATIC_DIR / name).read_bytes()
        if name == "index.html":
            body = body.replace(TOKEN_PLACEHOLDER.encode(), self.server.token.encode())
        self._send(200, body, content_type)

    # -- API ----------------------------------------------------------------

    def _api(self, method: str, path: str) -> None:
        hub = self.server.hub
        if method == "GET" and path == "/api/alerts":
            self._json(200, {"alerts": hub.alert_rows()})
        elif method == "POST" and path == "/api/uploads":
            body = self._body()
            if body is None:
                return
            upload = hub.add_upload(body)
            self._json(201, {"alert_id": upload.alert.alert_id, "service": upload.service.name})
        elif method == "POST" and path in ("/api/runs", "/api/playground"):
            body = self._body()
            if body is None:
                return
            playground = path == "/api/playground"
            req = validate_run_request(body, hub.known_alerts(), hub.has_service)
            if playground and not req["text"]:
                raise ValidationError({"text": "is required"})
            self._json(202, {"run_id": hub.start(req, playground=playground).run_id})
        elif method == "POST" and path == "/api/intake/alertmanager":
            body = self._body()
            if body is None:
                return
            self._json(201, {"alerts": hub.add_intake(body)})
        elif method == "GET" and path == "/api/metrics":
            self._json(200, hub.metrics())
        elif method == "GET" and path == "/api/history":
            self._json(200, hub.history())
        elif method == "GET" and path == "/api/audit":
            self._json(200, hub.audit())
        elif method == "GET" and _HISTORY_PATH.match(path):
            self._json(200, hub.history_get(_HISTORY_PATH.match(path).group(1)))  # type: ignore[union-attr]
        elif method == "POST" and path == "/api/explain":
            body = self._body()
            if body is None:
                return
            req = validate_explain_request(body, hub.known_alerts())
            self._json(202, {"run_id": hub.start_explain(req).run_id})
        elif method == "POST" and path == "/api/evaluate":
            body = self._body()
            if body is None:
                return
            self._json(202, {"run_id": hub.start_evaluate(validate_evaluate_request(body)).run_id})
        elif method == "POST" and path == "/api/diff":
            body = self._body()
            if body is None:
                return
            ids = parse_diff_request(body)
            self._json(200, hub.diff(*ids))
        else:
            self._run_route(method, path)

    def _run_route(self, method: str, path: str) -> None:
        hub = self.server.hub
        match = _RUN_PATH.match(path)
        if match is None:
            self._error(404, "not found")
            return
        run_id, action = match.group(1), match.group(2)
        if method == "GET" and action is None:
            self._json(200, hub.get(run_id).view())
        elif method == "GET" and action == "postmortem.md":
            text = render(hub.postmortem(run_id))  # type: ignore[arg-type]
            self._send(200, text.encode("utf-8"), "text/markdown; charset=utf-8")
        elif method == "GET" and action == "postmortem.json":
            self._json(200, dataclasses.asdict(hub.postmortem(run_id)))  # type: ignore[call-overload]
        elif method == "POST" and action == "approval":
            body = self._body()
            if not isinstance(body, dict):
                if body is not None:
                    self._error(400, "body must be an object")
                return
            outcome = hub.approve(run_id, body.get("nonce"), body.get("decision"))
            self._json(200 if outcome == "accepted" else 409, {"outcome": outcome})
        elif method == "GET" and action == "stream":
            self._stream(hub.get(run_id))
        elif method == "GET" and action == "similar":
            self._json(200, hub.similar(run_id))
        elif method == "POST" and action == "publish":
            self._json(200, hub.publish(run_id))
        else:
            self._error(404, "not found")


def make_server(
    port: int = 0,
    client_factory: ClientFactory | None = None,
    store: Store | None = None,
) -> HubServer:
    return HubServer(port, client_factory, store)
