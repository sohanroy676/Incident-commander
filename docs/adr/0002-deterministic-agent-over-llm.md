# ADR-0002: Deterministic agent over an LLM agent

## Status
Proposed

## Date
2026-10-20

## Context
The graded build must reproduce exact acceptance values (ALRT-9001/9002/9003, approval priya to devon,
195 ms resolved / 3900 ms reopened) on every run, with no keys, no network and no environment variables.
An LLM that reads logs is also open to indirect prompt injection, which the planted-log attack tests directly
(docs/PHASE3.md).

## Decision
Every decision (verdict, remediation tier, approval, verification) comes from typed evidence and fixed rules
in `incident_commander/`. An LLM exists only in the optional `ic_plus` package, in narrator, explainer and
advisor roles. Its replies pass a deterministic guard and fall back to a template. It never makes or changes a decision.

## Alternatives considered
- LLM-driven investigator: rejected. Results vary between runs, the exact acceptance values are no longer
  guaranteed, and it needs keys or network access.
- LLM as tie-breaker inside the core: rejected. It breaks the purity gate (G1) and the log-injection guarantee.

## Consequences
Runs are reproducible and diffable (`traces/run.txt`, DECISION lines identical with the LLM on or off).
The cost is less flexibility: new alert types need new fixtures and runbooks instead of a prompt.
