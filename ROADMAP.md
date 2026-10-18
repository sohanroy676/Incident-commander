# Roadmap — Incident Commander (PS4)
Full detail per version: docs/DETAILED_ROADMAP.md. Each version is done when its tests pass, earlier
gates still pass, its trace is saved to traces/vX.Y.txt, and the git tag exists.

## Now
- v1.0 is merged to main, CI green, tagged `v1.0`; `incident_commander/` is frozen. v1.1, v1.2, v1.3 and v2.0 are merged, CI green, tagged. Nothing planned next.

## Done
- v0.1 Foundations (tagged `v0.1`): scaffold, clocks, types, config, simulated world, five tools, M1 output, G1 purity.
- v0.2 Investigator (tagged `v0.2`): predicates, planner, bounded 4-round loop with a declared stub ranker, `investigate` command.
- v0.3 Gates (tagged `v0.3`): blast-radius classifier, approval gate with real clock and escalation, idempotent executor, `gates` command.
- v0.4 MVP-1 (tagged `v0.4`): verifier, postmortem, Commander state machine, `run --all` end to end.
- v0.5 Hybrid retrieval (tagged `v0.5`): BM25 + char TF-IDF fused with RRF, M2 table.
- v0.6 Evaluation (merged to main, CI green, tagged `v0.6`): golden set 3/3, differential planted-log attack, naive baseline, `evaluate` and `naive`, real M8.
- v1.0 Graded release (merged to main, CI green, tagged `v1.0`): `dod trace|repro|all` (G1–G6), `tests/test_invariants.py`, `tests/test_outcomes.py`, `tests/test_canaries.py`, full README, real `traces/run.txt`, CI runs `dod all`.
- v1.1 Extension scaffold (merged to main, CI green, tagged `v1.1`): `ic_plus` with `--llm off`, interactive CLI approver, eight extra scenarios, `tests_plus/`, `traces/v1.1.txt`.
- v1.2 LLM client, guard and narrator (merged to main, CI green, tagged `v1.2`): `ic_plus` stdlib OpenAI-compatible client, `.env` parser, deterministic `guard_narrative`, narrator with template fallback, `--llm local|hosted --llm-url --model`, X4 tests with a fake server, `traces/v1.2.txt`. Live trace `traces/v1.2-live.txt` still pending (manual).
- v1.3 Explainer, advisor and hosted provider (merged to main, CI green, tagged `v1.3`): `ic_plus explain`, `advisor.py` + `guard_advice`, `guard_explanation`, `ic_plus evaluate --llm` with the X3 proof (`llm: roles=narrator,explainer,advisor decisions_changed=0`), `traces/v1.3.txt` and `traces/v1.3-evaluate.txt`. Live traces with a real model still pending (manual).

- v2.0 Extended release (merged to main, CI green, tagged `v2.0`): `docs/DEMO.md` (graded and extended demo scripts, dry-run), README extension section, `tests_plus/test_release.py` (X1-X4), `traces/v2.0.txt`, live local-model traces `traces/v1.2-live.txt` and `traces/v1.3-live-evaluate.txt` (Ollama llama3.2).

## Next
- Nothing scheduled. Submission and viva rehearsal with docs/DEMO.md.

## Later / ideas
- Optional GitHub Actions workflow running `dod all` (first to cut if time runs short).
- Hosted free-tier run saved as a trace (manual; free-tier limits still unchecked).

## Explicitly not planned
- Incident queue, JSON/Markdown exports, random fault injection.
- Web UI, persistent storage, learned or persisted agent memory.
- Multi-agent coordination.
- Real infrastructure, real observability systems, live incident data, identity/signing.
- Any LLM in the graded build.