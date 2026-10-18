"""Runbook corpus: machine-checkable signatures and actions (PHASE4 7.1).

The `text` is the retrieval corpus (v0.5). It overlaps on purpose: RB-101 and RB-102 share
"latency spike", "error rate normal", "checkout" and "service slowdown", and RB-104 shares
"after a release" and "error rate" with RB-101, so retrieval alone cannot separate them.
Signatures are never indexed; the Investigator tests them against evidence.
"""

from __future__ import annotations

from ..types import Runbook

_TEXT_101 = (
    "Checkout latency spike with error rate normal: service slowdown that began right after a "
    "release. Requests succeed but take far longer, a sudden step in response time. Compare the "
    "latency jump with the deployment time and roll back the bad deployment regression."
)
_TEXT_102 = (
    "Checkout latency spike with error rate normal: service slowdown that builds up slowly with "
    "no recent release. Memory leak and heap growth push garbage collection pauses up, a gradual "
    "climb in response time. Restart the service to release the exhausted resources."
)
_TEXT_103 = (
    "Service slowdown and rising error rate caused by a downstream dependency. Upstream timeouts "
    "and failed calls to an unhealthy database or payment provider. Check dependency health and "
    "fail over to the standby dependency."
)
_TEXT_104 = (
    "Error rate elevated after a release or config change while latency stays normal. Requests "
    "fail fast with 5xx responses, an error rate jump right after the deployment. Roll back the "
    "release or revert the config change."
)

RUNBOOKS: dict[str, Runbook] = {
    r.runbook_id: r
    for r in (
        Runbook(
            "RB-101",
            "Bad deployment regression",
            _TEXT_101,
            ("latency_elevated", "latency_step_change", "error_normal", "deploy_in_window"),
            "rollback_deployment",
            (
                "Add a latency check to the release pipeline",
                "Review the rolled-back change before redeploying",
            ),
        ),
        Runbook(
            "RB-102",
            "Gradual resource exhaustion (memory leak)",
            _TEXT_102,
            ("latency_elevated", "latency_gradual_trend", "error_normal", "no_deploy_in_window"),
            "restart_service",
            (
                "Find and fix the leak behind the heap growth",
                "Add a memory-growth alert before exhaustion",
            ),
        ),
        Runbook(
            "RB-103",
            "Downstream dependency degraded",
            _TEXT_103,
            ("latency_elevated", "error_elevated", "dependency_unhealthy"),
            "failover_dependency",
            (
                "Agree timeout and retry limits with the dependency owner",
                "Test the failover path regularly",
            ),
        ),
        Runbook(
            "RB-104",
            "Errors after a release or config change",
            _TEXT_104,
            ("latency_normal", "error_elevated", "deploy_in_window"),
            "rollback_deployment",
            (
                "Add a post-release error-rate gate",
                "Validate config changes in staging first",
            ),
        ),
    )
}
