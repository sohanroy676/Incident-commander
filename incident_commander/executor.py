"""Idempotent executor: one effect per (case, action, service), token for high tier (PHASE5 7.9)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .blast_radius import classify_remediation
from .clocks import DataClock
from .types import ApprovalToken, Execution
from .world import SimWorld


class ApprovalRequired(Exception):
    """A high-tier action was executed without a valid approval token."""


@dataclass(frozen=True)
class ExecutionResult:
    status: str  # "executed" | "already_executed" | "failed"
    execution_id: str | None
    error: str | None = None


def execution_id_for(key: tuple) -> str:
    return "exec-" + hashlib.sha256(repr(key).encode("utf-8")).hexdigest()[:10]


def _token_valid(token: ApprovalToken | None, action: str, service: str) -> bool:
    return token is not None and token.action == action and token.service == service


class Executor:
    def __init__(self, world: SimWorld, clock: DataClock) -> None:
        self._world = world
        self._clock = clock
        self._ledger: dict[tuple, Execution] = {}

    def execute(
        self, action: str, service: str, case_id: str, token: ApprovalToken | None
    ) -> ExecutionResult:
        key = (case_id, action, service)
        done = self._ledger.get(key)
        if done is not None:
            return ExecutionResult("already_executed", done.execution_id)
        if classify_remediation(action).requires_approval and not _token_valid(
            token, action, service
        ):
            raise ApprovalRequired(f"{action} on {service} needs a matching approval token")
        at = self._clock.now()
        try:
            self._world.apply_remediation(service, action, at)
        except (KeyError, ValueError) as exc:
            return ExecutionResult("failed", None, f"{type(exc).__name__}: {exc}")
        execution = Execution(execution_id_for(key), key, action, service, at)
        self._ledger[key] = execution
        return ExecutionResult("executed", execution.execution_id)
