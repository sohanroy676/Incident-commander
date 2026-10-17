"""Verifier: re-query the alert's own metric after the fix (PHASE5 7.10, PHASE4 9.4)."""

from __future__ import annotations

import statistics

from .clocks import DataClock
from .config import METRIC_TOOLS, VERIFY_TOLERANCE, VERIFY_WINDOW_S
from .tools import get_error_rate, get_latency
from .types import Execution, Observation, Verification
from .world import SimWorld

NO_FRESH_DATA = "no fresh post-fix data"
NOT_RESOLVED = "remediation ran but did not resolve the signal"


def assess(
    metric: str, obs: Observation, executed_at: float, tolerance: float = VERIFY_TOLERANCE
) -> Verification:
    """Pure decision over a typed observation: resolved only with fresh post-fix data in tolerance."""
    values = [v for t, v in obs.data if t >= executed_at]
    usable = obs.status == "ok" and obs.fresh and obs.as_of >= executed_at and values
    if not usable or not obs.baseline:
        return Verification("reopened", False, metric, obs.baseline, None, NO_FRESH_DATA)
    observed = statistics.median(values)
    if observed <= obs.baseline * tolerance:
        return Verification("resolved", True, metric, obs.baseline, observed)
    return Verification("reopened", False, metric, obs.baseline, observed, NOT_RESOLVED)


def verify(
    world: SimWorld,
    clock: DataClock,
    service: str,
    metric: str,
    execution: Execution,
    tolerance: float = VERIFY_TOLERANCE,
    window_s: float = VERIFY_WINDOW_S,
) -> Verification:
    """Wait (in simulated time) for the post-fix window, then re-query `metric` for `service`."""
    tool = METRIC_TOOLS.get(metric)
    if tool is None:
        return Verification("reopened", False, metric, None, None, NO_FRESH_DATA)
    start, end = execution.executed_at, execution.executed_at + window_s
    if clock.now() < end:
        clock.advance(end - clock.now())
    query = get_latency if tool == "get_latency" else get_error_rate
    return assess(
        metric, query(world, clock, service, start, end), execution.executed_at, tolerance
    )
