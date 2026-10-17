"""SimWorld: read-only simulated telemetry keyed by service name and timestamp."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping

from .config import RECENT_WINDOW_S, SAMPLE_INTERVAL_S, TOOL_SPECS
from .fixtures.alerts import ALERTS
from .fixtures.services import SERVICES, ServiceSpec, make_logs
from .types import Alert


class SimWorld:
    """Holds service fixtures and answers read queries. v0.1 has no write path.

    Data is never returned beyond `until` (the tool's `as_of`): a query for the
    future gets only what has been produced so far.
    """

    def __init__(
        self,
        services: Mapping[str, ServiceSpec] = SERVICES,
        alerts: Mapping[str, Alert] = ALERTS,
        tool_lags: Mapping[str, float] | None = None,
    ) -> None:
        self._services = dict(services)
        self._alerts = dict(alerts)
        self._tool_lags = dict(tool_lags or {})
        self._logs = {name: make_logs(s.anchor) for name, s in self._services.items()}

    def alert(self, alert_id: str) -> Alert:
        return self._alerts[alert_id]

    def alert_ids(self) -> tuple[str, ...]:
        return tuple(self._alerts)

    def lag_for(self, tool: str) -> float:
        return self._tool_lags.get(tool, TOOL_SPECS[tool].lag_s)

    def _service(self, name: str) -> ServiceSpec:
        return self._services[
            name
        ]  # KeyError for an unknown service: tools turn it into status=error

    def _grid(self, start: float, end: float) -> range:
        first = math.ceil(start / SAMPLE_INTERVAL_S) * SAMPLE_INTERVAL_S
        return range(first, math.floor(end) + 1, SAMPLE_INTERVAL_S)

    def latency_points(self, service: str, start: float, end: float, until: float):
        svc = self._service(service)
        return tuple((float(t), svc.latency(t)) for t in self._grid(start, min(end, until)))

    def error_points(self, service: str, start: float, end: float, until: float):
        svc = self._service(service)
        return tuple((float(t), svc.error_rate(t)) for t in self._grid(start, min(end, until)))

    def baselines(self, service: str) -> tuple[float, float]:
        svc = self._service(service)
        return svc.baseline_latency_ms, svc.baseline_error_rate

    def deployments(self, service: str, start: float, end: float, until: float):
        svc = self._service(service)
        return tuple(d for d in svc.deployments if start <= d[0] <= min(end, until))

    def logs(self, service: str, start: float, end: float, until: float):
        self._service(service)
        return tuple(r for r in self._logs[service] if start <= r[0] <= min(end, until))

    def dependency_ratios(self, service: str, at: float, until: float):
        """(dependency, latency_ratio, error_ratio) from each dependency's own series."""
        rows = []
        at = min(at, until)  # latest data produced so far when the source lags
        for dep in self._service(service).dependencies:
            lat = self.latency_points(dep, at - RECENT_WINDOW_S + 1, at, until)
            err = self.error_points(dep, at - RECENT_WINDOW_S + 1, at, until)
            base_lat, base_err = self.baselines(dep)
            rows.append(
                (
                    dep,
                    statistics.median(v for _, v in lat) / base_lat,
                    statistics.median(v for _, v in err) / base_err,
                )
            )
        return tuple(rows)

    def snapshot(self, start: float, end: float) -> tuple:
        """Everything readable over a window, for read-only tests."""
        return tuple(
            (
                name,
                self.latency_points(name, start, end, end),
                self.error_points(name, start, end, end),
                self.deployments(name, start, end, end),
                self.logs(name, start, end, end),
                self.baselines(name),
            )
            for name in sorted(self._services)
        )
