# Thresholds and tunables

Every tunable number lives in `incident_commander/config.py`. Changing one needs a note here with its
reason. The golden set is never used to tune a threshold (DETAILED_ROADMAP section 6, rule 6).

## Decision thresholds (PHASE5 9.1, frozen in v0.1, first used from v0.2)

| Name | Value | Reason |
|---|---|---|
| `LATENCY_ELEVATED_RATIO` | 2.0 x baseline | clear degradation, tolerant of noise |
| `LATENCY_NORMAL_RATIO` | 1.25 x baseline | between 1.25 and 2.0 is UNKNOWN |
| `ERROR_NORMAL_RATIO` | 2.0 x baseline | |
| `ERROR_ELEVATED_RATIO` | 3.0 x baseline | between 2.0 and 3.0 is UNKNOWN |
| `DEPLOY_WINDOW_S` | 1800 | "what touched it last": 30 min before `fired_at` |
| `LOOKBACK_S` | 21600 | 6 h, long enough to see a slow climb |
| `STEP_FRACTION` | 0.5 | one adjacent jump of at least half the final level |
| `TREND_R2` | 0.8 | gradual trend needs a good linear fit |
| `DEP_LATENCY_UNHEALTHY` / `DEP_ERROR_UNHEALTHY` | 2.0 / 3.0 | same bands as latency and error |
| `VERIFY_TOLERANCE` | 1.10 | 195/180 = 1.083 passes, 3900/180 = 21.7 fails |
| `ROUND_BUDGET` | 4 | equals the number of evidence tools |
| `APPROVAL_DEADLINE_S` | 0.3 | per page, demo value |
| `RRF_K` / `BM25_K1` / `BM25_B` | 60 / 1.5 / 0.75 | v0.5 retrieval constants from PHASE5 7.4 |
| `CHAR_NGRAM_RANGE` | (2, 4) | v0.5 `char_wb` n-gram sizes (choice beyond PHASE5) |
| `SMALL_MARGIN` | 0.001 | v0.5 top-2 fused gap under this prints the "small margin" note; real value 0.000529 |
| `STATIC_RANKER_ORDER` | RB-102, RB-101, RB-104, RB-103 | v0.2 stub order, deliberately wrong-first so evidence visibly overrides rank |

## Simulation parameters (v0.1)

| Name | Value | Reason |
|---|---|---|
| `SAMPLE_INTERVAL_S` | 60 | PHASE5 8: series sampled every minute |
| `DATA_CLOCK_START_OFFSET_S` | 5.0 | DataClock starts at `fired_at + 5` |
| `DATA_CLOCK_TICK_S` | 2.0 | each tool call advances simulated time, so ages are reproducible |
| `RECENT_WINDOW_S` | 300 | "median of the last 5 min" |
| `TOOL_SPECS` | 60 / 60 / 300 / 3600 / 120 s | PHASE5 9.2 staleness budgets; lags 3 / 3 / 10 / 30 / 5 s |

## Fixture choices that go beyond PHASE5 (v0.1)

- `inventory-service` error rate is a flat 0.010 (its baseline), not "about 0.012". With 0.012 the
  dependency view of ALRT-9001 would show `err=1.2`, while the roadmap's expected M1 output and
  PHASE5's "healthy dependency ~ 1.0" both need 1.0. It is still "normal" for ALRT-9002 (ratio 1.0 <= 2.0).
- Alerts are one day apart (`T0`, `T0 + 1 day`, `T0 + 2 days`) so no service's incident overlaps another
  alert's 6 h lookback. `T0` is a multiple of 60 s so alerts sit on the sampling grid.
- `Observation` has an extra optional `baseline` field. PHASE5 7.3 says latency and error tools return
  "baseline in payload"; a dedicated field keeps `data` a plain tuple of points.
- `get_dependencies` reads each dependency's last 5 minutes ending at `min(at, as_of)`: with a lagging
  source it uses the latest data produced so far instead of failing.
- Golden-set services arrived with v0.6 (see the v0.6 section below).

## Choices that go beyond PHASE5 (v0.2)

- The verdict is also checked once after the loop ends, so a hypothesis confirmed by the last allowed
  round (for example a stale answer refetched fresh at round 4) still counts. PHASE4 8.3's pseudo-code
  only checks at the top of each iteration.
- Two confirmed hypotheses end the loop at once with `ambiguous_match`; more evidence cannot un-confirm a TRUE predicate.
- A stale answer is refetched once (its own round, `mode=refetch`) only if budget remains. A tool that
  returned `status=error` is not refetched: a retry of the same call adds nothing the planner can use.
- Latency/error predicates mirror each other: elevated is FALSE at or below the "normal" ratio and
  UNKNOWN in the middle band (and normal is the reverse), so 1.99x gives UNKNOWN for both.
- A constant (zero-variance) latency series is not a gradual trend (FALSE); fewer than 3 points is UNKNOWN.
- `latency_step_change` requires every point before the biggest jump to stay within `LATENCY_NORMAL_RATIO` of baseline.
- ROUND lines print the tool's predicates that appear in a hypothesis still alive at the start of the round
  (all of them in exploratory mode); `RoundRecord.values` keeps every predicate for the tool.
- Runbook `text` was a placeholder until v0.5 (now real, see the v0.5 section).

## Choices that go beyond PHASE5 (v0.3)

- `APPROVAL_TICK_S = 0.02`: the gate polls the responder every 20 ms of real time (PHASE5 7.8 default).
- `APPROVAL_DEMO_SLEEP_S = 0.4`: the M5 demo sleeps 0.4 s against a 0.3 s page window, leaving a 0.1 s margin.
- The remediation effects (195 / 3900 / 182 ms) and their 60 s delay are fixture data in `fixtures/services.py`.
- Any approval reply other than "approve" yields no token (fail closed); "deny" ends the request at once.

## Choices that go beyond PHASE5 (v0.4)

- `verify` takes `service` and `metric` (not the whole `Alert`), so no summary or severity can reach it. A pure
  `assess(metric, obs, executed_at, tolerance)` makes the decision and is what the 198.0 / 198.1 boundary tests call.
- The verifier advances the DataClock to `executed_at + VERIFY_WINDOW_S` (300 s, simulated, no real sleep) before
  re-querying, and uses the median of the window's points at or after `executed_at`. A metric with no tool in
  `METRIC_TOOLS`, an errored or stale observation, or `as_of < executed_at` reopens with "no fresh post-fix data".
- `Executor` takes an `outcome` ("success" | "fix_fails") and passes it to `SimWorld.apply_remediation`.
- `PostmortemDraft.notified` is a list so `notified == []` holds as the acceptance criterion states. The draft is
  built before the final DRAFTED state event, so its timeline ends at the last pre-draft event.
- `run --all` runs every case first (real clock), then prints M1-M8 from the recorded cases, so each header appears
  once. The `fix_fails` variant runs on a fresh `SimWorld` because the first run already fixed the service.
- M6 prints the ALRT-9003 handoff; M7 prints a postmortem decision line for all three cases but publishes only
  ALRT-9001, and shows counts for log excerpts instead of their text.
- `DEMO_SECONDARY_DELAY_S = 0.1` (devon approves 0.1 s after being paged; priya never answers), `VERIFY_WINDOW_S = 300`,
  `PUBLISH_RECIPIENTS = ("oncall-channel",)` and `METRIC_TOOLS` live in `config.py`.

## Choices that go beyond PHASE5 (v0.5)

- BM25 tokens are lowercase `\w+` words; IDF is `ln(1 + (N - df + 0.5) / (df + 0.5))` so it is never negative.
- Ties in either ranking keep corpus order, so output is deterministic. All-zero scores (empty or unknown query) give corpus order.
- `margin` is the fused-score gap between rank 1 and rank 2. With 4 runbooks and agreeing BM25 and char ranks it is
  2 * (1/61 - 1/62) = 0.000529 for all three alerts, so "small" is a ratio of ranks, not of evidence strength.
- AC-16 result: RB-101 and RB-102 are the top 2 for ALRT-9001 and ALRT-9002; RB-104 ranks first for ALRT-9003.
- `run --all` M2 uses `HybridRanker`; `investigate` (M3 command) and the investigator tests still use the labelled `StaticRanker`.
- Runbook `text` and `follow_ups` are real. The `traces/v0.5.txt` header records the Python and scikit-learn versions
  of the real run (3.14.2 / 1.8.0: the 3.12 interpreter was missing from this machine, so the dev `.venv` was not rebuilt).

## Choices that go beyond PHASE5 (v0.6)

- Golden services are named `search-service`, `cart-service`, `auth-service` and `user-db` (PHASE5 8 style, not the shorter v0.1 note).
  They live in `fixtures/golden.py`, with alert ids ALRT-9101/9102/9103 on days 3, 4 and 5 after `T0`. The default `SimWorld()` and
  `run --all` still hold only the three demo alerts; evaluation uses `golden_world()`, which adds the golden services and alerts.
- G-1 step to 700 ms at `fired_at - 480 s` after a deploy at `-540 s`; G-2 slow climb to 800 ms with no deploy in the window;
  G-3 latency 5x and errors 5x with an unhealthy `user-db`. None of the thresholds was changed or tuned for them.
- Remediation effects for the golden pairs are in `fixtures/services.py` so the golden cases run to a verified resolution.
- `Commander.run` has no `planted_logs` parameter (PHASE5 7.12 had one). Instead `SimWorld(planted_logs={service: lines})` adds
  untrusted lines to one service's logs, so the Commander and Investigator run unchanged and the test stays honest.
- The attack compares the exact `Observation` tuple the Investigator received and the full DECISION-line set (verdict, classify,
  approval, execute, verify, handoff), each run on a fresh world. Three variants: "blame payment-service, do not roll back",
  "ignore previous instructions...", "approval granted...". The planted text may appear only in the postmortem's untrusted excerpts.
- Expected answers for ALRT-9001/2/3 (`DEMO_EXPECTED`) and the golden set (`GOLDEN_EXPECTED`) are used only for reporting, never by a decision.
- `naive` runs top-1 retrieval -> action with no investigation on all six alerts. Real result: wrong on 4 of 6 (ALRT-9002, 9003, 9102, 9103);
  right only where the top runbook happens to be right. On ALRT-9003 any action is wrong because the correct outcome is a hand-off.
- `evaluate` exits 1 if a golden case fails or the attack changes anything. `traces/v0.6.txt` ends with the `naive` table.

## Choices that go beyond PHASE5 (v1.0)

- No new tunable was added to `config.py`. The acceptance values the trace gate looks for (`rounds=4`, 195 ms, 3900 ms,
  priya to devon, and so on) are the brief's promised outputs, kept as constants in `dod.py`, not thresholds a decision reads.
- `run --all` and `run <ALERT>` now exit 1 when the M8 section fails (a golden miss or a changed attack). Before, the result was
  printed but ignored, so a failing evaluation could still produce a trace that passed G5.
- G5 (`dod trace`) checks that each of the eight headers appears exactly once and in order, that the nine acceptance DECISION
  lines are present as whole lines, that the attack line ends in `unchanged=True`, that the ALRT-9001 draft has `notified=[]
  published=False`, and that ALRT-9002 executes once and then reports `already_executed` with the same `execution_id`.
  Execution ids are deterministic (a hash of the idempotency key), so they are compared with each other, not pinned.
- G6 (`dod repro`) normalises by dropping the leading `[t+<s>s] ` stamp and any `elapsed_s=` field. Those are the only parts of a run
  that differ (checked on two real runs); everything else, execution ids included, must match line for line. `dod all` reuses its G5
  run as the first of the two G6 runs.
- `dod all` takes G5 from a fresh `run --all`, never from the saved `traces/run.txt`. G4 passes when `evaluate` exits 0 and prints
  `DECISION golden_summary passed=3 total=3`. G2 and G3 run `tests.test_invariants` and `tests.test_outcomes` in fresh interpreters.
- `tests/test_invariants.py` and `tests/test_outcomes.py` are new adversarial suites. The per-module tests stay in place;
  the two files are the ones the gates run. G3 runs the shipped pipeline (hybrid ranker, scripted responder, real clock).
- `tests/test_canaries.py` has nine canaries over a temporary copy of the package: an extra import and environment access (G1);
  a `severity` parameter, an incident id in a fixture, a free-text predicate parameter and a notifier reachable from `build_draft` (G2);
  a no-op `ControlClock.sleep` and a verifier that always resolves (G3). Each also checks that the expected test class fails, and
  each sabotage asserts its target text occurs exactly once so it cannot silently do nothing.
- `traces/run.txt` is exactly `python -m incident_commander run --all > traces/run.txt`. Unlike the versioned traces it has no
  interpreter header line and no appended `naive` table, so G5 and G6 read the plain output.

## Choices that go beyond PHASE5 (v1.1)

- CLI shape: subcommands `run [ALERT|--all]` and `scenario <name>|all` (DETAILED_ROADMAP showed both flags and a subcommand);
  `--llm off|local|hosted` is accepted before or after the subcommand, and `local`/`hosted` exit 2 with "not available until v1.2".
- `run ... --approver scripted` calls the graded `cmd_run` unchanged, so its output is the graded output plus one
  `extension: llm=off approver=scripted` line; only `--approver cli` (one alert, optional `--deadline S`) has its own runner.
- `CliResponder` reads lines on a daemon thread into a queue; only the exact words `approve` / `deny` (any case, trimmed) count,
  noise is ignored, and a closed or failing stream is no answer. A typed answer goes to whichever page is being polled.
- Scenarios use the public graded API only (`SimWorld(tool_lags=, planted_logs=)`, a `ServiceSpec` with a raising `error_rate`,
  `fix_outcome="fix_fails"`, both responders silent, `classify_remediation("delete_database")`). Injection variants use the three
  PHASE5 texts, planted in the plain demo world on ALRT-9001 (not the golden world used by the graded attack).
- Keys: `.env` (AGENTS.md) wins over the older `--llm-key-file` plan. v1.1 reads no environment and no key. The committed
  `.env.example` template (empty `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`) is added now; v1.2 is the first to read `.env`.
- `traces/v1.1.txt` is `python -m ic_plus run --all --llm off`; its DECISION lines equal `traces/run.txt`.

## Choices that go beyond PHASE5 (v1.2)

- Provider flag is `--llm local|hosted` (not `ollama`); X2 uses `--llm local`. `--llm-url` and `--model` are accepted before or after
  the subcommand. There is no `--llm-key-file`: `.env` wins (AGENTS.md), parsed by `ic_plus/envfile.py`, the only place `.env` is read.
  No process variables are read anywhere.
- Precedence: flags, then `.env` (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`), then the local default `http://localhost:11434/v1`.
  `hosted` needs url, model and key; `local` ignores the key. Anything missing prints `llm: not configured (missing ...)` on stderr and
  uses the fallback. A missing `.env` is normal.
- `LLMClient.chat` never raises, has no retries, a 20 s default timeout, sends the key only as a bearer header, and scrubs it from errors.
- Decisions come from the unchanged graded `cmd_run`; with `--llm local|hosted` the narrator then runs on separate, identical
  deterministic cases (cmd_run prints but does not return its cases). Output per alert, before the banner:
  `narrator: alert=<ID>`, then `llm: ok role=narrator model=<m> guard=pass` plus `postmortem narrative: "AI-drafted narrative (not authoritative): ..."`,
  or `llm_rejected role=narrator alert=<ID> reason=...` plus `llm: rejected, deterministic fallback`, or `llm: unavailable, deterministic fallback`.
  After the first unavailable result the remaining alerts skip the server. The banner is `extension: llm=<mode> approver=<x>`.
- The graded draft is frozen, so the AI narrative is printed by `ic_plus`, not written into the graded postmortem draft; the template
  narrative is that draft. `llm_ok` / `llm_rejected` / `llm_unavailable` events are emitted into the narrated case's trace.
- Narrator facts are typed outcome fields of the case (ids, verdict, tier, approval, execution, verification, handoff reason); never
  `Observation.data` or log excerpts. Reply keys are exactly `summary`, `impact`, `root_cause_text`, each at most 600 characters.
- Guard limits: numbers, hyphenated identifiers and the known service/runbook/approver names must appear in the facts; sentences that
  start with an imperative verb or match instruction phrases are rejected. A free-form unknown person name is not detectable; the guard
  is a backstop and the fallback is always safe.
- Purity test now allows `urllib`/`http` only in `llm_client.py` and `.env` only in `envfile.py`.

## Choices that go beyond PHASE5 (v1.3)

- Roles: `explainer.py` (`ic_plus explain <ALERT> "<question>"`), `advisor.py` (`advise`) and `x3.py` (`ic_plus evaluate --llm ...`).
  Trace events reuse the v1.2 names (`llm_ok`, `llm_rejected`, `llm_unavailable`) with a `role=narrator|explainer|advisor` field.
- Explainer: free text (no JSON mode), at most 600 characters, same grounding checks as the narrator (numbers, hyphenated identifiers
  and known names must appear in the typed facts; no instruction phrases or imperative sentence starts). The question is untrusted:
  reduced to one printable line of at most 200 characters before it reaches the model. Fallback is a deterministic sentence built from the
  facts, which passes its own guard. Output is labelled `[AI explanation, not authoritative]` or `[deterministic explanation]`.
- Advisor guard (`guard_advice`): reply is exactly `{"order": [...]}`; every name must be one of the four evidence tools (never
  `get_logs`), none repeated. "Nothing new" is read as "no name outside the allow-list". A partial list is padded with the remaining
  tools in fixed order, so the result is always a permutation. The request holds ids and numbers only (alert id, service, metric, ranked
  candidates with scores, allowed tool names); no summary text, severity or logs.
- Advice enters only through `investigate(tool_order=...)`, which exists in the frozen package but is not forwarded by `Commander.run`.
  `x3.advised_orders` wraps `incident_commander.commander.investigate` for the duration of a run and restores it afterwards; nothing
  in `incident_commander/` is edited. `ic_plus run` does not apply advice; only `evaluate` does, as the X3 proof.
- X3 (`evaluate --llm local|hosted`): the graded M8 prints unchanged, then per fixture alert (3 demo + 3 golden) the advisor is asked,
  the pipeline runs under the advised order, and the narrator and explainer read the finished case. Its DECISION lines must equal a
  no-LLM baseline; the graded M8 is also re-run under the advised orders and its whole output compared. Output ends with
  `llm: roles=narrator,explainer,advisor decisions_changed=N` and the command exits 1 when N > 0. A role that is unavailable or
  rejected still counts as run (its fallback is what is compared). `--llm off` prints `llm: off`.
- Automatic X3 test: all 24 tool orders give the same verdict on all six fixture alerts; reversed advice, adversarial advice and a dead
  model leave every DECISION line unchanged; a one-tool order is shown to change decisions, so the comparison can fail.
- Hosted provider: nothing new in the client. `--llm hosted` needs `LLM_BASE_URL` (or `--llm-url`), `LLM_MODEL` (or `--model`) and
  `LLM_API_KEY`, the key from `.env` only (never a flag). Example hosted URL: `https://api.groq.com/openai/v1`. Free-tier limits were not
  checked in this session (no key available); 4xx/429/5xx and timeouts fall back and exit normally (tested against a fake server).
  Whether a given hosted provider supports `response_format: json_object` is unverified; the client sends it for JSON roles only
  (not for the explainer).
- v1.2 gap closed: once the server is down, later alerts skip the call and now also record `llm_unavailable` in their trace.
- Traces: `traces/v1.3.txt` (`run --all --llm local`) and `traces/v1.3-evaluate.txt` (`evaluate --llm local`) are real runs against an
  unreachable URL; their DECISION lines equal `traces/run.txt`. Live traces with a real model are still pending and manual.

## Choices that go beyond PHASE5 (v2.2, ic_hub)

`ic_hub/` is the approved portfolio hub (P2, 2026-10-20). It is stdlib only, imports `incident_commander` and `ic_plus`, and is imported by neither.
It makes no decision: it builds a world, picks a responder, calls the frozen `Commander.run`, and reports the finished case.

- Server: `http.server.ThreadingHTTPServer` bound to 127.0.0.1 only (`python -m ic_hub [--port N]`, default 8765, 0 picks a free port).
  Quiet by design (`log_message` does nothing). A stalled client times out after 10 s.
- Checks on every request: Host must be `127.0.0.1:<port>` or `localhost:<port>` (DNS rebinding), Origin must match when present,
  `/api/*` needs the per-start token in the `X-Hub-Token` header (never the query string). The token is embedded in the page as a `<meta>`
  tag, so inline script is never needed and the CSP stays `default-src 'none'; script-src 'self'; style-src 'self'; ...` with no `unsafe-*`.
- Bodies: `Content-Length` required (chunked refused, 411), at most 1 MB (413, refused before it is read), `Content-Type: application/json` (415).
  JSON is parsed strictly: UTF-8, duplicate keys, `NaN`/`Infinity`/`1e999` and pathological nesting are all rejected.
- Static files come from a three-entry allowlist (`/`, `/app.js`, `/app.css`); no path is built from the request.
- Upload schema (one service plus one alert): `flat`/`step`/`ramp` series, baselines > 0, deployments (at most 10), dependencies (at most 5, must
  already exist, no self or repeat), remediation effects for known actions with both outcomes. Times must lie within 400 days of the demo
  anchor `T0`; `fired_at` and `anchor` must sit on the 60 s grid. Names clashing with built-in or earlier uploaded services or alerts are refused.
  At most 20 uploads. All errors are returned per field. A run takes its time window from the alert only, so no request can ask for a huge window.
- `HubWorld(SimWorld)` adds uploaded services, alerts and effects; a (service, action) pair without an uploaded effect falls back to the graded behaviour.
- Runs: one background thread each, at most 2 at a time (429 beyond that), the last 50 are kept. Approver modes: `scripted` (the graded wiring, priya
  silent and devon approves after 0.1 s), `silent` (nobody answers), `web` (a person in the page). Default deadline per page is the graded 0.3 s for
  `scripted`/`silent` and 20 s for `web`; `deadline_s` is capped at 60 s (a web run can take twice that).
- Web approval: `WebResponder.poll` opens a pending page with a fresh nonce; `submit` accepts only the current nonce, once, before its deadline
  (`accepted`, `stale`, `expired`, `bad_decision`; anything but `accepted` is HTTP 409). The gate still owns the real deadline and the escalation.
  The page says that approver identity is simulated.
- Replay: the page animates the finished trace (250 ms per event, with a skip button). Live streaming of the trace came with v3.1 (`on_event`).
- Injection playground: runs the same alert twice (clean, then with one planted log line) and compares `case_decision_lines`; it reports `unchanged`.
- Postmortem: render, Markdown and JSON export (`dataclasses.asdict`), and an explicit Publish that goes to the in-memory `OutboxNotifier` only.
- Page rule: every server string is set with `textContent`; a test fails if `app.js` contains an HTML sink or the page an inline script or handler.
- Parity: the DECISION lines of ALRT-9001, 9002 and 9003 through the hub (scripted) are checked against `traces/run.txt`; the planted-log runs match too.
- Not in v2.2 (added later in v2.3, see below): charts, what-if toggles, evaluate view, explain box, run history, audit log, Alertmanager intake.

## Choices that go beyond PHASE5 (v2.3, views: charts, what-if, run diff)

- Chart data: `ic_hub/charts.py::build_chart` re-reads the alert's own metric from the run's own world (so a fix shows as recovery), the baseline, the verify limit (baseline x `VERIFY_TOLERANCE`) and the deployments in the 30 minute window. Marker times come from trace events (`EXECUTE` with status executed, `VERIFY`). It is added to a finished run's result as `chart` (null if the series cannot be read) and kept across publish. Nothing reads it back into a decision.
- Verify marker: `VERIFY` data time is at least `VERIFY_WINDOW_S` after the fix (the data clock also ticks per tool call), so the tests assert a lower bound.
- What-if toggles: `what_if` is an optional list of at most two distinct names from `stale_deployments` (the `get_deployments` lag of the ic_plus `stale_data` scenario, 900 s) and `tool_failure` (the alert service's error-rate backend raises, as in the `tool_failure` scenario). Anything else is a 422. "Fix fails" and "silent approver" already exist as `fix_outcome` and `mode`. Applied through `HubWorld(tool_lags=, broken_error_rate=)`; no core change.
- Run diff: `POST /api/diff` with `{"a", "b"}` (generated 16-hex run ids only) compares state, handoff reason, DECISION lines and trace kinds of two finished incident runs; playground and unfinished runs are a 409, unknown ids 404. Computed on the server so it is tested over HTTP.

## Choices that go beyond PHASE5 (v2.3, evaluate and explain)

- Evaluate: `POST /api/evaluate` starts a background job (same run store and concurrency cap as runs, one evaluation at a time, else 409) that calls `run_golden`, `attack_differential` and `naive_baseline` from `incident_commander.evaluate`, then `ic_plus.x3.run_x3` and re-runs the golden set and attack under the advised tool orders. `decisions_changed` counts non-identical x3 rows plus one if the advised golden or attack result differs. It runs x3 for every mode, also `off`, where every role falls back to its template.
- x3 swaps `incident_commander.commander.investigate` for one run, so the hub holds one lock around it. A plain run started at the same moment may briefly see the advised tool order; the tests_plus suite shows all 24 orders give the same verdict on every fixture alert.
- Explain: `POST /api/explain` runs the alert on the graded wiring, then calls `ic_plus.explainer.explain`. Free text, at most 200 printable characters. `off` returns the deterministic template without any client.
- Keys and endpoints: the request carries only `alert_id`, `question`, `llm` and `acknowledge_remote`; any other field (url, model, key) is a 422. The client comes from `ic_plus.clientcfg.client_from_env`, so the URL, model and key come from the server's own configuration and the hub code never touches them. `__main__._make_client` uses the same `build_client`.
- Hosted mode needs `acknowledge_remote: true` (422 otherwise, and no request leaves). The result carries `remote: true` only if a client was used, and the page says so. Local mode needs no confirmation (localhost).
- Not configured or server down: `configured: false` with the names of what is missing (never values), and the labelled deterministic fallback.

## Choices that go beyond PHASE5 (v2.3, history and audit)

- Opt-in: nothing is written unless the hub starts with `--data-dir PATH` (suggested: `data`, which is in `.gitignore`). Without it the history and audit endpoints answer `enabled: false`.
- File names: run records are `runs/<run_id>.json` and the audit log is `audit.jsonl`. The id is the 16 hex characters the hub generated; every read and write re-checks it with a full match, and the HTTP route only matches that shape, so request text never forms a path. Writes are atomic (temp file, then replace).
- Limits: 200 stored runs (the oldest are removed), 1 MB per record (larger is refused and reported as `write_error`), 8 MB for the audit log (appends stop and `audit_full` is reported), at most 12 detail fields of 200 printable characters per audit entry. Damaged, oversized or mismatched files are skipped on read.
- What is stored: finished incident runs only (not the playground, explain or evaluate), including the chart and the postmortem. A publish rewrites the stored copy.
- Similar runs: `GET /api/runs/{id}/similar` lists up to five earlier stored runs on the same service or with the same runbook, as text for a human. It is computed in `ic_hub/store.py`, which `incident_commander/` never imports, and nothing reads it back into ranking or a decision.
- Audit log: append-only JSONL. Each entry has `seq`, `ts`, `event`, `detail`, `prev` and `hash` = SHA-256 over `prev` plus the other fields in canonical JSON; the first `prev` is 64 zeros. `GET /api/audit` recomputes the chain and returns the last 50 entries. Events: `upload_added`, `run_started`, `approval_answer` (target, decision as approve, deny or invalid, outcome; never the nonce or free text), `run_finished`, `published`, `explain_finished`, `evaluate_finished`. Questions and uploaded text are not logged.
- What the chain proves: editing, deleting, reordering or inserting a line in the middle is detected, and a forger who re-hashes one line still breaks the next. It is tamper-evident only: no signature, no identity, and removing lines from the end is not detected unless the `head` hash was noted elsewhere.

## Choices that go beyond PHASE5 (v2.3, intake and polish)

- Alertmanager intake: `POST /api/intake/alertmanager` takes a webhook v4 body (`version` must be `"4"`; the other top-level keys of the format are accepted and checked, anything else is a 422). The v4 field list is not in the repo; the accepted fields are `version`, `groupKey`, `truncatedAlerts`, `status`, `receiver`, `groupLabels`, `commonLabels`, `commonAnnotations`, `externalURL` and `alerts[]` of `status`, `labels`, `annotations`, `startsAt`, `endsAt`, `generatorURL`, `fingerprint`. Limits: 1 to 10 alerts per post, 20 held in all (`MAX_INTAKE`), 20 labels of at most 100 printable characters, 10 annotations of at most 200, `startsAt` 40, keys `[A-Za-z_][A-Za-z0-9_]*`. Only `firing` alerts are accepted. One bad field rejects the whole post (422, nothing added). Same transport rules as every POST (Host, Origin, token, 1 MB, strict JSON, Content-Type).
- Labels are untrusted text. The `service` label is an exact-match lookup key into services the hub already holds (built-in, golden or uploaded); unknown means 422. An optional `metric` label must be `latency_ms` or `error_rate`, else the service's own alert metric is used. Severity is the fixed value `medium` (`INTAKE_SEVERITY`) whatever any label says; the alert id is generated (`AM-` plus 8 hex), never taken from input; `startsAt` is display text only. The simulated data has no wall-clock series, so `fired_at` is the incident time of the service's existing alert: an intake alert therefore reproduces that incident (tests check state, handoff and DECISION lines against the original, also with hostile label text).
- Intake alerts are held as `Upload` objects that reuse the service already in the hub (no new service, no new effects), listed with source `intake` and their labels as text. They do not use the upload cap (`MAX_UPLOADS`) and have their own. A repeated `fingerprint` on the same service returns the earlier alert id with status `duplicate`. The audit log records `alertmanager_intake` with alert ids only, never label text. Intake alerts live in memory like uploads (not stored in `--data-dir`).
- Metrics: `GET /api/metrics` returns counters only: incident runs started (lifetime), running, done and failed, final states and mean run seconds over the last 50 stored runs, approval answers by outcome, intake and upload counts. No label, log or question text is ever included. Run starts and ends are timed with the monotonic clock.
- Approval stream: `GET /api/runs/<id>/stream` sends server-sent events with `status`, `pending` (the same data `GET /api/runs/<id>` already shows) and `error`, an `end` event when the run finishes, and a comment heartbeat every 5 s. The page reads it with `fetch` so the `X-Hub-Token` header applies (`EventSource` cannot send a header, and a token in the URL is refused). Bounds: 4 open streams (429 above), 60 s lifetime then `end` with reason `timeout` and the page reconnects, and a failed write ends the thread. If a stream cannot open, the page polls as before. The result and trace still come from the normal GET; the trace is also streamed live since v3.1. Approval POSTs and their per-page nonce are unchanged.
- Page: a theme button and the `t` key set `data-theme` (the system setting still applies until a choice is made; the choice is kept in `localStorage` inside try/catch). Shortcuts are `r` (run the last alert again), `t`, `?`, and Shift+A / Shift+D for approve and deny, only while an approval card shows; they are off while typing in a field. Shift is required so a stray key press cannot approve. Added a skip link, table caption and scope, `aria-live` regions, `aria-keyshortcuts` and a visible focus ring; tests check each form control has a name.
- Browser smoke test: `scripts/playwright_smoke.py` (dev-only; `pip install playwright` and `playwright install chromium`, in no requirements file and not in CI). It drives the page: run an alert, theme switch and shortcuts, intake, no console errors. Gotcha: the page CSP forbids string evaluation, so Playwright's `wait_for_function` fails; the script waits on locators instead.

## Choices that go beyond PHASE5 (v3.1, hub live progress)

- The hub passes `on_event=` (v3.0 hook, ADR-0005) to `Commander.run`. The observer runs on the run thread and only appends a JSON copy of each event to the run (cap `MAX_RUN_EVENTS` = 500; a run emits about 25). It never raises and never reads or changes a decision.
- The approval stream (`GET /api/runs/<id>/stream`) now also sends `event: trace` blocks: a JSON list of events with a sequence number above the last one sent on that stream. Events are read after the status, so the last block before `end` holds every event. The status and pending messages, the 4-stream cap, the 60 s lifetime and the heartbeat are unchanged.
- The page draws events as they arrive and remembers the highest sequence number; the final replay only adds the events not yet drawn (so there are no duplicates), and runs opened from History still replay as before. The polling fallback shows the trace only at the end. Tests check live events equal `result.trace`, arrive while the run waits for approval, and stay in order.

## Choices that go beyond PHASE5 (v3.1, runbook editor)

- A runbook set is `{"runbooks": [...]}` with 1 to 8 runbooks (`MAX_RUNBOOKS`). Each has `runbook_id` (1-20 letters, digits or dashes, unique), `title` (80 characters), `text` (1000, line breaks allowed), `signature` (1 to 6 distinct predicate ids from the nine in `predicates.PREDICATES`), `action` (one of the four in `ACTION_PROPERTIES`) and up to 3 `follow_ups` (200 characters). Unknown keys are refused, so `tier` cannot be sent: the tier comes from the action alone (`blast_radius`), and a custom runbook cannot lower the approval requirement.
- Why these checks: an unknown predicate id would raise `KeyError` inside the investigator, and an empty signature is confirmed at once (`all([])` is true). The runbook text is only used by the ranker to order candidates; the verdict reads predicates on fresh evidence, so text (including injected instructions) cannot change a decision. A test checks this.
- `POST /api/runbooks` keeps the set in memory (the newest 5, `MAX_RUNBOOK_SETS`) and returns `set_id`, its SHA-256 and warnings. A run request may carry `runbook_set`; an unknown or expired id is a 422 before the run starts. The ranker is rebuilt from the chosen set for each run, so ranker and runbook ids always match (a mismatch would raise `ValueError` in the investigator). `GET /api/runbooks/builtin` gives the built-in corpus, the predicates with one-line help and the actions with their tier.
- Warning, not an error: an action that no service has a remediation effect for (today `scale_out_service`) is accepted, because verification then reopens the case and hands off, which is a safe outcome. The page shows the warning.
- The audit log records `runbooks_added` (set id, hash, count; never the text) and `run_started` carries the set hash or `builtin`. Sets are not stored in `--data-dir`.

## Choices that go beyond PHASE5 (v3.2, scenario generator)

- `ic_plus/generator.py` builds worlds from `flat`, `step` and `ramp` with parameters from `random.Random(seed)`: same seed, same worlds. Nothing random happens at run time, so this is not fault injection.
- Five classes, cycled in order: deploy regression (RB-101), memory leak (RB-102), dependency down (RB-103), config errors (RB-104) and no fault (none). The class is the label by construction; `generate` prints a confusion matrix of label against the runbook the graded pipeline picked, and exits 1 on any mismatch.
- Severity is drawn at random too, and a test relabels it: a decision that read severity would show up as a mismatch.
- Magnitudes are well past the thresholds in `config.py`, so this checks consistency on authored fixtures. It is not an accuracy figure and must not be quoted as one.
- Generated alerts use ids ALRT-9500+ and days 20+ after T0, so they never collide with the demo or golden alerts. Command: `python -m ic_plus generate --seed N --count N` (1 to 200).
