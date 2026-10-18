# Progress

## Done

- v0.1 Foundations (PR #4 merged to main, tag `v0.1`, CI green): types, config, clocks, fixtures for the three demo alerts, SimWorld, five read-only tools, M1 `tools` command, G1 `dod purity`. 44 unittest tests, ruff clean, `traces/v0.1.txt` saved from a real run. 2026-10-18
- v0.2 Investigator (PR #6 merged to main, tag `v0.2`, CI green): `Tri`/`Runbook`/`Candidate`/`Verdict` types, runbook fixtures, `predicates.py`, `retrieval.py` (Ranker + StaticRanker), `investigator.py` (ToolBox without get_logs, coverage-first/exploratory planner, stale refetch), `investigate <ALERT>` command. 106 unittest tests, ruff clean, G1 passes, `traces/v0.2.txt` from real runs. DECISION lines: 9001 matched RB-101 rounds=3; 9002 matched RB-102 rounds=3; 9003 no_confident_match rounds=4 reason=all_refuted. 2026-10-18

- v0.3 Gates (branch `v0.3-gates` merged to main locally without a PR, pushed, CI green, tag `v0.3`): `blast_radius.py`, `approval.py` (Page, ScriptedResponder, ApprovalGate, ApprovalToken), `executor.py` (ledger, ApprovalRequired), `SimWorld.apply_remediation` + fixture effects, `gates` command. 154 unittest tests, ruff clean, G1 passes, `traces/v0.3.txt` from a real run. `ControlClock.sleep` now loops until the monotonic clock has advanced the full duration (Windows `time.sleep` returned ~9 ms early). 2026-10-18

- v0.4 MVP-1 (branch `v0.4-mvp1` merged to main locally without a PR, pushed, CI green, tag `v0.4`): `verifier.py`, `postmortem.py`, `commander.py` (state machine, Case, append-only Trace), `report.py` formatters, `run <ALERT>` / `run --all` (M1-M8, fix_fails variant, M8 placeholder). 201 unittest tests, ruff clean, G1 passes, `traces/v0.4.txt` from a real run. 2026-10-18

- v0.5 Hybrid retrieval (merged to main, tagged `v0.5`): `bm25_scores`, `rrf`, `HybridRanker` in `retrieval.py`, real runbook text and follow_ups, M2 table in `report.py` and `run --all`. 217 unittest tests, ruff clean, G1 passes, `traces/v0.5.txt` from a real run; DECISION lines identical to v0.4. 2026-10-18

- v0.6 Evaluation (branch `v0.6-evaluation` merged to main, pushed, CI green, tag `v0.6`): `evaluate.py` (`run_golden`, `attack_differential`, `naive_baseline`), `fixtures/golden.py` (G-1..G-3, 3 attack variants), `SimWorld(planted_logs=)`, `evaluate` and `naive` commands, real M8 in `run --all`. 239 unittest tests, ruff clean, G1 passes, `traces/v0.6.txt` from a real run on Python 3.12.10 / scikit-learn 1.9.1; earlier DECISION lines identical to v0.5. Golden 3/3, attack unchanged, naive wrong on 4 of 6. 2026-10-18

- v1.0 Graded release (branch `v1.0-graded`; NOT yet merged, pushed or tagged): `dod.py` now has `trace <file>` (G5), `repro` (G6) and `all` (G1-G6 table); `run` exits 1 when M8 fails; `tests/test_invariants.py` (G2), `tests/test_outcomes.py` (G3), `tests/test_canaries.py` (9 canaries); full README; v1.0 section in docs/THRESHOLDS.md; CI runs `dod all`; real `traces/run.txt` (`run --all`, 112 lines, G5 passes, DECISION lines identical to v0.6). 301 unittest tests (about 3 minutes), ruff clean, `dod all` passes in the repo and in a fresh clone with an almost empty environment, on Python 3.12.10 / scikit-learn 1.9.1. 2026-10-18

## In progress

- v1.0 awaiting your approval to merge locally (--no-ff), push, wait for CI, then tag `v1.0`. After the tag the graded package `incident_commander/` is frozen. Next: v1.1 Extension scaffold.
