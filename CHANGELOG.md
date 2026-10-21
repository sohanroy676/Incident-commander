# Changelog

All notable changes to this project are documented here.
Generated from Conventional Commits with git-cliff; do not hand-edit.
## [Unreleased]

### Documentation
- Record the v3.0 and v3.1 releases in the memory bank
- **license**: Add MIT license
## [v3.1] - 2026-10-21

### Features
- **hub**: Stream the live trace while a run is in progress
- **hub**: Add a runbook editor with validated custom sets
## [v3.0] - 2026-10-21

### Documentation
- Record the v2.3 release in the memory bank
- **readme**: Add hub hero GIF

### Features
- **commander**: Add runbooks and on_event hooks for v3.0
## [v2.3] - 2026-10-21

### Documentation
- **readme**: Rewrite pitch, add hub section and badges
- Record v2.3 intake and polish choices

### Features
- **hub**: Add evidence chart, what-if toggles and run diff
- **hub**: Add evaluate view and explain box
- **hub**: Add opt-in run history and hash-chained audit log
- **hub**: Add Alertmanager intake, metrics and approval stream
- **hub**: Add metrics strip, intake form, dark mode and shortcuts

### Tests
- **hub**: Add dev-only Playwright smoke script
- **hub**: Close the stream response so the server sees the client leave
## [v2.2] - 2026-10-20

### Documentation
- Record v2.1 merged and P2 approved
- Record v2.2 hub choices and progress

### Features
- **hub**: Add local ic_hub web hub (v2.2 core)

### Fixes
- **types**: Clear mypy errors in ic_plus and ic_hub
## [v2.1] - 2026-10-20

### Chores
- **build**: Add pyproject.toml with console scripts

### Documentation
- Record v2.0 merge and tag
- **readme**: Add full quick start from clone
- **readme**: Fix Tests section and trim overlap
- **plan**: Verify and correct the extension plan
- Add SECURITY.md and CONTRIBUTING.md
- **adr**: Propose ADRs 0002-0004
- Add ARCHITECTURE.md and architecture diagram
- **memory-bank**: Record v2.1 progress
- **memory-bank**: Fix v2.1 merge status

### Ci
- Add coverage, mypy, bandit, pip-audit; parallel jobs
- Shard tests by module and merge coverage
## [v2.0] - 2026-10-18

### Chores
- Add v2.0 and live model traces

### Documentation
- Record v1.3 merge and tag
- Add demo scripts and extended-build README

### Tests
- **ic_plus**: Add release gate checks X1-X4
## [v1.3] - 2026-10-18

### Chores
- Add v1.3 traces (llm unavailable runs)

### Documentation
- Record v1.2 merge and tag
- Record v1.3 choices in THRESHOLDS

### Features
- **ic_plus**: Add advisor guard
- **ic_plus**: Add explainer role and explain command
- **ic_plus**: Add advisor role
- **ic_plus**: Prove X3 with all roles on

### Fixes
- **ic_plus**: Trace llm_unavailable after the server is down
## [v1.2] - 2026-10-18

### Chores
- Add v1.2 trace (llm unavailable run)

### Documentation
- Record v1.1 merge and tag
- Record v1.2 choices in THRESHOLDS

### Features
- **ic_plus**: Add stdlib .env parser
- **ic_plus**: Add never-raising LLM client
- **ic_plus**: Add deterministic narrative guard
- **ic_plus**: Add LLM narrator with template fallback
- **ic_plus**: Wire --llm local|hosted with narrator
## [v1.1] - 2026-10-18

### Chores
- **traces**: Save the real v1.1 run trace
- Add .env.example template

### Documentation
- Record v1.0 merge and tag
- Record v1.1 status

### Features
- **ic_plus**: Add interactive CLI approver
- **ic_plus**: Add entry point and extra scenarios

### Ci
- Note that extension tests now run
## [v1.0] - 2026-10-18

### Chores
- **traces**: Save the real v1.0 run trace

### Documentation
- Record v0.6 as merged, CI green and tagged
- Write the v1.0 README and record v1.0 choices
- Record v1.0 status in roadmap and memory bank

### Features
- **dod**: Add trace, repro and all gates

### Fixes
- **cli**: Exit non-zero when run's evaluation section fails

### Tests
- **invariants**: Add G2 structural honesty suite
- **outcomes**: Add G3 exact-value outcome suite
- **canaries**: Add gate canaries and dod all tests

### Ci
- Run all six Definition-of-Done gates
## [v0.6] - 2026-10-18

### Chores
- **traces**: Save v0.6 trace

### Documentation
- Record v0.6 evaluation choices and progress

### Features
- **fixtures**: Add golden set and planted-log attack variants
- **evaluate**: Add golden set, differential attack, naive baseline
- **cli**: Add evaluate and naive commands, real M8 in run
## [v0.5] - 2026-10-18

### Chores
- **traces**: Save v0.5 trace

### Documentation
- Mark v0.4 tagged and record handoff
- Record v0.5 retrieval choices and progress

### Features
- **retrieval**: Add BM25, RRF and HybridRanker
- **fixtures**: Write runbook text corpus and follow-ups
- **cli**: Show hybrid retrieval scores in run M2
## [v0.4] - 2026-10-18

### Chores
- **traces**: Save v0.4 trace and update docs

### Features
- **executor**: Pass remediation outcome to world
- **verifier**: Verify the alert metric after a fix
- **postmortem**: Add pure draft and explicit publish
- **commander**: Add state machine, case and trace
- **cli**: Add run command for M1-M8
## [v0.3] - 2026-10-17

### Chores
- **traces**: Save v0.3 trace and update docs

### Documentation
- Mark v0.3 tagged and record handoff

### Features
- **gates**: Add blast-radius classifier
- **gates**: Add time-boxed approval gate
- **world**: Add remediation effects
- **gates**: Add idempotent executor
- **cli**: Add gates command
## [v0.2] - 2026-10-17

### Chores
- **traces**: Save v0.2 trace and update memory bank

### Documentation
- Mark v0.1 merged and tagged
- Record v0.2 choices and roadmap status
- Mark v0.2 done and record handoff

### Features
- **types**: Add Tri, Runbook, Candidate, Verdict and runbook fixtures
- **predicates**: Add three-valued numeric predicates
- **retrieval**: Add Ranker protocol and StaticRanker
- **investigator**: Add bounded 4-round evidence loop
- **cli**: Add investigate command
## [v0.1] - 2026-10-17

### Chores
- Migrate Cline config to Claude Code and fix CI
- Add ruff config and README stub

### Documentation
- Add PHASE1-5 design specs
- Record v0.1 progress and project patterns
- Log v0.1 in progress.md

### Features
- **world**: Add types, config, clocks and simulated fixtures
- **tools**: Add five read-only signal tools and M1 output
- **dod**: Add G1 purity gate

### Fixes
- **ci**: Add requirements files and skip steps until code exists
- **ci**: Run G1 purity until dod all exists
