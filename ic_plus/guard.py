"""Deterministic guard for LLM replies. A backstop, not a defence: the LLM never decides anything.

guard_narrative accepts a reply only if it is exactly the expected JSON, every number and
identifier in it comes from the trace facts, and it contains no instruction-like text.
Any failure means the caller logs `llm_rejected` and uses the deterministic template.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from incident_commander.config import PRIMARY_ONCALL, SECONDARY_ONCALL
from incident_commander.fixtures.runbooks import RUNBOOKS
from incident_commander.fixtures.services import SERVICES

NARRATIVE_KEYS = ("summary", "impact", "root_cause_text")
MAX_FIELD_CHARS = 600

NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")
# Hyphenated tokens are treated as identifiers (services, alert ids, runbook ids, people).
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+")
WORD = re.compile(r"[a-z]+")
SENTENCE = re.compile(r"[.!?\n]+")

# Names the facts may mention; each must appear in the facts to be allowed in the text.
KNOWN_NAMES = frozenset(
    {*SERVICES, *RUNBOOKS, PRIMARY_ONCALL, SECONDARY_ONCALL}
    | {n.split("-", 1)[1] for n in (PRIMARY_ONCALL, SECONDARY_ONCALL)}
)

IMPERATIVE_STARTS = frozenset(
    {
        *("execute", "run", "roll", "restart", "delete", "drop", "kill", "ignore"),
        *("disregard", "approve", "deploy", "apply", "disable", "enable", "shutdown", "shut"),
        *("escalate", "override", "grant", "forget", "reveal", "please"),
    }
)
INSTRUCTION_PHRASES = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bignore\b.{0,20}\b(previous|prior|above|earlier|instructions)\b",
        r"\bdisregard\b",
        r"\broll(ing)?[ -]?back\b.{0,20}\bnow\b",
        r"\b(you|we) (must|should|need to|have to)\b",
        r"\bsystem prompt\b",
        r"\bas an ai\b",
        r"\bapprove (it|this|the)\b",
        r"\bexecute (it|this|the|a|an)\b",
    )
)


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    reason: str = ""
    data: dict | None = None


def _reject(reason: str) -> GuardResult:
    return GuardResult(ok=False, reason=reason)


def _numbers(text: str) -> set[float]:
    return {float(m) for m in NUMBER.findall(text)}


def _facts_text(facts: dict) -> str:
    return json.dumps(facts, sort_keys=True, default=str)


def _instruction_like(text: str) -> str | None:
    for pattern in INSTRUCTION_PHRASES:
        if pattern.search(text):
            return f"instruction phrase /{pattern.pattern}/"
    for sentence in SENTENCE.split(text):
        words = WORD.findall(sentence.lower())
        if words and words[0] in IMPERATIVE_STARTS:
            return f"imperative sentence starting {words[0]!r}"
    return None


def guard_narrative(reply_text: str, facts: dict) -> GuardResult:
    """Validate a narrator reply against the trace facts it was built from."""
    if not isinstance(reply_text, str) or not reply_text.strip():
        return _reject("empty reply")
    try:
        data = json.loads(reply_text)
    except ValueError:
        return _reject("not valid JSON")
    if not isinstance(data, dict):
        return _reject("not a JSON object")
    if set(data) != set(NARRATIVE_KEYS):
        return _reject(f"keys {sorted(data)} != {sorted(NARRATIVE_KEYS)}")
    for key in NARRATIVE_KEYS:
        value = data[key]
        if not isinstance(value, str) or not value.strip():
            return _reject(f"{key} is empty or not text")
        if len(value) > MAX_FIELD_CHARS:
            return _reject(f"{key} longer than {MAX_FIELD_CHARS} characters")

    text = " ".join(data[k] for k in NARRATIVE_KEYS)
    facts_text = _facts_text(facts)
    extra = _numbers(text) - _numbers(facts_text)
    if extra:
        return _reject(f"numbers not in the facts: {sorted(extra)}")

    allowed = facts_text.lower()
    for token in IDENTIFIER.findall(text):
        if token.lower() not in allowed:
            return _reject(f"identifier not in the facts: {token}")
    for word in set(WORD.findall(text.lower())):
        if word in KNOWN_NAMES and word not in allowed:
            return _reject(f"name not in the facts: {word}")

    found = _instruction_like(text)
    if found:
        return _reject(found)
    return GuardResult(ok=True, data={k: data[k] for k in NARRATIVE_KEYS})
