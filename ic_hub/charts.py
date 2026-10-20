"""Chart data and run diffs for the hub, read from a finished case and the world it ran in.

Nothing here decides anything: it re-reads the alert's own metric series (the same read-only world
queries the tools use), the deployments in the 30 minute window, and the trace times for the fix.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from incident_commander.commander import Case
from incident_commander.config import DEPLOY_WINDOW_S, METRIC_TOOLS, VERIFY_TOLERANCE
from incident_commander.world import SimWorld


def _event_time(case: Case, kind: str, status: str | None = None) -> float | None:
    for event in case.trace.events:
        if event.kind == kind and (status is None or dict(event.fields).get("status") == status):
            return event.data_time
    return None


def build_chart(world: SimWorld, case: Case) -> dict[str, object] | None:
    """The alert's metric over the deploy window plus the verify window, or None if unreadable."""
    alert = case.alert
    tool = METRIC_TOOLS.get(alert.metric)
    if tool is None:
        return None
    start = alert.fired_at - DEPLOY_WINDOW_S
    end = max([alert.fired_at, *(e.data_time for e in case.trace.events)])
    try:
        if tool == "get_latency":
            points = world.latency_points(alert.service, start, end, end)
            baseline = world.baselines(alert.service)[0]
        else:
            points = world.error_points(alert.service, start, end, end)
            baseline = world.baselines(alert.service)[1]
        deploys = world.deployments(alert.service, start, end, end)
    except Exception:  # noqa: BLE001 - a broken backend (what-if) leaves the run without a chart
        return None
    return {
        "service": alert.service,
        "metric": alert.metric,
        "points": [[t, v] for t, v in points],
        "baseline": baseline,
        "limit": baseline * VERIFY_TOLERANCE,
        "fired_at": alert.fired_at,
        "window_start": start,
        "window_end": end,
        "executed_at": _event_time(case, "EXECUTE", "executed"),
        "verify_end": _event_time(case, "VERIFY"),
        "deployments": [{"at": t, "version": str(v)} for t, v in deploys],
    }


def diff_runs(a: Mapping[str, object], b: Mapping[str, object]) -> dict[str, object]:
    """What differs between two finished run results: state, handoff, DECISION lines, trace kinds."""

    def kinds(result: Mapping[str, object]) -> list[str]:
        trace = result["trace"]
        assert isinstance(trace, list)
        return [str(e["kind"]) for e in trace]

    def lines(result: Mapping[str, object]) -> list[str]:
        value = result["decision_lines"]
        assert isinstance(value, list)
        return [str(x) for x in value]

    def only(first: Sequence[str], second: Sequence[str]) -> list[str]:
        return [x for x in first if x not in second]

    la, lb = lines(a), lines(b)
    ka, kb = kinds(a), kinds(b)
    return {
        "state": [a["state"], b["state"]],
        "handoff_reason": [a["handoff_reason"], b["handoff_reason"]],
        "only_in_a": only(la, lb),
        "only_in_b": only(lb, la),
        "same_decisions": la == lb,
        "trace_kinds": [ka, kb],
        "same_trace_kinds": ka == kb,
    }
