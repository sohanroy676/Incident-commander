"""Commander: the only orchestrator, an explicit state machine with an append-only trace (PHASE5 7.12)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from .approval import ApprovalGate, ApprovalOutcome, Responder
from .blast_radius import classify_remediation
from .clocks import ControlClock, DataClock
from .config import (
    APPROVAL_DEADLINE_S,
    APPROVAL_TICK_S,
    DATA_CLOCK_START_OFFSET_S,
    LOOKBACK_S,
    PRIMARY_ONCALL,
    SECONDARY_ONCALL,
)
from .executor import ExecutionResult, Executor
from .fixtures.runbooks import RUNBOOKS
from .fixtures.services import REMEDIATION_OUTCOMES
from .investigator import InvestigationResult, ToolBox, investigate
from .postmortem import Notifier, build_draft, publish
from .retrieval import Ranker
from .tools import get_logs
from .types import (
    Alert,
    ApprovalToken,
    Candidate,
    Classification,
    Execution,
    Observation,
    PostmortemDraft,
    Runbook,
    TraceEvent,
    Verification,
)
from .verifier import verify
from .world import SimWorld

(
    RECEIVED,
    INVESTIGATING,
    MATCHED,
    NO_MATCH,
    CLASSIFIED,
    AWAITING_APPROVAL,
    EXECUTING,
    VERIFYING,
    RESOLVED,
    REOPENED,
    HANDOFF,
    DRAFTED,
    PUBLISHED,
) = STATES = (
    "RECEIVED",
    "INVESTIGATING",
    "MATCHED",
    "NO_MATCH",
    "CLASSIFIED",
    "AWAITING_APPROVAL",
    "EXECUTING",
    "VERIFYING",
    "RESOLVED",
    "REOPENED",
    "HANDOFF",
    "DRAFTED",
    "PUBLISHED",
)

TRANSITIONS: dict[str, frozenset[str]] = {
    RECEIVED: frozenset({INVESTIGATING}),
    INVESTIGATING: frozenset({MATCHED, NO_MATCH}),
    NO_MATCH: frozenset({HANDOFF}),
    MATCHED: frozenset({CLASSIFIED}),
    CLASSIFIED: frozenset({EXECUTING, AWAITING_APPROVAL}),
    AWAITING_APPROVAL: frozenset({EXECUTING, HANDOFF}),
    EXECUTING: frozenset({VERIFYING, HANDOFF}),
    VERIFYING: frozenset({RESOLVED, REOPENED}),
    REOPENED: frozenset({HANDOFF}),
    RESOLVED: frozenset({DRAFTED}),
    HANDOFF: frozenset({DRAFTED}),
    DRAFTED: frozenset({PUBLISHED}),
    PUBLISHED: frozenset(),
}


class IllegalTransition(Exception):
    """A state change not in TRANSITIONS."""


class Trace:
    """Append-only event log. Only `emit` adds; `events` is a read-only snapshot.

    `on_event` is an optional observer called with each event after it is appended. It cannot change
    or remove an event; an exception it raises propagates to the caller.
    """

    def __init__(
        self,
        data_clock: DataClock,
        control_clock: ControlClock,
        on_event: Callable[[TraceEvent], None] | None = None,
    ) -> None:
        self._data = data_clock
        self._control = control_clock
        self._on_event = on_event
        self._events: list[TraceEvent] = []

    def emit(self, kind: str, **fields: object) -> None:
        event = TraceEvent(
            len(self._events) + 1,
            kind,
            self._data.now(),
            self._control.elapsed(),
            tuple(fields.items()),
        )
        self._events.append(event)
        if self._on_event is not None:
            self._on_event(event)

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return tuple(self._events)


@dataclass
class Case:
    """Working memory for one incident. Written only by the Commander."""

    case_id: str
    alert: Alert
    trace: Trace
    state: str = RECEIVED
    candidates: list[Candidate] = field(default_factory=list)
    investigation: InvestigationResult | None = None
    classification: Classification | None = None
    approval: ApprovalOutcome | None = None
    execution: ExecutionResult | None = None
    retry: ExecutionResult | None = None
    verification: Verification | None = None
    handoff_reason: str | None = None
    logs: Observation | None = None
    draft: PostmortemDraft | None = None
    executor: Executor | None = None
    token: ApprovalToken | None = None
    action: str | None = None


class Commander:
    def __init__(
        self,
        world: SimWorld,
        ranker: Ranker,
        responder: Responder,
        *,
        deadline_s: float = APPROVAL_DEADLINE_S,
        tick_s: float = APPROVAL_TICK_S,
        primary: str = PRIMARY_ONCALL,
        secondary: str = SECONDARY_ONCALL,
        control_clock: ControlClock | None = None,
    ) -> None:
        self._world = world
        self._ranker = ranker
        self._control = control_clock or ControlClock()
        self._gate = ApprovalGate(self._control, responder, primary, secondary, deadline_s, tick_s)
        self._primary = primary
        self._secondary = secondary
        self._deadline_s = deadline_s

    def _move(self, case: Case, to: str) -> None:
        if to not in TRANSITIONS.get(case.state, frozenset()):
            raise IllegalTransition(f"{case.state} -> {to}")
        case.trace.emit("STATE", **{"from": case.state, "to": to})
        case.state = to

    def _handoff(self, case: Case, reason: str) -> None:
        case.handoff_reason = reason
        self._move(case, HANDOFF)
        case.trace.emit("HANDOFF", alert=case.alert.alert_id, reason=reason)

    def run(
        self,
        alert: Alert,
        *,
        fix_outcome: str = "success",
        runbooks: Mapping[str, Runbook] | None = None,
        on_event: Callable[[TraceEvent], None] | None = None,
    ) -> Case:
        if fix_outcome not in REMEDIATION_OUTCOMES:
            raise ValueError(f"unknown fix_outcome: {fix_outcome}")
        books = RUNBOOKS if runbooks is None else runbooks
        clock = DataClock(alert.fired_at + DATA_CLOCK_START_OFFSET_S)
        case = Case(alert.alert_id, alert, Trace(clock, self._control, on_event))
        trace = case.trace
        trace.emit(
            "ALERT_RECEIVED",
            alert=alert.alert_id,
            service=alert.service,
            severity_label=alert.severity,
            metric=alert.metric,
            summary=alert.summary,
        )

        case.candidates = self._ranker.rank(alert.summary)
        trace.emit(
            "RANK",
            alert=alert.alert_id,
            ranker=self._ranker.label,
            order=",".join(c.runbook_id for c in case.candidates),
        )
        self._move(case, INVESTIGATING)
        case.investigation = investigate(
            alert, self._ranker, ToolBox(self._world, clock), trace=trace, runbooks=books
        )
        verdict = case.investigation.verdict
        trace.emit(
            "VERDICT",
            verdict=verdict.kind,
            runbook=verdict.runbook_id or "none",
            rounds=verdict.rounds,
            reason=verdict.reason,
        )
        if verdict.runbook_id is None:
            self._move(case, NO_MATCH)
            self._handoff(case, verdict.kind)
        else:
            self._move(case, MATCHED)
            self._remediate(case, books[verdict.runbook_id].action, clock, fix_outcome)
        self._draft(case, clock, books)
        return case

    def _remediate(self, case: Case, action: str, clock: DataClock, fix_outcome: str) -> None:
        alert, trace = case.alert, case.trace
        case.action = action
        case.classification = classify_remediation(action)  # the action alone: never severity
        self._move(case, CLASSIFIED)
        trace.emit(
            "CLASSIFY",
            action=action,
            tier=case.classification.tier,
            requires_approval=case.classification.requires_approval,
        )
        if case.classification.requires_approval:
            self._move(case, AWAITING_APPROVAL)
            trace.emit("PAGE", target=self._primary, deadline_s=self._deadline_s)
            outcome = self._gate.request(action, alert.service)
            case.approval = outcome
            if outcome.escalated:
                trace.emit("ESCALATE", **{"from": self._primary, "to": self._secondary})
            trace.emit(
                "APPROVAL",
                alert=alert.alert_id,
                status=outcome.status,
                escalated=outcome.escalated,
                approved_by=outcome.token.approved_by if outcome.token else "none",
            )
            if outcome.token is None:
                self._handoff(case, f"approval_{outcome.status}")
                return
            case.token = outcome.token
        self._move(case, EXECUTING)
        case.executor = Executor(self._world, clock, fix_outcome)
        result = case.executor.execute(action, alert.service, case.case_id, case.token)
        case.execution = result
        trace.emit(
            "EXECUTE",
            alert=alert.alert_id,
            action=action,
            status=result.status,
            execution_id=result.execution_id,
        )
        if result.status == "failed":
            self._handoff(case, "execution_failed")
            return
        self._move(case, VERIFYING)
        execution = Execution(
            result.execution_id or "",
            (case.case_id, action, alert.service),
            action,
            alert.service,
            clock.now(),
        )
        verification = verify(self._world, clock, alert.service, alert.metric, execution)
        case.verification = verification
        trace.emit(
            "VERIFY",
            alert=alert.alert_id,
            status=verification.status,
            verified=verification.verified,
            baseline_ms=verification.baseline,
            observed_ms=verification.observed,
            reason=verification.reason,
        )
        if verification.verified:
            self._move(case, RESOLVED)
        else:
            self._move(case, REOPENED)
            self._handoff(case, "reopened")

    def retry_execution(self, case: Case) -> ExecutionResult:
        """Repeat the same execution: the ledger returns `already_executed` with the same id."""
        if case.executor is None or case.action is None:
            raise IllegalTransition("no execution to retry")
        result = case.executor.execute(case.action, case.alert.service, case.case_id, case.token)
        case.retry = result
        case.trace.emit(
            "EXECUTE",
            alert=case.alert.alert_id,
            action=case.action,
            status=result.status,
            execution_id=result.execution_id,
        )
        return result

    def _draft(self, case: Case, clock: DataClock, books: Mapping[str, Runbook]) -> None:
        alert = case.alert
        start, end = alert.fired_at - LOOKBACK_S, alert.fired_at
        case.logs = get_logs(self._world, clock, alert.service, start, end)  # Scribe only
        verdict = case.investigation.verdict if case.investigation else None
        runbook = books.get(verdict.runbook_id) if verdict and verdict.runbook_id else None
        draft = build_draft(case.trace.events, case.logs, runbook)
        self._move(case, DRAFTED)
        case.draft = draft
        case.trace.emit("DRAFT", alert=alert.alert_id, notified=draft.notified, published=False)

    def publish(self, case: Case, notifier: Notifier) -> PostmortemDraft:
        """The explicit, human-triggered side effect: DRAFTED -> PUBLISHED."""
        if case.draft is None:
            raise IllegalTransition(f"{case.state} has no draft to publish")
        published = publish(case.draft, notifier)
        self._move(case, PUBLISHED)
        case.draft = published
        case.trace.emit(
            "PUBLISH", alert=case.alert.alert_id, published=True, notified=published.notified
        )
        return published
