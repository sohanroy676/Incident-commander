"""First LLM role: an AI-drafted postmortem narrative.

The narrator runs after every decision is final. It sees typed trace facts only (never log
text, never `Observation.data`), its reply passes `guard_narrative`, and any failure falls back
to the deterministic template. It has no write path to the Case except trace events.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from incident_commander.commander import Case

from .guard import guard_narrative
from .llm_client import LLMClient

UNAVAILABLE_LINE = "llm: unavailable, deterministic fallback"
REJECTED_LINE = "llm: rejected, deterministic fallback"
NARRATIVE_LABEL = "AI-drafted narrative (not authoritative):"

SYSTEM_PROMPT = (
    "You write a short postmortem narrative for an incident. Use ONLY the JSON facts you are "
    "given. Reply with one JSON object with exactly the keys summary, impact, root_cause_text; "
    "each value is plain text under 400 characters. Use only numbers and identifiers that "
    "appear in the facts. Do not use hyphenated words other than identifiers from the facts. "
    "Describe what happened in the past tense; never give instructions or advice."
)


@dataclass(frozen=True)
class NarratorOutcome:
    status: str  # "ok" | "unavailable" | "rejected"
    lines: tuple[str, ...]
    narrative: dict | None = None


def build_facts(case: Case) -> dict:
    """Typed facts from a finished case. No log text, no free-form strings from tools."""
    verdict = case.investigation.verdict if case.investigation else None
    token = case.approval.token if case.approval else None
    verification = case.verification
    return {
        "alert_id": case.alert.alert_id,
        "service": case.alert.service,
        "metric": case.alert.metric,
        "verdict": verdict.kind if verdict else None,
        "runbook_id": verdict.runbook_id if verdict else None,
        "rounds": verdict.rounds if verdict else None,
        "no_match_reason": verdict.reason if verdict else None,
        "action": case.action,
        "tier": case.classification.tier if case.classification else None,
        "requires_approval": (
            case.classification.requires_approval if case.classification else None
        ),
        "approval_status": case.approval.status if case.approval else None,
        "escalated": case.approval.escalated if case.approval else None,
        "approved_by": token.approved_by if token else None,
        "execution_status": case.execution.status if case.execution else None,
        "verification_status": verification.status if verification else None,
        "verified": verification.verified if verification else None,
        "baseline_value": verification.baseline if verification else None,
        "observed_value": verification.observed if verification else None,
        "handoff_reason": case.handoff_reason,
    }


def build_messages(facts: dict) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(facts, sort_keys=True)},
    ]


def _printable(text: str, limit: int = 120) -> str:
    """One safe line: model-influenced text must never add lines or control characters."""
    return re.sub(r"[^\x20-\x7e]+", " ", text).strip()[:limit]


def narrative_line(narrative: dict) -> str:
    body = (
        f"{narrative['summary']} Impact: {narrative['impact']} "
        f"Root cause: {narrative['root_cause_text']}"
    )
    return f'postmortem narrative: "{NARRATIVE_LABEL} {_printable(body, 2000)}"'


def narrate(case: Case, client: LLMClient | None) -> NarratorOutcome:
    """Ask the model for a narrative; never raises and never touches a decision."""
    if client is None:
        case.trace.emit("llm_unavailable", role="narrator", reason="not configured")
        return NarratorOutcome("unavailable", (UNAVAILABLE_LINE,))
    facts = build_facts(case)
    reply = client.chat(build_messages(facts), json_mode=True)
    if not reply.ok:
        case.trace.emit("llm_unavailable", role="narrator", reason=_printable(reply.error))
        return NarratorOutcome("unavailable", (UNAVAILABLE_LINE,))
    result = guard_narrative(reply.text, facts)
    if not result.ok:
        reason = _printable(result.reason)
        case.trace.emit("llm_rejected", role="narrator", reason=reason)
        lines = (f"llm_rejected role=narrator alert={case.alert.alert_id} reason={reason}",)
        return NarratorOutcome("rejected", (*lines, REJECTED_LINE))
    assert result.data is not None  # ok means the guard returned data
    case.trace.emit("llm_ok", role="narrator", model=_printable(reply.model, 60), guard="pass")
    ok_lines = (
        f"llm: ok role=narrator model={_printable(reply.model, 60)} guard=pass",
        narrative_line(result.data),
    )
    return NarratorOutcome("ok", ok_lines, result.data)
