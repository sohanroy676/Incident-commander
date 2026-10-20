# Incident Commander: extension plan (v2.1 to v3.x)

Written 2026-10-18 from the v2.0 tag state. **Reviewed and corrected 2026-10-20** against the current code
(main at `e2a8ecb`). No project code was changed. Evidence tags: **[V]** verified in code (with `file:line`),
**[I]** inferred. Change markers from the review: **[CHANGED]** corrected or re-scoped, **[NEW]** added by the
review, **[PENDING]** needs owner approval before any work starts.

Review baseline (real runs, 2026-10-20): `dod all` G1-G6 PASS (53 s); `tests/` 301 OK (178 s);
`tests_plus/` 153 OK (353 s); `ruff` clean; `git diff v1.0 -- incident_commander/` empty.

---

## 0. Pending owner approval

Nothing below is decided. Work on these items does not start until the owner says so.

| # | Decision | Needed by |
|---|---|---|
| P1 | **v3.0 unfreeze** of `incident_commander/` (items 35-37 only) | before v3.0; after course submission and viva |
| P2 | **Portfolio scope (v2.1+)**: a new section in `projectBrief.md` / `ROADMAP.md` that allows a web UI, local persistence, exports and an intake adapter. The graded "Out of scope" list stays untouched | **APPROVED 2026-10-20** (owner) |
| P3 | **Re-baselining X1** (`tests_plus/test_release.py:41` diffs against `v1.0`) to a later tag when v3.0 lands | with P1 |
| P4 | **Public Pages demo** (item 41): publishes content outward | before item 41 |
| P5 | **Item 40** (new predicates): edits the frozen predicate registry, so it is a separate decision | before item 40 |
| P6 | **License choice and holder name** (item 1); owner to check whether the college claims rights over coursework | before item 1 |

---

## 1. Verdict on the plan's claims (re-checked 2026-10-20)

| Claim | Result | Evidence |
|---|---|---|
| `Commander.run` reads built-in `RUNBOOKS` directly | **True** [V] | `commander.py:19` import; `:191` `investigate(...)` has no `runbooks=`; `:207` `RUNBOOKS[verdict.runbook_id]`; `:299` `RUNBOOKS.get(...)` |
| `investigate()` already pluggable | **True** [V] | `investigator.py:159-160` `runbooks=RUNBOOKS`, `tool_order=EVIDENCE_TOOLS` |
| Only five service/action pairs change a signal | **True** [V] | `fixtures/services.py:76-82`; lookup `world.py:117`; unlisted pair unchanged `world.py:110`; unknown action `ValueError` `world.py:114` |
| Custom effects need no core change | **True** [V] | `executor.py:53` only calls `world.apply_remediation`; `Commander` takes `world` (`commander.py:137-149`) |
| Uploaded alerts/services possible | **True, with a caveat** [V] | `SimWorld(services=, alerts=, tool_lags=, planted_logs=)` `world.py:29-35`; `ServiceSpec.latency/error_rate` are callables `services.py:45-46` **[CHANGED: was 48-50]**, so JSON shapes (`flat`/`step`/`ramp`) are needed |
| Web approval without core change | **True** [V] | `Responder.poll(target, elapsed_s)` `approval.py:15-16`; `deadline_s`, `tick_s`, `control_clock` ctor args `commander.py:143-147`; default 0.3 s `config.py:20`. Deadline is **per page**, worst case 2 x deadline (`approval.py:104,119`) **[NEW]** |
| "Live run" timeline | **Replay unless a core hook is added** [V] | `Trace` created in `run()` `commander.py:172`; `Case` returned only after `run()` ends (`:209`) |
| Live progress **without** core change | **[NEW] Partly possible** [V] | A `SimWorld` subclass can report each tool read as it happens, and the `WebResponder` sees the page. Hypotheses and verdict still need the `on_event` hook (v3.0) |
| Custom runbook upload is limited | **True** [V] | Nine predicates `predicates.py:140-158`; four actions `config.py:56-61`; unknown action fails closed to high tier `blast_radius.py:11-13` |
| Guard works with uploaded names | **Plausible, unverified** [I] | `guard.py:31-34` built-ins only; identifier check only for hyphenated tokens `guard.py:95-97`; a non-hyphenated uploaded name gets only the number and instruction checks. Needs one test |
| Alert times on the 60 s grid | **True** [V] | `fixtures/alerts.py:7` **[CHANGED: was :8]** |
| `postmortem.render` exists; no JSON export | **True** [V] | `postmortem.py:106`; `Commander.publish` `commander.py:305` |
| Extra scenarios, explain, evaluate exist | **True** [V] | `ic_plus/scenarios.py:131`; `ic_plus/__main__.py:176-190` |
| No LICENSE, CONTRIBUTING, pyproject, Dockerfile; one ADR; empty CHANGELOG | **True** [V] | `docs/adr/` holds `0001` and a template |
| "Code is already fully annotated" | **False** [V] **[CHANGED]** | Unannotated defs in `predicates.py:39,57,70`, `tools.py:57-96`, `world.py:64-88`. Type-checking cannot be clean without editing the frozen package |
| Reuse `diagrams/phase4-architecture.svg` | **False** [V] **[CHANGED]** | No `docs/diagrams/` and no `.svg` in the repo; the folder named in `PHASE5.md` and `architecture.md` was never created. The diagram must be drawn |
| Test suite durations (~3 min and ~5 min) | **True** [V] | 178 s and 353 s; the time is real approval waits in `test_approval`, `test_canaries`, `test_outcomes`, `test_cli` |

The old note about an unreadable scratchpad `hub_plan.md` is **removed**: that file no longer exists and nothing depends on it.

**Net effect:** uploaded services and effects work through a `SimWorld` subclass with no core change. The only
core changes are (1) pass `runbooks=` through `Commander` and (2) an optional `on_event` hook, both in v3.0 and both
defaulting to today's behaviour.

---

## 2. Prioritized list

Priority: **P0** first, **P1** strong, **P2** nice to have. Every version keeps `dod all` green and the
`traces/run.txt` DECISION lines identical. Rule for the whole plan: `incident_commander/` is not edited before v3.0
is approved, and nothing here adds a non-stdlib dependency to `incident_commander/` or `ic_hub/` (dev tools only
in `requirements-dev.txt`).

### v2.1 Polish and docs (no behaviour change, no hub dependency) [CHANGED: README rewrite moved to v2.2]

| # | P | Item | Status |
|---|---|---|---|
| 1 | P0 | `LICENSE` (see P6) | plan, [PENDING] P6 |
| 2 | P0 | `pyproject.toml` with `incident-commander`, `ic-plus`, `ic-hub` console scripts. `requirements.txt` stays the single source of the scikit-learn pin (no duplicate pin); `tech-stack.md` line "no packaging" is amended | plan, [CHANGED] |
| 3a | P0 | README structure: pitch, badges (CI, Python, license), "what makes it interesting" bullets. **No hero GIF yet** | [CHANGED] split from 3 |
| 4 | P0 | `docs/ARCHITECTURE.md` and a user guide; the architecture diagram is **drawn new** (SVG under `docs/diagrams/`) | plan, [CHANGED] |
| 5 | P0 | ADRs 0002-0004 with status **proposed**: deterministic agent over LLM, investigator has no log tool, hub stdlib only. The v3.0 unfreeze ADR is written only after P1 | [CHANGED] |
| 6 | P1 | **Faster tests without patched sleep** [CHANGED: was "inject a fake clock"]. A fake clock breaks `AGENTS.md` and `tech-stack.md` ("real clocks, no patched sleep"). Instead: (a) tests that only need the approval path use a shorter real `deadline_s` (already a `Commander` argument), never below the margins the lower-bound asserts need; (b) CI runs `tests/` and `tests_plus/` as parallel jobs; (c) CI stops running the G2/G3 suites twice (once by `unittest`, once inside `dod all`) if timing shows it matters. Gate tests (G2, G3, canaries) keep their current real deadlines. Target: CI wall time down, no weaker assertion | new, reframed |
| 7 | P1 | Coverage report (`coverage`, dev-only) in CI with a badge | new |
| 8 | P1 | Static type check (`mypy`, dev-only) with a lenient config that **excludes `incident_commander/`** until P1 is decided (annotating it would change the frozen package) | new, [CHANGED] |
| 9 | P1 | `pip-audit` and `bandit` or CodeQL in CI, plus `SECURITY.md` | new |
| 10 | P1 | `Dockerfile` + compose file | plan |
| 11 | P1 | `CONTRIBUTING.md`. `CHANGELOG.md` stays generated and never hand-edited; installing a generator (git-cliff) is a prerequisite and an open blocker | plan, [CHANGED] |
| 12 | P2 | `pre-commit` config running ruff | new |
| 13 | P2 | Tidy `memory-bank/progress.md` (v1.1-v2.0 sit under "In progress") | new |

### v2.2 Hub core (`ic_hub/`, stdlib only, no core change) [CHANGED: was the whole hub]

Prerequisite: P2 approved. Hub imports `incident_commander` and `ic_plus`; neither imports the hub (G1 and X1 unaffected).

| # | P | Item | Status |
|---|---|---|---|
| 14 | P0 | `python -m ic_hub` on 127.0.0.1, vanilla HTML/JS single page, JSON API | plan |
| 15 | P0 | Incidents view: 3 demo + 3 golden + uploads; field-level errors | plan |
| 16 | P0 | **Upload schema** (`flat`/`step`/`ramp` + baseline, deploys, dependencies) translated to `ServiceSpec`. Reject names that clash with built-ins and `fired_at` off the 60 s grid. **[NEW] Also bound `fired_at`, anchors, lookback and window sizes**: `latency_points` builds one point per grid step, and a start near 0 builds about 29M points (`activeContext.md` gotcha) | new, [CHANGED] |
| 17 | P0 | Uploaded effects via `HubWorld(SimWorld)` overriding `apply_remediation` | new |
| 18 | P0 | Run view as an **animated replay** of the finished trace. [NEW] Tool reads may stream live through a `SimWorld` subclass; hypotheses and verdict appear at the end | plan, corrected |
| 19 | P0 | Web approval card with countdown **per page** (worst case 2 x deadline), Approve/Deny bound to one pending page by a nonce, `WebResponder`, background thread. [NEW] Cap `deadline_s` and concurrent runs. The UI states that approver identity is simulated (priya/devon), not authenticated | plan, [CHANGED] |
| 21 | P0 | **Injection playground**: plant a log line via `planted_logs`, show DECISION lines unchanged side by side | new |
| 23 | P1 | Postmortem view with Publish and Markdown/JSON export (`postmortem.render`; JSON via `dataclasses.asdict` [I]) | plan |
| 29 | P1 | Security: schema validation, 1 MB cap, **Host header check** [NEW], Origin check, per-start token and per-page approval nonce on POST, reject duplicate keys and non-finite numbers [NEW], all log text and Alertmanager-style labels as `textContent` never `innerHTML`, strict CSP, generated ids only for any file under `data/` [NEW] | plan, [CHANGED] |
| 45 | P0 | **Tests for the hub** [NEW]: handler tests with stdlib `http.client` against a local server; adversarial uploads (huge window, NaN, duplicate keys, name clash); XSS payload in a log line; wrong Host/Origin; replayed or stale approval nonce; DECISION lines of the three demo alerts identical to `traces/run.txt` through the hub; `dod purity` still PASS | new |

### v2.3 Hub extras (no core change) [CHANGED: split from v2.2]

| # | P | Item | Status |
|---|---|---|---|
| 20 | P0 | Evidence charts as inline SVG (baseline, deploy markers, 30 min window, verify window) | new |
| 22 | P1 | What-if toggles (fix fails, stale deployments, tool failure, silent approver) | new |
| 24 | P1 | Evaluate view that **calls** `incident_commander.evaluate` / `ic_plus.x3`, not a copy of their logic | plan, [CHANGED] |
| 25 | P1 | Explain box. [NEW] In hosted mode it warns that text leaves the machine; the key is never sent to the browser | plan, [CHANGED] |
| 26 | P1 | Run diff | new |
| 27 | P1 | Run history as JSON in a gitignored `data/` [NEW: add `data/` to `.gitignore`]. Similar-incident panel advisory only, never fed to ranking | plan, [PENDING] P2 |
| 28 | P1 | Audit log: append-only JSONL with a SHA-256 chain. It is tamper-evident, **not** signing or identity | new, [PENDING] P2 |
| 30 | P1 | Alertmanager-shaped intake: a local adapter mapping JSON to `Alert`; labels treated as untrusted text | new, [PENDING] P2 |
| 31 | P2 | Metrics strip per run | new |
| 32 | P2 | Server-Sent Events for approval state. Full trace streaming waits for v3.0 | new |
| 33 | P2 | Dark mode, keyboard shortcuts, accessible labels | new |
| 34 | P2 | Playwright smoke test (dev-only) | new |

### Showcase (after v2.2)

| # | P | Item | Status |
|---|---|---|---|
| 3b | P0 | README rewrite with hero GIF/screenshot (needs v2.2) | [CHANGED] moved here |
| 41 | P0 | Static trace viewer on GitHub Pages replaying pre-recorded runs. Recordings are produced by a script from real runs, never hand-edited, and labelled as recorded | new, [PENDING] P4 |
| 42 | P0 | 2-3 minute demo video and GIF | new |
| 43 | P1 | Release workflow: on a tag, build and push the Docker image to GHCR | new |
| 44 | P2 | `docs/CASE_STUDY.md` | new |

### v3.0 Pluggable core [PENDING] P1, P3. Only version that touches `incident_commander/`

Starts only after the course submission and viva and after owner approval.

| # | P | Item | Status |
|---|---|---|---|
| 35 | P1 | `Commander.run(..., runbooks=None)` passed into `investigate` and used at `commander.py:207` and `:299`, defaulting to `RUNBOOKS` | plan, narrowed |
| 36 | P1 | Optional `on_event` callback on `Trace.emit` (`commander.py:98`) | new |
| 37 | P1 | Test that default behaviour equals v1.0; G1-G6 pass; DECISION lines identical; ADR with the diff. **[NEW] X1 is re-baselined** (P3): `test_release.py:41` otherwise fails by design. Add a `v2.x` tag as the new baseline and keep the v1.0-to-baseline diff documented | plan, [CHANGED] |
| 38 | P1 | Runbook editor: nine predicates, four actions, validate, re-index `HybridRanker` (`retrieval.py:95`) | plan, constrained |
| 39 | P2 | Seeded scenario generator as a **robustness check**: confusion matrix over worlds built with the same helpers as the fixtures. It measures consistency, not real-world accuracy, and is labelled so. It is not a headline resume number. [PENDING] P2 (random fault injection is on the out-of-scope list) | plan, [CHANGED] |
| 40 | P2 | New predicates. Edits the frozen registry and risks `test_invariants`, `test_canaries` and the golden set | new, [PENDING] P5 |

Deliberately left out: multi-incident queue, Slack/e-mail sending, user accounts, PyPI publishing, a JS framework.

---

## 3. Recommendations (owner's call)

1. **Order:** v2.1, v2.2, showcase (README GIF, video), v2.3, then v3.0 if approved. A clickable demo is what a reader sees first.
2. **License:** MIT is the portfolio default; Apache-2.0 if a patent grant matters. Use the full legal name and year; check any college claim over coursework (P6).
3. **v3.0 and scope amendment:** approve both only after the course submission and viva, so the graded package stays exactly `v1.0`. Add "Portfolio scope (v2.1+)" as a new section; do not edit the graded "Out of scope" list.
