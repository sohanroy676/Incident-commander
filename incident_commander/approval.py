"""Time-boxed human approval on a real clock, with escalation (PHASE5 7.8, PHASE4 9.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .clocks import ControlClock
from .types import ApprovalToken

PENDING, ACKNOWLEDGED, ESCALATED = "PENDING", "ACKNOWLEDGED", "ESCALATED"
APPROVE, DENY = "approve", "deny"


class Responder(Protocol):
    def poll(self, target: str, elapsed_s: float) -> str | None:
        """The target's answer ("approve" | "deny") once given, else None."""
        ...


class ScriptedResponder:
    """Simulated humans: {person: (delay_s, response)}; a None delay never answers."""

    def __init__(self, script: dict[str, tuple[float | None, str]]) -> None:
        self._script = dict(script)

    def poll(self, target: str, elapsed_s: float) -> str | None:
        delay, response = self._script.get(target, (None, ""))
        if delay is None or elapsed_s < delay:
            return None
        return response


@dataclass(frozen=True)
class PageCheck:
    escalated: bool
    reason: str | None = None
    from_: str | None = None
    to: str | None = None


class Page:
    """One page to one person with its own deadline on the control clock."""

    def __init__(
        self,
        page_id: str,
        target: str,
        issued_at: float,
        deadline_s: float,
        escalate_to: str | None = None,
    ) -> None:
        self.page_id = page_id
        self.target = target
        self.issued_at = issued_at
        self.deadline_s = deadline_s
        self.escalate_to = escalate_to
        self.state = PENDING

    def acknowledge(self) -> None:
        if self.state == PENDING:
            self.state = ACKNOWLEDGED

    def check(self, now: float) -> PageCheck:
        if self.state == ACKNOWLEDGED:
            return PageCheck(False, "already resolved")
        if self.state == PENDING and now - self.issued_at >= self.deadline_s:
            self.state = ESCALATED
        if self.state == ESCALATED:
            return PageCheck(True, None, self.target, self.escalate_to)
        return PageCheck(False)


@dataclass(frozen=True)
class ApprovalOutcome:
    status: str  # "approved" | "denied" | "expired"
    token: ApprovalToken | None
    escalated: bool
    pages: tuple[Page, ...]


class ApprovalGate:
    def __init__(
        self,
        clock: ControlClock,
        responder: Responder,
        primary: str,
        secondary: str,
        deadline_s: float,
        tick_s: float = 0.02,
    ) -> None:
        if deadline_s <= 0 or tick_s <= 0:
            raise ValueError("deadline_s and tick_s must be positive")
        if primary == secondary:
            raise ValueError("primary and secondary must be different people")
        self._clock = clock
        self._responder = responder
        self._primary = primary
        self._secondary = secondary
        self._deadline_s = deadline_s
        self._tick_s = tick_s

    def new_page(self, target: str, escalate_to: str | None = None) -> Page:
        return Page(f"page-{target}", target, self._clock.now(), self._deadline_s, escalate_to)

    def _wait(self, page: Page) -> str | None:
        """Poll until the page is answered (the reply) or its deadline passes (None)."""
        while True:
            elapsed = self._clock.now() - page.issued_at
            # A late tick must not turn an in-time answer into a miss.
            answer = self._responder.poll(page.target, min(elapsed, page.deadline_s))
            if answer is not None:
                page.acknowledge()
                return answer
            if page.check(self._clock.now()).escalated:
                return None
            self._clock.sleep(self._tick_s)

    def request(self, action: str, service: str) -> ApprovalOutcome:
        first = self.new_page(self._primary, self._secondary)
        pages = [first]
        answer = self._wait(first)
        escalated = answer is None
        approver = self._primary
        if escalated:
            second = self.new_page(self._secondary)
            pages.append(second)
            answer = self._wait(second)
            approver = self._secondary
        if answer is None:
            return ApprovalOutcome("expired", None, escalated, tuple(pages))
        if answer != APPROVE:
            return ApprovalOutcome("denied", None, escalated, tuple(pages))
        token = ApprovalToken(action, service, approver, self._clock.now())
        return ApprovalOutcome("approved", token, escalated, tuple(pages))
