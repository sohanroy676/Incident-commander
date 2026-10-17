# Phase 2: Domain Knowledge and Research — PS4 "The Incident Commander"

> Builds on [PHASE1.md](PHASE1.md). **No architecture is chosen here.** Where a finding points toward a design option, it is flagged as *input for Phase 3*, not a decision.
>
> Phase 1 questions still open, so these defaults apply: **no LLM in the decision path** (A1), **DoD gates unknown** (A2), **we author all fixtures** (A3).

### How to read this document

Each topic is tagged:

- 🟥 **Essential**: you cannot build or defend the project without it.
- 🟧 **Recommended**: makes your design noticeably better and helps in the viva.
- 🟩 **Optional**: background or stretch reading.

Every factual claim from outside sources has a citation in [§10 Sources](#10-sources), as `[S#]`. Statements marked *(inference)* are my reasoning, not something a source says.

---

## 0. Learning path at a glance

| Level | Topic | Tag | Maps to requirement | Section |
|---|---|---|---|---|
| 1 | How incident response works (roles, paging, escalation, postmortems) | 🟥 | R5, R6, R7 | §1 |
| 1 | Observability signals: latency, errors, baselines, deployments | 🟥 | R1, R3, R6 | §2 |
| 2 | Correlation vs causation; "what touched it last" | 🟥 | R3, R8 | §2.4 |
| 2 | Text retrieval: TF-IDF, BM25, LSA, character n-grams | 🟥 | R2 | §3 |
| 2 | Hybrid retrieval and rank fusion (RRF) | 🟥 | R2 | §3.4 |
| 3 | What makes software an "agent"; workflows vs agents | 🟥 | Viva defence | §4 |
| 3 | Reliability patterns: monotonic clocks, timeouts, idempotency, drafts | 🟥 | R5, R7, Outcome 5 | §5 |
| 3 | Prompt/data injection and trust boundaries | 🟥 | R8 | §6 |
| 4 | Evaluation: golden sets and adversarial tests | 🟥 | R8 | §7 |
| 4 | Research landscape: AIOps, LLM root-cause analysis, benchmarks | 🟧 | Viva, related work | §8 |
| 4 | Industry tools (Alertmanager, PagerDuty, StackStorm) | 🟩 | Context | §8.4 |

Suggested order: §1 → §2 → §3 → §5 → §6 → §4 → §7 → §8. Agent theory (§4) lands better once you've seen the concrete pieces it has to coordinate.

---

## 1. Incident response fundamentals 🟥

### 1.1 What an incident is and when to declare one

Google's SRE book says to **declare an incident early**. Something counts as an incident if a second team must be involved, the outage is visible to customers, or the problem is still unsolved after an hour of concentrated analysis [S1].

**In our project:** the alert (`ALRT-900x`) is the trigger. Our system takes over at "an alert fired; now what?"

### 1.2 Roles: the incident commander is a coordinator, not a fixer

Google's incident management is based on the **Incident Command System (ICS)**, created by firefighters in 1968 and later adapted for software outages [S2]. It defines distinct roles [S1][S2]:

| Role | Job |
|---|---|
| **Incident Commander (IC)** | Holds the overall state of the incident, assigns work, removes roadblocks |
| **Operations Lead** | The only one who changes the system during the incident [S1] |
| **Communications Lead** | Keeps stakeholders updated |
| **Planning** | Tracks changes so they can be reverted; arranges handoffs [S1] |

PagerDuty's public response guide goes further: the IC is *"the single source of truth"* and is **explicitly "NOT a resolver"**. The IC collects proposed repair actions, recommends one, and delegates its execution [S3].

**Why this matters for you:** the problem statement calls the system an "incident commander agent". The real-world IC **investigates, decides and coordinates**; it doesn't silently execute risky fixes on its own. That is exactly the shape of requirements R3–R7: investigate, classify, seek approval, verify, document. *(inference)*

### 1.3 "Stop the bleeding" first; root cause second

Google's guidance: *"Google always aims to first stop the impact of an incident,"* using generic mitigations like **rollbacks**, then finds the root cause [S2]. The troubleshooting chapter agrees: *"Stopping the bleeding should be your first priority"* [S4].

**In our project:** `rollback_deployment` and `restart_service` are mitigations. The system doesn't need to prove the deep root cause; it needs enough evidence to pick the right mitigation safely.

### 1.4 Paging, on-call and escalation

- On-call engineers are expected to be able to act within minutes of a page. Typical targets are **5 minutes for user-facing services** and 30 minutes for less critical ones [S5].
- Many teams run **primary and secondary** rotations. In one common model, the secondary catches pages the primary misses [S5].
- In PagerDuty, if a paged responder doesn't accept before the **escalation timeout**, the page escalates to the next level of the escalation policy [S6].

**In our project:** `engineer-priya` (primary) → `engineer-devon` (secondary) after a deadline. The statement scales "5 minutes" down to **0.3 s** so the demo runs quickly, but insists the clock is **real** (R5).

### 1.5 Postmortems

A postmortem is a written record of an incident: its impact, the actions taken, the root causes, and follow-up actions [S7]. Key ideas:

- **Blameless:** focus on systems and processes, *"without indicting any individual or team"* [S7].
- **Triggers** include on-call intervention such as a **release rollback** [S7]. So `ALRT-9001` (rollback) is a textbook postmortem trigger.
- **Drafts are reviewed before broad sharing.** Senior engineers review the first draft; only then is it shared widely [S7]. *"An unreviewed postmortem might as well never have existed"* [S7].

**In our project:** R7's "zero side effects until `publish()`" is a software enforcement of Google's *draft → review → publish* workflow. That's a strong viva point. *(inference)*

### 1.6 Self-check

1. Why should the IC not be the one who executes a fix?
2. Why might a team roll back before it knows the root cause?
3. In our project, which real-world role does the postmortem `publish()` step correspond to?

---

## 2. Observability signals and correlation 🟥

### 2.1 The four golden signals

Google's monitoring chapter names four signals to watch for any user-facing system [S8]:

| Signal | Definition [S8] | Used in our project? |
|---|---|---|
| **Latency** | *"The time it takes to service a request"* | ✅ Core (elevated latency; 180 ms baseline) |
| **Traffic** | Demand placed on the system | Not mentioned |
| **Errors** | *"The rate of requests that fail"* | ✅ Core (normal error rate) |
| **Saturation** | How "full" the service is | Not mentioned |

**Why "elevated latency + normal error rate" is a meaningful signature:** the service still *works* (requests succeed) but is *slow*. That pattern is typical of a performance regression, for example from a bad deploy, rather than a crash. *(inference; this is a common SRE heuristic, and the statement uses it as the example signature)*

### 2.2 Baselines, averages and percentiles 🟧

- Google warns against designing around the **mean**, because averages hide the slow tail; collect latency as distributions or percentiles [S8].
- The 99th percentile over a short window can be a *"very early signal of saturation"* [S8].

**In our project:** the statement only gives single numbers (180 ms baseline; 195 ms and 3900 ms after the fix). Whether those numbers are means or p99 is undefined; that's input for Phase 3 (ambiguity A6/A8). Simplest honest choice: treat them as a single summary value per time window, and say so.

### 2.3 Symptoms vs causes

Monitoring should answer *"what's broken"* (the symptom) and *"why"* (the cause); Google calls this one of the most important distinctions in monitoring [S8]. Paging should focus on **symptoms** [S8].

**In our project:** the alert is the **symptom** (latency is high). The investigation loop looks for the **cause** (a deploy inside the correlation window). Verification (R6) re-checks the **symptom**, not the cause; that's exactly why "the remediation ran without error" isn't proof of resolution.

### 2.4 "What touched it last" and correlation vs causation

- Google's troubleshooting chapter: *"Recent changes to a system can be a productive place to start identifying what's going wrong"* [S4]. Systems should log deployments so responders can correlate them with performance changes [S4].
- The SRE book reports that *"roughly 70% of outages are due to changes in a live system"* [S9].
- But: *"correlation is not causation"*, and coincidental correlations are a common troubleshooting pitfall [S4].

**This is the theoretical core of R3:**

```
Alert fired at T
Correlation window = [T − W, T]

Evidence for "bad deploy":
  ✔ latency elevated vs baseline        (symptom present)
  ✔ error rate normal                   (rules out a crash-type failure)
  ✔ deploy timestamp ∈ [T − W, T]       (a plausible cause happened just before)
→ all three agree → confident match → rollback_deployment
```

Any single signal could be coincidence. **Requiring several independent signals to agree** is the practical defence against spurious correlation. *(inference)*

### 2.5 Data freshness (staleness) 🟥

The statement requires each tool to *declare how stale its data may be before a caller should not trust it* (R1). I found no single authoritative source that defines this exact contract, so this section is my explanation. *(inference)*

- Every observation has an **as-of timestamp**. Its **age** = now − as-of.
- Each tool declares a **max staleness** (a budget, e.g. "metrics older than 60 s are untrusted").
- The caller compares age with the budget, and must decide what to do with stale data: refetch, lower confidence, or refuse to decide. Which one is an open Phase 3 question (A14).

**Why it matters:** acting on old data is a classic way to "fix" a problem that has already changed, or to verify a fix using numbers from before the fix ran.

### 2.6 Self-check

1. After a rollback, why re-query latency rather than check that the rollback command succeeded?
2. A deploy happened 3 hours before the alert. Should it count as evidence? What decides that?
3. Why does "normal error rate" make the "bad deploy → rollback" verdict *more* confident, not less?

---

## 3. Information retrieval for runbook grounding 🟥

R2 asks for a **hybrid retriever** over runbooks whose signature sections **deliberately share vocabulary**, so that retrieval *alone* can't tell them apart. The point is to show that retrieval rank is a weak signal. You need to understand retrieval well enough to (a) build it and (b) explain why it fails here.

### 3.1 Bag-of-words and TF-IDF 🟥

- Represent each document as word counts; weight each word by **TF** (how often it occurs in this doc) × **IDF** (how rare it is across all docs). Rare, distinctive words score high; common words score low.
- Compare query and document vectors with **cosine similarity**.
- scikit-learn provides `TfidfVectorizer` with options including word or character n-grams (`analyzer='word' | 'char' | 'char_wb'`), `ngram_range`, and `sublinear_tf` (replace tf with 1 + log(tf)) [S10].

**Worked example.** Two runbooks:

- RB-A "Bad deploy": *"latency spike after deployment; error rate normal; roll back the deployment"*
- RB-B "Memory leak": *"latency spike growing over hours; error rate normal; restart the service"*

Alert text: *"checkout latency spike, error rate normal"*. Both runbooks share "latency spike" and "error rate normal", so TF-IDF scores them **almost equally**. Text can't say which is right; only the **deployment timestamp** can. That's precisely the trap the statement wants you to *show*.

### 3.2 BM25 🟥

BM25 is the classic probabilistic ranking function from the Probabilistic Relevance Framework [S11]. Compared with plain TF-IDF it adds two practical ideas:

- **Term-frequency saturation** (parameter `k1`): the 10th occurrence of a word adds much less than the 1st.
- **Length normalisation** (parameter `b`): long documents don't win just by being long.

Scikit-learn has no built-in BM25 estimator as far as I know, but the formula is short enough to write with the standard library over `CountVectorizer` output. *(inference; to be confirmed when implementing)*

### 3.3 LSA: "semantic" retrieval within scikit-learn 🟧

Modern "dense" retrieval uses neural embeddings, but those need libraries (PyTorch, sentence-transformers) that the statement **forbids**. Within scikit-learn, the classic alternative is **Latent Semantic Analysis**: `TruncatedSVD` applied to a TF-IDF matrix. The scikit-learn docs say this is known as LSA, and recommend about 100 components for LSA [S12].

*(inference)* With a tiny runbook corpus (maybe 5–15 documents), 100 components is impossible: SVD can't produce more components than there are documents. The number of components becomes a design choice to justify in Phase 3.

### 3.4 Hybrid retrieval and Reciprocal Rank Fusion 🟥

"Hybrid" means combining two or more rankers so each covers the others' blind spots. Options:

| Fusion method | How it works | Pros / cons |
|---|---|---|
| **Weighted score sum** | `α·score₁ + (1−α)·score₂` | Simple, but scores are on different scales and need normalising |
| **Reciprocal Rank Fusion (RRF)** | `RRF(d) = Σ_r 1/(k + rank_r(d))`, with `k = 60` [S13] | Uses only ranks, so no score calibration. Reported to beat each individual system and Condorcet fusion [S13] |

Candidate pairings that respect the stdlib + scikit-learn rule (for Phase 3 comparison, **not chosen**):

1. BM25 (stdlib) + TF-IDF on character n-grams (`char_wb`)
2. TF-IDF on words + LSA (`TruncatedSVD`)
3. BM25 + LSA

### 3.5 Why "retrieval rank ≠ correctness" 🟥

The key conceptual point of R2/R3, and a likely viva question:

- Retrieval measures **textual similarity**, not **diagnostic fit**.
- When runbooks share vocabulary, the top-1 result is close to a coin flip, and its score **looks confident** anyway.
- So the retriever should **propose candidates**; the decision should come from **checking each candidate's signature against real signals**.
- When no candidate's signature is confirmed (`ALRT-9003`), the honest answer is `no_confident_match` after the round budget, not "the top-ranked runbook".

Useful idea to explore in Phase 3: report the **margin** between the top two retrieval scores; a small margin is an explicit "retrieval can't tell these apart" flag. *(inference)*

### 3.6 Self-check

1. Why can't TF-IDF distinguish RB-A from RB-B in the example above?
2. Why does RRF not need score normalisation?
3. Why is LSA a reasonable "semantic" component here, but not as powerful as neural embeddings?

---

## 4. What makes this "agentic"? 🟥

This is the topic your faculty is most likely to probe, so it gets careful treatment.

### 4.1 Classic definition

In the standard AI textbook (Russell & Norvig, *Artificial Intelligence: A Modern Approach*), an **agent** is anything that perceives its environment through sensors and acts on it through actuators [S14]. That definition **doesn't require an LLM**. A thermostat is a (very simple) agent; so is a rule-based investigation loop that calls tools and acts on the result.

### 4.2 Modern LLM-era vocabulary: workflows vs agents

Anthropic's widely cited engineering post *Building Effective Agents* (Dec 2024) distinguishes [S15]:

- **Workflows**: *"systems where LLMs and tools are orchestrated through predefined code paths."*
- **Agents**: *"systems where LLMs dynamically direct their own processes and tool usage."*

It recommends *"finding the simplest solution possible, and only increasing complexity when needed"*, which *"might mean not building agentic systems at all"* [S15]. It lists workflow patterns: prompt chaining, routing, parallelisation, orchestrator-workers, evaluator-optimiser [S15].

### 4.3 ReAct: the reason → act → observe loop

**ReAct** (Yao et al., ICLR 2023) has a language model interleave **reasoning** steps with **actions** that fetch outside information, so that reasoning guides actions and observations update reasoning [S16]. This loop of *think → call a tool → observe → think again* is the conceptual template for most tool-using agents.

### 4.4 Where our project sits (analysis, not a decision)

| Agentic property | Required by the statement? | Notes |
|---|---|---|
| Perceives environment via tools | ✅ R1: five read-only tools | |
| Iterative loop: observe → decide → act | ✅ R3: investigation rounds | |
| Bounded autonomy (budget) | ✅ `rounds=4` | |
| Chooses next evidence based on what it has seen | ✅ R3: "gathers additional evidence" | The *how* is a Phase 3 question |
| Acts on the world | ✅ remediation, paging | Gated by blast radius and approval |
| Human-in-the-loop for risky actions | ✅ R4, R5 | |
| Verifies outcomes of its own actions | ✅ R6 | Closed-loop control |
| Free-form LLM reasoning | ❌ Not required; deps rule excludes LLM SDKs | Ambiguity A1 |

*(inference)* The statement describes an agent in the **classic** sense: a goal-directed, tool-using, bounded, self-verifying control loop with human gates. In the Anthropic vocabulary, a deterministic version is closer to a **workflow with an agent-like loop** than to an LLM-driven agent. Being able to say this clearly, and argue *why* determinism is the right choice for the decision path (exact expected outputs, injection resistance, auditability), is a strong viva position. Phase 3 will compare this with LLM-in-the-loop alternatives.

### 4.5 Multi-agent: does anything justify it?

Nothing in the statement requires multiple agents. The ICS roles in §1.2 (commander, ops, comms) *could* be mapped to separate agents, but the statement has no communication or parallelism need that a single loop can't meet. Rule 4 of your brief says not to introduce agents without justification; Phase 3 will test this explicitly.

### 4.6 Self-check

1. Is a deterministic tool-calling loop an "agent"? Defend both yes and no.
2. Why would an LLM make Outcome 2's exact values harder to guarantee?
3. Which of the five Anthropic workflow patterns, if any, resembles "investigate in bounded rounds"?

---

## 5. Reliability engineering patterns 🟥

These are small, concrete techniques that each requirement relies on.

### 5.1 Real time-boxing: use a monotonic clock (R5)

PEP 418 explains that the system clock (`time.time()`) can be changed manually or adjusted by NTP, so timeouts measured with it can fire too early or too late; a **monotonic clock** (`time.monotonic()`) is unaffected and should be used for timeouts [S17].

```python
deadline = time.monotonic() + 0.3
check()                 # escalated: False (deadline not reached)
time.sleep(0.4)         # real elapsed time, as R5 demands
check()                 # escalated: True  (monotonic now > deadline)
```

*(inference)* This also answers a likely viva challenge: "How do you know your escalation is real and not faked?" Because the decision compares a real monotonic clock with a deadline; nothing is mocked.

### 5.2 Escalation semantics (R5)

From PagerDuty: an un-acknowledged page escalates to the next level after the escalation timeout [S6]. From Outcome 3: a page **answered in time** must **not** escalate, and reports `reason: already resolved`. So the page needs at least three states, roughly *pending → acknowledged* or *pending → escalated*. The exact state machine is a Phase 3 design task.

### 5.3 Idempotency (Outcome 5)

Stripe's API docs describe idempotency keys: the client sends a unique key; the server saves the result of the first request with that key; **retries with the same key return the saved result** instead of performing the operation again [S18]. Stripe suggests random UUIDs as keys [S18].

**In our project:** retrying `restart_service` must return `already_executed` with the **same `execution_id`**. Same idea: remember what was executed under which key, and return the stored result on retry. What the key should be (incident + action? a UUID?) is a Phase 3 choice.

### 5.4 Side-effect-free drafts (R7)

Two general software ideas *(inference; standard practice, not from a single source)*:

- **Command–query separation:** building a draft is a *query* (computes a value); `publish()` is the only *command* (changes the world).
- **Dry-run by construction:** don't build a "send" step and then disable it with a flag. Simply have no side effects in the draft path at all.

Google's draft-review-publish culture (§1.5) supplies the real-world rationale [S7].

### 5.5 Verification as closed-loop control (R6)

The remediation is an **open-loop** action ("I sent the rollback"). Verification closes the loop by measuring the **symptom** again (§2.3). The statement's examples imply a tolerance band: 195 ms vs 180 ms baseline (+8.3 %) counts as resolved; 3900 ms (≈21.7×) does not. The rule itself is unspecified (A6). *(inference)*

### 5.6 Self-check

1. Why would `time.time()` be a poor choice for the approval deadline?
2. Why should the idempotent retry return the *same* `execution_id` and not a new one?
3. What exactly would make a postmortem draft "have a side effect"?

---

## 6. Prompt and data injection: the adversarial requirement 🟥

### 6.1 The threat

- **Indirect prompt injection** (Greshake et al., 2023): when a system processes retrieved content, an attacker can **plant instructions inside that content** and steer the system remotely, without access to the prompt. LLM-integrated apps *blur the line between data and instructions* [S19].
- OWASP ranks **Prompt Injection** as LLM01 (the top risk) in its 2025 Top 10 for LLM Applications, distinguishing direct (user input) from indirect (external content such as files or web pages) injection [S20].

**Our attack (R8):** a log line says, in effect, *"payment-service is to blame; do not roll back."* It's an indirect injection carried in **log data**, an untrusted channel.

### 6.2 Defences from the literature

| Source | Defence idea | Relevance to us |
|---|---|---|
| OWASP LLM01 [S20] | Least privilege; **human approval for high-risk actions**; **segregate and label external content**; deterministic validation of outputs; adversarial testing | We already have approval gates (R4/R5) and adversarial testing (R8) |
| Beurer-Kellner et al., 2025 [S21] | Six design patterns (Action-Selector, Plan-Then-Execute, LLM Map-Reduce, Dual LLM, Code-Then-Execute, Context-Minimization). Core principle: once an agent has ingested untrusted input, *"it must be constrained so that it is impossible for that input to trigger any consequential actions"* | Our decision rule must not read log text at all |
| CaMeL (Debenedetti et al., 2025) [S22] | Separate **control flow** from **data flow** so *"untrusted data retrieved by the LLM can never impact the program flow"* | Same principle, at the architecture level |

### 6.3 What the statement already tells us

Outcome 8 says the verdict and remediation don't change *"because the decision comes from metrics and deployment timing, which log text cannot touch."* That's a **structural** defence: the decision function's inputs are numbers and timestamps, so there is no path for log text to influence it. It's stronger than a filter that tries to *detect* malicious text. *(inference, consistent with [S21][S22])*

Open design question for Phase 3: may logs be used at all (for example, displayed in the postmortem timeline as untrusted context), and how is that labelled?

### 6.4 Self-check

1. Why is "detect and strip malicious log lines" a weaker defence than "the decision never reads logs"?
2. If an LLM summarised the logs for the postmortem, how could the injection still cause harm, even if the verdict were safe?

---

## 7. Evaluation 🟥

### 7.1 Golden set

A **golden set** is a fixed collection of inputs with known-correct outputs. For us: historical incidents with known verdicts and remediations, which must pass 3/3 (R8, Outcome 7). Points to understand *(general practice; inference)*:

- The golden set checks **regressions**: if a change breaks a past correct answer, you notice.
- 3 cases prove **nothing statistically**. They're acceptance tests, not accuracy measurements. Say so in the viva; overclaiming is a red flag.
- Golden cases must be **different from** the demo alerts, or the evaluation just checks the demo against itself (Phase 1, A13).

### 7.2 Adversarial testing

OWASP recommends regular adversarial testing that treats the model as an untrusted user [S20]. Our version is one fixed attack (R8). A good evaluation states the **attack model** explicitly: what the attacker controls (log text), and what they don't (metrics, deploy timestamps).

### 7.3 What research benchmarks measure (context) 🟧

- RCACopilot reports Micro-F1 of 0.766 on 653 Microsoft incidents [S23].
- OpenRCA reports that the best setup solved only **11.34 %** of 335 failure cases [S25].

These numbers aren't comparable to our 3/3 golden set. They're useful to say *why* a deterministic, evidence-checked design is reasonable for a high-stakes decision.

---

## 8. Research landscape: existing approaches 🟧

### 8.1 AIOps

**AIOps** (AI for IT Operations) applies AI and big data to operating IT systems. A 2020 systematic mapping study found that **62 %** of AIOps contributions address failure-related tasks such as anomaly detection and root-cause analysis [S26]. A 2024 survey on AIOps for failure management in the LLM era organises the field into four stages [S27]:

| Stage [S27] | Example tasks [S27] | Our requirement |
|---|---|---|
| Data preprocessing | log parsing, metric imputation | R1 (typed tools) |
| Failure perception | anomaly detection, failure prediction | Given to us: the alert fires |
| Root cause analysis | failure localisation, category classification | R2, R3 |
| Auto remediation | mitigation generation, automatic execution | R4–R6 |

Our project covers stages 3–4 plus governance (approval, verification, postmortem), which the survey's stages don't emphasise. *(inference)*

### 8.2 LLM-based incident management (research)

| Work | What it does | Takeaway for us |
|---|---|---|
| **Ahmed et al., 2023** — *Recommending Root-Cause and Mitigation Steps for Cloud Incidents using LLMs* [S28] | Evaluated GPT-3.x models on **40,000+** Microsoft incidents to recommend root causes and mitigations; incident owners judged them promising | LLMs can *suggest*; the study is about recommendation, not autonomous action |
| **RCACopilot** (Chen et al., EuroSys 2024) [S23] | Two stages: (1) **handlers** mapped to alert types run predefined actions to collect logs, metrics and traces; (2) an LLM predicts a root-cause category, using retrieved similar past incidents as examples | Closest to our design problem. Stage 1 is a **deterministic, tool-based evidence collector**, much like R1 + R3 |
| **OpenRCA** (Xu et al., ICLR 2025) [S25] | Benchmark: 335 failures, 68+ GB telemetry; best model + agent solved 11.34 % | LLM agents are still weak at root-cause localisation from raw telemetry |

*(inference)* The pattern across this literature: **evidence collection is structured and tool-driven**, and LLMs are used for summarisation or suggestion. That supports, but doesn't by itself decide, keeping our decision path deterministic.

### 8.3 Datasets and benchmarks

| Resource | What it is | Usable for us? |
|---|---|---|
| **Loghub** [S29] | 19 real system log datasets (github.com/logpai/loghub) | 🟩 Only as inspiration for realistic log line formats. Statement puts real data out of scope |
| **RCAEval** [S30] | 735 failure cases from three microservice systems; 15 baselines | 🟩 Reading only; far beyond our scope |
| **AIOpsLab** (Microsoft, 2025, MIT licence) [S31][S32] | Deploys microservice environments, injects faults, generates workloads, exports telemetry, and provides an agent-cloud interface for evaluation | 🟩 Good related-work citation; running it would violate "out of scope: production infrastructure" |
| **OpenRCA** [S25] | RCA benchmark for LLMs | 🟩 Related work |

**Conclusion:** no public dataset fits our constraints (stdlib + scikit-learn, simulated, fixtures keyed by service and timestamp). We'll **author synthetic fixtures** (default A3). Phase 3 needs to design them so that correlation is genuine (Outcome 9).

### 8.4 Industry tools (context only) 🟩

| Tool | Relevant concept | Source |
|---|---|---|
| **Prometheus Alertmanager** | **Grouping** related alerts, **inhibition** (mute alerts caused by a bigger one), **silences** | [S33] |
| **PagerDuty** | Incident roles; escalation policies with timeouts | [S3][S6] |
| **StackStorm** | Open-source event-driven automation, used for auto-remediation | [S34] |

None can be used (dependency rule), but naming the concepts shows you know what real systems do.

---

## 9. Requirement → knowledge → source map

| Req | Concepts you must explain | Key sources |
|---|---|---|
| R1 Freshness | observation age, staleness budget, typed read-only tools | §2.5 (inference), [S8] |
| R2 Hybrid retrieval | TF-IDF, BM25, LSA, RRF, rank ≠ correctness | [S10][S11][S12][S13] |
| R3 Investigation | golden signals, symptom vs cause, what touched it last, correlation ≠ causation, bounded loop | [S4][S8][S9][S16] |
| R4 Blast radius | mitigation risk vs incident severity; approval for high-risk actions | [S2][S20] |
| R5 Time-boxed approval | on-call, primary/secondary, escalation timeout, monotonic clock | [S5][S6][S17] |
| R6 Verification | closed loop; re-measure the symptom | [S8] |
| R7 Draft postmortem | blameless, draft → review → publish, command–query separation | [S7] |
| R8 Evaluation | golden set, indirect prompt injection, structural defences | [S19][S20][S21][S22] |
| Outcome 5 | idempotency keys | [S18] |
| Viva "is it an agent?" | agent definition; workflows vs agents; ReAct | [S14][S15][S16] |

---

## 10. Sources

All accessed 2026-10-17 unless noted. Each was opened and checked during this phase except [S14] (a standard textbook, cited from general knowledge) and [S34] (seen in search results only).

| # | Source | Type |
|---|---|---|
| S1 | Google, *Site Reliability Engineering*, ch. 14 "Managing Incidents" — https://sre.google/sre-book/incident-response/ | Book (free online) |
| S2 | Google, *The Site Reliability Workbook*, ch. 9 "Incident Response" — https://sre.google/workbook/incident-response/ | Book (free online) |
| S3 | PagerDuty Incident Response Guide, "Different Roles" — https://response.pagerduty.com/before/different_roles/ | Industry docs |
| S4 | Google, *SRE*, ch. 12 "Effective Troubleshooting" — https://sre.google/sre-book/effective-troubleshooting/ | Book |
| S5 | Google, *SRE*, ch. 11 "Being On-Call" — https://sre.google/sre-book/being-on-call/ | Book |
| S6 | PagerDuty Knowledge Base, "Incident Roles" — https://support.pagerduty.com/docs/incident-roles | Vendor docs |
| S7 | Google, *SRE*, ch. 15 "Postmortem Culture: Learning from Failure" — https://sre.google/sre-book/postmortem-culture/ | Book |
| S8 | Google, *SRE*, ch. 6 "Monitoring Distributed Systems" — https://sre.google/sre-book/monitoring-distributed-systems/ | Book |
| S9 | Google, *SRE*, ch. 1 "Introduction" — https://sre.google/sre-book/introduction/ | Book |
| S10 | scikit-learn, `TfidfVectorizer` — https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html | Official docs |
| S11 | Robertson, S. & Zaragoza, H. (2009). *The Probabilistic Relevance Framework: BM25 and Beyond.* Foundations and Trends in IR 3(4) — https://nowpublishers.com/article/Details/INR-019 | Peer-reviewed survey |
| S12 | scikit-learn, `TruncatedSVD` — https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.TruncatedSVD | Official docs |
| S13 | Cormack, G., Clarke, C. & Büttcher, S. (2009). *Reciprocal Rank Fusion outperforms Condorcet and individual rank learning methods.* SIGIR '09 — https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf | Peer-reviewed paper |
| S14 | Russell, S. & Norvig, P. *Artificial Intelligence: A Modern Approach*, 4th ed., ch. 2 "Intelligent Agents" | Textbook (not re-checked online) |
| S15 | Anthropic (2024-12-19). *Building Effective Agents* — https://www.anthropic.com/research/building-effective-agents | Industry engineering article |
| S16 | Yao, S. et al. (2023). *ReAct: Synergizing Reasoning and Acting in Language Models.* ICLR 2023 — https://arxiv.org/abs/2210.03629 | Peer-reviewed paper |
| S17 | PEP 418, *Add monotonic time, performance counter, and process time functions* — https://peps.python.org/pep-0418/ | Official Python docs |
| S18 | Stripe API docs, "Idempotent requests" — https://docs.stripe.com/api/idempotent_requests | Vendor docs |
| S19 | Greshake, K. et al. (2023). *Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection* — https://arxiv.org/abs/2302.12173 | Paper (arXiv) |
| S20 | OWASP Gen AI Security Project, *LLM01:2025 Prompt Injection* — https://genai.owasp.org/llmrisk/llm01-prompt-injection/ | Industry standard |
| S21 | Beurer-Kellner, L. et al. (2025). *Design Patterns for Securing LLM Agents against Prompt Injections* — https://arxiv.org/abs/2506.08837 | Paper (arXiv) |
| S22 | Debenedetti, E. et al. (2025). *Defeating Prompt Injections by Design* (CaMeL) — https://arxiv.org/abs/2503.18813 | Paper (arXiv) |
| S23 | Chen, Y. et al. (2024). *Automatic Root Cause Analysis via Large Language Models for Cloud Incidents* (RCACopilot). EuroSys '24 — https://arxiv.org/abs/2305.15778 | Peer-reviewed paper |
| S25 | Xu, J. et al. (2025). *OpenRCA: Can Large Language Models Locate the Root Cause of Software Failures?* ICLR 2025 — https://mlanthology.org/iclr/2025/xu2025iclr-openrca | Peer-reviewed paper |
| S26 | Notaro, P. et al. (2020). *A Systematic Mapping Study in AIOps.* AIOPS Workshop 2020 — https://arxiv.org/abs/2012.09108 | Workshop paper |
| S27 | Zhang, L. et al. (2024). *A Survey of AIOps for Failure Management in the Era of Large Language Models* — https://arxiv.org/abs/2406.11213 | Survey (arXiv) |
| S28 | Ahmed, T. et al. (2023). *Recommending Root-Cause and Mitigation Steps for Cloud Incidents using Large Language Models* — https://arxiv.org/abs/2301.03797 (listed in the ICSE 2023 technical track) | Paper |
| S29 | Zhu, J. et al. *Loghub: A Large Collection of System Log Datasets for AI-driven Log Analytics* — https://arxiv.org/abs/2008.06448 | Dataset paper |
| S30 | Pham, L. et al. (2024). *RCAEval: A Benchmark for Root Cause Analysis of Microservice Systems with Telemetry Data* — https://arxiv.org/abs/2412.17015 | Benchmark paper |
| S31 | Chen, Y. et al. (2025). *AIOpsLab: A Holistic Framework to Design, Develop and Evaluate AI Agents for Enabling Autonomous Clouds* — https://arxiv.org/abs/2501.06706 | Paper (arXiv) |
| S32 | InfoQ (Jan 2025), Microsoft Research AIOpsLab news (MIT licence; https://github.com/microsoft/AIOpsLab) — https://www.infoq.com/news/2025/01/microsoft-reasearch-aiopslab | Tech news |
| S33 | Prometheus, "Alertmanager" — https://prometheus.io/docs/alerting/latest/alertmanager/ | Official docs |
| S34 | StackStorm (st2), event-driven automation — https://github.com/StackStorm/st2 | Open-source project |

---

## 11. Viva preparation: likely questions

Short model answers you should be able to give *in your own words* by the end of this phase.

1. **"Why not just retrieve the best runbook and run it?"** Because retrieval measures text similarity, not diagnostic fit. Our runbooks share vocabulary on purpose, so the top hit can be confidently wrong. Signals decide; retrieval only proposes. [§3.5]
2. **"Why ignore severity when deciding approval?"** Severity describes the *incident's impact*, guessed by a human. Approval protects against the *fix's risk*. A low-risk restart doesn't become risky because the alert says "high". [R4, §1.3]
3. **"Is this really an agent if there's no LLM?"** By the classic definition (perceive via sensors, act via actuators), yes: it's a goal-directed, bounded, tool-using loop that verifies its own actions. By Anthropic's LLM-era vocabulary it's closer to a workflow, and here's why that's the right trade-off… [§4]
4. **"How do you know the escalation is real?"** It compares a monotonic clock to a real deadline after a real sleep; nothing is mocked. [§5.1]
5. **"How does your system resist the 'do not roll back' log line?"** The decision function only takes metrics and deploy timestamps as inputs; log text has no path to it. That's a structural defence, recommended by recent prompt-injection research. [§6]
6. **"What does 3/3 on the golden set prove?"** That known past cases still pass; it's a regression check, not a statistical accuracy claim. [§7.1]
7. **"How does your work relate to research?"** RCACopilot also collects evidence with predefined, alert-specific handlers before any LLM step; OpenRCA shows LLM agents are still weak at RCA, so our deterministic evidence checks are a defensible choice. [§8.2]

---

## 12. Phase 2 summary

### Decisions made
- None architectural. Defaults A1 (no LLM in decision path), A3 (we author fixtures) remain in force.
- Confirmed by research: no public dataset fits the constraints → synthetic fixtures.
- Confirmed by research: scikit-learn supports TF-IDF (word/char n-grams) and LSA; BM25 and RRF are simple enough to write in stdlib.

### Unresolved
- **A1 (LLM allowed?)**, **A2 (six DoD gates)**: still unanswered from Phase 1.
- A5 (which hybrid pairing), A6 (verification tolerance), A14 (staleness policy), A7 (what a "round" is) now have concrete options to compare.

### What Phase 3 needs
- Your answers to A1/A2, if available.
- Phase 3 should compare candidate architectures against R1–R8, covering: deterministic loop vs LLM-in-the-loop; single vs multi-agent; retrieval pairing options (§3.4); staleness policies; page/approval state machine; fixture design keyed by service + timestamp.

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

## Knowledge base (Phase 2)
SRE: ICS roles, IC is not a resolver, mitigate first, draft→review→publish postmortems,
  ~70% outages from changes, "what touched it last", correlation ≠ causation.
Retrieval: TF-IDF (word/char_wb), BM25 (stdlib), LSA (TruncatedSVD), RRF k=60.
Agents: classic perceive/act definition; Anthropic workflows vs agents; ReAct loop.
Reliability: time.monotonic for deadlines; idempotency keys; command–query separation.
Security: indirect prompt injection; structural defence = untrusted text never reaches decision.
Related work: RCACopilot (handlers + LLM), OpenRCA (11.34%), AIOpsLab, RCAEval, Loghub.

## Status
Phase 1 done (analysis). Phase 2 done (domain knowledge + research). No architecture chosen.
Defaults: no LLM in decision path; we author fixtures. Unknown: six DoD gates.
Next: Phase 3, compare architectures and justify a choice.
```
