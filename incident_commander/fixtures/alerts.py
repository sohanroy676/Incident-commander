"""The alert table: the ONLY place incident ids exist (PHASE5 8)."""

from __future__ import annotations

from ..types import Alert

# T0 is a multiple of 60 so every alert lands on the sampling grid. Alerts are
# one day apart so no service's incident overlaps another alert's lookback.
T0 = 1_760_000_100.0
DAY_S = 86_400.0

ALERTS: dict[str, Alert] = {
    a.alert_id: a
    for a in (
        Alert(
            "ALRT-9001",
            "checkout-service",
            T0,
            "high",
            "latency_ms",
            "checkout latency spike, error rate normal",
        ),
        Alert(
            "ALRT-9002",
            "inventory-service",
            T0 + DAY_S,
            "high",
            "latency_ms",
            "inventory latency spike, error rate normal",
        ),
        Alert(
            "ALRT-9003",
            "notification-service",
            T0 + 2 * DAY_S,
            "medium",
            "error_rate",
            "notification error rate elevated, latency normal",
        ),
    )
}
