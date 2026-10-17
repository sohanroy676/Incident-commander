# Tech Stack — Incident Commander (PS4)

## Languages and frameworks
- Python 3.12 (target); code must also run on Python ≥ 3.10.
- Graded build (`incident_commander/`): Python standard library + scikit-learn only.
  - scikit-learn `>=1.5,<2` (record the exact version from the first real run).
    Used only for `TfidfVectorizer(analyzer="char_wb")` and cosine similarity.
  - No direct `numpy` import. No environment variables, no keys, no network.
  - BM25 and RRF (k=60) are hand-written in stdlib (`math`, `collections.Counter`).
- Extended build (`ic_plus/`): same as above; LLM access through stdlib `urllib.request` + `json`
  (OpenAI-compatible `/chat/completions`). No extra Python package.
- No web framework, no UI. CLI only (`argparse`), run with `python -m`.

## Tests
- Framework: `unittest` (stdlib). pytest is not used.
- Location / naming: `tests/test_<module>.py` (graded build), `tests_plus/test_<module>.py` (extension).
  Gate suites: `tests/test_invariants.py` (G2), `tests/test_outcomes.py` (G3), `tests/test_canaries.py`.
- Run:
  - `python -m unittest discover -s tests -v`
  - `python -m unittest discover -s tests_plus -v`
  - `python -m incident_commander.dod all`   (all six Definition-of-Done gates G1–G6)
- Real-clock tests: real `time.sleep`, lower-bound timing asserts only, never patched sleep.

## Lint / format
- ruff (dev-only, in `requirements-dev.txt`; never imported by code).
  - Lint: `ruff check .`
  - Format: `ruff format .`

## Setup / run / dev commands
- `python3.12 -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt`          (scikit-learn only)
- `pip install -r requirements-dev.txt`      (ruff)
- Graded demo: `python -m incident_commander run --all`
- Extended demo: `python -m ic_plus run --all --llm off|local|hosted`
- No build step, no installer, no packaging.

## Database / external services
- Database: none. All data is simulated in-memory fixtures; no persistent storage.
- Graded build: no external services.
- Extended build (optional):
  - Local: Ollama at `http://localhost:11434/v1` (no key).
  - Hosted: a free-tier OpenAI-compatible API, e.g. Groq `https://api.groq.com/openai/v1` (key required).
  - Keys only in `.env` (gitignored). See architecture.md.

## Version control / CI
- git; branch per roadmap version (`vX.Y-<name>`), merge to `main`, tag each version.
- Optional GitHub Actions: setup-python 3.12, `pip install -r requirements.txt`,
  `python -m incident_commander.dod all`.