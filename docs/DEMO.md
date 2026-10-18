# Demo scripts

Both scripts were dry-run on Windows with `.venv` (Python 3.12.10, scikit-learn 1.9.1). Activate first:
`.venv\Scripts\activate`. Timings are the measured wall-clock times of the commands, not including narration.

## Graded demo (about 5 minutes)

1. `python -m incident_commander.dod all` (about 30 s). G1-G6 all PASS: show rigour first.
2. `python -m incident_commander run --all` (about 10 s). Narrate by milestone:
   - M1 freshness; M2 retrieval cannot decide (read the top-2 margin);
   - M3 three investigations: 9001 evidence beats the wrong top rank; 9003 uses all 4 rounds;
   - M4 same severity, opposite approval; M5 a real 0.4 s sleep and escalation priya -> devon;
   - M6 idempotent retry and verification both ways (195 ms resolved, 3900 ms reopened);
   - M7 draft with `notified=[]`; M8 golden 3/3 and the attack unchanged.
3. Open the planted log line in the draft's "Untrusted log excerpts" section: shown, labelled, never read by a decision.
4. Q&A anchors: PHASE4 section 18 (why each component exists), PHASE4 section 22 and PHASE3 section 6.2 (viva answers).

## Extended demo (about 5 minutes)

1. `python -m incident_commander.dod all`: still G1-G6 PASS with `ic_plus` present (X1).
2. `python -m ic_plus run ALRT-9001 --approver cli --deadline 20`: you type `approve` within 20 s (the default 0.3 s deadline is too short for a human).
3. With Ollama running (`ollama pull llama3.2`):
   `python -m ic_plus run ALRT-9001 --llm local --llm-url http://localhost:11434/v1 --model llama3.2`.
   The AI narrative appears under its label; the DECISION lines equal the graded run.
   The small local model can write wrong prose (in the rehearsal it said a restart "failed" when it resolved).
   Use that as the point: the text is labelled non-authoritative and no decision reads it.
4. `python -m ic_plus evaluate --llm local --llm-url http://localhost:11434/v1 --model llama3.2` (about 90 s with
   llama3.2 on this machine): ends with `decisions_changed=0` (X3). Skip it live if short of time and show
   `traces/v1.3-live-evaluate.txt`.
5. Stop Ollama and re-run step 3: `llm: unavailable, deterministic fallback`, everything else unchanged (X2).
6. `python -m ic_plus scenario stale_data` and `python -m ic_plus scenario fix_fails`: honest `no_confident_match`
   and `reopened`.

## Without a model

Use `--llm off` (the default) for steps 2 and 6, and show the recorded runs instead of steps 3 and 4:
`traces/v1.2-live.txt` (`run --all`, local model), `traces/v1.3-live-evaluate.txt` (`evaluate`, local model)
and `traces/v1.3-evaluate.txt` (no server, fallback).
