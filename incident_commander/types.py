"""Frozen dataclasses shared across the graded build (PHASE5 section 7.1)."""

from __future__ import annotations

from dataclasses import dataclass


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
