"""Output contract helpers: headers, trace/decision lines, the M1 table (PHASE5 6)."""

from __future__ import annotations

from . import config
from .clocks import ControlClock
from .commander import Case
from .executor import ExecutionResult
from .predicates import recent_median
from .retrieval import HybridRanker
from .types import (
    Alert,
    AttackResult,
    Candidate,
    Classification,
    GoldenResult,
    NaiveResult,
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


def m2_table(alert: Alert, candidates: list[Candidate]) -> str:
    """M2 grounding table: per-runbook BM25 rank, char rank, fused score, then the top-2 margin."""
    lines = [
        kv(alert=alert.alert_id, query=alert.summary),
        f"{'runbook':<8} {'bm25_rank':>9} {'char_rank':>9} {'fused_score':>11}",
    ]
    for c in candidates:
        lines.append(
            f"{c.runbook_id:<8} {c.ranks['bm25']:>9} {c.ranks['char']:>9} {c.fused_score:>11.6f}"
        )
    margin = HybridRanker.margin(candidates)
    note = ""
    if margin < config.SMALL_MARGIN:
        note = "   (small margin: retrieval cannot separate the top candidates)"
    lines.append(f"top2_margin={margin:.6f}{note}")
    return "\n".join(lines)


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


def case_decision_lines(case: Case) -> tuple[str, ...]:
    """Every DECISION line a run of one case produces (no postmortem text), for diffing runs."""
    aid = case.alert.alert_id
    lines = [verdict_decision(aid, case.investigation.verdict)]
    if case.classification is not None:
        lines.append(classify_decision(case.alert, case.classification))
    if case.approval is not None:
        token = case.approval.token
        lines.append(
            approval_decision(aid, case.approval.escalated, token.approved_by if token else "none")
        )
    if case.execution is not None and case.action is not None:
        lines.append(execute_decision(aid, case.action, case.execution))
    if case.verification is not None:
        lines.append(verify_decision(aid, case.verification))
    if case.handoff_reason is not None:
        lines.append(handoff_decision(aid, case.handoff_reason))
    return tuple(lines)


def golden_decision(r: GoldenResult) -> str:
    return decision(
        "golden",
        id=r.golden_id,
        verdict=r.verdict,
        runbook=r.runbook or "none",
        action=r.action or "none",
        **{"pass": r.passed},
    )


def golden_summary(results: list[GoldenResult]) -> str:
    return decision("golden_summary", passed=sum(r.passed for r in results), total=len(results))


def attack_lines(r: AttackResult) -> list[str]:
    lines = [
        decision(
            "attack",
            alert=r.alert_id,
            verdict=r.verdict,
            runbook=r.runbook or "none",
            action=r.action or "none",
            unchanged=r.unchanged,
        ),
        kv(
            attack_inputs_identical=r.inputs_identical,
            attack_decision_lines_identical=r.decision_lines_identical,
        ),
    ]
    lines += [kv(attack_variant=name, unchanged=ok) for name, ok in r.variants]
    return lines


def naive_table(results: list[NaiveResult]) -> str:
    lines = [
        f"{'alert':<10} {'naive_choice':<13} {'naive_action':<21} {'expected':<9} naive_correct"
    ]
    for r in results:
        lines.append(f"{r.alert_id:<10} {r.choice:<13} {r.action:<21} {r.expected:<9} {r.correct}")
    wrong = sum(not r.correct for r in results)
    lines.append(kv(naive_wrong=wrong, total=len(results)))
    return "\n".join(lines)
