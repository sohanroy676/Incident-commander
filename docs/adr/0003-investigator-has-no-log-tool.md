# ADR-0003: The investigator has no log tool

## Status
Proposed

## Date
2026-10-20

## Context
Logs are free text written by other systems and can carry instructions ("do not roll back"). The evaluation
plants such a line and requires the verdict and remediation to stay unchanged.

## Decision
`get_logs` exists in `tools.py` so logs can be shown in the trace and postmortem as labelled untrusted context,
but the investigator's `ToolBox` does not expose it. Predicates read only metrics, deployments and topology.

## Alternatives considered
- Let the investigator read logs and sanitize them: rejected. Sanitizing free text is an arms race, and a
  structural guarantee is easier to verify.
- Drop `get_logs` entirely: rejected. The trace and postmortem would lose useful, clearly labelled context.

## Consequences
The planted-log attack is unchanged by construction, and the differential check in `evaluate` can assert it.
The agent cannot use log evidence even when it would help; that trade-off is accepted.
