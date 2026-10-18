"""Third LLM role: an optional tool-order suggestion for the investigator's tie-break.

The advisor sees typed numbers only (alert id, service, metric, ranked candidates with scores and
the allowed tool names; never summary text, severity or logs). Its reply passes `guard_advice`:
only allowed read-only tools, once each. Any failure means the investigator's fixed order. The
suggestion is only a `tool_order` argument: it can reorder equally useful calls, never add, drop
or run anything, and the guard's output is data, never a command.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from incident_commander.investigator import EVIDENCE_TOOLS
from incident_commander.types import Alert, Candidate

from .guard import ADVICE_KEY, guard_advice
from .llm_client import LLMClient
from .narrator import REJECTED_LINE, UNAVAILABLE_LINE, _printable

SCORE_DIGITS = 4

SYSTEM_PROMPT = (
    "You suggest the order in which an incident investigator should call its read-only evidence "
    "tools. You are given JSON with the alert, the ranked runbook candidates and allowed_tools. "
    'Reply with one JSON object with exactly one key, "order": a list of tool names taken from '
    "allowed_tools, each at most once, most useful first. Never name anything else."
)


class _Sink(Protocol):
    def emit(self, kind: str, **fields: object) -> None: ...


@dataclass(frozen=True)
class AdvisorOutcome:
    status: str  # "ok" | "unavailable" | "rejected"
    order: tuple[str, ...]  # always a permutation of EVIDENCE_TOOLS; the fixed order on any failure
    lines: tuple[str, ...]


def build_facts(alert: Alert, candidates: Sequence[Candidate]) -> dict:
    """Numbers and ids only: no summary text, no severity label, no observation data."""
    return {
        "alert_id": alert.alert_id,
        "service": alert.service,
        "metric": alert.metric,
        "candidates": [
            {
                "runbook_id": c.runbook_id,
                "rank": c.rank,
                "fused_score": round(c.fused_score, SCORE_DIGITS),
            }
            for c in candidates
        ],
        "allowed_tools": list(EVIDENCE_TOOLS),
        "evidence_so_far": [],
    }


def build_messages(facts: dict) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(facts, sort_keys=True)},
    ]


def advise(
    alert: Alert,
    candidates: Sequence[Candidate],
    client: LLMClient | None,
    trace: _Sink | None = None,
) -> AdvisorOutcome:
    """Ask the model for a tool order; never raises and never runs anything."""

    def emit(kind: str, **fields: object) -> None:
        if trace is not None:
            trace.emit(kind, role="advisor", **fields)

    if client is None:
        emit("llm_unavailable", reason="not configured")
        return AdvisorOutcome("unavailable", EVIDENCE_TOOLS, (UNAVAILABLE_LINE,))
    reply = client.chat(build_messages(build_facts(alert, candidates)), json_mode=True)
    if not reply.ok:
        emit("llm_unavailable", reason=_printable(reply.error))
        return AdvisorOutcome("unavailable", EVIDENCE_TOOLS, (UNAVAILABLE_LINE,))
    result = guard_advice(reply.text, EVIDENCE_TOOLS)
    if not result.ok:
        reason = _printable(result.reason)
        emit("llm_rejected", reason=reason)
        lines = (
            f"llm_rejected role=advisor alert={alert.alert_id} reason={reason}",
            REJECTED_LINE,
        )
        return AdvisorOutcome("rejected", EVIDENCE_TOOLS, lines)
    order = result.data[ADVICE_KEY]
    model = _printable(reply.model, 60)
    emit("llm_ok", model=model, guard="pass", order=",".join(order))
    line = f"llm: ok role=advisor model={model} guard=pass order={','.join(order)}"
    return AdvisorOutcome("ok", order, (line,))
