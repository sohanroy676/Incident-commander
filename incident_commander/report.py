"""Output contract helpers: headers, trace/decision lines, the M1 table (PHASE5 6)."""

from __future__ import annotations

import statistics

from .config import RECENT_WINDOW_S
from .types import Alert, Observation

M1_TITLE = "SIGNAL INGESTION"


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


def _recent_median(obs: Observation) -> float | None:
    values = [v for t, v in obs.data if t > obs.end - RECENT_WINDOW_S]
    return statistics.median(values) if values else None


def summarize(obs: Observation) -> str:
    """One-line M1 summary of an observation. Log content is never shown (untrusted)."""
    if obs.status != "ok":
        return f"error={fmt(obs.error or 'unknown')}"
    if obs.tool == "get_latency":
        med = _recent_median(obs)
        return kv(median_5m_ms=med, baseline_ms=obs.baseline)
    if obs.tool == "get_error_rate":
        med = _recent_median(obs)
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


def m1_report(alert: Alert, observations: list[Observation]) -> str:
    lines = [
        header(1, M1_TITLE),
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
