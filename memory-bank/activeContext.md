# Active Context

## Current focus
v0.1 Foundations is done: merged to main via PR #4, tag `v0.1` pushed, CI green. Starting v0.2 next.

## Recent decisions
- Specs came from docs/PHASE1-5.md (now committed). Deviations from PHASE5 are listed in docs/THRESHOLDS.md
  ("Fixture choices that go beyond PHASE5"): inventory-service error rate 0.010, extra `Observation.baseline`
  field, alerts one day apart, golden-set services deferred to v0.6.
- `ruff.toml` excludes `docs/`: this ruff version rewrites Python code blocks inside Markdown.
- CI: guards for tests/ and dod.py removed; the DoD step runs `dod purity` (only G1 exists). Switch it to
  `dod all` in v1.0. The tests_plus guard stays until v1.1.
- CHANGELOG.md left alone: no generator (git-cliff / conventional-changelog) is installed.
- Dev env: `.venv` on Python 3.12.3, scikit-learn 1.9.1 (gitignored).

## Blockers / open questions
- Install git-cliff (or similar) to regenerate CHANGELOG.md? (none installed; CHANGELOG still empty)

## Next step
v0.2 Investigator (`v0.2-investigator`): predicates, planner, bounded
4-round loop, StaticRanker (deliberately wrong-first), `investigate` command, tests, `traces/v0.2.txt`.
