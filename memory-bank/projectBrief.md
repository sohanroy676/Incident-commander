# Project Brief — Incident Commander (PS4)

## What and who
An incident-commander agent for the Sem VII Agentic AI course (PS4): it investigates simulated
production alerts by correlating real signals, gates risky fixes behind time-boxed human approval,
verifies the fix, and drafts a postmortem. Built for the course submission and viva.

## Core goal / success criteria
Two independently demoable builds:
- Graded build (v1.0, done when):
  - All eight milestones (M1–M8) run end to end with one command: `python -m incident_commander run --all`.
  - Outcomes 1–9 hold with the exact acceptance values (ALRT-9001/9002/9003, approval priya → devon,
    195 ms resolved / 3900 ms reopened, idempotent retry, golden set 3/3, planted-log attack unchanged).
  - All six Definition-of-Done gates G1–G6 pass: `python -m incident_commander.dod all`,
    on Python 3.12 in a fresh clone with no environment variables set.
  - `traces/run.txt` is the real, unedited trace pasted into the report.
- Extended build (v2.0, done when):
  - `ic_plus` runs the same pipeline with `--llm off|local|hosted`, interactive approver, extra scenarios.
  - Graded package unchanged since v1.0; G1–G6 and X1–X4 pass; decisions identical with LLM on or off.

## Out of scope
- Production infrastructure, real observability systems, live incident data, identity/signing.
- Web UI, persistent storage, any learned or persisted agent memory.
- Incident queue, JSON/Markdown exports, random fault injection.
- Multi-agent coordination.
- Any LLM in the graded build; any LLM making or changing a decision in the extended build.