# Active Context

## Current focus
v0.1 Foundations is built and committed on branch `v0.1-foundations`, awaiting user review. Not pushed, merged or tagged.

## Recent decisions
- Specs came from docs/PHASE1-5.md (now committed). Deviations from PHASE5 are listed in docs/THRESHOLDS.md
  ("Fixture choices that go beyond PHASE5"): inventory-service error rate 0.010, extra `Observation.baseline`
  field, alerts one day apart, golden-set services deferred to v0.6.
- `ruff.toml` excludes `docs/`: this ruff version rewrites Python code blocks inside Markdown.
- CI `if: hashFiles(...)` guards stay: tests_plus/ arrives in v1.1 and `dod all` in v1.0.
  Remove them when each of those exists, not before.
- CHANGELOG.md left alone: no generator (git-cliff / conventional-changelog) is installed.
- Dev env: `.venv` on Python 3.12.3, scikit-learn 1.9.1 (gitignored).

## Blockers / open questions
- Merge `v0.1-foundations` to main and tag `v0.1`? Needs user approval (also push).
- Install git-cliff (or similar) to regenerate CHANGELOG.md?

## Next step
After v0.1 is merged and tagged: v0.2 Investigator (`v0.2-investigator`): predicates, planner, bounded
4-round loop, StaticRanker (deliberately wrong-first), `investigate` command, tests, `traces/v0.2.txt`.
