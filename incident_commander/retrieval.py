"""Runbook ranking (PHASE5 7.4). v0.2 ships only the labelled stub; HybridRanker arrives in v0.5.

A ranker only orders hypotheses (a planner tie-break). It never confirms one.
"""

from __future__ import annotations

from typing import Protocol

from .types import Candidate


class Ranker(Protocol):
    label: str

    def rank(self, query: str) -> list[Candidate]: ...


class StaticRanker:
    """Fixed order, declared as a stub in the output. The query is ignored."""

    label = "STUB"

    def __init__(self, order: list[str] | tuple[str, ...]) -> None:
        if not order:
            raise ValueError("StaticRanker needs a non-empty order")
        if len(set(order)) != len(order):
            raise ValueError("StaticRanker order has duplicate runbook ids")
        self.order = tuple(order)

    def rank(self, query: str) -> list[Candidate]:
        return [
            Candidate(runbook_id, {"static": i}, 0.0, i)
            for i, runbook_id in enumerate(self.order, start=1)
        ]
