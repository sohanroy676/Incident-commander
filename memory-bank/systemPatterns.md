# System Patterns

## Naming conventions
- Modules, functions, variables: snake_case; classes: PascalCase; constants: UPPER_SNAKE in `config.py`.
- Tools are `get_<signal>`; output helpers in `report.py` (`header`, `kv`, `decision`).

## Folder structure logic
- One responsibility per module, layered per PHASE5 section 12 (types/config/clocks -> fixtures/world -> tools -> ...).
- Tests mirror modules: `tests/test_<module>.py`; unittest only.

## Common patterns used in this project
- Frozen dataclasses for data crossing module boundaries (`types.py`).
- Tunable numbers only in `config.py`, each documented in `docs/THRESHOLDS.md`.
- Series are pure functions of absolute time; tools take `(world, clock, service, start, end)`, never an incident id.
- A tool failure becomes `Observation(status="error")`, never an exception.
- Output lines: `== M<n> TITLE ==`, `[t+..s] KIND k=v`, `DECISION kind k=v`; values via `report.fmt`.
- Predicates return `Tri` (TRUE/FALSE/UNKNOWN) from numbers only; error/stale/ambiguous evidence is UNKNOWN, which never confirms or refutes.
- Investigator tools come from a `ToolBox` of the four evidence tools; `get_logs` is never importable there.
- Real output goes to `traces/vX.Y.txt` by redirecting commands, never hand-written.

## Things to avoid
- Importing anything outside stdlib + scikit-learn in `incident_commander/`; env vars; `ic_plus` references (G1 enforces).
- Running `ruff format` over docs/ (excluded in `ruff.toml`).
- Passing text (logs, summaries) into any decision function.
