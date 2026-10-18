# Progress

## Done

- v0.1 Foundations (PR #4 merged to main, tag `v0.1`, CI green): types, config, clocks, fixtures for the three demo alerts, SimWorld, five read-only tools, M1 `tools` command, G1 `dod purity`. 44 unittest tests, ruff clean, `traces/v0.1.txt` saved from a real run. 2026-10-18
- v0.2 Investigator (PR #6 merged to main, tag `v0.2`, CI green): `Tri`/`Runbook`/`Candidate`/`Verdict` types, runbook fixtures, `predicates.py`, `retrieval.py` (Ranker + StaticRanker), `investigator.py` (ToolBox without get_logs, coverage-first/exploratory planner, stale refetch), `investigate <ALERT>` command. 106 unittest tests, ruff clean, G1 passes, `traces/v0.2.txt` from real runs. DECISION lines: 9001 matched RB-101 rounds=3; 9002 matched RB-102 rounds=3; 9003 no_confident_match rounds=4 reason=all_refuted. 2026-10-18

- v0.3 Gates (branch `v0.3-gates` merged to main locally without a PR, pushed, CI green, tag `v0.3`): `blast_radius.py`, `approval.py` (Page, ScriptedResponder, ApprovalGate, ApprovalToken), `executor.py` (ledger, ApprovalRequired), `SimWorld.apply_remediation` + fixture effects, `gates` command. 154 unittest tests, ruff clean, G1 passes, `traces/v0.3.txt` from a real run. `ControlClock.sleep` now loops until the monotonic clock has advanced the full duration (Windows `time.sleep` returned ~9 ms early). 2026-10-18

- v0.4 MVP-1 (branch `v0.4-mvp1` merged to main locally without a PR, pushed, CI green, tag `v0.4`): `verifier.py`, `postmortem.py`, `commander.py` (state machine, Case, append-only Trace), `report.py` formatters, `run <ALERT>` / `run --all` (M1-M8, fix_fails variant, M8 placeholder). 201 unittest tests, ruff clean, G1 passes, `traces/v0.4.txt` from a real run. 2026-10-18

## In progress

- Nothing. Next: v0.5 Hybrid retrieval (`v0.5-retrieval`).
