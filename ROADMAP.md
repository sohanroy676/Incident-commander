# Roadmap — Incident Commander (PS4)
Full detail per version: docs/DETAILED_ROADMAP.md. Each version is done when its tests pass, earlier
gates still pass, its trace is saved to traces/vX.Y.txt, and the git tag exists.

## Now
- v0.5 Hybrid retrieval is built on branch `v0.5-retrieval`; waiting for merge, push, CI and tag.

## Done
- v0.1 Foundations (tagged `v0.1`): scaffold, clocks, types, config, simulated world, five tools, M1 output, G1 purity.
- v0.2 Investigator (tagged `v0.2`): predicates, planner, bounded 4-round loop with a declared stub ranker, `investigate` command.
- v0.3 Gates (tagged `v0.3`): blast-radius classifier, approval gate with real clock and escalation, idempotent executor, `gates` command.
- v0.4 MVP-1 (tagged `v0.4`): verifier, postmortem, Commander state machine, `run --all` end to end.

## Next
- v0.6 Evaluation: golden set, differential planted-log attack, naive baseline.
- v1.0 Graded release: G1–G6 via `dod all`, README, THRESHOLDS.md, saved traces/run.txt, gate canaries; graded package frozen.
- v1.1 Extension scaffold: `ic_plus`, interactive CLI approver, extra scenarios, `--llm off`.
- v1.2 LLM client, guard and narrator: stdlib OpenAI-compatible client, deterministic guard, AI-drafted narrative.
- v1.3 Explainer, advisor and hosted provider; X3 decisions-unchanged proof.
- v2.0 Extended release: demo scripts, rehearsal, G1–G6 and X1–X4 green, tag.

## Later / ideas
- Optional GitHub Actions workflow running `dod all` (first to cut if time runs short).
- Live local-model and hosted free-tier runs saved as traces (manual; check free-tier limits when starting v1.3).

## Explicitly not planned
- Incident queue, JSON/Markdown exports, random fault injection.
- Web UI, persistent storage, learned or persisted agent memory.
- Multi-agent coordination.
- Real infrastructure, real observability systems, live incident data, identity/signing.
- Any LLM in the graded build.