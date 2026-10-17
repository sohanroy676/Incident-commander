# Incident Commander (PS4)

A deterministic incident-response agent over simulated production data (Sem VII Agentic AI course).
It investigates alerts from real signals, gates risky fixes behind time-boxed human approval, verifies
the fix, and drafts a postmortem. An optional LLM extension (`ic_plus`, from v1.1) never makes decisions.

**Status: v0.1 Foundations.** Simulated world, five read-only signal tools, M1 output and the G1 purity gate.
The rest follows `ROADMAP.md` (detail in `docs/DETAILED_ROADMAP.md`).

## Setup

```
python3.12 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
```

## Commands (v0.1)

```
python -m incident_commander tools ALRT-9001     # M1: five tools with freshness (also ALRT-9002, ALRT-9003)
python -m incident_commander.dod purity          # G1: stdlib + scikit-learn only, no env vars, no ic_plus
python -m unittest discover -s tests -v          # tests
ruff check . && ruff format .                    # lint and format
```

The full README (demo, all gates, how to read the trace) arrives with v1.0.
