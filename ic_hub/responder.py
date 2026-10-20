"""WebResponder: a human answering through the page, bound to one pending page by a nonce.

The approval gate polls `poll(target, elapsed_s)` from the run thread; the HTTP thread calls
`submit`. The gate still owns the deadline and the escalation, so the hub adds no decision.
The approver identity (priya, devon) is simulated, not authenticated.
"""

from __future__ import annotations

import hmac
import secrets
import threading
import time
from dataclasses import dataclass

APPROVE, DENY = "approve", "deny"


@dataclass
class _Pending:
    target: str
    nonce: str
    opened: float
    answer: str | None = None


class WebResponder:
    def __init__(self, deadline_s: float) -> None:
        self._deadline_s = deadline_s
        self._lock = threading.Lock()
        self._pending: _Pending | None = None

    def poll(self, target: str, elapsed_s: float) -> str | None:
        with self._lock:
            pending = self._pending
            if pending is None or pending.target != target:
                self._pending = _Pending(target, secrets.token_hex(16), time.monotonic())
                return None
            if pending.answer is not None:
                self._pending = None  # consumed: the nonce cannot be used again
                return pending.answer
            return None

    def pending(self) -> dict[str, object] | None:
        """What the approval card shows: who was paged, the nonce, seconds left on this page."""
        with self._lock:
            p = self._pending
            if p is None or p.answer is not None:
                return None
            remaining = max(0.0, self._deadline_s - (time.monotonic() - p.opened))
            return {
                "target": p.target,
                "nonce": p.nonce,
                "deadline_s": self._deadline_s,
                "remaining_s": round(remaining, 3),
            }

    def submit(self, nonce: object, decision: object) -> str:
        """ "accepted", or why not: "bad_decision", "stale" (no such pending page), "expired"."""
        if decision not in (APPROVE, DENY):
            return "bad_decision"
        with self._lock:
            p = self._pending
            if (
                p is None
                or p.answer is not None
                or not isinstance(nonce, str)
                or not hmac.compare_digest(nonce, p.nonce)
            ):
                return "stale"
            if time.monotonic() - p.opened > self._deadline_s:
                return "expired"
            p.answer = str(decision)
            return "accepted"

    def close(self) -> None:
        with self._lock:
            self._pending = None
