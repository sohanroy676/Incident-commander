"""Bounded, hypothesis-driven evidence loop (PHASE5 7.6, PHASE4 8.1-8.4).

Each round is one tool call (a stale refetch is its own round). Retrieval rank is
only a tie-break; a verdict comes from predicates over typed evidence, never text.
The toolbox holds the four evidence tools, so `get_logs` is absent by construction.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from .clocks import DataClock
from .config import LOOKBACK_S, ROUND_BUDGET, TOOL_SPECS
from .fixtures.runbooks import RUNBOOKS
from .predicates import PREDICATES, evaluate
from .retrieval import Ranker
from .tools import get_dependencies, get_deployments, get_error_rate, get_latency
from .types import Alert, Observation, Runbook, Tri, Verdict
from .world import SimWorld

EVIDENCE_TOOLS: tuple[str, ...] = tuple(n for n, s in TOOL_SPECS.items() if s.evidence)

OPEN, CONFIRMED, REFUTED = "open", "confirmed", "refuted"


class TraceSink(Protocol):
    def emit(self, kind: str, **fields: object) -> None: ...


class NullTrace:
    def emit(self, kind: str, **fields: object) -> None:
        pass


class ToolBox:
    """The Investigator's tools: latency, error_rate, deployments, dependencies. No logs."""

    names = EVIDENCE_TOOLS

    def __init__(self, world: SimWorld, clock: DataClock) -> None:
        self._world = world
        self._clock = clock

    def call(self, tool: str, service: str, fired_at: float) -> Observation:
        start, end = fired_at - LOOKBACK_S, fired_at
        w, c = self._world, self._clock
        if tool == "get_latency":
            return get_latency(w, c, service, start, end)
        if tool == "get_error_rate":
            return get_error_rate(w, c, service, start, end)
        if tool == "get_deployments":
            return get_deployments(w, c, service, start, end)
        if tool == "get_dependencies":
            return get_dependencies(w, c, service, end)
        raise KeyError(f"tool not available to the investigator: {tool}")


@dataclass(frozen=True)
class Hypothesis:
    runbook_id: str
    signature: tuple[str, ...]
    status: str  # open | confirmed | refuted
    undetermined: tuple[str, ...]


@dataclass(frozen=True)
class RoundRecord:
    n: int
    tool: str
    mode: str  # coverage | exploratory | refetch
    fresh: bool
    status: str  # ok | error
    values: Mapping[str, Tri]  # this tool's predicates after the call


@dataclass(frozen=True)
class InvestigationResult:
    verdict: Verdict
    hypotheses: dict[str, Hypothesis]
    observations: tuple[Observation, ...]
    rounds: tuple[RoundRecord, ...]


def _hypotheses(runbooks: Mapping[str, Runbook], table: Mapping[str, Tri]) -> dict[str, Hypothesis]:
    out = {}
    for rb in runbooks.values():
        values = [table[p] for p in rb.signature]
        if Tri.FALSE in values:
            status = REFUTED
        elif all(v is Tri.TRUE for v in values):
            status = CONFIRMED
        else:
            status = OPEN
        undetermined = tuple(p for p in rb.signature if table[p] is Tri.UNKNOWN)
        out[rb.runbook_id] = Hypothesis(rb.runbook_id, rb.signature, status, undetermined)
    return out


def next_tool(
    hypotheses: Mapping[str, Hypothesis],
    called: set[str],
    ranks: Mapping[str, int],
    tool_order: tuple[str, ...],
) -> tuple[str, str] | None:
    """(tool, mode), or None when every tool has been called.

    Coverage: the uncalled tool answering an undetermined predicate of the most live
    hypotheses; tie-break 1 best retrieval rank among them, tie-break 2 fixed tool order.
    Exploratory: nothing left to test, so the next uncalled tool in fixed order.
    """
    live = [h for h in hypotheses.values() if h.status != REFUTED]
    best: tuple[int, int, int] | None = None
    best_tool = ""
    for order_index, tool in enumerate(tool_order):
        if tool in called:
            continue
        answering = [h for h in live if any(PREDICATES[p].tool == tool for p in h.undetermined)]
        if not answering:
            continue
        key = (-len(answering), min(ranks[h.runbook_id] for h in answering), order_index)
        if best is None or key < best:
            best, best_tool = key, tool
    if best is not None:
        return best_tool, "coverage"
    for tool in tool_order:
        if tool not in called:
            return tool, "exploratory"
    return None


def _verdict(hypotheses: Mapping[str, Hypothesis], rounds: int) -> Verdict:
    confirmed = [h.runbook_id for h in hypotheses.values() if h.status == CONFIRMED]
    if len(confirmed) == 1:
        return Verdict("matched", confirmed[0], rounds, None)
    if len(confirmed) > 1:
        return Verdict("no_confident_match", None, rounds, "ambiguous_match")
    if all(h.status == REFUTED for h in hypotheses.values()):
        return Verdict("no_confident_match", None, rounds, "all_refuted")
    return Verdict("no_confident_match", None, rounds, "insufficient_evidence")


def _ranks(ranker: Ranker, alert: Alert, runbooks: Mapping[str, Runbook]) -> dict[str, int]:
    candidates = ranker.rank(alert.summary)
    unknown = [c.runbook_id for c in candidates if c.runbook_id not in runbooks]
    if unknown:
        raise ValueError(f"ranker returned unknown runbook ids: {unknown}")
    ranks = {c.runbook_id: c.rank for c in candidates}
    return {rid: ranks.get(rid, len(runbooks) + 1) for rid in runbooks}


def investigate(
    alert: Alert,
    ranker: Ranker,
    tools: ToolBox,
    budget: int = ROUND_BUDGET,
    trace: TraceSink | None = None,
    runbooks: Mapping[str, Runbook] = RUNBOOKS,
    tool_order: tuple[str, ...] = EVIDENCE_TOOLS,
) -> InvestigationResult:
    trace = trace or NullTrace()
    ranks = _ranks(ranker, alert, runbooks)
    table: dict[str, Tri] = {p: Tri.UNKNOWN for p in PREDICATES}
    hypotheses = _hypotheses(runbooks, table)
    observations: list[Observation] = []
    rounds: list[RoundRecord] = []
    called: set[str] = set()

    def run_round(tool: str, mode: str, shown: tuple[str, ...]) -> Observation:
        nonlocal hypotheses
        obs = tools.call(tool, alert.service, alert.fired_at)
        observations.append(obs)
        for pred_id, pred in PREDICATES.items():
            if pred.tool == tool:
                table[pred_id] = evaluate(pred_id, obs, obs.baseline, alert.fired_at)
        values = {p: table[p] for p, pr in PREDICATES.items() if pr.tool == tool}
        n = len(rounds) + 1
        rounds.append(RoundRecord(n, tool, mode, obs.fresh, obs.status, values))
        fields = {p: table[p].name for p in shown}
        if obs.status != "ok":
            fields["status"] = obs.status
        trace.emit("ROUND", n=n, tool=tool, mode=mode, fresh=obs.fresh, **fields)
        hypotheses = _hypotheses(runbooks, table)
        trace.emit("HYPOTHESES", **{rid: h.status for rid, h in hypotheses.items()})
        return obs

    while len(rounds) < budget:
        if any(h.status == CONFIRMED for h in hypotheses.values()):
            break
        pick = next_tool(hypotheses, called, ranks, tool_order)
        if pick is None:
            break
        tool, mode = pick
        live_preds = {p for h in hypotheses.values() if h.status != REFUTED for p in h.signature}
        shown = tuple(
            p
            for p, pr in PREDICATES.items()
            if pr.tool == tool and (mode == "exploratory" or p in live_preds)
        )
        obs = run_round(tool, mode, shown)
        called.add(tool)
        # a stale answer costs one refetch round; an errored tool is not retried
        if obs.status == "ok" and not obs.fresh and len(rounds) < budget:
            run_round(tool, "refetch", shown)

    return InvestigationResult(
        _verdict(hypotheses, len(rounds)), hypotheses, tuple(observations), tuple(rounds)
    )
