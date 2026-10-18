# Incident Commander (PS4)

A deterministic incident-response agent over simulated production data (Sem VII Agentic AI course).
It investigates alerts from real signals, gates risky fixes behind time-boxed human approval, verifies
the fix, and drafts a postmortem. An optional LLM extension (`ic_plus`) never makes decisions.

**Status: v2.0 Extended release** (graded build tagged `v1.0`). All eight milestones (M1 to M8) run end to end with one command, and all
six Definition-of-Done gates (G1 to G6) pass with one command. The graded package `incident_commander/` is
frozen from here on. Planning documents: `ROADMAP.md`, `docs/DETAILED_ROADMAP.md`, `docs/PHASE1.md` to `PHASE5.md`.

Stack: Python 3.12 (works on 3.10 and later), standard library plus scikit-learn only. The graded build reads
no environment variables, no keys and no network. Verified on Python 3.12.10 with scikit-learn 1.9.1.

## Quick start (from a fresh clone)

You need Git and Python 3.12 (3.10 or later also works). Commands for Windows PowerShell and for
Linux/macOS are shown side by side.

**1. Clone**

```
git clone https://github.com/sohanroy676/incident-commander.git
cd incident-commander
```

**2. Create and activate a virtual environment**

```
# Windows (PowerShell)
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1

# Linux / macOS
python3.12 -m venv .venv
source .venv/bin/activate
```

On Windows, if activation is blocked, run `Set-ExecutionPolicy -Scope Process RemoteSigned` first, or skip
activation and call `.venv\Scripts\python` instead of `python` in every command below.

**3. Install dependencies**

```
pip install -r requirements.txt -r requirements-dev.txt
```

`requirements.txt` holds scikit-learn only. `requirements-dev.txt` holds ruff (dev only, never imported).

**4. Run the graded build** (no `.env`, no environment variables, no network)

```
python -m incident_commander run --all        # all eight milestones, about 10 s
python -m incident_commander.dod all          # gates G1-G6, about 30 s; prints one PASS/FAIL line each
```

**5. Run the extended build without a model** (also needs no `.env`)

```
python -m ic_plus run --all --llm off
```

**6. Optional: add an LLM (extension only)**

The model only writes labelled text; it never changes a decision. Skip this step to run without one.

- *Local, no key (Ollama):* install Ollama, then `ollama pull llama3.2` and keep it running. No `.env` is needed:

  ```
  python -m ic_plus run --all --llm local --llm-url http://localhost:11434/v1 --model llama3.2
  ```

- *Hosted, key required (any OpenAI-compatible API, for example Groq):* copy the template, then edit `.env`.

  ```
  # Windows (PowerShell)
  Copy-Item .env.example .env
  # Linux / macOS
  cp .env.example .env
  ```

  Fill in `.env` (it is gitignored; never commit it or paste the key anywhere else):

  ```
  LLM_BASE_URL=https://api.groq.com/openai/v1
  LLM_MODEL=<model name from your provider>
  LLM_API_KEY=<your key>
  ```

  Then run `python -m ic_plus run --all --llm hosted`. Flags `--llm-url` and `--model` override `.env`.
  Only `ic_plus` reads `.env`; `LLM_API_KEY` is used by `--llm hosted` only. Free-tier limits of hosted
  providers were not checked.

If the model is missing or unreachable, the run still finishes and prints
`llm: unavailable, deterministic fallback`.

**7. Run the tests and lint**: see [Tests, lint and format](#tests-lint-and-format).

## Demo (one command)

```
python -m incident_commander run --all
```

This runs three alerts through the whole pipeline and prints one section per milestone. It takes about
10 seconds because the approval gate waits on a real clock. Save the run with
`python -m incident_commander run --all > traces/run.txt`.

| Alert | Service | What happens |
|---|---|---|
| ALRT-9001 | checkout-service | Matched to RB-101 (rollback). High tier, so it pages priya. She stays silent, the page escalates to devon, he approves, the fix runs and latency is verified at 182 ms against a 180 ms baseline. |
| ALRT-9002 | inventory-service | Matched to RB-102 (restart). Low tier, so no approval. Latency is verified at 195 ms (resolved). A retry returns `already_executed` with the same `execution_id`. In the `fix_fails` variant latency stays at 3900 ms, the case is reopened and handed to a human, with no second fix. |
| ALRT-9003 | notification-service | Every hypothesis is refuted after 4 rounds: `no_confident_match`. Nothing is executed and the case is handed to a human with the evidence. |

Other commands:

```
python -m incident_commander tools ALRT-9001        # M1: the five read-only tools, with freshness
python -m incident_commander investigate ALRT-9001  # M3: the bounded evidence loop on its own
python -m incident_commander gates                  # M4/M5: blast-radius tiers and the approval gate
python -m incident_commander run ALRT-9002          # one alert, M1 to M8
python -m incident_commander evaluate               # M8: golden set and planted-log attack
python -m incident_commander naive                  # the no-investigation baseline, for comparison
```

## The Definition-of-Done gates

```
python -m incident_commander.dod all
```

prints one table and exits 0 only if every gate passes (about 25 seconds):

| Gate | What it proves | Run alone |
|---|---|---|
| G1 purity | Only stdlib and scikit-learn are imported; no environment access, no network modules, no `ic_plus`. | `python -m incident_commander.dod purity` |
| G2 invariants | The result is produced honestly: tools are read-only, fixtures hold no incident ids, the blast-radius tier ignores severity, no log text reaches a decision, drafting a postmortem has no side effects. | `python -m unittest tests.test_invariants -v` |
| G3 outcomes | The exact promised values: `rounds=4` for ALRT-9003, tiers per alert, escalation priya to devon after a real sleep, 195 ms resolved and 3900 ms reopened, idempotent retry, unpublished draft. | `python -m unittest tests.test_outcomes -v` |
| G4 evaluation | The golden set passes 3/3 and the planted-log attack changes no decision. | `python -m incident_commander evaluate` |
| G5 trace | A run's output has all eight headers and every acceptance value. | `python -m incident_commander.dod trace traces/run.txt` |
| G6 repro | Two fresh runs produce identical output once timestamps are removed. | `python -m incident_commander.dod repro` |

`dod all` runs G5 on a fresh run, never on the saved `traces/run.txt`, so a stale file cannot pass it.
The canaries in `tests/test_canaries.py` plant one defect at a time in a temporary copy (a `severity`
parameter, an extra import, an incident id in a fixture, and so on) and check that the matching gate fails.

## How to read the trace

Every section starts with a header `== M<n> <TITLE> ==`:

| Header | Content |
|---|---|
| M1 SIGNAL INGESTION | The alert and what each of the five tools returned, with age against its freshness budget. Log content is never shown here: it is untrusted. |
| M2 RUNBOOK GROUNDING | The ranker's scores (BM25 rank, character TF-IDF rank, fused RRF score). Retrieval only proposes candidates. |
| M3 INVESTIGATION | One tool call per `ROUND`, then the `HYPOTHESES` table (`open`, `refuted`, `confirmed`) and the verdict. |
| M4 BLAST-RADIUS CLASSIFICATION | Tier and approval requirement, decided from the action alone. |
| M5 TIME-BOXED APPROVAL | The page check demo on a real clock, then each `PAGE`, `ESCALATE` and approval. |
| M6 VERIFIED RESOLUTION | Execution (with idempotency), verification against the alert's own metric, hand-offs. |
| M7 POSTMORTEM DRAFT | The draft built from the trace (`notified=[] published=False`) and the one explicit publish. |
| M8 EVALUATION | Golden set and the differential planted-log attack. |

Two kinds of line carry the meaning:

- `[t+7.12s] ROUND n=1 tool=get_latency ...` is a trace event with seconds since the process started. The
  timestamp is the only part that changes between runs.
- `DECISION <kind> key=value ...` is a decision. These lines hold no wall-clock values, are what the gates
  compare, and are identical on every run. For example
  `DECISION verdict alert=ALRT-9003 verdict=no_confident_match runbook=none rounds=4 reason=all_refuted`.

Predicates print as `TRUE`, `FALSE` or `UNKNOWN`. A stale or failed observation yields `UNKNOWN`, never a guess.

## Tests, lint and format

```
python -m unittest discover -s tests -v          # graded build, about 3 minutes
python -m unittest discover -s tests_plus -v     # extension, about 5 minutes
python -m incident_commander.dod all             # gates G1-G6, about 30 seconds
ruff check .                                     # lint
ruff format --check .                            # format check; drop --check to rewrite files
```

CI runs ruff, both test suites and `dod all` on Ubuntu with Python 3.12.

`docs/THRESHOLDS.md` lists every tunable, where it lives (`incident_commander/config.py`) and the choices made
beyond the written spec. `traces/` holds the real, unedited output of each version; `traces/run.txt` is the
trace for the report. Do not edit a trace by hand.

## Design rules that the gates enforce

- Decisions use typed evidence only: never severity, log text or any model output.
- Thresholds live only in `incident_commander/config.py`.
- The graded package imports only the standard library and scikit-learn and never imports `ic_plus`.
- Time-boxed approval uses a real clock and a real sleep; tests never patch sleep.

## Extended build (`ic_plus`, optional)

The extension runs the same pipeline and may add AI-written text under a label. It never makes or changes a
decision: replies pass a deterministic guard, and any failure falls back to a template. Setup and the model
options (`off`, `local`, `hosted`) are in Quick start steps 5 and 6.

```
python -m ic_plus run --all --llm off                          # default; same DECISION lines as the graded run
python -m ic_plus run ALRT-9001 --approver cli --deadline 20   # you approve the page within 20 s
python -m ic_plus explain ALRT-9001 "why rollback?"            # add --llm local ... for an AI explanation
python -m ic_plus evaluate --llm off                           # M8 only; with a model it adds the X3 line
python -m ic_plus scenario all                                 # extra scenarios
```

Add `--llm local --llm-url http://localhost:11434/v1 --model llama3.2` to `run`, `explain` or `evaluate` to use
Ollama. Without a reachable model the run prints `llm: unavailable, deterministic fallback`. Demo scripts and
recorded model runs (`traces/v1.2-live.txt`, `traces/v1.3-live-evaluate.txt`) are in `docs/DEMO.md`. Gates
X1-X4 are checked by `tests_plus/test_release.py`.
