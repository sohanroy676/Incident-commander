"""Frozen dataclasses shared across the graded build (PHASE5 section 7.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Tri(Enum):
    """Three-valued predicate result. UNKNOWN never confirms and never refutes."""

    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Alert:
    alert_id: str
    service: str
    fired_at: float
    severity: str
    metric: str
    summary: str


@dataclass(frozen=True)
class ToolSpec:
    """A tool's declared freshness budget and the lag of its simulated data."""

    max_staleness_s: int
    lag_s: float
    evidence: bool


@dataclass(frozen=True)
class Observation:
    tool: str
    service: str
    start: float
    end: float
    data: tuple
    as_of: float
    max_staleness_s: int
    status: str  # "ok" | "error"
    age_s: float
    fresh: bool
    error: str | None = None
    baseline: float | None = None  # latency_ms / error_rate baseline, where the tool has one


@dataclass(frozen=True)
class Runbook:
    runbook_id: str
    title: str
    text: str  # retrieval input only; the Investigator tests `signature`
    signature: tuple[str, ...]  # predicate ids, all must be TRUE
    action: str
    follow_ups: tuple[str, ...] = ()


@dataclass(frozen=True)
class Candidate:
    runbook_id: str
    ranks: dict[str, int]
    fused_score: float
    rank: int


@dataclass(frozen=True)
class Verdict:
    kind: str  # "matched" | "no_confident_match"
    runbook_id: str | None
    rounds: int
    reason: str | None  # all_refuted | insufficient_evidence | ambiguous_match


@dataclass(frozen=True)
class Classification:
    action: str
    tier: str  # "low" | "high"
    requires_approval: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ApprovalToken:
    """Structural guard created only inside the approval gate; not a cryptographic credential."""

    action: str
    service: str
    approved_by: str
    approved_at: float


@dataclass(frozen=True)
class Execution:
    execution_id: str
    key: tuple
    action: str
    service: str
    executed_at: float


@dataclass(frozen=True)
class Verification:
    status: str  # "resolved" | "reopened"
    verified: bool
    metric: str
    baseline: float | None
    observed: float | None
    reason: str | None = None


@dataclass(frozen=True)
class TraceEvent:
    seq: int
    kind: str
    data_time: float  # simulated DataClock seconds
    elapsed_s: float  # real seconds since process start
    fields: tuple[tuple[str, object], ...]


@dataclass(frozen=True)
class PostmortemDraft:
    """Pure data built from a trace; `published` and `notified` change only through publish()."""

    summary: str
    impact: str
    detection: str
    evidence: tuple[str, ...]
    remediation: str
    approval_history: tuple[str, ...]
    verification: str
    timeline: tuple[str, ...]
    untrusted_log_excerpts: tuple[str, ...]
    follow_ups: tuple[str, ...]
    notified: list[str] = field(default_factory=list)
    published: bool = False
