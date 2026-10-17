"""Scribe: a pure postmortem draft from the trace; publish() is the only side effect (PHASE5 7.11)."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .config import PUBLISH_RECIPIENTS
from .types import Observation, PostmortemDraft, Runbook, TraceEvent


class Notifier(Protocol):
    def send(self, recipient: str, subject: str, body: str) -> None: ...


class OutboxNotifier:
    """In-memory outbox: the demo's notifier and the tests' spy."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, recipient: str, subject: str, body: str) -> None:
        self.sent.append((recipient, subject, body))


def _kv(event: TraceEvent) -> dict[str, object]:
    return dict(event.fields)


def _fmt(event: TraceEvent) -> str:
    return " ".join(f"{k}={v}" for k, v in event.fields)


def _of(trace: tuple[TraceEvent, ...], *kinds: str) -> list[TraceEvent]:
    return [e for e in trace if e.kind in kinds]


def _one(trace: tuple[TraceEvent, ...], kind: str) -> dict[str, object]:
    found = _of(trace, kind)
    return _kv(found[-1]) if found else {}


def build_draft(
    case_trace: tuple[TraceEvent, ...], logs: Observation | None, runbook: Runbook | None
) -> PostmortemDraft:
    """Pure: reads the trace, returns data. No I/O, no notifier. Log text is quoted, never used."""
    alert = _one(case_trace, "ALERT_RECEIVED")
    verdict = _one(case_trace, "VERDICT")
    classify = _one(case_trace, "CLASSIFY")
    execute = _of(case_trace, "EXECUTE")
    verify = _one(case_trace, "VERIFY")
    handoff = _one(case_trace, "HANDOFF")

    matched = verdict.get("verdict") == "matched"
    cause = f"matched runbook {verdict.get('runbook')}" if matched else "no confident match"
    if verify:
        outcome = f"verification {verify.get('status')}"
    elif handoff:
        outcome = f"handed off ({handoff.get('reason')})"
    else:
        outcome = "no outcome recorded"
    remediation = "no remediation executed"
    if execute:
        first = _kv(execute[0])
        remediation = f"{first.get('action')} {first.get('status')} id={first.get('execution_id')}"

    evidence = tuple(_fmt(e) for e in _of(case_trace, "ROUND", "HYPOTHESES"))
    approvals = tuple(_fmt(e) for e in _of(case_trace, "PAGE", "ESCALATE", "APPROVAL"))
    excerpts = (
        tuple(f"[{t}] {text}" for t, text in logs.data) if logs and logs.status == "ok" else ()
    )
    follow_ups = runbook.follow_ups if runbook else ()
    return PostmortemDraft(
        summary=f"{alert.get('alert')} on {alert.get('service')}: {cause}; {outcome}",
        impact=f"{alert.get('metric')} alert on {alert.get('service')} (label {alert.get('severity_label')})",
        detection=f"alert fired: {alert.get('summary')}",
        evidence=evidence,
        remediation=remediation + (f" (tier {classify.get('tier')})" if classify else ""),
        approval_history=approvals,
        verification=_fmt_verification(verify),
        timeline=tuple(f"#{e.seq} {e.kind} {_fmt(e)}".rstrip() for e in case_trace),
        untrusted_log_excerpts=excerpts,
        follow_ups=follow_ups,
    )


def _fmt_verification(verify: dict[str, object]) -> str:
    if not verify:
        return "not verified"
    return " ".join(f"{k}={v}" for k, v in verify.items())


def publish(
    draft: PostmortemDraft,
    notifier: Notifier,
    recipients: tuple[str, ...] = PUBLISH_RECIPIENTS,
) -> PostmortemDraft:
    """The only function that sends. A draft that is already published sends nothing."""
    if draft.published:
        return draft
    for recipient in recipients:
        notifier.send(recipient, f"Postmortem: {draft.summary}", render(draft))
    return replace(draft, published=True, notified=list(recipients))


def render(draft: PostmortemDraft) -> str:
    """Plain-text body; log excerpts sit only in their labelled, unverified section."""
    parts = [
        ("Summary", (draft.summary,)),
        ("Impact", (draft.impact,)),
        ("Detection", (draft.detection,)),
        ("Evidence and verdict", draft.evidence),
        ("Remediation", (draft.remediation,)),
        ("Approval and escalation", draft.approval_history),
        ("Verification", (draft.verification,)),
        ("Timeline", draft.timeline),
        ("Follow-ups", draft.follow_ups),
        ("Untrusted log excerpts (unverified)", draft.untrusted_log_excerpts),
    ]
    return "\n".join(f"## {title}\n" + "\n".join(f"- {x}" for x in items) for title, items in parts)
