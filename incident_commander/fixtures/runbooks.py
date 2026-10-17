"""Runbook corpus: machine-checkable signatures and actions (PHASE4 7.1).

The `text` is a placeholder until v0.5 writes the real retrieval corpus.
"""

from __future__ import annotations

from ..types import Runbook

_PLACEHOLDER = "placeholder text until v0.5"

RUNBOOKS: dict[str, Runbook] = {
    r.runbook_id: r
    for r in (
        Runbook(
            "RB-101",
            "Bad deployment regression",
            _PLACEHOLDER,
            ("latency_elevated", "latency_step_change", "error_normal", "deploy_in_window"),
            "rollback_deployment",
        ),
        Runbook(
            "RB-102",
            "Gradual resource exhaustion (memory leak)",
            _PLACEHOLDER,
            ("latency_elevated", "latency_gradual_trend", "error_normal", "no_deploy_in_window"),
            "restart_service",
        ),
        Runbook(
            "RB-103",
            "Downstream dependency degraded",
            _PLACEHOLDER,
            ("latency_elevated", "error_elevated", "dependency_unhealthy"),
            "failover_dependency",
        ),
        Runbook(
            "RB-104",
            "Errors after a release or config change",
            _PLACEHOLDER,
            ("latency_normal", "error_elevated", "deploy_in_window"),
            "rollback_deployment",
        ),
    )
}
