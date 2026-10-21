# Contributing

## Setup

    python3.12 -m venv .venv
    source .venv/bin/activate          # Windows: .venv\Scripts\activate
    pip install -r requirements.txt -r requirements-dev.txt

## Checks before a change is ready

    ruff check . && ruff format --check .
    python -m unittest discover -s tests -v
    python -m unittest discover -s tests_plus -v
    python -m incident_commander.dod all

The suites use real clocks (about 3 minutes for `tests/`, about 6 for `tests_plus/`). Tests are `unittest`, not
pytest, and never patch sleep or fake a clock. Timing asserts are lower bounds only.

## Ground rules

- `incident_commander/` is frozen at tag `v1.0`: `git diff v1.0 -- incident_commander/` must stay empty.
  `ic_plus/` may import it; the reverse never happens.
- `incident_commander/` uses only the standard library and scikit-learn, and reads no environment variables.
- Decisions use typed evidence only. Tunables live in `config.py`.
- Never hand-edit a trace or `CHANGELOG.md`; both are generated. DECISION lines in `traces/run.txt` must not change.
- Never commit secrets. Keys go in `.env`, which is gitignored.
- Tests ship with the code, including adversarial cases.

## Workflow

- One branch per change off `main` (`feature/...`, `fix/...`, `docs/...`, or a version branch). Never commit to `main`.
- Conventional Commits: `type(scope): summary`, imperative, under 50 characters, with a short body saying why.
- Do not push, force-push, rebase or delete branches or tags without the owner's approval.
- Significant, hard-to-reverse decisions get an ADR in `docs/adr/` (copy `adr-template.md`).

## Licensing

The project is released under the MIT License (see `LICENSE`).
