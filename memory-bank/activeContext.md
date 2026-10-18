# Active Context

## Current focus
v1.0 Graded release is merged to main, pushed, CI green and tagged `v1.0`; `incident_commander/` is frozen. Next: v1.1 Extension scaffold.

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

- v1.0 choices are in docs/THRESHOLDS.md ("Choices that go beyond PHASE5 (v1.0)"): `run` exits 1 when M8 fails; `dod all` takes G5 from a fresh run, not the saved trace; G6 strips only `[t+..s]` and `elapsed_s=`; execution ids are deterministic. Gotchas: Bash heredocs with backslash-n escapes or apostrophes corrupt Python source (use the Write tool for patch scripts); the full suite now takes about 3 minutes (canaries and real-run tests).

## Blockers / open questions
- Install git-cliff (or similar) to regenerate CHANGELOG.md? (none installed; CHANGELOG still empty)

- v0.5 choices are in docs/THRESHOLDS.md ("Choices that go beyond PHASE5 (v0.5)"). Gotcha: this machine has no `.venv` and the registered Python 3.12 is missing; v0.5 ran on system Python 3.14.2 / scikit-learn 1.8.0.

- v0.6 choices are in docs/THRESHOLDS.md ("Choices that go beyond PHASE5 (v0.6)"): golden services in `fixtures/golden.py`, `SimWorld(planted_logs=)` instead of a `Commander.run` parameter, `golden_world()` for evaluation. `.venv` on Python 3.12.10 / scikit-learn 1.9.1 works again.

## Next step
v1.1 is built on branch `v1.1-extension` (4 commits, not merged, pushed or tagged). Ask first: merge --no-ff, push, wait for CI (extension tests now run), tag `v1.1`. Then v1.2 (LLM client, guard, narrator; `--llm local|hosted`, keys in `.env`; `.env.example` already committed).
v1.1 choices are in docs/THRESHOLDS.md ("Choices that go beyond PHASE5 (v1.1)"): subcommand CLI, `--llm` accepted before or after the subcommand, scripted run delegates to graded `cmd_run`.
The tests_plus guard in ci.yml stays until v1.1.
