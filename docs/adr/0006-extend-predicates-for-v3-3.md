# ADR-0006: Extend the predicate registry for v3.3, predicates.py only

## Status
Accepted (owner approved P5 on 2026-10-21)

## Date
2026-10-21

## Context
The hub's runbook editor lets people write their own signatures, but the nine predicates only describe
latency shapes and a dependency that is unhealthy. A custom runbook cannot say "error rate jumped in one
step" or "dependencies are fine". ADR-0005 unfroze `commander.py` only, so adding predicates needs its own
decision (EXTENSION_PLAN.md item 40, P5).

## Decision
Only `incident_commander/predicates.py` changes, and only by addition:
- `error_step_change` and `error_gradual_trend` on `get_error_rate`: the same numeric tests as the latency
  versions (the step test uses `ERROR_NORMAL_RATIO` for "quiet before"; the trend test is shared).
- `dependency_healthy` on `get_dependencies`: the complement of `dependency_unhealthy` (no dependency at all is
  healthy).
- `latency_step_change` and `latency_gradual_trend` now call shared helpers; their results are unchanged.
- No new thresholds: tunables stay in `config.py`. Signature `(data, baseline, fired_at)` and numbers-only inputs
  are unchanged (tests/test_invariants.py).
- No built-in runbook uses the new predicates (a test enforces it), so no built-in decision can depend on them.
- `ic_hub/schema.py` gets one help line per new predicate (a test keeps its keys equal to `PREDICATES`).
- X1 is re-baselined: the core may differ from `v3.0` in `predicates.py` only, and once tag `v3.3` exists the core
  must equal `v3.3`. The v1.0 to v2.3 diff stays empty and is still tested.

## Alternatives considered
- Change a built-in runbook to use them: rejected, it would change graded decisions and the golden set.
- Keep the registry frozen and let the hub compute extra signals: rejected, it would duplicate predicate logic.

## Consequences
DECISION lines are identical to `traces/run.txt`. One ROUND trace line differs: an exploratory round lists every
predicate of the tool it called, so ALRT-9003's `get_dependencies` round now also shows `dependency_healthy`.
The saved `traces/run.txt` predates this; regenerate it from a real run (never by hand) if it should match.
