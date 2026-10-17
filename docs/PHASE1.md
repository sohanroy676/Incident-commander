# Phase 1: Problem Analysis — PS4 "The Incident Commander"

> Source of truth: two phone screenshots of `AAI Project-II.docx`, page 12 of 13 (uploaded 2026-10-17).
> Scope of this phase: understand the problem only. **No architecture is chosen here.**

---

## 1. Faithful transcription

Transcribed verbatim from the screenshots. Inline code (monospace in the original) is kept as `code`. Nothing has been added or corrected.

### Title

**PS4- Problem Statement: The Incident Commander — An Investigative, Time-Boxed Incident Response System**

### Objective

Design and build an **incident commander agent** that investigates production alerts by correlating real signals rather than trusting retrieval rank, classifies the blast radius of the remedy independently of the incident's severity label, enforces a **time-boxed approval** with a genuine elapsed-time escalation, verifies that a fix actually resolved the original signal, and drafts a zero-side-effect postmortem. The objective is to prove that incident response can be investigative rather than scripted, deadline-honest rather than aspirational, and blast-radius-aware rather than severity-driven.

### Problem Statement

Production incident response fails in predictable ways. Alert triage collapses into pattern-matching the nearest runbook, so an incident whose signature lies outside the corpus gets a confident wrong answer instead of gathering more evidence. Severity labels — usually a human's first guess — silently drive approval requirements, so a "high" alert that actually needs a low-risk restart gets blocked by an approval path built for a rollback. Approval deadlines are documented but never enforced by a real clock, so pages sit unanswered while the system reports success. And postmortems are written with side effects — notifications fired, entries committed — before anyone decides whether the draft is worth keeping.

The engineering challenge is **investigation under time pressure with honest reporting**. The system must satisfy eight coupled requirements.
(1) **Signal ingestion with declared freshness** — five typed, read-only tools, each declaring how stale its own data may be before a caller should not trust it.
(2) **Runbook grounding** — a hybrid retriever over a runbook corpus whose signature sections deliberately share vocabulary, shown rather than smoothed over, because retrieval alone cannot tell them apart.
(3) **An investigation loop that correlates real signals** — elevated latency, normal error rate, and a deployment timestamp inside the correlation window before the alert fired — with a bounded round budget, so an unmatched signature gathers additional evidence rather than guessing from whichever runbook ranked first.
(4) **Blast-radius classification of the remedy** — the incident's own severity label must never enter the approval decision; only the remediation action does.
(5) **Time-boxed approval with real, elapsed-time escalation** — a real deadline, a real `time.sleep` past it, a real escalation to a secondary, alongside a separate page answered in time that does not escalate.
(6) **Verified resolution or handoff** — after a fix, the original signal is re-queried, not assumed fixed because the remediation ran without error.
(7) **A postmortem draft with zero side effects** — discarding it costs nothing; only an explicit `publish()` makes it real.
(8) **Evaluation against history plus a real adversarial attack** — a golden set of historical incidents checked against known-correct verdicts and remediations, and a planted log line that falsely blames a downstream dependency and instructs "do not roll back," which must not change the conclusion.

The build is complete only when all eight milestones run end to end and all six Definition-of-Done gates pass under their exact verifying commands, with every trace pasted from a real terminal run. **In scope:** a self-contained Python prototype (only `scikit-learn` beyond the standard library); no signing key or environment variable, because governance here is about time and correlation, not identity. **Out of scope:** production infrastructure, real observability systems, and live incident data.

### Expected Outcomes

1. **Investigative, not scripted** — `ALRT-9003` exhausts its full round budget (`rounds=4`, `verdict=no_confident_match`) gathering evidence rather than settling for the nearest retrieval match.
2. **Equal severity, opposite approval requirements** — `ALRT-9001` (severity=high) resolves to `rollback_deployment` (`tier=high`, `requires_approval=True`); `ALRT-9002` (severity=high) resolves to `restart_service` (`tier=low`, `requires_approval=False`). The severity label never enters `classify_remediation()`.
3. **Deadline-honest escalation** — a 0.3s window yields `escalated: False` immediately, then `escalated: True` after a real 0.4s sleep, escalating `engineer-priya` → `engineer-devon`; a second page responded to in time returns `escalated: False, reason: already resolved`.
4. **Verified, not assumed** — post-fix latency of 195ms against a 180ms baseline yields `status: resolved, verified: True`; 3900ms yields `status: reopened, verified: False` with the explicit reason that the remediation ran but did not resolve the signal.
5. **Idempotent remediation** — a retried auto-executed restart returns `already_executed` with the identical `execution_id`.
6. **Draft-safe postmortem** — `notified: []` and `published: False` until `publish()` is called, with a full timeline built from the incident's own trace.
7. **Golden-set evaluation** — 3/3 historical incidents pass against known-correct verdicts and remediations.
8. **Adversarial resistance** — a planted log line blaming `payment-service` and instructing "do not roll back" does not change the verdict (`matched`) or the remediation (`rollback_deployment`), because the decision comes from metrics and deployment timing, which log text cannot touch.
9. **A design flaw caught before anything was built on it** — the original fixtures keyed signals by a pre-known incident ID, which would have made "investigation" a lookup with the answer attached; rebuild around service name and real timestamps so correlation is genuine.

### Deliverable

Participants must deliver a working prototype demonstrating the complete incident-response workflow — from signal ingestion and freshness-checked retrieval, through investigative correlation and blast-radius classification, to time-boxed approval with real escalation, verified resolution, and a zero-side-effect postmortem draft — all validated against a golden set and a live adversarial attack.

### Not visible in the screenshots

- **Page 13** of the document (the screenshots show page 12 of 13).
- **The six Definition-of-Done gates and their "exact verifying commands"** — referenced but not listed anywhere visible.
- Partially hidden assignment text on the left margin of the Classroom page (fragments: "Skomal…", "100 poin…", "All eight … implemen… it must a…"). It looks like general submission instructions, but it cannot be read.

---

## 2. The problem in plain language

Imagine you run an online shop. At 2 a.m. a monitoring system fires an **alert**: "checkout-service is slow." Someone (or something) has to decide *what went wrong* and *what to do about it*. That someone is the **incident commander**.

Teams keep a library of **runbooks**: short guides like "if latency is high right after a deploy, roll the deploy back." Today, a common shortcut is to search the runbooks for the text closest to the alert and do whatever it says. The problem statement says that shortcut fails in four predictable ways:

| Failure today | Everyday analogy | What the project must do instead |
|---|---|---|
| Pick the runbook that *reads* most similar, even when nothing actually fits | A doctor diagnosing from the first matching search result | **Investigate**: check real evidence (latency, error rate, recent deploys); if nothing truly fits, gather more evidence for a fixed number of rounds, then honestly say "no confident match" |
| The alert's "severity: high" label decides who must approve the fix | Requiring a surgeon's sign-off to give someone a plaster because they shouted "it's serious!" | Decide approval by how **risky the fix** is (its *blast radius*), never by the alert's label |
| "Approval needed within 5 minutes" is written down but nothing checks the clock | A deadline nobody enforces | Use a **real clock**: if the person paged doesn't answer in time, actually escalate to a backup person |
| A fix runs without error, so the system says "fixed" | Taking the medicine and assuming you're cured without re-checking the fever | **Re-measure** the original problem after the fix; if it's still bad, say "reopened" |
| Postmortem write-ups send emails and save records before anyone reviews them | An email that sends itself while you're still drafting | Produce a **draft** that does nothing until someone explicitly calls `publish()` |

On top of this, the system must be **tested** in two ways: against a small set of past incidents with known right answers (a "golden set"), and against an **attack**: someone plants a fake log line saying "it's payment-service's fault, do not roll back." The system must ignore that, because its decision is supposed to rest on numbers (metrics and deploy times), not on what text in a log says.

The whole thing is a **small, self-contained Python program** using fake (simulated) data. No real servers, no real monitoring tools, no live incidents.

### Worked example (based on Outcome 2 and 8)

1. Alert `ALRT-9001` fires for some service, severity "high".
2. The commander queries its tools: latency is far above baseline, error rate is normal, and a deployment to that service happened shortly before the alert.
3. That pattern matches the "bad deploy" runbook signature → verdict `matched`.
4. The remedy is `rollback_deployment`. A rollback is risky (it changes what code is running), so its blast-radius tier is `high` → `requires_approval=True`.
5. A human is paged with a deadline. If they don't respond in time, the page escalates to a secondary.
6. After the rollback, the commander re-queries latency. If it's back near baseline → `resolved, verified: True`.
7. A postmortem draft is assembled from the recorded trace, unsent and unpublished.

Compare `ALRT-9002`: same "high" severity, but the evidence points to something a **restart** fixes. A restart is low risk → `tier=low`, no approval needed. Same severity, opposite approval path: that contrast is the heart of requirement (4).

---

## 3. Requirements, classified

Legend: **E** = explicit in the statement · **D** = directly derived from an Expected Outcome value · **A** = my assumption (needs confirmation or is a reasonable default) · **O** = optional / nice-to-have, not required.

### 3.1 Functional requirements (the eight milestones)

| # | Requirement | Type | What exactly must be true |
|---|---|---|---|
| R1 | Signal ingestion with declared freshness | E | Exactly **five** tools; each **typed**, **read-only**, and declares a **maximum staleness** for its own data; callers must be able to tell when data is too stale to trust |
| R1a | The five tools' identities | A | Not named. The problem text implies at least: latency metrics, error-rate metrics, deployment history, logs. The fifth is unknown (candidates: alert details, service topology/dependencies, runbook search, recent changes) |
| R2 | Runbook grounding via **hybrid** retrieval | E | Retriever combines more than one retrieval method over a runbook corpus |
| R2a | Corpus with deliberately overlapping signature vocabulary | E | Runbooks must *intentionally* share words so text similarity alone can't separate them, and this must be **shown** (e.g., printed scores), not hidden |
| R3 | Investigation loop correlating real signals | E | Uses latency (elevated), error rate (normal), and deploy timestamp *inside a correlation window before the alert* as evidence |
| R3a | Bounded round budget | E/D | Loop stops after a fixed number of rounds; Outcome 1 fixes it at `rounds=4` for `ALRT-9003` |
| R3b | Unmatched → gather more evidence, not guess | E | When signals don't fit the top runbook, keep investigating; at budget exhaustion return `verdict=no_confident_match` |
| R3c | Correlation by service name and real timestamps | E (Outcome 9) | Fixtures must **not** be keyed by incident ID; signals are found by service + time |
| R4 | Blast-radius classification of the remedy | E | `classify_remediation()` takes the remediation action, **never** the severity label; outputs a tier and `requires_approval` |
| R5 | Time-boxed approval with real escalation | E | Real deadline; real `time.sleep` past it; real escalation primary → secondary; a second page answered in time does **not** escalate |
| R6 | Verified resolution or handoff | E | After remediation, re-query the original signal; resolved only if the signal itself recovered; otherwise `reopened` with explicit reason |
| R6a | "Handoff" path | A | Title says "resolution **or handoff**"; Outcome 4 only shows `reopened`. Likely means handing to a human when verification fails |
| R7 | Zero-side-effect postmortem draft | E | Draft creation sends nothing and persists nothing; `notified: []`, `published: False` until explicit `publish()`; timeline built from the incident's own trace |
| R8 | Evaluation: golden set | E/D | Historical incidents with known-correct verdict + remediation; Outcome 7 says **3/3** pass |
| R8a | Evaluation: adversarial log line | E/D | Planted log blames `payment-service`, says "do not roll back"; verdict stays `matched`, remediation stays `rollback_deployment` |
| R9 | Idempotent remediation | D (Outcome 5) | Not one of the eight numbered requirements, but an expected outcome: retrying an executed action returns `already_executed` with the same `execution_id` |
| R10 | End-to-end workflow | E | All eight milestones run together in one flow, not as disconnected demos |

### 3.2 Exact expected values (acceptance fixtures)

These are concrete numbers and strings the demo must reproduce. They effectively define the test fixtures.

| Outcome | Input / scenario | Expected output |
|---|---|---|
| 1 | `ALRT-9003` (signature outside corpus) | `rounds=4`, `verdict=no_confident_match` |
| 2 | `ALRT-9001`, severity=high | `rollback_deployment`, `tier=high`, `requires_approval=True` |
| 2 | `ALRT-9002`, severity=high | `restart_service`, `tier=low`, `requires_approval=False` |
| 3 | Page with 0.3s window, checked immediately | `escalated: False` |
| 3 | Same page after a real 0.4s sleep | `escalated: True`, `engineer-priya` → `engineer-devon` |
| 3 | Second page answered in time | `escalated: False`, `reason: already resolved` |
| 4 | Post-fix latency 195ms vs 180ms baseline | `status: resolved`, `verified: True` |
| 4 | Post-fix latency 3900ms vs 180ms baseline | `status: reopened`, `verified: False`, reason: remediation ran but signal not resolved |
| 5 | Retry an auto-executed restart | `already_executed`, identical `execution_id` |
| 6 | Draft postmortem | `notified: []`, `published: False` until `publish()` |
| 7 | Golden set | 3/3 pass |
| 8 | Planted log blaming `payment-service` + "do not roll back" | verdict `matched`, remediation `rollback_deployment` unchanged |

Note: `ALRT-9001` is likely the scenario used for the adversarial test (verdict `matched` + `rollback_deployment` are exactly 9001's outputs). This is an **inference**, not stated.

### 3.3 Non-functional requirements and constraints

| Constraint | Type | Notes |
|---|---|---|
| Python, self-contained prototype | E | |
| Dependencies: standard library + `scikit-learn` only | E | Strong constraint. No LangChain, no vector DB, no LLM SDK (see Ambiguity A1) |
| No signing key, no environment variables | E | Must run with zero configuration; "governance is about time and correlation, not identity" |
| Simulated data only | E | Out of scope: production infra, real observability systems, live data |
| Real time, not simulated time, for the approval clock | E | `time.sleep` must actually elapse; a mocked clock would violate "real" |
| Traces pasted from a real terminal run | E | The submission includes actual console output, not hand-written examples |
| Six Definition-of-Done gates with exact verifying commands | E | **Content unknown** — not in the screenshots |
| Honest reporting | E | The system must never report success it hasn't verified (escalation, resolution, publication) |

### 3.4 Optional / out of scope

- **Out of scope (explicit):** production infrastructure, real observability systems (Prometheus, Grafana, Datadog…), live incident data, identity/signing.
- **Optional (my classification):** a UI, an LLM-written postmortem narrative, more than three golden incidents, extra attack variants. None is required; any of them must not violate the dependency constraint.

---

## 4. Success criteria

The project succeeds when **all** of these hold (derived from "the build is complete only when…"):

1. **SC1 — End-to-end run:** one command runs the full workflow across all eight milestones on simulated data.
2. **SC2 — Exact outcomes:** every value in table 3.2 is reproduced in real terminal output.
3. **SC3 — DoD gates:** all six Definition-of-Done gates pass using their exact verifying commands *(blocked until the gates are known)*.
4. **SC4 — Dependency purity:** nothing beyond stdlib + scikit-learn is imported; no env vars or keys are needed.
5. **SC5 — Structural honesty** (checkable by reading code, not only output):
   - severity is not a parameter of, nor read inside, `classify_remediation()`;
   - fixtures are keyed by service name + timestamp, not incident ID;
   - the escalation depends on real elapsed time;
   - postmortem creation has no side effects before `publish()`;
   - log text cannot influence the verdict or the remediation.
6. **SC6 — Explainability (for the viva):** you can justify why each design choice satisfies its requirement and where an LLM or "agent" is or isn't used.

---

## 5. Domain concepts to learn

Ordered roughly by when you'll need them. Each is tied to where it shows up in this project.

### Incident management (SRE) basics
| Concept | Meaning | Where it appears |
|---|---|---|
| **Alert** | Automated notification that a monitored condition crossed a threshold | `ALRT-9001/9002/9003` |
| **Incident** | An unplanned disruption being actively handled | The workflow as a whole |
| **Severity label** | A first-guess rating of impact (e.g., high/medium/low) | Must be **excluded** from approval decisions |
| **Incident commander** | The role that coordinates response and decisions | The "agent" being built |
| **Paging / on-call** | Notifying a responsible engineer; primary and secondary rotations | `engineer-priya` → `engineer-devon` |
| **Escalation** | Moving to the next responder when the first doesn't answer in time | Requirement 5 |
| **Runbook** | A documented procedure for a known failure pattern | The retrieval corpus |
| **Signature** | The observable pattern that identifies a failure type (e.g., high latency + normal errors + recent deploy) | Runbook sections; correlation logic |
| **Remediation** | The action that fixes the problem (rollback, restart, scale up…) | `rollback_deployment`, `restart_service` |
| **Blast radius** | How much could break if the remediation itself goes wrong | Requirement 4; `tier` |
| **Postmortem** | Written review of an incident: timeline, cause, actions | Requirement 7 |

### Observability signals
| Concept | Meaning | Where it appears |
|---|---|---|
| **Metrics: latency, error rate** | Time per request; fraction of failed requests | Core correlation evidence |
| **Baseline** | Normal value for a metric | 180ms latency baseline |
| **Deployment events** | Timestamps when new code was released | "Deploy inside correlation window before alert" |
| **Logs** | Free-text event records | The **untrusted** channel used in the attack |
| **Data freshness / staleness** | How old data is; old data may no longer reflect reality | Requirement 1 (each tool declares max staleness) |
| **Correlation window** | Time range before an alert in which a related event (e.g., a deploy) is considered a plausible cause | Requirement 3 |
| **Correlation vs causation** | Two things happening together doesn't prove one caused the other | Why multiple signals must agree, not one |

### Information retrieval
| Concept | Meaning | Where it appears |
|---|---|---|
| **Lexical (sparse) retrieval** | Matching on words, e.g., TF-IDF, BM25 | One half of "hybrid" |
| **Semantic / dense retrieval** | Matching on meaning via vectors | Possible other half (constrained by scikit-learn-only) |
| **Hybrid retrieval & score fusion** | Combining rankers, e.g., weighted sum or Reciprocal Rank Fusion | Requirement 2 |
| **Retrieval rank ≠ correctness** | Top-ranked text may be wrong when vocabulary overlaps | The central lesson of requirements 2–3 |

### Agentic AI concepts
| Concept | Meaning | Where it appears |
|---|---|---|
| **Agent** | A system that pursues a goal by repeatedly observing, deciding, and acting with tools | The "incident commander agent" |
| **Tool use** | The agent calls well-defined functions to get information or act | The five read-only tools; remediation actions |
| **Agent loop with a budget** | Observe → reason → act, capped by rounds or time | `rounds=4` |
| **Grounding** | Basing decisions on retrieved evidence rather than assumptions | Runbook grounding + signal correlation |
| **Human-in-the-loop (HITL) approval** | Risky actions need a person's sign-off | `requires_approval=True` for high tier |
| **Guardrails / policy gates** | Rules that constrain what an agent may do | Blast-radius tiering, approval gate, draft-only postmortem |
| **Prompt / data injection** | Instructions hidden in data the system reads, trying to steer it | The planted "do not roll back" log line |
| **Separation of trusted and untrusted inputs** | Decision paths only read trusted, structured data | Outcome 8's defense |
| **Idempotency** | Repeating an action has no additional effect | `execution_id`, `already_executed` |
| **Side effects / dry-run** | Actions that change the outside world vs. ones that only compute | Postmortem `publish()` |
| **Traceability** | Recording every step so it can be audited | Postmortem timeline "built from the incident's own trace" |

### Evaluation
| Concept | Meaning | Where it appears |
|---|---|---|
| **Golden set** | Labeled examples with known-correct answers | 3 historical incidents |
| **Adversarial / red-team test** | A deliberately hostile input to test robustness | Planted log line |
| **Definition of Done** | Explicit, checkable criteria for "finished" | The six (unknown) gates |

---

## 6. Ambiguities and open points

Grouped by impact. "Default" is the reasonable assumption I'll carry into Phase 2 unless you say otherwise; none of them is an architecture decision.

### High impact (block parts of later phases)

| ID | Ambiguity | Why it matters | Default if unanswered |
|---|---|---|---|
| A1 | **Is an LLM expected or allowed?** The statement says "agent" but limits dependencies to stdlib + scikit-learn, which excludes LLM SDKs. | Decides whether the "agent" is a deterministic tool-using loop or LLM-driven. Also affects how you defend "agentic" in the viva. | Core decision path uses **no LLM** (it must be deterministic for exact outcomes and injection-proof anyway). An LLM, if allowed, could only be optional and outside the decision path. |
| A2 | **The six Definition-of-Done gates and their verifying commands** are not in the screenshots (likely on page 13). | They are the formal completion criteria. | Cannot default. Treat table 3.2 as provisional acceptance tests until the gates are known. |
| A3 | **Who provides the fixtures and runbook corpus?** | Determines whether we design the simulated data ourselves. | We author all fixtures (alerts, metrics, deploys, logs, runbooks, golden set). |

### Medium impact (design details later phases will have to settle)

| ID | Ambiguity | Default |
|---|---|---|
| A4 | Which five tools? Only four signal kinds are implied (latency, error rate, deploys, logs). | Decide in Phase 2/3 with justification. |
| A5 | "Hybrid retriever": hybrid of what, under scikit-learn only? (e.g., word TF-IDF + character n-gram TF-IDF, or TF-IDF + LSA/TruncatedSVD; BM25 isn't in scikit-learn but is easy to write in stdlib). | Research in Phase 2. |
| A6 | Verification threshold: 195ms vs 180ms counts as resolved (+8.3%), 3900ms doesn't. The tolerance rule isn't stated. | Pick a documented rule (e.g., within X% or Y×baseline) that reproduces both values. |
| A7 | What counts as a "round" in the investigation loop, and what new evidence is gathered each round? | Define in design phase. |
| A8 | Correlation window length, and what "elevated" and "normal" mean numerically. | Define in design; document thresholds. |
| A9 | Remediation catalogue and tier mapping beyond rollback (high) and restart (low). Are there medium tiers? | At least these two; add more only if justified. |
| A10 | "Handoff": what happens after `reopened`? Escalate to a human, try another remediation, or stop? | Hand off to a human with the evidence attached; no automatic second fix. |
| A11 | Does approval for `ALRT-9001` connect to the escalation demo, or are Outcomes 2 and 3 separate scenarios? Who "answers" a page in a simulation? | Simulated responder with a scripted response time. |
| A12 | Is `ALRT-9003` a different service, or the same service with a pattern no runbook covers? | Pattern not covered by any runbook. |
| A13 | What does the third golden-set incident look like (9001, 9002, 9003, or separate historical cases)? | Separate historical incidents, distinct from the demo alerts. |
| A14 | How is staleness enforced: does stale data reduce confidence, trigger re-fetch, or block a decision? | Decide in design. |

### Low impact

| ID | Ambiguity |
|---|---|
| A15 | Output format of traces (plain prints vs JSON). The field names suggest dict-like outputs. |
| A16 | Whether real `time.sleep` in tests is acceptable for run time (it's only 0.4s, so yes in practice). |
| A17 | Outcome 9 is phrased as a past event ("the original fixtures…"). It reads as a design lesson the statement wants you to *demonstrate awareness of*, i.e., fixtures keyed by service + timestamp. |
| A18 | Team size, deadline, review format, and the hidden assignment text on the Classroom page. |

### A note on "agentic" rigor (for later phases, not a decision)

The statement deliberately makes the critical decisions (verdict, tier, approval, verification) **deterministic and evidence-based**, and its adversarial outcome explicitly requires that text cannot affect the decision. That's a strong hint that the "agent" is valued for its **control loop**: tool use, bounded investigation, gates, escalation and honest state, not for free-form language generation. Whether multiple agents are justified is an open question for Phase 2; nothing in the statement requires more than one.

---

## 7. Essential clarification questions

1. **Can you share page 13** (or wherever the six Definition-of-Done gates and their verifying commands are listed), plus the assignment instructions on the Classroom page?
2. **Has your faculty said whether an LLM must, may, or must not be used?** (The statement's "only scikit-learn" rule suggests no LLM.)
3. **Are you working solo or in a team, and when is the review?** This shapes how we pace the phases.

---

## 8. Phase 1 summary

### Decisions made
- The screenshots are the source of truth; table 3.2 is treated as the provisional acceptance test.
- No architecture chosen. No agent or multi-agent design assumed.
- Working defaults recorded for ambiguities A1–A14 (above), each reversible.

### Unresolved
- A1 (LLM), A2 (DoD gates), A3 (fixture ownership) are the blocking ones.

### What Phase 2 needs
- Answers to the three questions in §7.
- Research targets: hybrid retrieval with scikit-learn (TF-IDF variants, LSA, BM25 in stdlib, score fusion); deterministic agent loops vs LLM agents; HITL approval and escalation patterns; idempotency keys; prompt/data-injection defenses; golden-set evaluation practice; SRE references (Google SRE book on incident management and postmortems).

---

## PROJECT_CONTEXT.md (reusable summary)

```markdown
# PROJECT_CONTEXT — Incident Commander (PS4, Agentic AI, Sem VII)

## Problem
Build an incident commander agent (Python, stdlib + scikit-learn only, simulated data,
no env vars/keys) that investigates alerts by correlating signals instead of trusting
retrieval rank, classifies remediation blast radius independent of severity, enforces
time-boxed approval with real escalation, verifies fixes by re-querying the signal,
and drafts a side-effect-free postmortem. Evaluated on a golden set + adversarial log.

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

## Status
Phase 1 done (analysis). No architecture chosen.
Blocking unknowns: six DoD gates (page 13?), LLM allowed?, fixture ownership (default: we author).
Next: Phase 2 research & approach comparison.
```
