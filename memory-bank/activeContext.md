# Active Context

## Current focus
v0.4 MVP-1 is implemented and committed on branch `v0.4-mvp1` (6 commits, tests/lint/G1 green, `traces/v0.4.txt` saved).
Not yet merged, pushed or tagged: needs the user's approval for each step.

## Recent decisions
- Specs came from docs/PHASE1-5.md (now committed). Deviations from PHASE5 are listed in docs/THRESHOLDS.md
  ("Fixture choices that go beyond PHASE5"): inventory-service error rate 0.010, extra `Observation.baseline`
  field, alerts one day apart, golden-set services deferred to v0.6.
- `ruff.toml` excludes `docs/`: this ruff version rewrites Python code blocks inside Markdown.
- CI: guards for tests/ and dod.py removed; the DoD step runs `dod purity` (only G1 exists). Switch it to
  `dod all` in v1.0. The tests_plus guard stays until v1.1.
- CHANGELOG.md left alone: no generator (git-cliff / conventional-changelog) is installed.
- Dev env: `.venv` on Python 3.12.3, scikit-learn 1.9.1 (gitignored).

- v0.2 choices beyond PHASE5 are in docs/THRESHOLDS.md ("Choices that go beyond PHASE5 (v0.2)"): post-loop verdict check,
  no refetch on tool error, ambiguous stops the loop at once, constant series is not a trend.
- `report.recent_median` moved to `predicates.recent_median` (report imports it).

- Workflow preference (from the user, 2026-10-18): from v0.3 on, try branch -> commit -> merge locally without a PR when viable; still ask before pushing/merging/tagging.

- v0.3 choices are in docs/THRESHOLDS.md ("Choices that go beyond PHASE5 (v0.3)"). `ControlClock.sleep` loops until
  monotonic time has really advanced (Windows early return); `Page` takes an optional `escalate_to`; the gate polls
  with `min(elapsed, deadline)` so a late tick cannot drop an in-time answer.
- Gotcha: never call `SimWorld.latency_points` with start=0 in tests (builds ~29M grid points); use windows near `fired_at`.

- v0.4 choices are in docs/THRESHOLDS.md ("Choices that go beyond PHASE5 (v0.4)"): `verify(service, metric, ...)` plus pure `assess`,
  `Executor(outcome=...)`, `run --all` runs all cases first and prints sections from them, `notified` is a list.
- Gotcha: Bash heredocs fail with apostrophes (use the Write tool); never write temp files to `/`, use the scratchpad dir.

## Blockers / open questions
- Install git-cliff (or similar) to regenerate CHANGELOG.md? (none installed; CHANGELOG still empty)

## Next step
Merge `v0.4-mvp1` (approval needed), push, wait for CI, tag `v0.4`; switch CI to `dod trace` once it exists. Then v0.5 (`v0.5-retrieval`): hybrid ranker.
