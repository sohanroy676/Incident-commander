# Progress

## Done

- v0.1 Foundations (PR #4 merged to main, tag `v0.1`, CI green): types, config, clocks, fixtures for the three demo alerts, SimWorld, five read-only tools, M1 `tools` command, G1 `dod purity`. 44 unittest tests, ruff clean, `traces/v0.1.txt` saved from a real run. 2026-10-18

## In progress

- v0.2 Investigator (branch `v0.2-investigator`, PR open, awaiting CI + review): `Tri`/`Runbook`/`Candidate`/`Verdict` types, runbook fixtures, `predicates.py`, `retrieval.py` (Ranker + StaticRanker), `investigator.py` (ToolBox without get_logs, coverage-first/exploratory planner, stale refetch), `investigate <ALERT>` command. 106 unittest tests, ruff clean, G1 passes, `traces/v0.2.txt` saved from real runs. DECISION lines: 9001 matched RB-101 rounds=3; 9002 matched RB-102 rounds=3; 9003 no_confident_match rounds=4 reason=all_refuted. 2026-10-18
- Not done until the user approves: merge to main and tag `v0.2`.

## Next

- v0.3 Gates (`v0.3-gates`): blast-radius classifier, approval gate with real clock and escalation, idempotent executor.
