# Thresholds and tunables

Every tunable number lives in `incident_commander/config.py`. Changing one needs a note here with its
reason. The golden set is never used to tune a threshold (DETAILED_ROADMAP section 6, rule 6).

## Decision thresholds (PHASE5 9.1, frozen in v0.1, first used from v0.2)

| Name | Value | Reason |
|---|---|---|
| `LATENCY_ELEVATED_RATIO` | 2.0 x baseline | clear degradation, tolerant of noise |
| `LATENCY_NORMAL_RATIO` | 1.25 x baseline | between 1.25 and 2.0 is UNKNOWN |
| `ERROR_NORMAL_RATIO` | 2.0 x baseline | |
| `ERROR_ELEVATED_RATIO` | 3.0 x baseline | between 2.0 and 3.0 is UNKNOWN |
| `DEPLOY_WINDOW_S` | 1800 | "what touched it last": 30 min before `fired_at` |
| `LOOKBACK_S` | 21600 | 6 h, long enough to see a slow climb |
| `STEP_FRACTION` | 0.5 | one adjacent jump of at least half the final level |
| `TREND_R2` | 0.8 | gradual trend needs a good linear fit |
| `DEP_LATENCY_UNHEALTHY` / `DEP_ERROR_UNHEALTHY` | 2.0 / 3.0 | same bands as latency and error |
| `VERIFY_TOLERANCE` | 1.10 | 195/180 = 1.083 passes, 3900/180 = 21.7 fails |
| `ROUND_BUDGET` | 4 | equals the number of evidence tools |
| `APPROVAL_DEADLINE_S` | 0.3 | per page, demo value |
| `STATIC_RANKER_ORDER` | RB-102, RB-101, RB-104, RB-103 | v0.2 stub order, deliberately wrong-first so evidence visibly overrides rank |

## Simulation parameters (v0.1)

| Name | Value | Reason |
|---|---|---|
| `SAMPLE_INTERVAL_S` | 60 | PHASE5 8: series sampled every minute |
| `DATA_CLOCK_START_OFFSET_S` | 5.0 | DataClock starts at `fired_at + 5` |
| `DATA_CLOCK_TICK_S` | 2.0 | each tool call advances simulated time, so ages are reproducible |
| `RECENT_WINDOW_S` | 300 | "median of the last 5 min" |
| `TOOL_SPECS` | 60 / 60 / 300 / 3600 / 120 s | PHASE5 9.2 staleness budgets; lags 3 / 3 / 10 / 30 / 5 s |

## Fixture choices that go beyond PHASE5 (v0.1)

- `inventory-service` error rate is a flat 0.010 (its baseline), not "about 0.012". With 0.012 the
  dependency view of ALRT-9001 would show `err=1.2`, while the roadmap's expected M1 output and
  PHASE5's "healthy dependency ~ 1.0" both need 1.0. It is still "normal" for ALRT-9002 (ratio 1.0 <= 2.0).
- Alerts are one day apart (`T0`, `T0 + 1 day`, `T0 + 2 days`) so no service's incident overlaps another
  alert's 6 h lookback. `T0` is a multiple of 60 s so alerts sit on the sampling grid.
- `Observation` has an extra optional `baseline` field. PHASE5 7.3 says latency and error tools return
  "baseline in payload"; a dedicated field keeps `data` a plain tuple of points.
- `get_dependencies` reads each dependency's last 5 minutes ending at `min(at, as_of)`: with a lagging
  source it uses the latest data produced so far instead of failing.
- Golden-set services (`search`, `cart`, `auth`, `user-db`) are added with v0.6, not now.

## Choices that go beyond PHASE5 (v0.2)

- The verdict is also checked once after the loop ends, so a hypothesis confirmed by the last allowed
  round (for example a stale answer refetched fresh at round 4) still counts. PHASE4 8.3's pseudo-code
  only checks at the top of each iteration.
- Two confirmed hypotheses end the loop at once with `ambiguous_match`; more evidence cannot un-confirm a TRUE predicate.
- A stale answer is refetched once (its own round, `mode=refetch`) only if budget remains. A tool that
  returned `status=error` is not refetched: a retry of the same call adds nothing the planner can use.
- Latency/error predicates mirror each other: elevated is FALSE at or below the "normal" ratio and
  UNKNOWN in the middle band (and normal is the reverse), so 1.99x gives UNKNOWN for both.
- A constant (zero-variance) latency series is not a gradual trend (FALSE); fewer than 3 points is UNKNOWN.
- `latency_step_change` requires every point before the biggest jump to stay within `LATENCY_NORMAL_RATIO` of baseline.
- ROUND lines print the tool's predicates that appear in a hypothesis still alive at the start of the round
  (all of them in exploratory mode); `RoundRecord.values` keeps every predicate for the tool.
- Runbook `text` is a placeholder until v0.5; `follow_ups` is empty.
