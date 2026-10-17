# Phase 3: Approaches, Comparison and Recommendation — PS4 "The Incident Commander"

> Inputs: the two problem-statement screenshots (source of truth), PHASE1.md (requirements R1–R10, acceptance values, ambiguities A1–A18) and PHASE2.md (domain knowledge, sources S1–S34).
> Scope of this phase: compare genuinely different ways to solve the problem, recommend one, and fix the Definition of Done. **No code and no detailed module design here**; that is Phase 4.
> Legend used throughout: *(inference)* = my reasoning, not a sourced fact. *(prediction)* = an expected result that has **not** been measured yet and must be confirmed by a real run.

---

## 0. What changed since Phase 2 (your answers)

| Open point | Your decision (2026-10-17) | Consequence for this phase |
|---|---|---|
| A2: six Definition-of-Done gates (page 13) | Screenshots are everything; **write our own** DoD | §2 defines six gates with exact commands. They are ours, not the faculty's, and the viva should say so. |
| A1: LLM allowed? | Build **strictly per the statement first** (stdlib + scikit-learn, no LLM). Then an **extended** end-to-end version with an **optional LLM mode** | Two deliverables. §6 recommends an architecture where the extension is a switchable layer on top of an untouched baseline, so either can be demoed alone. |
| A3: fixtures | Unchanged default: we author all simulated data | |

---

## 1. Two deliverables, one rule between them

You want to be able to demo either version depending on the audience. That only works if the two can never contaminate each other. So, before comparing approaches, here is the constraint every approach below is judged against:

| | **Statement build** ("baseline", `incident_commander`) | **Extended build** (`ic_plus`) |
|---|---|---|
| Purpose | Satisfy PS4 exactly; graded artefact | Show a more realistic end-to-end system and an LLM option |
| Dependencies | Python stdlib + scikit-learn only. No env vars, no keys, no network | Still stdlib + scikit-learn for the code itself; the LLM is reached over HTTP with stdlib `urllib` (§5.3), so no new Python package is needed |
| LLM | Never | Optional, `--llm off` by default |
| Must pass | DoD gates G1–G6 (§2) | G1–G6 still pass on the baseline, **plus** extension gates X1–X4 (§2.3) |
| Dependency direction | Never imports `ic_plus` | Imports `incident_commander`; never edits it |

The one-way import rule is the whole trick: if the baseline never imports the extension, the extension cannot break it, and G1 can check that mechanically.

---

## 2. Definition of Done (our six gates)

The statement says the build is complete only when "all eight milestones run end to end and all six Definition-of-Done gates pass under their exact verifying commands, with every trace pasted from a real terminal run". Since page 13 isn't available, these gates are written to cover every explicit requirement and acceptance value from PHASE1 §3.1–3.3 **exactly once**, so nothing is untested and nothing is double-counted.

Design choices behind the gates:
- **Tests use `unittest` (stdlib), not `pytest`.** `pytest` is a third-party package, and "only scikit-learn beyond the standard library" is easiest to defend if even the test runner is stdlib. *(inference)*
- **Every gate is one command with exit code 0 = pass**, so the grader (or you, during the viva) can run them blind.
- **Python 3.12** is the target (your decision); the minimum is 3.10, because G1 uses `sys.stdlib_module_names`, which was added in 3.10.
- Command names are proposals; Phase 4 may rename modules, but the six gates and what they check are now fixed.

### 2.1 The six gates

| Gate | Name | Exact verifying command | Passes when | Covers |
|---|---|---|---|---|
| **G1** | Purity and zero-config | `python -m incident_commander.dod purity` | Static (AST) scan of the baseline package finds: every top-level import is in `sys.stdlib_module_names` or is `sklearn`; no `os.environ`, `os.getenv`, `dotenv`; no `socket`, `urllib.request`, `http.client` (no network); no import of `ic_plus` | In-scope/constraint lines; §1 separation |
| **G2** | Structural honesty | `python -m unittest tests.test_invariants -v` | (a) `inspect.signature(classify_remediation)` has no severity-like parameter and the call works on an action alone; (b) every fixture record is keyed by `service` + timestamp and no fixture field is an incident ID (Outcome 9); (c) the decision function's inputs contain no log text (checked by signature and by type); (d) building a postmortem draft with a spy outbox leaves the outbox empty; (e) each of the five tools is read-only (repeat calls return equal data and mutate nothing) and declares `max_staleness_s` | R1, R3c, R4, R7, Outcome 9, SC5 |
| **G3** | Acceptance outcomes | `python -m unittest tests.test_outcomes -v` | One test per expected value in PHASE1 §3.2 for Outcomes 1–6, asserting the **exact** strings and numbers (e.g. `rounds == 4`, `verdict == "no_confident_match"`; `engineer-priya` → `engineer-devon`; `already_executed` with equal `execution_id`). The escalation test uses the real clock: it asserts measured `time.monotonic()` elapsed ≥ 0.4 s | Outcomes 1–6, R3, R5, R6 |
| **G4** | Evaluation | `python -m incident_commander evaluate` | Prints `golden: 3/3 pass` and `attack: verdict=matched remediation=rollback_deployment (unchanged)`; exits non-zero on any miss. The attack check is **differential**: run the same incident with and without the planted log line and assert identical decision inputs and outputs | R8, Outcomes 7–8 |
| **G5** | End-to-end real trace | `python -m incident_commander run --all > traces/run.txt` then `python -m incident_commander.dod trace traces/run.txt` | One process runs all eight milestones in order; the checker finds all eight milestone markers and every acceptance value in the saved trace. `traces/run.txt` is the file you paste into the report | R10, SC1, "traces pasted from a real terminal run" |
| **G6** | Reproducibility | `python -m incident_commander.dod repro` | Runs the full flow twice in fresh subprocesses and compares the decision lines (verdicts, tiers, approvals, statuses) after removing wall-clock timestamps and random IDs; any difference fails | Honest reporting; "deadline-honest, not aspirational" |

One convenience command, `python -m incident_commander.dod all`, runs G1–G6 in order and prints a pass/fail table. It is a wrapper, not a seventh gate.

### 2.2 Why these six and not others

- G2 checks **how** the result is produced, G3 checks **what** is produced. A system that hard-codes Outcome 2's strings would pass G3 but fail G2(a)/(c). Faculty questions about "did you just print the expected values?" are answered by G2.
- G4 is separate from G3 because evaluation (history + attack) is its own requirement (R8) and its own deliverable line.
- G6 exists because a deterministic decision path is our main defence (§4); if two runs disagree, that claim is false.

### 2.3 Extension gates (extended build only)

| Gate | Command | Passes when |
|---|---|---|
| **X1** Baseline untouched | `python -m incident_commander.dod all` run in the extended repo | G1–G6 all pass with `ic_plus` present |
| **X2** LLM off/unavailable | `python -m ic_plus run --all --llm off` and again with `--llm ollama` while no LLM server is running | Both complete; every decision line equals the baseline's; the second prints `llm: unavailable, deterministic fallback` instead of failing or pretending |
| **X3** LLM cannot change decisions | `python -m ic_plus evaluate --llm ollama` (server running) | `golden: 3/3`, attack unchanged, and the decision lines equal the baseline's. If the LLM ever changes a verdict, tier, approval or status, this gate fails |
| **X4** LLM output is validated | `python -m unittest tests_plus.test_llm_guard -v` | Malformed, out-of-schema or unknown-tool LLM replies (fed from recorded fixtures, no live model needed) are rejected and logged, never executed |

---

## 3. The approaches

Six candidates, chosen to be **genuinely different in where the decision comes from**, not variations of one design. Two are non-agentic, three are agentic, one is multi-agent.

For each: workflow, how it meets R1–R8, feasibility, cost, risks, how to evaluate it.

### A. Naive retrieve-and-execute pipeline (non-agentic straw man)

**Workflow.** Alert text → hybrid retriever → top-1 runbook → run its remediation → (optionally) postmortem.

```
alert ─▶ retrieve(runbooks) ─▶ top-1 ─▶ remediation ─▶ done
```

This is exactly the failure the problem statement describes: "alert triage collapses into pattern-matching the nearest runbook".

| Aspect | Assessment |
|---|---|
| Meets requirements? | ❌ R3 (no correlation, no loop), ❌ Outcome 1 (would return the nearest match for `ALRT-9003` instead of `no_confident_match`) *(prediction)*. R4–R7 could be bolted on, but the core is wrong |
| Feasibility / effort | Very small |
| Cost | Zero |
| Risk | Confidently wrong answers; nothing to defend in a viva as a solution |
| Why keep it | **As an evaluation baseline.** Running it on the same fixtures shows, with real output, what the investigation loop adds. That is the "non-agentic baseline" a fair comparison needs |

### B. Static rule pipeline / decision table (strongest non-agentic design)

**Workflow.** Fetch **all** signals from all five tools once, evaluate every runbook's signature predicate (e.g. "latency elevated AND error rate normal AND deploy within window") in one pass, pick the runbook whose predicates all hold, else `no_confident_match`. No loop, no choices about what to look at next.

```
alert ─▶ call all 5 tools ─▶ evaluate every signature ─▶ match | no_confident_match ─▶ gates ─▶ verify ─▶ draft
```

| Aspect | Assessment |
|---|---|
| Meets requirements? | ✅ R1, R2, R4–R8 can all be met. ⚠️ **R3 only in letter-bending form**: there is no "investigation loop … with a bounded round budget" and no "gathers additional evidence"; reporting `rounds=4` would be faked. Outcome 1 explicitly says 9003 "exhausts its full round budget (`rounds=4`)", so B contradicts the statement's own wording |
| Feasibility / effort | Small |
| Cost | Zero |
| Risk | Fails the "investigative, not scripted" objective by construction; examiner can call it a lookup table. Also scales badly when tools are expensive or slow, because it always calls everything *(inference)* |
| Strength | Deterministic, trivially injection-proof (decision reads only numbers), easy to test |
| Why keep it | Honest point for the viva: **with only five cheap simulated tools, B would reach the same verdicts as C** *(prediction)*. C is chosen because the statement requires a bounded evidence-gathering loop, and because the loop's advantages (fetch only what is needed, re-fetch stale data, stop early) are real once tools have cost. B is also a useful **test oracle**: C's verdicts should equal B's on every fixture (optional differential test) |

### C. Deterministic single agent: hypothesis-driven bounded loop (classic agent)

**Idea.** The retriever **proposes** candidate runbooks (hypotheses). Each runbook carries a machine-checkable **signature** (predicates over metrics and deploy timing). Each round, the agent picks the most useful unchecked predicate of the leading open hypothesis, calls **one** read-only tool to test it, and updates every hypothesis it touches (confirmed / refuted / open). It stops when one hypothesis is fully confirmed (`matched`) or the round budget runs out (`no_confident_match` → hand off to a human). Everything after the verdict is an explicit state machine with real gates.

```
                ┌──────────────── investigation loop (≤ 4 rounds) ───────────────┐
alert ─▶ hybrid │ choose next predicate ─▶ call 1 tool ─▶ freshness check ─▶     │
retrieval ─▶    │ update hypotheses ─▶ confirmed? ── yes ─▶ verdict=matched      │
candidates +    │        ▲                    no ─┘                              │
scores+margin   │        └──── budget left? ── no ─▶ verdict=no_confident_match ─┼─▶ handoff
                └────────────────────────────────────────────────────────────────┘
matched ─▶ classify_remediation(action) ─▶ tier, requires_approval
        ─▶ [approval gate: page primary, real deadline, escalate to secondary]   (only if required)
        ─▶ execute (idempotent ledger → execution_id)
        ─▶ verify: re-query the ORIGINAL signal ─▶ resolved/verified | reopened → handoff
        ─▶ postmortem draft (pure function of the trace) ── publish() is the only side effect
```

**Why this counts as an agent** *(inference, based on [S14][S15][S16])*: it perceives through tools, keeps state (its hypotheses), **chooses** its next action from that state, acts on the world through gated actuators, and checks the effect of its own actions. Its policy is a deterministic rule rather than an LLM. In Anthropic's vocabulary [S15] it is closest to a *workflow* with an agent-like loop; in the classic textbook sense [S14] it is an agent. You should say both in the viva; the point is that the autonomy is **bounded on purpose**.

**How it meets each requirement**

| Req | How C satisfies it |
|---|---|
| R1 | Five typed, read-only tool functions, each returning `(data, as_of, max_staleness_s)`; the loop checks freshness before using a result (§5.2 policy) |
| R2 | Hybrid retriever ranks candidates and **prints** scores and the top-2 margin, making the shared-vocabulary problem visible |
| R3 | The loop correlates latency, error rate and deploy timestamp within a window before `alert.fired_at`; bounded at 4 rounds; unmatched → keeps gathering, then `no_confident_match` |
| R4 | `classify_remediation(action)` maps action → tier → `requires_approval`; severity is never passed |
| R5 | Page object with a `time.monotonic()` deadline; real `time.sleep`; escalation primary → secondary; acknowledged page does not escalate |
| R6 | After execution, re-query the same metric for the same service; tolerance rule decides `resolved` vs `reopened` |
| R7 | Draft built from the incident's own trace with no I/O; `publish()` is the only function that notifies |
| R8 | Golden set and differential attack test (G4); the decision function's inputs are numbers and timestamps only |

| Aspect | Assessment |
|---|---|
| Feasibility / effort | Medium. The hard parts are fixture design (correlation must be genuine, Outcome 9) and the loop's "next predicate" rule, not code volume |
| Cost | Zero. Runtime of a full run is dominated by the deliberate 0.4 s sleep *(prediction)* |
| Risks | (1) Fixtures accidentally make the loop trivial (every signature decided in round 1); (2) the "next predicate" rule over-fits the three demo alerts; (3) tolerance and window thresholds look arbitrary. Mitigations: golden-set incidents distinct from demo alerts (A13), thresholds stated in one config table with their justification, and B as an oracle |
| Determinism | Full. Same inputs → same trace (G6) |
| Injection resistance | Structural: log text is not an input to any decision function [S21][S22] |
| Explainability | High; every decision is a printed predicate with its evidence |

### D. LLM-driven ReAct agent

**Workflow.** An LLM receives the alert and tool descriptions, then loops: reason → call a tool → observe → reason [S16], and finally outputs the verdict and remediation. Gates (approval, verification) may or may not be enforced in code around it.

| Aspect | Assessment |
|---|---|
| Meets requirements? | ❌ Violates the dependency/no-network/no-key constraint in its usual forms (SDKs, hosted APIs). ⚠️ Exact acceptance values (Outcome 2's tiers, Outcome 1's `rounds=4`) are no longer guaranteed, because the model can choose differently between runs. ❌ R8 is at risk by design: the planted log line is exactly the indirect prompt injection that OWASP ranks as the top LLM risk [S19][S20], and the model reads logs as part of its context |
| Feasibility / effort | Low code, high effort to make reliable; would need many retries and guards to hit exact values |
| Cost | Hosted API: per-token charges plus a key (forbidden in the baseline). Local model: free but slow on a laptop, and output quality varies by model *(inference)* |
| Risks | Non-determinism (fails G6), injection (fails G4 unless defended), hallucinated tool calls, unverifiable "reasoning". Research context: on the OpenRCA benchmark the best model + agent setup solved 11.34 % of cases [S25] |
| Verdict | **Rejected** for the decision path in both builds. Useful only as an *optional ablation* (§7.3) to show, with real output, why the decision must not read logs |

### E. Constrained hybrid: deterministic core + LLM in advisory and narrative roles

**Idea.** Keep C unchanged as the decision-maker. Add an LLM only where language helps and where its output **cannot** reach a consequential action. This follows the prompt-injection design patterns literature: once an LLM has read untrusted input, it must be impossible for that input to trigger consequential actions [S21]; separate control flow from data flow [S22].

| LLM role (extended build) | What the LLM sees | What its output can do | Pattern [S21] |
|---|---|---|---|
| **Narrator**: write the human-readable postmortem narrative and an incident summary | The structured trace (facts, numbers), **not** raw logs by default | Fills a clearly labelled "AI-drafted narrative" section of the **draft**; the factual timeline stays deterministic; publishing still needs explicit `publish()` | Context-minimization |
| **Explainer**: answer "why did you roll back?" in plain English | The trace | Text only, shown to the human | Context-minimization |
| **Advisor**: suggest which hypothesis/predicate to check next | Alert fields, candidate list, evidence so far (numbers only) | A suggestion that the deterministic loop **may** accept if it names an allowed, not-yet-checked predicate; otherwise ignored. The verdict is still computed from predicates | Action-Selector / Plan-Then-Execute |

What the LLM **never** does in E: decide the verdict, the tier, `requires_approval`, the approval outcome, the verification status, or call any tool with side effects.

| Aspect | Assessment |
|---|---|
| Meets requirements? | ✅ Baseline unaffected (LLM off by default, separate package). ✅ X1–X4 make "LLM cannot change decisions" a tested property, not a claim |
| Feasibility / effort | Medium on top of C: an HTTP client in stdlib, a JSON-schema check, fallback when the server is down, recorded fixtures for tests |
| Cost | Free with a local open-source model through Ollama (§5.3). A hosted API is possible but needs a key and money, so it is not the default |
| Risks | (1) **Advisor** can waste rounds: a poor suggestion order could exhaust the 4-round budget before the right hypothesis is confirmed, turning `matched` into `no_confident_match`. Mitigation: the advisor may only **reorder within** the deterministic candidate list, and X3 fails if any verdict changes. (2) **Narrator** reading logs could repeat the attacker's false claim in the draft ("payment-service caused this"). Mitigation: logs excluded from the LLM context by default; if included, quoted as untrusted data, and the narrative is a draft a human reviews. (3) Local model too slow on your hardware. Mitigation: everything works with `--llm off`; demo the LLM part with a small model |
| Explainability | High for decisions (unchanged); the LLM text is clearly marked as non-authoritative |

### F. Multi-agent (incident-command roles as separate agents)

**Idea.** Map ICS roles (Phase 2 §1.2 [S1][S3]) to agents: an Investigator, an Operations agent (remediation), a Communications agent (paging), a Scribe (postmortem), coordinated by a Commander agent, exchanging messages.

| Aspect | Assessment |
|---|---|
| Justification test | Multi-agent design pays off when sub-tasks need **parallelism**, **separate contexts too large for one agent**, or **different trust levels** *(inference, consistent with [S15]'s "simplest solution" advice)*. Here: the steps are strictly sequential (no verdict → no remediation → no verification); the whole state fits in one small object; and the trust boundary (log text vs decisions) is already enforced by function signatures |
| Meets requirements? | Could, but adds message-passing that the statement never asks for and that every gate would have to see through |
| Cost / risk | More code, more nondeterminism if agents are LLMs, harder to trace "who decided what" |
| Verdict | **Rejected.** The ICS roles are kept as **modules** inside one agent (investigator, gatekeeper, executor, verifier, scribe), which gives the same separation of concerns without the coordination overhead. This is the honest viva answer to "why not multi-agent?" |

### Framework option (considered, not a separate approach)

Agent frameworks such as LangGraph or CrewAI would provide graphs, state and LLM integration. They are third-party packages, so they are **excluded from the baseline** by the dependency rule, and in the extended build they would add a large dependency to do what roughly a page of explicit state-machine code does. Not chosen. *(inference; framework licences and features were not re-checked in this phase)*

---

## 4. Side-by-side comparison

### 4.1 Requirements fit

✅ satisfied by design · ⚠️ possible with caveats · ❌ not satisfied

| | A Naive | B Rules | C Det. agent | D LLM ReAct | E Hybrid (C + LLM) | F Multi-agent |
|---|---|---|---|---|---|---|
| R1 typed tools + freshness | ⚠️ | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| R2 hybrid retrieval, shown | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| R3 correlation loop, round budget | ❌ | ⚠️ no real loop | ✅ | ⚠️ not exact | ✅ | ✅ |
| R4 action-only blast radius | ⚠️ | ✅ | ✅ | ⚠️ unless in code | ✅ | ✅ |
| R5 real time-boxed escalation | ⚠️ | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| R6 verified resolution | ❌ | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| R7 zero-side-effect draft | ⚠️ | ✅ | ✅ | ⚠️ | ✅ (LLM text in draft only) | ✅ |
| R8 golden + attack | ❌ | ✅ | ✅ | ❌ injection risk | ✅ (X3 tested) | ⚠️ |
| stdlib + sklearn, no keys | ✅ | ✅ | ✅ | ❌ | ✅ baseline / ext uses stdlib HTTP | ✅ if no LLM |
| Exact values reproducible (G6) | ✅ | ✅ | ✅ | ❌ | ✅ | ⚠️ |

### 4.2 Practical criteria

| | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| Relative effort | XS | S | M | M code / L reliability | M + S on top of C | L |
| Money cost | 0 | 0 | 0 | API fees or 0 locally | 0 (local model) | 0–fees |
| Hardware | any | any | any | GPU/large RAM helps | baseline any; LLM mode needs a machine that can run a small local model | any |
| Determinism | full | full | full | none | full for decisions | depends |
| Injection resistance | n/a (wrong anyway) | structural | structural | weak | structural for decisions; residual risk in narrative text | depends |
| Viva defensibility | as a baseline only | "isn't this a lookup table?" | strong | weak for this statement | strong, and shows LLM literacy | weak ("why multi?") |
| Demo value | shows the failure | — | shows the full PS4 workflow | — | shows a modern LLM agent safely bounded | — |

---

## 5. Key sub-decisions inside the recommended design

Phase 2 listed open design questions. These are the defaults I recommend carrying into Phase 4; each is reversible.

### 5.1 Retrieval pairing (R2, A5)

**Recommend: BM25 (stdlib) + TF-IDF over character n-grams (`analyzer="char_wb"`, scikit-learn), fused with Reciprocal Rank Fusion, k = 60** [S10][S11][S13].
- The two are genuinely different signals: BM25 is word-level with saturation and length normalisation; character n-grams tolerate word-form variation ("rollback" / "rolled back").
- LSA (`TruncatedSVD`) is rejected for the baseline: with a corpus of roughly 5–10 runbooks it can produce at most that many components, far below the ~100 the scikit-learn docs suggest for LSA [S12], so it would be a weak and hard-to-justify component *(inference)*.
- RRF avoids calibrating two different score scales [S13].
- Print each runbook's two ranks, fused score and the **top-2 margin**; a small margin is the visible "retrieval can't tell these apart" signal R2 asks for.

### 5.2 Freshness policy (R1, A14)

**Recommend: refetch once, then distrust.** If a tool result is older than its declared `max_staleness_s`, the loop re-calls the tool (this uses a round). If still stale, the observation is marked `untrusted` and **cannot confirm a predicate**; it can only be reported. So stale data can push the outcome toward `no_confident_match`, never toward a confident wrong match. Verification (R6) **refuses** to mark `verified: True` from stale data.

### 5.3 LLM access for the extended build

- **Default runtime: Ollama**, an open-source local model server. Its chat endpoint is `POST http://localhost:11434/api/chat` and supports tool definitions as JSON-schema `function` objects, returning `tool_calls` [S35]. It can constrain replies to a supplied JSON schema via the `format` parameter [S37]. It also offers an OpenAI-compatible endpoint at `http://localhost:11434/v1/`, where a key value must be sent but is ignored [S36].
- **Call it with stdlib `urllib.request` and `json`**, not an SDK, so the extended build still installs nothing beyond scikit-learn. Endpoint and model come from **command-line flags** (`--llm ollama --model <name>`), not environment variables, keeping the statement's no-env-var spirit even in the extension.
- **Free-tier hosted API (your decision: local *or* free tier, e.g. Groq).** Groq exposes an OpenAI-compatible endpoint at `https://api.groq.com/openai/v1` and requires an API key [S38]. Because Ollama's local server also speaks the OpenAI-compatible protocol [S36], the extension needs **one** stdlib client with a swappable `--llm-url` and `--model`: `--llm-url http://localhost:11434/v1` (local) or `--llm-url https://api.groq.com/openai/v1` (hosted). Free-tier limits were not checked in this phase; verify them before the demo.
- **Key handling (important):** the statement forbids env vars and keys, so this applies to the baseline only. For the extension the key is read from a **gitignored file passed by flag** (`--llm-key-file path`), never an environment variable, never committed, never printed in traces. This keeps the baseline's "no key, no env var" property provable by G1, since only `ic_plus` touches a key.
- **Privacy note:** with a hosted API, only the structured, simulated incident trace is sent (no real data exists in this project); logs stay out of the prompt by default (see E).
- Which model to use, and whether your machine runs a local one fast enough, must be measured in Phase 5; I have not tested any model on your hardware. Since you are unsure, the plan assumes **either** local or free-tier hosted, so the LLM mode does not depend on your laptop.

### 5.4 The five tools (R1, A4)

**Recommend:** `get_latency(service, start, end)`, `get_error_rate(service, start, end)`, `get_deployments(service, start, end)`, `get_logs(service, start, end)`, and `get_dependencies(service)` (service topology). The alert itself is the **input**, not a tool.
- The topology tool gives the loop a metric-based way to test the attacker's claim: check `payment-service`'s own latency and error rate. If they are normal, the "downstream dependency" hypothesis is refuted by **numbers**, while the log line is never read by the decision *(inference; to be designed in Phase 4)*.
- `get_logs` exists so logs can be shown in the trace and postmortem as **labelled untrusted context**, which is also where the planted line appears.

### 5.5 Other defaults

| Topic | Default | Reason |
|---|---|---|
| Verification tolerance (A6) | `resolved` if post-fix value ≤ baseline × 1.10 | 195/180 = 1.083 passes; 3900/180 ≈ 21.7 fails. One documented constant |
| Correlation window (A8) | Deploy counts if it happened within a fixed window (e.g. 30 min) **before** `alert.fired_at`; "elevated" and "normal" are ratios to a per-service baseline | Mirrors "what touched it last" [S4]; all thresholds in one table |
| What a round is (A7) | One tool call that tests one predicate (a refetch for staleness also costs a round) | Makes `rounds=4` meaningful and countable |
| Handoff (A10) | After `no_confident_match` or `reopened`: stop, attach evidence, assign to a human; no automatic second remediation | Honest reporting; avoids compounding a wrong fix |
| Idempotency key (Outcome 5) | `(incident_id, action, service)` → stored `execution_id` (UUID) in an in-memory ledger | Stripe-style keys [S18] |
| Page state machine (R5) | `PENDING → ACKNOWLEDGED` or `PENDING → ESCALATED`; `check()` reads `time.monotonic()` [S17] | Outcome 3's three cases map to these states |
| Fixtures (Outcome 9) | Signals stored per service with real timestamps; incidents reference only service + time | Correlation must be a real join, not a lookup |
| Direct `numpy` imports | None in our code (it comes with scikit-learn, but we stay literal to "only scikit-learn") | Keeps G1 simple to defend |

---

## 6. Recommendation

**Build Approach C as the statement build, and Approach E (C + an optional, bounded LLM layer) as the extended build. Keep A as an evaluation baseline. Reject B, D and F as solutions, with B optionally kept as a test oracle.**

```
incident_commander/            ← statement build (stdlib + scikit-learn)
   tools · retrieval · investigator · blast_radius · approval · executor · verifier · postmortem · evaluate · dod
ic_plus/                       ← extended build (imports incident_commander, never the reverse)
   llm client (urllib) · guard (schema + allow-list) · narrator · explainer · advisor · end-to-end runner
tests/        → G2, G3        tests_plus/  → X4
traces/run.txt                 ← pasted evidence (G5)
```

### 6.1 Justification against the official requirements

| Statement says | Why C (and E on top) fits | Why the alternatives fit worse |
|---|---|---|
| "investigates … by correlating real signals rather than trusting retrieval rank" | Retrieval only proposes; predicates over metrics and deploy timing decide | A trusts rank; D lets text drive decisions |
| "investigation loop … with a bounded round budget, so an unmatched signature gathers additional evidence" | The loop is real, counted and bounded; Outcome 1's `rounds=4` is a natural result | B has no loop, so `rounds=4` would be invented |
| "only the remediation action does" enter approval | `classify_remediation(action)` has no severity parameter (checked by G2) | Same possible in others, but D cannot guarantee it |
| "real deadline, a real `time.sleep` … real escalation" | Monotonic clock, real sleep, asserted in G3 | — |
| "verified resolution … not assumed fixed" | Re-query the original metric; reopen on failure | A has no verification |
| "zero side effects … only an explicit `publish()`" | Pure draft function; spy-outbox test (G2d). In E, LLM text only lands in the draft | — |
| "planted log line … must not change the conclusion" | Decision inputs exclude log text; differential test (G4); in E, X3 re-checks with the LLM on | D reads logs by design |
| "only scikit-learn beyond the standard library; no signing key or environment variable" | Baseline uses exactly that; E reaches a local LLM through stdlib HTTP with CLI flags | D needs SDKs or keys; frameworks add packages |
| "investigative rather than scripted, deadline-honest, blast-radius-aware" | Each phrase maps to a tested gate (G3, G2, G6) | — |
| Your rule 4: no agents without justification; rule 5: simplest architecture | One agent; multi-agent rejected with a stated test (§3F); LLM only where language adds value | F and D add complexity the statement doesn't need |

### 6.2 What to say in the viva about "is it agentic?"

A short version you should be able to give in your own words:
1. "The statement wants an agent in the classic sense: it perceives through five tools, keeps hypotheses, chooses what evidence to fetch next, acts through gated actuators, and verifies its own actions [S14]."
2. "Its policy is deterministic on purpose. The outcomes are exact, the attack must fail, and a deterministic decision path is the strongest known defence against injected text [S21][S22]."
3. "In the extended version I add an LLM where language helps: narration, explanation and advice. It is tested (X3) to never change a decision, which is the same principle recent prompt-injection research recommends."
4. "I compared it with a naive pipeline (A), a static rule table (B), an LLM ReAct agent (D) and a multi-agent design (F); here is why each was rejected."

---

## 7. Evaluation plan

All numbers below are **targets or predictions**, not results. Results will be reported only from real runs in Phase 5/6.

### 7.1 What is measured, and against what

| Evaluation | Systems | Measure | Target |
|---|---|---|---|
| Acceptance outcomes (G3) | C | exact-value tests | all pass |
| Golden set (G4) | C, and A for contrast | verdict + remediation correct per incident | C: 3/3. A: reported as measured |
| Adversarial attack (G4) | C | decision unchanged with vs without planted line | identical |
| Retrieval diagnostics | retriever alone | top-1 vs true runbook; top-2 margin per alert | reported, expected to be small on overlapping runbooks *(prediction)* |
| Naive vs investigative | A vs C on demo alerts + golden set | correct verdicts; especially `ALRT-9003` | shows what the loop adds |
| Reproducibility (G6) | C | identical decision lines across runs | identical |
| LLM safety (X2, X3) | E with LLM off / unavailable / on | decisions equal to C | identical |
| LLM usefulness (optional) | E narrator | you (and maybe a classmate) rate the narrative for factual errors against the trace | reported qualitatively; no accuracy claim |

### 7.2 Honesty rules for reporting
- 3/3 on a golden set we wrote ourselves is a **regression check**, not an accuracy claim (Phase 2 §7.1).
- Golden-set incidents must differ from `ALRT-9001/9002/9003` (A13), or the evaluation tests the demo against itself.
- State the attack model: the attacker controls log text only, not metrics or deploy history.

### 7.3 Optional ablation for the viva (extended build only)
Run a deliberately **unsafe** variant where the LLM reads the logs and picks the remediation (Approach D), on the attack incident, and record what happens. Whatever the result, it is informative: if the model is fooled, it demonstrates the threat; if not, it shows that safety would then depend on model behaviour rather than structure. This variant is never part of the normal run and is clearly labelled.

---

## 8. Risk register (recommended design)

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| K1 | Fixtures make investigation trivial or leak the answer (Outcome 9 flaw) | Medium | High (examiner calls it scripted) | Key by service + time; G2(b); distinct golden incidents; show at least one hypothesis being refuted mid-loop |
| K2 | Thresholds look tuned to the expected values | Medium | Medium | One threshold table with a reason per value; golden set exercises them on different numbers |
| K3 | Real `time.sleep` makes tests flaky on a busy machine | Low | Low | Assert elapsed ≥ 0.4 s (never ≤); deadline 0.3 s leaves margin |
| K4 | Extension quietly changes baseline behaviour | Low | High | One-way imports (G1); X1 runs the baseline gates in the extended repo |
| K5 | Local LLM too slow or unavailable at demo time | Medium | Low | `--llm off` default; X2 fallback; demo LLM features with recorded output if needed, labelled as recorded |
| K6 | LLM narrative repeats the attacker's claim | Medium | Medium | No raw logs in LLM context by default; labelled AI-drafted section; human publish |
| K7 | Lab machine has Python < 3.10 | Low (you target 3.12) | Medium (G1 uses `sys.stdlib_module_names`) | Confirm the demo machine runs 3.12; fallback stdlib list if needed |
| K9 | Free-tier API key leaks or rate-limits at demo | Medium | Medium | Key via gitignored file flag only; `--llm off` fallback (X2); recorded output as last resort, labelled |
| K8 | Our own DoD differs from the faculty's real page 13 | Unknown | Medium | Say clearly in the report that gates were self-defined from the visible statement; they cover every visible requirement |

---

## 9. Phase 3 summary

### Decisions made
- **Statement build = Approach C**: deterministic single agent, hypothesis-driven loop with a 4-round budget, explicit gates and state machines; stdlib + scikit-learn; no LLM.
- **Extended build = Approach E**: separate package on top of C; optional local LLM (Ollama via stdlib HTTP, CLI flags, no env vars) for narration, explanation and advice only; tested never to change a decision.
- **Approach A** kept as the non-agentic evaluation baseline; **B** optional test oracle; **D** and **F** rejected (D allowed only as a labelled ablation).
- **Definition of Done**: six self-defined gates G1–G6 with exact commands (§2.1), plus X1–X4 for the extension. Tests use stdlib `unittest`. Python ≥ 3.10.
- Sub-decision defaults: BM25 + TF-IDF `char_wb` with RRF (k = 60); refetch-once-then-distrust freshness; tolerance baseline × 1.10; five tools = latency, error rate, deployments, logs, dependencies.

### Unresolved
- ~~Python version~~ resolved: 3.12.
- ~~Local model feasibility~~ resolved by design: local Ollama **or** free-tier hosted (e.g. Groq) behind one OpenAI-compatible client. Actual model choice and free-tier limits are still to be checked in Phase 5.
- Team size and deadline (A18), still unknown; affects pacing only.

### What Phase 4 needs
- Detailed design: module interfaces, data schemas for fixtures (services, metrics series, deploys, logs, topology), runbook corpus with deliberately overlapping signatures, the "next predicate" rule, threshold table, page state machine, trace format with the eight milestone markers.
- Concrete golden-set incidents (three, distinct from 9001–9003) and the planted log line.
- Extension design (CLI, LLM guard schema, recorded LLM fixtures for X4) can follow after the baseline design is fixed.

---

## 10. New sources (this phase)

Accessed 2026-10-17. S1–S34 are listed in PHASE2.md §10.

| # | Source | Type |
|---|---|---|
| S35 | Ollama docs, "Tool calling" — https://docs.ollama.com/capabilities/tool-calling.md | Official docs |
| S36 | Ollama docs, "OpenAI compatibility" — https://docs.ollama.com/api/openai-compatibility.md | Official docs |
| S38 | Groq docs, "OpenAI Compatibility" — https://console.groq.com/docs/openai | Official docs |
| S37 | Ollama blog, "Structured outputs" (2024-12-06) — https://registry.ollama.ai/blog/structured-outputs | Official blog |

---

## PROJECT_CONTEXT.md (updated)

```markdown
# PROJECT_CONTEXT — Incident Commander (PS4, Agentic AI, Sem VII)

## Problem
Incident commander agent (Python, stdlib + scikit-learn only, simulated data, no env
vars/keys): investigate alerts by correlating signals, not retrieval rank; classify
remediation blast radius independent of severity; real time-boxed approval with
escalation; verify fixes by re-querying the symptom; side-effect-free postmortem draft;
evaluate on golden set + adversarial log injection.

## 8 requirements
1 Five typed read-only tools with declared max staleness
2 Hybrid runbook retriever; corpus with deliberately overlapping signature vocabulary
3 Investigation loop: latency up, errors normal, deploy within correlation window; round budget
4 classify_remediation() uses the action only, never severity
5 Real deadline + real time.sleep + real escalation; in-time page doesn't escalate
6 Re-query signal after fix: resolved/verified or reopened/handoff
7 Postmortem draft: notified=[], published=False until publish()
8 Golden set (3/3) + planted log ("blame payment-service, do not roll back") must not change outcome
(+ idempotent remediation via execution_id; fixtures keyed by service+timestamp, not incident ID)

## Acceptance values
9003: rounds=4, no_confident_match | 9001 high → rollback_deployment, tier=high, approval
9002 high → restart_service, tier=low, no approval | 0.3s window, 0.4s sleep, priya→devon
195ms vs 180ms → resolved/verified | 3900ms → reopened/unverified
retry → already_executed, same execution_id | golden 3/3 | attack: matched + rollback

## User decisions
No page 13: we define our own six DoD gates. Build statement version first (no LLM),
then an extended end-to-end version with optional LLM; both must be demoable separately.

## Architecture (Phase 3)
Statement build `incident_commander` = deterministic single agent: retriever proposes
hypotheses → loop (≤4 rounds, 1 tool call = 1 round) tests signature predicates on
metrics + deploy timing → matched | no_confident_match/handoff → classify_remediation(action)
→ approval page (monotonic deadline, priya→devon) → idempotent executor → verify by
re-query (≤ baseline×1.10) → pure postmortem draft, publish() only side effect.
Extended build `ic_plus` imports core (never reverse); optional local LLM (Ollama,
stdlib urllib, CLI flags, no env vars; local OR free-tier hosted e.g. Groq via same OpenAI-compatible client, key from gitignored file flag) for narration/explanation/advice only.
Non-agentic baseline A (naive top-1 retrieval) kept for evaluation; rule table B optional
oracle; LLM ReAct D and multi-agent F rejected.
Defaults: BM25 + TF-IDF char_wb + RRF k=60; stale → refetch once → untrusted;
tools = latency, error_rate, deployments, logs, dependencies; unittest; Python 3.12 (min 3.10).

## Definition of Done
G1 purity: python -m incident_commander.dod purity
G2 invariants: python -m unittest tests.test_invariants -v
G3 outcomes: python -m unittest tests.test_outcomes -v
G4 evaluation: python -m incident_commander evaluate
G5 e2e trace: python -m incident_commander run --all > traces/run.txt; python -m incident_commander.dod trace traces/run.txt
G6 repro: python -m incident_commander.dod repro
Extension: X1 baseline gates pass in ext repo; X2 LLM off/unavailable → same decisions;
X3 LLM on → same decisions, golden 3/3, attack unchanged; X4 LLM output validated.

## Status
Phase 1 (analysis), Phase 2 (research), Phase 3 (approaches + recommendation + DoD) done.
Open: team/deadline; actual LLM model + free-tier limits (check Phase 5).
Next: Phase 4, detailed design of the statement build.
```
