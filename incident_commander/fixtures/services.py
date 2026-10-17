"""Deterministic per-service signal generators (PHASE5 8).

Series are pure functions of absolute time: no randomness and no incident
lookup. A tool asks "service X between t1 and t2" and gets samples.
Golden-set services (search, cart, auth, user-db) arrive with v0.6.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..config import LOOKBACK_S
from .alerts import ALERTS, DAY_S, T0

Series = Callable[[float], float]


def flat(level: float) -> Series:
    return lambda t: level


def step(base: float, at: float, level: float) -> Series:
    return lambda t: level if t >= at else base


def ramp(base: float, start: float, end: float, level: float) -> Series:
    """Linear climb from base at `start` to level at `end`, flat outside."""

    def fn(t: float) -> float:
        if t <= start:
            return base
        if t >= end:
            return level
        return base + (level - base) * (t - start) / (end - start)

    return fn


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    baseline_latency_ms: float
    baseline_error_rate: float
    latency: Series
    error_rate: Series
    deployments: tuple[tuple[float, str], ...]
    anchor: float  # logs are generated over the LOOKBACK_S before this time
    quiet_until: float  # latency sits at its quiet level before this time (sanity tests)
    dependencies: tuple[str, ...] = ()


_LOG_TEMPLATES = (
    "[INFO] request handled path=/api/v1/items status=200",
    "[INFO] health check ok",
    "[WARN] slow response from upstream cache, retrying once",
    "[INFO] connection pool size=32 in_use=11",
    "[INFO] config reload complete",
    "[WARN] retry budget at 80 percent for outbound client",
)
LOG_COUNT = 24


def make_logs(anchor: float) -> tuple[tuple[float, str], ...]:
    """24 plain INFO/WARN lines, one every 15 min across the lookback."""
    gap = LOOKBACK_S / LOG_COUNT
    return tuple(
        (anchor - LOOKBACK_S + (i + 1) * gap, _LOG_TEMPLATES[i % len(_LOG_TEMPLATES)])
        for i in range(LOG_COUNT)
    )


_A1 = ALERTS["ALRT-9001"].fired_at
_A2 = ALERTS["ALRT-9002"].fired_at
_A3 = ALERTS["ALRT-9003"].fired_at

SERVICES: dict[str, ServiceSpec] = {
    s.name: s
    for s in (
        ServiceSpec(
            "checkout-service",
            180.0,
            0.010,
            step(180.0, _A1 - 660, 1440.0),  # step 11 min before fired_at, after the deploy
            flat(0.011),
            ((_A1 - 720, "v2.14.0"),),
            _A1,
            _A1 - 660,
            ("payment-service", "inventory-service"),
        ),
        ServiceSpec(
            "inventory-service",
            180.0,
            0.010,
            ramp(180.0, _A2 - LOOKBACK_S, _A2, 1080.0),  # slow climb across the 6 h
            flat(0.010),  # at baseline: healthy as a dependency (ratio 1.0)
            ((_A2 - 18000, "v1.9.3"),),  # inside the lookback, outside the 30 min window
            _A2,
            _A2 - LOOKBACK_S,
        ),
        ServiceSpec(
            "notification-service",
            180.0,
            0.010,
            flat(185.0),
            step(0.010, _A3 - 1200, 0.050),  # 5x errors, no deploy
            (),
            _A3,
            _A3,
            ("email-gateway",),
        ),
        ServiceSpec("payment-service", 120.0, 0.005, flat(120.0), flat(0.005), (), T0, T0),
        ServiceSpec(
            "email-gateway",
            90.0,
            0.004,
            flat(90.0),
            flat(0.004),
            (),
            T0 + 2 * DAY_S,
            T0,
        ),
    )
}
