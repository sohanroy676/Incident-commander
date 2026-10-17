"""Blast-radius classifier (PHASE5 7.7): tier from the action's properties only."""

from __future__ import annotations

from .config import ACTION_PROPERTIES
from .types import Classification


def classify_remediation(action: str) -> Classification:
    """High tier if the action is not quickly reversible or changes code/routing; unknown -> high."""
    props = ACTION_PROPERTIES.get(action)
    if props is None:
        return Classification(action, "high", True, ("unknown action: fail closed",))
    reversible, changes_code_or_routing = props
    reasons = []
    if not reversible:
        reasons.append("not quickly reversible")
    if changes_code_or_routing:
        reasons.append("changes running code or traffic routing")
    if not reasons:
        return Classification(
            action, "low", False, ("quickly reversible", "no change to code or routing")
        )
    return Classification(action, "high", True, tuple(reasons))
