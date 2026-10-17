"""Five typed, read-only signal tools (PHASE5 7.3).

Tools take a service and a time window, never an incident id. Every call
advances the DataClock; a tool failure becomes status="error", never a raise.
"""

from __future__ import annotations

from collections.abc import Callable

from .clocks import DataClock
from .config import DATA_CLOCK_TICK_S, TOOL_SPECS
from .types import Observation
from .world import SimWorld

__all__ = [
    "TOOL_SPECS",
    "get_dependencies",
    "get_deployments",
    "get_error_rate",
    "get_latency",
    "get_logs",
]

# fetch(as_of) -> (data, baseline)
_Fetch = Callable[[float], tuple[tuple, float | None]]


def _observe(
    world: SimWorld,
    clock: DataClock,
    tool: str,
    service: str,
    start: float,
    end: float,
    fetch: _Fetch,
) -> Observation:
    spec = TOOL_SPECS[tool]
    clock.advance(DATA_CLOCK_TICK_S)
    data_now = clock.now()
    as_of = data_now - world.lag_for(tool)
    age_s = data_now - as_of
    fresh = age_s <= spec.max_staleness_s
    try:
        data, baseline = fetch(as_of)
    except Exception as exc:  # noqa: BLE001 - a failing tool must never propagate
        return Observation(
            tool, service, start, end, (), as_of, spec.max_staleness_s, "error", age_s,
            False, f"{type(exc).__name__}: {exc}",
        )  # fmt: skip
    return Observation(
        tool, service, start, end, data, as_of, spec.max_staleness_s, "ok", age_s,
        fresh, None, baseline,
    )  # fmt: skip


def get_latency(world: SimWorld, clock: DataClock, service: str, start: float, end: float):
    """data: ((t, ms), ...); baseline: the service's baseline latency in ms."""

    def fetch(as_of: float):
        return world.latency_points(service, start, end, as_of), world.baselines(service)[0]

    return _observe(world, clock, "get_latency", service, start, end, fetch)


def get_error_rate(world: SimWorld, clock: DataClock, service: str, start: float, end: float):
    """data: ((t, errors_per_request), ...); baseline: the service's baseline error rate."""

    def fetch(as_of: float):
        return world.error_points(service, start, end, as_of), world.baselines(service)[1]

    return _observe(world, clock, "get_error_rate", service, start, end, fetch)


def get_deployments(world: SimWorld, clock: DataClock, service: str, start: float, end: float):
    """data: ((deployed_at, version), ...)"""

    def fetch(as_of: float):
        return world.deployments(service, start, end, as_of), None

    return _observe(world, clock, "get_deployments", service, start, end, fetch)


def get_dependencies(world: SimWorld, clock: DataClock, service: str, at: float):
    """data: ((dependency, latency_ratio, error_ratio), ...) from the dependencies' own series."""

    def fetch(as_of: float):
        return world.dependency_ratios(service, at, as_of), None

    return _observe(world, clock, "get_dependencies", service, at, at, fetch)


def get_logs(world: SimWorld, clock: DataClock, service: str, start: float, end: float):
    """data: ((t, text), ...). Untrusted text; the Investigator never gets this tool."""

    def fetch(as_of: float):
        return world.logs(service, start, end, as_of), None

    return _observe(world, clock, "get_logs", service, start, end, fetch)
