"""Every tunable number, with its reason (mirrored in docs/THRESHOLDS.md)."""

from __future__ import annotations

from .types import ToolSpec

# --- Thresholds (PHASE5 9.1). Used from v0.2; defined here so they live in one place.
LATENCY_ELEVATED_RATIO = 2.0  # clear degradation, tolerant of noise
LATENCY_NORMAL_RATIO = 1.25  # between normal and elevated is UNKNOWN
ERROR_NORMAL_RATIO = 2.0
ERROR_ELEVATED_RATIO = 3.0  # between 2.0 and 3.0 is UNKNOWN
DEPLOY_WINDOW_S = 1800  # "what touched it last": 30 min before fired_at
LOOKBACK_S = 21600  # 6 h: long enough to see a slow climb
STEP_FRACTION = 0.5  # one adjacent jump >= 0.5 x final level
TREND_R2 = 0.8
DEP_LATENCY_UNHEALTHY = 2.0
DEP_ERROR_UNHEALTHY = 3.0
VERIFY_TOLERANCE = 1.10  # 195/180 = 1.083 passes, 3900/180 = 21.7 fails
ROUND_BUDGET = 4  # equals the number of evidence tools
APPROVAL_DEADLINE_S = 0.3  # per page, demo value
APPROVAL_TICK_S = 0.02  # gate poll interval (real sleep)
APPROVAL_DEMO_SLEEP_S = 0.4  # M5 demo sleep: 0.1 s past the 0.3 s deadline
VERIFY_WINDOW_S = 300  # post-fix window the verifier re-queries (simulated time)
METRIC_TOOLS = {"latency_ms": "get_latency", "error_rate": "get_error_rate"}  # alert.metric -> tool
DEMO_SECONDARY_DELAY_S = 0.1  # ALRT-9001 demo: devon approves 0.1 s after being paged
PUBLISH_RECIPIENTS = ("oncall-channel",)

# --- Stub ranker (v0.2-v0.4): deliberately wrong-first for ALRT-9001/9002, to show evidence overrides rank.
STATIC_RANKER_ORDER = ("RB-102", "RB-101", "RB-104", "RB-103")

# --- Hybrid retrieval (v0.5). Rank is a planner tie-break only; none of these decide a verdict.
RRF_K = 60  # standard reciprocal-rank-fusion constant
BM25_K1 = 1.5  # term-frequency saturation
BM25_B = 0.75  # document-length normalisation
CHAR_NGRAM_RANGE = (2, 4)  # char_wb n-gram sizes for the TF-IDF side
SMALL_MARGIN = (
    0.001  # top-2 fused gap below this = retrieval cannot separate them (two rank steps ~0.0005)
)

# --- Simulated data and clocks (PHASE5 7.2, 8)
SAMPLE_INTERVAL_S = 60  # series sampling step
DATA_CLOCK_START_OFFSET_S = 5.0  # DataClock starts at fired_at + 5
DATA_CLOCK_TICK_S = 2.0  # each tool call advances the DataClock
RECENT_WINDOW_S = 300  # "median of the last 5 min"

# --- Staleness (PHASE5 9.2): name -> (max_staleness_s, lag_s, evidence tool)
TOOL_SPECS: dict[str, ToolSpec] = {
    "get_latency": ToolSpec(60, 3.0, True),
    "get_error_rate": ToolSpec(60, 3.0, True),
    "get_deployments": ToolSpec(300, 10.0, True),
    "get_dependencies": ToolSpec(3600, 30.0, True),
    "get_logs": ToolSpec(120, 5.0, False),  # untrusted text: Scribe only
}

# --- Action properties (PHASE5 9.3): (quickly_reversible, changes_code_or_routing).
ACTION_PROPERTIES: dict[str, tuple[bool, bool]] = {
    "restart_service": (True, False),
    "scale_out_service": (True, False),
    "rollback_deployment": (False, True),
    "failover_dependency": (False, True),
}

# --- Escalation (PHASE5 9.4)
PRIMARY_ONCALL = "engineer-priya"
SECONDARY_ONCALL = "engineer-devon"
