"""Shared helpers: a hub server on an ephemeral port and a small http.client wrapper."""

from __future__ import annotations

import http.client
import json
import threading
import time
import unittest
from pathlib import Path

from ic_hub.server import HubServer, make_server

ROOT = Path(__file__).resolve().parent.parent
RUN_TXT = ROOT / "traces" / "run.txt"


def saved_decisions() -> list[str]:
    return [
        line.strip()
        for line in RUN_TXT.read_text(encoding="utf-8").splitlines()
        if line.startswith("DECISION ")
    ]


class Reply:
    def __init__(self, status: int, headers: http.client.HTTPMessage, body: bytes) -> None:
        self.status = status
        self.headers = headers
        self.body = body

    def json(self) -> dict:
        return json.loads(self.body)


class HubTestCase(unittest.TestCase):
    """A fresh server per test, so uploads and runs never leak between tests."""

    server: HubServer

    def setUp(self) -> None:
        self.server = make_server(0)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self._stop, thread)
        self.port = self.server.port

    def _stop(self, thread: threading.Thread) -> None:
        self.server.shutdown()
        self.server.server_close()
        thread.join(timeout=5)

    def call(
        self,
        method: str,
        path: str,
        body: object | bytes | None = None,
        *,
        headers: dict[str, str] | None = None,
        token: bool = True,
        content_type: str | None = "application/json",
    ) -> Reply:
        hdrs = dict(headers or {})
        if token:
            hdrs.setdefault("X-Hub-Token", self.server.token)
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            if content_type:
                hdrs.setdefault("Content-Type", content_type)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request(method, path, body=data, headers=hdrs)
            resp = conn.getresponse()
            return Reply(resp.status, resp.headers, resp.read())
        finally:
            conn.close()

    def raw(self, lines: list[bytes]) -> tuple[int, bytes]:
        """Send hand-written request bytes (for framing http.client would not let us break)."""
        import socket

        with socket.create_connection(("127.0.0.1", self.port), timeout=15) as sock:
            sock.sendall(b"\r\n".join(lines) + b"\r\n\r\n")
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
        status = int(data.split(b" ", 2)[1])
        return status, data

    def start_run(self, alert_id: str, **extra: object) -> str:
        reply = self.call("POST", "/api/runs", {"alert_id": alert_id, **extra})
        self.assertEqual(reply.status, 202, reply.body)
        return reply.json()["run_id"]

    def wait_for(self, run_id: str, status: str = "done", timeout: float = 30.0) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            view = self.call("GET", f"/api/runs/{run_id}").json()
            if view["status"] == status:
                return view
            if view["status"] == "error" or time.monotonic() > deadline:
                self.fail(f"run {run_id} did not reach {status}: {view}")
            time.sleep(0.02)

    def run_to_end(self, alert_id: str, **extra: object) -> dict:
        return self.wait_for(self.start_run(alert_id, **extra))

    def wait_pending(self, run_id: str, target: str | None = None, timeout: float = 30.0) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            view = self.call("GET", f"/api/runs/{run_id}").json()
            pending = view["pending"]
            if pending is not None and (target is None or pending["target"] == target):
                return pending
            if view["status"] != "running" or time.monotonic() > deadline:
                self.fail(f"no pending page for {target}: {view}")
            time.sleep(0.01)
