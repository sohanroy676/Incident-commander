"""Output contract helpers: headers, trace/decision lines, the M1 table (PHASE5 6)."""

from __future__ import annotations

from .clocks import ControlClock
from .executor import ExecutionResult
from .predicates import recent_median
from .types import (
    Alert,
    Classification,
    Observation,
    PostmortemDraft,
    TraceEvent,
    Verdict,
    Verification,
)

M1_TITLE = "SIGNAL INGESTION"
M2_TITLE = "RUNBOOK GROUNDING"
M3_TITLE = "INVESTIGATION"
M4_TITLE = "BLAST-RADIUS CLASSIFICATION"
M5_TITLE = "TIME-BOXED APPROVAL"
M6_TITLE = "VERIFIED RESOLUTION"
M7_TITLE = "POSTMORTEM DRAFT"
M8_TITLE = "EVALUATION"
EXECUTION_HEADER = "== EXECUTION (idempotency demo) =="


def header(n: int, title: str) -> str:
    return f"== M{n} {title} =="


def fmt(value: object) -> str:
    """key=value formatting: bools as True/False, spaced strings double-quoted."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.10g}"
    if isinstance(value, str) and (" " in value or value == ""):
        return f'"{value}"'
    return str(value)


def kv(**fields: object) -> str:
    return " ".join(f"{k}={fmt(v)}" for k, v in fields.items())


def decision(kind: str, **fields: object) -> str:
    """A DECISION line: deterministic values only, no wall-clock."""
    return f"DECISION {kind} {kv(**fields)}"


def summarize(obs: Observation) -> str:
    """One-line M1 summary of an observation. Log content is never shown (untrusted)."""
    if obs.status != "ok":
        return f"error={fmt(obs.error or 'unknown')}"
    if obs.tool == "get_latency":
        med = recent_median(obs.data, obs.end)
        return kv(median_5m_ms=med, baseline_ms=obs.baseline)
    if obs.tool == "get_error_rate":
        med = recent_median(obs.data, obs.end)
        ratio = round(med / obs.baseline, 2) if med is not None and obs.baseline else None
        return kv(
            median_5m=f"{med:.3f}" if med is not None else None,
            baseline=f"{obs.baseline:.3f}" if obs.baseline is not None else None,
            ratio=ratio,
        )
    if obs.tool == "get_deployments":
        if not obs.data:
            return kv(count=0, latest="none")
        at, version = max(obs.data)
        return kv(count=len(obs.data), latest=version, before_alert_s=obs.end - at)
    if obs.tool == "get_dependencies":
        if not obs.data:
            return "none"
        return " ".join(f"{d}(lat={lr:.1f},err={er:.1f})" for d, lr, er in obs.data)
    return f"lines={len(obs.data)}   (content not shown here: untrusted)"


def m1_report(alert: Alert, observations: list[Observation], with_header: bool = True) -> str:
    lines = [header(1, M1_TITLE)] if with_header else []
    lines += [
        kv(
            alert=alert.alert_id,
            service=alert.service,
            fired_at=alert.fired_at,
            severity_label=alert.severity,
        ),
        f"{'tool':<17}{'age_s':<7}{'max_staleness_s':<17}{'fresh':<6}summary",
    ]
    for o in observations:
        lines.append(
            f"{o.tool:<17}{o.age_s:<7.1f}{o.max_staleness_s:<17}{o.fresh!s:<6}{summarize(o)}"
        )
    return "\n".join(lines)


def trace_line(elapsed_s: float, kind: str, **fields: object) -> str:
    """`[t+0.00s] KIND k=v`: real elapsed seconds, then the event's fields."""
    body = f" {kv(**fields)}" if fields else ""
    return f"[t+{elapsed_s:.2f}s] {kind}{body}"


class PrintTrace:
    """Trace sink that prints each event with real seconds since it was created."""

    def __init__(self, clock: ControlClock | None = None) -> None:
        self._clock = clock or ControlClock()
        self._start = self._clock.now()

    def emit(self, kind: str, **fields: object) -> None:
        print(trace_line(self._clock.now() - self._start, kind, **fields))


def verdict_decision(alert_id: str, verdict: Verdict) -> str:
    fields: dict[str, object] = {
        "alert": alert_id,
        "verdict": verdict.kind,
        "runbook": verdict.runbook_id or "none",
        "rounds": verdict.rounds,
    }
    if verdict.reason:
        fields["reason"] = verdict.reason
    return decision("verdict", **fields)


def classify_decision(alert: Alert, c: Classification) -> str:
    """`severity_label` is display only: it is read from the alert, never given to the classifier."""
    return decision(
        "classify",
        alert=alert.alert_id,
        severity_label=alert.severity,
        action=c.action,
        tier=c.tier,
        requires_approval=c.requires_approval,
    )


def event_line(event: TraceEvent) -> str:
    """A recorded trace event as a `[t+…s]` line."""
    return trace_line(event.elapsed_s, event.kind, **dict(event.fields))


def approval_decision(alert_id: str, escalated: bool, approved_by: str) -> str:
    return decision("approval", alert=alert_id, escalated=escalated, approved_by=approved_by)


def execute_decision(alert_id: str, action: str, result: ExecutionResult) -> str:
    return decision(
        "execute",
        alert=alert_id,
        action=action,
        status=result.status,
        execution_id=result.execution_id,
    )


def verify_decision(alert_id: str, v: Verification, variant: str | None = None) -> str:
    fields: dict[str, object] = {"alert": alert_id}
    if variant:
        fields["variant"] = variant
    fields.update(status=v.status, verified=v.verified)
    fields.update(baseline_ms=v.baseline, observed_ms=v.observed)
    if v.reason:
        fields["reason"] = v.reason
    return decision("verify", **fields)


def handoff_decision(alert_id: str, reason: str) -> str:
    return decision("handoff", alert=alert_id, reason=reason)


def postmortem_decision(alert_id: str, draft: PostmortemDraft) -> str:
    return decision(
        "postmortem", alert=alert_id, notified=draft.notified, published=draft.published
    )


def publish_decision(alert_id: str, draft: PostmortemDraft) -> str:
    return decision("publish", alert=alert_id, published=draft.published, notified=draft.notified)
