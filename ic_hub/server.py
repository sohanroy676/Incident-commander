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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from incident_commander.postmortem import render

from .runner import Conflict, Hub, NotFound, TooManyRuns
from .schema import MAX_BODY_BYTES, ValidationError, parse_json, validate_run_request

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
_RUN_PATH = re.compile(r"^/api/runs/([0-9a-f]{16})(?:/([a-z.]+))?$")


class HubServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int = 0) -> None:
        super().__init__((HOST, port), _Handler)
        self.hub = Hub()
        self.token = secrets.token_urlsafe(24)
        self.allowed_hosts = frozenset({f"127.0.0.1:{self.port}", f"localhost:{self.port}"})
        self.allowed_origins = frozenset(f"http://{h}" for h in self.allowed_hosts)

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
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

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
        elif method == "POST" and action == "publish":
            self._json(200, hub.publish(run_id))
        else:
            self._error(404, "not found")


def make_server(port: int = 0) -> HubServer:
    return HubServer(port)
