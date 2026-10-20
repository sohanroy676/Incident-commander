# Architecture — Incident Commander (PS4)

Single deterministic agent (graded build) plus a separate extension package (extended build).
Dependency direction is one way: `ic_plus` imports `incident_commander`; never the reverse (checked by G1).

## Folder structure
incident-commander/
├─ README.md
├─ requirements.txt            scikit-learn pin only
├─ requirements-dev.txt        ruff
├─ .gitignore                  .venv, __pycache__, .env
├─ .env.example                committed template (no real values)
├─ docs/                       PHASE1–5.md, DETAILED_ROADMAP.md, THRESHOLDS.md, diagrams/
├─ incident_commander/         GRADED BUILD (stdlib + scikit-learn)
│   ├─ __main__.py             CLI: tools | investigate | gates | run | evaluate | naive
│   ├─ clocks.py               DataClock (simulated), ControlClock (monotonic)
│   ├─ types.py                frozen dataclasses and enums
│   ├─ config.py               thresholds, tier table, staleness, escalation, budgets
│   ├─ fixtures/               alerts.py, services.py, runbooks.py, golden.py
│   ├─ world.py                SimWorld, remediation effects
│   ├─ tools.py                five read-only tools + Observation
│   ├─ retrieval.py            Ranker protocol, StaticRanker, HybridRanker
│   ├─ predicates.py           three-valued predicates
│   ├─ investigator.py         planner, hypotheses, verdict
│   ├─ blast_radius.py         classify_remediation(action)
│   ├─ approval.py             Page, Responder, ApprovalGate, ApprovalToken
│   ├─ executor.py             idempotent ledger, execute
│   ├─ verifier.py             verify
│   ├─ postmortem.py           build_draft (pure), publish
│   ├─ commander.py            state machine, Case, Trace
│   ├─ evaluate.py             golden set, differential attack, naive baseline
│   ├─ report.py               output contract: headers, DECISION lines
│   └─ dod.py                  purity | trace | repro | all
├─ tests/                      unittest, graded build
├─ traces/                     run.txt (G5 evidence), vX.Y.txt per version
├─ ic_plus/                    EXTENDED BUILD
│   ├─ __main__.py  llm_client.py  guard.py  narrator.py  explainer.py
│   └─ advisor.py  approver_cli.py  scenarios.py
└─ tests_plus/                 extension tests, fake HTTP server, recorded replies

## Proposed: `ic_hub/` (v2.2, not built, pending owner approval)
Local web app (stdlib `http.server`, vanilla JS, 127.0.0.1) on top of the same pipeline. It imports
`incident_commander` and `ic_plus`; neither imports it. Uploaded services and remediation effects run through a
`SimWorld` subclass, so no core change is needed. The run view is a replay of the finished trace; web approval uses
a `WebResponder`. Security checks (Host, Origin, token, per-page nonce, size and window bounds, text-only
rendering, CSP) are listed in docs/EXTENSION_PLAN.md. Note: `docs/diagrams/` named below does not exist yet.

## Data flow (one alert)
1. Receive: Commander gets an alert (id, service, fired_at, severity, metric, summary) → new Case, trace event.
2. Propose: Retriever ranks runbooks (BM25 + char TF-IDF, fused with RRF); prints scores and top-2 margin.
3. Investigate: up to 4 rounds; each round = one tool call → freshness check → predicates re-evaluated →
   hypotheses updated → Verdict (`matched` + runbook, or `no_confident_match`).
4a. No confident match → hand off to a human with evidence; stop.
4b. Matched → classify the runbook's action (tier, requires_approval) from the action alone.
5. Approval (if required): page primary on a real deadline; escalate to secondary; no token → stop, hand off.
6. Execute once under an idempotency key; retry returns `already_executed` with the same execution_id.
7. Verify: re-query the alert's own metric after execution; resolved/verified or reopened/unverified.
8. Reopened → hand off; no automatic second fix.
9. Draft postmortem from the trace (notified=[], published=False); only an explicit publish() makes it real.
Evaluation wraps the whole pipeline (golden set + planted-log attack, decision lines diffed).
Extended build: the same pipeline; LLM roles see structured trace facts only, every reply passes a
deterministic guard, and any failure falls back to a template. The LLM never makes a decision.

## Key modules and responsibilities
- commander: state machine and append-only trace; the only orchestrator.
- tools / world: five typed read-only signal tools over simulated, service+timestamp-keyed data.
- retrieval: proposes candidate runbooks; tie-break only, never decides.
- investigator / predicates: bounded evidence loop; three-valued predicates; verdict.
- blast_radius: action → tier; severity is never a parameter; unknown action → high.
- approval: real monotonic deadline, real sleep, escalation, ApprovalToken.
- executor: idempotent execution; token required for high tier.
- verifier: re-queries the symptom; ≤ baseline × 1.10 and fresh data after execution.
- postmortem: zero-side-effect draft; publish() is the only side effect.
- evaluate / dod: golden set, attack, naive baseline; gates G1–G6.
- ic_plus: LLM narrator / explainer / advisor + guard, interactive CLI approver, extra scenarios.

## Third-party services and keys
- Graded build: none. Reads no environment variables, no .env, no network.
- Extended build: Ollama (local, no key) and/or a hosted OpenAI-compatible free tier (e.g. Groq).
- Keys go in `.env` at the repo root (gitignored), e.g. `LLM_API_KEY=...`; `.env.example` is committed
  without values. Only `ic_plus` reads `.env`, with a small stdlib parser. Keys are never hardcoded,
  printed, logged, or written to traces. This replaces the earlier gitignored key-file flag plan.