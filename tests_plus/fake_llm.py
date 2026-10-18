"""A fake OpenAI-compatible server on localhost for the extension tests (stdlib http.server)."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def chat_body(content: str, model: str = "fake-model") -> str:
    return json.dumps(
        {"model": model, "choices": [{"message": {"role": "assistant", "content": content}}]}
    )


class FakeLLM:
    """Replays `replies` in order (the last repeats). A reply is (status, body, delay_s)."""

    def __init__(self, replies: list[tuple[int, str, float]]):
        self.replies = replies
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                index = min(len(outer.requests), len(outer.replies) - 1)
                outer.requests.append(
                    {"path": self.path, "headers": dict(self.headers), "body": raw.decode("utf-8")}
                )
                status, body, delay = outer.replies[index]
                time.sleep(delay)
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body.encode("utf-8"))
                except OSError:
                    pass  # the client gave up (timeout test)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()


def unused_url() -> str:
    """A localhost URL with nothing listening (the port was just released)."""
    probe = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = probe.server_address[1]
    probe.server_close()
    return f"http://127.0.0.1:{port}/v1"
