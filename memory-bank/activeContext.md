# Active Context

## Current focus
v2.2 hub core is merged to main and pushed; tag `v2.2` waits for green CI. P2 is approved. Older focus: v2.0 extended release is merged to main, pushed, CI green and tagged `v2.0`. `incident_commander/` stays frozen (tag `v1.0`). All planned versions are done; remaining work is submission and viva rehearsal (docs/DEMO.md).

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

## Extension plan review (2026-10-20)
docs/EXTENSION_PLAN.md was verified against the code and corrected (versions now v2.1, v2.2 hub core, v2.3 hub extras, v3.0). Pending owner approval (section 0 there): v3.0 unfreeze, "Portfolio scope (v2.1+)", X1 re-baseline, Pages demo, new predicates, license holder. Item 6 reframed: no fake clock or patched sleep (rule), use shorter real deadlines and parallel CI jobs. Baseline: `dod all` PASS 53 s, tests 301 OK 178 s, tests_plus 153 OK 353 s. Docs only; no code changed, nothing committed (EXTENSION_PLAN.md is still untracked; `.claude/settings.json` change left alone). There is no `.clinerules/` in this repo.

## v2.1 polish (2026-10-20)
P6 answered: no license yet (holder would be Sohan Roy Talari). No LICENSE file, no license field or badge; item 1 stays pending. v2.1 is docs and CI only; see progress.md. The new CI workflow has not run on GitHub yet (not pushed): check the shard jobs, `actions/upload-artifact` with `include-hidden-files`, and the coverage merge on the first push. mypy and bandit baselines are documented in `ci.yml`.

## Next step
No version is planned. Optional: a hosted free-tier live trace (key in `.env`, limits unchecked); install git-cliff to generate CHANGELOG.md. `git diff v1.0 -- incident_commander/` must stay empty. v2.0 gotchas: the cli approver needs `--deadline 20` for a human; live Ollama (llama3.2) `evaluate` takes about 90 s; local branches v1.3-roles, docs/v1.3-status and v2.0-release await your confirmation to delete.
v1.3 choices are in docs/THRESHOLDS.md ("Choices that go beyond PHASE5 (v1.3)"): `ic_plus run` does not apply advisor advice (only `evaluate` does, via `x3.advised_orders`, a temporary wrapper around the frozen `investigate`); explainer is free text (no JSON mode) capped at 600 characters; `guard_advice` pads partial lists to a permutation; free-tier limits of hosted providers were not checked.
v1.2 choices are in docs/THRESHOLDS.md ("Choices that go beyond PHASE5 (v1.2)"): `.env` only (no `--llm-key-file`), flags beat `.env`, narrator runs on separate identical cases after the graded `cmd_run`, narrative is printed by `ic_plus` (graded draft is frozen), guard limits.
Gotchas: `.claude/settings.json` has an uncommitted local change; leave it unless asked. Reading `.env` via Bash is denied by settings, so tests never depend on it (flags plus a patched `load_env`). `traces/v1.2-live.txt` and a v1.3 live trace (a real local or hosted model run, e.g. `evaluate --llm local`) are still pending and manual. Gotcha: `git merge` does not accept `-F -`; use `-m`. Heredoc-appended text to CRLF Python files leaves mixed endings (normalise with a patch script).

## v2.2 hub (2026-10-20)
`ic_hub/` is built (see progress.md and docs/THRESHOLDS.md "v2.2, ic_hub"). Gotchas: the hub token is embedded as a `<meta>` tag (placeholder `__HUB_TOKEN__` in `index.html`); a test forbids HTML sinks in `app.js`, even in comments; golden alerts are ALRT-9101..9103 (G-1..G-3 are golden ids, not alert ids); ALRT-9002 has 4 DECISION lines in `case_decision_lines`. Open: README rewrite (after the v2.2 tag), P1/P3/P4/P5 still pending. mypy is clean and gating (`mypy ic_plus ic_hub`); merged local branches were deleted.
