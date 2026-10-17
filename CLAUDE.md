# CLAUDE.md

@AGENTS.md

## Project context (memory bank)
Read at session start; update `progress.md` and `activeContext.md` at the end of a session.
@memory-bank/projectBrief.md
@memory-bank/tech-stack.md
@memory-bank/architecture.md
@memory-bank/activeContext.md
@memory-bank/progress.md

Also consult `memory-bank/systemPatterns.md`, `ROADMAP.md` and `docs/` when relevant.

## Rules and workflows
- Always-on rules live in `.claude/rules/` (security, commit style, testing, self-review, git workflow, session efficiency).
- Slash commands: `/commit`, `/debug`, `/new-feature` (`.claude/commands/`).
- Never commit to `main`; never push, force-push, rebase or delete branches without explicit approval.
- Generated files (`CHANGELOG.md`, `traces/*`) are never hand-edited.

## Notes
- Windows dev machine: use `.venv\Scripts\activate`; CI runs on Ubuntu/Python 3.12.
- Tests are `unittest`, not pytest. Format with `ruff format` (not black).
