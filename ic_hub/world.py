"""HubWorld: the graded SimWorld plus uploaded services, alerts and remediation effects."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from incident_commander.config import ACTION_PROPERTIES
from incident_commander.fixtures.alerts import ALERTS
from incident_commander.fixtures.golden import GOLDEN_ALERTS, GOLDEN_SERVICES
from incident_commander.fixtures.services import (
    REMEDIATION_DELAY_S,
    REMEDIATION_OUTCOMES,
    SERVICES,
)
from incident_commander.world import SimWorld

from .schema import Upload


class HubWorld(SimWorld):
    """Built-in demo and golden data beside uploads. A fresh instance per run."""

    def __init__(
        self,
        uploads: Iterable[Upload] = (),
        planted_logs: Mapping[str, tuple[str, ...]] | None = None,
    ) -> None:
        uploads = tuple(uploads)
        super().__init__(
            services={
                **SERVICES,
                **GOLDEN_SERVICES,
                **{u.service.name: u.service for u in uploads},
            },
            alerts={**ALERTS, **GOLDEN_ALERTS, **{u.alert.alert_id: u.alert for u in uploads}},
            planted_logs=planted_logs,
        )
        self._effects = {
            (u.service.name, action): dict(outcomes)
            for u in uploads
            for action, outcomes in u.effects.items()
        }

    def has_service(self, name: str) -> bool:
        return name in self._services

    def apply_remediation(
        self, service: str, action: str, at: float, outcome: str = "success"
    ) -> None:
        effect = self._effects.get((service, action))
        if effect is None:
            super().apply_remediation(service, action, at, outcome)
            return
        if action not in ACTION_PROPERTIES:
            raise ValueError(f"unknown action: {action}")
        if outcome not in REMEDIATION_OUTCOMES:
            raise ValueError(f"unknown outcome: {outcome}")
        self._latency_overrides[service] = (at + REMEDIATION_DELAY_S, effect[outcome])
