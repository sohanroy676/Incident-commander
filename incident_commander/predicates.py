"""Three-valued predicates over numbers only (PHASE5 7.5, PHASE4 8.2).

Inputs are an observation's numeric data, a baseline and `fired_at`. No log
text, alert text or severity ever reaches a predicate. UNKNOWN covers missing,
errored, stale and ambiguous-band evidence; it never confirms and never refutes.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass

from .config import (
    DEP_ERROR_UNHEALTHY,
    DEP_LATENCY_UNHEALTHY,
    DEPLOY_WINDOW_S,
    ERROR_ELEVATED_RATIO,
    ERROR_NORMAL_RATIO,
    LATENCY_ELEVATED_RATIO,
    LATENCY_NORMAL_RATIO,
    RECENT_WINDOW_S,
    STEP_FRACTION,
    TREND_R2,
)
from .types import Observation, Tri

_MIN_TREND_POINTS = 3

PredicateFn = Callable[[tuple, "float | None", float], Tri]


def recent_median(data: tuple, end: float) -> float | None:
    """Median of the values in the last RECENT_WINDOW_S before `end`."""
    values = [v for t, v in data if t > end - RECENT_WINDOW_S]
    return statistics.median(values) if values else None


def _band(data: tuple, baseline: float | None, fired_at: float, low: float, high: float):
    """(ratio <= low, ratio >= high) of recent median to baseline; None if unmeasurable."""
    med = recent_median(data, fired_at)
    if med is None or not baseline:
        return None
    ratio = med / baseline
    return ratio <= low, ratio >= high


def _tri(value: bool | None) -> Tri:
    if value is None:
        return Tri.UNKNOWN
    return Tri.TRUE if value else Tri.FALSE


def _high_is_true(low: float, high: float) -> PredicateFn:
    """TRUE at >= high, FALSE at <= low, UNKNOWN in between."""

    def fn(data, baseline, fired_at):
        band = _band(data, baseline, fired_at, low, high)
        if band is None:
            return Tri.UNKNOWN
        is_low, is_high = band
        return Tri.TRUE if is_high else Tri.FALSE if is_low else Tri.UNKNOWN

    return fn


def _low_is_true(low: float, high: float) -> PredicateFn:
    """TRUE at <= low, FALSE at >= high, UNKNOWN in between."""

    def fn(data, baseline, fired_at):
        band = _band(data, baseline, fired_at, low, high)
        if band is None:
            return Tri.UNKNOWN
        is_low, is_high = band
        return Tri.TRUE if is_low else Tri.FALSE if is_high else Tri.UNKNOWN

    return fn


def _largest_jump(values: list[float]) -> tuple[int, float]:
    """(index of the point after the biggest adjacent rise, size of that rise)."""
    best_i, best = 0, 0.0
    for i in range(1, len(values)):
        if values[i] - values[i - 1] > best:
            best_i, best = i, values[i] - values[i - 1]
    return best_i, best


def latency_step_change(data, baseline, fired_at) -> Tri:
    values = [v for _, v in data]
    if len(values) < 2 or not baseline:
        return Tri.UNKNOWN
    final = values[-1]
    i, jump = _largest_jump(values)
    big = final > 0 and jump >= STEP_FRACTION * final
    quiet_before = all(v <= LATENCY_NORMAL_RATIO * baseline for v in values[:i])
    return _tri(big and quiet_before)


def latency_gradual_trend(data, baseline, fired_at) -> Tri:
    values = [v for _, v in data]
    if len(values) < _MIN_TREND_POINTS:
        return Tri.UNKNOWN
    _, jump = _largest_jump(values)
    if values[-1] > 0 and jump >= STEP_FRACTION * values[-1]:
        return Tri.FALSE
    times = [t for t, _ in data]
    try:
        slope, _ = statistics.linear_regression(times, values)
        r_squared = statistics.correlation(times, values) ** 2
    except statistics.StatisticsError:  # constant series: no trend
        return Tri.FALSE
    return _tri(slope > 0 and r_squared >= TREND_R2)


def _deploy_in_window(data, baseline, fired_at) -> bool:
    return any(fired_at - DEPLOY_WINDOW_S <= deployed_at <= fired_at for deployed_at, _ in data)


def deploy_in_window(data, baseline, fired_at) -> Tri:
    return _tri(_deploy_in_window(data, baseline, fired_at))


def no_deploy_in_window(data, baseline, fired_at) -> Tri:
    return _tri(not _deploy_in_window(data, baseline, fired_at))


def dependency_unhealthy(data, baseline, fired_at) -> Tri:
    return _tri(
        any(lat >= DEP_LATENCY_UNHEALTHY or err >= DEP_ERROR_UNHEALTHY for _, lat, err in data)
    )


@dataclass(frozen=True)
class Predicate:
    tool: str
    fn: PredicateFn


PREDICATES: dict[str, Predicate] = {
    "latency_elevated": Predicate(
        "get_latency", _high_is_true(LATENCY_NORMAL_RATIO, LATENCY_ELEVATED_RATIO)
    ),
    "latency_step_change": Predicate("get_latency", latency_step_change),
    "latency_gradual_trend": Predicate("get_latency", latency_gradual_trend),
    "latency_normal": Predicate(
        "get_latency", _low_is_true(LATENCY_NORMAL_RATIO, LATENCY_ELEVATED_RATIO)
    ),
    "error_normal": Predicate(
        "get_error_rate", _low_is_true(ERROR_NORMAL_RATIO, ERROR_ELEVATED_RATIO)
    ),
    "error_elevated": Predicate(
        "get_error_rate", _high_is_true(ERROR_NORMAL_RATIO, ERROR_ELEVATED_RATIO)
    ),
    "deploy_in_window": Predicate("get_deployments", deploy_in_window),
    "no_deploy_in_window": Predicate("get_deployments", no_deploy_in_window),
    "dependency_unhealthy": Predicate("get_dependencies", dependency_unhealthy),
}


def evaluate(pred_id: str, obs: Observation, baseline: float | None, fired_at: float) -> Tri:
    """UNKNOWN for any error or stale observation; otherwise the predicate's own verdict."""
    if obs.status != "ok" or not obs.fresh:
        return Tri.UNKNOWN
    return PREDICATES[pred_id].fn(obs.data, baseline, fired_at)
