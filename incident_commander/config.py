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
# Data only in v0.1; the classifier arrives in v0.3.
ACTION_PROPERTIES: dict[str, tuple[bool, bool]] = {
    "restart_service": (True, False),
    "scale_out_service": (True, False),
    "rollback_deployment": (False, True),
    "failover_dependency": (False, True),
}

# --- Escalation (PHASE5 9.4)
PRIMARY_ONCALL = "engineer-priya"
SECONDARY_ONCALL = "engineer-devon"
