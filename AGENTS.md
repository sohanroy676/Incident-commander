# AGENTS.md
Incident Commander (PS4): a deterministic incident-response agent over simulated data, plus an optional LLM extension (`ic_plus`) that never makes decisions.
Stack: Python 3.12 (≥3.10), stdlib + scikit-learn only; unittest; ruff; Ollama / OpenAI-compatible API (extension only).
- Setup: `python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt`
- Run: `python -m incident_commander run --all` · `python -m ic_plus run --all --llm off`
- Test: `python -m unittest discover -s tests -v` · `python -m incident_commander.dod all`
- Lint: `ruff check . && ruff format .`
## Critical conventions
- `incident_commander/` imports only stdlib + scikit-learn, reads no env vars/keys/network, and never imports `ic_plus`.
- Decisions use typed evidence only: never severity, log text or LLM output; tunables live only in `config.py`.
- Never hand-edit a trace or fake a result; tests ship with the code; real clocks, no patched sleep.
- Extension keys only in `.env` (gitignored); never hardcode, print or log them.
- Proposed, not approved: `ic_hub/` (v2.2) would be stdlib only and never imported by `incident_commander/` or `ic_plus/`; see `docs/EXTENSION_PLAN.md`.
Detailed rules: see `.claude/rules/` (workflows are slash commands in `.claude/commands/`); see also `CLAUDE.md`.