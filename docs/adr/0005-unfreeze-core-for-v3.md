# ADR-0005: Unfreeze incident_commander/ for v3.0, commander.py only

## Status
Accepted (owner approved P1 and P3 on 2026-10-21)

## Date
2026-10-21

## Context
`incident_commander/` was frozen at tag `v1.0` so the graded build stayed exactly as submitted. The hub
(`ic_hub`) needs two things it cannot get from outside: custom runbooks passed through `Commander`, and a way to
watch trace events as they happen. A `SimWorld` subclass covers the rest.

A branch `submission` was cut from `main` (commit 37aaa6b, core identical to `v1.0`) for the course submission,
so the graded code stays reachable after this change.

## Decision
Only `incident_commander/commander.py` changes (EXTENSION_PLAN.md items 35-37):
- `Commander.run(alert, *, fix_outcome, runbooks=None, on_event=None)`. `runbooks=None` means the fixture
  `RUNBOOKS`; the mapping is passed to `investigate` and used for the action and the postmortem draft.
- `Trace(data_clock, control_clock, on_event=None)`. The observer is called with each event after it is
  appended. It cannot change or remove events; an exception it raises propagates.

Nothing else changes: no config values, no decision logic, no new imports other than `collections.abc`.
The X1 gate is re-baselined (P3): the core may differ from `v2.3` in `commander.py` only, and once tag `v3.0`
exists the core must equal `v3.0`. The `v1.0` to `v2.3` core diff stays empty and is still tested.

## Alternatives considered
- Keep the core frozen and copy the commander into the hub: rejected, it would duplicate decision logic.
- A pluggable-core refactor of several modules: rejected, larger risk to the graded behaviour.

## Consequences
Default behaviour equals v1.0: tests compare default and explicit `RUNBOOKS` runs event by event, and
DECISION lines must stay identical to `traces/run.txt`. A ranker must match the runbook ids it is given;
a mismatch raises `ValueError` from the investigator instead of guessing.
